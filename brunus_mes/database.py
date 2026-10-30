"""Ligações SQLite, esquema único e migração explícita sem perda de histórico."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import os
from pathlib import Path
import sqlite3
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = ROOT / "sql" / "criar_base_dados.sql"
SCHEMA_VERSION = 1
TABLE_COLUMNS = {
    "cabines": ("id", "main_line", "estacao", "nome_processo", "status"),
    "historico_producao": ("id", "main_line", "timestamp", "status_peca", "tempo_ciclo"),
    "registo_avarias": (
        "id", "cabine_id", "robo_afetado", "codigo_erro", "descricao", "causa_provavel",
        "timestamp_inicio", "timestamp_fim", "status",
    ),
    "sessao_ativa": ("id", "perfil", "timestamp"),
}


class MigrationRequired(RuntimeError):
    """A base existente precisa da migração explícita antes de ser utilizada."""


class MigrationError(RuntimeError):
    """Dados legados incompatíveis: corrigir a origem antes de repetir a migração."""


def get_db_path(path=None) -> Path:
    configured = path if path is not None else os.environ.get("BRUNUS_DB_PATH")
    return Path(configured).expanduser().resolve() if configured else ROOT / "data" / "brunus_dev.db"


@contextmanager
def connect(path=None) -> Iterator[sqlite3.Connection]:
    """Uma ligação por operação; fecha, confirma ou desfaz sempre a transação."""
    conn = sqlite3.connect(get_db_path(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _tables(conn) -> set[str]:
    return {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )}


def _check_schema(conn) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version != SCHEMA_VERSION or not set(TABLE_COLUMNS).issubset(_tables(conn)):
        raise MigrationRequired("Base desatualizada. Execute python -m brunus_mes.database migrate --db CAMINHO")
    fk = conn.execute("PRAGMA foreign_key_list(registo_avarias)").fetchall()
    if not any(row[2] == "cabines" and row[3] == "cabine_id" and row[4] == "id" for row in fk):
        raise MigrationRequired("O esquema não contém a relação entre avarias e cabines.")


def check_database(path=None) -> None:
    """Verifica em modo estritamente de leitura; nunca cria um ficheiro."""
    db_path = get_db_path(path)
    if not db_path.is_file():
        raise FileNotFoundError(f"Base de dados não encontrada: {db_path}")
    conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    try:
        _check_schema(conn)
    finally:
        conn.close()


def _apply_schema(conn) -> None:
    # executescript faz COMMIT implícito; cada instrução preserva a transação.
    statement = ""
    for line in SCHEMA_FILE.read_text(encoding="utf-8").splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            conn.execute(statement)
            statement = ""
    if statement.strip():
        raise RuntimeError("O script SQL contém uma instrução incompleta.")


def initialize_database(path=None) -> Path:
    db_path = get_db_path(path)
    if db_path.exists():
        with connect(db_path) as conn:
            if _tables(conn):
                _check_schema(conn)
                return db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _apply_schema(conn)
    return db_path


def seed_demo_stations(path=None) -> None:
    """Adiciona as oito estações fictícias sem substituir registos existentes."""
    check_database(path)
    processes = (
        "Alimentação & Pick/Place Frame", "Montagem e Aparafusamento PCB",
        "União Óptica da Lente TFT", "Teste de Fim de Linha (EOL)",
    )
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for offset, main_line in ((0, "Main A"), (4, "Main B")):
            for number, process in enumerate(processes, start=1):
                conn.execute(
                    "INSERT OR IGNORE INTO cabines (id, main_line, estacao, nome_processo) VALUES (?, ?, ?, ?)",
                    (offset + number, main_line, f"Estação {number}", process),
                )


def _legacy_rows(conn) -> dict:
    present = _tables(conn)
    if "cabines" not in present:
        raise MigrationError("A base não tem a tabela cabines; não foi alterada.")
    rows = {}
    for table, columns in TABLE_COLUMNS.items():
        if table not in present:
            rows[table] = []
            continue
        actual = tuple(row[1] for row in conn.execute(f'PRAGMA table_info("{table}")'))
        if set(actual) != set(columns):
            raise MigrationError(f"Colunas não suportadas em {table}; é necessária revisão manual.")
        rows[table] = []
        for row in conn.execute(f'SELECT {", ".join(columns)} FROM "{table}"'):
            values = list(row)
            if table == "registo_avarias" and values[-1] == "RESOLVED":
                values[-1] = "RESOLVIDO"
            rows[table].append(tuple(values))
    return rows


def _check_legacy_layout(conn) -> None:
    """Recusa extensões desconhecidas em vez de as eliminar ou reescrever."""
    unknown_tables = _tables(conn) - set(TABLE_COLUMNS)
    if unknown_tables:
        raise MigrationError("Tabelas adicionais exigem revisão manual: " + ", ".join(sorted(unknown_tables)))
    standard_indexes = {"idx_producao_timestamp", "idx_avarias_cabine_status", "idx_avarias_intervalo"}
    for row in conn.execute("SELECT type, name FROM sqlite_master WHERE type IN ('view', 'trigger', 'index') AND sql IS NOT NULL"):
        object_type, name = row
        if object_type != "index" or name not in standard_indexes:
            raise MigrationError(f"Objeto adicional exige revisão manual: {object_type} {name}")


def _sequences(conn) -> dict:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'").fetchone():
        return {}
    return {row[0]: row[1] for row in conn.execute("SELECT name, seq FROM sqlite_sequence")
            if row[0] in TABLE_COLUMNS}


def _restore_sequences(conn, sequences) -> None:
    for table, high_water in sequences.items():
        current = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)).fetchone()
        if current is None:
            conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (table, high_water))
        elif current[0] < high_water:
            conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (high_water, table))


def _insert_rows(conn, rows) -> None:
    for table, columns in TABLE_COLUMNS.items():
        placeholders = ", ".join("?" for _ in columns)
        for values in rows[table]:
            try:
                conn.execute(
                    f'INSERT INTO "{table}" ({", ".join(columns)}) VALUES ({placeholders})', values
                )
            except sqlite3.IntegrityError as exc:
                raise MigrationError(f"Dados inválidos em {table}, id={values[0]}: {exc}") from exc


def migrate_database(path=None) -> Path | None:
    """Preserva histórico; normaliza RESOLVED e deriva estados das avarias ativas."""
    db_path = get_db_path(path)
    if not db_path.is_file():
        raise FileNotFoundError(f"Base de dados não encontrada: {db_path}")
    with connect(db_path) as conn:
        try:
            _check_schema(conn)
        except MigrationRequired:
            pass
        else:
            return None
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise MigrationError("A base foi criada por uma versão mais recente; não foi alterada.")
        conn.execute("BEGIN IMMEDIATE")
        _check_legacy_layout(conn)
        sequences = _sequences(conn)
        rows = _legacy_rows(conn)
        validator = sqlite3.connect(":memory:")
        validator.execute("PRAGMA foreign_keys = ON")
        try:
            _apply_schema(validator)
            _insert_rows(validator, rows)
        finally:
            validator.close()
        # A reserva de escrita impede alterações concorrentes durante o backup e a migração.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = db_path.with_name(f"{db_path.stem}.backup_{stamp}{db_path.suffix}")
        source = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        present = _tables(conn)
        for table in TABLE_COLUMNS:
            if table in present:
                conn.execute(f'ALTER TABLE "{table}" RENAME TO "{table}_legacy_migration"')
        _apply_schema(conn)
        _insert_rows(conn, rows)
        # Corrige estados atuais que o antigo fluxo de reparação podia deixar incoerentes.
        # As ocorrências e os seus timestamps históricos não são modificados.
        conn.execute("""UPDATE cabines SET status = CASE WHEN EXISTS (
            SELECT 1 FROM registo_avarias r WHERE r.cabine_id = cabines.id AND r.status = 'ATIVO'
        ) THEN 'ERRO' ELSE 'OK' END""")
        # Remover primeiro a tabela filha, para respeitar qualquer FK legada.
        for table in ("registo_avarias", "historico_producao", "sessao_ativa", "cabines"):
            if table in present:
                conn.execute(f'DROP TABLE "{table}_legacy_migration"')
        _restore_sequences(conn, sequences)
        _apply_schema(conn)
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise MigrationError("Referências inválidas: as alterações foram desfeitas.")
    return backup_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Preparar ou migrar explicitamente uma base BRUNUS MES.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "migrate"):
        command = commands.add_parser(name)
        command.add_argument("--db", help="Caminho da base; alternativa: BRUNUS_DB_PATH")
        if name == "init":
            command.add_argument("--demo", action="store_true", help="Adicionar oito estações de demonstração")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            path = initialize_database(args.db)
            if args.demo:
                seed_demo_stations(path)
            print(f"Base preparada: {path}")
        else:
            backup = migrate_database(args.db)
            print(f"Migração concluída. Backup: {backup}" if backup else "O esquema já está atualizado.")
    except (MigrationRequired, MigrationError, FileNotFoundError, sqlite3.Error) as exc:
        parser.exit(1, f"Erro: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
