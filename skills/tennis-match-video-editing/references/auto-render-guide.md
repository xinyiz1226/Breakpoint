# Auto Render Guide

## Purpose

This guide covers the automatic render path for the tennis match editing skill.

## Input and Output

- Input: full raw tennis match video.
- Input metadata: clip decision manifest json.
- Output: final highlight mp4 video.
- Default output location: same directory as the source video.
- Hard rule: output resolution must match source exactly.

## Manifest

Use this example as a base:

- [auto-render-manifest.example.json](auto-render-manifest.example.json)

Only clips with `action: keep` are rendered into final output.
If `output` is omitted in the manifest, the script writes `<source_stem>_highlights.mp4` beside the source video.

## Auto-Drafting a Manifest

Generate a draft manifest from the source video using audio-driven rally detection:

```bash
python3 skills/tennis-match-video-editing/tools/generate_manifest_draft.py \
  /absolute/path/to/raw_match.mov \
  --keep-count 22
```

What the generator does:

1. Extracts mono audio via ffmpeg with denoising (`highpass=f=2500,lowpass=f=10000,afftdn=nf=-25`). Use `--no-denoise` to disable, or `--audio-filter` to override.
2. Detects sharp ball-impact onsets via spectral flux on the high-frequency band (`--high-freq-hz`, `--onset-threshold-ratio`).
3. Groups onsets into rally sequences using rhythm constraints: `--rally-min-hits`, `--rally-min-interval`, `--rally-max-interval`, `--rally-max-jitter`.
4. Merges adjacent sequences within `--merge-gap`, pads each window via `--pre-pad`/`--post-pad`, ranks by score, and marks the top `--keep-count` as keep.
5. Writes the draft manifest beside the source video (`<source_stem>_draft_manifest.json`) and an onset CSV for inspection.

Review policy: the auto draft is a candidate set. Promote `review` clips you want kept, demote any `keep` clips that are not real rallies, then run the render step.

## Command

```bash
python3 skills/tennis-match-video-editing/tools/render_from_manifest.py \
  skills/tennis-match-video-editing/references/auto-render-manifest.example.json
```

Optional quality knobs:

```bash
python3 skills/tennis-match-video-editing/tools/render_from_manifest.py <manifest.json> \
  --crf 18 \
  --preset medium \
  --log /absolute/path/to/edit-log.md
```

## Fallback Rule

If automatic render cannot pass quality review, switch to semi-automatic path:

1. Keep the same keep/drop clip decisions.
2. Export timeline package for CapCut/Jianying.
3. Manually export with source-matching resolution.
