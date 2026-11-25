from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
import sqlite3
from threading import Thread
from typing import Any, Callable

from domain.models import AndonCategory, AndonEvent, OutboxEvent
from protocol.tcp_codec import encode_event

DbTask = tuple[Callable[..., Any] | None, tuple[Any, ...], Future[Any] | None]


class DatabaseWorker:
    """Owns the only SQLite connection and executes commands serially."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._tasks: Queue[DbTask] = Queue()
        self._thread = Thread(target=self._run, name="sqlite-worker", daemon=True)

    def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._thread.start()
        self.submit(self._initialize).result(timeout=10)

    def stop(self) -> None:
        if not self._thread.is_alive():
            return
        self._tasks.put((None, (), None))
        self._thread.join(timeout=10)

    def submit(self, operation: Callable[..., Any], *args: Any) -> Future[Any]:
        future: Future[Any] = Future()
        self._tasks.put((operation, args, future))
        return future

    def _run(self) -> None:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            while True:
                operation, args, future = self._tasks.get()
                if operation is None:
                    break
                assert future is not None
                if not future.set_running_or_notify_cancel():
                    continue
                try:
                    future.set_result(operation(connection, *args))
                except BaseException as exc:
                    future.set_exception(exc)
        finally:
            connection.close()

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS andon_state (
                station INTEGER NOT NULL CHECK(station BETWEEN 1 AND 12),
                category TEXT NOT NULL,
                is_on INTEGER NOT NULL CHECK(is_on IN (0, 1)),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (station, category)
            );
            CREATE TABLE IF NOT EXISTS outbox_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload BLOB NOT NULL CHECK(length(payload) = 16),
                station INTEGER NOT NULL,
                button_id INTEGER NOT NULL,
                status INTEGER NOT NULL CHECK(status IN (1, 2)),
                occurred_at TEXT NOT NULL,
                delivery_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(delivery_status IN ('pending', 'confirmed')),
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                confirmed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_outbox_pending
                ON outbox_event(delivery_status, id);
            """
        )
        now = datetime.now(timezone.utc).isoformat()
        connection.executemany(
            """INSERT OR IGNORE INTO andon_state
               (station, category, is_on, updated_at) VALUES (?, ?, 0, ?)""",
            (
                (station, category.name, now)
                for station in range(1, 13)
                for category in AndonCategory
            ),
        )
        connection.commit()

    @staticmethod
    def load_states(connection: sqlite3.Connection) -> dict[tuple[int, AndonCategory], bool]:
        rows = connection.execute(
            "SELECT station, category, is_on FROM andon_state"
        ).fetchall()
        return {
            (row["station"], AndonCategory[row["category"]]): bool(row["is_on"])
            for row in rows
        }

    @staticmethod
    def toggle_and_enqueue(
        connection: sqlite3.Connection,
        station: int,
        category: AndonCategory,
        occurred_at: datetime,
    ) -> tuple[bool, int, bytes]:
        if not 1 <= station <= 12:
            raise ValueError("Station must be between 1 and 12")
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT is_on FROM andon_state WHERE station = ? AND category = ?",
                (station, category.name),
            ).fetchone()
            if row is None:
                raise RuntimeError("Andon state row is missing")
            new_state = not bool(row["is_on"])
            event = AndonEvent(station, category, new_state, occurred_at)
            payload = encode_event(event)
            timestamp = occurred_at.isoformat()
            connection.execute(
                """UPDATE andon_state SET is_on = ?, updated_at = ?
                   WHERE station = ? AND category = ?""",
                (int(new_state), timestamp, station, category.name),
            )
            cursor = connection.execute(
                """INSERT INTO outbox_event
                   (payload, station, button_id, status, occurred_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    payload,
                    station,
                    category.button_id,
                    1 if new_state else 2,
                    timestamp,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
            return new_state, int(cursor.lastrowid), payload
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def first_pending(connection: sqlite3.Connection) -> OutboxEvent | None:
        row = connection.execute(
            """SELECT id, payload, attempts FROM outbox_event
               WHERE delivery_status = 'pending' ORDER BY id LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        return OutboxEvent(int(row["id"]), bytes(row["payload"]), int(row["attempts"]))

    @staticmethod
    def record_failure(connection: sqlite3.Connection, event_id: int, error: str) -> None:
        connection.execute(
            """UPDATE outbox_event SET attempts = attempts + 1, last_error = ?
               WHERE id = ? AND delivery_status = 'pending'""",
            (error[:1000], event_id),
        )
        connection.commit()

    @staticmethod
    def mark_confirmed(connection: sqlite3.Connection, event_id: int) -> None:
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE outbox_event
                   SET delivery_status = 'confirmed', confirmed_at = ?, last_error = NULL
                   WHERE id = ? AND delivery_status = 'pending'""",
                (datetime.now(timezone.utc).isoformat(), event_id),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def counts(connection: sqlite3.Connection) -> tuple[int, int]:
        rows = connection.execute(
            "SELECT delivery_status, COUNT(*) count FROM outbox_event GROUP BY delivery_status"
        ).fetchall()
        values = {row["delivery_status"]: row["count"] for row in rows}
        return int(values.get("pending", 0)), int(values.get("confirmed", 0))

