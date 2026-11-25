from datetime import datetime
from zoneinfo import ZoneInfo

from gateway.plc_clock import encode_plc_clock


def test_encodes_ls_datewr_words_in_bcd() -> None:
    timestamp = datetime(2026, 9, 27, 14, 5, 8, tzinfo=ZoneInfo("America/Manaus"))

    assert encode_plc_clock(timestamp) == [
        0x0926,  # D1000: month 09, year 26
        0x1427,  # D1001: hour 14, date 27
        0x0805,  # D1002: second 08, minute 05
        0x2000,  # D1003: century 20, Sunday 0
    ]


def test_encodes_monday_as_weekday_one() -> None:
    timestamp = datetime(2026, 9, 28, 0, 0, 0)

    assert encode_plc_clock(timestamp)[3] == 0x2001
