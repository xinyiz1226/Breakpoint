from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import VideoAssetStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    has_video: bool = False
    has_analysis: bool = False
    video_asset_status: VideoAssetStatus | None = None
