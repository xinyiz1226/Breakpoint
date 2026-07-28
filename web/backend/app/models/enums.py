"""Shared enums for model state machines.

Stored as plain strings (``native_enum=False`` at the column level) so both
Postgres and SQLite behave identically and future states can be added
without an ``ALTER TYPE`` migration.
"""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class JobStatus(str, enum.Enum):
    """Shared state machine for analysis and export jobs.

    Workers are not implemented in this layer; jobs are created in
    ``QUEUED`` and never transitioned automatically.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED})
ACTIVE_JOB_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.RUNNING})


class VideoAssetStatus(str, enum.Enum):
    UPLOAD_INITIATED = "upload_initiated"
    UPLOADED = "uploaded"
    UPLOAD_ABORTED = "upload_aborted"


class VideoDurationStatus(str, enum.Enum):
    """Set by the future analysis worker after it probes the uploaded
    file's real duration against ``Settings.max_video_duration_seconds``.

    This layer never sets this column: it does not probe media files or
    trust a client-declared duration. ``NULL`` means "not yet checked",
    which is the only value this layer ever persists. The worker must
    write ``WITHIN_LIMIT`` or ``EXCEEDED`` before analysis runs, and mark
    the associated ``AnalysisJob`` ``FAILED`` (with a user-safe failure
    summary) for ``EXCEEDED`` assets instead of running analysis on them.
    """

    WITHIN_LIMIT = "within_limit"
    EXCEEDED = "exceeded"


class EmailTokenPurpose(str, enum.Enum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class QuotaLedgerEventType(str, enum.Enum):
    """Ledger balance semantics: a user's monthly analysis-seconds usage is
    the running sum of ``seconds_delta`` across these event types for the
    month (see ``services.quota.monthly_analysis_seconds_used``).

    Reservation lifecycle (the state contract the next layer must follow):

    1. ``ANALYSIS_RESERVED`` — written by this layer at upload *initiate*
       time with ``seconds_delta = +declared_duration_seconds``. This
       provisionally books quota against the client-declared duration
       before the real duration is known, so a user cannot bypass the
       monthly cap by declaring a short duration for a long video and
       starting many uploads at once.
    2. ``ANALYSIS_RESERVATION_RELEASED`` — written with
       ``seconds_delta = -declared_duration_seconds`` whenever a
       reservation must be freed without counting real usage: this layer
       does so synchronously if finalize's integrity checks fail (the
       asset is marked ``UPLOAD_ABORTED`` and will never be analyzed). The
       future worker must do the same the moment ffprobe finds the
       authoritative duration exceeds ``max_video_duration_seconds``,
       failing the job instead of running analysis.
    3. ``ANALYSIS_COMPLETED`` — the future worker writes this with
       ``seconds_delta = +actual_duration_seconds`` once analysis
       succeeds, alongside releasing the original reservation (step 2),
       so the ledger balance reconciles from the provisional estimate to
       real usage rather than double-counting.

    ``ANALYSIS_FAILED``/``ANALYSIS_CANCELLED`` carry no ``seconds_delta``;
    they are informational markers for jobs that consumed no billable
    analysis time (the reservation is still released via step 2).
    """

    UPLOAD_FINALIZED = "upload_finalized"
    ANALYSIS_QUEUED = "analysis_queued"
    ANALYSIS_RESERVED = "analysis_reserved"
    ANALYSIS_RESERVATION_RELEASED = "analysis_reservation_released"
    ANALYSIS_COMPLETED = "analysis_completed"
    ANALYSIS_FAILED = "analysis_failed"
    ANALYSIS_CANCELLED = "analysis_cancelled"
