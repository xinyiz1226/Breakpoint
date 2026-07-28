"""Registration/mailbox password authority contract and cleanup intent
generations.

Adds:
- Drops ``email_tokens.pending_password_hash``: registration no longer
  accepts, hashes, or carries a password at all -- the mailbox owner's
  password is now submitted only at verify-email, alongside the token, and
  assigned directly to ``users.password_hash`` at that point.
- ``storage_cleanup_tasks.generation`` / ``video_assets.cleanup_generation``:
  durable idempotency/uniqueness scope for a video asset's cleanup tasks,
  keyed by ``(video_asset_id, operation, generation)`` rather than merely
  ``(video_asset_id, operation)``. This lets a caller that discovers a
  storage-side artifact may be newer than any prior cleanup attempt (e.g.
  finalize detecting a concurrent project tombstone after its own S3
  completion, while an earlier same-generation cleanup task may still be
  ``RUNNING``) force a genuinely new successor task instead of reusing one
  that may have already run its external side effect against a
  not-yet-existent object.
- A unique index on ``storage_cleanup_tasks (video_asset_id, operation,
  generation)`` so two tasks can never coexist for the same asset,
  operation, and generation (NULL ``video_asset_id`` rows -- tasks with no
  associated asset -- are each treated as distinct by both SQLite and
  Postgres unique-index NULL semantics, so this does not constrain them).

Both new columns are added nullable first and backfilled before the unique
index is created: a pre-existing 0006 database may already have legitimate
historical rows sharing the same ``(video_asset_id, operation)`` (e.g. a
completed delete followed by a later retry row) from before generations
existed. Each row in such a group is assigned a distinct, deterministic
0-based rank ordered by ``created_at`` then ``id``, and each asset's
``cleanup_generation`` is set to at least the max generation among its own
tasks, so collapsing everything to generation 0 never happens and the next
newly-created intent cannot collide with backfilled history.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("email_tokens") as batch_op:
        batch_op.drop_column("pending_password_hash")

    # Both new columns start nullable (no default yet) so the backfill
    # below can distinguish "not yet assigned" from a real generation
    # before the unique index is created. A pre-existing 0006 database may
    # already have legitimate historical rows sharing the same
    # (video_asset_id, operation) -- e.g. a completed delete followed by a
    # later retry row -- created before generations existed. Collapsing
    # all of them to generation=0 would violate the new unique index (or
    # silently misrepresent history); instead each row in such a group is
    # assigned a distinct, deterministic 0-based rank ordered by
    # created_at then id.
    op.add_column("storage_cleanup_tasks", sa.Column("generation", sa.Integer(), nullable=True))
    op.add_column("video_assets", sa.Column("cleanup_generation", sa.Integer(), nullable=True))

    bind = op.get_bind()

    # Rank within each (video_asset_id, operation) group by counting
    # strictly-earlier rows in the same group. This correlated-subquery
    # form (rather than a window function) runs unmodified on both SQLite
    # and Postgres.
    bind.execute(
        sa.text(
            """
            UPDATE storage_cleanup_tasks
            SET generation = (
                SELECT COUNT(*)
                FROM storage_cleanup_tasks AS earlier
                WHERE earlier.video_asset_id = storage_cleanup_tasks.video_asset_id
                  AND earlier.operation = storage_cleanup_tasks.operation
                  AND (
                      earlier.created_at < storage_cleanup_tasks.created_at
                      OR (
                          earlier.created_at = storage_cleanup_tasks.created_at
                          AND earlier.id < storage_cleanup_tasks.id
                      )
                  )
            )
            WHERE video_asset_id IS NOT NULL
            """
        )
    )
    # Tasks with no associated asset are never constrained by the unique
    # index (NULL video_asset_id rows are each distinct under both
    # SQLite's and Postgres's unique-index NULL semantics); generation 0
    # is just a stable default for them.
    bind.execute(
        sa.text("UPDATE storage_cleanup_tasks SET generation = 0 WHERE video_asset_id IS NULL")
    )

    # Each asset's cleanup_generation must be at least the max generation
    # among its own cleanup tasks, so the next newly-created intent
    # increments from there instead of colliding with backfilled history.
    bind.execute(
        sa.text(
            """
            UPDATE video_assets
            SET cleanup_generation = (
                SELECT COALESCE(MAX(t.generation), 0)
                FROM storage_cleanup_tasks AS t
                WHERE t.video_asset_id = video_assets.id
            )
            """
        )
    )

    with op.batch_alter_table("storage_cleanup_tasks") as batch_op:
        batch_op.alter_column("generation", existing_type=sa.Integer(), nullable=False, server_default="0")
    with op.batch_alter_table("video_assets") as batch_op:
        batch_op.alter_column(
            "cleanup_generation", existing_type=sa.Integer(), nullable=False, server_default="0"
        )

    op.create_index(
        op.f("ix_storage_cleanup_tasks_video_asset_id_operation_generation"),
        "storage_cleanup_tasks",
        ["video_asset_id", "operation", "generation"],
        unique=True,
    )

    with op.batch_alter_table("storage_cleanup_tasks") as batch_op:
        batch_op.alter_column("generation", server_default=None)
    with op.batch_alter_table("video_assets") as batch_op:
        batch_op.alter_column("cleanup_generation", server_default=None)


def downgrade() -> None:
    op.drop_index(
        op.f("ix_storage_cleanup_tasks_video_asset_id_operation_generation"),
        table_name="storage_cleanup_tasks",
    )

    op.drop_column("video_assets", "cleanup_generation")
    op.drop_column("storage_cleanup_tasks", "generation")

    with op.batch_alter_table("email_tokens") as batch_op:
        batch_op.add_column(sa.Column("pending_password_hash", sa.String(length=255), nullable=True))
