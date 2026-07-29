"""persist source-expiry cleanup intent

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "video_assets",
        sa.Column("source_expired_at", sa.DateTime(timezone=True), nullable=True),
    )
    migration_time = datetime.now(timezone.utc)
    bind = op.get_bind()

    # A pending/failed delete is safe to resume as retention cleanup only
    # when an active project has an expired source, a completed report, and
    # a matching source-object task. RUNNING tasks are intentionally excluded
    # because the migration cannot know which in-flight caller owns them.
    bind.execute(
        sa.text(
            """
            UPDATE video_assets
            SET source_expired_at = retention_expires_at
            WHERE status = 'CLEANUP_PENDING'
              AND retention_expires_at IS NOT NULL
              AND retention_expires_at <= :migration_time
              AND EXISTS (
                  SELECT 1
                  FROM projects
                  WHERE projects.id = video_assets.project_id
                    AND projects.deleted_at IS NULL
              )
              AND EXISTS (
                  SELECT 1
                  FROM analysis_jobs
                  WHERE analysis_jobs.video_asset_id = video_assets.id
                    AND analysis_jobs.status = 'SUCCEEDED'
                    AND analysis_jobs.report_object_key IS NOT NULL
              )
              AND EXISTS (
                  SELECT 1
                  FROM storage_cleanup_tasks
                  WHERE storage_cleanup_tasks.video_asset_id = video_assets.id
                    AND storage_cleanup_tasks.object_key = video_assets.object_key
                    AND storage_cleanup_tasks.operation = 'DELETE_OBJECT'
                    AND storage_cleanup_tasks.status IN ('PENDING', 'FAILED')
              )
            """
        ),
        {"migration_time": migration_time},
    )

    # Before this column existed, successful source deletion terminated at
    # UPLOAD_ABORTED. Completed matching delete evidence distinguishes those
    # historical retention rows from genuine pre-finalize multipart aborts.
    bind.execute(
        sa.text(
            """
            UPDATE video_assets
            SET source_expired_at = (
                    SELECT MAX(storage_cleanup_tasks.completed_at)
                    FROM storage_cleanup_tasks
                    WHERE storage_cleanup_tasks.video_asset_id = video_assets.id
                      AND storage_cleanup_tasks.object_key = video_assets.object_key
                      AND storage_cleanup_tasks.operation = 'DELETE_OBJECT'
                      AND storage_cleanup_tasks.status = 'COMPLETED'
                ),
                status = 'SOURCE_EXPIRED'
            WHERE status = 'UPLOAD_ABORTED'
              AND retention_expires_at IS NOT NULL
              AND retention_expires_at <= :migration_time
              AND EXISTS (
                  SELECT 1
                  FROM projects
                  WHERE projects.id = video_assets.project_id
                    AND projects.deleted_at IS NULL
              )
              AND EXISTS (
                  SELECT 1
                  FROM analysis_jobs
                  WHERE analysis_jobs.video_asset_id = video_assets.id
                    AND analysis_jobs.status = 'SUCCEEDED'
                    AND analysis_jobs.report_object_key IS NOT NULL
              )
              AND EXISTS (
                  SELECT 1
                  FROM storage_cleanup_tasks
                  WHERE storage_cleanup_tasks.video_asset_id = video_assets.id
                    AND storage_cleanup_tasks.object_key = video_assets.object_key
                    AND storage_cleanup_tasks.operation = 'DELETE_OBJECT'
                    AND storage_cleanup_tasks.status = 'COMPLETED'
                    AND storage_cleanup_tasks.completed_at IS NOT NULL
              )
            """
        ),
        {"migration_time": migration_time},
    )


def downgrade() -> None:
    op.drop_column("video_assets", "source_expired_at")
