"""Idempotent reservation release helpers.

``VideoAsset``'s durable ``analysis_reserved_seconds`` /
``storage_reserved_bytes`` / ``storage_counted_bytes`` fields -- not ledger
history -- are authoritative for whether there is anything left to release.
Every helper here reads the current durable amount and, if it is already
zero, writes no ledger entry at all: this is what makes repeated calls (e.g.
a finalize integrity failure followed by a later project tombstone, or a
retried cleanup task) safe to call more than once without double-releasing.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.enums import QuotaLedgerEventType
from app.models.video import VideoAsset
from app.services import quota as quota_service


def release_analysis_reservation(db: Session, video_asset: VideoAsset) -> None:
    """Release the video asset's outstanding analysis-seconds reservation,
    if any. No-op if it has already been released (or never made)."""
    reserved = video_asset.analysis_reserved_seconds
    if reserved <= 0:
        return
    quota_service.record_ledger_event(
        db,
        user_id=video_asset.owner_id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVATION_RELEASED,
        video_asset_id=video_asset.id,
        seconds_delta=-reserved,
    )
    video_asset.analysis_reserved_seconds = 0.0


def release_storage_reservation(db: Session, video_asset: VideoAsset) -> None:
    """Release the video asset's outstanding declared-size storage-byte
    reservation, if any (an upload that never reached UPLOADED)."""
    reserved = video_asset.storage_reserved_bytes
    if reserved <= 0:
        return
    quota_service.record_ledger_event(
        db,
        user_id=video_asset.owner_id,
        event_type=QuotaLedgerEventType.STORAGE_RESERVATION_RELEASED,
        video_asset_id=video_asset.id,
        bytes_delta=-reserved,
    )
    video_asset.storage_reserved_bytes = 0


def release_counted_storage_bytes(db: Session, video_asset: VideoAsset) -> None:
    """Release previously *counted* (post-finalize actual) stored bytes.

    Used when the underlying object is actually deleted: project tombstone
    cleanup, or retention expiry. Retention cleanup must use this same
    helper so a byte accounting release is never inferred ad hoc from
    ledger history.
    """
    counted = video_asset.storage_counted_bytes
    if counted <= 0:
        return
    quota_service.record_ledger_event(
        db,
        user_id=video_asset.owner_id,
        event_type=QuotaLedgerEventType.STORAGE_RELEASED,
        video_asset_id=video_asset.id,
        bytes_delta=-counted,
    )
    video_asset.storage_counted_bytes = 0
