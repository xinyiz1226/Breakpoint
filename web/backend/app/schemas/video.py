from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import VideoAssetStatus, VideoDurationStatus
from app.schemas.job import AnalysisJobRead

ALLOWED_VIDEO_CONTENT_TYPES = frozenset(
    {
        "video/mp4",
        "video/quicktime",
        "video/x-matroska",
        "video/webm",
        "video/x-msvideo",
    }
)


class UploadInitiateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    content_type: str
    size_bytes: int = Field(gt=0)
    duration_seconds: float = Field(
        gt=0,
        description=(
            "Client-declared duration. Validated against the configured "
            "video duration cap and used to provisionally reserve monthly "
            "analysis-seconds quota. Not authoritative — a future worker "
            "re-checks the real duration via ffprobe."
        ),
    )
    part_count: int = Field(ge=1, le=10_000)


class PartUploadUrl(BaseModel):
    part_number: int
    url: str
    content_length_bytes: int = Field(
        description=(
            "The exact byte length this part's presigned URL is signed for "
            "(bound via the S3 Content-Length signing parameter). The "
            "client must upload exactly this many bytes for this part."
        )
    )


class UploadInitiateResponse(BaseModel):
    video_asset_id: uuid.UUID
    object_key: str
    upload_id: str
    part_urls: list[PartUploadUrl]
    expires_in_seconds: int


class CompletedPart(BaseModel):
    part_number: int = Field(ge=1)
    etag: str = Field(min_length=1)


class FinalizeUploadRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    parts: list[CompletedPart] = Field(min_length=1)


class VideoAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: VideoAssetStatus
    original_filename: str
    content_type: str
    declared_size_bytes: int
    actual_size_bytes: int | None
    declared_duration_seconds: float
    duration_seconds: float | None
    duration_status: VideoDurationStatus | None
    retention_expires_at: datetime | None
    created_at: datetime


class FinalizeUploadResponse(BaseModel):
    video_asset: VideoAssetRead
    analysis_job: AnalysisJobRead


class SignedUrlResponse(BaseModel):
    url: str
    expires_in_seconds: int
