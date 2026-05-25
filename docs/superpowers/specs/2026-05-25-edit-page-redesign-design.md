# Edit Page Redesign Design

## Goal

After video analysis completes, the edit page should feel like a focused confirmation step: users review suggested tennis rally clips, fine-tune boundaries when needed, and export a highlight compilation with confidence.

The redesign will closely follow the provided reference image: a large preview area on the left, a full-match rally map below it, and a fixed export queue on the right.

## Layout

Use a four-zone confirmation layout:

1. Top title bar: lightweight app header with `Breakpoint · 确认回合片段`, plus `返回欢迎页` and `重新处理`.
2. Main left area: large video preview with a poster-style guidance overlay when no segment is actively playing. The current selected segment should still play in the existing video player.
3. Bottom-left map: a full-match rally map showing every candidate segment as a vertical bar.
4. Right queue: a fixed `回合队列` panel with batch actions, selected rally cards, inline trim controls, and a bottom export call-to-action.

The left area should occupy roughly 70% of the width and the right queue roughly 30%, with the queue constrained enough to feel like a review panel but wide enough for titles and time ranges.

## Rally Queue

Each rally card shows:

- Inclusion state with a prominent checkbox.
- A generated rally title.
- Segment number.
- Time range using adjusted times when available.
- Optional supporting metadata such as duration, hit count, and score.

The selected card expands in place to show trim controls. Included cards are visually strong; excluded cards remain visible but muted so users can re-enable them.

## Generated Titles

Titles should be generated from existing segment data rather than requiring new analysis.

Initial title rules:

- High score: `高强度回合`
- Many hits: `多拍相持`
- Short duration: `短回合`
- Medium recommended score: `推荐回合`
- Low score: `普通回合`

Rules can combine where helpful, for example `多拍高强度回合 #08`. If no strong signal exists, fall back to `推荐回合 #08` or `普通回合 #08`.

This avoids expanding the scope into tactical understanding while still making the queue feel editorial and readable.

## Batch Actions

The queue header provides:

- `全选`: include all candidate segments.
- `推荐`: restore the automatic threshold-based recommendation.
- `清空`: exclude all segments.

`推荐` replaces the reference image's `最佳` label because it more accurately describes the current behavior: use the existing score threshold instead of selecting a fixed top-N set.

## Trim Interaction

The selected rally card expands to include:

- Start and end labels.
- A two-handle range bar.
- A left-side `- / +` pair to nudge the start.
- A right-side `- / +` pair to nudge the end.
- A reset action when adjusted times differ from the original segment.

Dragging a handle or pressing a nudge button updates the adjusted boundary and seeks the video to that boundary immediately. Export continues to use `startAdjusted` and `endAdjusted` when present, preserving the current data flow.

Nudge increments should be small enough for trimming, with `0.1s` as the default. Boundaries must remain valid with a minimum segment duration of `0.5s`, matching the current trim guard.

## Full-Match Rally Map

The bottom map becomes a reference-style vertical bar map:

- Orange: high-score recommended rally.
- Green: recommended/keepable rally.
- Gray: low-score or excluded rally.
- Selected segment: strong outline and time marker.

Clicking a bar selects the segment and seeks to its start. A `只看建议保留` filter can hide low-score/excluded candidates from the map when users want a focused review.

## Export Area

The right panel has a fixed bottom export summary:

- Selected rally count.
- Estimated compilation duration.
- Export button using the existing export flow.
- Export progress and export result feedback remain visible in this area.

This replaces the current top toolbar as the primary export action location, matching the confirmation-page mental model.

## Components and Data Flow

Reuse the existing React state and export pipeline:

- `AppState` remains the source of truth for `segments`, `included`, `selectedSegmentIndex`, `startAdjusted`, `endAdjusted`, and `videoDuration`.
- `VideoPlayer` remains responsible for playback, seeking, and pause-at-segment-end behavior.
- `SegmentList` should evolve into a right-side queue component, or be replaced by a more specifically named queue component if the implementation becomes clearer that way.
- `Timeline` should evolve into the reference-style full-match rally map.
- `Toolbar` export summary should move into the right queue panel, or be split so export status can render inside that panel.
- `flowCopy.ts` should own summary copy, export button copy, and generated rally title helpers.

No new backend analysis data is required.

## Edge Cases

- If there are no segments, show a clear empty state in the queue and disable export.
- If all segments are cleared, keep the map visible and show `选择回合后导出`.
- If an adjusted boundary would cross the opposite boundary, clamp it to preserve the minimum duration.
- If export fails, show the error in the right export area and keep the current selections intact.
- If the selected segment is filtered out by `只看建议保留`, clear the selection or select the next visible segment.

## Testing

Use existing renderer tests/build checks. Add focused coverage where practical for:

- Generated title helper output for high-score, multi-hit, short, recommended, and fallback segments.
- Review summary selected count and duration after adjusted times.
- Reducer behavior for restoring recommended segments via the existing threshold.
- Trim clamping behavior if helper logic is extracted.

Manual verification should cover selecting cards, toggling inclusion, using `推荐`, dragging/nudging trim handles, clicking map bars, and exporting adjusted selected clips.
