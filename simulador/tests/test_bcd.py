import pytest

from protocol.bcd import decode_bcd, encode_bcd


@pytest.mark.parametrize("value", [0, 1, 9, 10, 42, 99])
def test_bcd_round_trip(value: int) -> None:
    assert decode_bcd(encode_bcd(value)) == value


@pytest.mark.parametrize("value", [-1, 100])
def test_encode_bcd_rejects_out_of_range(value: int) -> None:
    with pytest.raises(ValueError):
        encode_bcd(value)


@pytest.mark.parametrize("value", [0x1A, 0xA1, 0xFF])
def test_decode_bcd_rejects_invalid_nibbles(value: int) -> None:
    with pytest.raises(ValueError):
        decode_bcd(value)

