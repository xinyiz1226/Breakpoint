# iOS Cloud App Design

## Goal

Design an iOS version of Breakpoint with desktop-like analysis, review, trim,
and export capabilities. The iOS app should be a native client for Breakpoint
Cloud rather than a local port of the desktop Python engine.

## Product Scope

The first iOS version supports authenticated users, project history, uploading
existing videos, cloud analysis, cloud export, mobile review/editing, task
notifications, quota visibility, weak offline caching, and TestFlight rollout.

The first version does not support local on-device analysis, in-app full-match
recording, multi-video batch projects, paid subscriptions, enterprise SSO, or
strong offline review of original source video.

## Key Decisions

- Build the app as a native SwiftUI app.
- Reuse the same Breakpoint Cloud backend, account system, projects, quotas,
  analysis jobs, exports, retention rules, and storage model as the web SaaS.
- Do not port the current Python, OpenCV, librosa, ONNX, and FFmpeg pipeline
  into iOS for the first version.
- Let users select existing videos from Photos or Files.
- Support background and resumable uploads.
- Prefer Wi-Fi for upload; allow cellular upload only after explicit user
  confirmation.
- Stream source video from signed cloud URLs, using preview proxy videos when
  the original format is not reliably playable by iOS.
- Download only exported highlight videos by default, not original source
  videos.
- Preserve desktop-equivalent review capabilities, but redesign the UI for
  mobile.
- Support English and Chinese through iOS localization.
- Launch through TestFlight before public App Store release.

## Architecture

```text
iOS App
  - SwiftUI
  - Photos/Files import
  - background upload
  - AVPlayer review
  - Match Map / Rally Queue / Trim UI
  - push notifications
        |
        v
Breakpoint Cloud API
  - auth
  - projects
  - upload sessions
  - job state
  - edit autosave
  - export jobs
  - quota reads
        |
        v
Workers
  - existing Python engine
  - OpenCV/librosa/ONNX pipeline
  - FFmpeg export
        |
        v
Storage + Database
  - object storage for videos/reports/exports
  - Postgres for projects/jobs/rallies/edits/quotas
```

The iOS app is one client of the same cloud product described in the web SaaS
design. It should not create a separate backend or a separate project model.

## Why Analysis Stays in the Cloud

The current desktop pipeline depends on Python, librosa, OpenCV, FFmpeg, ONNX,
and YOLOX-Nano. Moving that stack into iOS would create high implementation and
maintenance cost:

- Python and scientific-computing dependencies are hard to package for iOS.
- Long video analysis would be constrained by battery, heat, memory, and iOS
  background execution limits.
- FFmpeg, OpenCV, and ONNX packaging would increase binary size and App Store
  review complexity.
- Full vision analysis is likely to be slow and fragile on typical phones.

On-device analysis can be considered later for a short-video or audio-only fast
mode, but it should not be part of the first complete iOS product.

## Main User Flow

1. The user signs in with the same Breakpoint Cloud account used on the web.
2. The Projects screen shows existing projects, task states, export states, and
   remaining quota.
3. The user creates a new project and selects one existing video from Photos or
   Files.
4. The app shows file size, upload policy, and network mode. If the user is on
   cellular, it asks for explicit confirmation before large upload.
5. The app creates an upload session through the API.
6. The app uploads the video with a background-capable, resumable upload flow.
7. The cloud finalizes the video and enqueues analysis.
8. The app shows queued/running/progress states and can receive push
   notifications for completion or failure.
9. When analysis succeeds, the Review screen loads the video through a signed
   streaming URL or preview proxy.
10. The user reviews rallies, seeks through the match map, toggles inclusion,
    and adjusts start/end boundaries.
11. Edits are automatically saved to the cloud.
12. The user starts export.
13. The cloud runs FFmpeg export as a background job.
14. The app receives completion status and lets the user save the result to
    Photos or share it to Files and other apps.

## iOS App Screens

### Projects

The Projects screen is the app's home. It shows project name or video filename,
thumbnail if available, creation time, analysis status, export status, and
remaining quota. It should support retrying failed jobs and opening completed
projects.

### Upload

The Upload screen selects a video from Photos or Files, displays size and
duration once available, checks quota, and shows upload progress. Upload state
must survive app backgrounding and recover from temporary network failures.

### Progress

The Progress screen shows cloud analysis state:

- queued;
- running;
- current pipeline step;
- sub-progress where available;
- failed;
- cancelled;
- succeeded.

It supports cancel and retry, but not pause/resume of analysis.

### Review

The Review screen preserves desktop-equivalent editing capabilities with a
mobile layout:

- AVPlayer at the top or in full-screen mode;
- bottom sheet or tabs for Rally Queue, Match Map, and Export;
- rally cards with score, time range, hit count, player-side metadata when
  available, and include/exclude state;
- trim controls for adjusted start and end;
- autosaved edits;
- quick seek and play for selected rally.

The UI should not copy the desktop three-column layout. It should adapt to
portrait and landscape phone use.

### Export

The Export area shows selected rally count, estimated duration, export progress,
completion, failure, retry, and cancel where supported by the cloud API.

After export succeeds, the app offers:

- save to Photos;
- share sheet;
- save to Files.

It should request Photos write permission only when the user chooses to save to
Photos.

### Profile

The Profile screen shows account email, language setting, quota usage, and sign
out. Admin controls are not part of the iOS first version.

## Networking and Background Behavior

Use iOS background upload support for large video uploads. Upload finalization
must be idempotent so the app can safely retry after interruption.

The app should cache project metadata, reports, and unsynced edit drafts. When
offline, it can show cached project state as read-only or draft state, but
upload, analysis, playback, export, and download require network access.

## Notifications

Support a minimal APNs notification set:

- analysis completed;
- analysis failed;
- export completed.

Notifications should deep link into the relevant project or export result.

## Data and Retention

iOS follows the same cloud retention policy as the web app:

- original videos expire after seven days;
- exported videos expire after seven days;
- reports, rally data, edits, job history, and project metadata remain long
  term;
- users can manually delete projects.

## Testing

### iOS Client

Test authentication state, project list rendering, upload state recovery,
network-mode prompts, progress rendering, review interactions, trim editing,
autosave retries, export completion, sharing, and localization.

### Backend Contracts

Use contract tests for project, upload, job, rally, edit, export, quota, signed
URL, and notification payloads. The web app and iOS app should consume the same
contract.

### End-to-End

For TestFlight readiness, cover:

1. sign in;
2. select video;
3. background upload interruption and resume;
4. analysis completion notification;
5. review and edit;
6. export completion notification;
7. save or share exported video.

## Rollout

Start with TestFlight. The first test group should focus on upload reliability,
large video handling, task progress accuracy, review usability, notification
delivery, and cloud cost per analyzed video.

Public App Store release should wait until the cloud backend has stable quota
controls, failure diagnostics, retention cleanup, and predictable worker cost.
