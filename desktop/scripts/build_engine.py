"""
Build the Python analysis engine into a standalone executable using PyInstaller.
Run from the project root: python desktop/scripts/build_engine.py
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENTRY = PROJECT_ROOT / "TennisHighlightAnalysis.py"
DIST_DIR = PROJECT_ROOT / "dist-engine"


def main():
    if not ENTRY.exists():
        print(f"Error: entry point not found: {ENTRY}")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--name", "TennisHighlightAnalysis",
        "--distpath", str(DIST_DIR),
        "--workpath", str(PROJECT_ROOT / "build-engine"),
        "--specpath", str(PROJECT_ROOT / "build-engine"),
        "--hidden-import", "librosa",
        "--hidden-import", "soundfile",
        "--hidden-import", "sklearn",
        "--hidden-import", "sklearn.utils._cython_blas",
        "--hidden-import", "scipy.signal",
        "--hidden-import", "cv2",
        "--hidden-import", "numpy",
        "--hidden-import", "phase1",
        "--hidden-import", "phase1.analyze",
        "--hidden-import", "phase1.compile",
        "--hidden-import", "phase1.compare",
        "--hidden-import", "phase2",
        "--hidden-import", "phase2.player_motion",
        "--collect-all", "librosa",
        "--collect-all", "soundfile",
        str(ENTRY),
    ]

    print(f"Running PyInstaller...")
    print(f"  Entry: {ENTRY}")
    print(f"  Output: {DIST_DIR}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print("PyInstaller build failed!")
        sys.exit(1)

    print(f"\nEngine built successfully at: {DIST_DIR / 'TennisHighlightAnalysis'}")
    print("Next: place ffmpeg.exe in dist-engine/ffmpeg/ then run electron-builder")


if __name__ == "__main__":
    main()
