# Breakpoint Web Frontend (Contract Placeholder)

There is no frontend implementation in this repository yet. This directory
exists only to record the API contract the future web frontend (see
`docs/designs/web-saas-design.md`) will depend on, so backend changes do not
silently drift away from it.

## Backend base URL

The frontend talks to the FastAPI service in `web/backend`. In local
development that service listens on `http://localhost:8000`.

## Auth contract

- `POST /api/v1/auth/register` — create an account (email only; no password
  is ever accepted or stored by this call) and trigger a verification email
  containing a one-time token. Existing verified accounts return a conflict;
  an unverified account can retry to receive a fresh verification token that
  invalidates any earlier one. Until verified, the account has an
  unguessable, server-generated placeholder password that cannot be used to
  log in.
- `POST /api/v1/auth/verify-email` — consume a one-time verification token
  together with the chosen password (subject to the same constraints as
  login). This is the only call that ever sets the account's real
  `password_hash`: the mailbox owner who submits the token they received
  controls the account's eventual password, not whoever called `register`.
- `POST /api/v1/auth/login` — email + password. Returns a short-lived JWT
  access token in the JSON body and sets an HttpOnly, `SameSite=Lax` refresh
  token cookie. Only verified, active users can log in.
- `POST /api/v1/auth/refresh` — reads the refresh cookie, atomically rotates
  it (revokes the old session, issues a new one), returns a new access token.
- `POST /api/v1/auth/logout` — revokes every active refresh session for the
  account identified by the presented cookie (even a stale, already-rotated
  one) and clears the cookie.
- `POST /api/v1/auth/forgot-password` — always returns a generic response
  regardless of whether the email exists.
- `POST /api/v1/auth/reset-password` — consumes a one-time reset token, sets a
  new password, and revokes all of the user's refresh sessions.

The access token must be sent in the Authorization request header using
the bearer scheme on all authenticated requests. The frontend never reads or
stores the refresh token directly — the browser cookie jar handles it.

## Project / upload contract

- `POST /api/v1/projects`, `GET /api/v1/projects`, `GET /api/v1/projects/{id}`,
  `PATCH /api/v1/projects/{id}`, `DELETE /api/v1/projects/{id}` — project CRUD,
  owner-scoped.
- `POST /api/v1/projects/{id}/uploads` — start a multipart upload session
  (requires a declared duration, validates MIME type/size/duration and quota,
  reserves declared analysis seconds, and returns presigned part URLs).
- `POST /api/v1/projects/{id}/uploads/{video_asset_id}/finalize` — complete
  the multipart upload with an idempotency key; safe to retry.
- `GET /api/v1/projects/{id}/video/signed-url` — short-lived signed GET URL
  for playback.

## Quota contract

- `GET /api/v1/quota/me` — current usage (analysis seconds this month, active
  job count) and effective limits (including any per-user override).

## Admin contract (read-only)

- `GET /api/v1/admin/users`
- `GET /api/v1/admin/projects`
- `GET /api/v1/admin/analysis-jobs`
- `GET /api/v1/admin/export-jobs`
- `GET /api/v1/admin/failures`

None of the admin endpoints support mutation, retry, or cancellation in this
layer.

## Rally / report shape

Rallies mirror the desktop report convention: `source_index`, `start`, `end`,
`score`, `features`, `players`, `report_version`. Rally edits mirror the
desktop edit convention: `included`, `adjusted_start`, `adjusted_end`.

## Analysis, progress, review, and export

- `GET /api/v1/projects/{id}/analysis` — durable analysis snapshot.
- `POST /api/v1/projects/{id}/analysis/cancel` — cancels queued work immediately
  or requests active child-process termination.
- `POST /api/v1/projects/{id}/analysis/retry` — requeues a failed job after
  atomically rebooking its authoritative-duration reservation.
- `GET /api/v1/projects/{id}/analysis/events` — owner-authorized SSE. Send
  `Last-Event-ID`; event IDs are persisted monotonic job versions. Event data
  includes status, progress, current step, user-safe failure summary, and finish
  time, but never admin diagnostics.
- `GET /api/v1/projects/{id}/rallies` and
  `PATCH /api/v1/projects/{id}/rallies/{rally_id}` — review and autosave edits.
- `POST /api/v1/projects/{id}/exports` — atomically snapshots the current
  included/trimmed rally selection before enqueue.
- `GET /api/v1/projects/{id}/exports/{export_job_id}` plus `/cancel`, `/retry`,
  `/events`, and `/signed-url` — export lifecycle, SSE, and seven-day download.

Analysis reports use `analysis_version: 2`. Source playback automatically uses
the H.264/AAC preview proxy when the original probe found an incompatible
browser container/codec combination.

This file should be kept in sync with `web/backend/app/routers` whenever the
contract changes, until a real frontend implementation replaces it.
