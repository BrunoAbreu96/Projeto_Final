"""A demonstração manual respeita permissões e a paragem da linha."""

from datetime import datetime, timedelta

import pytest

from brunus_mes.database import connect, initialize_database, seed_demo_stations
from brunus_mes.demo import generate_demo_event
from brunus_mes.services import resolve_breakdown


@pytest.fixture
def demo_db(tmp_path, monkeypatch):
    path = tmp_path / "manual-demo.db"
    initialize_database(path)
    seed_demo_stations(path)
    monkeypatch.setenv("BRUNUS_DEMO_MODE", "1")
    return path


@pytest.mark.parametrize("profile", ["operador", "tecnico", None])
def test_demo_events_require_master(demo_db, profile):
    with pytest.raises(PermissionError):
        generate_demo_event("ERRO", "Main A", profile, demo_db)
    with connect(demo_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM registo_avarias").fetchone()[0] == 0


def test_demo_events_require_explicit_demo_mode(demo_db, monkeypatch):
    monkeypatch.delenv("BRUNUS_DEMO_MODE")
    with pytest.raises(PermissionError, match="modo de demonstração"):
        generate_demo_event("OK", "Main A", "master", demo_db)


def test_manual_events_stop_and_resume_after_technical_resolution(demo_db):
    now = datetime(2026, 11, 2, 10)
    failure = generate_demo_event("ERRO", "Main A", "master", demo_db, now)
    assert failure["event"] == "ERRO"
    assert generate_demo_event("OK", "Main A", "master", demo_db, now)["event"] == "PARADA"
    assert generate_demo_event("OK", "Main B", "master", demo_db, now)["event"] == "OK"
    resolve_breakdown(failure["id"], "tecnico", demo_db, now + timedelta(minutes=5))
    assert generate_demo_event("REJEITADA", "Main A", "master", demo_db, now + timedelta(minutes=6))["event"] == "REJEITADA"
    with connect(demo_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM historico_producao").fetchone()[0] == 2


def test_unknown_event_does_not_insert_data(demo_db):
    with pytest.raises(ValueError):
        generate_demo_event("OUTRO", "Main A", "master", demo_db)
