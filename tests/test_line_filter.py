"""Relatórios por linha: os dados e todos os indicadores usam o mesmo filtro."""

from datetime import date, datetime
from functools import partial

import pytest

from brunus_mes.database import connect, initialize_database
import brunus_mes.pdf_report as pdf_module
from brunus_mes.reporting import build_shift_report


DAY = date(2026, 11, 2)
SNAPSHOT = datetime(2026, 11, 2, 10)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "line_filter.db"
    initialize_database(path)
    with connect(path) as conn:
        conn.executemany("INSERT INTO cabines (id, main_line, estacao, nome_processo) VALUES (?, ?, ?, ?)",
            [(1, "Main A", "Estação 1", "Montagem"), (2, "Main A", "Estação 2", "Teste"),
             (3, "Main B", "Estação 1", "Montagem")])
        conn.executemany("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES (?, ?, ?, 10)",
            [("Main A", "2026-11-02T09:00:00", "OK"),
             ("Main A", "2026-11-02T09:01:00", "REJEITADA"),
             ("Main B", "2026-11-02T09:00:00", "OK"),
             ("Main B", "2026-11-02T09:01:00", "OK"),
             ("Main B", "2026-11-02T09:02:00", "OK")])
        conn.executemany("""INSERT INTO registo_avarias
            (cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, timestamp_fim, status)
            VALUES (?, 'Robô 1', 'TESTE', 'Sintética', 'Inspeção', ?, ?, ?)""",
            [(1, "2026-11-02T07:55:00", "2026-11-02T08:10:00", "RESOLVIDO"),
             (2, "2026-11-02T08:05:00", "2026-11-02T08:20:00", "RESOLVIDO"),
             (1, "2026-11-02T09:00:00", None, "ATIVO"),
             (3, "2026-11-02T08:00:00", "2026-11-02T08:05:00", "RESOLVIDO")])
    return path


def test_selected_line_filters_production_quality_downtime_and_finances(db):
    first = build_shift_report(DAY, 1, db, SNAPSHOT, main_line="Main A")
    second = build_shift_report(DAY, 1, db, SNAPSHOT, main_line="Main B")
    all_lines = build_shift_report(DAY, 1, db, SNAPSHOT)
    assert first.main_line == "Main A"
    assert (first.total_pieces, first.ok_pieces, first.rejected_pieces, first.quality_percent) == (2, 1, 1, 50)
    assert (second.total_pieces, second.ok_pieces, second.rejected_pieces, second.quality_percent) == (3, 3, 0, 100)
    assert all_lines.main_line is None
    assert all_lines.quality_percent == 80
    assert {row["main_line"] for row in first.production + first.breakdowns} == {"Main A"}
    assert {row["main_line"] for row in second.production + second.breakdowns} == {"Main B"}
    assert first.downtime_by_line == {"Main A": 4800}
    assert second.downtime_by_line == {"Main B": 300}
    assert all_lines.downtime_line_seconds == first.downtime_line_seconds + second.downtime_line_seconds == 5100
    assert (first.occurrences, first.overlapping_breakdowns, first.active_breakdowns) == (2, 3, 1)
    assert (second.occurrences, second.overlapping_breakdowns, second.active_breakdowns) == (1, 1, 0)
    assert (first.completed_repairs, first.mttr_seconds) == (1, 900)
    assert (second.completed_repairs, second.mttr_seconds) == (1, 300)
    assert all_lines.mttr_seconds == 600
    assert first.estimated_result == -11935
    assert second.estimated_result == -450
    assert all_lines.estimated_result == first.estimated_result + second.estimated_result


def test_line_filter_preserves_exact_temporal_boundaries_and_snapshot(db):
    with connect(db) as conn:
        conn.executemany("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES ('Main B', ?, 'OK', 10)",
            [("2026-11-02T07:59:59.999999",), ("2026-11-02T08:00:00",),
             ("2026-11-02T09:59:59.999999",), ("2026-11-02T10:00:00.000001",),
             ("2026-11-02T17:00:00",)])
    report = build_shift_report(DAY, 1, db, SNAPSHOT, "Main B")
    assert report.total_pieces == 5
    assert "2026-11-02T08:00:00" in {row["timestamp"] for row in report.production}
    assert "2026-11-02T09:59:59.999999" in {row["timestamp"] for row in report.production}
    assert all(report.start <= datetime.fromisoformat(row["timestamp"]) <= SNAPSHOT for row in report.production)


def test_unknown_line_and_future_shift_keep_empty_report_with_selected_line(db):
    for now in (SNAPSHOT, datetime(2026, 11, 2, 7)):
        report = build_shift_report(DAY, 1, db, now, "Linha inexistente")
        assert report.main_line == "Linha inexistente"
        assert not report.has_data
        assert report.total_pieces == report.occurrences == report.downtime_line_seconds == 0
        assert report.quality_percent is report.mttr_seconds is None


@pytest.mark.parametrize("line", ["", " ", 1, False, [], {}])
def test_invalid_line_filter_is_rejected(db, line):
    with pytest.raises(ValueError, match="linha válida"):
        build_shift_report(DAY, 1, db, SNAPSHOT, line)


def test_pdf_identifies_selected_line_or_all_lines(db, monkeypatch):
    # Compression is disabled only in this test so the generated PDF text can
    # be checked with the standard library, without a new test dependency.
    monkeypatch.setattr(pdf_module, "SimpleDocTemplate", partial(pdf_module.SimpleDocTemplate, pageCompression=0))
    selected = pdf_module.generate_shift_pdf(build_shift_report(DAY, 1, db, SNAPSHOT, "Main A"))
    all_lines = pdf_module.generate_shift_pdf(build_shift_report(DAY, 1, db, SNAPSHOT))
    empty = pdf_module.generate_shift_pdf(build_shift_report(DAY, 1, db, SNAPSHOT, "Linha inexistente"))
    assert selected.startswith(b"%PDF-") and all_lines.startswith(b"%PDF-") and empty.startswith(b"%PDF-")
    assert b"Linha:" in selected and b"Main A" in selected and b"Main B" not in selected
    assert b"Todas as linhas" in all_lines
    assert b"Linha inexistente" in empty


def test_line_filter_preserves_exact_line_names_from_legacy_data(db):
    # The schema permits surrounding spaces and migration preserves them.
    # A line selected from the database must match that exact stored identity.
    with connect(db) as conn:
        conn.execute("INSERT INTO historico_producao(main_line,timestamp,status_peca,tempo_ciclo) VALUES (?,?,'OK',10)",
            (" Main A ", "2026-11-02T09:30:00"))
    report = build_shift_report(DAY, 1, db, SNAPSHOT, " Main A ")
    assert report.main_line == " Main A "
    assert report.total_pieces == 1
    assert report.production[0]["main_line"] == " Main A "
    assert build_shift_report(DAY, 1, db, SNAPSHOT, "Main A").total_pieces == 2
