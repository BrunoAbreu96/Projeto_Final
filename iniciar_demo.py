"""Arranque local do BRUNUS MES com dados e credenciais de demonstração isolados."""
from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    raise SystemExit("O BRUNUS MES precisa de Python 3.11 ou superior.")

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import secrets
import socket
import sqlite3
import subprocess
import time
import tomllib
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
PROFILES = ("operador", "tecnico", "master")


@dataclass
class DemoSession:
    runtime: Path
    database: Path
    secrets_file: Path
    credentials: dict[str, str]
    new_database: bool


def _write_credentials(runtime: Path) -> dict[str, str]:
    credentials = {profile: f"Demo-{secrets.token_urlsafe(12)}" for profile in PROFILES}
    hashes = []
    for profile, password in credentials.items():
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
        hashes.append(f'{profile}_hash = "pbkdf2_sha256$600000${salt}${digest}"')
    (runtime / "acesso_demo.json").write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
    (runtime / ".streamlit" / "secrets.toml").write_text("[credenciais]\n" + "\n".join(hashes) + "\n", encoding="utf-8")
    return credentials


def _read_credentials(runtime: Path) -> dict[str, str]:
    from brunus_mes.auth import verify_password

    credentials = json.loads((runtime / "acesso_demo.json").read_text(encoding="utf-8"))
    saved = tomllib.loads((runtime / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))["credenciais"]
    if not isinstance(credentials, dict) or not isinstance(saved, dict) or not all(
        verify_password(credentials.get(profile), saved.get(f"{profile}_hash")) for profile in PROFILES
    ):
        raise ValueError("Credenciais de demonstração inconsistentes.")
    return {profile: credentials[profile] for profile in PROFILES}


def _seed_events(database: Path, now: datetime) -> None:
    from brunus_mes.reporting import shift_interval
    from brunus_mes.services import resolve_breakdown
    from simulador_continuo import ciclo_fabrica_avancado

    rng = random.Random(42)
    yesterday = now.date() - timedelta(days=1)
    for shift in (1, 2, 3):
        start, _ = shift_interval(yesterday, shift)
        for line in ("Main A", "Main B"):
            for minute, event in enumerate(("OK", "OK", "REJEITADA"), start=1):
                ciclo_fabrica_avancado(database, event, rng, start + timedelta(minutes=minute), line)
        failure = ciclo_fabrica_avancado(database, "ERRO", rng, start + timedelta(minutes=5), "Main A")
        resolve_breakdown(failure["id"], "tecnico", database, start + timedelta(minutes=10))
    for line in ("Main A", "Main B"):
        ciclo_fabrica_avancado(database, "OK", rng, now, line)
    ciclo_fabrica_avancado(database, "ERRO", rng, now, "Main A")


def prepare_demo(root: Path = ROOT, *, now: datetime | None = None, regenerate_credentials: bool = False) -> DemoSession:
    """Cria uma demonstração só na primeira utilização; nunca limpa uma base existente."""
    from brunus_mes.database import check_database, initialize_database, seed_demo_stations

    moment = datetime.now() if now is None else now
    if moment.tzinfo is not None:
        raise ValueError("Use uma data local sem fuso horário.")
    runtime = Path(root).resolve() / "data" / "demo"
    config_dir = runtime / ".streamlit"
    config_dir.mkdir(parents=True, exist_ok=True)
    # Protege também a pasta criada num clone que ainda não tenha esta regra global.
    (runtime / ".gitignore").write_text("*\n", encoding="utf-8")
    secrets_file = config_dir / "secrets.toml"
    access_file = runtime / "acesso_demo.json"
    if regenerate_credentials or (not secrets_file.exists() and not access_file.exists()):
        credentials = _write_credentials(runtime)
    else:
        try:
            credentials = _read_credentials(runtime)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError("Não foi possível ler o acesso da demonstração. Use --regenerate-credentials para redefinir apenas esse acesso.") from exc
    (config_dir / "config.toml").write_text(
        '[server]\naddress = "127.0.0.1"\nheadless = true\n'
        '[browser]\ngatherUsageStats = false\n'
        '[secrets]\nfiles = ' + json.dumps([secrets_file.as_posix()]) + "\n",
        encoding="utf-8",
    )
    database = runtime / "demo.db"
    new_database = not database.exists()
    if new_database:
        initialize_database(database)
        seed_demo_stations(database)
        _seed_events(database, moment)
    else:
        check_database(database)
    return DemoSession(runtime, database, secrets_file, credentials, new_database)


def command_plan(session: DemoSession, port: int, *, manual: bool = False,
                 python: str | None = None, root: Path = ROOT, environ: dict | None = None) -> tuple[dict[str, list[str]], dict]:
    """Comandos sem shell; ambos recebem a mesma base e o modo de demonstração."""
    executable = python or sys.executable
    commands = {"dashboard": [executable, "-m", "streamlit", "run", str(Path(root) / "dashboard.py"),
        "--server.address", "127.0.0.1", "--server.port", str(port), "--server.headless", "true",
        "--browser.gatherUsageStats", "false", "--secrets.files", str(session.secrets_file)]}
    if not manual:
        commands["simulator"] = [executable, str(Path(root) / "simulador_continuo.py"), "--db", str(session.database)]
    environment = dict(os.environ if environ is None else environ)
    environment.update(BRUNUS_DB_PATH=str(session.database), BRUNUS_DEMO_MODE="1", PYTHONUTF8="1")
    return commands, environment


def _healthy(port: int) -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=0.5) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


@contextmanager
def _launcher_lock(runtime: Path, port: int | None):
    """Bloqueio do sistema operativo; libertado mesmo se o lançador terminar abruptamente."""
    runtime.mkdir(parents=True, exist_ok=True)
    lock = runtime / "launcher.lock"
    with lock.open("a+b") as file:
        if file.seek(0, 2) == 0:
            file.write(b"\0")
            file.flush()
        file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("A demonstração já está aberta ou a iniciar. Use a janela existente.") from exc
        try:
            # Um servidor pode continuar aberto se a janela anterior foi forçada a terminar.
            try:
                previous = json.loads(file.read())
                previous_port = previous.get("port")
            except (ValueError, TypeError, AttributeError):
                previous_port = None
            if isinstance(previous_port, int) and previous_port in range(8501, 8521) and _healthy(previous_port):
                raise RuntimeError(f"O servidor anterior ainda responde em http://127.0.0.1:{previous_port}/. Feche-o antes de iniciar outra demonstração.")
            file.seek(0)
            file.truncate()
            file.write(json.dumps({"pid": os.getpid(), "port": port}).encode())
            file.flush()
            yield
        finally:
            file.seek(0)
            if os.name == "nt":
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def _available_port() -> int:
    for port in range(8501, 8521):
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    raise RuntimeError("As portas locais 8501–8520 estão ocupadas. Feche uma demonstração anterior e volte a tentar.")


def _stop_children(children: dict, *, windows: bool | None = None) -> None:
    """Termina apenas os processos criados neste arranque e os seus descendentes."""
    on_windows = os.name == "nt" if windows is None else windows
    for child in children.values():
        if child.poll() is None:
            if on_windows:
                # O executável de um venv pode ser um wrapper com um Python filho.
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                child.terminate()
    for child in children.values():
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def _raise_if_stopped(children: dict) -> None:
    for name, child in children.items():
        code = child.poll()
        if code is not None:
            raise RuntimeError(f"O processo {name} terminou inesperadamente com código {code}. Consulte as mensagens nesta janela.")


def _run(session: DemoSession, port: int, *, manual: bool, no_browser: bool) -> None:
    commands, environment = command_plan(session, port, manual=manual)
    children = {}
    try:
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {}
        for name, command in commands.items():
            children[name] = subprocess.Popen(command, cwd=session.runtime, env=environment, stdin=subprocess.DEVNULL, **options)
        deadline = time.monotonic() + 30
        while not _healthy(port):
            _raise_if_stopped(children)
            if time.monotonic() >= deadline:
                raise RuntimeError("O dashboard não respondeu em 30 segundos. Consulte as mensagens nesta janela.")
            time.sleep(0.2)
        address = f"http://127.0.0.1:{port}/"
        print(f"\nAplicação: {address}\nMantenha esta janela aberta. Para terminar, prima Ctrl+C.", flush=True)
        if not no_browser:
            webbrowser.open(address)
        while True:
            _raise_if_stopped(children)
            time.sleep(0.5)
    finally:
        _stop_children(children)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manual", action="store_true", help="Só dashboard; gere eventos no painel Demonstração como master.")
    parser.add_argument("--no-browser", action="store_true", help="Não abrir o navegador automaticamente.")
    parser.add_argument("--prepare-only", action="store_true", help="Preparar a demonstração sem iniciar processos.")
    parser.add_argument("--regenerate-credentials", action="store_true", help="Redefinir apenas as credenciais sintéticas da demonstração.")
    args = parser.parse_args(argv)
    try:
        if not args.prepare_only:
            missing = [name for name in ("streamlit", "streamlit_autorefresh", "pandas", "reportlab") if importlib.util.find_spec(name) is None]
            if missing:
                raise RuntimeError("Faltam dependências. Instale-as neste Python com: python -m pip install -r requirements.txt")
        port = None if args.prepare_only else _available_port()
        with _launcher_lock(ROOT / "data" / "demo", port):
            session = prepare_demo(regenerate_credentials=args.regenerate_credentials)
            print("\nBRUNUS MES — demonstração local com dados sintéticos")
            print(f"Base: {session.database}\nAcesso guardado apenas neste computador: {session.runtime / 'acesso_demo.json'}")
            for profile, password in session.credentials.items():
                print(f"  {profile}: {password}")
            print("Modo manual: use Gerar evento como master." if args.manual else "Modo contínuo: o simulador gera eventos automaticamente.", flush=True)
            if not args.prepare_only:
                _run(session, port, manual=args.manual, no_browser=args.no_browser)
    except KeyboardInterrupt:
        print("\nDemonstração terminada.")
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
        print(f"\nNão foi possível iniciar: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
