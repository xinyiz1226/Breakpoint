from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy import Uuid as UuidType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import VideoAssetStatus, VideoDurationStatus

if TYPE_CHECKING:
    from app.models.job import AnalysisJob
    from app.models.project import Project


class VideoAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A project's single source video, from multipart initiation through
    finalization.

    ``declared_duration_seconds`` is the client's declaration at upload
    initiate time. The API validates it against
    ``Settings.max_video_duration_seconds`` and uses it to provisionally
    reserve monthly analysis-seconds quota (see
    ``QuotaLedgerEventType.ANALYSIS_RESERVED``) before the real duration is
    known. It is never authoritative for analysis.

    ``duration_seconds``/``duration_status`` are the authoritative pair,
    filled in later by a worker (not implemented in this layer) that
    ffprobes the finalized object; this layer never derives them from
    client input. The worker's first step must ffprobe the asset and, if
    the authoritative duration exceeds ``max_video_duration_seconds``, fail
    validation (mark the job ``FAILED``, set ``duration_status=EXCEEDED``)
    and release the reservation instead of running analysis.
    """

    __tablename__ = "video_assets"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # enforces one video per project at the database level
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    object_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    declared_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Client-declared duration at initiate time, validated against
    # max_video_duration_seconds and used to reserve quota. Provisional,
    # not authoritative — see the class docstring.
    declared_duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)

    # Both fields below are worker-authoritative and remain NULL until a
    # future worker probes the uploaded file. This layer never sets them
    # from client input. See VideoDurationStatus for the contract the
    # worker must follow before running analysis.
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_status: Mapped[VideoDurationStatus | None] = mapped_column(
        Enum(VideoDurationStatus, native_enum=False, validate_strings=True, length=32),
        nullable=True,
    )
    retention_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    status: Mapped[VideoAssetStatus] = mapped_column(
        Enum(VideoAssetStatus, native_enum=False, validate_strings=True, length=32),
        default=VideoAssetStatus.UPLOAD_INITIATED,
        nullable=False,
    )

    # S3-compatible multipart upload bookkeeping.
    upload_id: Mapped[str] = mapped_column(String(512), nullable=False)
    part_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Finalize idempotency. Populated on the first successful finalize call;
    # replay with the same key + payload fingerprint returns the same result,
    # replay with a different payload under the same key is rejected (409).
    finalize_idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    finalize_request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="video_asset")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        back_populates="video_asset", cascade="all, delete-orphan"
    )
