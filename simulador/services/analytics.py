from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import floor

from domain.models import AndonCategory

Interval = tuple[datetime, datetime]
CALCULATION_REVISION = "2026-11-20.01"


def _performance_percent(good: int, estimate: int) -> float | None:
    return 100 * good / estimate if good > 0 and estimate > 0 else None


def _merge_seconds(intervals: Iterable[Interval]) -> float:
    ordered = sorted(intervals, key=lambda item: item[0])
    if not ordered:
        return 0.0
    total = 0.0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += (current_end - current_start).total_seconds()
            current_start, current_end = start, end
    return total + (current_end - current_start).total_seconds()


def _display_minutes(seconds: float) -> float:
    minutes = Decimal(str(seconds)) / 60
    return float(minutes.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _metric_set(
    elapsed: float,
    stopped: float,
    performance: float | None,
    good: int = 0,
    defective: int = 0,
) -> dict[str, float | None]:
    availability = 100 * max(0.0, elapsed - stopped) / elapsed if elapsed > 0 else 100.0
    total = good + defective
    quality = 100 * good / total if total else 100.0
    return {
        "availability": round(availability, 1),
        "performance": round(performance, 1) if performance is not None else None,
        "quality": round(quality, 1),
        "oee": round(availability * performance * quality / 10_000, 1)
        if performance is not None
        else None,
    }


def calculate_dashboard_metrics(
    occurrences: Iterable[tuple[int, int, str, str | None]],
    now: datetime,
    shift_start: str,
    shift_duration_minutes: int,
    production_cycles: Iterable[tuple[int, str]] = (),
    defects: Iterable[tuple[int, str]] = (),
    reset_at: str | None = None,
    measurement_started_at: str | None = None,
    production_target: int = 480,
    available_time_minutes: float = 480.0,
    measurement_active: bool = True,
    performance_snapshot: dict | None = None,
    plc_production_count: int | None = None,
) -> dict:
    """Compare P12 output with the integer estimate shown in the dashboard.

    Line output is P12; station operations must never be added as finished pieces.
    Shift time defines the target rate, not a cap on the measurement clock.
    """
    hour, minute = (int(part) for part in shift_start.split(":", maxsplit=1))
    period_start = datetime.combine(now.date(), time(hour, minute), now.tzinfo)
    if now < period_start:
        period_start -= timedelta(days=1)
    if measurement_started_at:
        period_start = datetime.fromisoformat(measurement_started_at)
    elif reset_at:
        period_start = datetime.fromisoformat(reset_at)
    if not measurement_active:
        period_start = now
    period_end = now
    period_seconds = max(0.0, (period_end - period_start).total_seconds())
    expected = production_target * period_seconds / (available_time_minutes * 60)
    estimated_production = floor(expected)
    line_intervals: dict[AndonCategory, list[Interval]] = defaultdict(list)
    currently_stopped = False
    for station, button_id, opened_at, closed_at in occurrences:
        opened = datetime.fromisoformat(opened_at)
        closed = datetime.fromisoformat(closed_at) if closed_at else period_end
        if opened <= now and (closed_at is None or closed > now):
            currently_stopped = True
        start = max(opened, period_start)
        end = min(closed, period_end)
        if end > start:
            line_intervals[AndonCategory.from_button_id(button_id)].append((start, end))
    all_intervals = [
        interval for intervals in line_intervals.values() for interval in intervals
    ]
    stopped = _merge_seconds(all_intervals)
    completed_counts: dict[int, int] = defaultdict(int)
    defect_counts: dict[int, int] = defaultdict(int)
    last_p12 = None
    for station, timestamp in production_cycles:
        completed_at = datetime.fromisoformat(timestamp)
        if measurement_active and period_start <= completed_at <= period_end:
            completed_counts[station] += 1
            if station == 12 and (last_p12 is None or completed_at > last_p12):
                last_p12 = completed_at
    for station, timestamp in defects:
        occurred_at = datetime.fromisoformat(timestamp)
        if measurement_active and period_start <= occurred_at <= period_end:
            defect_counts[station] += 1

    if plc_production_count is not None:
        completed_counts[12] = plc_production_count
    good = completed_counts[12]
    defective = sum(defect_counts.values())
    # Legacy snapshots remain accepted for compatibility, but cannot freeze the
    # denominator at a different time or plan than the visible production estimate.
    performance = _performance_percent(good, estimated_production)
    stations = {
        str(station): _metric_set(
            period_seconds, stopped, performance, good, defect_counts[station]
        )
        for station in range(1, 13)
    }
    category_seconds = {
        category.name.lower(): _merge_seconds(line_intervals[category])
        for category in AndonCategory
    }
    downtime_seconds = {**category_seconds, "total": stopped}
    overlap_seconds = max(0.0, sum(category_seconds.values()) - stopped)
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "stations": stations,
        "line": _metric_set(period_seconds, stopped, performance, good, defective),
        "timing": {
            "calculation_revision": CALCULATION_REVISION,
            "measurement_started_at": period_start.isoformat()
            if measurement_active
            else None,
            "elapsed_seconds": period_seconds,
            "stopped_seconds": stopped,
            "production_seconds": max(0, period_seconds - stopped),
            "expected_production": expected,
            "estimated_production": estimated_production,
            "production_target": production_target,
            "available_time_minutes": available_time_minutes,
            "currently_stopped": currently_stopped,
            "performance_ready": performance is not None,
            "performance_updated_at": now.isoformat()
            if performance is not None
            else None,
            "last_p12_completed_at": last_p12.isoformat() if last_p12 else None,
            "performance_elapsed_seconds": period_seconds,
            "performance_expected_production": estimated_production,
            "performance_production_target": production_target,
            "performance_available_time_minutes": available_time_minutes,
        },
        "downtime_minutes": {
            name: _display_minutes(seconds) for name, seconds in downtime_seconds.items()
        },
        "downtime_overlap_minutes": _display_minutes(overlap_seconds),
        "downtime_seconds": {**downtime_seconds, "overlap": overlap_seconds},
        "production_counts": {
            "stations": {
                str(station): {
                    "produced": good,
                    "defective": defect_counts[station],
                    "good": good,
                    "total": good + defect_counts[station],
                    "completed_cycles": completed_counts[station],
                }
                for station in range(1, 13)
            },
            "line": {
                "produced": good,
                "defective": defective,
                "good": good,
                "total": good + defective,
            },
        },
    }


def synchronize_dashboard_performance(analytics: dict) -> dict:
    """Publish one current denominator for the card, all columns and the OEE.

    Older snapshot providers may still supply the fractional target at the last
    P12. Recalculate from current quantities at the HTTP/WebSocket boundary too,
    without changing the provider's shared dictionary or production records.
    """
    timing = analytics.get("timing")
    counts = analytics.get("production_counts", {})
    line_counts = counts.get("line")
    if not timing or not line_counts or "expected_production" not in timing:
        return analytics

    estimate = floor(timing["expected_production"])
    good = line_counts["good"]
    performance = _performance_percent(good, estimate)
    elapsed = timing["elapsed_seconds"]
    stopped = timing["stopped_seconds"]
    station_counts = counts.get("stations", {})
    return {
        **analytics,
        "timing": {
            **timing,
            "calculation_revision": CALCULATION_REVISION,
            "estimated_production": estimate,
            "performance_expected_production": estimate,
            "performance_elapsed_seconds": elapsed,
            "performance_production_target": timing["production_target"],
            "performance_available_time_minutes": timing["available_time_minutes"],
            "performance_updated_at": analytics.get("period_end")
            if performance is not None
            else None,
            "performance_ready": performance is not None,
        },
        "line": _metric_set(
            elapsed, stopped, performance, good, line_counts["defective"]
        ),
        "stations": {
            station: _metric_set(
                elapsed,
                stopped,
                performance,
                good,
                station_counts[station]["defective"],
            )
            for station in analytics["stations"]
        },
    }
