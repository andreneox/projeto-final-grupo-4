from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import socketserver
import sqlite3
from threading import Lock
from zoneinfo import ZoneInfo

from communications.opcua_client import OpcUaClientWorker
from communications.desktop_start import DesktopStartClient
from config.settings import load_settings
from domain.models import AndonCategory, AndonEvent
from domain.production_plan import ProductionPlan
from domain.runtime_events import (
    AndonRuntime,
    CycleRuntime,
    ResetRuntime,
    PlanRuntime,
    SessionRuntime,
)
from persistence.runtime_store import (
    begin_measurement,
    read_production_plan,
    read_performance_snapshot,
    write_production_plan,
    clear_production_day,
    day_bounds,
    initialize_production,
    insert_cycle,
)
from protocol.tcp_codec import (
    ACK,
    EVENT_TYPE,
    SIMULATOR_EVENT_TYPE,
    TIME_REQUEST,
    TIME_REQUEST_TYPE,
    decode_event,
    encode_time_response,
    encode_event,
)
from services.analytics import calculate_dashboard_metrics
from services.telemetry import TelemetryStore
from services.process_configuration import ProcessConfigurationStore
from services.runtime_receiver import handle_runtime_event
from web.dashboard import DashboardServerWorker


class ReceiverDatabase:
    def __init__(self, path: Path, timezone_name: str = "America/Manaus") -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self.timezone = ZoneInfo(timezone_name)
        with sqlite3.connect(self.path) as connection:
            connection.executescript(
                """
                PRAGMA synchronous=FULL;
                CREATE TABLE IF NOT EXISTS stop_occurrence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station INTEGER NOT NULL,
                    button_id INTEGER NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_open_occurrence
                    ON stop_occurrence(station, button_id) WHERE closed_at IS NULL;
                CREATE TABLE IF NOT EXISTS key_reference (
                    station INTEGER NOT NULL,
                    button_id INTEGER NOT NULL,
                    occurred_at TEXT NOT NULL,
                    PRIMARY KEY (station, button_id)
                );
                CREATE TABLE IF NOT EXISTS reception (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_at TEXT NOT NULL,
                    occurred_at TEXT,
                    raw BLOB NOT NULL,
                    message_type INTEGER,
                    station INTEGER,
                    button_id INTEGER,
                    status INTEGER,
                    result TEXT NOT NULL,
                    occurrence_id INTEGER REFERENCES stop_occurrence(id)
                );
                CREATE INDEX IF NOT EXISTS idx_reception_andon_raw
                    ON reception(raw) WHERE station IS NOT NULL;
                """
            )
            initialize_production(connection)
            connection.execute("""CREATE TABLE IF NOT EXISTS runtime_receipt (
                event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, received_at TEXT NOT NULL
            )""")
            # Each historical ON transition represents one defect, not the OFF/ACK/retry.
            connection.execute("""INSERT OR IGNORE INTO defect_item
                SELECT 'reception:' || id, station, occurred_at FROM reception
                WHERE message_type IN (?, ?) AND button_id=1 AND result='ON'""",
                (EVENT_TYPE, SIMULATOR_EVENT_TYPE),
            )

    def dashboard_metrics(
        self,
        now: datetime,
        shift_start: str,
        shift_duration_minutes: int,
        plc_production_count: int | None = None,
    ) -> dict:
        with self.lock, sqlite3.connect(self.path) as connection:
            occurrences = connection.execute(
                """SELECT station, button_id, opened_at, closed_at
                   FROM stop_occurrence"""
            ).fetchall()
            cycles = connection.execute(
                "SELECT station, completed_at FROM production_cycle"
            ).fetchall()
            defects = connection.execute(
                "SELECT station, occurred_at FROM defect_item"
            ).fetchall()
            plan = read_production_plan(connection)
            performance_snapshot = read_performance_snapshot(connection)
            measurement = connection.execute(
                "SELECT value FROM runtime_meta WHERE key='measurement_started_at'"
            ).fetchone()
            reset = connection.execute(
                "SELECT value FROM runtime_meta WHERE key='last_reset_at'"
            ).fetchone()
            waiting_for_start = connection.execute(
                "SELECT 1 FROM runtime_meta WHERE key='plc_waiting_for_start'"
            ).fetchone() is not None
            # TCP-only installations keep using the configured shift.
            measurement_active = bool(measurement or reset) or connection.execute(
                "SELECT 1 FROM reception WHERE message_type = ? AND station IS NOT NULL LIMIT 1",
                (EVENT_TYPE,),
            ).fetchone() is not None
        return calculate_dashboard_metrics(
            occurrences,
            now,
            shift_start,
            shift_duration_minutes,
            production_cycles=cycles,
            defects=defects,
            reset_at=reset[0] if reset else None,
            measurement_started_at=measurement[0]
            if measurement
            else (reset[0] if reset else None),
            measurement_active=measurement_active and not waiting_for_start,
            performance_snapshot=performance_snapshot,
            plc_production_count=0 if waiting_for_start else plc_production_count,
            production_target=plan.production_target,
            available_time_minutes=plan.available_time_minutes,
        )

    def begin_plc_session(self, confirmed_at: datetime) -> None:
        with self.lock, sqlite3.connect(self.path) as connection:
            begin_measurement(connection, confirmed_at.astimezone(self.timezone))

    def production_plan(self) -> ProductionPlan:
        with self.lock, sqlite3.connect(self.path) as connection:
            return read_production_plan(connection)

    def imported_cycle_base(self) -> dict | None:
        with self.lock, sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT value FROM runtime_meta WHERE key='imported_cycle_base'"
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_imported_cycle_base(self, filename: str, takt_times: list[float]) -> None:
        details = json.dumps({"filename": filename, "takt_times": takt_times}, ensure_ascii=False)
        with self.lock, sqlite3.connect(self.path) as connection:
            connection.execute(
                """INSERT INTO runtime_meta(key, value) VALUES ('imported_cycle_base', ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (details,),
            )

    def save_production_plan(self, plan: ProductionPlan) -> None:
        with self.lock, sqlite3.connect(self.path) as connection:
            write_production_plan(connection, plan)

    def clear_plc_base(self, confirmed_at: datetime) -> None:
        with self.lock, sqlite3.connect(self.path, timeout=10) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._reset_day_sql(connection, confirmed_at.astimezone(self.timezone))
            connection.execute("DELETE FROM runtime_meta WHERE key='measurement_started_at'")
            connection.execute(
                "INSERT INTO runtime_meta(key, value) VALUES ('plc_waiting_for_start', '1')"
            )

    def record_invalid(self, raw: bytes, received_at: datetime, result: str) -> None:
        with self.lock, sqlite3.connect(self.path) as connection:
            connection.execute(
                """INSERT INTO reception(received_at, raw, result)
                   VALUES (?, ?, ?)""",
                (received_at.isoformat(), raw, result),
            )

    def record_time_request(self, raw: bytes, received_at: datetime) -> None:
        with self.lock, sqlite3.connect(self.path) as connection:
            connection.execute(
                """INSERT INTO reception(received_at, raw, message_type, result)
                   VALUES (?, ?, ?, 'TIME_REQUEST')""",
                (received_at.isoformat(), raw, TIME_REQUEST_TYPE),
            )

    def _apply_event_sql(
        self,
        connection,
        raw: bytes,
        received_at: datetime,
        precise_time: datetime | None = None,
    ) -> str:
        event = decode_event(raw)
        event_time = precise_time or event.occurred_at.replace(
            tzinfo=received_at.tzinfo
        )
        if self._before_reset(connection, event_time):
            return "IGNORADO_LIMPEZA"
        key = (event.station, event.category.button_id)
        reference = connection.execute(
            """SELECT occurred_at FROM key_reference
                       WHERE station = ? AND button_id = ?""",
            key,
        ).fetchone()
        occurrence_id: int | None = None
        if reference and event_time < datetime.fromisoformat(reference["occurred_at"]):
            result = "ATRASADO"
        else:
            open_row = connection.execute(
                """SELECT id FROM stop_occurrence
                           WHERE station = ? AND button_id = ? AND closed_at IS NULL""",
                key,
            ).fetchone()
            if event.is_on and open_row:
                result = "ON_REPETIDO"
                occurrence_id = int(open_row["id"])
            elif event.is_on:
                cursor = connection.execute(
                    """INSERT INTO stop_occurrence
                               (station, button_id, opened_at) VALUES (?, ?, ?)""",
                    (*key, event_time.isoformat()),
                )
                occurrence_id = int(cursor.lastrowid)
                result = "ON"
            elif open_row:
                occurrence_id = int(open_row["id"])
                connection.execute(
                    "UPDATE stop_occurrence SET closed_at = ? WHERE id = ?",
                    (event_time.isoformat(), occurrence_id),
                )
                result = "OFF"
            else:
                result = "OFF_SEM_ABERTURA"
            connection.execute(
                """INSERT INTO key_reference(station, button_id, occurred_at)
                           VALUES (?, ?, ?)
                           ON CONFLICT(station, button_id)
                           DO UPDATE SET occurred_at = excluded.occurred_at""",
                (*key, event_time.isoformat()),
            )
        reception = connection.execute(
            """INSERT INTO reception
                       (received_at, occurred_at, raw, message_type, station,
                        button_id, status, result, occurrence_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                received_at.isoformat(),
                event_time.isoformat(),
                raw,
                int.from_bytes(raw[:2], "big"),
                event.station,
                event.category.button_id,
                1 if event.is_on else 2,
                result,
                occurrence_id,
            ),
        )
        if result == "ON" and event.category == AndonCategory.QUALIDADE:
            connection.execute(
                "INSERT INTO defect_item VALUES (?, ?, ?)",
                (
                    f"reception:{reception.lastrowid}",
                    event.station,
                    event_time.isoformat(),
                ),
            )
        return result

    def apply_event(self, raw: bytes, received_at: datetime) -> str:
        with self.lock, sqlite3.connect(self.path, timeout=10) as connection:
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("BEGIN IMMEDIATE")
                # The Gateway resends the same bytes when it misses the ACK.
                if int.from_bytes(raw[:2], "big") == EVENT_TYPE:
                    duplicate = connection.execute(
                        """INSERT INTO reception (
                               received_at, occurred_at, raw, message_type, station,
                               button_id, status, result, occurrence_id
                           )
                           SELECT ?, occurred_at, raw, message_type, station,
                                  button_id, status, 'DUPLICADO', occurrence_id
                           FROM reception
                           WHERE raw = ? AND station IS NOT NULL
                           ORDER BY id LIMIT 1""",
                        (received_at.isoformat(), raw),
                    ).rowcount
                    if duplicate:
                        connection.commit()
                        return "DUPLICADO"
                result = self._apply_event_sql(connection, raw, received_at)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _before_reset(connection, moment) -> bool:
        reset = connection.execute(
            "SELECT value FROM runtime_meta WHERE key='last_reset_at'"
        ).fetchone()
        return bool(reset and moment <= datetime.fromisoformat(reset[0]))

    def apply_runtime(self, event) -> dict:
        event_id = str(event.event_id)
        fingerprint = hashlib.sha256(
            event.model_dump_json(exclude_none=True).encode()
        ).hexdigest()
        with self.lock, sqlite3.connect(self.path, timeout=10) as connection:
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("BEGIN IMMEDIATE")
                receipt = connection.execute(
                    "SELECT fingerprint FROM runtime_receipt WHERE event_id=?",
                    (event_id,),
                ).fetchone()
                if receipt:
                    if receipt[0] != fingerprint:
                        raise ValueError(
                            "O identificador já foi usado para outro evento."
                        )
                    connection.rollback()
                    return {"event_id": event_id, "result": "duplicate"}
                result = "applied"
                andon_result = None
                if isinstance(event, PlanRuntime):
                    write_production_plan(connection, event.production_plan)
                elif self._before_reset(connection, event.occurred_at):
                    result = "ignored_before_reset"
                elif isinstance(event, AndonRuntime):
                    raw = encode_event(
                        AndonEvent(
                            event.station,
                            AndonCategory.from_button_id(event.button_id),
                            event.is_on,
                            event.occurred_at,
                        ),
                        message_type=SIMULATOR_EVENT_TYPE,
                    )
                    andon_result = self._apply_event_sql(
                        connection, raw, datetime.now(self.timezone), event.occurred_at
                    )
                elif isinstance(event, CycleRuntime):
                    insert_cycle(connection, event)
                elif isinstance(event, SessionRuntime):
                    begin_measurement(
                        connection, event.occurred_at, event.production_plan
                    )
                elif isinstance(event, ResetRuntime):
                    self._reset_day_sql(
                        connection, event.occurred_at.astimezone(self.timezone)
                    )
                    if event.production_plan is not None:
                        write_production_plan(connection, event.production_plan)
                connection.execute(
                    "INSERT INTO runtime_receipt VALUES (?, ?, ?)",
                    (event_id, fingerprint, datetime.now(self.timezone).isoformat()),
                )
                connection.commit()
                response = {"event_id": event_id, "result": result}
                if andon_result is not None:
                    response["andon_result"] = andon_result
                return response
            except BaseException:
                connection.rollback()
                raise

    def _reset_day_sql(self, connection, moment) -> None:
        start, end = day_bounds(moment)
        clear_production_day(connection, moment)
        begin_measurement(connection, moment)
        # Remove today's receptions first. Keep historical receptions and closed intervals.
        connection.execute(
            """DELETE FROM reception WHERE
            julianday(COALESCE(occurred_at, received_at))>=julianday(?) AND
            julianday(COALESCE(occurred_at, received_at))<julianday(?) AND
            julianday(COALESCE(occurred_at, received_at))<=julianday(?)""",
            (start.isoformat(), end.isoformat(), moment.isoformat()),
        )
        connection.execute(
            """DELETE FROM stop_occurrence WHERE julianday(opened_at)>=julianday(?)
            AND julianday(opened_at)<julianday(?) AND julianday(opened_at)<=julianday(?)""",
            (start.isoformat(), end.isoformat(), moment.isoformat()),
        )
        # An interval opened yesterday is closed at midnight, preserving yesterday's duration.
        connection.execute(
            """UPDATE stop_occurrence SET closed_at=? WHERE julianday(opened_at)<julianday(?)
            AND (closed_at IS NULL OR julianday(closed_at)>julianday(?))""",
            (start.isoformat(), start.isoformat(), start.isoformat()),
        )
        connection.execute(
            """DELETE FROM key_reference WHERE julianday(occurred_at)>=julianday(?)
            AND julianday(occurred_at)<=julianday(?)""",
            (start.isoformat(), moment.isoformat()),
        )


def receive_exact(connection: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


class LineRequestHandler(socketserver.BaseRequestHandler):
    server: "ReferenceServer"

    def handle(self) -> None:
        self.request.settimeout(5)
        raw = receive_exact(self.request, 16)
        received_at = datetime.now(self.server.timezone)
        if raw == TIME_REQUEST:
            try:
                self.server.database.record_time_request(raw, received_at)
            except Exception as exc:
                print(
                    f"[{received_at.isoformat()}] ERRO pedido de hora: {exc}",
                    flush=True,
                )
                return
            self.request.sendall(encode_time_response(received_at))
            print(f"[{received_at.isoformat()}] HORA respondida", flush=True)
            return
        if len(raw) != 16:
            try:
                self.server.database.record_invalid(
                    raw, received_at, "TAMANHO_INVALIDO"
                )
            except Exception:
                pass
            print(
                f"[{received_at.isoformat()}] INVALIDO tamanho={len(raw)} sem ACK",
                flush=True,
            )
            return
        try:
            event = decode_event(raw)
            result = self.server.database.apply_event(raw, received_at)
        except Exception as exc:
            try:
                self.server.database.record_invalid(
                    raw, received_at, f"INVALIDO: {exc}"
                )
            except Exception:
                pass
            print(
                f"[{received_at.isoformat()}] INVALIDO erro={exc} sem ACK",
                flush=True,
            )
            return
        self.request.sendall(ACK)
        state = "ON" if event.is_on else "OFF"
        print(
            f"[{received_at.isoformat()}] posto={event.station:02d} "
            f"botao={event.category.label} estado={state} "
            f"resultado={result} ACK=enviado",
            flush=True,
        )


class ReferenceServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        database: ReceiverDatabase,
        timezone_name: str,
    ) -> None:
        super().__init__(address, LineRequestHandler)
        self.database = database
        self.timezone = ZoneInfo(timezone_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Receptor TCP de referencia")
    parser.add_argument("--config", default="config.toml")
    args = parser.parse_args()
    settings = load_settings(args.config)
    receiver_settings = settings.receiver
    database = ReceiverDatabase(
        receiver_settings.database_path, receiver_settings.timezone
    )
    configuration_store = ProcessConfigurationStore(
        receiver_settings.database_path, settings.application.last_cycle_seconds
    )
    telemetry = TelemetryStore()
    timezone = ZoneInfo(receiver_settings.timezone)
    uses_plc = settings.opcua_client.enabled and not settings.desktop_api.start_url

    def snapshot() -> dict:
        opcua_snapshot = telemetry.snapshot(settings.dashboard.opcua_stale_seconds)
        return {
            "opcua": opcua_snapshot,
            "imported_cycle_base": database.imported_cycle_base() if uses_plc else None,
            "analytics": database.dashboard_metrics(
                datetime.now(timezone),
                settings.dashboard.shift_start,
                settings.dashboard.shift_duration_minutes,
                plc_production_count=opcua_snapshot["plc_production_count"] if uses_plc else None,
            ),
        }

    def handle_runtime(event) -> dict:
        return handle_runtime_event(database, telemetry, event)

    opcua = OpcUaClientWorker(
        settings.opcua_client,
        telemetry,
        lambda status: print(f"Cliente OPC UA: {status}", flush=True),
    )
    dashboard = DashboardServerWorker(
        settings.dashboard,
        snapshot,
        lambda status: print(f"Dashboard web: {status}", flush=True),
        configuration_store=configuration_store,
        desktop_start=DesktopStartClient(
            settings.desktop_api.start_url, settings.desktop_api.timeout_seconds
        ),
        runtime_handler=handle_runtime,
        instruction_provider=telemetry.instruction_snapshot,
        plc_control=opcua if uses_plc else None,
        plc_session_started=database.begin_plc_session,
        read_plan=database.production_plan,
        save_plan=database.save_production_plan,
        plc_base_cleared=database.clear_plc_base,
        cycle_base_imported=database.save_imported_cycle_base,
    )
    opcua.start()
    dashboard.start()
    try:
        with ReferenceServer(
            (receiver_settings.host, receiver_settings.port),
            database,
            receiver_settings.timezone,
        ) as server:
            print(
                f"Receptor TCP ouvindo em "
                f"{receiver_settings.host}:{receiver_settings.port}",
                flush=True,
            )
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        opcua.stop()
        dashboard.stop()


if __name__ == "__main__":
    main()
