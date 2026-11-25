from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ProductionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    production_target: Annotated[int, Field(strict=True, gt=0)] = 480
    available_time_minutes: Annotated[
        float, Field(strict=True, gt=0, allow_inf_nan=False)
    ] = 480.0


class AndonInterlockError(ValueError):
    """Another Andon must be released before a new one can be activated."""
