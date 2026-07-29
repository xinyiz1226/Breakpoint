"""Layer 2 media-processing job state.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("video_assets", sa.Column("preview_object_key", sa.String(512), nullable=True))
    op.add_column(
        "analysis_jobs",
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("analysis_jobs", sa.Column("accounting_month", sa.Date(), nullable=True))
    op.execute(
        """
        UPDATE analysis_jobs
        SET accounting_month = (
            SELECT analysis_reservation_month
            FROM video_assets
            WHERE video_assets.id = analysis_jobs.video_asset_id
        )
        """
    )
    op.execute(
        """
        UPDATE analysis_jobs
        SET accounting_month = (
            SELECT MIN(quota_ledger_entries.accounting_month)
            FROM quota_ledger_entries
            WHERE quota_ledger_entries.video_asset_id = analysis_jobs.video_asset_id
              AND quota_ledger_entries.event_type = 'ANALYSIS_RESERVED'
        )
        WHERE accounting_month IS NULL
        """
    )
    op.add_column(
        "analysis_jobs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("analysis_jobs", sa.Column("lease_token", sa.Uuid(), nullable=True))
    op.add_column("analysis_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_analysis_jobs_heartbeat_at"), "analysis_jobs", ["heartbeat_at"])
    op.add_column("export_jobs", sa.Column("current_step", sa.String(200), nullable=True))
    op.add_column(
        "export_jobs",
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "export_jobs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("export_jobs", sa.Column("lease_token", sa.Uuid(), nullable=True))
    op.add_column("export_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_export_jobs_heartbeat_at"), "export_jobs", ["heartbeat_at"])
    op.add_column(
        "export_jobs",
        sa.Column("selection_snapshot", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column("export_jobs", sa.Column("output_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        op.f("ix_export_jobs_output_expires_at"),
        "export_jobs",
        ["output_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_export_jobs_output_expires_at"), table_name="export_jobs")
    op.drop_index(op.f("ix_export_jobs_heartbeat_at"), table_name="export_jobs")
    op.drop_column("export_jobs", "output_expires_at")
    op.drop_column("export_jobs", "selection_snapshot")
    op.drop_column("export_jobs", "cancel_requested_at")
    op.drop_column("export_jobs", "heartbeat_at")
    op.drop_column("export_jobs", "lease_token")
    op.drop_column("export_jobs", "event_version")
    op.drop_column("export_jobs", "current_step")
    op.drop_column("analysis_jobs", "cancel_requested_at")
    op.drop_index(op.f("ix_analysis_jobs_heartbeat_at"), table_name="analysis_jobs")
    op.drop_column("analysis_jobs", "heartbeat_at")
    op.drop_column("analysis_jobs", "lease_token")
    op.drop_column("analysis_jobs", "accounting_month")
    op.drop_column("analysis_jobs", "event_version")
    op.drop_column("video_assets", "preview_object_key")
