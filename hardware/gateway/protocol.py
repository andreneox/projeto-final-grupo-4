from __future__ import annotations

from datetime import datetime
import struct
import zlib

from gateway.domain import AndonCategory, AndonEvent


EVENT_SIZE = 16
EVENT_TYPE = 1
ACK = b"0" * 20 + b"15"


def decode_bcd(value: int) -> int:
    high, low = value >> 4, value & 0x0F
    if high > 9 or low > 9:
        raise ValueError(f"Invalid BCD byte: 0x{value:02X}")
    return high * 10 + low


def decode_event(payload: bytes) -> AndonEvent:
    if len(payload) != EVENT_SIZE:
        raise ValueError("Andon event must contain exactly 16 bytes")
    message_type, station = struct.unpack(">HH", payload[:4])
    if message_type != EVENT_TYPE:
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


def crc32(payload: bytes) -> int:
    if len(payload) != EVENT_SIZE:
        raise ValueError("CRC32 requires the complete 16-byte event")
    return zlib.crc32(payload) & 0xFFFFFFFF


def make_event_uid(gateway_id: str, payload: bytes) -> str:
    event = decode_event(payload)
    timestamp = event.occurred_at.strftime("%Y%m%d%H%M%S")
    return f"{gateway_id}-{timestamp}-{crc32(payload):08X}"
