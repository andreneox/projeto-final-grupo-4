from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from services.analytics import calculate_dashboard_metrics


@pytest.mark.parametrize(("plc_count", "good"), [(None, 1), (0, 0), (4, 4)])
def test_uses_absolute_plc_count_when_available(plc_count, good) -> None:
    now = datetime(2026, 9, 24, 1, 0, tzinfo=ZoneInfo("America/Manaus"))
    result = calculate_dashboard_metrics(
        [], now, "00:00", 1440,
        production_cycles=[(12, "2026-09-24T00:30:00-04:00")],
        plc_production_count=plc_count,
    )

    assert result["production_counts"]["line"]["good"] == good
    assert result["production_counts"]["stations"]["12"]["completed_cycles"] == good


def test_metrics_use_category_losses_and_union_overlaps() -> None:
    timezone = ZoneInfo("America/Manaus")
    now = datetime(2026, 9, 24, 1, 0, tzinfo=timezone)
    occurrences = [
        (1, 2, "2026-09-24T00:00:00-04:00", "2026-09-24T00:10:00-04:00"),
        (2, 4, "2026-09-24T00:05:00-04:00", "2026-09-24T00:15:00-04:00"),
        (1, 3, "2026-09-24T00:00:00-04:00", "2026-09-24T00:06:00-04:00"),
        (1, 1, "2026-09-24T00:00:00-04:00", "2026-09-24T00:03:00-04:00"),
    ]

    metrics = calculate_dashboard_metrics(
        occurrences,
        now,
        "00:00",
        1440,
        production_cycles=[(12, "2026-09-24T00:30:00-04:00")] * 20,
        defects=[(1, "2026-09-24T00:00:00-04:00")],
    )

    assert metrics["line"] == {
        "availability": 75.0,
        "performance": 33.3,
        "quality": 95.2,
        "oee": 23.8,
    }
    assert metrics["downtime_minutes"] == {
        "qualidade": 3.0,
        "equipamento": 10.0,
        "processo": 6.0,
        "material": 10.0,
        "total": 15.0,
    }


def test_open_occurrence_is_counted_until_now() -> None:
    timezone = ZoneInfo("America/Manaus")
    now = datetime(2026, 9, 24, 0, 30, tzinfo=timezone)
    metrics = calculate_dashboard_metrics(
        [(1, 1, "2026-09-24T00:20:00-04:00", None)],
        now,
        "00:00",
        1440,
        production_cycles=[(1, "2026-09-24T00:25:00-04:00")] * 3,
        defects=[(1, "2026-09-24T00:20:00-04:00")],
    )
    assert metrics["downtime_minutes"]["qualidade"] == 10.0
    assert metrics["stations"]["1"]["quality"] == 0.0


def test_closed_category_display_stays_stable_while_other_category_grows() -> None:
    timezone = ZoneInfo("America/Manaus")
    equipment_start = datetime(2026, 9, 24, 0, 1, tzinfo=timezone)
    occurrences = [
        (1, 4, "2026-09-24T00:00:00-04:00", "2026-09-24T00:00:04-04:00"),
        (1, 2, equipment_start.isoformat(), None),
    ]

    earlier = calculate_dashboard_metrics(
        occurrences, equipment_start + timedelta(milliseconds=400), "00:00", 1440
    )["downtime_minutes"]
    later = calculate_dashboard_metrics(
        occurrences, equipment_start + timedelta(milliseconds=1200), "00:00", 1440
    )["downtime_minutes"]

    assert earlier["material"] == later["material"] == 0.07
    assert (earlier["equipamento"], later["equipamento"]) == (0.01, 0.02)
    assert (earlier["total"], later["total"]) == (0.07, 0.09)
