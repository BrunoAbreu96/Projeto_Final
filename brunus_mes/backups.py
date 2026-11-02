"""Cópias consistentes SQLite e restauro transacional, reservados ao master.

O restauro altera o conteúdo da base aberta, sem substituir o ficheiro que o
dashboard/simulador utilizam. Convém parar o simulador para que novos eventos
não sejam acrescentados imediatamente depois do ponto restaurado.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import secrets
import sqlite3

from .database import (
    SCHEMA_VERSION, TABLE_COLUMNS, MigrationError, _apply_schema, _insert_rows,
    _restore_sequences, connect, get_db_path,
)


class BackupError(ValueError):
    """A cópia ou a base não é compatível; o restauro não foi aplicado."""


def _authorize(profile):
    if profile != "master":
        raise PermissionError("Só o perfil master pode criar ou restaurar cópias de segurança.")


def _directory(db_path: Path, backup_dir=None) -> Path:
    folder = Path(backup_dir).expanduser() if backup_dir is not None else db_path.parent / "backups"
    return folder.resolve()


def _pattern(db_path: Path):
    return re.compile(re.escape(db_path.stem) + r"\.backup_\d{8}_\d{6}_\d{6}_[0-9a-f]{6}\.db\Z")


def _signature(conn):
    # Compara também CHECKs, índices e FKs, não apenas nomes de tabelas.
    return [
        (kind, name, table, sql.strip())
        for kind, name, table, sql in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
    ]


def _validate(conn):
    """Valida um snapshot isolado e devolve dados sem os corrigir."""
    if [tuple(row) for row in conn.execute("PRAGMA integrity_check")] != [("ok",)]:
        raise BackupError("A base não passou a verificação de integridade.")
    canonical = sqlite3.connect(":memory:")
    try:
        canonical.execute("PRAGMA foreign_keys = ON")
        _apply_schema(canonical)
        if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION or _signature(conn) != _signature(canonical):
            raise BackupError("Esquema incompatível ou objetos adicionais: reveja a base antes de restaurar.")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise BackupError("A base contém referências inválidas entre avarias e estações.")
        rows = {
            table: conn.execute(f'SELECT {", ".join(columns)} FROM "{table}" ORDER BY id').fetchall()
            for table, columns in TABLE_COLUMNS.items()
        }
        # Reinsere num esquema canónico para verificar todos os CHECKs mesmo
        # quando o ficheiro foi escrito por uma ferramenta externa.
        _insert_rows(canonical, rows)
        sequences = dict(conn.execute("SELECT name, seq FROM sqlite_sequence"))
        if any(rows[table] and table not in sequences for table in ("historico_producao", "registo_avarias")):
            raise BackupError("Falta uma sequência de numeração para os IDs existentes.")
        for table, sequence in sequences.items():
            if table not in {"historico_producao", "registo_avarias"} or not isinstance(sequence, int) or sequence < 0:
                raise BackupError("Sequência de numeração inválida na base.")
            highest = max((record[0] for record in rows[table]), default=0)
            if sequence < highest:
                raise BackupError("Sequência de numeração inferior aos IDs existentes.")
        inconsistent = canonical.execute("""
            SELECT c.id FROM cabines c WHERE c.status != CASE WHEN EXISTS (
                SELECT 1 FROM registo_avarias r WHERE r.cabine_id=c.id AND r.status='ATIVO'
            ) THEN 'ERRO' ELSE 'OK' END LIMIT 1
        """).fetchone()
        if inconsistent:
            raise BackupError("O estado de uma estação não corresponde às suas avarias ativas.")
        return rows, sequences
    except MigrationError as exc:
        raise BackupError(f"Dados inválidos na cópia: {exc}") from exc
    finally:
        canonical.close()


def _snapshot(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"Base de dados não encontrada: {path}")
    memory = sqlite3.connect(":memory:")
    source = None
    try:
        source = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=15)
        source.backup(memory)
        _validate(memory)
    except BaseException:
        memory.close()
        raise
    finally:
        if source is not None:
            source.close()
    return memory


def _save_snapshot(snapshot, db_path: Path, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = folder / f"{db_path.stem}.backup_{stamp}_{secrets.token_hex(3)}.db"
    # A reserva exclusiva impede que um ficheiro existente seja substituído.
    with target.open("xb"):
        pass
    try:
        destination = sqlite3.connect(target)
        try:
            snapshot.backup(destination)
        finally:
            destination.close()
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def create_backup(profile, path=None, backup_dir=None) -> Path:
    """Guarda uma cópia consistente e validada, sem credenciais da aplicação."""
    _authorize(profile)
    db_path = get_db_path(path)
    snapshot = _snapshot(db_path)
    try:
        return _save_snapshot(snapshot, db_path, _directory(db_path, backup_dir))
    finally:
        snapshot.close()


def list_backups(path=None, backup_dir=None) -> list[Path]:
    """Lista cópias compatíveis dessa base; ficheiros inválidos são excluídos."""
    db_path = get_db_path(path)
    folder = _directory(db_path, backup_dir)
    if not folder.is_dir():
        return []
    candidates = []
    for candidate in folder.iterdir():
        if candidate.is_symlink() or not candidate.is_file() or not _pattern(db_path).fullmatch(candidate.name):
            continue
        try:
            snapshot = _snapshot(candidate)
        except (sqlite3.Error, BackupError, OSError):
            continue
        else:
            snapshot.close()
            candidates.append(candidate)
    return sorted(candidates, key=lambda value: value.name, reverse=True)


def _replace_contents(conn, rows, sequences):
    for table in ("registo_avarias", "historico_producao", "sessao_ativa", "cabines"):
        conn.execute(f'DELETE FROM "{table}"')
    conn.execute("DELETE FROM sqlite_sequence")
    _insert_rows(conn, rows)
    _restore_sequences(conn, sequences)
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        raise BackupError("Referências inválidas; o restauro foi desfeito.")


def restore_backup(backup_path, profile, confirmed=False, path=None, backup_dir=None) -> Path:
    """Restaura dados atomicamente e devolve a cópia do estado pré-restauro.

    Só aceita cópias válidas da pasta de backups dessa base. Uma falha desfaz
    todas as escritas; nunca elimina a cópia do estado anterior já guardada.
    """
    _authorize(profile)
    if confirmed is not True:
        raise BackupError("É necessária confirmação explícita para restaurar a cópia de segurança.")
    db_path = get_db_path(path)
    if not db_path.is_file():
        raise FileNotFoundError(f"Base de dados não encontrada: {db_path}")
    folder = _directory(db_path, backup_dir)
    candidate = Path(backup_path).expanduser()
    if candidate.is_symlink() or candidate.resolve().parent != folder or not _pattern(db_path).fullmatch(candidate.name):
        raise BackupError("Selecione uma cópia gerada para esta base na sua pasta de backups.")
    snapshot = _snapshot(candidate.resolve())
    try:
        rows, sequences = _validate(snapshot)
        with connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            # A ligação write bloqueia outros escritores. A ligação de leitura
            # separada consegue obter o snapshot confirmado sem bloquear backup.
            _validate(conn)
            previous = _snapshot(db_path)
            try:
                recovery_path = _save_snapshot(previous, db_path, folder)
            finally:
                previous.close()
            _replace_contents(conn, rows, sequences)
        return recovery_path
    finally:
        snapshot.close()
