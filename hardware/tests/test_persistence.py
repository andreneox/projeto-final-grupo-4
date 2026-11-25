import sqlite3

import gateway.persistence as persistence_module
from gateway.persistence import GatewayDatabase


ON_PAYLOAD = bytes.fromhex(
    "00 01 00 01 08 26 16 31 10 08 20 01 00 01 00 01"
)
OFF_PAYLOAD = bytes.fromhex(
    "00 01 00 01 08 26 16 31 10 08 20 01 00 01 00 02"
)


def test_capture_is_durable_and_exact_payload_is_deduplicated(tmp_path) -> None:
    path = tmp_path / "gateway.db"
    database = GatewayDatabase(path, "LINHA_A")
    database.start()
    try:
        first = database.capture_event(ON_PAYLOAD)
        duplicate = database.capture_event(ON_PAYLOAD)
    finally:
        database.stop()

    assert first.inserted is True
    assert duplicate.inserted is False
    assert duplicate.event_id == first.event_id
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM gateway_event").fetchone()[0] == 1


def test_crc_uid_collision_never_discards_a_different_payload(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        persistence_module, "make_event_uid", lambda _gateway_id, _payload: "COLLISION"
    )
    database = GatewayDatabase(tmp_path / "gateway.db", "LINHA_A")
    database.start()
    try:
        first = database.capture_event(ON_PAYLOAD)
        second = database.capture_event(OFF_PAYLOAD)
        counts = database.counts()
    finally:
        database.stop()

    assert first.inserted is True
    assert second.inserted is True
    assert second.crc_collision is True
    assert counts == (2, 0)


def test_pending_event_survives_database_restart(tmp_path) -> None:
    path = tmp_path / "gateway.db"
    first_database = GatewayDatabase(path, "LINHA_A")
    first_database.start()
    captured = first_database.capture_event(ON_PAYLOAD)
    first_database.stop()

    second_database = GatewayDatabase(path, "LINHA_A")
    second_database.start()
    try:
        pending = second_database.first_pending()
        assert pending is not None
        assert pending.id == captured.event_id
        assert pending.payload == ON_PAYLOAD
        second_database.mark_plc_acknowledged(captured.event_id)
        second_database.mark_confirmed(captured.event_id)
        assert second_database.counts() == (0, 1)
    finally:
        second_database.stop()
