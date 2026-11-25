from __future__ import annotations

from gateway.domain import AndonCategory, PlcSnapshot, StationTelemetry


D100 = 100
D160 = 160
REGISTER_COUNT = D160 - D100 + 1
EVENT_REGISTER_OFFSET = 1
EVENT_REGISTER_COUNT = 8
ANDON_REGISTER_OFFSET = 9
MOTOR_ON_REGISTER_OFFSET = 12
METRIC_REGISTER_OFFSET = 13
STATION_COUNT = 12


def decode_register_block(
    registers: list[int] | tuple[int, ...],
    *,
    event_byte_order: str,
    uint32_word_order: str,
    time_scale_to_seconds: float,
) -> PlcSnapshot:
    if len(registers) != REGISTER_COUNT:
        raise ValueError(
            f"Expected {REGISTER_COUNT} registers (D100-D160), got {len(registers)}"
        )
    if any(not 0 <= value <= 0xFFFF for value in registers):
        raise ValueError("Modbus registers must be unsigned 16-bit values")
    if event_byte_order not in {"big", "little"}:
        raise ValueError("event_byte_order must be 'big' or 'little'")
    if uint32_word_order not in {"high_low", "low_high"}:
        raise ValueError("uint32_word_order must be 'high_low' or 'low_high'")
    if time_scale_to_seconds <= 0:
        raise ValueError("time_scale_to_seconds must be positive")

    event_size = registers[0]
    if event_size < 0 or event_size % EVENT_REGISTER_COUNT != 0:
        raise ValueError(
            f"D100 must be zero or a multiple of 8 pending WORDs, got {event_size}"
        )
    event_payload = None
    if event_size > 0:
        event_words = registers[
            EVENT_REGISTER_OFFSET : EVENT_REGISTER_OFFSET + EVENT_REGISTER_COUNT
        ]
        event_payload = b"".join(
            value.to_bytes(2, event_byte_order) for value in event_words
        )

    motor_value = registers[MOTOR_ON_REGISTER_OFFSET]
    if motor_value not in {0, 1}:
        raise ValueError(f"D112 motor command must be 0 or 1, got {motor_value}")

    stations: dict[int, StationTelemetry] = {}
    for station in range(1, STATION_COUNT + 1):
        zero_based = station - 1
        andon_word = registers[ANDON_REGISTER_OFFSET + zero_based // 4]
        nibble = (andon_word >> ((zero_based % 4) * 4)) & 0x0F
        states = {
            category: bool(nibble & (1 << (category.button_id - 1)))
            for category in AndonCategory
        }
        metric_offset = METRIC_REGISTER_OFFSET + zero_based * 4
        takt_raw = _uint32(
            registers[metric_offset],
            registers[metric_offset + 1],
            uint32_word_order,
        )
        cycle_raw = _uint32(
            registers[metric_offset + 2],
            registers[metric_offset + 3],
            uint32_word_order,
        )
        stations[station] = StationTelemetry(
            states=states,
            takt_time=takt_raw * time_scale_to_seconds,
            last_cycle=cycle_raw * time_scale_to_seconds,
        )
    return PlcSnapshot(event_size, event_payload, bool(motor_value), stations)


def _uint32(first: int, second: int, word_order: str) -> int:
    high, low = (first, second) if word_order == "high_low" else (second, first)
    return (high << 16) | low
