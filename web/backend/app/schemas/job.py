from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import JobStatus


class AnalysisJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    video_asset_id: uuid.UUID
    status: JobStatus
    progress: float
    current_step: str | None
    report_object_key: str | None
    failure_summary: str | None
    event_version: int
    cancel_requested_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ExportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: JobStatus
    progress: float
    current_step: str | None
    event_version: int
    cancel_requested_at: datetime | None
    selection_snapshot: list[dict]
    output_object_key: str | None
    output_expires_at: datetime | None
    failure_summary: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
