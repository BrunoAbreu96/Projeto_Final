"""Backup/restauro apenas em bases sintéticas, sem dados industriais locais."""

from datetime import datetime
from pathlib import Path
import sqlite3

import pytest

import brunus_mes.backups as backups
from brunus_mes.backups import BackupError, create_backup, list_backups, restore_backup
from brunus_mes.database import TABLE_COLUMNS, connect, initialize_database, seed_demo_stations
from brunus_mes.services import resolve_breakdown


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "demo.db"
    initialize_database(path)
    seed_demo_stations(path)
    with connect(path) as conn:
        conn.execute("INSERT INTO historico_producao (id, main_line, timestamp, status_peca, tempo_ciclo) VALUES (10, 'Main A', '2026-11-02T09:00:00', 'OK', 10)")
        conn.execute("INSERT INTO registo_avarias (id, cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, status) VALUES (20, 1, 'Robô 1', 'TESTE', 'Avaria sintética', 'Teste', '2026-11-02T09:05:00', 'ATIVO')")
        conn.execute("UPDATE cabines SET status='ERRO' WHERE id=1")
        conn.execute("INSERT INTO sessao_ativa (id, perfil, timestamp) VALUES (1, 'master', '2026-11-02T09:00:00')")
        # Preservar uma sequência acima dos IDs existentes também é necessário.
        conn.execute("UPDATE sqlite_sequence SET seq=80 WHERE name='historico_producao'")
    return path


def state(path):
    with sqlite3.connect(path) as conn:
        return {
            **{table: conn.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall() for table in TABLE_COLUMNS},
            "sequences": conn.execute("SELECT * FROM sqlite_sequence ORDER BY name").fetchall(),
        }


def test_backup_is_consistent_and_preserves_rows_and_sequences(db):
    before = state(db)
    backup = create_backup("master", db)
    assert backup.parent == db.parent / "backups"
    assert backup.name.startswith("demo.backup_")
    assert state(backup) == before == state(db)
    assert list_backups(db) == [backup]


def test_restore_recovers_snapshot_and_keeps_pre_restore_copy(db):
    original = state(db)
    backup = create_backup("master", db)
    resolve_breakdown(20, "tecnico", db, datetime(2026, 11, 2, 10))
    with connect(db) as conn:
        conn.execute("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES ('Main B', '2026-11-02T10:00:00', 'REJEITADA', 11)")
    later = state(db)
    assert later != original
    recovery = restore_backup(backup, "master", True, db)
    assert state(db) == original
    assert state(recovery) == later
    assert recovery != backup
    # O snapshot anterior ao restauro também pode ser recuperado.
    restore_backup(recovery, "master", True, db)
    assert state(db) == later


@pytest.mark.parametrize("profile", ["operador", "tecnico", "", None])
def test_backup_and_restore_are_master_only(db, profile):
    before = state(db)
    with pytest.raises(PermissionError):
        create_backup(profile, db)
    with pytest.raises(PermissionError):
        restore_backup(db.parent / "missing.db", profile, True, db)
    assert state(db) == before
    assert not (db.parent / "backups").exists()


@pytest.mark.parametrize("confirmation", [False, None, 1, "sim"])
def test_restore_requires_boolean_confirmation(db, confirmation):
    backup = create_backup("master", db)
    before = state(db)
    with pytest.raises(BackupError, match="confirmação explícita"):
        restore_backup(backup, "master", confirmation, db)
    assert state(db) == before
    assert len(list_backups(db)) == 1


def test_missing_database_never_creates_an_empty_file(tmp_path):
    missing = tmp_path / "missing" / "demo.db"
    with pytest.raises(FileNotFoundError):
        create_backup("master", missing)
    with pytest.raises(FileNotFoundError):
        restore_backup(tmp_path / "anything.db", "master", True, missing)
    assert not missing.parent.exists()
    assert list_backups(missing) == []


def test_restore_rejects_files_outside_backup_directory(db, tmp_path):
    backup = create_backup("master", db)
    outside = tmp_path / backup.name
    outside.write_bytes(backup.read_bytes())
    before = state(db)
    with pytest.raises(BackupError, match="pasta de backups"):
        restore_backup(outside, "master", True, db)
    assert state(db) == before


def test_restore_rejects_other_database_prefix_or_extension(db):
    backup = create_backup("master", db)
    before = state(db)
    for name in (backup.name.replace("demo.", "other.", 1), backup.name + ".txt"):
        other = backup.with_name(name)
        other.write_bytes(backup.read_bytes())
        with pytest.raises(BackupError, match="pasta de backups"):
            restore_backup(other, "master", True, db)
    assert list_backups(db) == [backup]
    assert state(db) == before


@pytest.mark.parametrize("alteration", [
    "CREATE TABLE extra (id INTEGER)",
    "CREATE TRIGGER extra_trigger AFTER UPDATE ON cabines BEGIN SELECT 1; END",
    "CREATE VIEW extra_view AS SELECT * FROM cabines",
    "PRAGMA user_version=2",
    "UPDATE cabines SET status='OK' WHERE id=1",
    "UPDATE sqlite_sequence SET seq=0 WHERE name='registo_avarias'",
])
def test_invalid_or_incompatible_copy_is_rejected_without_changes(db, alteration):
    backup = create_backup("master", db)
    with sqlite3.connect(backup) as conn:
        conn.execute(alteration)
    before = state(db)
    with pytest.raises(BackupError):
        restore_backup(backup, "master", True, db)
    assert state(db) == before
    assert list_backups(db) == []


def test_constraint_invalid_data_is_rejected_even_if_checks_were_bypassed(db):
    backup = create_backup("master", db)
    with sqlite3.connect(backup) as conn:
        conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute("UPDATE historico_producao SET tempo_ciclo=-1")
    before = state(db)
    with pytest.raises(BackupError):
        restore_backup(backup, "master", True, db)
    assert state(db) == before


def test_invalid_foreign_key_is_rejected(db):
    backup = create_backup("master", db)
    with sqlite3.connect(backup) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("UPDATE registo_avarias SET cabine_id=999")
    before = state(db)
    with pytest.raises(BackupError, match="referências inválidas"):
        restore_backup(backup, "master", True, db)
    assert state(db) == before


def test_invalid_target_layout_is_not_silently_discarded(db):
    backup = create_backup("master", db)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE important_extra (id INTEGER)")
        conn.execute("INSERT INTO important_extra VALUES (1)")
    before = db.read_bytes()
    with pytest.raises(BackupError, match="objetos adicionais"):
        restore_backup(backup, "master", True, db)
    assert db.read_bytes() == before
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT * FROM important_extra").fetchall() == [(1,)]


def test_complete_rollback_after_restore_write_failure(db, monkeypatch):
    backup = create_backup("master", db)
    resolve_breakdown(20, "tecnico", db, datetime(2026, 11, 2, 10))
    before = state(db)
    original_replace = backups._replace_contents

    def fail_after_write(conn, rows, sequences):
        original_replace(conn, rows, sequences)
        raise sqlite3.OperationalError("falha sintética após escrita")

    monkeypatch.setattr(backups, "_replace_contents", fail_after_write)
    with pytest.raises(sqlite3.OperationalError, match="falha sintética"):
        restore_backup(backup, "master", True, db)
    assert state(db) == before
    others = [candidate for candidate in list_backups(db) if candidate != backup]
    assert len(others) == 1
    assert state(others[0]) == before


def test_backup_directory_can_be_selected_and_no_files_are_overwritten(db, tmp_path):
    folder = tmp_path / "selected"
    first = create_backup("master", db, folder)
    first_bytes = first.read_bytes()
    second = create_backup("master", db, folder)
    assert first != second
    assert first.read_bytes() == first_bytes
    assert set(list_backups(db, folder)) == {first, second}
    assert list_backups(db) == []
    restore_backup(first, "master", True, db, folder)


def test_corrupt_file_is_not_listed_or_restored(db):
    backup = create_backup("master", db)
    backup.write_bytes(b"not a sqlite database")
    before = state(db)
    assert list_backups(db) == []
    with pytest.raises(sqlite3.DatabaseError):
        restore_backup(backup, "master", True, db)
    assert state(db) == before


def test_wal_committed_rows_are_included_in_online_backup(db):
    with sqlite3.connect(db) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES ('Main B', '2026-11-02T10:00:00', 'OK', 12)")
        writer.commit()
        backup = create_backup("master", db)
        assert state(backup) == state(db)


def test_restore_in_wal_preserves_an_existing_reader_snapshot(db):
    backup = create_backup("master", db)
    with sqlite3.connect(db) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES ('Main B', '2026-11-02T10:00:00', 'OK', 12)")
        writer.commit()
    reader = sqlite3.connect(db)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT count(*) FROM historico_producao").fetchone()[0] == 2
        restore_backup(backup, "master", True, db)
        # O leitor já aberto conserva o seu snapshot; o ficheiro não é trocado.
        assert reader.execute("SELECT count(*) FROM historico_producao").fetchone()[0] == 2
        reader.rollback()
        assert reader.execute("SELECT count(*) FROM historico_producao").fetchone()[0] == 1
    finally:
        reader.close()


def test_a_name_collision_does_not_overwrite_existing_backup(db, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 11, 2, 11, 30)

    monkeypatch.setattr(backups, "datetime", FixedDatetime)
    monkeypatch.setattr(backups.secrets, "token_hex", lambda size: "abcdef")
    backup = create_backup("master", db)
    before = backup.read_bytes()
    with pytest.raises(FileExistsError):
        create_backup("master", db)
    assert backup.read_bytes() == before
    assert list_backups(db) == [backup]
