from pathlib import Path
import sqlite3

import pytest

from brunus_mes.database import (
    MigrationError, MigrationRequired, check_database, connect, get_db_path,
    initialize_database, migrate_database, seed_demo_stations,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "data" / "synthetic.db"
    initialize_database(path)
    seed_demo_stations(path)
    return path


def test_new_schema_and_each_connection_enforce_foreign_keys(db):
    for _ in range(2):
        with connect(db) as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("""INSERT INTO registo_avarias
                    (cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, status)
                    VALUES (999, 'Robô 1', 'E1', 'Sintético', 'Teste', '2026-10-30T09:00:00', 'ATIVO')""")
    check_database(db)


@pytest.mark.parametrize("column,value", [
    ("main_line", None), ("main_line", " "), ("timestamp", "inválido"),
    ("timestamp", "2026-02-30T09:00:00"), ("timestamp", "2026-10-30"),
    ("timestamp", "2026-10-30T09:00:00+01:00"), ("timestamp", "2026-10-30T09:00:00Z"),
    ("timestamp", "2026-10-30T24:00:00"), ("timestamp", "2026-10-30T09:60:00"),
    ("timestamp", "2026-10-30T09:00:60"), ("timestamp", "2026-10-30T09:00:00."),
    ("timestamp", "2026-10-30T09:00:00.a"), ("timestamp", "2026-10-30T09:00:00.1234567"),
    ("timestamp", "0000-10-30T09:00:00"),
    ("status_peca", "ERRO"), ("tempo_ciclo", 0), ("tempo_ciclo", -1),
    ("tempo_ciclo", "texto"), ("tempo_ciclo", float("inf")),
])
def test_reject_invalid_production(db, column, value):
    values = {"main_line": "Main A", "timestamp": "2026-10-30T09:00:00", "status_peca": "OK", "tempo_ciclo": 10}
    values[column] = value
    with connect(db) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES (?, ?, ?, ?)", tuple(values.values()))


@pytest.mark.parametrize("status,end", [
    ("ATIVO", "2026-10-30T10:00:00"), ("RESOLVIDO", None),
    ("RESOLVIDO", "2026-10-30T08:59:59"), ("RESOLVIDO", "texto"), ("OUTRO", None),
])
def test_reject_inconsistent_breakdown_dates_and_status(db, status, end):
    with connect(db) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("""INSERT INTO registo_avarias
            (cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, timestamp_fim, status)
            VALUES (1, 'Robô 1', 'E1', 'Sintético', 'Teste', '2026-10-30T09:00:00', ?, ?)""", (end, status))


def test_configurable_path_and_readonly_check_never_creates(tmp_path, monkeypatch):
    path = tmp_path / "not-created" / "test.db"
    monkeypatch.setenv("BRUNUS_DB_PATH", str(path))
    assert get_db_path() == path
    with pytest.raises(FileNotFoundError):
        check_database()
    assert not path.parent.exists()
    initialize_database()
    assert path.is_file()


def create_legacy(path, invalid=False):
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE cabines (id INTEGER PRIMARY KEY, main_line TEXT, estacao TEXT, nome_processo TEXT, status TEXT);
            CREATE TABLE historico_producao (id INTEGER PRIMARY KEY AUTOINCREMENT, main_line TEXT, timestamp TEXT, status_peca TEXT, tempo_ciclo REAL);
            CREATE TABLE registo_avarias (id INTEGER PRIMARY KEY AUTOINCREMENT, cabine_id INTEGER, robo_afetado TEXT, codigo_erro TEXT, descricao TEXT, causa_provavel TEXT, timestamp_inicio TEXT, timestamp_fim TEXT, status TEXT);
            INSERT INTO cabines VALUES (7, 'Main A', 'Estação 1', 'Teste', 'OK');
            INSERT INTO historico_producao VALUES (21, 'Main A', '2026-10-30 09:00:00', 'OK', 10);
            INSERT INTO registo_avarias VALUES (31, 7, 'Robô 1', 'E1', 'Teste', 'Teste', '2026-10-30T08:00:00', '2026-10-30T08:10:00', 'RESOLVED');
        """)
        if invalid:
            conn.execute("UPDATE registo_avarias SET cabine_id = 999")
    return path


def test_legacy_requires_explicit_migration_without_changes(tmp_path):
    path = create_legacy(tmp_path / "legacy.db")
    before = path.read_bytes()
    with pytest.raises(MigrationRequired):
        initialize_database(path)
    assert path.read_bytes() == before
    with pytest.raises(MigrationRequired):
        check_database(path)


def test_migrate_preserves_ids_history_and_backup_and_is_idempotent(tmp_path):
    path = create_legacy(tmp_path / "legacy.db")
    backup = migrate_database(path)
    assert isinstance(backup, Path) and backup.is_file()
    with sqlite3.connect(backup) as conn:
        assert conn.execute("SELECT status FROM registo_avarias WHERE id=31").fetchone()[0] == "RESOLVED"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    with connect(path) as conn:
        assert tuple(conn.execute("SELECT * FROM historico_producao").fetchone()) == (21, "Main A", "2026-10-30 09:00:00", "OK", 10)
        row = conn.execute("SELECT id, cabine_id, timestamp_fim, status FROM registo_avarias").fetchone()
        assert tuple(row) == (31, 7, "2026-10-30T08:10:00", "RESOLVIDO")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    check_database(path)
    assert migrate_database(path) is None


def test_migration_invalid_reference_aborts_before_writing(tmp_path):
    path = create_legacy(tmp_path / "legacy.db", invalid=True)
    before = path.read_bytes()
    with pytest.raises(MigrationError, match="registo_avarias, id=31"):
        migrate_database(path)
    assert path.read_bytes() == before
    assert list(tmp_path.glob("*.backup_*")) == []


def test_seed_is_idempotent_and_preserves_existing_stations(db):
    with connect(db) as conn:
        conn.execute("UPDATE cabines SET nome_processo = 'Nome existente' WHERE id=1")
    seed_demo_stations(db)
    with connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM cabines").fetchone()[0] == 8
        assert conn.execute("SELECT nome_processo FROM cabines WHERE id=1").fetchone()[0] == "Nome existente"


@pytest.mark.parametrize("timestamp", ["2026-10-30T23:59:59.999999", "2026-10-30 23:59:59.999999", "2026-10-30T09:00:00.1"])
def test_valid_naive_timestamps_preserve_microseconds(db, timestamp):
    with connect(db) as conn:
        conn.execute("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES ('Main A', ?, 'OK', 10)", (timestamp,))
        assert conn.execute("SELECT timestamp FROM historico_producao").fetchone()[0] == timestamp


def test_breakdown_end_one_microsecond_before_start_is_rejected(db):
    with connect(db) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("""INSERT INTO registo_avarias
            (cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, timestamp_fim, status)
            VALUES (1, 'Robô 1', 'E1', 'Teste', 'Teste', '2026-10-30T09:00:00.000002', '2026-10-30 09:00:00.000001', 'RESOLVIDO')""")


def test_equal_breakdown_timestamps_accept_different_fraction_precision(db):
    with connect(db) as conn:
        conn.execute("""INSERT INTO registo_avarias
            (cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, timestamp_fim, status)
            VALUES (1, 'Robô 1', 'E1', 'Teste', 'Teste', '2026-10-30T09:00:00.000000', '2026-10-30 09:00:00', 'RESOLVIDO')""")


@pytest.mark.parametrize("sql", [
    "CREATE TABLE extra (cabine_id INTEGER REFERENCES cabines(id))",
    "CREATE VIEW station_view AS SELECT * FROM cabines",
    "CREATE TRIGGER station_trigger AFTER UPDATE ON cabines BEGIN SELECT 1; END",
    "CREATE INDEX custom_index ON cabines(estacao)",
])
def test_migration_refuses_unknown_schema_objects_without_writing(tmp_path, sql):
    path = create_legacy(tmp_path / "legacy.db")
    with sqlite3.connect(path) as conn:
        conn.execute(sql)
    before = path.read_bytes()
    with pytest.raises(MigrationError, match="revisão manual"):
        migrate_database(path)
    assert path.read_bytes() == before
    assert list(tmp_path.glob("*.backup_*")) == []


def test_migration_preserves_autoincrement_high_water_after_deleted_rows(tmp_path):
    path = create_legacy(tmp_path / "legacy.db")
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO historico_producao VALUES (100, 'Main A', '2026-10-30T10:00:00', 'OK', 10)")
        conn.execute("DELETE FROM historico_producao WHERE id=100")
        conn.execute("INSERT INTO registo_avarias SELECT 200, cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, timestamp_fim, status FROM registo_avarias WHERE id=31")
        conn.execute("DELETE FROM registo_avarias WHERE id=200")
    migrate_database(path)
    with connect(path) as conn:
        inserted = conn.execute("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES ('Main A', '2026-10-30T11:00:00', 'OK', 10)")
        assert inserted.lastrowid == 101
        inserted = conn.execute("""INSERT INTO registo_avarias
            (cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, status)
            VALUES (7, 'Robô 1', 'E2', 'Teste', 'Teste', '2026-10-30T11:00:00', 'ATIVO')""")
        assert inserted.lastrowid == 201


def test_migration_rebuilds_current_station_state_from_active_breakdowns(tmp_path):
    path = create_legacy(tmp_path / "legacy.db")
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO cabines VALUES (8, 'Main B', 'Estação 1', 'Teste', 'ERRO')")
        conn.execute("""INSERT INTO registo_avarias
            (id, cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, status)
            VALUES (32, 7, 'Robô 2', 'E2', 'Teste', 'Teste', '2026-10-30T09:00:00', 'ATIVO')""")
    migrate_database(path)
    with connect(path) as conn:
        assert [tuple(row) for row in conn.execute("SELECT id,status FROM cabines ORDER BY id")] == [(7, "ERRO"), (8, "OK")]
        assert tuple(conn.execute("SELECT timestamp_fim,status FROM registo_avarias WHERE id=31").fetchone()) == ("2026-10-30T08:10:00", "RESOLVIDO")
        assert tuple(conn.execute("SELECT timestamp_fim,status FROM registo_avarias WHERE id=32").fetchone()) == (None, "ATIVO")
