# Breakpoint Desktop App — Design Spec

## Overview

Breakpoint Desktop is a cross-platform (Windows + macOS) desktop GUI for the Breakpoint tennis highlight extraction pipeline. It replaces the existing CLI + Flask web UI with a native desktop experience.

## Technology Stack

- **Frontend**: Electron + React
- **Backend**: Python pipeline packaged as standalone binary via PyInstaller
- **Communication**: JSON-line protocol over stdout/stderr between Electron and Python process
- **Packaging**: electron-builder (Windows .exe installer, macOS .dmg)
- **Data format**: Reuses existing `full_report.json` timeline format

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 Electron Main                    │
│  · Window management, menus, file dialogs        │
│  · Python Bridge: spawn PyInstaller binary,      │
│    JSON-line bidirectional communication,         │
│    progress callbacks to renderer                 │
├─────────────────────────────────────────────────┤
│              Electron Renderer (React)            │
│  · Video player (HTML5 <video>)                  │
│  · Timeline editor (drag, add, delete segments)  │
│  · Analysis progress overlay                     │
│  · Export controls                               │
├─────────────────────────────────────────────────┤
│           PyInstaller Binary (standalone)         │
│  · analyze: audio + vision analysis → JSON       │
│  · compile: JSON timeline → MP4 highlight video  │
└─────────────────────────────────────────────────┘
```

## Visual Design

- **Aesthetic**: Light, airy, Roland-Garros inspired
- **Color palette**:
  - Terre battue (primary): `#D4845A`
  - Green (secondary): `#5A8C6F`
  - Gold (accent): `#C9A96E`
  - Cream background: `#FDFBF8`
  - Warm white: `#F7F3EE`
  - Text: `#3D3530`
- **Typography**: Playfair Display (headings), DM Sans (body), JetBrains Mono (data/timestamps)
- **Layout**: Top-bottom split — video player above, timeline editor below (Premiere/DaVinci style)
- **Mockup reference**: `.superpowers/brainstorm/229790-1778594034/content/breakpoint-ui-v2.html`

## User Flow

### 1. Welcome Screen (First Screen)

User opens the app and sees:
- Centered "打开视频" (Open Video) button
- Recent projects list below: video thumbnail + filename + last analysis timestamp
- Drag-and-drop zone: user can drop a video file anywhere on the window to open it

### 2. Video Selected → Auto-Analysis

When a video is selected:
1. Check if a cached `full_report.json` exists for this video (in `output_<video_stem>/`)
2. **Cache hit**: Load the existing timeline directly into the editor, skip analysis
3. **Cache miss**: Automatically start analysis with default parameters. No user action required.

During analysis:
- Video loads into the player (playable even during analysis)
- Progress overlay in top-right corner shows current step:
  - `[1/4] 音频提取...`
  - `[2/4] 击球检测...`
  - `[3/4] Vision 分析... 45%`
  - `[4/4] 评分排序...`
- "运行分析" toolbar button is replaced with "重新分析" (Re-analyze) for manual re-runs

### 3. Analysis Complete → Timeline Editing

When analysis finishes:
- Segments populate the timeline, ordered by time
- Each segment is color-coded by score:
  - High score (>2.3): terre battue tint
  - Medium score (1.7–2.3): green tint
  - Low score (<1.7): sand/gray
- Segment interactions:
  - **Click** a segment → video jumps to that timestamp and plays preview
  - **Delete** a segment → remove from timeline
  - **Adjust endpoints** → drag segment edges to fine-tune start/end
  - **Sort toggle**: by time (default) or by score
- Detail bar at bottom shows selected segment info: index, time range, duration, hit count, score, rank

### 4. Export

- Click "导出 Highlights" button
- Confirmation dialog shows: total segments, total duration
- FFmpeg compilation runs with progress bar
- On completion: open the output folder containing the highlight video
- Default output: `<video_stem>_highlights.mp4` in the same directory as the source video

## Toolbar Actions

| Button | Action |
|--------|--------|
| 打开视频 | File dialog to select video |
| 重新分析 | Re-run analysis (uses default params) |
| 添加 | Add a new manual segment at current playhead position |
| 拆分 | Split selected segment at current playhead position |
| 删除 | Remove selected segment from timeline |
| 导出 Highlights | Compile and export highlight video |

## Python–Electron Communication Protocol

Python process outputs JSON-line messages to stdout:

```jsonl
{"type":"progress","step":"1/4","label":"音频提取","pct":0}
{"type":"progress","step":"3/4","label":"Vision 分析","pct":45}
{"type":"result","data":[...segments...]}
{"type":"error","message":"..."}
```

Electron main process reads stdout line-by-line, parses JSON, and forwards to renderer via IPC.

## Analysis Parameters

Parameters are hidden from the main flow and use defaults:
- `silence_gap`: 6.0s
- `buffer`: 1.5s
- `vision`: enabled
- `vision_keep`: 0.7

Advanced users can adjust these in a Settings/Preferences page (accessible from menu bar).

## File Structure (Desktop App)

```
desktop/
├── package.json
├── electron/
│   ├── main.ts          # Electron main process
│   ├── preload.ts       # Context bridge
│   └── python-bridge.ts # Spawn and communicate with Python binary
├── src/
│   ├── App.tsx
│   ├── components/
│   │   ├── WelcomeScreen.tsx
│   │   ├── VideoPlayer.tsx
│   │   ├── Timeline.tsx
│   │   ├── SegmentBlock.tsx
│   │   ├── DetailBar.tsx
│   │   ├── Toolbar.tsx
│   │   └── ProgressOverlay.tsx
│   ├── hooks/
│   │   ├── useAnalysis.ts
│   │   └── useTimeline.ts
│   └── styles/
│       └── theme.css     # CSS variables from design spec
├── python/
│   └── build.py          # PyInstaller build script
└── electron-builder.yml
```

## Scope Boundaries

**In scope (v1)**:
- Open video, auto-analyze, edit timeline, preview, export
- Recent projects list
- Drag-and-drop file open
- Windows + macOS packaging

**Out of scope (v1)**:
- Batch processing (multiple videos)
- ROI manual calibration UI (relies on auto-detection)
- Comparison with reference videos
- Cloud sync or sharing
