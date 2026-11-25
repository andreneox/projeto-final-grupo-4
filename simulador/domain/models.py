from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AndonCategory(Enum):
    QUALIDADE = ("Qualidade", 1, "#FFD600")
    EQUIPAMENTO = ("Equipamento", 2, "#5B9BD5")
    PROCESSO = ("Processo", 3, "#70AD47")
    MATERIAL = ("Material", 4, "#FF0000")

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def button_id(self) -> int:
        return self.value[1]

    @property
    def color(self) -> str:
        return self.value[2]

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
class OutboxEvent:
    id: int
    payload: bytes
    attempts: int


@dataclass(frozen=True)
class StationSnapshot:
    station: int
    states: dict[AndonCategory, bool]
    takt_time: float
    last_cycle: float

