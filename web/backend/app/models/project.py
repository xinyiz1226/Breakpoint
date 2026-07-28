from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy import Uuid as UuidType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.job import AnalysisJob, ExportJob
    from app.models.user import User
    from app.models.video import VideoAsset


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    owner: Mapped["User"] = relationship(back_populates="projects")
    video_asset: Mapped["VideoAsset | None"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    export_jobs: Mapped[list["ExportJob"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    @property
    def has_video(self) -> bool:
        return self.video_asset is not None
