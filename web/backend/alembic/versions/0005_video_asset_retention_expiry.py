"""add video asset retention expiry

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_assets",
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_video_assets_retention_expires_at"),
        "video_assets",
        ["retention_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_video_assets_retention_expires_at"), table_name="video_assets")
    op.drop_column("video_assets", "retention_expires_at")
