from datetime import date, datetime, timedelta

import pytest

from brunus_mes.database import connect, initialize_database
from brunus_mes.pdf_report import generate_shift_pdf
from brunus_mes.reporting import build_shift_report, shift_interval, union_seconds


DAY = date(2026, 10, 30)
AFTER_DAY = datetime(2026, 10, 31, 2)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "reports.db"
    initialize_database(path)
    with connect(path) as conn:
        conn.executemany(
            "INSERT INTO cabines(id,main_line,estacao,nome_processo,status) VALUES (?,?,?,?,?)",
            [(1, "Main A", "Estação 1", "Montagem", "OK"),
             (2, "Main A", "Estação 2", "Teste", "OK"),
             (3, "Main B", "Estação 1", "Montagem", "OK")],
        )
    return path


def production(path, timestamp, status="OK", line="Main A"):
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO historico_producao(main_line,timestamp,status_peca,tempo_ciclo) VALUES(?,?,?,?)",
            (line, timestamp, status, 10.0),
        )


def breakdown(path, start, end=None, cabine=1):
    with connect(path) as conn:
        return conn.execute(
            """INSERT INTO registo_avarias(cabine_id,robo_afetado,codigo_erro,descricao,
                causa_provavel,timestamp_inicio,timestamp_fim,status)
                VALUES(?,?,?,?,?,?,?,?)""",
            (cabine, "Robô 1", "DEMO", "Avaria sintética", "Teste", start, end,
             "RESOLVIDO" if end else "ATIVO"),
        ).lastrowid


@pytest.mark.parametrize("shift,first,last", [
    (1, "2026-10-30T08:00:00", "2026-10-30T17:00:00"),
    (2, "2026-10-30T17:00:00", "2026-10-31T01:00:00"),
    (3, "2026-10-30T01:00:00", "2026-10-30T08:00:00"),
])
def test_shift_intervals_use_civil_start_date(shift, first, last):
    assert shift_interval(DAY, shift) == (datetime.fromisoformat(first), datetime.fromisoformat(last))


def test_invalid_shift_is_rejected():
    with pytest.raises(ValueError):
        shift_interval(DAY, 4)
    with pytest.raises(ValueError):
        shift_interval(DAY, True)


def test_midnight_and_half_open_boundaries_with_mixed_iso_separators(db):
    for timestamp in ["2026-10-30 16:59:59", "2026-10-30T17:00:00",
                      "2026-10-31 00:59:59", "2026-10-31T01:00:00"]:
        production(db, timestamp)
    report = build_shift_report(DAY.isoformat(), "Turno 2 (17:00 - 01:00)", db, AFTER_DAY)
    assert report.total_pieces == 2
    assert {row["timestamp"] for row in report.production} == {
        "2026-10-30T17:00:00", "2026-10-31 00:59:59",
    }


def test_microseconds_are_not_lost_by_sqlite_date_rounding(db):
    for timestamp in ["2026-10-30T07:59:59.999999", "2026-10-30T08:00:00",
                      "2026-10-30T16:59:59.999999", "2026-10-30T17:00:00"]:
        production(db, timestamp)
    breakdown(db, "2026-10-30T07:00:00", "2026-10-30T08:00:00.000001")
    report = build_shift_report(DAY, 1, db, AFTER_DAY)
    assert report.total_pieces == 2
    assert report.production[-1]["timestamp"] == "2026-10-30T16:59:59.999999"
    assert report.occurrences == 0
    assert report.overlapping_breakdowns == 1
    assert report.downtime_line_seconds == pytest.approx(0.000001)


def test_union_merges_overlap_and_touching_intervals():
    first = datetime(2026, 10, 30, 8)
    intervals = [(first, first + timedelta(minutes=10)),
                 (first + timedelta(minutes=5), first + timedelta(minutes=15)),
                 (first + timedelta(minutes=15), first + timedelta(minutes=20)),
                 (first, first)]
    assert union_seconds(intervals) == 1200
    assert union_seconds([]) == 0


def test_downtime_unions_same_line_but_adds_distinct_lines(db):
    breakdown(db, "2026-10-30T07:00:00", "2026-10-30T09:00:00", 1)
    breakdown(db, "2026-10-30T08:30:00", "2026-10-30T10:00:00", 2)
    breakdown(db, "2026-10-30T09:30:00", "2026-10-30T11:00:00", 1)
    breakdown(db, "2026-10-30T08:30:00", "2026-10-30T09:30:00", 3)
    report = build_shift_report(DAY, 1, db, AFTER_DAY)
    assert report.occurrences == 3
    assert report.overlapping_breakdowns == 4
    assert report.downtime_by_line == {"Main A": 10800, "Main B": 3600}
    assert report.downtime_line_seconds == 14400
    assert report.completed_repairs == 3
    assert report.mttr_seconds == 4800


def test_active_breakdowns_and_future_events_are_limited_to_snapshot(db):
    production(db, "2026-10-30T08:04:00")
    production(db, "2026-10-30T08:05:00.000001")
    breakdown(db, "2026-10-30T07:50:00")
    breakdown(db, "2026-10-30T08:06:00", cabine=2)
    report = build_shift_report(DAY, 1, db, datetime(2026, 10, 30, 8, 5))
    assert report.total_pieces == 1
    assert report.occurrences == 0
    assert report.active_breakdowns == 1
    assert report.downtime_line_seconds == 300
    assert report.mttr_seconds is None


def test_previous_breakdown_ending_at_shift_start_has_no_overlap(db):
    breakdown(db, "2026-10-30T07:00:00", "2026-10-30T08:00:00")
    report = build_shift_report(DAY, 1, db, AFTER_DAY)
    assert not report.has_data
    assert report.occurrences == report.overlapping_breakdowns == 0


def test_completed_repair_outside_shift_keeps_full_mttr_but_clips_downtime(db):
    breakdown(db, "2026-10-30T16:55:00", "2026-10-30T17:05:00")
    report = build_shift_report(DAY, 1, db, AFTER_DAY)
    assert report.mttr_seconds == 600
    assert report.completed_repairs == 1
    assert report.downtime_line_seconds == 300
    assert report.occurrences == 1


def test_a_known_future_repair_is_still_active_at_replayed_snapshot(db):
    breakdown(db, "2026-10-30T08:00:00", "2026-10-30T09:00:00")
    report = build_shift_report(DAY, 1, db, datetime(2026, 10, 30, 8, 30))
    assert report.downtime_line_seconds == 1800
    assert report.active_breakdowns == 1
    assert report.completed_repairs == 0
    assert report.mttr_seconds is None


def test_empty_and_future_periods_have_no_fabricated_quality_or_mttr(db):
    for snapshot in [datetime(2026, 10, 30, 7), AFTER_DAY]:
        report = build_shift_report(DAY, 1, db, snapshot)
        assert not report.has_data
        assert report.total_pieces == 0
        assert report.quality_percent is None
        assert report.mttr_seconds is None
        assert report.estimated_result == 0
        assert generate_shift_pdf(report).startswith(b"%PDF-")


def test_quality_and_financial_estimates_use_filtered_data(db):
    production(db, "2026-10-30T09:00:00")
    production(db, "2026-10-30T09:01:00")
    production(db, "2026-10-30T09:02:00", "REJEITADA")
    production(db, "2026-10-30T18:00:00")
    breakdown(db, "2026-10-30T09:05:00", "2026-10-30T09:10:00")
    report = build_shift_report(DAY, 1, db, AFTER_DAY)
    assert report.total_pieces == 3
    assert report.ok_pieces == 2
    assert report.rejected_pieces == 1
    assert report.quality_percent == pytest.approx(200 / 3)
    assert report.estimated_margin == 200
    assert report.estimated_scrap_cost == 35
    assert report.estimated_downtime_cost == 750
    assert report.estimated_result == -585
    pdf = generate_shift_pdf(report)
    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
