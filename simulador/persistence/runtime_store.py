from __future__ import annotations

from datetime import datetime, time, timedelta
import sqlite3
import json

from domain.runtime_events import CycleRuntime
from domain.production_plan import ProductionPlan


def initialize_production(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS production_cycle (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            station INTEGER NOT NULL CHECK(station BETWEEN 1 AND 12),
            recipe_step INTEGER NOT NULL CHECK(recipe_step > 0),
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            takt_time_seconds REAL NOT NULL CHECK(takt_time_seconds >= 0),
            cycle_time_seconds REAL NOT NULL CHECK(cycle_time_seconds > 0),
            source_name TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_production_completed ON production_cycle(completed_at, station);
        CREATE TABLE IF NOT EXISTS defect_item (
            event_id TEXT PRIMARY KEY,
            station INTEGER NOT NULL CHECK(station BETWEEN 1 AND 12),
            occurred_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runtime_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS production_plan (
            id INTEGER PRIMARY KEY CHECK(id=1),
            production_target INTEGER NOT NULL CHECK(production_target>0),
            available_time_minutes REAL NOT NULL CHECK(available_time_minutes>0)
        );
        INSERT OR IGNORE INTO production_plan VALUES (1, 480, 480.0);
    """)

    if read_performance_snapshot(connection) is None:
        capture_performance_snapshot(connection)


def insert_cycle(connection: sqlite3.Connection, event: CycleRuntime) -> None:
    cursor = connection.execute(
        """INSERT OR IGNORE INTO production_cycle
        (event_id, run_id, station, recipe_step, started_at, completed_at,
         takt_time_seconds, cycle_time_seconds, source_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(event.event_id),
            str(event.run_id),
            event.station,
            event.recipe_step,
            event.started_at.isoformat(),
            event.occurred_at.isoformat(),
            event.takt_time_seconds,
            event.cycle_time_seconds,
            event.source_name,
        ),
    )

    if cursor.rowcount and event.station == 12:
        capture_performance_snapshot(connection)


def read_performance_snapshot(connection: sqlite3.Connection) -> dict | None:
    row = connection.execute(
        "SELECT value FROM runtime_meta WHERE key='performance_at_p12'"
    ).fetchone()
    return json.loads(row[0]) if row else None


def capture_performance_snapshot(connection: sqlite3.Connection) -> None:
    start = connection.execute(
        "SELECT value FROM runtime_meta WHERE key='measurement_started_at'"
    ).fetchone()
    if start is None:
        start = connection.execute(
            "SELECT value FROM runtime_meta WHERE key='last_reset_at'"
        ).fetchone()
    if start is None:
        return
    latest = connection.execute(
        """SELECT completed_at FROM production_cycle WHERE station=12
        AND julianday(completed_at)>=julianday(?) ORDER BY julianday(completed_at) DESC, event_id DESC LIMIT 1""",
        (start[0],),
    ).fetchone()
    if latest is None:
        return
    previous = read_performance_snapshot(connection)
    if (
        previous
        and previous["completed_at"] == latest[0]
        and previous["measurement_started_at"] == start[0]
    ):
        return
    snapshot = {
        "measurement_started_at": start[0],
        "completed_at": latest[0],
        "production_plan": read_production_plan(connection).model_dump(),
    }
    connection.execute(
        """INSERT INTO runtime_meta(key, value) VALUES ('performance_at_p12', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (json.dumps(snapshot),),
    )


def read_production_plan(connection: sqlite3.Connection) -> ProductionPlan:
    row = connection.execute(
        "SELECT production_target, available_time_minutes FROM production_plan WHERE id=1"
    ).fetchone()
    return ProductionPlan(production_target=row[0], available_time_minutes=row[1])


def write_production_plan(connection: sqlite3.Connection, plan: ProductionPlan) -> None:
    connection.execute(
        "UPDATE production_plan SET production_target=?, available_time_minutes=? WHERE id=1",
        (plan.production_target, plan.available_time_minutes),
    )


def begin_measurement(
    connection: sqlite3.Connection, moment: datetime, plan: ProductionPlan | None = None
) -> None:
    connection.execute(
        """INSERT INTO runtime_meta(key, value) VALUES ('measurement_started_at', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (moment.isoformat(),),
    )
    connection.execute("DELETE FROM runtime_meta WHERE key IN ('performance_at_p12', 'plc_waiting_for_start')")
    if plan is not None:
        write_production_plan(connection, plan)


def day_bounds(moment: datetime) -> tuple[datetime, datetime]:
    start = datetime.combine(moment.date(), time.min, moment.tzinfo)
    return start, start + timedelta(days=1)


def clear_production_day(connection: sqlite3.Connection, moment: datetime) -> None:
    start, end = day_bounds(moment)
    for table, column in [
        ("production_cycle", "completed_at"),
        ("defect_item", "occurred_at"),
    ]:
        connection.execute(
            f"""DELETE FROM {table}
            WHERE julianday({column}) >= julianday(?) AND julianday({column}) < julianday(?)
              AND julianday({column}) <= julianday(?)""",
            (start.isoformat(), end.isoformat(), moment.isoformat()),
        )
    connection.execute(
        """INSERT INTO runtime_meta(key, value) VALUES ('last_reset_at', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (moment.isoformat(),),
    )
