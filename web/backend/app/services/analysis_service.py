import json
import subprocess
import sys
from pathlib import Path

from app.config import settings


def run_engine_analysis(video_path: str, output_dir: str) -> list[dict]:
    engine_dir = str(Path(settings.engine_path).resolve())
    cmd = [
        sys.executable, "-m", "engine.pipeline",
        video_path,
        "--output-dir", output_dir,
        "--json-progress",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=engine_dir)
    if result.returncode != 0:
        raise RuntimeError(f"Engine failed: {result.stderr}")

    report_path = Path(output_dir) / "full_report.json"
    if not report_path.exists():
        raise RuntimeError("Engine did not produce a report")

    return json.loads(report_path.read_text())


def run_engine_export(video_path: str, segments: list[dict], output_path: str) -> str:
    engine_dir = str(Path(settings.engine_path).resolve())
    timeline_path = Path(output_path).parent / "export_timeline.json"
    timeline_path.write_text(json.dumps(segments))

    cmd = [
        sys.executable, "-m", "engine.export.compile",
        video_path,
        str(timeline_path),
        "--output", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=engine_dir)
    if result.returncode != 0:
        raise RuntimeError(f"Export failed: {result.stderr}")
    return output_path
