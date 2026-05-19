import uuid

from pydantic import BaseModel


class SegmentResponse(BaseModel):
    id: uuid.UUID
    index: int
    start: float
    end: float
    start_adjusted: float | None = None
    end_adjusted: float | None = None
    score: float
    features: dict
    included: bool

    model_config = {"from_attributes": True}


class SegmentListResponse(BaseModel):
    segments: list[SegmentResponse]


class SegmentUpdate(BaseModel):
    start_adjusted: float | None = None
    end_adjusted: float | None = None
    included: bool | None = None


class SegmentBatchSelect(BaseModel):
    segment_ids: list[uuid.UUID]
    included: bool
