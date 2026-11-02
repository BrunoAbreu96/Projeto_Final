from datetime import datetime
import random
import sqlite3

import pytest

from brunus_mes.database import connect, initialize_database
from simulador_continuo import ciclo_fabrica_avancado, iniciar_base_dados_avancada, main


def test_synthetic_production_breakdown_and_blocked_line(tmp_path):
    path = tmp_path / "simulator.db"
    iniciar_base_dados_avancada(path)
    for index, event in enumerate(("OK", "REJEITADA", "ERRO")):
        result = ciclo_fabrica_avancado(path, event, random.Random(7), datetime(2026, 10, 30, 9, index), "Main A")
        assert result["event"] == event
    assert ciclo_fabrica_avancado(path, "OK", main_line="Main A")["event"] == "PARADA"
    with connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM historico_producao").fetchone()[0] == 2
        row = conn.execute("SELECT c.status,r.status FROM registo_avarias r JOIN cabines c ON c.id=r.cabine_id").fetchone()
        assert tuple(row) == ("ERRO", "ATIVO")


def test_simulator_rollback_keeps_station_normal_if_insert_fails(tmp_path):
    path = tmp_path / "simulator.db"
    iniciar_base_dados_avancada(path)
    with connect(path) as conn:
        conn.execute("CREATE TRIGGER fail_event BEFORE INSERT ON registo_avarias BEGIN SELECT RAISE(ABORT, 'falha'); END")
    with pytest.raises(sqlite3.IntegrityError):
        ciclo_fabrica_avancado(path, "ERRO", main_line="Main A")
    with connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM cabines WHERE status='ERRO'").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM registo_avarias").fetchone()[0] == 0


def test_cli_finite_cycles_and_init_only(tmp_path):
    path = tmp_path / "cli" / "simulator.db"
    assert main(["--db", str(path), "--init-only"]) == 0
    assert main(["--db", str(path), "--cycles", "3", "--interval", "0", "--seed", "7", "--event", "OK"]) == 0
    with connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM historico_producao").fetchone()[0] == 3


def test_restart_preserves_customized_stations_and_does_not_restore_deleted_ids(tmp_path):
    path = tmp_path / "custom.db"
    iniciar_base_dados_avancada(path)
    with connect(path) as conn:
        conn.execute("DELETE FROM cabines WHERE id IN (1, 2)")
        conn.execute("UPDATE cabines SET main_line='P-rack C', estacao='Montagem', nome_processo='Customizado' WHERE id=3")
        before = [tuple(row) for row in conn.execute("SELECT * FROM cabines ORDER BY id")]
    iniciar_base_dados_avancada(path)
    with connect(path) as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM cabines ORDER BY id")] == before
    assert ciclo_fabrica_avancado(path, event="OK", main_line="P-rack C")["main_line"] == "P-rack C"


def test_restart_of_existing_empty_database_does_not_create_demo_stations(tmp_path):
    path = tmp_path / "empty.db"
    initialize_database(path)
    iniciar_base_dados_avancada(path)
    with connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM cabines").fetchone()[0] == 0
