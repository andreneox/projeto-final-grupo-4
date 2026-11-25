from __future__ import annotations

import socket
from threading import Event, Thread
import time
from typing import Callable

from gateway.config import TcpSettings
from gateway.persistence import GatewayDatabase
from gateway.protocol import ACK


StatusCallback = Callable[[str], None]


def receive_exact(connection: socket.socket, size: int, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    chunks = bytearray()
    while len(chunks) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Response timed out after {len(chunks)} of {size} bytes")
        connection.settimeout(remaining)
        chunk = connection.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError(
                f"Peer closed after {len(chunks)} of {size} response bytes"
            )
        chunks.extend(chunk)
    return bytes(chunks)


class TcpSender:
    RETRY_DELAYS = (1.0, 2.0, 5.0, 10.0, 30.0)

    def __init__(
        self,
        settings: TcpSettings,
        database: GatewayDatabase,
        status_callback: StatusCallback,
    ) -> None:
        self._settings = settings
        self._database = database
        self._status_callback = status_callback
        self._stop = Event()
        self._wake = Event()
        self._thread = Thread(target=self._run, name="tcp-sender", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)

    def wake(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._database.first_pending()
            except Exception as exc:
                self._status_callback(f"database query failed: {exc}")
                self._stop.wait(2)
                continue
            if event is None:
                self._status_callback("waiting for events")
                self._wake.wait()
                self._wake.clear()
                continue
            try:
                self.send_event(event.payload)
                self._database.mark_confirmed(event.id)
                self._status_callback(f"event {event.id} confirmed")
            except Exception as exc:
                try:
                    self._database.record_failure(event.id, str(exc))
                except Exception as database_exc:
                    self._status_callback(
                        f"failed to record TCP error: {database_exc}"
                    )
                    self._stop.wait(2)
                    continue
                attempt = event.attempts + 1
                delay = self.RETRY_DELAYS[
                    min(attempt - 1, len(self.RETRY_DELAYS) - 1)
                ]
                self._status_callback(
                    f"server unavailable; event {event.id} retries in {delay:g}s"
                )
                self._stop.wait(delay)

    def send_event(self, payload: bytes) -> None:
        with socket.create_connection(
            (self._settings.host, self._settings.port),
            timeout=self._settings.connect_timeout_seconds,
        ) as connection:
            connection.settimeout(self._settings.send_timeout_seconds)
            connection.sendall(payload)
            response = receive_exact(
                connection, len(ACK), self._settings.response_timeout_seconds
            )
        if response != ACK:
            raise ValueError(f"Invalid ACK: {response!r}")

