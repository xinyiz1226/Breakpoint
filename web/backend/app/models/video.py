from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, DateTime, Enum, Float, ForeignKey, Integer, String
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
    source_expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    preview_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[VideoAssetStatus] = mapped_column(
        Enum(VideoAssetStatus, native_enum=False, validate_strings=True, length=32),
        default=VideoAssetStatus.UPLOAD_INITIATED,
        nullable=False,
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # S3-compatible multipart upload bookkeeping.
    upload_id: Mapped[str] = mapped_column(String(512), nullable=False)
    part_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # When a not-yet-finalized multipart upload's presigned part URLs
    # expire (Settings.multipart_upload_ttl_hours after initiate). A
    # durable ABORT_MULTIPART StorageCleanupTask with a matching
    # ``not_before`` is created in the same transaction as this asset, so
    # an abandoned upload is eventually aborted and its reservations
    # released even if the client never returns. NULL once the upload
    # reaches a terminal state (finalize claim cancels the scheduled task).
    upload_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Finalize idempotency. Populated on the first successful finalize call;
    # replay with the same key + payload fingerprint returns the same result,
    # replay with a different payload under the same key is rejected (409).
    finalize_idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    finalize_request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Durable reservation/accounting fields. These -- not ledger history --
    # are authoritative for whether there is anything left to release, so
    # release helpers are idempotent even if called more than once (e.g. a
    # finalize failure followed by a later project tombstone).
    analysis_reserved_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    storage_reserved_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    storage_counted_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Which accounting month (first UTC day) each *live* reservation above
    # belongs to. Set when a reservation is created/resized, cleared to
    # NULL when it is released. Release/resize always target this original
    # period -- not whatever wall-clock month the release/resize happens to
    # run in -- so a reservation made in one calendar month and released
    # (or grown/shrunk by the worker) after rollover to the next month
    # never nets against, or is judged by, the wrong month's usage. See
    # app.services.quota/app.services.reservations.
    analysis_reservation_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    storage_reservation_month: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Monotonic source for StorageCleanupTask.generation. Callers that
    # create/reuse a cleanup task for this asset via
    # get_or_create_cleanup_task normally pass this value unchanged, so
    # retries reuse the same task. A caller that discovers a storage-side
    # artifact may be newer than any prior cleanup attempt (finalize
    # detecting a concurrent tombstone after its own S3 completion)
    # increments this under lock first, forcing a genuinely new successor
    # task rather than reusing one that may already be RUNNING/COMPLETED
    # against a now-stale view of the object.
    cleanup_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="video_asset")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        back_populates="video_asset", cascade="all, delete-orphan"
    )
