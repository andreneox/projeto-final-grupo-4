from datetime import datetime, timedelta
import socket
import sqlite3
from threading import Thread
from zoneinfo import ZoneInfo

from domain.models import AndonCategory, AndonEvent
from protocol.tcp_codec import ACK, SIMULATOR_EVENT_TYPE, encode_event
from services.telemetry import TelemetryStore
from tools.reference_receiver import ReceiverDatabase, ReferenceServer


def payload(is_on: bool, second: int) -> bytes:
    return encode_event(
        AndonEvent(
            1,
            AndonCategory.QUALIDADE,
            is_on,
            datetime(2026, 8, 31, 16, 8, second),
        )
    )


def test_reference_receiver_exception_policy(tmp_path) -> None:
    database = ReceiverDatabase(tmp_path / "receiver.db")
    received = datetime(2026, 8, 31, 16, 9, tzinfo=ZoneInfo("America/Manaus"))
    assert database.apply_event(payload(True, 10), received) == "ON"
    assert database.apply_event(payload(True, 20), received) == "ON_REPETIDO"
    assert database.apply_event(payload(False, 30), received) == "OFF"
    assert database.apply_event(payload(False, 40), received) == "OFF_SEM_ABERTURA"
    assert database.apply_event(payload(True, 15), received) == "ATRASADO"


def test_socket_event_does_not_change_opcua_telemetry(tmp_path) -> None:
    database = ReceiverDatabase(tmp_path / "receiver.db")
    telemetry = TelemetryStore()
    received = datetime(2026, 8, 31, 16, 9, tzinfo=ZoneInfo("America/Manaus"))
    before = telemetry.snapshot(10)

    database.apply_event(payload(True, 10), received)

    assert telemetry.snapshot(10) == before


def test_tcp_commit_is_persisted_before_ack(tmp_path) -> None:
    database = ReceiverDatabase(tmp_path / "receiver.db")
    server = ReferenceServer(("127.0.0.1", 0), database, "America/Manaus")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection(server.server_address, timeout=2) as connection:
            connection.sendall(payload(True, 10))
            response = connection.recv(len(ACK))
        assert response == ACK
        with sqlite3.connect(database.path) as connection:
            persisted = connection.execute(
                "SELECT COUNT(*) FROM reception WHERE result = 'ON'"
            ).fetchone()[0]
        assert persisted == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_exact_retransmission_is_acked_without_reapplying_event(tmp_path) -> None:
    database = ReceiverDatabase(tmp_path / "receiver.db")
    received = datetime(2026, 8, 31, 16, 9, tzinfo=ZoneInfo("America/Manaus"))
    event_payload = payload(True, 10)

    assert database.apply_event(event_payload, received) == "ON"
    assert database.apply_event(event_payload, received) == "DUPLICADO"

    with sqlite3.connect(database.path) as connection:
        occurrence_count = connection.execute(
            "SELECT COUNT(*) FROM stop_occurrence"
        ).fetchone()[0]
        duplicate_count = connection.execute(
            "SELECT COUNT(*) FROM reception WHERE result = 'DUPLICADO'"
        ).fetchone()[0]
    assert occurrence_count == 1
    assert duplicate_count == 1


def test_receiver_accepts_both_tcp_formats_and_retains_legacy_shift(tmp_path) -> None:
    database = ReceiverDatabase(tmp_path / "receiver.db")
    received = datetime(2026, 8, 31, 16, 9, tzinfo=database.timezone)
    legacy_on = payload(True, 10)
    simulator_off = encode_event(
        AndonEvent(1, AndonCategory.QUALIDADE, False, received + timedelta(seconds=20)),
        message_type=SIMULATOR_EVENT_TYPE,
    )

    assert database.apply_event(legacy_on, received) == "ON"
    assert database.apply_event(simulator_off, received) == "OFF"
    assert database.apply_event(legacy_on, received) == "DUPLICADO"

    with sqlite3.connect(database.path) as connection:
        rows = connection.execute(
            "SELECT message_type, result FROM reception ORDER BY id"
        ).fetchall()
    assert rows == [(1, "ON"), (2, "OFF"), (1, "DUPLICADO")]
    metrics = database.dashboard_metrics(received + timedelta(minutes=1), "00:00", 1440)
    assert metrics["production_counts"]["line"]["defective"] == 1
    assert metrics["downtime_seconds"]["total"] == 70.0
