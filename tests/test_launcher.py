"""Preparação isolada e plano de arranque; sem servidores ou navegador reais."""
from datetime import date, datetime
import json
import tomllib
from unittest.mock import Mock, call

import pytest

from brunus_mes.auth import verify_password
from brunus_mes.database import connect
from brunus_mes.reporting import build_shift_report
import iniciar_demo as launcher
from iniciar_demo import DemoSession, command_plan, prepare_demo

NOW = datetime(2026, 11, 2, 9, 30)


def test_prepare_creates_isolated_demo_with_three_historical_shifts(tmp_path):
    real_database = tmp_path / "data" / "brunus_dev.db"
    real_database.parent.mkdir()
    real_database.write_bytes(b"original intocavel")
    real_secrets = tmp_path / ".streamlit" / "secrets.toml"
    real_secrets.parent.mkdir()
    real_secrets.write_text("credenciais originais", encoding="utf-8")
    session = prepare_demo(tmp_path, now=NOW)
    assert session.new_database
    assert session.database == tmp_path / "data" / "demo" / "demo.db"
    assert real_database.read_bytes() == b"original intocavel"
    assert real_secrets.read_text(encoding="utf-8") == "credenciais originais"
    with connect(session.database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM cabines").fetchone()[0] == 8
        assert conn.execute("SELECT COUNT(*) FROM historico_producao").fetchone()[0] == 20
        assert conn.execute("SELECT COUNT(*) FROM registo_avarias WHERE status='ATIVO'").fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    for shift in (1, 2, 3):
        report = build_shift_report(date(2026, 11, 1), shift, session.database, NOW)
        assert report.total_pieces == 6
        assert report.mttr_seconds == 300
    config = tomllib.loads((session.runtime / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["secrets"]["files"] == [session.secrets_file.as_posix()]
    assert config["server"]["address"] == "127.0.0.1"


def test_restart_preserves_history_credentials_and_station_changes(tmp_path):
    session = prepare_demo(tmp_path, now=NOW)
    before = session.secrets_file.read_bytes()
    with connect(session.database) as conn:
        conn.execute("UPDATE cabines SET nome_processo='Processo de ensaio' WHERE id=1")
        conn.execute("DELETE FROM historico_producao")
    restarted = prepare_demo(tmp_path, now=datetime(2026, 11, 3, 10))
    assert not restarted.new_database
    assert restarted.credentials == session.credentials
    assert restarted.secrets_file.read_bytes() == before
    with connect(restarted.database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM historico_producao").fetchone()[0] == 0
        assert conn.execute("SELECT nome_processo FROM cabines WHERE id=1").fetchone()[0] == "Processo de ensaio"


def test_explicit_regeneration_changes_only_demo_access(tmp_path):
    session = prepare_demo(tmp_path, now=NOW)
    before = session.database.read_bytes()
    regenerated = prepare_demo(tmp_path, now=NOW, regenerate_credentials=True)
    assert regenerated.credentials != session.credentials
    assert regenerated.database.read_bytes() == before
    hashes = tomllib.loads(regenerated.secrets_file.read_text(encoding="utf-8"))["credenciais"]
    for profile, password in regenerated.credentials.items():
        assert verify_password(password, hashes[f"{profile}_hash"])
        assert hashes[f"{profile}_hash"].startswith("pbkdf2_sha256$600000$")


def test_incomplete_credentials_fail_without_silent_reset(tmp_path):
    session = prepare_demo(tmp_path, now=NOW)
    session.secrets_file.unlink()
    with pytest.raises(ValueError, match="regenerate-credentials"):
        prepare_demo(tmp_path, now=NOW)
    assert json.loads((session.runtime / "acesso_demo.json").read_text(encoding="utf-8")) == session.credentials


def test_command_plan_overrides_real_database_and_uses_only_demo_secrets(tmp_path):
    session = prepare_demo(tmp_path, now=NOW)
    environment = {"BRUNUS_DB_PATH": "outra-base.db", "PATH": "preservado"}
    commands, child_env = command_plan(session, 8510, python="python de teste", root=tmp_path, environ=environment)
    assert environment["BRUNUS_DB_PATH"] == "outra-base.db"
    assert child_env["BRUNUS_DB_PATH"] == str(session.database)
    assert child_env["BRUNUS_DEMO_MODE"] == "1"
    assert child_env["PATH"] == "preservado"
    assert commands["dashboard"][0] == "python de teste"
    assert commands["dashboard"][-2:] == ["--secrets.files", str(session.secrets_file)]
    assert commands["simulator"][-2:] == ["--db", str(session.database)]
    manual_commands, _ = command_plan(session, 8510, manual=True)
    assert list(manual_commands) == ["dashboard"]


def test_windows_cleanup_targets_only_own_process_trees(monkeypatch):
    dashboard = Mock(pid=401)
    simulator = Mock(pid=402)
    finished = Mock(pid=403)
    dashboard.poll.return_value = simulator.poll.return_value = None
    finished.poll.return_value = 0
    run = Mock()
    monkeypatch.setattr(launcher.subprocess, "run", run)
    launcher._stop_children({"dashboard": dashboard, "simulator": simulator, "finished": finished}, windows=True)
    assert [item.args[0] for item in run.call_args_list] == [
        ["taskkill", "/PID", "401", "/T", "/F"],
        ["taskkill", "/PID", "402", "/T", "/F"],
    ]
    dashboard.terminate.assert_not_called()
    simulator.terminate.assert_not_called()
    assert dashboard.wait.call_args == call(timeout=3)


def test_process_exit_after_health_is_error_and_cleans_up(tmp_path, monkeypatch):
    session = DemoSession(tmp_path, tmp_path / "demo.db", tmp_path / "secrets.toml", {}, False)
    child = Mock(pid=404)
    child.poll.return_value = 7
    monkeypatch.setattr(launcher.subprocess, "Popen", Mock(return_value=child))
    monkeypatch.setattr(launcher, "_healthy", lambda port: True)
    cleanup = Mock()
    monkeypatch.setattr(launcher, "_stop_children", cleanup)
    with pytest.raises(RuntimeError, match="dashboard.*código 7"):
        launcher._run(session, 8501, manual=True, no_browser=True)
    cleanup.assert_called_once_with({"dashboard": child})
