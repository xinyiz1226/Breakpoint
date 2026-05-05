import json

from cv_pipeline.segment_rallies import (
    find_continuous_runs, count_hits_in_run, segment, RallyParams,
    filter_too_long, filter_too_dense, resolve_overlaps,
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


def test_filter_too_dense_drops_warmup():
    rallies = [
        {"id": "R001", "start_t": 0.0, "end_t": 10.0, "n_hits": 8, "score": 4.0,    # 0.8 hits/s — OK
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
        {"id": "R002", "start_t": 20.0, "end_t": 50.0, "n_hits": 100, "score": 50.0, # 3.3 hits/s — warm-up
         "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
    ]
    out = filter_too_dense(rallies, max_hits_per_s=1.5)
    assert len(out) == 1
    assert out[0]["id"] == "R001"


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
