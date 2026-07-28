"""Regression coverage for the 0007 migration's cleanup-generation backfill.

Upgrading straight to 0007 with ``generation``/``cleanup_generation`` added
as ``NOT NULL DEFAULT 0`` followed immediately by a unique index on
``(video_asset_id, operation, generation)`` corrupts (or fails to migrate)
any pre-existing database that already has legitimate historical duplicate
rows sharing the same ``(video_asset_id, operation)`` -- e.g. a completed
delete-object attempt followed by a later retry row. This test drives the
real Alembic upgrade path against a scratch SQLite database seeded at
revision 0006 to prove the backfill assigns each row in such a group a
distinct generation (rather than colliding), that the owning asset's
``cleanup_generation`` ends up at least the max generation among its tasks,
and that the new unique index is actually enforced afterward.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from app.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_DIR = BACKEND_DIR / "alembic"
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _run_alembic(db_path: Path, revision: str) -> None:
    # alembic/env.py resolves its URL from app.config.get_settings(), which
    # is lru_cache'd, so the override must go through the same env var it
    # reads rather than the Config object alone.
    old_url = os.environ.get("BREAKPOINT_DATABASE_URL")
    os.environ["BREAKPOINT_DATABASE_URL"] = f"sqlite:///{db_path}"
    get_settings.cache_clear()
    try:
        command.upgrade(_alembic_config(db_path), revision)
    finally:
        if old_url is None:
            os.environ.pop("BREAKPOINT_DATABASE_URL", None)
        else:
            os.environ["BREAKPOINT_DATABASE_URL"] = old_url
        get_settings.cache_clear()


@pytest.fixture
def scratch_db_path():
    path = BACKEND_DIR / f"_migration_test_scratch_{uuid.uuid4().hex}.db"
    yield path
    if path.exists():
        path.unlink()


def _seed_duplicate_generation_group(engine: sa.engine.Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed one user/project/video_asset plus two historical cleanup tasks
    sharing (video_asset_id, operation), as would exist on a real 0006
    database predating the generation concept."""

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    task_id_older = uuid.uuid4()
    task_id_newer = uuid.uuid4()
    now = datetime.now(timezone.utc)
    older_created_at = now - timedelta(minutes=10)

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO users (
                    id, created_at, updated_at, email, password_hash, role,
                    is_active, is_verified, quota_monthly_analysis_seconds_override,
                    quota_max_active_analysis_jobs_override, quota_storage_bytes_override
                ) VALUES (
                    :id, :created_at, :updated_at, :email, :password_hash, :role,
                    :is_active, :is_verified, NULL, NULL, NULL
                )
                """
            ),
            {
                "id": str(user_id),
                "created_at": older_created_at,
                "updated_at": older_created_at,
                "email": "owner@example.com",
                "password_hash": "not-a-real-hash",
                "role": "USER",
                "is_active": True,
                "is_verified": True,
            },
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO projects (id, created_at, updated_at, owner_id, name, deleted_at)
                VALUES (:id, :created_at, :updated_at, :owner_id, :name, NULL)
                """
            ),
            {
                "id": str(project_id),
                "created_at": older_created_at,
                "updated_at": older_created_at,
                "owner_id": str(user_id),
                "name": "Migration Regression Project",
            },
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO video_assets (
                    id, created_at, updated_at, project_id, owner_id, object_key,
                    original_filename, content_type, declared_size_bytes,
                    actual_size_bytes, declared_duration_seconds, duration_seconds,
                    duration_status, retention_expires_at, status, upload_id,
                    part_count, upload_expires_at, finalize_idempotency_key,
                    finalize_request_fingerprint, analysis_reserved_seconds,
                    storage_reserved_bytes, storage_counted_bytes
                ) VALUES (
                    :id, :created_at, :updated_at, :project_id, :owner_id, :object_key,
                    :original_filename, :content_type, :declared_size_bytes,
                    NULL, :declared_duration_seconds, NULL,
                    NULL, NULL, :status, :upload_id,
                    :part_count, NULL, NULL,
                    NULL, :analysis_reserved_seconds,
                    :storage_reserved_bytes, :storage_counted_bytes
                )
                """
            ),
            {
                "id": str(asset_id),
                "created_at": older_created_at,
                "updated_at": older_created_at,
                "project_id": str(project_id),
                "owner_id": str(user_id),
                "object_key": "videos/migration-regression.mp4",
                "original_filename": "clip.mp4",
                "content_type": "video/mp4",
                "declared_size_bytes": 1024,
                "declared_duration_seconds": 30.0,
                "status": "UPLOAD_INITIATED",
                "upload_id": "fake-upload-id",
                "part_count": 1,
                "analysis_reserved_seconds": 0.0,
                "storage_reserved_bytes": 0,
                "storage_counted_bytes": 0,
            },
        )

        # Two legitimate historical rows for the *same* (video_asset_id,
        # operation) -- e.g. a completed delete followed by a later retry
        # row created for the same asset/operation before generations
        # existed. created_at ordering (older first) drives the expected
        # deterministic backfilled generation order (0, then 1).
        for task_id, status, created_at in (
            (task_id_older, "COMPLETED", older_created_at),
            (task_id_newer, "PENDING", now),
        ):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO storage_cleanup_tasks (
                        id, created_at, updated_at, project_id, video_asset_id,
                        object_key, upload_id, operation, status, attempts,
                        last_error, claimed_at, completed_at, lease_token, not_before
                    ) VALUES (
                        :id, :created_at, :updated_at, :project_id, :video_asset_id,
                        :object_key, NULL, :operation, :status, 0,
                        NULL, NULL, NULL, NULL, NULL
                    )
                    """
                ),
                {
                    "id": str(task_id),
                    "created_at": created_at,
                    "updated_at": created_at,
                    "project_id": str(project_id),
                    "video_asset_id": str(asset_id),
                    "object_key": "videos/migration-regression.mp4",
                    "operation": "DELETE_OBJECT",
                    "status": status,
                },
            )

    return asset_id, task_id_older, task_id_newer


def test_0007_backfill_assigns_distinct_generations_to_historical_duplicates(scratch_db_path):
    _run_alembic(scratch_db_path, "0006")

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        asset_id, task_id_older, task_id_newer = _seed_duplicate_generation_group(engine)
    finally:
        engine.dispose()

    _run_alembic(scratch_db_path, "0007")

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT id, generation FROM storage_cleanup_tasks WHERE id IN (:older, :newer)"
                ),
                {"older": str(task_id_older), "newer": str(task_id_newer)},
            ).mappings().all()
            generation_by_id = {row["id"]: row["generation"] for row in rows}

            # The two seeded rows for the same (video_asset_id, operation)
            # must not collide on generation 0 -- the older row keeps rank
            # 0, the later one is bumped to a distinct generation.
            assert generation_by_id[str(task_id_older)] == 0
            assert generation_by_id[str(task_id_newer)] == 1

            asset_generation = conn.execute(
                sa.text("SELECT cleanup_generation FROM video_assets WHERE id = :id"),
                {"id": str(asset_id)},
            ).scalar_one()
            assert asset_generation == 1

            # The unique index must exist and actually be enforced.
            index_names = {
                row[1]
                for row in conn.execute(sa.text("PRAGMA index_list('storage_cleanup_tasks')")).fetchall()
            }
            assert "ix_storage_cleanup_tasks_video_asset_id_operation_generation" in index_names

        insert_sql = sa.text(
            """
            INSERT INTO storage_cleanup_tasks (
                id, created_at, updated_at, project_id, video_asset_id,
                object_key, upload_id, operation, status, attempts,
                last_error, claimed_at, completed_at, lease_token,
                not_before, generation
            ) VALUES (
                :id, :created_at, :updated_at, NULL, :video_asset_id,
                :object_key, NULL, :operation, :status, 0,
                NULL, NULL, NULL, NULL, NULL, :generation
            )
            """
        )

        with pytest.raises(IntegrityError):
            with engine.begin() as insert_conn:
                insert_conn.execute(
                    insert_sql,
                    {
                        "id": str(uuid.uuid4()),
                        "created_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                        "video_asset_id": str(asset_id),
                        "object_key": "videos/migration-regression.mp4",
                        "operation": "DELETE_OBJECT",
                        "status": "PENDING",
                        "generation": 0,  # duplicate of task_id_older's (asset, op, gen)
                    },
                )

        # A genuinely new generation for the same asset/operation must
        # still be insertable.
        with engine.begin() as insert_conn:
            insert_conn.execute(
                insert_sql,
                {
                    "id": str(uuid.uuid4()),
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "video_asset_id": str(asset_id),
                    "object_key": "videos/migration-regression.mp4",
                    "operation": "DELETE_OBJECT",
                    "status": "PENDING",
                    "generation": 2,
                },
            )
    finally:
        engine.dispose()
