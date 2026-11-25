from __future__ import annotations

from typing import Annotated, Literal, Union
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from domain.production_plan import ProductionPlan


class RuntimeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: AwareDatetime


class AndonRuntime(RuntimeBase):
    kind: Literal["andon"] = "andon"
    station: Annotated[int, Field(strict=True, ge=1, le=12)]
    button_id: Annotated[int, Field(strict=True, ge=1, le=4)]
    is_on: Annotated[bool, Field(strict=True)]


class CycleRuntime(RuntimeBase):
    kind: Literal["cycle"] = "cycle"
    run_id: UUID
    station: Annotated[int, Field(strict=True, ge=1, le=12)]
    recipe_step: Annotated[int, Field(strict=True, ge=1)]
    started_at: AwareDatetime
    takt_time_seconds: Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
    cycle_time_seconds: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
    source_name: str = Field(max_length=255)

    @model_validator(mode="after")
    def ordered_times(self) -> "CycleRuntime":
        if (
            self.occurred_at - self.started_at
        ).total_seconds() + 0.001 < self.cycle_time_seconds:
            raise ValueError("O ciclo não pode ser concluído antes da sua duração.")
        return self


class ResetRuntime(RuntimeBase):
    kind: Literal["reset_day"] = "reset_day"
    production_plan: ProductionPlan | None = None


class PlanRuntime(RuntimeBase):
    kind: Literal["production_plan"] = "production_plan"
    production_plan: ProductionPlan


class SessionRuntime(RuntimeBase):
    kind: Literal["session_start"] = "session_start"
    run_id: UUID
    production_plan: ProductionPlan
    source_name: str = Field(max_length=255)


RuntimeEvent = Annotated[
    Union[AndonRuntime, CycleRuntime, ResetRuntime, PlanRuntime, SessionRuntime],
    Field(discriminator="kind"),
]
