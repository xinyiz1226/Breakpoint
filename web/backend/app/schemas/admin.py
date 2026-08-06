from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import JobStatus, UserRole


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    is_verified: bool
    quota_monthly_analysis_seconds_override: int | None
    quota_max_active_analysis_jobs_override: int | None
    quota_storage_bytes_override: int | None
    created_at: datetime


class AdminProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class AdminAnalysisJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    video_asset_id: uuid.UUID
    owner_id: uuid.UUID
    status: JobStatus
    progress: float
    current_step: str | None
    failure_summary: str | None
    failure_detail: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AdminExportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    owner_id: uuid.UUID
    status: JobStatus
    progress: float
    failure_summary: str | None
    failure_detail: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class FailureSummaryRead(BaseModel):
    job_id: uuid.UUID
    job_type: str
    project_id: uuid.UUID
    owner_id: uuid.UUID
    status: JobStatus
    failure_summary: str | None
    failure_detail: str | None
    finished_at: datetime | None
