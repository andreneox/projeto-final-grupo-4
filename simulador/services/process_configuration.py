from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StationConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station: Annotated[int, Field(strict=True, ge=1, le=12)]
    cycle_time_seconds: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
    has_prototype: Annotated[int, Field(strict=True, ge=0, le=1)]


class ProcessConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stations: Annotated[list[StationConfiguration], Field(min_length=12, max_length=12)]

    @model_validator(mode="after")
    def complete_line(self) -> "ProcessConfiguration":
        if {item.station for item in self.stations} != set(range(1, 13)):
            raise ValueError("Informe cada posto de 1 a 12 exatamente uma vez.")
        return self


class ProcessConfigurationStore:
    """The receiver's SQLite stores one atomic configuration for all 12 stations."""

    def __init__(self, path: Path, default_cycle: float = 57.5) -> None:
        # Validate defaults through the same rules used by the API.
        StationConfiguration(station=1, cycle_time_seconds=default_cycle, has_prototype=0)
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, sqlite3.connect(self.path, timeout=10) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS process_configuration (
                    station INTEGER PRIMARY KEY CHECK (station BETWEEN 1 AND 12),
                    cycle_time_seconds REAL NOT NULL CHECK (cycle_time_seconds > 0),
                    has_prototype INTEGER NOT NULL CHECK (has_prototype IN (0, 1)),
                    updated_at TEXT NOT NULL
                )
            """)
            connection.executemany(
                """INSERT OR IGNORE INTO process_configuration
                   (station, cycle_time_seconds, has_prototype, updated_at)
                   VALUES (?, ?, 0, ?)""",
                [(station, default_cycle, now) for station in range(1, 13)],
            )

    def read(self) -> dict:
        with self._lock, sqlite3.connect(self.path, timeout=10) as connection:
            return self._read(connection)

    @staticmethod
    def _read(connection: sqlite3.Connection) -> dict:
        rows = connection.execute("""
            SELECT station, cycle_time_seconds, has_prototype, updated_at
            FROM process_configuration ORDER BY station
        """).fetchall()
        return {
            "stations": [
                {"station": row[0], "cycle_time_seconds": row[1], "has_prototype": row[2]}
                for row in rows
            ],
            "updated_at": max((row[3] for row in rows), default=None),
        }

    def save(self, configuration: ProcessConfiguration) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, sqlite3.connect(self.path, timeout=10) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                """UPDATE process_configuration
                   SET cycle_time_seconds = ?, has_prototype = ?, updated_at = ?
                   WHERE station = ?""",
                [(item.cycle_time_seconds, item.has_prototype, now, item.station)
                 for item in configuration.stations],
            )
            result = self._read(connection)
            connection.commit()
            return result
