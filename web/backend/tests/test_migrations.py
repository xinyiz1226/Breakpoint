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

import importlib.util
import os
import uuid
from datetime import date, datetime, timedelta, timezone
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


def test_0008_postgres_month_backfill_is_explicitly_utc():
    migration_path = ALEMBIC_DIR / "versions" / "0008_quota_accounting_periods.py"
    spec = importlib.util.spec_from_file_location("migration_0008", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    expression = migration._month_start_expression("created_at", "postgresql")
    assert expression == "date_trunc('month', created_at AT TIME ZONE 'UTC')::date"


@pytest.fixture
def scratch_db_path():
    path = BACKEND_DIR / f"_migration_test_scratch_{uuid.uuid4().hex}.db"
    yield path
    if path.exists():
        path.unlink()


def _seed_analysis_lifecycle(
    engine: sa.engine.Engine,
    *,
    live_reserved_seconds: float,
    entries: list[tuple[str, float, datetime, str]],
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    job_id = uuid.uuid4()
    entry_ids: list[uuid.UUID] = []
    created_at = entries[0][2]

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
                "created_at": created_at,
                "updated_at": created_at,
                "email": f"{user_id}@example.com",
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
                "created_at": created_at,
                "updated_at": created_at,
                "owner_id": str(user_id),
                "name": "Quota Lifecycle Migration",
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
                    storage_reserved_bytes, storage_counted_bytes, cleanup_generation
                ) VALUES (
                    :id, :created_at, :updated_at, :project_id, :owner_id, :object_key,
                    :original_filename, :content_type, :declared_size_bytes,
                    NULL, :declared_duration_seconds, NULL,
                    NULL, NULL, :status, :upload_id,
                    :part_count, NULL, NULL,
                    NULL, :analysis_reserved_seconds,
                    0, 0, 0
                )
                """
            ),
            {
                "id": str(asset_id),
                "created_at": created_at,
                "updated_at": entries[-1][2],
                "project_id": str(project_id),
                "owner_id": str(user_id),
                "object_key": f"videos/{asset_id}.mp4",
                "original_filename": "clip.mp4",
                "content_type": "video/mp4",
                "declared_size_bytes": 1024,
                "declared_duration_seconds": entries[0][1],
                "status": "UPLOADED",
                "upload_id": f"upload-{asset_id}",
                "part_count": 1,
                "analysis_reserved_seconds": live_reserved_seconds,
            },
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO analysis_jobs (
                    id, created_at, updated_at, project_id, video_asset_id, owner_id,
                    status, progress, current_step, worker_version, engine_params,
                    report_object_key, failure_summary, failure_detail, started_at, finished_at
                ) VALUES (
                    :id, :created_at, :updated_at, :project_id, :video_asset_id, :owner_id,
                    :status, 0, NULL, NULL, NULL,
                    NULL, NULL, NULL, NULL, NULL
                )
                """
            ),
            {
                "id": str(job_id),
                "created_at": created_at,
                "updated_at": entries[-1][2],
                "project_id": str(project_id),
                "video_asset_id": str(asset_id),
                "owner_id": str(user_id),
                "status": "QUEUED",
            },
        )

        for event_type, seconds_delta, event_created_at, association in entries:
            entry_id = uuid.uuid4()
            entry_ids.append(entry_id)
            conn.execute(
                sa.text(
                    """
                    INSERT INTO quota_ledger_entries (
                        id, user_id, event_type, analysis_job_id, video_asset_id,
                        seconds_delta, bytes_delta, created_at
                    ) VALUES (
                        :id, :user_id, :event_type, :analysis_job_id, :video_asset_id,
                        :seconds_delta, NULL, :created_at
                    )
                    """
                ),
                {
                    "id": str(entry_id),
                    "user_id": str(user_id),
                    "event_type": event_type,
                    "analysis_job_id": str(job_id) if association == "job" else None,
                    "video_asset_id": str(asset_id) if association == "asset" else None,
                    "seconds_delta": seconds_delta,
                    "created_at": event_created_at,
                },
            )

    return asset_id, entry_ids


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


def test_0008_backfill_derives_accounting_month_from_created_at(scratch_db_path):
    """Seed quota_ledger_entries at revision 0007 with created_at values in
    different UTC calendar months (including a leap-day month and a
    year-boundary rollover), upgrade to 0008, and assert accounting_month
    is backfilled to each row's own created_at truncated to the first day
    of its UTC month -- never today's wall-clock month, and never another
    row's month."""
    _run_alembic(scratch_db_path, "0007")

    user_id = uuid.uuid4()
    entry_specs = [
        (uuid.uuid4(), datetime(2025, 1, 15, 3, 30, tzinfo=timezone.utc), date(2025, 1, 1)),
        (uuid.uuid4(), datetime(2025, 2, 1, 0, 0, tzinfo=timezone.utc), date(2025, 2, 1)),
        (uuid.uuid4(), datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc), date(2025, 12, 1)),
        (uuid.uuid4(), datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), date(2026, 1, 1)),
    ]

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
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
                    "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                    "updated_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                    "email": "accounting-month-migration@example.com",
                    "password_hash": "not-a-real-hash",
                    "role": "USER",
                    "is_active": True,
                    "is_verified": True,
                },
            )
            for entry_id, created_at, _expected_month in entry_specs:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO quota_ledger_entries (
                            id, user_id, event_type, analysis_job_id, video_asset_id,
                            seconds_delta, bytes_delta, created_at
                        ) VALUES (
                            :id, :user_id, :event_type, NULL, NULL,
                            :seconds_delta, NULL, :created_at
                        )
                        """
                    ),
                    {
                        "id": str(entry_id),
                        "user_id": str(user_id),
                        "event_type": "ANALYSIS_RESERVED",
                        "seconds_delta": 10.0,
                        "created_at": created_at,
                    },
                )
    finally:
        engine.dispose()

    _run_alembic(scratch_db_path, "0008")

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        with engine.connect() as conn:
            for entry_id, _created_at, expected_month in entry_specs:
                accounting_month = conn.execute(
                    sa.text("SELECT accounting_month FROM quota_ledger_entries WHERE id = :id"),
                    {"id": str(entry_id)},
                ).scalar_one()
                assert accounting_month == expected_month.isoformat(), (
                    f"entry {entry_id} expected {expected_month}, got {accounting_month}"
                )

            # The column must be non-null after backfill.
            null_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM quota_ledger_entries WHERE accounting_month IS NULL")
            ).scalar_one()
            assert null_count == 0

            index_names = {
                row[1]
                for row in conn.execute(sa.text("PRAGMA index_list('quota_ledger_entries')")).fetchall()
            }
            assert "ix_quota_ledger_entries_user_id_accounting_month" in index_names
    finally:
        engine.dispose()


def test_0008_backfills_live_reservation_months_from_original_ledger_entries(scratch_db_path):
    """Live reservations created before 0008 retain their original periods.

    Without this asset-level backfill, releasing or resizing a January
    reservation after deployment in a later month would fall back to that
    later month and create a negative current-month balance.
    """
    _run_alembic(scratch_db_path, "0007")

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    january_created_at = datetime(2025, 1, 15, 3, 30, tzinfo=timezone.utc)
    february_created_at = datetime(2025, 2, 20, 4, 45, tzinfo=timezone.utc)

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
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
                    "created_at": january_created_at,
                    "updated_at": january_created_at,
                    "email": "live-reservation-migration@example.com",
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
                    "created_at": january_created_at,
                    "updated_at": january_created_at,
                    "owner_id": str(user_id),
                    "name": "Live Reservation Migration",
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
                        storage_reserved_bytes, storage_counted_bytes, cleanup_generation
                    ) VALUES (
                        :id, :created_at, :updated_at, :project_id, :owner_id, :object_key,
                        :original_filename, :content_type, :declared_size_bytes,
                        NULL, :declared_duration_seconds, NULL,
                        NULL, NULL, :status, :upload_id,
                        :part_count, NULL, NULL,
                        NULL, :analysis_reserved_seconds,
                        :storage_reserved_bytes, 0, 0
                    )
                    """
                ),
                {
                    "id": str(asset_id),
                    "created_at": january_created_at,
                    "updated_at": february_created_at,
                    "project_id": str(project_id),
                    "owner_id": str(user_id),
                    "object_key": "videos/live-reservation.mp4",
                    "original_filename": "clip.mp4",
                    "content_type": "video/mp4",
                    "declared_size_bytes": 1024,
                    "declared_duration_seconds": 100.0,
                    "status": "UPLOAD_INITIATED",
                    "upload_id": "live-upload-id",
                    "part_count": 1,
                    "analysis_reserved_seconds": 100.0,
                    "storage_reserved_bytes": 1024,
                },
            )
            for event_type, seconds_delta, bytes_delta, created_at in (
                ("ANALYSIS_RESERVED", 100.0, None, january_created_at),
                ("STORAGE_RESERVED", None, 1024, february_created_at),
            ):
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO quota_ledger_entries (
                            id, user_id, event_type, analysis_job_id, video_asset_id,
                            seconds_delta, bytes_delta, created_at
                        ) VALUES (
                            :id, :user_id, :event_type, NULL, :video_asset_id,
                            :seconds_delta, :bytes_delta, :created_at
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": str(user_id),
                        "event_type": event_type,
                        "video_asset_id": str(asset_id),
                        "seconds_delta": seconds_delta,
                        "bytes_delta": bytes_delta,
                        "created_at": created_at,
                    },
                )
    finally:
        engine.dispose()

    _run_alembic(scratch_db_path, "0008")

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    """
                    SELECT analysis_reservation_month, storage_reservation_month
                    FROM video_assets
                    WHERE id = :id
                    """
                ),
                {"id": str(asset_id)},
            ).one()
            assert row.analysis_reservation_month == "2025-01-01"
            assert row.storage_reservation_month == "2025-02-01"
    finally:
        engine.dispose()


def test_0008_backfill_books_cross_month_release_to_original_reservation_period(scratch_db_path):
    _run_alembic(scratch_db_path, "0007")
    january = datetime(2025, 1, 15, tzinfo=timezone.utc)
    february = datetime(2025, 2, 3, tzinfo=timezone.utc)

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        _asset_id, entry_ids = _seed_analysis_lifecycle(
            engine,
            live_reserved_seconds=0.0,
            entries=[
                ("ANALYSIS_RESERVED", 100.0, january, "asset"),
                ("ANALYSIS_RESERVATION_RELEASED", -100.0, february, "asset"),
            ],
        )
    finally:
        engine.dispose()

    _run_alembic(scratch_db_path, "0008")

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    """
                    SELECT accounting_month, seconds_delta
                    FROM quota_ledger_entries
                    WHERE id IN (:reserved_id, :released_id)
                    ORDER BY created_at
                    """
                ),
                {
                    "reserved_id": str(entry_ids[0]),
                    "released_id": str(entry_ids[1]),
                },
            ).all()
            assert rows == [("2025-01-01", 100.0), ("2025-01-01", -100.0)]

            balances = conn.execute(
                sa.text(
                    """
                    SELECT accounting_month, SUM(seconds_delta)
                    FROM quota_ledger_entries
                    GROUP BY accounting_month
                    ORDER BY accounting_month
                    """
                )
            ).all()
            assert balances == [("2025-01-01", 0.0)]
    finally:
        engine.dispose()


def test_0008_backfill_keeps_cross_month_resize_in_original_period(scratch_db_path):
    _run_alembic(scratch_db_path, "0007")
    january = datetime(2025, 1, 15, tzinfo=timezone.utc)
    february = datetime(2025, 2, 3, tzinfo=timezone.utc)

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        asset_id, entry_ids = _seed_analysis_lifecycle(
            engine,
            live_reserved_seconds=150.0,
            entries=[
                ("ANALYSIS_RESERVED", 100.0, january, "asset"),
                ("ANALYSIS_RESERVATION_RELEASED", -100.0, february, "job"),
                ("ANALYSIS_RESERVED", 150.0, february, "job"),
            ],
        )
    finally:
        engine.dispose()

    _run_alembic(scratch_db_path, "0008")

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        with engine.connect() as conn:
            months = conn.execute(
                sa.text(
                    """
                    SELECT accounting_month
                    FROM quota_ledger_entries
                    WHERE id IN (:initial_id, :release_id, :replacement_id)
                    ORDER BY created_at, id
                    """
                ),
                {
                    "initial_id": str(entry_ids[0]),
                    "release_id": str(entry_ids[1]),
                    "replacement_id": str(entry_ids[2]),
                },
            ).scalars().all()
            assert months == ["2025-01-01", "2025-01-01", "2025-01-01"]

            balances = conn.execute(
                sa.text(
                    """
                    SELECT accounting_month, SUM(seconds_delta)
                    FROM quota_ledger_entries
                    GROUP BY accounting_month
                    ORDER BY accounting_month
                    """
                )
            ).all()
            assert balances == [("2025-01-01", 150.0)]

            asset_month = conn.execute(
                sa.text(
                    "SELECT analysis_reservation_month FROM video_assets WHERE id = :id"
                ),
                {"id": str(asset_id)},
            ).scalar_one()
            assert asset_month == "2025-01-01"
    finally:
        engine.dispose()


def test_0008_backfill_normalizes_unassociated_release_without_negative_period(scratch_db_path):
    _run_alembic(scratch_db_path, "0007")
    january = datetime(2025, 1, 15, tzinfo=timezone.utc)
    february = datetime(2025, 2, 3, tzinfo=timezone.utc)

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        _asset_id, entry_ids = _seed_analysis_lifecycle(
            engine,
            live_reserved_seconds=0.0,
            entries=[
                ("ANALYSIS_RESERVED", 100.0, january, "none"),
                ("ANALYSIS_RESERVATION_RELEASED", -100.0, february, "none"),
            ],
        )
    finally:
        engine.dispose()

    _run_alembic(scratch_db_path, "0008")

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    """
                    SELECT accounting_month, seconds_delta
                    FROM quota_ledger_entries
                    WHERE id IN (:reserved_id, :released_id)
                    ORDER BY created_at
                    """
                ),
                {
                    "reserved_id": str(entry_ids[0]),
                    "released_id": str(entry_ids[1]),
                },
            ).all()
            assert rows == [("2025-01-01", 100.0), ("2025-01-01", -100.0)]
    finally:
        engine.dispose()


def test_0008_does_not_apply_orphan_release_to_live_associated_reservation(scratch_db_path):
    _run_alembic(scratch_db_path, "0007")
    january = datetime(2025, 1, 15, tzinfo=timezone.utc)
    february = datetime(2025, 2, 3, tzinfo=timezone.utc)

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        _seed_analysis_lifecycle(
            engine,
            live_reserved_seconds=100.0,
            entries=[
                ("ANALYSIS_RESERVED", 100.0, january, "asset"),
                ("ANALYSIS_RESERVATION_RELEASED", -100.0, february, "none"),
            ],
        )
    finally:
        engine.dispose()

    try:
        _run_alembic(scratch_db_path, "0008")
    except RuntimeError as exc:
        assert "Cannot safely migrate negative monthly analysis quota balances" in str(exc)
    else:
        pytest.fail("migration consumed an associated live reservation for an orphan release")


def test_0008_rejects_negative_associated_reservation_lifecycle(scratch_db_path):
    _run_alembic(scratch_db_path, "0007")
    february = datetime(2025, 2, 3, tzinfo=timezone.utc)

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        _seed_analysis_lifecycle(
            engine,
            live_reserved_seconds=0.0,
            entries=[
                ("ANALYSIS_RESERVATION_RELEASED", -100.0, february, "asset"),
            ],
        )
    finally:
        engine.dispose()

    try:
        _run_alembic(scratch_db_path, "0008")
    except RuntimeError as exc:
        assert "Cannot safely migrate negative analysis reservation lifecycles" in str(exc)
    else:
        pytest.fail("migration accepted a negative associated reservation lifecycle")


def test_0008_rejects_associated_release_masked_by_later_reservation(scratch_db_path):
    _run_alembic(scratch_db_path, "0007")
    february = datetime(2025, 2, 3, tzinfo=timezone.utc)
    march = datetime(2025, 3, 5, tzinfo=timezone.utc)

    engine = sa.create_engine(f"sqlite:///{scratch_db_path}")
    try:
        _seed_analysis_lifecycle(
            engine,
            live_reserved_seconds=100.0,
            entries=[
                ("ANALYSIS_RESERVATION_RELEASED", -100.0, february, "asset"),
                ("ANALYSIS_RESERVED", 100.0, march, "asset"),
            ],
        )
    finally:
        engine.dispose()

    try:
        _run_alembic(scratch_db_path, "0008")
    except RuntimeError as exc:
        assert "Cannot safely migrate negative analysis reservation lifecycles" in str(exc)
    else:
        pytest.fail("later reservation masked an earlier negative associated lifecycle")
