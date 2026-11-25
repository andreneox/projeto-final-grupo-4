from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import signal
from concurrent.futures import Future
from datetime import datetime
from zoneinfo import ZoneInfo
from threading import Event

from gateway.config import Settings
from gateway.modbus_transport import PymodbusSerialTransport
from gateway.motor_output import RaspberryMotorOutput
from gateway.ntp_client import SntpClientWorker
from gateway.opcua_server import OpcUaServerWorker
from gateway.persistence import GatewayDatabase
from gateway.plc_poller import PlcPoller
from gateway.tcp_sender import TcpSender


class GatewayApplication:
    def __init__(self, settings: Settings, stop_file: Path | None = None) -> None:
        self._settings = settings
        self._stop_file = stop_file
        self._stop = Event()
        self._logger = logging.getLogger("gateway")
        self._database = GatewayDatabase(
            settings.application.database_path,
            settings.application.gateway_id,
        )
        self._sender = TcpSender(
            settings.tcp,
            self._database,
            lambda status: self._logger.info("TCP: %s", status),
        )
        self._opcua = OpcUaServerWorker(
            settings.opcua,
            lambda status: self._logger.info("OPC UA: %s", status),
            self._request_motor_speed,
            self._request_line_stop,
            cycle_base_callback=lambda times: self._poller.request_cycle_base(times),
            simulation_start_callback=lambda: self._poller.request_simulation_start(),
            cycle_base_ready=lambda: self._poller.cycle_base_ready(),
            base_reset_callback=lambda: self._poller.request_base_reset(),
        )
        self._motor_output = RaspberryMotorOutput(
            settings.motor_output,
            lambda status: self._logger.info("Motor: %s", status),
        )
        transport = PymodbusSerialTransport(settings.modbus)
        self._poller = PlcPoller(
            settings.modbus,
            transport,
            self._database,
            self._opcua.update_telemetry,
            self._motor_output.set_motor_state,
            self._sender.wake,
            lambda status: self._logger.info("Modbus: %s", status),
            motor_fault_callback=self._motor_output.disable,
        )
        self._ntp = SntpClientWorker(
            settings.ntp,
            self._request_clock_sync,
            lambda status: self._logger.info("SNTP: %s", status),
        )

    def set_motor_speed(self, speed: int, timeout: float = 5.0) -> None:
        self._request_motor_speed(speed).result(timeout=timeout)

    def set_line_stopped(self, stopped: bool, timeout: float = 5.0) -> None:
        self._request_line_stop(stopped).result(timeout=timeout)

    def _request_motor_speed(self, speed: int) -> Future[None]:
        return self._poller.request_motor_speed(speed)

    def _request_line_stop(self, stopped: bool) -> Future[None]:
        return self._poller.request_line_stop(stopped)

    def _request_clock_sync(self, timestamp: datetime) -> Future[None]:
        local_time = timestamp.astimezone(
            ZoneInfo(self._settings.application.timezone)
        )
        return self._poller.request_clock_sync(local_time)

    def run(self) -> int:
        if self._stop_file is not None:
            self._stop_file.unlink(missing_ok=True)
        self._database.start()
        self._opcua.start()
        self._sender.start()
        self._motor_output.start()
        self._poller.start()
        self._ntp.start()
        self._logger.info(
            "Gateway %s started", self._settings.application.gateway_id
        )
        try:
            while not self._stop.wait(0.2):
                if self._stop_file is not None and self._stop_file.is_file():
                    self._logger.info("Stop file received")
                    self._stop.set()
        except KeyboardInterrupt:
            self._logger.info("Ctrl+C received")
            self._stop.set()
        finally:
            self._logger.info("Gateway stopping")
            workers = (
                ("motor", self._motor_output.stop),
                ("SNTP", self._ntp.stop),
                ("OPC UA", self._opcua.stop),
                ("Modbus", self._poller.stop),
                ("TCP", self._sender.stop),
                ("SQLite", self._database.stop),
            )
            for name, stop in workers:
                self._logger.info("Stopping %s", name)
                try:
                    stop()
                except Exception:
                    self._logger.exception("Failed to stop %s cleanly", name)
            if self._stop_file is not None:
                self._stop_file.unlink(missing_ok=True)
            self._logger.info("Gateway stopped")
        return 0

    def request_stop(self, *_args) -> None:
        self._logger.info("Stop requested")
        self._stop.set()


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(console)
    root.addHandler(file_handler)


def install_signal_handlers(application: GatewayApplication) -> None:
    # Keep Python's default SIGINT handler so Ctrl+C raises KeyboardInterrupt.
    signal.signal(signal.SIGTERM, application.request_stop)
