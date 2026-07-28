from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, JSON, String
from sqlalchemy import Uuid as UuidType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import JobStatus

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.rally import Rally
    from app.models.video import VideoAsset


class AnalysisJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Asynchronous analysis state machine. Created queued at upload finalize
    time; no worker in this layer ever transitions it further.
    """

    __tablename__ = "analysis_jobs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_asset_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True), ForeignKey("video_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, validate_strings=True, length=16),
        default=JobStatus.QUEUED,
        nullable=False,
        index=True,
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(200), nullable=True)
    worker_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # User-safe summary vs. admin-only diagnostic excerpt (e.g. stderr tail).
    failure_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(String(4000), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="analysis_jobs")
    video_asset: Mapped["VideoAsset"] = relationship(back_populates="analysis_jobs")
    rallies: Mapped[list["Rally"]] = relationship(
        back_populates="analysis_job", cascade="all, delete-orphan"
    )


class ExportJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Asynchronous FFmpeg highlight-compilation state machine. Not executed
    by any worker in this layer.
    """

    __tablename__ = "export_jobs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, validate_strings=True, length=16),
        default=JobStatus.QUEUED,
        nullable=False,
        index=True,
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    output_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(String(4000), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="export_jobs")
