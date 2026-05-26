# Desktop MSI Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `python desktop\scripts\package.py` build the Python engine, build the Electron desktop app, and produce a verified MSI in one run.

**Architecture:** Keep `build_engine.py` focused on PyInstaller and move orchestration into `desktop/scripts/package.py`. The packaging script will use small helper functions for command execution, dependency checks, cache preparation, artifact validation, and MSI output selection.

**Tech Stack:** Python 3, PyInstaller, npm, Electron Builder, WiX MSI target, Windows PowerShell/cmd compatibility.

---

## File Structure

- Modify `desktop/scripts/package.py`: replace the current two-command wrapper with a robust one-shot MSI pipeline.
- Modify `desktop/package.json`: add a script that invokes the Python packager, without changing existing `build` behavior.
- No production app code changes are required.

---

### Task 1: Replace package.py with a robust packaging pipeline

**Files:**
- Modify: `desktop/scripts/package.py`

- [ ] **Step 1: Replace the imports and constants**

Replace the whole file with this implementation:

```python
"""
Full packaging pipeline: build Python engine + Electron MSI installer.
Run from anywhere: python desktop/scripts/package.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DESKTOP_DIR = PROJECT_ROOT / "desktop"
ENGINE_EXE = PROJECT_ROOT / "dist-engine" / "TennisHighlightAnalysis" / "TennisHighlightAnalysis.exe"
FFMPEG_EXE = PROJECT_ROOT / "dist-engine" / "ffmpeg" / "ffmpeg.exe"
DEFAULT_WINDOWS_OUTPUT = Path("C:/bp-msi")
DEFAULT_OUTPUT = DESKTOP_DIR / "release-msi"
WIN_CODE_SIGN_CACHE = Path.home() / "AppData" / "Local" / "electron-builder" / "Cache" / "winCodeSign"
WIN_CODE_SIGN_VERSION_DIR = "winCodeSign-2.6.0"
```

- [ ] **Step 2: Add command and tool helpers**

Add these functions below the constants:

```python
def is_windows() -> bool:
    return os.name == "nt"


def npm_command() -> str:
    return "npm.cmd" if is_windows() else "npm"


def npx_command() -> str:
    return "npx.cmd" if is_windows() else "npx"


def run(cmd: list[str], cwd: Path, label: str, env: dict[str, str] | None = None) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}\n")
    print(f"Running: {' '.join(cmd)}")

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    result = subprocess.run(cmd, cwd=str(cwd), env=merged_env)
    if result.returncode != 0:
        raise SystemExit(f"\nFAILED: {label} exited with code {result.returncode}")


def require_file(path: Path, message: str) -> None:
    if not path.exists():
        raise SystemExit(f"{message}\nExpected path: {path}")
```

- [ ] **Step 3: Add dependency installation and engine validation helpers**

Add these functions below `require_file`:

```python
def ensure_node_dependencies() -> None:
    node_modules = DESKTOP_DIR / "node_modules"
    if node_modules.exists():
        print(f"Node dependencies already installed: {node_modules}")
        return

    run(
        [npm_command(), "ci"],
        cwd=DESKTOP_DIR,
        label="Installing desktop dependencies",
    )


def build_engine() -> None:
    run(
        [sys.executable, str(DESKTOP_DIR / "scripts" / "build_engine.py")],
        cwd=PROJECT_ROOT,
        label="Step 1/3: Building Python engine",
    )
    require_file(
        ENGINE_EXE,
        "Python engine build completed, but the packaged engine executable was not found.",
    )
    require_file(
        FFMPEG_EXE,
        "ffmpeg.exe is required in dist-engine/ffmpeg before packaging the desktop app.",
    )
```

- [ ] **Step 4: Add winCodeSign cache preparation**

Add this function below `build_engine`:

```python
def prepare_win_code_sign_cache() -> None:
    if not is_windows() or not WIN_CODE_SIGN_CACHE.exists():
        return

    target = WIN_CODE_SIGN_CACHE / WIN_CODE_SIGN_VERSION_DIR
    if (target / "windows-10").exists() and (target / "rcedit-x64.exe").exists():
        print(f"winCodeSign cache already prepared: {target}")
        return

    candidates = [
        path
        for path in WIN_CODE_SIGN_CACHE.iterdir()
        if path.is_dir()
        and path.name != WIN_CODE_SIGN_VERSION_DIR
        and (path / "windows-10").exists()
        and (path / "rcedit-x64.exe").exists()
    ]
    if not candidates:
        return

    source = max(candidates, key=lambda item: item.stat().st_mtime)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    print(f"Prepared winCodeSign cache: {target}")
```

- [ ] **Step 5: Add Electron build, MSI packaging, and artifact verification**

Add these functions below `prepare_win_code_sign_cache`:

```python
def build_desktop() -> None:
    run(
        [npm_command(), "run", "build"],
        cwd=DESKTOP_DIR,
        label="Step 2/3: Building Electron desktop app",
    )


def package_msi(output_dir: Path) -> None:
    prepare_win_code_sign_cache()
    env = {"CSC_IDENTITY_AUTO_DISCOVERY": "false"}
    run(
        [
            npx_command(),
            "electron-builder",
            "--config",
            "electron-builder.yml",
            "--win",
            "msi",
            f"--config.directories.output={output_dir}",
        ],
        cwd=DESKTOP_DIR,
        label="Step 3/3: Building MSI installer",
        env=env,
    )


def verify_msi(output_dir: Path) -> Path:
    installers = sorted(output_dir.glob("*.msi"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not installers:
        raise SystemExit(f"MSI build finished but no .msi file was found in: {output_dir}")

    installer = installers[0]
    size_mb = installer.stat().st_size / (1024 * 1024)
    print(f"\n{'=' * 60}")
    print("  Done")
    print(f"{'=' * 60}")
    print(f"MSI: {installer}")
    print(f"Size: {size_mb:.1f} MB")
    return installer
```

- [ ] **Step 6: Add argument parsing and main**

Add these functions at the bottom of the file:

```python
def parse_args() -> argparse.Namespace:
    default_output = DEFAULT_WINDOWS_OUTPUT if is_windows() else DEFAULT_OUTPUT
    parser = argparse.ArgumentParser(description="Build the Breakpoint desktop MSI installer.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output,
        help=f"Directory for Electron Builder output. Default: {default_output}",
    )
    parser.add_argument(
        "--skip-engine",
        action="store_true",
        help="Reuse the existing dist-engine output instead of rebuilding it.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()

    ensure_node_dependencies()
    if args.skip_engine:
        require_file(ENGINE_EXE, "Cannot skip engine build because the engine executable is missing.")
        require_file(FFMPEG_EXE, "Cannot skip engine build because ffmpeg.exe is missing.")
    else:
        build_engine()
    build_desktop()
    package_msi(output_dir)
    verify_msi(output_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the script with existing engine output for a fast first check**

Run:

```powershell
python desktop\scripts\package.py --skip-engine
```

Expected: command exits 0 and prints an MSI path under `C:\bp-msi`.

- [ ] **Step 8: Commit**

Run:

```powershell
git add desktop\scripts\package.py
git commit -m "build: make desktop msi packaging one-shot" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Add a package:msi npm shortcut

**Files:**
- Modify: `desktop/package.json`

- [ ] **Step 1: Add a script entry**

In `desktop/package.json`, change the `scripts` block from:

```json
"scripts": {
  "dev": "vite",
  "test:renderer-flow": "node scripts/renderer-flow.test.mjs",
  "build": "tsc && vite build",
  "preview": "vite preview",
  "package": "npm run build && electron-builder --config electron-builder.yml --win"
}
```

to:

```json
"scripts": {
  "dev": "vite",
  "test:renderer-flow": "node scripts/renderer-flow.test.mjs",
  "build": "tsc && vite build",
  "preview": "vite preview",
  "package": "npm run build && electron-builder --config electron-builder.yml --win",
  "package:msi": "python scripts/package.py"
}
```

- [ ] **Step 2: Verify JSON is valid**

Run:

```powershell
node -e "JSON.parse(require('fs').readFileSync('desktop/package.json','utf8')); console.log('package.json ok')"
```

Expected: `package.json ok`

- [ ] **Step 3: Commit**

Run:

```powershell
git add desktop\package.json
git commit -m "build: add msi package shortcut" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Full verification

**Files:**
- No new files.

- [ ] **Step 1: Run the one-shot packager**

Run:

```powershell
python desktop\scripts\package.py
```

Expected: command exits 0 and prints `MSI: C:\bp-msi\Breakpoint 0.1.6.msi`.

- [ ] **Step 2: Verify the MSI artifact**

Run:

```powershell
Get-Item 'C:\bp-msi\Breakpoint 0.1.6.msi' | Select-Object FullName,Length,LastWriteTime | Format-List
```

Expected: output includes `FullName : C:\bp-msi\Breakpoint 0.1.6.msi` and a non-zero `Length`.

- [ ] **Step 3: Check git status**

Run:

```powershell
git --no-pager status --short
```

Expected: only expected ignored/untracked build artifacts are present; no accidental source changes are left unstaged.
