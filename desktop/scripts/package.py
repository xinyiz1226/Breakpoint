"""
Full packaging pipeline: build Python engine + Electron installer.
Run from anywhere: python desktop/scripts/package.py
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DESKTOP_DIR = PROJECT_ROOT / "desktop"


def run(cmd: list[str], cwd: Path, label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=str(cwd), shell=True)
    if result.returncode != 0:
        print(f"\nFAILED: {label}")
        sys.exit(1)


def main():
    run(
        [sys.executable, str(DESKTOP_DIR / "scripts" / "build_engine.py")],
        cwd=PROJECT_ROOT,
        label="Step 1/2: Building Python engine (PyInstaller)",
    )

    run(
        ["npm", "run", "package"],
        cwd=DESKTOP_DIR,
        label="Step 2/2: Building Electron installer",
    )

    print(f"\n{'='*60}")
    print(f"  Done! Installer at: {DESKTOP_DIR / 'release'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
