import subprocess
import shutil


def run_ffmpeg(cmd: list[str]):
    if not shutil.which(cmd[0]):
        raise RuntimeError(
            f"'{cmd[0]}' not found. Install ffmpeg and ensure it's on your PATH.\n"
            f"  https://ffmpeg.org/download.html"
        )
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace").strip()
        raise RuntimeError(
            f"ffmpeg failed (exit {e.returncode}):\n"
            f"  Command: {' '.join(cmd[:6])}{'...' if len(cmd) > 6 else ''}\n"
            f"  {stderr[-500:]}"
        ) from None
