from __future__ import annotations


def encode_bcd(value: int) -> int:
    if not 0 <= value <= 99:
        raise ValueError(f"BCD value out of range: {value}")
    return ((value // 10) << 4) | (value % 10)


def decode_bcd(value: int) -> int:
    high, low = value >> 4, value & 0x0F
    if high > 9 or low > 9:
        raise ValueError(f"Invalid BCD byte: 0x{value:02X}")
    return high * 10 + low

