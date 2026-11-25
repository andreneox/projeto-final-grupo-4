from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
import time

from pydantic import ValidationError

from domain.models import AndonCategory
from domain.work_instruction import INSTRUCTION_NODE, WorkInstructionState, cover_state
from services.plc_work_instruction import PlcWorkInstruction


PRODUCTION_COUNT_NODE = "Linha/TotalProduzido"
PROCESS_STATUS_NODE = "Linha/StatusProcesso"


class TelemetryStore:
    """Latest telemetry from OPC UA and acknowledged, ordered production events."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._connected = False
        self._status = "aguardando conexao"
        self._last_seen: datetime | None = None
        self._instruction_state = None
        self._instruction_received = None
        self._plc_instruction = PlcWorkInstruction()
        self._plc_production_count: int | None = None
        self._stations = {
            str(station): {
                "andon": {category.name.lower(): None for category in AndonCategory},
                "takt_time": None,
                "cycle_time": None,
                "process_status": None,
            }
            for station in range(1, 13)
        }

    def set_connection(self, connected: bool, status: str) -> None:
        with self._lock:
            self._connected = connected
            self._status = status
            if not connected:
                self._instruction_state = None
                self._instruction_received = None
                self._plc_instruction.reset()
            if connected:
                self._last_seen = datetime.now(timezone.utc)

    def reset_day(self) -> None:
        with self._lock:
            self._instruction_state = None
            self._instruction_received = None
            self._plc_instruction.reset()
            for station in self._stations.values():
                station["andon"] = {
                    category.name.lower(): False for category in AndonCategory
                }
                station["takt_time"] = 0.0
                station["cycle_time"] = 0.0
            # Keep the real connection state; a reset does not prove OPC UA connectivity.
            if self._connected:
                self._last_seen = datetime.now(timezone.utc)

    def mark_alive(self) -> None:
        with self._lock:
            if self._connected:
                self._last_seen = datetime.now(timezone.utc)

    def update(self, node_path: str, value: object) -> None:
        if node_path == PROCESS_STATUS_NODE:
            if value is None:
                value = [None] * len(self._stations)
            if isinstance(value, list) and len(value) == len(self._stations):
                with self._lock:
                    for station, status in zip(self._stations.values(), value, strict=True):
                        station["process_status"] = (
                            status if type(status) is int and 0 <= status <= 3 else None
                        )
                    self._plc_instruction.update_status(
                        self._stations["7"]["process_status"],
                        time.monotonic(),
                        connected=self._connected,
                        stopped=self._active_andon() is not None,
                    )
            return
        if node_path == PRODUCTION_COUNT_NODE:
            if value is None or (type(value) is int and 0 <= value <= 0xFFFF):
                with self._lock:
                    self._plc_production_count = value
            return
        if node_path == INSTRUCTION_NODE:
            try:
                state = WorkInstructionState.model_validate_json(value).model_dump()
            except (ValidationError, TypeError, ValueError):
                return
            with self._lock:
                self._instruction_state = state
                self._instruction_received = time.monotonic()
            return
        parts = node_path.split("/")
        if not parts or not parts[0].startswith("P"):
            return
        try:
            station = str(int(parts[0][1:]))
        except ValueError:
            return
        with self._lock:
            target = self._stations.get(station)
            if target is None:
                return
            if len(parts) == 3 and parts[1] == "Andon":
                try:
                    category = next(
                        item for item in AndonCategory if item.label == parts[2]
                    )
                except StopIteration:
                    return
                target["andon"][category.name.lower()] = bool(value)
                if value:
                    self._plc_instruction.interrupt()
            elif len(parts) == 2 and parts[1] == "TaktTime":
                target["takt_time"] = float(value)
            elif len(parts) == 2 and parts[1] == "UltimoCiclo":
                target["cycle_time"] = float(value)
            else:
                return
            self._last_seen = datetime.now(timezone.utc)

    def instruction_snapshot(self, stale_after_seconds: float = 1.5) -> dict:
        with self._lock:
            if not self._connected:
                return cover_state("disconnected")
            now = time.monotonic()
            if self._plc_instruction.process_status is not None:
                state = self._plc_instruction.snapshot(now)
            elif (
                self._instruction_state is not None
                and self._instruction_received is not None
                and now - self._instruction_received <= stale_after_seconds
            ):
                state = dict(self._instruction_state)
            else:
                return cover_state("disconnected")
            stop = self._active_andon()
            if stop is not None:
                station, category = stop
                state.update(slide=1, status="paused", stop_station=station, stop_category=category)
            return state

    def _active_andon(self) -> tuple[int, str] | None:
        for station, values in self._stations.items():
            for category, active in values["andon"].items():
                if active is True:
                    return int(station), category
        return None

    def snapshot(self, stale_after_seconds: float) -> dict:
        with self._lock:
            last_seen = self._last_seen
            age = (
                (datetime.now(timezone.utc) - last_seen).total_seconds()
                if last_seen is not None
                else None
            )
            connected = self._connected and (
                age is not None and age <= stale_after_seconds
            )
            return {
                "connected": connected,
                "status": self._status,
                "last_seen": last_seen.isoformat() if last_seen else None,
                "plc_production_count": self._plc_production_count,
                "stations": deepcopy(self._stations),
            }
