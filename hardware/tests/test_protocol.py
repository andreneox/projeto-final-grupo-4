from datetime import datetime

from gateway.domain import AndonCategory
from gateway.protocol import ACK, crc32, decode_event, make_event_uid


PAYLOAD = bytes.fromhex(
    "00 01 00 01 08 26 16 31 10 08 20 01 00 01 00 01"
)


def test_decodes_the_existing_sixteen_byte_protocol() -> None:
    event = decode_event(PAYLOAD)

    assert event.station == 1
    assert event.category is AndonCategory.QUALIDADE
    assert event.is_on is True
    assert event.occurred_at == datetime(2026, 8, 31, 16, 8, 10)
    assert ACK == b"0" * 20 + b"15"


def test_event_uid_combines_source_timestamp_and_crc32() -> None:
    checksum = crc32(PAYLOAD)

    assert make_event_uid("LINHA_A", PAYLOAD) == (
        f"LINHA_A-20260831160810-{checksum:08X}"
    )
