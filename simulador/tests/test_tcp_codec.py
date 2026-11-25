from datetime import datetime

import pytest

from domain.models import AndonCategory, AndonEvent
from protocol.tcp_codec import (
    ACK,
    TIME_REQUEST,
    decode_event,
    decode_time_response,
    encode_event,
    encode_time_response,
)


def test_documented_on_example() -> None:
    event = AndonEvent(
        1,
        AndonCategory.QUALIDADE,
        True,
        datetime(2026, 8, 31, 16, 8, 10),
    )
    assert encode_event(event).hex(" ").upper() == (
        "00 01 00 01 08 26 16 31 10 08 20 01 00 01 00 01"
    )


def test_documented_off_example() -> None:
    event = AndonEvent(
        1,
        AndonCategory.QUALIDADE,
        False,
        datetime(2026, 8, 31, 16, 8, 40),
    )
    assert encode_event(event).hex(" ").upper() == (
        "00 01 00 01 08 26 16 31 40 08 20 01 00 01 00 02"
    )


def test_station_twelve_is_binary_integer() -> None:
    payload = encode_event(
        AndonEvent(12, AndonCategory.MATERIAL, True, datetime(2026, 8, 31))
    )
    assert payload[2:4] == b"\x00\x0c"
    assert decode_event(payload).station == 12


def test_decoder_rejects_inconsistent_weekday() -> None:
    payload = bytearray(
        encode_event(
            AndonEvent(1, AndonCategory.PROCESSO, True, datetime(2026, 8, 31))
        )
    )
    payload[11] = 2
    with pytest.raises(ValueError, match="Weekday mismatch"):
        decode_event(bytes(payload))


def test_time_request_and_response() -> None:
    timestamp = datetime(2026, 8, 31, 16, 8, 10)
    assert TIME_REQUEST == b"\x00\x01" + bytes(14)
    assert decode_time_response(encode_time_response(timestamp)) == timestamp
    assert ACK == b"0" * 20 + b"15"
