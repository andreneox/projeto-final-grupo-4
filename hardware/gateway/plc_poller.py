from __future__ import annotations

from concurrent.futures import Future
from dataclasses import replace
from datetime import datetime
from queue import Empty, Queue
from threading import Event, Thread
import time
from typing import Callable

from gateway.config import ModbusSettings
from gateway.cycle_control import PlcCycleControl, encode_cycle_times
from gateway.domain import StationTelemetry
from gateway.modbus_transport import PlcTransport
from gateway.persistence import GatewayDatabase
from gateway.protocol import decode_event
from gateway.register_map import decode_register_block


TelemetryCallback = Callable[[dict[int, StationTelemetry]], None]
StatusCallback = Callable[[str], None]
WakeCallback = Callable[[], None]
MotorStateCallback = Callable[[bool, int], None]


class PlcPoller:
    def __init__(
        self,
        settings: ModbusSettings,
        transport: PlcTransport,
        database: GatewayDatabase,
        telemetry_callback: TelemetryCallback,
        motor_state_callback: MotorStateCallback,
        event_wake_callback: WakeCallback,
        status_callback: StatusCallback,
        motor_fault_callback: WakeCallback | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._database = database
        self._telemetry_callback = telemetry_callback
        self._motor_state_callback = motor_state_callback
        self._motor_fault_callback = motor_fault_callback
        self._cycles = PlcCycleControl(settings, transport)
        self._event_wake_callback = event_wake_callback
        self._status_callback = status_callback
        self._stop = Event()
        self._thread = Thread(target=self._run, name="modbus-poller", daemon=True)
        self._last_stations: dict[int, StationTelemetry] | None = None
        self._production_count: int | None = None
        self._production_retry_at = 0.0
        self._process_status_available = False
        self._process_status_retry_at = 0.0
        self._presented_payload: bytes | None = None
        self._last_status: str | None = None
        self._commands: Queue[tuple[str, object, Future]] = Queue()

    def start(self) -> None:
        if not self._settings.enabled:
            self._set_status("disabled")
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)
        self._transport.close()
        self._reject_pending_commands("Modbus poller stopped")

    def request_motor_speed(self, speed: int) -> Future[None]:
        if isinstance(speed, bool) or not isinstance(speed, int) or not 0 <= speed <= 100:
            raise ValueError("Motor speed must be an integer between 0 and 100")
        return self._queue_command("motor_speed", speed)

    def request_line_stop(self, stopped: bool) -> Future[None]:
        if not isinstance(stopped, bool):
            raise ValueError("Line stop command must be boolean")
        return self._queue_command("line_stop", stopped)

    def request_clock_sync(self, timestamp: datetime) -> Future[None]:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Clock synchronization requires a timezone-aware timestamp")
        return self._queue_command("clock", timestamp)

    def request_cycle_base(self, times: list[float]) -> Future[None]:
        return self._queue_command("cycle_base", encode_cycle_times(times))

    def request_simulation_start(self) -> Future[datetime | None]:
        return self._queue_command("simulation_start", None)

    def request_base_reset(self) -> Future[datetime]:
        return self._queue_command("base_reset", None)

    def cycle_base_ready(self) -> bool:
        return self._cycles.ready()

    def poll_once(self) -> None:
        try:
            self._cycles.advance()
            self._process_control_commands()
            registers = self._transport.read_register_block()
            snapshot = decode_register_block(
                registers,
                event_byte_order=self._settings.event_byte_order,
                uint32_word_order=self._settings.uint32_word_order,
                time_scale_to_seconds=self._settings.time_scale_to_seconds,
            )
            motor_speed = self._transport.read_motor_speed()
        except Exception as exc:
            self._cycles.communication_failed(exc)
            if self._last_stations and any(
                station.process_status is not None for station in self._last_stations.values()
            ):
                self._publish_stations({
                    number: replace(station, process_status=None)
                    for number, station in self._last_stations.items()
                })
            if self._motor_fault_callback is not None:
                self._motor_fault_callback()
            raise
        self._motor_state_callback(snapshot.motor_on, motor_speed)
        if self._settings.production_count_address is not None:
            self._read_production_count()
            snapshot.stations[12] = replace(
                snapshot.stations[12], production_count=self._production_count
            )
        if self._settings.process_status_address is not None:
            for station, status in enumerate(self._read_process_statuses(), 1):
                snapshot.stations[station] = replace(
                    snapshot.stations[station],
                    process_status=status if 0 <= status <= 3 else None,
                )
        self._publish_stations(snapshot.stations)

        if snapshot.event_payload is None:
            self._presented_payload = None
            return
        if snapshot.event_payload == self._presented_payload:
            return

        decode_event(snapshot.event_payload)
        captured = self._database.capture_event(snapshot.event_payload)
        if captured.crc_collision:
            self._set_status(
                f"critical CRC32 UID collision on event {captured.event_id}"
            )
        self._transport.acknowledge_event()
        self._database.mark_plc_acknowledged(captured.event_id)
        self._presented_payload = snapshot.event_payload
        if captured.delivery_status == "pending":
            self._event_wake_callback()

    def _publish_stations(self, stations: dict[int, StationTelemetry]) -> None:
        if stations != self._last_stations:
            self._telemetry_callback(stations)
            self._last_stations = stations

    def _read_production_count(self) -> None:
        if time.monotonic() < self._production_retry_at:
            return
        try:
            count = self._transport.read_production_count()
        except Exception as exc:
            if not self._production_retry_at:
                self._status_callback(f"production count unavailable: {exc}")
            self._production_retry_at = time.monotonic() + self._settings.reconnect_seconds
        else:
            if self._production_count is None or self._production_retry_at:
                self._status_callback("production count available")
            self._production_count = count
            self._production_retry_at = 0.0

    def _read_process_statuses(self) -> list[int]:
        if time.monotonic() < self._process_status_retry_at:
            return []
        try:
            statuses = self._transport.read_process_statuses()
        except Exception as exc:
            if not self._process_status_retry_at:
                self._status_callback(f"process status unavailable: {exc}")
            self._process_status_available = False
            self._process_status_retry_at = time.monotonic() + self._settings.reconnect_seconds
            return []
        if not self._process_status_available:
            self._status_callback("process status available")
        self._process_status_available = True
        self._process_status_retry_at = 0.0
        return statuses

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                try:
                    self.poll_once()
                    self._set_status("connected")
                    delay = max(0.0, self._settings.poll_interval_seconds - (time.monotonic() - started))
                    release = self._cycles.time_to_release()
                    if release is not None:
                        delay = min(delay, release)
                except Exception as exc:
                    self._transport.close()
                    self._set_status(f"unavailable: {exc}")
                    delay = self._settings.reconnect_seconds
                    release = self._cycles.time_to_release()
                    if release:
                        delay = min(delay, release)
                self._stop.wait(delay)
        finally:
            try:
                self._cycles.stop()
            except OSError as exc:
                self._set_status(f"failed to release PLC command during shutdown: {exc}")

    def _set_status(self, status: str) -> None:
        if status == self._last_status:
            return
        self._last_status = status
        self._status_callback(status)

    def _queue_command(self, name: str, value: object) -> Future:
        future: Future[None] = Future()
        if not self._settings.enabled:
            future.set_exception(RuntimeError("Modbus communication is disabled"))
            return future
        if self._stop.is_set():
            future.set_exception(RuntimeError("Modbus poller is stopped"))
            return future
        self._commands.put((name, value, future))
        return future

    def _process_control_commands(self) -> None:
        while True:
            try:
                name, value, future = self._commands.get_nowait()
            except Empty:
                return
            if not future.set_running_or_notify_cancel():
                continue
            try:
                if name == "clock":
                    assert isinstance(value, datetime)
                    self._transport.synchronize_clock(value)
                elif name == "motor_speed":
                    self._transport.set_motor_speed(int(value))
                elif name == "cycle_base":
                    self._cycles.upload(value, future)
                    continue
                elif name == "simulation_start":
                    self._cycles.start(future)
                    continue
                elif name == "base_reset":
                    self._cycles.reset_base(future)
                    continue
                else:
                    self._transport.set_line_stopped(bool(value))
                future.set_result(None)
            except BaseException as exc:
                future.set_exception(exc)

    def _reject_pending_commands(self, message: str) -> None:
        while True:
            try:
                _name, _value, future = self._commands.get_nowait()
            except Empty:
                return
            if not future.done():
                future.set_exception(RuntimeError(message))
