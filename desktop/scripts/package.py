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
