"""Reproducible trainer acceptance flow using only a temporary demo database."""

from datetime import date, datetime
import random

import pytest

from brunus_mes.database import connect, initialize_database, seed_demo_stations
from brunus_mes.pdf_report import generate_shift_pdf
from brunus_mes.reporting import build_shift_report
from brunus_mes.services import resolve_breakdown
from simulador_continuo import ciclo_fabrica_avancado


def test_new_install_simulation_repair_and_shift_report(tmp_path):
    path = tmp_path / "new-install" / "data" / "demo.db"
    initialize_database(path)
    seed_demo_stations(path)
    rng = random.Random(42)

    production = ciclo_fabrica_avancado(
        path=path,
        event="OK",
        main_line="Main A",
        rng=rng,
        now=datetime(2026, 10, 30, 9),
    )
    failure = ciclo_fabrica_avancado(
        path=path,
        event="ERRO",
        main_line="Main A",
        rng=rng,
        now=datetime(2026, 10, 30, 9, 5),
    )
    assert production["event"] == "OK"
    assert failure["event"] == "ERRO"
    with connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM cabines").fetchone()[0] == 8
        breakdown = dict(
            conn.execute(
                "SELECT * FROM registo_avarias WHERE id = ?", (failure["id"],)
            ).fetchone()
        )
        assert breakdown["status"] == "ATIVO"
        assert conn.execute(
            "SELECT status FROM cabines WHERE id = ?", (breakdown["cabine_id"],)
        ).fetchone()[0] == "ERRO"

    stopped = ciclo_fabrica_avancado(
        path=path,
        event="OK",
        main_line="Main A",
        rng=rng,
        now=datetime(2026, 10, 30, 9, 6),
    )
    assert stopped["event"] == "PARADA"
    with pytest.raises(PermissionError):
        resolve_breakdown(
            failure["id"], "operador", path=path, now=datetime(2026, 10, 30, 9, 10)
        )
    assert resolve_breakdown(
        failure["id"], "tecnico", path=path, now=datetime(2026, 10, 30, 9, 10)
    )

    with connect(path) as conn:
        resolved = conn.execute(
            "SELECT * FROM registo_avarias WHERE id = ?", (failure["id"],)
        ).fetchone()
        assert resolved["status"] == "RESOLVIDO"
        start = datetime.fromisoformat(resolved["timestamp_inicio"])
        end = datetime.fromisoformat(resolved["timestamp_fim"])
        assert (end - start).total_seconds() == 300
        assert conn.execute(
            "SELECT status FROM cabines WHERE id = ?", (resolved["cabine_id"],)
        ).fetchone()[0] == "OK"
        raw_count = conn.execute(
            "SELECT COUNT(*) FROM historico_producao WHERE timestamp >= ? AND timestamp < ?",
            ("2026-10-30T08:00:00", "2026-10-30T17:00:00"),
        ).fetchone()[0]

    report = build_shift_report(
        date(2026, 10, 30), 1, path=path, now=datetime(2026, 10, 30, 17)
    )
    assert report.total_pieces == raw_count == 1
    assert report.ok_pieces == 1
    assert report.rejected_pieces == 0
    assert report.quality_percent == 100
    assert report.occurrences == report.overlapping_breakdowns == 1
    assert report.active_breakdowns == 0
    assert report.completed_repairs == 1
    assert report.mttr_seconds == 300
    assert report.downtime_by_line["Main A"] == 300
    assert report.downtime_line_seconds == 300
    assert report.estimated_downtime_cost == 750
    assert report.estimated_result == -650
    pdf = generate_shift_pdf(report)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1_000
