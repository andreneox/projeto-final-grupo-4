from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime, timezone
import socket
import struct
from threading import Event, Thread
import time
from typing import Callable

from gateway.config import NtpSettings


NTP_EPOCH_DELTA = 2_208_988_800
NTP_PACKET_SIZE = 48
TimeCallback = Callable[[datetime], Future[None]]
StatusCallback = Callable[[str], None]
QueryCallback = Callable[[str, int, float], datetime]
SystemTimeCallback = Callable[[], datetime]


def system_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def query_sntp(server: str, port: int, timeout: float) -> datetime:
    errors: list[str] = []

    for family, socktype, proto, _name, address in socket.getaddrinfo(
        server, port, type=socket.SOCK_DGRAM
    ):
        try:
            with socket.socket(family, socktype, proto) as connection:
                connection.settimeout(timeout)
                connection.connect(address)
                sent_at = time.time()
                request = bytearray(NTP_PACKET_SIZE)
                request[0] = 0x23  # No warning, NTPv4, client mode.
                request[40:48] = _encode_timestamp(sent_at)
                connection.send(request)
                response = connection.recv(512)
                received_at = time.time()
            return decode_sntp_response(
                response, bytes(request[40:48]), sent_at, received_at
            )
        except OSError as exc:
            errors.append(str(exc))
    detail = "; ".join(errors) or "no address resolved"
    raise ConnectionError(f"SNTP query to {server}:{port} failed: {detail}")


def decode_sntp_response(
    response: bytes,
    request_transmit: bytes,
    sent_at: float,
    received_at: float,
) -> datetime:
    if len(response) < NTP_PACKET_SIZE:
        raise ValueError(f"SNTP response has {len(response)} bytes, expected 48")
    leap = response[0] >> 6
    version = (response[0] >> 3) & 0x07
    mode = response[0] & 0x07
    stratum = response[1]
    if leap == 3:
        raise ValueError("SNTP server reports an unsynchronized clock")
    if version < 3 or mode not in (4, 5):
        raise ValueError(f"Invalid SNTP response version/mode: {version}/{mode}")
    if not 1 <= stratum <= 15:
        raise ValueError(f"Invalid SNTP stratum: {stratum}")
    if response[24:32] != request_transmit:
        raise ValueError("SNTP originate timestamp does not match the request")

    server_received = _decode_timestamp(response[32:40])
    server_transmitted = _decode_timestamp(response[40:48])
    if server_received == 0 or server_transmitted == 0:
        raise ValueError("SNTP server returned an empty timestamp")
    offset = (
        (server_received - sent_at) + (server_transmitted - received_at)
    ) / 2.0
    return datetime.fromtimestamp(received_at + offset, timezone.utc)


def _encode_timestamp(unix_timestamp: float) -> bytes:
    ntp_timestamp = unix_timestamp + NTP_EPOCH_DELTA
    seconds = int(ntp_timestamp)
    fraction = int((ntp_timestamp - seconds) * (1 << 32))
    return struct.pack("!II", seconds, fraction)


def _decode_timestamp(value: bytes) -> float:
    seconds, fraction = struct.unpack("!II", value)
    return seconds - NTP_EPOCH_DELTA + fraction / (1 << 32)


class SntpClientWorker:
    def __init__(
        self,
        settings: NtpSettings,
        time_callback: TimeCallback,
        status_callback: StatusCallback,
        query_callback: QueryCallback = query_sntp,
        system_time_callback: SystemTimeCallback = system_utc_now,
    ) -> None:
        self._settings = settings
        self._time_callback = time_callback
        self._status_callback = status_callback
        self._query_callback = query_callback
        self._system_time_callback = system_time_callback
        self._stop = Event()
        self._thread = Thread(target=self._run, name="sntp-client", daemon=True)

    def start(self) -> None:
        if not self._settings.enabled:
            self._status_callback("disabled")
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)

    def _run(self) -> None:
        system_time_applied = False
        while not self._stop.is_set():
            try:
                timestamp = self._query_callback(
                    self._settings.server,
                    self._settings.port,
                    self._settings.timeout_seconds,
                )
            except Exception as exc:
                if not system_time_applied:
                    system_time_applied = self._apply_system_time(
                        f"unavailable: {exc}"
                    )
                else:
                    self._status_callback(
                        f"unavailable: {exc}; system clock already applied; retrying"
                    )
                delay = self._settings.retry_interval_seconds
            else:
                try:
                    command = self._time_callback(timestamp)
                    command.result(timeout=self._settings.apply_timeout_seconds)
                except Exception as exc:
                    self._status_callback(
                        f"network time could not be applied: {exc}; retrying"
                    )
                    delay = self._settings.retry_interval_seconds
                else:
                    self._status_callback(
                        f"synchronized at {timestamp.isoformat()}"
                    )
                    delay = self._settings.sync_interval_seconds
            self._stop.wait(delay)

    def _apply_system_time(self, reason: str) -> bool:
        try:
            timestamp = self._system_time_callback()
            if timestamp.tzinfo is None:
                raise ValueError("system clock must include timezone information")
            command = self._time_callback(timestamp)
            command.result(timeout=self._settings.apply_timeout_seconds)
        except Exception as exc:
            self._status_callback(
                f"{reason}; system clock could not be applied: {exc}; retrying"
            )
            return False
        self._status_callback(
            f"{reason}; PLC updated from system clock at {timestamp.isoformat()}; "
            "retrying NTP"
        )
        return True
