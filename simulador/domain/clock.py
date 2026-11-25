from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock
import time
from zoneinfo import ZoneInfo


class LogicalClock:
    """Logical wall clock advanced from a monotonic base."""

    def __init__(self, timezone_name: str) -> None:
        self._timezone = ZoneInfo(timezone_name)
        self._lock = Lock()
        self._base_time = datetime.now(self._timezone)
        self._base_monotonic = time.monotonic()

    def now(self) -> datetime:
        with self._lock:
            elapsed = time.monotonic() - self._base_monotonic
            return self._base_time + timedelta(seconds=elapsed)

    def synchronize(self, timestamp: datetime) -> None:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=self._timezone)
        else:
            timestamp = timestamp.astimezone(self._timezone)
        with self._lock:
            self._base_time = timestamp
            self._base_monotonic = time.monotonic()

