import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    name: str
    video_filename: str


class ProjectCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    upload_url: str
    video_key: str

    model_config = {"from_attributes": True}


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    video_filename: str
    status: ProjectStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
