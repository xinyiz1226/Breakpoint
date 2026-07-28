"""Durable, retryable storage-cleanup outbox.

A ``StorageCleanupTask`` row is the single source of truth that an object
(or an in-progress multipart upload) still needs a storage-side action
performed. Callers persist and commit one of these *before* attempting the
corresponding S3 call, so a crash or a failed delete/abort never leaves an
object silently orphaned: the task simply stays ``pending``/``failed`` until
something (today: the same synchronous best-effort attempt at write time;
later: a retry sweep) claims and completes it.

``project_id``/``video_asset_id`` are plain UUID columns, not foreign keys,
so task history survives tombstoning or eventual hard deletion of the
project/asset rows it describes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Index, Integer, String
from sqlalchemy import Uuid as UuidType
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import StorageCleanupOperation, StorageCleanupStatus

if TYPE_CHECKING:
    pass


class StorageCleanupTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "storage_cleanup_tasks"
    __table_args__ = (
        Index(
            "ix_storage_cleanup_tasks_video_asset_id_operation_generation",
            "video_asset_id",
            "operation",
            "generation",
            unique=True,
        ),
    )

    project_id: Mapped[uuid.UUID | None] = mapped_column(UuidType(as_uuid=True), nullable=True, index=True)
    video_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidType(as_uuid=True), nullable=True, index=True
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    upload_id: Mapped[str | None] = mapped_column(String(512), nullable=True)

    operation: Mapped[StorageCleanupOperation] = mapped_column(
        Enum(StorageCleanupOperation, native_enum=False, validate_strings=True, length=32),
        nullable=False,
    )
    status: Mapped[StorageCleanupStatus] = mapped_column(
        Enum(StorageCleanupStatus, native_enum=False, validate_strings=True, length=16),
        default=StorageCleanupStatus.PENDING,
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Durable lease: minted fresh each time a claim transaction sets this
    # task RUNNING (either the initial synchronous attempt or a later sweep
    # reclaiming a stale RUNNING task). The completion transaction re-locks
    # by id *and* this exact lease token; if a stale claimer's lease has
    # since been superseded by a fresher one, its completion attempt finds
    # no matching row and safely no-ops instead of mutating state or
    # accounting it no longer owns.
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UuidType(as_uuid=True), nullable=True)

    # Only set for tasks that must not be processed before a scheduled time
    # (e.g. the ABORT_MULTIPART task created at upload-initiate time, due
    # at the multipart upload's expiry). NULL means "due immediately".
    not_before: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Idempotency/uniqueness scope, together with (video_asset_id,
    # operation): sourced from VideoAsset.cleanup_generation at the moment
    # this task was created. Ordinary callers (project delete, an
    # integrity-failure abort discovered in the same request that created
    # the object) pass the asset's *current* generation, so a retry keeps
    # reusing the same task. A caller that discovers a storage-side
    # artifact may be newer than any prior cleanup attempt for this asset
    # (finalize detecting a tombstone after its own S3 completion, while an
    # earlier same-generation task may still be RUNNING) instead bumps the
    # asset's generation first, guaranteeing get_or_create_cleanup_task
    # creates a genuinely new successor task rather than reusing a task
    # that may have already run its external side effect against a
    # not-yet-existent object.
    generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
