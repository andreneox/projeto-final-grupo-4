from __future__ import annotations

import socket
from threading import Event, Thread
import time
from typing import Callable

from config.settings import TcpSettings
from domain.clock import LogicalClock
from persistence.outbox import Outbox
from protocol.tcp_codec import ACK, TIME_REQUEST, decode_time_response

StatusCallback = Callable[[str], None]
CountsCallback = Callable[[int, int], None]


def _receive_exact(connection: socket.socket, size: int, timeout: float) -> bytes:
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
        outbox: Outbox,
        status_callback: StatusCallback,
        counts_callback: CountsCallback,
    ) -> None:
        self._settings = settings
        self._outbox = outbox
        self._status_callback = status_callback
        self._counts_callback = counts_callback
        self._stop = Event()
        self._wake = Event()
        self._thread = Thread(target=self._run, name="tcp-sender", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=10)

    def wake(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        self._publish_counts()
        while not self._stop.is_set():
            try:
                event = self._outbox.first_pending()
            except Exception as exc:
                self._status_callback(f"Erro ao consultar fila: {exc}")
                self._stop.wait(2)
                continue
            if event is None:
                self._status_callback("TCP aguardando eventos")
                self._wake.wait()
                self._wake.clear()
                continue
            try:
                self._send_event(event.payload)
                self._outbox.mark_confirmed(event.id)
                self._status_callback(f"Evento {event.id} confirmado")
                self._publish_counts()
            except Exception as exc:
                try:
                    self._outbox.record_failure(event.id, str(exc))
                except Exception as database_exc:
                    self._status_callback(f"Erro ao registrar falha TCP: {database_exc}")
                    self._stop.wait(2)
                    continue
                attempt = event.attempts + 1
                delay = self.RETRY_DELAYS[min(attempt - 1, len(self.RETRY_DELAYS) - 1)]
                self._status_callback(
                    f"TCP indisponivel; evento {event.id} sera reenviado em {delay:g}s"
                )
                self._publish_counts()
                self._stop.wait(delay)

    def _send_event(self, payload: bytes) -> None:
        with socket.create_connection(
            (self._settings.host, self._settings.port),
            timeout=self._settings.connect_timeout_seconds,
        ) as connection:
            connection.settimeout(self._settings.send_timeout_seconds)
            connection.sendall(payload)
            response = _receive_exact(
                connection, len(ACK), self._settings.response_timeout_seconds
            )
        if response != ACK:
            raise ValueError(f"ACK invalido: {response!r}")

    def _publish_counts(self) -> None:
        try:
            self._counts_callback(*self._outbox.counts())
        except Exception as exc:
            self._status_callback(f"Erro ao contar fila: {exc}")


class TcpTimeSynchronizer:
    """Runs clock synchronization outside the event FIFO."""

    def __init__(self, settings: TcpSettings, clock: LogicalClock) -> None:
        self._settings = settings
        self._clock = clock

    def synchronize(self) -> None:
        with socket.create_connection(
            (self._settings.host, self._settings.port),
            timeout=self._settings.connect_timeout_seconds,
        ) as connection:
            connection.settimeout(self._settings.send_timeout_seconds)
            connection.sendall(TIME_REQUEST)
            payload = _receive_exact(
                connection, 8, self._settings.response_timeout_seconds
            )
        self._clock.synchronize(decode_time_response(payload))

