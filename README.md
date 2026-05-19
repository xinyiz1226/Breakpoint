# Breakpoint

Automatically extract highlight rallies from broadcast-angle tennis match footage.

Breakpoint analyzes full-length tennis videos using audio-based hit detection and computer vision to identify, rank, and export the best rallies — no manual scrubbing required.

**Website:** [xinyiz1226.github.io/Breakpoint](https://xinyiz1226.github.io/Breakpoint/)

![Welcome Screen](Images/Welcome.jpg)

## Features

- **Hit Detection** — Detects ball strikes via audio onset analysis with adaptive thresholds
- **Smart Segmentation** — Splits the match into individual rallies using silence gaps, with density trimming and duration filtering
- **Vision Ranking** — Scores each rally by player motion intensity (large court coverage, diving saves, etc.)
- **Visual Timeline Editor** — Browse, preview, and adjust rally boundaries in a desktop GUI
- **One-Click Export** — Export selected highlights as a single compiled video via ffmpeg

## Desktop App

Breakpoint ships as a standalone Windows desktop application. No Python, ffmpeg, or other dependencies required — everything is bundled in the installer.

### Download

Grab the latest release from the [Releases](https://github.com/xinyiz1226/Breakpoint/releases) page:

- **Breakpoint x.x.x.msi** — MSI installer

### Usage

1. **Open a video** — Launch the app and click "Open Video" or select a recent project
2. **Analyze** — The pipeline runs automatically: audio extraction → hit detection → segmentation → vision ranking. This produces a timeline (`full_report.json`) of ranked rally segments — no video files are generated at this stage.
3. **Review** — Browse the ranked segment list, click any segment to preview it in the video player
4. **Edit** — Drag the trim handles to adjust start/end times, toggle segments on/off with checkboxes
5. **Export** — Click "Export Highlights" to compile the selected segments into a single highlight `.mp4` video

![Editor](Images/Editor.jpg)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Analysis engine | Python 3.12, librosa, OpenCV, NumPy, SciPy |
| Desktop app | Electron, React, TypeScript, Vite |
| Video processing | ffmpeg |
| Packaging | PyInstaller (engine), electron-builder (installer) |

## Project Structure

```
engine/          Analysis pipeline (audio, vision, segmentation, ranking, export)
├── audio/       Audio extraction and hit detection (librosa)
├── vision/      Player motion analysis (OpenCV)
├── export/      Clip extraction and highlight compilation (ffmpeg)
├── pipeline.py  Main orchestrator
├── segmentation.py
├── ranking.py
└── ffutil.py

desktop/         Electron + React desktop application
├── src/main/    Electron main process (Python bridge, ffmpeg export)
├── src/renderer/ React UI (video player, timeline, segment list)
└── scripts/     Build and packaging scripts

tools/           Development utilities (comparison, parameter sweep, tests)
web/             Legacy Flask web UI
```

## Open Source License and Commercial Licensing (License)

This project is released under the **GNU Affero General Public License v3 (AGPL-3.0)**.

- **Personal / coach / research use**: free of charge. You may freely deploy, modify, and use this project for personal match review or teaching.
- **Cloud service and commercial use (anti-free-riding clause)**: if you plan to integrate this project's core algorithms (including but not limited to tennis target detection, rally segmentation, and automatic highlight editing logic) into your **commercial SaaS, WeChat mini-program, commercial app, or paid website backend services**, then under AGPL-3.0, **you must open-source the complete source code of your entire commercial system without additional restrictions**.
- **Commercial License**: if you do not want to open-source your system code but would like to use Breakpoint technology in commercial products, please contact the author for a commercial license.
