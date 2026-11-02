"""Seleção do turno atual, incluindo a mudança de data à meia-noite."""
from datetime import date, datetime, timezone

import pytest

import brunus_mes.reporting as reporting
from brunus_mes.reporting import current_shift, shift_interval


@pytest.mark.parametrize("timestamp,day,shift", [
    ("2026-11-02T00:00:00", date(2026, 11, 1), 2),
    ("2026-11-02T00:59:59.999999", date(2026, 11, 1), 2),
    ("2026-11-02T01:00:00", date(2026, 11, 2), 3),
    ("2026-11-02T01:00:00.000001", date(2026, 11, 2), 3),
    ("2026-11-02T07:59:59.999999", date(2026, 11, 2), 3),
    ("2026-11-02T08:00:00", date(2026, 11, 2), 1),
    ("2026-11-02T08:00:00.000001", date(2026, 11, 2), 1),
    ("2026-11-02T16:59:59.999999", date(2026, 11, 2), 1),
    ("2026-11-02T17:00:00", date(2026, 11, 2), 2),
    ("2026-11-02T17:00:00.000001", date(2026, 11, 2), 2),
    ("2026-11-02T23:59:59.999999", date(2026, 11, 2), 2),
    ("2027-01-01T00:30:00", date(2026, 12, 31), 2),
])
def test_current_shift_uses_civil_start_date_and_half_open_boundaries(timestamp, day, shift):
    now = datetime.fromisoformat(timestamp)
    assert current_shift(now) == (day, shift)
    start, end = shift_interval(day, shift)
    assert start <= now < end


def test_current_shift_rejects_timezone_aware_datetime():
    with pytest.raises(ValueError, match="sem fuso"):
        current_shift(datetime(2026, 11, 2, 9, tzinfo=timezone.utc))


def test_current_shift_defaults_to_local_clock(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 11, 2, 0, 30)

    monkeypatch.setattr(reporting, "datetime", FixedDatetime)
    assert current_shift() == (date(2026, 11, 1), 2)
