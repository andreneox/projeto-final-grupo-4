from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime, timezone
import socket
from threading import Event
from threading import Thread
import time

import pytest

from gateway.config import NtpSettings
from gateway.ntp_client import (
    SntpClientWorker,
    _encode_timestamp,
    decode_sntp_response,
    query_sntp,
)


def settings(**overrides) -> NtpSettings:
    values = {
        "enabled": True,
        "server": "time.internal",
        "port": 123,
        "timeout_seconds": 0.2,
        "retry_interval_seconds": 0.01,
        "sync_interval_seconds": 3600.0,
        "apply_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return NtpSettings(**values)


def test_decodes_valid_sntp_response_using_four_timestamp_offset() -> None:
    sent_at = 1_700_000_000.0
    received_at = sent_at + 0.02
    request_transmit = _encode_timestamp(sent_at)
    response = bytearray(48)
    response[0] = 0x24  # NTPv4 server response.
    response[1] = 2
    response[24:32] = request_transmit
    response[32:40] = _encode_timestamp(sent_at + 0.10)
    response[40:48] = _encode_timestamp(sent_at + 0.11)

    synchronized = decode_sntp_response(
        bytes(response), request_transmit, sent_at, received_at
    )

    assert synchronized.timestamp() == pytest.approx(sent_at + 0.115, abs=0.001)
    assert synchronized.tzinfo is timezone.utc


def test_rejects_unsynchronized_or_unmatched_sntp_response() -> None:
    request_transmit = _encode_timestamp(1_700_000_000.0)
    response = bytearray(48)
    response[0] = 0xE4  # Leap indicator 3: server clock unsynchronized.
    response[1] = 2

    with pytest.raises(ValueError, match="unsynchronized"):
        decode_sntp_response(bytes(response), request_transmit, 0.0, 0.1)


def test_worker_retries_then_applies_network_time() -> None:
    attempts = []
    applied = []
    synchronized = Event()
    fallback = datetime(2026, 9, 27, 19, 29, tzinfo=timezone.utc)
    timestamp = datetime(2026, 9, 27, 19, 30, tzinfo=timezone.utc)

    def query(server: str, port: int, timeout: float) -> datetime:
        attempts.append((server, port, timeout))
        if len(attempts) == 1:
            raise TimeoutError("offline")
        return timestamp

    def apply(value: datetime) -> Future[None]:
        applied.append(value)
        future: Future[None] = Future()
        future.set_result(None)
        return future

    def status_changed(status: str) -> None:
        if status.startswith("synchronized"):
            synchronized.set()

    worker = SntpClientWorker(
        settings(), apply, status_changed, query, lambda: fallback
    )
    worker.start()
    try:
        assert synchronized.wait(2)
    finally:
        worker.stop()

    assert len(attempts) == 2
    assert applied == [fallback, timestamp]


def test_worker_applies_system_time_only_once_while_ntp_is_unavailable() -> None:
    attempts = []
    applied = []
    fallback_applied = Event()
    fallback = datetime(2026, 9, 27, 19, 29, tzinfo=timezone.utc)

    def query(_server: str, _port: int, _timeout: float) -> datetime:
        attempts.append(1)
        raise TimeoutError("offline")

    def apply(value: datetime) -> Future[None]:
        applied.append(value)
        future: Future[None] = Future()
        future.set_result(None)
        fallback_applied.set()
        return future

    worker = SntpClientWorker(
        settings(), apply, lambda _status: None, query, lambda: fallback
    )
    worker.start()
    try:
        assert fallback_applied.wait(1)
        deadline = time.monotonic() + 1
        while len(attempts) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        worker.stop()

    assert len(attempts) >= 3
    assert applied == [fallback]


def test_queries_an_sntp_server_over_udp() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        port = int(server.getsockname()[1])

        def respond() -> None:
            request, address = server.recvfrom(512)
            now = time.time()
            response = bytearray(48)
            response[0] = 0x24
            response[1] = 2
            response[24:32] = request[40:48]
            response[32:40] = _encode_timestamp(now)
            response[40:48] = _encode_timestamp(now)
            server.sendto(response, address)

        thread = Thread(target=respond)
        thread.start()
        synchronized = query_sntp("127.0.0.1", port, 1.0)
        thread.join(timeout=1)

    assert not thread.is_alive()
    assert abs(synchronized.timestamp() - time.time()) < 1.0
