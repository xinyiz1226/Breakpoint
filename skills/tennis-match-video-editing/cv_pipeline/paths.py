"""Centralized paths and binary locations for the CV pipeline.

Override via environment variables when running on a different machine.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# External binaries
FFMPEG = os.environ.get(
    "BREAKPOINT_FFMPEG",
    "C:/Users/xinyi/AppData/Local/Microsoft/WinGet/Packages/"
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin/ffmpeg.exe",
)
FFPROBE = os.environ.get(
    "BREAKPOINT_FFPROBE",
    FFMPEG.replace("ffmpeg.exe", "ffprobe.exe"),
)

# Model weights
WEIGHTS_DIR = Path(os.environ.get(
    "BREAKPOINT_WEIGHTS_DIR",
    "C:/Users/xinyi/AppData/Local/Temp/breakpoint/weights",
))
YOLOV5_BALL = WEIGHTS_DIR / "yolo5_ball.pt"
YOLOV8N_PERSON = WEIGHTS_DIR / "yolov8n.pt"  # downloaded by ultralytics on first use

# Python venv with CUDA torch + ultralytics installed
PYTHON_BIN = os.environ.get(
    "BREAKPOINT_PYTHON",
    "C:/Users/xinyi/AppData/Local/Temp/breakpoint/venv312/Scripts/python.exe",
)


def assert_ready() -> None:
    """Raise informative errors if any external dep is missing."""
    if not Path(FFMPEG).exists() and not shutil.which(FFMPEG):
        raise RuntimeError(f"ffmpeg not found: {FFMPEG} (set BREAKPOINT_FFMPEG)")
    if not YOLOV5_BALL.exists():
        raise RuntimeError(f"YOLOv5 ball weights missing: {YOLOV5_BALL}")
