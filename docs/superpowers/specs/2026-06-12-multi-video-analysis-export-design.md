# Multi-Video Analysis and Export Design

## Goal

Add a desktop app workflow for selecting multiple video files, analyzing them as one batch, reviewing all successful rally candidates in one shared queue, and exporting selected rallies from multiple source videos into one MP4 highlight reel.

The first version should prioritize correctness and a clear batch review experience. It should not add persistent batch projects, parallel analysis, manual export reordering, or a cross-video unified timeline.

## Recommended approach

Use a batch workspace model in the renderer. The current app assumes one `videoPath`, one segment list, and one export source. Multi-video support should make source video identity explicit throughout the renderer state, queue UI, preview behavior, and export IPC contract.

The batch workspace is in memory for this iteration. Users create it by selecting or dropping multiple video files. Each video is analyzed sequentially. Successful analysis results are merged into one global rally queue; failed videos remain visible with a retry action and do not block review or export of successful videos.

## Architecture

Replace the single-video renderer state shape with a batch-oriented shape:

- `videos[]`: one record per imported video, with `id`, `path`, display name, selection order, analysis status, error message, progress state, duration, and rally count.
- `rallies[]`: one global queue of analyzed rally candidates. Each rally includes `id`, `videoId`, `sourceIndex`, original `start` and `end`, optional adjusted start/end, score, features, and included state.
- `activeVideoId`: the source video currently loaded in the player.
- `selectedRallyId`: the selected rally in the global queue.

Keep analysis and export APIs source-aware instead of relying on array position. A rally must always be traceable back to its source video, even after filtering, trimming, selection changes, and export preparation.

## Import and batch creation

The welcome screen becomes a batch creation screen:

- The open-file dialog supports selecting multiple video files.
- The drag-and-drop area accepts multiple supported video files.
- Recent videos can remain single-file shortcuts, but selecting recent items should create a one-video batch for backward compatibility.

After import, the app creates one workspace containing all selected videos in the order chosen by the user. That order defines the default global queue and export order.

## Analysis flow

Analyze videos sequentially to match the current single `analysisProcess` bridge and avoid excessive CPU/GPU usage. The batch controller should:

1. Check each video for a reusable analysis report.
2. Load reusable reports immediately when present.
3. Run `runAnalysis(videoPath)` for videos without reusable reports.
4. Convert successful reports into source-aware rallies.
5. Mark failed videos with an error and a retry action.
6. Move to the review workspace after all videos have either succeeded or failed.

Progress UI should show both batch-level and current-video progress, such as "Video 2 / 5" plus the existing analysis step/progress details. Retrying a failed video should analyze only that video and append or replace its source-aware rallies in the global queue.

## Review workspace UI

Use a batch workspace layout:

- A video list panel or strip shows each imported video, its status, rally count, and retry action when failed.
- The main player shows the active video.
- The match map remains scoped to the active video in this first version.
- The right-side rally queue becomes a global queue across all successful videos.

The global queue is sorted by user-selected video order, then by rally start time within each video. Each rally card shows a source label, such as the file name or "Video 1", so users know where the clip came from.

When the user clicks a rally from another video, the app updates `activeVideoId`, loads that source video into the player, seeks to the rally start time, and plays or previews using the existing seek behavior. Trim edits remain attached to the selected rally and its source video.

Global queue actions apply to all rallies:

- Select all.
- Restore recommended.
- Clear.

Failed videos do not appear in the rally queue until they are successfully retried.

## Export

Change the export contract from a single source video plus segments to source-aware export clips:

```ts
interface ExportClip {
  videoPath: string
  start: number
  end: number
}
```

Before export, the renderer filters included rallies and sorts them by video selection order, then by start time within each video. It passes `ExportClip[]` to the main process.

The ffmpeg bridge should create one input per clip, using each clip's own `videoPath`, then concatenate all selected clips into one MP4. The default output name should use the first selected video's base name, such as `<first-video>_highlights.mp4`.

Export progress should use the total selected clip duration across all source videos. Cancelling export should keep the current behavior of stopping ffmpeg and deleting the partial output file. Export failures should surface in the export panel without clearing the user's selected rallies or trim edits.

## Error handling

Batch analysis should not discard successful work when one video fails. The workspace should preserve successful videos and rallies, mark failed videos clearly, and let users retry each failed video independently.

Invalid or unsupported files should be rejected at import with a visible message. If all videos fail, the workspace should show the batch errors and offer returning to the welcome screen or retrying individual videos.

The implementation should avoid silent early returns for invalid batch state. Missing source video records, empty export selections, invalid clip durations, and ffmpeg failures should surface through the same UI error patterns used by the current app.

## Testing

Update renderer flow tests and source checks to cover:

- Creating a batch from multiple selected video paths.
- Sequential analysis state transitions across multiple videos.
- Loading reusable reports per video.
- Preserving successful videos when one video fails.
- Retrying a failed video without reprocessing successful videos.
- Global rally queue sorting by video selection order and in-video start time.
- Selecting a rally from another video updates the active video and seek target.
- Trim edits stay attached to the correct source-aware rally.
- Export payload contains `videoPath`, `start`, and `end` for each selected clip.
- Multi-select file dialog and multi-file drag-and-drop entry points.
- ffmpeg bridge construction for multi-source concat inputs.

Existing single-video behavior should remain supported as a one-video batch.

## Out of scope

This first iteration does not include:

- Saving or reopening batch projects.
- Parallel video analysis.
- Manual drag-and-drop ordering of the export queue.
- A unified timeline across all source videos.
- Website, documentation screenshot, or installer changes.

## Completion criteria

The feature is complete when:

- Users can select or drop multiple video files in the desktop app.
- The app analyzes selected videos sequentially and shows batch/current-video progress.
- Successful videos contribute rallies to one global review queue.
- Failed videos remain visible and can be retried individually.
- Clicking a rally previews the correct source video at the correct time.
- Users can select, clear, restore recommended, and trim rallies across the global queue.
- Export creates one MP4 containing selected rallies from all source videos in video-selection order and in-video time order.
- Existing one-video import, analysis, review, and export behavior still works.
- Renderer flow tests and the desktop build pass.
