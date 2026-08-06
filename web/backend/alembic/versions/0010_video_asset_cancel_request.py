"""Persist video upload cancellation intent.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_assets",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("video_assets", "cancel_requested_at")
