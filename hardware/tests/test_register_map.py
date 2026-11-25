from gateway.domain import AndonCategory
from gateway.register_map import REGISTER_COUNT, decode_register_block
import pytest


PAYLOAD = bytes.fromhex(
    "00 01 00 0C 08 26 16 31 10 08 20 01 00 04 00 01"
)


def _registers() -> list[int]:
    registers = [0] * REGISTER_COUNT
    registers[0] = 8
    for index in range(8):
        registers[index + 1] = int.from_bytes(PAYLOAD[index * 2 : index * 2 + 2], "big")
    registers[9] = 0x8421
    registers[10] = 0x1248
    registers[11] = 0x8888
    for station in range(12):
        metric = 13 + station * 4
        registers[metric : metric + 4] = [0, 60_000 + station, 0, 57_500 + station]
    return registers


def test_decodes_event_and_packed_andon_nibbles() -> None:
    snapshot = decode_register_block(
        _registers(),
        event_byte_order="big",
        uint32_word_order="high_low",
        time_scale_to_seconds=0.001,
    )

    assert snapshot.event_payload == PAYLOAD
    assert snapshot.motor_on is False
    assert snapshot.stations[1].states[AndonCategory.QUALIDADE] is True
    assert snapshot.stations[1].states[AndonCategory.EQUIPAMENTO] is False
    assert snapshot.stations[2].states[AndonCategory.EQUIPAMENTO] is True
    assert snapshot.stations[3].states[AndonCategory.PROCESSO] is True
    assert snapshot.stations[4].states[AndonCategory.MATERIAL] is True
    assert snapshot.stations[12].states[AndonCategory.MATERIAL] is True


def test_decodes_uint32_metrics_through_station_twelve() -> None:
    snapshot = decode_register_block(
        _registers(),
        event_byte_order="big",
        uint32_word_order="high_low",
        time_scale_to_seconds=0.001,
    )

    assert snapshot.stations[1].takt_time == 60.0
    assert snapshot.stations[1].last_cycle == 57.5
    assert snapshot.stations[12].takt_time == 60.011
    assert snapshot.stations[12].last_cycle == 57.511


def test_supports_low_word_first_uint32() -> None:
    registers = _registers()
    registers[13:17] = [0x5678, 0x1234, 0xDEF0, 0x9ABC]

    snapshot = decode_register_block(
        registers,
        event_byte_order="big",
        uint32_word_order="low_high",
        time_scale_to_seconds=1.0,
    )

    assert snapshot.stations[1].takt_time == 0x12345678
    assert snapshot.stations[1].last_cycle == 0x9ABCDEF0


def test_accepts_queued_event_word_counts_and_rejects_partial_events() -> None:
    registers = _registers()
    registers[0] = 32

    snapshot = decode_register_block(
        registers,
        event_byte_order="big",
        uint32_word_order="high_low",
        time_scale_to_seconds=1.0,
    )
    assert snapshot.event_size == 32
    assert snapshot.event_payload == PAYLOAD

    registers[0] = 7
    with pytest.raises(ValueError, match="multiple of 8"):
        decode_register_block(
            registers,
            event_byte_order="big",
            uint32_word_order="high_low",
            time_scale_to_seconds=1.0,
        )


def test_decodes_and_validates_d112_motor_command() -> None:
    registers = _registers()
    registers[12] = 1

    snapshot = decode_register_block(
        registers,
        event_byte_order="big",
        uint32_word_order="high_low",
        time_scale_to_seconds=1.0,
    )
    assert snapshot.motor_on is True

    registers[12] = 2
    with pytest.raises(ValueError, match="D112 motor command must be 0 or 1"):
        decode_register_block(
            registers,
            event_byte_order="big",
            uint32_word_order="high_low",
            time_scale_to_seconds=1.0,
        )
