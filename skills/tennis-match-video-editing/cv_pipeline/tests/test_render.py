import json
import subprocess

from cv_pipeline import render
from cv_pipeline import paths


def test_render_cuts_concats_kept_segments_only(data_dir, tmp_job_dir):
    src = data_dir / "tiny_5s_clip.mp4"
    segments = {
        "fps": 30.0,
        "rallies": [
            {"id": "R1", "start_t": 0.5, "end_t": 1.5, "n_hits": 5, "score": 1.0,
             "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
            {"id": "R2", "start_t": 2.0, "end_t": 2.5, "n_hits": 3, "score": 0.5,
             "match_type": "singles", "kept": False, "max_ball_speed_kmh": 0.0},
            {"id": "R3", "start_t": 3.5, "end_t": 4.5, "n_hits": 4, "score": 0.8,
             "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
        ],
    }
    seg_path = tmp_job_dir / "segments.json"
    seg_path.write_text(json.dumps(segments))
    out = tmp_job_dir / "highlight.mp4"

    render.render(src, seg_path, out, mode="highlight")

    # ffprobe duration; expected ≈ 1.0 + 1.0 = 2.0s ± 0.5s
    r = subprocess.run(
        [paths.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True,
    )
    duration = float(r.stdout.strip())
    assert 1.5 <= duration <= 2.5
