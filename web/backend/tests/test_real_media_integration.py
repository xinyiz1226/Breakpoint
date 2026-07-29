from __future__ import annotations

import os
import subprocess

import pytest

from app.services.media_tools import RealMediaTools


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("BREAKPOINT_RUN_MEDIA_INTEGRATION") != "1",
    reason="set BREAKPOINT_RUN_MEDIA_INTEGRATION=1 to run real ffmpeg/engine integration",
)
def test_real_small_video_engine_integration(tmp_path, test_settings) -> None:
    source = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=320x180:d=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=800:duration=4",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    tools = RealMediaTools(test_settings)
    probe = tools.probe(source)
    output_dir = tmp_path / "analysis"
    output_dir.mkdir()
    report = tools.analyze(
        source,
        output_dir,
        cancelled=lambda: False,
        progress=lambda event: None,
    )
    assert probe.duration_seconds > 0
    assert report.exists()
