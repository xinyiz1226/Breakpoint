"""One-shot env check. Run before Task 2.

Usage:
    python -m skills.tennis-match-video-editing.cv_pipeline.check_env
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from . import paths


def main() -> int:
    failures = []

    # ffmpeg / ffprobe
    for label, binpath in (("ffmpeg", paths.FFMPEG), ("ffprobe", paths.FFPROBE)):
        resolved = binpath if Path(binpath).exists() else shutil.which(binpath)
        if not resolved:
            failures.append(f"{label} not found: {binpath}")
        else:
            r = subprocess.run([resolved, "-version"], capture_output=True, text=True)
            print(f"  {label}: {r.stdout.splitlines()[0]}")

    # weights
    if paths.YOLOV5_BALL.exists():
        size_mb = paths.YOLOV5_BALL.stat().st_size / 1e6
        print(f"  YOLOv5 ball weights: {paths.YOLOV5_BALL} ({size_mb:.1f} MB)")
    else:
        failures.append(f"YOLOv5 ball weights missing: {paths.YOLOV5_BALL}")

    # torch + cuda
    try:
        import torch
        cuda = torch.cuda.is_available()
        dev = torch.cuda.get_device_name(0) if cuda else "none"
        print(f"  torch: {torch.__version__} cuda={cuda} device={dev}")
        if not cuda:
            failures.append(
                "CUDA torch not installed. Install with:\n"
                "  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124"
            )
    except ImportError:
        failures.append("torch not installed")

    # ultralytics
    try:
        import ultralytics
        print(f"  ultralytics: {ultralytics.__version__}")
    except ImportError:
        failures.append("ultralytics not installed (pip install ultralytics)")

    if failures:
        print()
        print("FAIL — fix the following before continuing:")
        for f in failures:
            print(f"  • {f}")
        return 1
    print()
    print("OK — environment ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
