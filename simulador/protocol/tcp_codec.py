from __future__ import annotations

from datetime import datetime
import struct

from domain.models import AndonCategory, AndonEvent
from protocol.bcd import decode_bcd, encode_bcd

EVENT_TYPE = 1
SIMULATOR_EVENT_TYPE = 2
TIME_REQUEST_TYPE = 1
ACK = b"0" * 20 + b"15"
TIME_REQUEST = struct.pack(">H", TIME_REQUEST_TYPE) + bytes(14)


def encode_event(event: AndonEvent, *, message_type: int = EVENT_TYPE) -> bytes:
    if not 1 <= event.station <= 12:
        raise ValueError("Station must be between 1 and 12")
    timestamp = event.occurred_at
    weekday = (timestamp.weekday() + 1) % 7
    year = timestamp.year
    return b"".join(
        (
            struct.pack(">H", message_type),
            struct.pack(">H", event.station),
            bytes(
                (
                    encode_bcd(timestamp.month),
                    encode_bcd(year % 100),
                    encode_bcd(timestamp.hour),
                    encode_bcd(timestamp.day),
                    encode_bcd(timestamp.second),
                    encode_bcd(timestamp.minute),
                    encode_bcd(year // 100),
                    encode_bcd(weekday),
                )
            ),
            struct.pack(">H", event.category.button_id),
            struct.pack(">H", 1 if event.is_on else 2),
        )
    )


def decode_event(payload: bytes) -> AndonEvent:
    if len(payload) != 16:
        raise ValueError("Andon event must contain exactly 16 bytes")
    message_type, station = struct.unpack(">HH", payload[:4])
    if message_type not in (EVENT_TYPE, SIMULATOR_EVENT_TYPE):
        raise ValueError(f"Unexpected message type: {message_type}")
    if not 1 <= station <= 12:
        raise ValueError(f"Invalid station: {station}")
    month, year_end, hour, day, second, minute, year_start, weekday = (
        decode_bcd(value) for value in payload[4:12]
    )
    occurred_at = datetime(
        year_start * 100 + year_end, month, day, hour, minute, second
    )
    expected_weekday = (occurred_at.weekday() + 1) % 7
    if weekday != expected_weekday:
        raise ValueError(
            f"Weekday mismatch: received {weekday}, expected {expected_weekday}"
        )
    button_id, status = struct.unpack(">HH", payload[12:16])
    if status not in (1, 2):
        raise ValueError(f"Invalid status: {status}")
    return AndonEvent(
        station=station,
        category=AndonCategory.from_button_id(button_id),
        is_on=status == 1,
        occurred_at=occurred_at,
    )


def encode_time_response(timestamp: datetime) -> bytes:
    weekday = (timestamp.weekday() + 1) % 7
    return bytes(
        (
            encode_bcd(timestamp.month),
            encode_bcd(timestamp.year % 100),
            encode_bcd(timestamp.hour),
            encode_bcd(timestamp.day),
            encode_bcd(timestamp.second),
            encode_bcd(timestamp.minute),
            encode_bcd(timestamp.year // 100),
            encode_bcd(weekday),
        )
    )


def decode_time_response(payload: bytes) -> datetime:
    if len(payload) != 8:
        raise ValueError("Time response must contain exactly 8 bytes")
    month, year_end, hour, day, second, minute, year_start, weekday = (
        decode_bcd(value) for value in payload
    )
    timestamp = datetime(year_start * 100 + year_end, month, day, hour, minute, second)
    expected_weekday = (timestamp.weekday() + 1) % 7
    if weekday != expected_weekday:
        raise ValueError(
            f"Weekday mismatch: received {weekday}, expected {expected_weekday}"
        )
    return timestamp
