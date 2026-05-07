import json

from cv_pipeline.segment_rallies import (
    find_continuous_runs, find_density_runs, count_hits_in_run, segment,
    RallyParams, filter_too_long, resolve_overlaps, filter_narrow_y_range,
)


def test_find_continuous_runs_synthetic(data_dir):
    csv_path = data_dir / "synthetic_ball_one_rally.csv"
    runs = find_continuous_runs(csv_path, min_run_frames=90)
    assert len(runs) == 1
    start, end = runs[0]
    assert 25 <= start <= 35
    assert 175 <= end <= 185


def test_no_rally_returns_empty(data_dir):
    csv_path = data_dir / "synthetic_ball_no_rally.csv"
    runs = find_continuous_runs(csv_path, min_run_frames=90)
    assert runs == []


def test_count_hits_triangular_wave(data_dir):
    csv_path = data_dir / "synthetic_ball_one_rally.csv"
    runs = find_continuous_runs(csv_path, min_run_frames=90)
    n_hits = count_hits_in_run(csv_path, runs[0], min_frames_between=10)
    assert n_hits >= 4


def test_segment_full_pipeline_one_rally(data_dir, tmp_job_dir):
    out = tmp_job_dir / "segments.json"
    segment(
        ball_csv=data_dir / "synthetic_ball_one_rally.csv",
        players_csv=None,
        meta={"fps": 30.0},
        out_segments=out,
        params=RallyParams(min_run_frames=90, min_hits=3),
    )
    data = json.loads(out.read_text())
    assert len(data["rallies"]) == 1
    r = data["rallies"][0]
    assert r["n_hits"] >= 3
    assert r["match_type"] == "unknown"  # no players csv
    assert r["kept"] is True


def test_filter_too_long_drops_overlong():
    rallies = [
        {"id": "R001", "start_t": 0.0, "end_t": 25.0, "n_hits": 10, "score": 5.0,
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
        {"id": "R002", "start_t": 30.0, "end_t": 70.0, "n_hits": 50, "score": 25.0,  # 40s — too long
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
        {"id": "R003", "start_t": 80.0, "end_t": 100.0, "n_hits": 8, "score": 4.0,
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
    ]
    out = filter_too_long(rallies, max_duration_s=30.0)
    assert len(out) == 2
    assert [r["id"] for r in out] == ["R001", "R003"]


def test_resolve_overlaps_pushes_later_start():
    rallies = [
        {"id": "R001", "start_t": 0.0, "end_t": 10.0, "n_hits": 8, "score": 4.0,
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
        {"id": "R002", "start_t": 8.0, "end_t": 20.0, "n_hits": 12, "score": 6.0,  # overlaps R001
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
    ]
    out = resolve_overlaps(rallies)
    assert len(out) == 2
    assert out[1]["start_t"] == 10.0  # pushed from 8.0 to 10.0
    # Score recomputed for the new duration (12-10) * 0.2 + 12 * 0.5 = 6.4
    assert out[1]["score"] == round(12 * 0.5 + (20.0 - 10.0) * 0.2, 3)


def test_resolve_overlaps_drops_zero_length():
    rallies = [
        {"id": "R001", "start_t": 0.0, "end_t": 10.0, "n_hits": 8, "score": 4.0,
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
        {"id": "R002", "start_t": 5.0, "end_t": 9.0, "n_hits": 5, "score": 2.5,  # fully inside R001
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
    ]
    out = resolve_overlaps(rallies)
    assert len(out) == 1  # R002 dropped because pushed start (10.0) >= end (9.0)


def test_filter_narrow_y_range_drops_low_arc(tmp_path):
    """Rally with narrow y trajectory (warm-up at baseline) is dropped;
    rally with high arc (real point) is kept."""
    ball_csv = tmp_path / "ball.csv"
    fps = 60.0
    # Frames 0-149: rally A, narrow y range (500-600 = 100px)
    # Frames 200-349: rally B, wide y range (200-700 = 500px)
    lines = ["frame,t,x,y,conf"]
    for fi in range(150):
        y = 500 + 100 * (fi % 2)  # alternates 500/600
        lines.append(f"{fi},{fi/fps:.4f},400.0,{y:.1f},0.5")
    for fi in range(150, 200):
        lines.append(f"{fi},{fi/fps:.4f},,,")  # gap
    for fi in range(200, 350):
        y = 200 + 500 * (fi % 2)  # alternates 200/700
        lines.append(f"{fi},{fi/fps:.4f},400.0,{y:.1f},0.5")
    ball_csv.write_text("\n".join(lines) + "\n")

    rallies = [
        {"id": "R001", "start_t": 0.0, "end_t": 149/60.0, "n_hits": 30, "score": 15.0,
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
        {"id": "R002", "start_t": 200/60.0, "end_t": 349/60.0, "n_hits": 30, "score": 15.0,
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
    ]
    out = filter_narrow_y_range(rallies, ball_csv, fps, min_y_range_px=250.0)
    assert len(out) == 1
    assert out[0]["id"] == "R002"


def test_filter_narrow_y_range_keeps_sparse_rallies(tmp_path):
    """A rally with very few ball detections is kept (not enough data to judge)."""
    ball_csv = tmp_path / "ball.csv"
    fps = 60.0
    lines = ["frame,t,x,y,conf"]
    for fi in range(150):
        if fi % 50 == 0:  # only 3 detections in 150 frames
            lines.append(f"{fi},{fi/fps:.4f},400.0,500.0,0.5")
        else:
            lines.append(f"{fi},{fi/fps:.4f},,,")
    ball_csv.write_text("\n".join(lines) + "\n")
    rallies = [{"id": "R001", "start_t": 0.0, "end_t": 149/60.0, "n_hits": 5, "score": 3.0,
                "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0}]
    out = filter_narrow_y_range(rallies, ball_csv, fps, min_y_range_px=250.0)
    assert len(out) == 1


def test_find_density_runs_sparse_detections(tmp_path):
    """Density finder should detect rally zones even at ~5% detection rate."""
    ball_csv = tmp_path / "ball.csv"
    fps = 60.0
    lines = ["frame,t,x,y,conf"]
    import random
    rng = random.Random(42)
    det_frames = set(rng.sample(range(600), 30))
    for fi in range(600):
        if fi in det_frames:
            y = 300 + 200 * ((fi // 30) % 2)
            lines.append(f"{fi},{fi/fps:.4f},500.0,{y:.1f},0.5")
        else:
            lines.append(f"{fi},{fi/fps:.4f},,,")
    for fi in range(600, 1200):
        lines.append(f"{fi},{fi/fps:.4f},,,")
    ball_csv.write_text("\n".join(lines) + "\n")

    runs = find_density_runs(ball_csv, fps, window_s=5, threshold=0.03)
    assert len(runs) >= 1
    assert runs[0][0] < 60
    assert runs[0][1] >= 300


def test_density_fallback_in_segment(tmp_path):
    """segment() should auto-switch to density mode for low detection rate."""
    ball_csv = tmp_path / "ball.csv"
    fps = 60.0
    lines = ["frame,t,x,y,conf"]
    import random
    rng = random.Random(99)
    det_frames = sorted(rng.sample(range(1800), 54))
    for fi in range(1800):
        if fi in det_frames:
            y = 300 + 300 * (fi % 2)
            lines.append(f"{fi},{fi/fps:.4f},500.0,{y:.1f},0.5")
        else:
            lines.append(f"{fi},{fi/fps:.4f},,,")
    ball_csv.write_text("\n".join(lines) + "\n")

    out_seg = tmp_path / "segments.json"
    params = RallyParams(
        min_run_frames=90, min_hits=2,
        density_window_s=10, density_threshold=0.02,
        density_fallback_rate=0.15,
        max_rally_duration_s=60.0,
    )
    payload = segment(
        ball_csv=ball_csv, players_csv=None,
        meta={"fps": fps}, out_segments=out_seg, params=params,
    )
    assert len(payload["rallies"]) >= 1
