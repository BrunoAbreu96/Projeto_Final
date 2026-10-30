from datetime import datetime
import sqlite3

import pytest

from brunus_mes.database import connect, initialize_database, seed_demo_stations
from brunus_mes.services import clear_demo_data, reset_active_breakdowns, resolve_breakdown

NOW = datetime(2026, 10, 30, 10)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "services.db"
    initialize_database(path)
    seed_demo_stations(path)
    with connect(path) as conn:
        conn.execute("UPDATE cabines SET status='ERRO' WHERE id=1")
        conn.execute("""INSERT INTO registo_avarias
            (id, cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, status)
            VALUES (1, 1, 'Robô 1', 'E1', 'Teste', 'Teste', '2026-10-30T09:00:00', 'ATIVO')""")
        conn.execute("""INSERT INTO registo_avarias
            (id, cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, timestamp_fim, status)
            VALUES (2, 1, 'Robô 1', 'E2', 'Teste', 'Teste', '2026-10-29T09:00:00', '2026-10-29T09:05:00', 'RESOLVIDO')""")
        conn.execute("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES ('Main A', '2026-10-30T08:00:00', 'OK', 10)")
    return path


def snapshot(path):
    with connect(path) as conn:
        return tuple(tuple(tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id"))
                     for table in ("cabines", "historico_producao", "registo_avarias"))


def test_resolve_preserves_historical_end_and_is_idempotent(db):
    assert resolve_breakdown(1, "tecnico", db, NOW)
    with connect(db) as conn:
        assert tuple(conn.execute("SELECT status,timestamp_fim FROM registo_avarias WHERE id=1").fetchone()) == ("RESOLVIDO", NOW.isoformat())
        assert conn.execute("SELECT status FROM cabines WHERE id=1").fetchone()[0] == "OK"
    state = snapshot(db)
    assert resolve_breakdown(1, "master", db, datetime(2026, 10, 30, 11)) is False
    assert resolve_breakdown(2, "master", db, NOW) is False
    assert resolve_breakdown(999, "master", db, NOW) is False
    assert snapshot(db) == state


def test_two_active_breakdowns_keep_station_in_error(db):
    with connect(db) as conn:
        conn.execute("""INSERT INTO registo_avarias
            (id, cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, status)
            VALUES (3, 1, 'Robô 2', 'E3', 'Teste', 'Teste', '2026-10-30T09:01:00', 'ATIVO')""")
    assert resolve_breakdown(1, "tecnico", db, NOW)
    with connect(db) as conn:
        assert conn.execute("SELECT status FROM cabines WHERE id=1").fetchone()[0] == "ERRO"
    assert resolve_breakdown(3, "master", db, NOW)
    with connect(db) as conn:
        assert conn.execute("SELECT status FROM cabines WHERE id=1").fetchone()[0] == "OK"


@pytest.mark.parametrize("operation", ["resolve", "reset", "clear"])
def test_complete_rollback_when_station_update_fails(db, operation):
    with connect(db) as conn:
        conn.execute("CREATE TRIGGER fail_station BEFORE UPDATE ON cabines BEGIN SELECT RAISE(ABORT, 'falha sintética'); END")
    before = snapshot(db)
    with pytest.raises(sqlite3.IntegrityError, match="falha sintética"):
        if operation == "resolve":
            resolve_breakdown(1, "master", db, NOW)
        elif operation == "reset":
            reset_active_breakdowns("master", db, NOW)
        else:
            clear_demo_data("master", True, db)
    assert snapshot(db) == before


def test_reset_only_closes_active_and_never_changes_history(db):
    assert reset_active_breakdowns("master", db, NOW) == 1
    with connect(db) as conn:
        rows = conn.execute("SELECT id,timestamp_fim,status FROM registo_avarias ORDER BY id").fetchall()
        assert [tuple(row) for row in rows] == [(1, NOW.isoformat(), "RESOLVIDO"), (2, "2026-10-29T09:05:00", "RESOLVIDO")]
        assert conn.execute("SELECT count(*) FROM historico_producao").fetchone()[0] == 1
    before = snapshot(db)
    assert reset_active_breakdowns("master", db, datetime(2026, 10, 30, 11)) == 0
    assert snapshot(db) == before


@pytest.mark.parametrize("profile", ["operador", "", "admin", None])
def test_resolution_denied_to_unauthorized_profiles(db, profile):
    before = snapshot(db)
    with pytest.raises(PermissionError):
        resolve_breakdown(1, profile, db, NOW)
    assert snapshot(db) == before


@pytest.mark.parametrize("profile", ["operador", "tecnico", "", None])
def test_reset_and_cleanup_restricted_to_master(db, profile):
    before = snapshot(db)
    with pytest.raises(PermissionError):
        reset_active_breakdowns(profile, db, NOW)
    with pytest.raises(PermissionError):
        clear_demo_data(profile, True, db)
    assert snapshot(db) == before


@pytest.mark.parametrize("confirmation", [False, None, 1, "sim"])
def test_cleanup_requires_explicit_boolean_confirmation(db, confirmation):
    before = snapshot(db)
    with pytest.raises(ValueError, match="confirmação"):
        clear_demo_data("master", confirmation, db)
    assert snapshot(db) == before


def test_confirmed_cleanup_removes_demo_history_and_restores_stations(db):
    clear_demo_data("master", True, db)
    with connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM historico_producao").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM registo_avarias").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM cabines WHERE status='OK'").fetchone()[0] == 8


def test_end_before_start_is_rejected_and_rolled_back(db):
    before = snapshot(db)
    with pytest.raises(sqlite3.IntegrityError):
        resolve_breakdown(1, "tecnico", db, datetime(2026, 10, 30, 8))
    assert snapshot(db) == before
