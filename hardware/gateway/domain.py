from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AndonCategory(Enum):
    QUALIDADE = ("Qualidade", 1)
    EQUIPAMENTO = ("Equipamento", 2)
    PROCESSO = ("Processo", 3)
    MATERIAL = ("Material", 4)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def button_id(self) -> int:
        return self.value[1]

    @classmethod
    def from_button_id(cls, button_id: int) -> "AndonCategory":
        for category in cls:
            if category.button_id == button_id:
                return category
        raise ValueError(f"Unknown button id: {button_id}")


@dataclass(frozen=True)
class AndonEvent:
    station: int
    category: AndonCategory
    is_on: bool
    occurred_at: datetime


@dataclass(frozen=True)
class StationTelemetry:
    states: dict[AndonCategory, bool]
    takt_time: float
    last_cycle: float
    production_count: int | None = None
    process_status: int | None = None


@dataclass(frozen=True)
class PlcSnapshot:
    event_size: int
    event_payload: bytes | None
    motor_on: bool
    stations: dict[int, StationTelemetry]


@dataclass(frozen=True)
class OutboxEvent:
    id: int
    payload: bytes
    attempts: int


@dataclass(frozen=True)
class CaptureResult:
    event_id: int
    inserted: bool
    crc_collision: bool
    delivery_status: str
    plc_acknowledged: bool
