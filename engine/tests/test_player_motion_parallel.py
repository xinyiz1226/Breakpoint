"""Parity and progress tests for analyze_motion speedups."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_DIR = REPO_ROOT / "tests"
SAMPLE_VIDEO = TESTS_DIR / "DJI_20260503142617_0532_D.MP4"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytestmark = pytest.mark.skipif(
    not SAMPLE_VIDEO.exists(),
    reason="sample video not present",
)


def _prep_segments_and_rois():
    from engine.audio.extract import extract_audio
    from engine.audio.detect_hits import detect_hits
    from engine.segmentation import segment_points
    from engine.vision.player_motion import select_rois

    audio_path = str(SAMPLE_VIDEO.with_suffix(".wav"))
    extract_audio(str(SAMPLE_VIDEO), audio_path)
    hit_times, hit_energies, _ = detect_hits(audio_path)
    points = segment_points(hit_times, hit_energies, silence_gap=6.0, buffer=1.5)
    rois = select_rois(str(SAMPLE_VIDEO))
    if rois is None:
        pytest.skip("court auto-detection failed on sample video")
    return points[:6], rois


def test_roi_cache_is_built_once_per_run(monkeypatch):
    from engine.vision import player_motion as pm

    segments, rois = _prep_segments_and_rois()

    calls = {"count": 0}
    real_make = pm._make_polygon_mask

    def counting_make(shape, polygon):
        calls["count"] += 1
        return real_make(shape, polygon)

    monkeypatch.setattr(pm, "_make_polygon_mask", counting_make)

    pm.analyze_motion(str(SAMPLE_VIDEO), segments, rois, _force_workers=1)

    assert calls["count"] == 2, (
        f"_make_polygon_mask should be called exactly twice (near + far) per "
        f"analyze_motion run when masks are cached; got {calls['count']}"
    )
