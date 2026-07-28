# Web SaaS Design

## Goal

Design a public web version of Breakpoint with desktop-like analysis, review,
trim, and export behavior. The first version should be a cloud SaaS: users
upload tennis footage, the service analyzes it asynchronously, users review and
adjust rally selections in the browser, and the service exports a downloadable
highlight video.

## Product Scope

The first version supports authenticated users, project history, one video per
project, analysis jobs, review/edit state, export jobs, user quotas, and a small
admin surface.

The first version does not support multi-video batch projects, paid
subscriptions, enterprise SSO, collaborative editing, or mainland-China-specific
deployment requirements.

## Key Decisions

- Use ordinary email login or magic-link authentication.
- Store original videos and exported videos for seven days.
- Store reports, project metadata, edit decisions, and job history long term.
- Limit uploads to a single video. The initial implementation caps declared
  upload size at 20 GiB (env-configurable, `MAX_UPLOAD_SIZE_BYTES`) and the
  product duration limit remains no more than 3 hours per video
  (env-configurable, `MAX_VIDEO_DURATION_SECONDS`, default 10800). The API
  validates the client-declared duration against this cap at upload
  initiation and provisionally reserves monthly analysis-seconds quota
  against it, since real usage cannot be known before analysis. The
  authoritative duration is still worker-determined: the future worker's
  first step (ffprobe) must reject (mark the analysis job failed) and
  release/reconcile the reservation for assets whose real duration turns out
  to exceed the cap, since the client declaration is never fully trusted.
- Run the full existing analysis pipeline by default: audio hit detection,
  segmentation, vision ranking, and player identity. Keep a fast audio-only mode
  as an internal fallback or debugging option.
- Keep the deployment design portable, but avoid choices that would block a
  later Azure deployment.
- Prioritize international, non-mainland-China users for the first version.

## Architecture

Build the web product as a standard SaaS with clear runtime boundaries.

### Web App

Use a React web app, such as Next.js, for authentication screens, project
history, upload flow, job progress, review/edit UI, and export downloads. The
browser should not process video bytes through the API server. It should request
short-lived signed URLs for upload, playback, and download.

The review UI should preserve the desktop product's core information
architecture:

- video player;
- match map;
- rally queue;
- include/exclude controls;
- trim controls;
- export action and status.

It should be redesigned as a web SaaS experience rather than a one-to-one copy
of the Electron window. Local file paths, native file dialogs, and desktop
window chrome do not belong in the web model.

### API Server

Use a Python API service, such as FastAPI, for:

- authentication and authorization;
- project, video, job, rally, edit, and export endpoints;
- quota checks;
- upload-session creation;
- signed URL creation;
- job enqueueing;
- progress reads;
- admin operations.

The API server must not run CPU-heavy analysis or FFmpeg export work inline.

### Worker

Use a separate Python worker container for analysis and export. The worker
downloads video assets from object storage into a temporary workspace, invokes
the Breakpoint engine, uploads reports or exported videos, records progress, and
cleans up local temporary files.

For the first implementation, prefer invoking the engine as a child process or
module command, similar to the desktop bridge. This isolates engine crashes from
the worker supervisor and keeps behavior close to the existing Electron/Python
integration. The engine can later expose a more direct library API once the
worker boundary is stable.

### Data Stores

Use Postgres for durable application data:

- users and roles;
- projects;
- video assets;
- analysis jobs;
- rallies;
- rally edits;
- export jobs;
- quota ledger entries.

Use Redis or an equivalent queue/progress backend for job dispatch and short
term progress events.

Use object storage for:

- original uploaded videos;
- optional preview proxy videos;
- analysis reports;
- exported highlight videos.

The storage layer should be abstracted around object keys and signed URLs so it
can target S3-compatible storage first and Azure Blob Storage later.

## Data Model

### User

Represents an account. Fields include email, auth identity, role, quota policy,
and timestamps. Roles are `user` and `admin` for the first version.

### Project

Represents a user's analysis workspace. The first version has one source video
per project. A project owns analysis jobs, rallies, edits, and export jobs.

### VideoAsset

Represents a stored uploaded video or preview proxy. Fields include owner,
project, object key, original filename, content type, size, duration, format,
retention expiry, and processing status. There are two duration fields with
different authority: `declared_duration_seconds` is the client-declared
value supplied at upload initiation, validated against the duration cap and
used to reserve monthly analysis quota; `duration_seconds` and its check
status (`within_limit` / `exceeded` against the video duration cap) are both
nullable and stay unset in this layer — only the future worker probes and
writes them, once it has the actual media in hand.

### AnalysisJob

Represents the asynchronous analysis state machine:

- `queued`;
- `running`;
- `succeeded`;
- `failed`;
- `cancelled`.

It records progress, current step, worker version, engine parameters, failure
summary, stderr excerpt for admins, and the report asset key after success.

### Rally

Represents one analyzed rally from the report. It stores source index, start,
end, score, features, optional player identity data, and report version.

### RallyEdit

Represents user review state for a rally: included/excluded, adjusted start,
adjusted end, and timestamps. Edits are saved automatically.

### ExportJob

Represents asynchronous FFmpeg highlight compilation. It uses the current
project edit state to create a downloadable MP4 asset, with progress, failure
state, cancellation, and retry support.

### QuotaLedger

Records usage events such as uploaded bytes, analyzed minutes, export minutes,
and job counts. This supports free quotas now and paid plans later without
rewriting the processing model.

## Main User Flow

1. The user signs in and opens the project list.
2. The user creates a project and selects one video.
3. The web app asks the API to create an upload session.
4. The API checks quota and upload limits, creates the project/video records,
   and returns signed multipart upload instructions.
5. The browser uploads video chunks directly to object storage.
6. The browser finalizes the upload with the API.
7. The API records upload metadata and enqueues analysis; the worker probes the
   authoritative media metadata before analysis begins.
8. The progress page subscribes to job state using SSE or WebSocket.
9. The worker downloads the video to temporary disk, runs the existing engine,
   uploads `full_report.json`, expands rallies into Postgres, and marks the job
   succeeded.
10. The review page loads the video through a signed playback URL, loads rallies
    and edits from the API, and lets the user preview, include/exclude, and trim
    segments.
11. Each edit is automatically saved to the API.
12. The user starts export.
13. The API enqueues an export job using the current edit state.
14. The worker downloads the source video, invokes FFmpeg, uploads the exported
    MP4, and marks the export succeeded.
15. The web app shows a signed download link for the exported video.

## Video Playback

Use a signed object-storage URL for primary playback. If the original file uses
a container or codec the browser cannot play reliably, enqueue a preview proxy
job that creates a browser-compatible MP4. Do not transcode every upload by
default; unconditional transcoding would add cost and delay for videos that
already play correctly.

## Existing Code Reuse

Keep `engine/` as the reusable core analysis package. The SaaS worker should
reuse the same analysis behavior as the desktop app, including report schema and
JSON progress concepts.

The legacy `web/app.py` local prototype has been removed. It demonstrated an
early browser workflow, but it did not become the SaaS backend because it
mixed file selection, synchronous analysis, video serving, export, and UI
assumptions in one Flask process. The SaaS backend lives in `web/backend`
instead, built from a clean slate as a modular FastAPI monolith.

Borrow these desktop concepts for the web UI and model:

- `RallySegment` shape;
- auto-include threshold;
- match map;
- rally queue;
- trim editor behavior;
- JSON progress protocol;
- report reuse and report-version validation.

Avoid coupling the SaaS design to desktop-only concepts:

- local filesystem paths;
- Electron IPC;
- native file dialogs;
- packaged binary resource checks;
- local recent-project storage.

## Errors, Security, and Operations

### Uploads

Uploads must support chunk retry and explicit finalization. Abandoned upload
sessions should be cleaned up by a scheduled task. The API rejects projects
that exceed quota, declared size, declared duration, or supported format
rules at upload time. Upload initiation requires a client-declared duration,
rejects it outright if it exceeds `MAX_VIDEO_DURATION_SECONDS`, and
provisionally reserves that many seconds against the caller's monthly
analysis-seconds quota — real usage cannot be known before analysis runs, so
the declaration is the best available basis for enforcing the limit early
and preventing quota exhaustion by many oversized uploads in flight at once.
This reservation is released if finalize's own integrity checks fail (the
asset will never be analyzed). The authoritative check still belongs to the
worker: its first step (ffprobe) validates the real duration against the
cap and, on rejection, marks the analysis job failed and releases/reconciles
the reservation to actual usage. The API never probes media itself and never
treats the client declaration as ground truth for anything other than the
initial cap check and quota reservation.

### Jobs

Analysis and export jobs use the same state model: queued, running, succeeded,
failed, and cancelled. Cancelling a running job terminates the active child
process and cleans temporary files. Failed jobs keep a user-safe error message
and an admin-only diagnostic excerpt.

### Authorization

Every project, video, job, rally, edit, export, and signed URL operation is
authorized by owner. Admin operations require the admin role. User input never
becomes a server filesystem path; workers operate on object keys and temporary
directories only.

### Retention

Original videos and exported videos expire after seven days. Reports, rallies,
edits, and job history remain durable. Signed playback and download URLs are
short-lived.

### Quotas

The first version should include quotas even without payment integration.
Default limits should include per-user storage, monthly analyzed minutes, and
one active analysis job per user. Admins can adjust quotas manually.

### Observability

All API and worker logs should include project id and job id. The admin surface
shows users, projects, task states, failure summaries, retry controls, cancel
controls, and quota settings.

## Testing

### Engine and Worker

Keep the existing Python engine tests. Add worker integration tests that run a
small fixture video through analysis and export, using fake or local object
storage. Cover success, engine failure, cancellation, and temporary-file cleanup.

### API

Test upload-session creation, quota rejection, project authorization, job state
transitions, rally edit autosave, export creation, signed URL authorization, and
admin-only operations.

### Frontend

Test project list, upload state, progress display, review UI, rally queue,
match map, trim editing, and export status. Use a small number of end-to-end
tests for sign in, mocked upload completion, analysis completion, edit save, and
export completion.

### Contracts

Define stable schemas for progress events, reports, rallies, edits, and export
requests. Contract tests should prevent the desktop bridge, SaaS worker, and web
frontend from drifting apart.

## Open Implementation Notes

### Layer 1 status

Layer 1 delivered the backend foundation described in this document: the
`web/backend` FastAPI modular monolith, the full data model (users, refresh
sessions, one-time email tokens, projects, video assets, analysis jobs,
rallies, rally edits, export jobs, quota ledger) with a matching Alembic
migration chain, Argon2/JWT/rotating-refresh-token auth with email verification and
password reset, owner-authorized project CRUD, quota-enforced S3-compatible
multipart uploads with idempotent finalization, read-only admin APIs, health
checks, and local Docker Compose infrastructure (Postgres, Redis, MinIO,
Mailpit). It deliberately does not implement Celery task execution, SSE or
WebSocket progress streaming, preview generation, analysis or export
execution, a retention scheduler, or the web frontend UI — those remain
scoped to later layers against the state machines and contracts this layer
established. It enforces the declared-duration cap during upload initiation,
but leaves authoritative enforcement to the worker:
`VideoAsset.duration_seconds` and `duration_status` are nullable and stay unset
until a future worker probes the finalized asset and compares it
against the env-configurable `MAX_VIDEO_DURATION_SECONDS` (default 10800,
i.e. 3 hours), rejecting over-limit assets before analysis.

Upload initiation validates and reserves against a client-declared duration
(`VideoAsset.declared_duration_seconds`, required, distinct from the
nullable authoritative pair above): requests exceeding
`MAX_VIDEO_DURATION_SECONDS` are rejected outright, and accepted requests
provisionally reserve that many seconds of monthly analysis quota via a
`QuotaLedgerEntry` of type `ANALYSIS_RESERVED`. This is a three-step ledger
contract that only the first step is implemented in Layer 1:

1. **Reserve** (implemented): initiate writes `ANALYSIS_RESERVED` for the
   declared duration, so concurrent uploads cannot collectively exceed the
   monthly budget before any of them are actually analyzed.
2. **Release** (implemented for finalize-time integrity failures only): if
   finalize's own checks fail (size mismatch, oversized actual object), the
   asset will never be analyzed, so the API writes
   `ANALYSIS_RESERVATION_RELEASED` to free the reservation immediately.
   Reservations for uploads that are never finalized are not released in
   Layer 1 — like other abandoned-upload cleanup, that is the scheduled
   task's responsibility (not implemented).
3. **Reconcile** (not implemented, contract only): the future worker's
   first step is `ffprobe`. If the authoritative duration exceeds the cap,
   the worker must mark the analysis job failed and write
   `ANALYSIS_RESERVATION_RELEASED` for the declared amount. Otherwise, once
   analysis completes, the worker reconciles the reservation to actual
   usage via `ANALYSIS_COMPLETED` (present in the enum from Layer 1, reused
   rather than redefined for this purpose).

`monthly_analysis_seconds_used` (`/quota/me` and enforcement) is computed as
the signed sum of `ANALYSIS_RESERVED`, `ANALYSIS_RESERVATION_RELEASED`, and
`ANALYSIS_COMPLETED` deltas within the calendar month, i.e. it reflects
"reserved-or-used" seconds. A reservation and its release straddling a
calendar month boundary can show as negative usage in the release month;
this is an accepted Layer 1 simplification rather than an engineered
cross-month reconciliation.

The design intentionally leaves vendor-specific deployment details to the
implementation plan. The storage, queue, and container boundaries should allow a
later Azure deployment with Azure Blob Storage, Azure Container Apps or AKS,
managed Postgres, and managed Redis without changing product behavior.
