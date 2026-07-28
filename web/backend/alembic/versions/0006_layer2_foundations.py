"""Layer 2 foundations: auth password ownership, soft project deletion,
worker-facing reservation accounting, and durable storage cleanup.

Adds:
- ``email_tokens.pending_password_hash``: carries the Argon2 hash of the
  password submitted with a registration/re-registration request; assigned
  to ``users.password_hash`` atomically on successful verification.
- ``projects.deleted_at``: soft-delete tombstone.
- ``users.quota_storage_bytes_override``: per-user storage-byte quota
  override (NULL = configured default; 0 is a valid "no quota" override).
- ``video_assets.analysis_reserved_seconds`` / ``storage_reserved_bytes`` /
  ``storage_counted_bytes``: durable reservation/accounting fields so
  release helpers are idempotent without inferring state from ledger
  history alone.
- ``storage_cleanup_tasks``: durable, retryable outbox for
  delete_object/abort_multipart operations.
- A unique index on ``analysis_jobs.video_asset_id`` so at most one
  analysis job can ever exist per video asset.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "storage_cleanup_tasks",
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("video_asset_id", sa.Uuid(), nullable=True),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("upload_id", sa.String(length=512), nullable=True),
        sa.Column(
            "operation",
            sa.Enum(
                "DELETE_OBJECT", "ABORT_MULTIPART", name="storagecleanupoperation", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "RUNNING", "COMPLETED", "FAILED", name="storagecleanupstatus", native_enum=False, length=16
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_storage_cleanup_tasks_project_id"), "storage_cleanup_tasks", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_storage_cleanup_tasks_status"), "storage_cleanup_tasks", ["status"], unique=False)
    op.create_index(
        op.f("ix_storage_cleanup_tasks_video_asset_id"), "storage_cleanup_tasks", ["video_asset_id"], unique=False
    )

    op.drop_index(op.f("ix_analysis_jobs_video_asset_id"), table_name="analysis_jobs")
    op.create_index(op.f("ix_analysis_jobs_video_asset_id"), "analysis_jobs", ["video_asset_id"], unique=True)

    op.add_column("email_tokens", sa.Column("pending_password_hash", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("quota_storage_bytes_override", sa.BigInteger(), nullable=True))
    # No existing data in this pre-production schema (see 0003), so these
    # NOT NULL columns need no server default.
    op.add_column("video_assets", sa.Column("analysis_reserved_seconds", sa.Float(), nullable=False))
    op.add_column("video_assets", sa.Column("storage_reserved_bytes", sa.BigInteger(), nullable=False))
    op.add_column("video_assets", sa.Column("storage_counted_bytes", sa.BigInteger(), nullable=False))

    with op.batch_alter_table("users") as batch_op:
        batch_op.create_check_constraint(
            "ck_users_quota_storage_bytes_override_non_negative",
            "quota_storage_bytes_override IS NULL OR quota_storage_bytes_override >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_quota_storage_bytes_override_non_negative", type_="check")

    op.drop_column("video_assets", "storage_counted_bytes")
    op.drop_column("video_assets", "storage_reserved_bytes")
    op.drop_column("video_assets", "analysis_reserved_seconds")
    op.drop_column("users", "quota_storage_bytes_override")
    op.drop_column("projects", "deleted_at")
    op.drop_column("email_tokens", "pending_password_hash")

    op.drop_index(op.f("ix_analysis_jobs_video_asset_id"), table_name="analysis_jobs")
    op.create_index(op.f("ix_analysis_jobs_video_asset_id"), "analysis_jobs", ["video_asset_id"], unique=False)

    op.drop_index(op.f("ix_storage_cleanup_tasks_video_asset_id"), table_name="storage_cleanup_tasks")
    op.drop_index(op.f("ix_storage_cleanup_tasks_status"), table_name="storage_cleanup_tasks")
    op.drop_index(op.f("ix_storage_cleanup_tasks_project_id"), table_name="storage_cleanup_tasks")
    op.drop_table("storage_cleanup_tasks")
