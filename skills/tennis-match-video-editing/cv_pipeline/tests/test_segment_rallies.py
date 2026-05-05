from cv_pipeline.segment_rallies import (
    find_continuous_runs, count_hits_in_run, segment, RallyParams,
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
    import json
    data = json.loads(out.read_text())
    assert len(data["rallies"]) == 1
    r = data["rallies"][0]
    assert r["n_hits"] >= 3
    assert r["match_type"] == "unknown"  # no players csv
    assert r["kept"] is True
