"""Configuração pelo master com conservação dos registos de produção e avarias."""

import sqlite3

import pytest

from brunus_mes.configuration import add_station, delete_station, update_station
from brunus_mes.database import connect, initialize_database, seed_demo_stations


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "configuration.db"
    initialize_database(path)
    seed_demo_stations(path)
    return path


def station_rows(path):
    with connect(path) as conn:
        return [tuple(row) for row in conn.execute("SELECT * FROM cabines ORDER BY id")]


def add_breakdown(path, status="ATIVO"):
    with connect(path) as conn:
        conn.execute("UPDATE cabines SET status='ERRO' WHERE id=1")
        conn.execute("""INSERT INTO registo_avarias
            (cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, timestamp_fim, status)
            VALUES (1, 'Robô 1', 'TESTE', 'Sintética', 'Inspeção', '2026-11-02T09:00:00', ?, ?)""",
            (None if status == "ATIVO" else "2026-11-02T09:05:00", status))


@pytest.mark.parametrize("profile", ["operador", "tecnico", "", None])
def test_configuration_requires_master_without_creating_database(tmp_path, profile):
    path = tmp_path / "absent.db"
    for operation in (
        lambda: add_station("Linha C", "Estação 1", "Teste", profile, path),
        lambda: update_station(1, "Linha C", "Estação 1", "Teste", profile, path),
        lambda: delete_station(1, profile, True, path),
    ):
        with pytest.raises(PermissionError):
            operation()
    assert not path.exists()


def test_add_station_creates_line_and_reuses_existing_line_spelling(db):
    first = add_station(" Linha Á ", " Estação 1 ", " Inspeção ", "master", db)
    second = add_station("LINHA Á", "Estação 2", "Montagem", "master", db)
    with connect(db) as conn:
        rows = conn.execute("SELECT id, main_line, estacao, nome_processo, status FROM cabines WHERE id IN (?, ?) ORDER BY id", (first, second)).fetchall()
    assert [tuple(row) for row in rows] == [
        (first, "Linha Á", "Estação 1", "Inspeção", "OK"),
        (second, "Linha Á", "Estação 2", "Montagem", "OK"),
    ]


@pytest.mark.parametrize("fields", [
    (" ", "Estação 1", "Teste"), ("Linha C", "", "Teste"),
    ("Linha C", "Estação 1", None), ("Linha C\nOutra", "Estação 1", "Teste"),
    ("L" * 129, "Estação 1", "Teste"), ("Linha C", "E" * 129, "Teste"),
    ("Linha C", "Estação 1", "P" * 201),
])
def test_invalid_fields_are_rejected_without_changes(db, fields):
    before = station_rows(db)
    with pytest.raises(ValueError):
        add_station(*fields, "master", db)
    with pytest.raises(ValueError):
        update_station(1, *fields, "master", db)
    assert station_rows(db) == before


def test_duplicate_station_is_rejected_ignoring_case_and_outer_spaces(db):
    before = station_rows(db)
    with pytest.raises(ValueError, match="Já existe"):
        add_station(" main a ", " ESTAÇÃO 1 ", "Outra", "master", db)
    with pytest.raises(ValueError, match="Já existe"):
        update_station(2, "main a", "estação 1", "Outra", "master", db)
    assert station_rows(db) == before


def test_station_without_history_can_change_line_and_name(db):
    update_station(1, "Linha C", "Montagem 1", "Novo processo", "master", db)
    with connect(db) as conn:
        assert tuple(conn.execute("SELECT main_line, estacao, nome_processo, status FROM cabines WHERE id=1").fetchone()) == (
            "Linha C", "Montagem 1", "Novo processo", "OK")


@pytest.mark.parametrize("status", ["ATIVO", "RESOLVIDO"])
def test_breakdown_history_protects_identity_and_removal_but_process_can_change(db, status):
    add_breakdown(db, status)
    before = station_rows(db)
    with pytest.raises(ValueError, match="histórico"):
        update_station(1, "Linha C", "Estação 1", "Outro", "master", db)
    with pytest.raises(ValueError, match="histórico"):
        update_station(1, "Main A", "Renomeada", "Outro", "master", db)
    with pytest.raises(ValueError, match="histórico"):
        delete_station(1, "master", True, db)
    assert station_rows(db) == before
    update_station(1, "Main A", "Estação 1", "Instrução revista", "master", db)
    with connect(db) as conn:
        assert tuple(conn.execute("SELECT nome_processo, status FROM cabines WHERE id=1").fetchone()) == ("Instrução revista", "ERRO")
        assert conn.execute("SELECT status FROM registo_avarias WHERE cabine_id=1").fetchone()[0] == status


def test_line_production_protects_station_identity_and_removal(db):
    with connect(db) as conn:
        conn.execute("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES ('Main A', '2026-11-02T09:00:00', 'OK', 10)")
    before = station_rows(db)
    with pytest.raises(ValueError, match="histórico"):
        update_station(2, "Outra linha", "Estação 2", "Teste", "master", db)
    with pytest.raises(ValueError, match="histórico"):
        delete_station(2, "master", True, db)
    assert station_rows(db) == before
    with connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM historico_producao").fetchone()[0] == 1


@pytest.mark.parametrize("confirmation", [False, None, 1, "sim"])
def test_deletion_requires_explicit_boolean_confirmation(db, confirmation):
    before = station_rows(db)
    with pytest.raises(ValueError, match="confirmação"):
        delete_station(1, "master", confirmation, db)
    assert station_rows(db) == before


def test_confirmed_deletion_only_removes_selected_unused_station(db):
    delete_station(1, "master", True, db)
    assert [row[0] for row in station_rows(db)] == list(range(2, 9))


@pytest.mark.parametrize("station_id", [999, 0, -1, True, "1"])
def test_missing_or_invalid_station_does_not_change_configuration(db, station_id):
    before = station_rows(db)
    with pytest.raises(ValueError):
        update_station(station_id, "Main A", "Estação 1", "Teste", "master", db)
    with pytest.raises(ValueError):
        delete_station(station_id, "master", True, db)
    assert station_rows(db) == before


@pytest.mark.parametrize("operation,sql_event", [("add", "INSERT"), ("update", "UPDATE"), ("delete", "DELETE")])
def test_failed_configuration_write_rolls_back(db, operation, sql_event):
    with connect(db) as conn:
        conn.execute(f"CREATE TRIGGER fail_configuration BEFORE {sql_event} ON cabines BEGIN SELECT RAISE(ABORT, 'falha sintética'); END")
    before = station_rows(db)
    with pytest.raises(sqlite3.IntegrityError, match="falha sintética"):
        if operation == "add":
            add_station("Linha C", "Estação 1", "Teste", "master", db)
        elif operation == "update":
            update_station(1, "Main A", "Estação 1", "Outro", "master", db)
        else:
            delete_station(1, "master", True, db)
    assert station_rows(db) == before
