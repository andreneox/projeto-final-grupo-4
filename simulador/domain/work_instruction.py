from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

INSTRUCTION_NODE = "IT/E07/State"
SEQUENCE_SECONDS = 36
STEP_ENDS = (7, 14, 29, 36)


class WorkInstructionState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    station: Literal[7] = 7
    source: Literal["simulator", "plc"] = "simulator"
    slide: int = Field(default=1, ge=1, le=5)
    status: Literal[
        "waiting", "running", "paused", "interrupted", "complete", "disconnected"
    ] = "waiting"
    cycle_id: str = Field(default="", max_length=100)
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    cycle_time_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    short_cycle: bool = False
    stop_station: int | None = Field(default=None, ge=1, le=12)
    stop_category: str = Field(default="", max_length=80)
    sequence: int = Field(default=0, ge=0)


def cover_state(status="waiting") -> dict:
    return WorkInstructionState(status=status).model_dump()
