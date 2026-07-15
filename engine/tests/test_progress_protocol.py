import json

import numpy as np

from engine import pipeline


def test_vision_progress_starts_before_first_segment(tmp_path, monkeypatch, capsys):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake")

    points = [
        {"start": 1.0, "end": 5.0, "hit_times": [1.2, 2.0, 3.1, 4.2], "hit_energies": [1, 2, 3, 4]},
        {"start": 10.0, "end": 14.0, "hit_times": [10.2, 11.0, 12.1, 13.2], "hit_energies": [1, 2, 3, 4]},
    ]

    monkeypatch.setattr(pipeline, "extract_audio", lambda *_args, **_kwargs: str(tmp_path / "audio.wav"))
    monkeypatch.setattr(pipeline, "detect_hits", lambda *_args, **_kwargs: (np.array([1, 2]), np.array([1, 2]), 22050))
    monkeypatch.setattr(pipeline, "segment_points", lambda *_args, **_kwargs: points)
    monkeypatch.setattr(pipeline, "rank_points", lambda pts, vision_data=None: [
        {**p, "features": {"hit_count": len(p["hit_times"])}, "score": 1.0}
        for p in pts
    ])

    from engine.vision import player_motion

    monkeypatch.setattr(player_motion, "select_rois", lambda *_args, **_kwargs: {"near": [], "far": []})

    def fake_analyze_motion(_video_path, segments, _rois, progress_callback=None):
        if progress_callback:
            progress_callback(1, len(segments))
            progress_callback(2, len(segments))
        return [{"player_motion_max": 0.1, "player_motion_var": 0.0} for _ in segments]

    monkeypatch.setattr(player_motion, "analyze_motion", fake_analyze_motion)

    from engine.vision import player_identity

    monkeypatch.setattr(
        player_identity,
        "analyze_player_identities",
        lambda _video_path, segments, _rois: [
            {"players": {"player_1": {"detected": False}, "player_2": {"detected": False}}}
            for _ in segments
        ],
    )

    pipeline.run_analysis(str(video_path), output_dir=str(tmp_path / "out"), json_progress=True)

    messages = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    progress_messages = [message for message in messages if message["type"] == "progress"]

    assert progress_messages[0] == {"type": "progress", "step": 3.5, "current": 0, "sub_total": 2}
    assert [message["current"] for message in progress_messages] == [0, 1, 2]

    report = json.loads((tmp_path / "out" / "full_report.json").read_text())
    assert report[0]["analysis_version"] == 2
    assert report[0]["player_identity_status"] == "complete"


def test_court_detection_fallback_report_is_versioned(tmp_path, monkeypatch):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake")
    points = [{
        "start": 1.0,
        "end": 5.0,
        "hit_times": [1.2, 2.0, 3.1, 4.2],
        "hit_energies": [1, 2, 3, 4],
    }]

    monkeypatch.setattr(pipeline, "extract_audio", lambda *_args, **_kwargs: str(tmp_path / "audio.wav"))
    monkeypatch.setattr(pipeline, "detect_hits", lambda *_args, **_kwargs: (np.array([1]), np.array([1]), 22050))
    monkeypatch.setattr(pipeline, "segment_points", lambda *_args, **_kwargs: points)

    from engine.vision import player_motion

    monkeypatch.setattr(player_motion, "select_rois", lambda *_args, **_kwargs: None)
    pipeline.run_analysis(str(video_path), output_dir=str(tmp_path / "out"))

    report = json.loads((tmp_path / "out" / "full_report.json").read_text())
    assert report[0]["analysis_version"] == 2
    assert report[0]["player_identity_status"] == "skipped_court_detection"
    assert "players" not in report[0]