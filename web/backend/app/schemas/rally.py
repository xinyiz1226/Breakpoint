from __future__ import annotations

import uuid
import math

from pydantic import BaseModel, ConfigDict, model_validator


class RallyEditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    included: bool
    adjusted_start: float | None
    adjusted_end: float | None


class RallyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_index: int
    start: float
    end: float
    score: float
    features: dict
    players: dict | None
    report_version: str
    edit: RallyEditRead


class RallyEditUpdate(BaseModel):
    included: bool
    adjusted_start: float | None = None
    adjusted_end: float | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "RallyEditUpdate":
        values = [
            value
            for value in (self.adjusted_start, self.adjusted_end)
            if value is not None
        ]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("adjusted times must be finite")
        if (
            self.adjusted_start is not None
            and self.adjusted_end is not None
            and self.adjusted_end <= self.adjusted_start
        ):
            raise ValueError("adjusted_end must be greater than adjusted_start")
        return self
