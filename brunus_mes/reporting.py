"""Relatórios de turno e indicadores calculados sobre um único instante de consulta.

Os eventos de produção representam a saída final de uma linha. As paragens
são unidas por linha; a soma entre linhas tem a unidade segundos-linha.
As datas são horas locais sem fuso, como os dados gerados pelo simulador.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any


TURNOS = {
    1: "Turno 1 (08:00 - 17:00)",
    2: "Turno 2 (17:00 - 01:00)",
    3: "Turno 3 (01:00 - 08:00)",
}
DEMO_MARGIN_OK = 100.0
DEMO_SCRAP_COST = 35.0
DEMO_DOWNTIME_PER_MINUTE = 150.0


def _shift_number(shift: int | str) -> int:
    if isinstance(shift, str):
        for number, label in TURNOS.items():
            if shift in (str(number), label):
                return number
    if isinstance(shift, int) and not isinstance(shift, bool) and shift in TURNOS:
        return shift
    raise ValueError("Selecione um turno válido: 1, 2 ou 3.")


def _local_datetime(value: datetime | str) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is not None:
        raise ValueError("Use datas e horas locais sem fuso horário.")
    return result


def shift_interval(day: date | str, shift: int | str) -> tuple[datetime, datetime]:
    """Calcula [início, fim), usando a data civil de início do turno.

    Exemplo: turno 2 de 30/10 começa às 17h de 30/10 e termina à 01h de 31/10.
    O turno 3 de 30/10 começa à 01h do próprio dia 30/10.
    """
    if isinstance(day, datetime):
        day = day.date()
    elif isinstance(day, str):
        day = date.fromisoformat(day)
    if not isinstance(day, date):
        raise ValueError("Selecione uma data válida para o início do turno.")
    number = _shift_number(shift)
    hours = {1: (8, 17), 2: (17, 1), 3: (1, 8)}
    first, last = hours[number]
    start = datetime.combine(day, time(first))
    end = datetime.combine(day, time(last))
    if end <= start:
        end += timedelta(days=1)
    return start, end


def union_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    """Duração da união, sem somar duas vezes intervalos sobrepostos."""
    ordered = sorted((start, end) for start, end in intervals if end > start)
    if not ordered:
        return 0.0
    start, end = ordered[0]
    total = 0.0
    for next_start, next_end in ordered[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += (end - start).total_seconds()
            start, end = next_start, next_end
    return total + (end - start).total_seconds()


@dataclass
class ShiftReport:
    day: date
    shift: int
    shift_label: str
    start: datetime
    end: datetime
    snapshot: datetime
    effective_end: datetime
    production: list[dict[str, Any]] = field(default_factory=list)
    breakdowns: list[dict[str, Any]] = field(default_factory=list)
    total_pieces: int = 0
    ok_pieces: int = 0
    rejected_pieces: int = 0
    quality_percent: float | None = None
    occurrences: int = 0
    overlapping_breakdowns: int = 0
    active_breakdowns: int = 0
    completed_repairs: int = 0
    mttr_seconds: float | None = None
    downtime_by_line: dict[str, float] = field(default_factory=dict)
    downtime_line_seconds: float = 0.0
    estimated_scrap_cost: float = 0.0
    estimated_downtime_cost: float = 0.0
    estimated_margin: float = 0.0
    estimated_result: float = 0.0

    @property
    def has_data(self) -> bool:
        return bool(self.production or self.breakdowns)


def build_shift_report(
    day: date | str,
    shift: int | str,
    path=None,
    now: datetime | None = None,
) -> ShiftReport:
    """Lê produção e avarias numa única transação de leitura SQLite.

    Produção: eventos em [início, fim), limitados ao instante da consulta.
    Ocorrências: avarias iniciadas nesse intervalo, até ao mesmo instante.
    Paragem: interseção com o turno, terminando no fim conhecido ou na consulta.
    MTTR: duração completa das ocorrências iniciadas no turno e reparadas até
    à consulta. Pode incluir a parte da reparação posterior ao fim do turno.
    """
    from .database import connect

    number = _shift_number(shift)
    start, end = shift_interval(day, number)
    snapshot = _local_datetime(now or datetime.now())
    effective_end = max(start, min(end, snapshot))
    report = ShiftReport(start.date(), number, TURNOS[number], start, end, snapshot, effective_end)
    if snapshot < start:
        return report

    with connect(path) as conn:
        # BEGIN fixes a consistent SQLite snapshot for both queries.
        conn.execute("BEGIN")
        production_rows = conn.execute(
            """SELECT id, main_line, timestamp, status_peca, tempo_ciclo
               FROM historico_producao
               WHERE julianday(timestamp) >= julianday(?) - 1.0 / 86400
                 AND julianday(timestamp) < julianday(?) + 1.0 / 86400
                 AND julianday(timestamp) <= julianday(?) + 1.0 / 86400
               ORDER BY julianday(timestamp), id""",
            (start.isoformat(), end.isoformat(), snapshot.isoformat()),
        ).fetchall()
        # Includes occurrences with zero duration and carry-in breakdowns.
        breakdown_rows = conn.execute(
            """SELECT r.*, c.main_line, c.estacao, c.nome_processo
               FROM registo_avarias r
               JOIN cabines c ON c.id = r.cabine_id
               WHERE julianday(r.timestamp_inicio) < julianday(?) + 1.0 / 86400
                 AND julianday(r.timestamp_inicio) <= julianday(?) + 1.0 / 86400
                 AND (julianday(r.timestamp_inicio) >= julianday(?) - 1.0 / 86400
                      OR r.timestamp_fim IS NULL
                      OR julianday(r.timestamp_fim) > julianday(?) - 1.0 / 86400)
               ORDER BY julianday(r.timestamp_inicio), r.id""",
            (end.isoformat(), snapshot.isoformat(), start.isoformat(), start.isoformat()),
        ).fetchall()

    # SQL fetches a one-second margin because julianday rounds milliseconds.
    # Exact Python comparisons preserve all microsecond interval boundaries.
    report.production = [
        dict(row) for row in production_rows
        if start <= _local_datetime(row["timestamp"]) < end
        and _local_datetime(row["timestamp"]) <= snapshot
    ]
    intervals_by_line: dict[str, list[tuple[datetime, datetime]]] = {}
    repairs: list[float] = []
    for row in breakdown_rows:
        record = dict(row)
        first = _local_datetime(record["timestamp_inicio"])
        if first >= end or first > snapshot:
            continue
        last = _local_datetime(record["timestamp_fim"]) if record["timestamp_fim"] else None
        occurred = start <= first < end
        clipped_start = max(start, first)
        clipped_end = min(effective_end, last if last is not None else snapshot)
        seconds = max(0.0, (clipped_end - clipped_start).total_seconds())
        if not occurred and seconds <= 0:
            continue
        record["started_in_shift"] = occurred
        record["downtime_seconds"] = seconds
        record["active_at_snapshot"] = last is None or last > snapshot
        record["full_duration_seconds"] = (last - first).total_seconds() if last and last <= snapshot else None
        report.breakdowns.append(record)
        report.occurrences += int(occurred)
        report.overlapping_breakdowns += int(seconds > 0)
        report.active_breakdowns += int(seconds > 0 and record["active_at_snapshot"])
        if seconds > 0:
            intervals_by_line.setdefault(record["main_line"], []).append((clipped_start, clipped_end))
        if occurred and last is not None and last <= snapshot:
            repairs.append((last - first).total_seconds())

    report.total_pieces = len(report.production)
    report.ok_pieces = sum(row["status_peca"] == "OK" for row in report.production)
    report.rejected_pieces = sum(row["status_peca"] == "REJEITADA" for row in report.production)
    if report.total_pieces:
        report.quality_percent = report.ok_pieces / report.total_pieces * 100
    report.completed_repairs = len(repairs)
    report.mttr_seconds = sum(repairs) / len(repairs) if repairs else None
    report.downtime_by_line = {line: union_seconds(intervals) for line, intervals in sorted(intervals_by_line.items())}
    report.downtime_line_seconds = sum(report.downtime_by_line.values())
    report.estimated_margin = report.ok_pieces * DEMO_MARGIN_OK
    report.estimated_scrap_cost = report.rejected_pieces * DEMO_SCRAP_COST
    report.estimated_downtime_cost = report.downtime_line_seconds / 60 * DEMO_DOWNTIME_PER_MINUTE
    report.estimated_result = report.estimated_margin - report.estimated_scrap_cost - report.estimated_downtime_cost
    return report
