"""Cross-month quota accounting regressions.

Ledger aggregation previously filtered on ``created_at >= current_month_start``,
so a release/reconciliation ledger row written *now* (e.g. a reservation made
in January reconciled or released after the calendar rolls over to February)
would net against -- and could drive negative -- the *current* month's
usage instead of the month the original reservation actually belonged to.

Every ledger entry now carries an explicit ``accounting_month`` (first UTC
day of the month) that is independent of ``created_at``, and
``VideoAsset.analysis_reservation_month`` / ``storage_reservation_month``
durably remember which month a live reservation belongs to, so release/
resize always targets that original period regardless of when (wall-clock)
the release/resize actually happens. These tests use explicit UTC
``date``/``datetime`` values for "January" and "February" rather than
monkeypatching ``datetime.now()``, since the service functions themselves
never consult wall-clock time once a caller passes an explicit
``accounting_month``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import QuotaLedgerEventType, VideoAssetStatus
from app.models.project import Project
from app.models.quota import QuotaLedgerEntry
from app.models.video import VideoAsset
from app.services import quota as quota_service
from app.services.reservations import release_analysis_reservation, release_storage_reservation
from tests.conftest import create_user

JANUARY = date(2026, 1, 1)
FEBRUARY = date(2026, 2, 1)


def _make_video_asset(db: Session, owner) -> VideoAsset:
    project = Project(owner_id=owner.id, name="Rollover Match")
    db.add(project)
    db.flush()
    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key=f"projects/{project.id}/source/{uuid.uuid4()}.mp4",
        original_filename="match.mp4",
        content_type="video/mp4",
        declared_size_bytes=1024,
        declared_duration_seconds=100.0,
        status=VideoAssetStatus.UPLOAD_INITIATED,
        upload_id="upload-1",
        part_count=1,
    )
    db.add(video_asset)
    db.flush()
    return video_asset


def test_monthly_analysis_usage_keys_on_accounting_month_not_created_at(
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="rollover-analysis@example.com", password="s3cret-pw!")

    quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        seconds_delta=500.0,
        accounting_month=JANUARY,
    )
    db_session.commit()

    # Written "now" (created_at truthfully reflects that), but the release
    # belongs to the January reservation it is compensating.
    release_entry = quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVATION_RELEASED,
        seconds_delta=-500.0,
        accounting_month=JANUARY,
    )
    db_session.commit()
    release_entry.created_at = datetime(2026, 2, 3, tzinfo=timezone.utc)
    db_session.commit()

    # An unrelated, independently valid February reservation.
    quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        seconds_delta=300.0,
        accounting_month=FEBRUARY,
    )
    db_session.commit()

    assert (
        quota_service.monthly_analysis_seconds_used(db_session, owner.id, accounting_month=JANUARY)
        == 0.0
    )
    assert (
        quota_service.monthly_analysis_seconds_used(db_session, owner.id, accounting_month=FEBRUARY)
        == 300.0
    )


def test_record_ledger_event_defaults_accounting_month_to_current_month(
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="default-month@example.com", password="s3cret-pw!")

    entry = quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        seconds_delta=42.0,
    )
    db_session.commit()

    expected = datetime.now(timezone.utc).date().replace(day=1)
    assert entry.accounting_month == expected


def test_release_analysis_reservation_writes_original_reservation_month(
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="release-original-month@example.com", password="s3cret-pw!")
    video_asset = _make_video_asset(db_session, owner)
    video_asset.analysis_reserved_seconds = 250.0
    video_asset.analysis_reservation_month = JANUARY
    quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        video_asset_id=video_asset.id,
        seconds_delta=250.0,
        accounting_month=JANUARY,
    )
    db_session.commit()

    # Release happens "in February" (wall clock), but must still be booked
    # against the reservation's original January period.
    release_analysis_reservation(db_session, video_asset)
    db_session.commit()

    release_row = db_session.execute(
        select(QuotaLedgerEntry)
        .where(
            QuotaLedgerEntry.video_asset_id == video_asset.id,
            QuotaLedgerEntry.event_type == QuotaLedgerEventType.ANALYSIS_RESERVATION_RELEASED,
        )
    ).scalar_one()
    assert release_row.accounting_month == JANUARY

    assert video_asset.analysis_reserved_seconds == 0.0
    assert video_asset.analysis_reservation_month is None
    assert (
        quota_service.monthly_analysis_seconds_used(db_session, owner.id, accounting_month=JANUARY)
        == 0.0
    )


def test_release_storage_reservation_writes_original_reservation_month(
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="release-storage-month@example.com", password="s3cret-pw!")
    video_asset = _make_video_asset(db_session, owner)
    video_asset.storage_reserved_bytes = 4096
    video_asset.storage_reservation_month = JANUARY
    quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.STORAGE_RESERVED,
        video_asset_id=video_asset.id,
        bytes_delta=4096,
        accounting_month=JANUARY,
    )
    db_session.commit()

    release_storage_reservation(db_session, video_asset)
    db_session.commit()

    release_row = db_session.execute(
        select(QuotaLedgerEntry)
        .where(
            QuotaLedgerEntry.video_asset_id == video_asset.id,
            QuotaLedgerEntry.event_type == QuotaLedgerEventType.STORAGE_RESERVATION_RELEASED,
        )
    ).scalar_one()
    assert release_row.accounting_month == JANUARY
    assert video_asset.storage_reserved_bytes == 0
    assert video_asset.storage_reservation_month is None


def test_storage_bytes_used_is_all_time_balance_across_month_rollover(
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="storage-rollover@example.com", password="s3cret-pw!")

    quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.STORAGE_RESERVED,
        bytes_delta=1000,
        accounting_month=JANUARY,
    )
    db_session.commit()

    release_entry = quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.STORAGE_RESERVATION_RELEASED,
        bytes_delta=-1000,
        accounting_month=JANUARY,
    )
    db_session.commit()
    release_entry.created_at = datetime(2026, 2, 5, tzinfo=timezone.utc)
    db_session.commit()

    # A January reservation fully released must not leave any residual
    # balance (and must never go negative) once the calendar has rolled
    # over to February.
    assert quota_service.storage_bytes_used(db_session, owner.id) == 0

    # A genuinely new February reservation is unaffected by -- and cannot
    # be inflated or bypassed by -- the already-settled January history.
    quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.STORAGE_RESERVED,
        bytes_delta=500,
        accounting_month=FEBRUARY,
    )
    db_session.commit()

    assert quota_service.storage_bytes_used(db_session, owner.id) == 500
