from __future__ import annotations

from datetime import datetime


def encode_plc_clock(timestamp: datetime) -> list[int]:
    """Encode LS DATEWR source words S through S+3."""
    weekday = (timestamp.weekday() + 1) % 7
    return [
        (_bcd(timestamp.month) << 8) | _bcd(timestamp.year % 100),
        (_bcd(timestamp.hour) << 8) | _bcd(timestamp.day),
        (_bcd(timestamp.second) << 8) | _bcd(timestamp.minute),
        (_bcd(timestamp.year // 100) << 8) | _bcd(weekday),
    ]


def _bcd(value: int) -> int:
    if not 0 <= value <= 99:
        raise ValueError(f"BCD value is outside 0..99: {value}")
    return ((value // 10) << 4) | (value % 10)
