from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
import sqlite3
from threading import Thread
from typing import Any, Callable

from gateway.domain import CaptureResult, OutboxEvent
from gateway.protocol import crc32, decode_event, make_event_uid


DbTask = tuple[Callable[..., Any] | None, tuple[Any, ...], Future[Any] | None]


class GatewayDatabase:
    """Serializes all SQLite access on one owning thread."""

    def __init__(self, path: Path, gateway_id: str) -> None:
        self._path = path
        self._gateway_id = gateway_id
        self._tasks: Queue[DbTask] = Queue()
        self._thread = Thread(target=self._run, name="sqlite-worker", daemon=True)

    def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._thread.start()
        self._submit(self._initialize).result(timeout=10)

    def stop(self) -> None:
        if not self._thread.is_alive():
            return
        self._tasks.put((None, (), None))
        self._thread.join(timeout=10)

    def capture_event(self, payload: bytes) -> CaptureResult:
        return self._submit(
            self._capture_event, self._gateway_id, payload
        ).result(timeout=10)

    def mark_plc_acknowledged(self, event_id: int) -> None:
        self._submit(self._mark_plc_acknowledged, event_id).result(timeout=10)

    def first_pending(self) -> OutboxEvent | None:
        return self._submit(self._first_pending).result(timeout=10)

    def mark_confirmed(self, event_id: int) -> None:
        self._submit(self._mark_confirmed, event_id).result(timeout=10)

    def record_failure(self, event_id: int, error: str) -> None:
        self._submit(self._record_failure, event_id, error).result(timeout=10)

    def counts(self) -> tuple[int, int]:
        return self._submit(self._counts).result(timeout=10)

    def _submit(self, operation: Callable[..., Any], *args: Any) -> Future[Any]:
        future: Future[Any] = Future()
        self._tasks.put((operation, args, future))
        return future

    def _run(self) -> None:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
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
            CREATE TABLE IF NOT EXISTS gateway_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gateway_id TEXT NOT NULL,
                event_uid TEXT NOT NULL,
                crc32 INTEGER NOT NULL,
                payload BLOB NOT NULL CHECK(length(payload) = 16),
                station INTEGER NOT NULL CHECK(station BETWEEN 1 AND 12),
                button_id INTEGER NOT NULL CHECK(button_id BETWEEN 1 AND 4),
                status INTEGER NOT NULL CHECK(status IN (1, 2)),
                occurred_at TEXT NOT NULL,
                plc_acknowledged INTEGER NOT NULL DEFAULT 0
                    CHECK(plc_acknowledged IN (0, 1)),
                plc_acknowledged_at TEXT,
                delivery_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(delivery_status IN ('pending', 'confirmed')),
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                captured_at TEXT NOT NULL,
                last_attempt_at TEXT,
                confirmed_at TEXT,
                UNIQUE(gateway_id, payload)
            );
            CREATE INDEX IF NOT EXISTS idx_gateway_event_pending
                ON gateway_event(delivery_status, id);
            CREATE INDEX IF NOT EXISTS idx_gateway_event_uid
                ON gateway_event(gateway_id, event_uid);
            """
        )
        connection.commit()

    @staticmethod
    def _capture_event(
        connection: sqlite3.Connection, gateway_id: str, payload: bytes
    ) -> CaptureResult:
        event = decode_event(payload)
        event_uid = make_event_uid(gateway_id, payload)
        checksum = crc32(payload)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT id, delivery_status, plc_acknowledged
                   FROM gateway_event
                   WHERE gateway_id = ? AND payload = ?""",
                (gateway_id, payload),
            ).fetchone()
            collision = connection.execute(
                """SELECT 1 FROM gateway_event
                   WHERE gateway_id = ? AND event_uid = ? AND payload <> ?
                   LIMIT 1""",
                (gateway_id, event_uid, payload),
            ).fetchone() is not None
            if existing is not None:
                connection.commit()
                return CaptureResult(
                    event_id=int(existing["id"]),
                    inserted=False,
                    crc_collision=collision,
                    delivery_status=str(existing["delivery_status"]),
                    plc_acknowledged=bool(existing["plc_acknowledged"]),
                )

            now = datetime.now(timezone.utc).isoformat()
            cursor = connection.execute(
                """INSERT INTO gateway_event (
                       gateway_id, event_uid, crc32, payload, station,
                       button_id, status, occurred_at, captured_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    gateway_id,
                    event_uid,
                    checksum,
                    payload,
                    event.station,
                    event.category.button_id,
                    1 if event.is_on else 2,
                    event.occurred_at.isoformat(),
                    now,
                ),
            )
            connection.commit()
            return CaptureResult(
                event_id=int(cursor.lastrowid),
                inserted=True,
                crc_collision=collision,
                delivery_status="pending",
                plc_acknowledged=False,
            )
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _mark_plc_acknowledged(
        connection: sqlite3.Connection, event_id: int
    ) -> None:
        connection.execute(
            """UPDATE gateway_event
               SET plc_acknowledged = 1, plc_acknowledged_at = ?
               WHERE id = ?""",
            (datetime.now(timezone.utc).isoformat(), event_id),
        )
        connection.commit()

    @staticmethod
    def _first_pending(connection: sqlite3.Connection) -> OutboxEvent | None:
        row = connection.execute(
            """SELECT id, payload, attempts FROM gateway_event
               WHERE delivery_status = 'pending' ORDER BY id LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        return OutboxEvent(int(row["id"]), bytes(row["payload"]), int(row["attempts"]))

    @staticmethod
    def _mark_confirmed(connection: sqlite3.Connection, event_id: int) -> None:
        connection.execute(
            """UPDATE gateway_event
               SET delivery_status = 'confirmed', confirmed_at = ?, last_error = NULL
               WHERE id = ? AND delivery_status = 'pending'""",
            (datetime.now(timezone.utc).isoformat(), event_id),
        )
        connection.commit()

    @staticmethod
    def _record_failure(
        connection: sqlite3.Connection, event_id: int, error: str
    ) -> None:
        connection.execute(
            """UPDATE gateway_event
               SET attempts = attempts + 1, last_error = ?, last_attempt_at = ?
               WHERE id = ? AND delivery_status = 'pending'""",
            (error[:1000], datetime.now(timezone.utc).isoformat(), event_id),
        )
        connection.commit()

    @staticmethod
    def _counts(connection: sqlite3.Connection) -> tuple[int, int]:
        rows = connection.execute(
            """SELECT delivery_status, COUNT(*) count
               FROM gateway_event GROUP BY delivery_status"""
        ).fetchall()
        values = {str(row["delivery_status"]): int(row["count"]) for row in rows}
        return values.get("pending", 0), values.get("confirmed", 0)

