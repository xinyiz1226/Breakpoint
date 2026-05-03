# Editing Principles

## Objective

Turn full-match high-angle amateur tennis footage into a cleaner, watchable final highlight video while preserving tactical value and shot quality.

## Keep/Drop Decision Model

### Drop-first categories

1. Non-rally utility segments:
- Ball pickup
- Side change
- Long ready/reset idle
- Camera-on-court with no active point

2. Low-value point endings:
- Return into net with no setup
- Immediate out ball with no pressure buildup
- Double fault with no tactical context value

### Keep-first categories

1. Serve value:
- Ace
- Direct serve winner

2. Rally value:
- Extended rally with momentum shift
- Forced-error point built by sustained pressure

3. Tactical value:
- Angle opening then finish
- Net entry and volley conversion
- Deep push then finish to open space

4. Execution value:
- High-speed winner with clear technique quality

## Pacing Guidance

- Start with 1-2 high-energy points to establish hook.
- Alternate fast points and longer rally points for rhythm.
- Avoid stacking too many similar points back-to-back.
- Keep replay usage minimal unless user requests cinematic style.

## Resolution and Export Constraints

- Final output width/height must equal source width/height.
- Keep frame rate unchanged unless user explicitly requests otherwise.
- Default output: mp4, H.264-compatible workflow.

## Ambiguity Handling

When uncertain whether a point is highlight-worthy:

1. Tag as REVIEW.
2. Add short reason (for example: "short rally but key score context").
3. Keep out of final timeline until reviewed.

## Automatic Draft Detection

The automatic draft (`generate_manifest_draft.py`) is a heuristic, not a tennis classifier:

1. Audio pre-filtering. Default ffmpeg chain `highpass=f=2500,lowpass=f=10000,afftdn=nf=-25` to suppress voice, wind, and ambient noise so racket impacts dominate.
2. Onset detection. Spectral flux on the high-frequency band (default >=2 kHz) finds sharp transients, with a minimum 120 ms separation to avoid duplicate triggers.
3. Rally-sequence grouping. Consecutive onsets are chained when intervals fall within `[rally-min-interval, rally-max-interval]` (default 0.45-2.5 s) and rhythm jitter (std/mean) is below `rally-max-jitter` (default 0.9). A sequence must have at least `rally-min-hits` (default 3) hits to qualify.
4. Scoring. Each sequence is scored by hit count weighted by rhythm steadiness; nearby sequences within `merge-gap` are merged.
5. Output. Each sequence becomes a candidate clip padded by `pre-pad`/`post-pad`. The top N by score are marked `keep`; the rest are `review`.

Known limits and review policy:

- The detector cannot distinguish hit-only signals (rallies, drills, warm-ups, fault-then-fault sequences). Reviewing the candidate list is recommended.
- Coverage of true rallies in `keep + review` is typically high; ranked KEEP precision is limited.
- For best results, sweep through the candidate list and promote/demote actions before rendering.
