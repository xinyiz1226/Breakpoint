# Design: Output Workflow Redesign

## Date: 2026-05-11

## Context

Current `pipeline.py` exports individual clip files + a compiled highlight video. This is slow and produces unnecessary intermediate files. The analysis and compilation should be separated, and a unified entry point should be provided.

## Changes

### 1. Rename `phase1/pipeline.py` → `phase1/analyze.py`

- Remove `export_clips` call and individual clip export
- Remove `export_compilation` call
- Only output timeline JSON (`full_report.json`) after vision filter
- Default output dir: `<video_parent>/output_<video_stem>/`
- Remove `--no-compile` flag (no longer relevant)
- Keep `--reference` flag for compare

### 2. New `phase1/compile.py`

- Read timeline JSON + original video path
- Use ffmpeg concat to produce a single highlight video
- Default output: `<video_stem>_highlights.mp4` in the JSON's directory
- CLI: `python compile.py <video> <timeline.json> [-o output.mp4]`

### 3. New `TennisHighlightAnalysis.py` (project root)

- Unified entry point: analyze → compile
- CLI: `python TennisHighlightAnalysis.py <video> [-o output_dir] [--no-vision] [--no-compile]`
- Default output dir: `<video_parent>/output_<video_stem>/`
- Default highlight name: `<video_stem>_highlights.mp4`
- Calls analyze + compile internally

### 4. Update references

- `run_tests.py`: import from `analyze` instead of `pipeline`
- `compare.py`: no changes needed (imports extract_audio/detect_hits directly)
- `web/app.py`: no changes needed (imports phase1 modules directly)
- `param_sweep.py`: no changes needed

## Output Structure

```
input/
  video.MP4
  output_video/
    full_report.json
    video_highlights.mp4
```
