"""
E2E test: simulate what the desktop app does to analyze a video.

Spawns `python -m engine.pipeline <video> --json-progress` (same command as
pythonBridge.ts), parses the JSON-line protocol, and verifies the output
directory + report are created correctly.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_DIR = REPO_ROOT / "tests"
SAMPLE_VIDEO = TESTS_DIR / "DJI_20260503142617_0532_D.MP4"


@pytest.fixture
def output_dir():
    out = SAMPLE_VIDEO.parent / f"output_{SAMPLE_VIDEO.stem}"
    if out.exists():
        shutil.rmtree(out)
    yield out
    if out.exists():
        shutil.rmtree(out)


@pytest.mark.skipif(not SAMPLE_VIDEO.exists(), reason="sample video not present")
def test_app_analysis_e2e(output_dir):
    """Reproduce the exact spawn the desktop app performs."""
    cmd = [sys.executable, "-m", "engine.pipeline", str(SAMPLE_VIDEO), "--json-progress"]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert proc.returncode == 0, f"Process failed (code {proc.returncode}):\n{proc.stderr}"

    messages = []
    for line in proc.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    types = [m["type"] for m in messages]
    assert "step" in types, "no 'step' messages received"
    assert "complete" in types, "no 'complete' message received"

    complete_msg = next(m for m in messages if m["type"] == "complete")
    assert "report_path" in complete_msg
    assert complete_msg["segment_count"] > 0

    assert output_dir.exists(), "output directory was not created"
    assert (output_dir / "audio.wav").exists(), "audio.wav not generated"

    report_path = output_dir / "full_report.json"
    assert report_path.exists(), "full_report.json not generated"

    report = json.loads(report_path.read_text())
    assert len(report) == complete_msg["segment_count"]

    first = report[0]
    for key in ("index", "start", "end", "score", "features"):
        assert key in first, f"missing key '{key}' in report segment"
    assert first["end"] > first["start"]
    assert first["score"] > 0


@pytest.mark.skipif(not SAMPLE_VIDEO.exists(), reason="sample video not present")
def test_app_analysis_no_vision(output_dir):
    """Same as above but with --no-vision flag."""
    cmd = [
        sys.executable, "-m", "engine.pipeline",
        str(SAMPLE_VIDEO), "--json-progress", "--no-vision",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert proc.returncode == 0, f"Process failed (code {proc.returncode}):\n{proc.stderr}"

    messages = []
    for line in proc.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    step_labels = [m.get("label") for m in messages if m["type"] == "step"]
    assert "Analyzing player motion" not in step_labels, \
        "vision step should not run with --no-vision"
    assert any(m["type"] == "complete" for m in messages)

    report = json.loads((output_dir / "full_report.json").read_text())
    assert len(report) > 0
    for seg in report:
        assert "player_motion_max" not in seg.get("features", {}), \
            "vision features should not be present with --no-vision"


@pytest.mark.skipif(not SAMPLE_VIDEO.exists(), reason="sample video not present")
def test_invalid_flag_rejected():
    """Ensure unknown flags (like the old --no-compile) fail clearly."""
    cmd = [
        sys.executable, "-m", "engine.pipeline",
        str(SAMPLE_VIDEO), "--json-progress", "--no-compile",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode != 0, "--no-compile should be rejected by argparse"
