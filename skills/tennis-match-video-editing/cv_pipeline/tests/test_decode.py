import json

from cv_pipeline import decode


def test_probe_writes_meta_json(data_dir, tmp_job_dir):
    src = data_dir / "tiny_5s_clip.mp4"
    out = tmp_job_dir / "meta.json"

    decode.probe(src, out)

    meta = json.loads(out.read_text())
    assert meta["w"] == 640
    assert meta["h"] == 360
    assert 29.0 <= meta["fps"] <= 31.0
    assert 145 <= meta["n_frames"] <= 155  # 5s @ 30fps ≈ 150
    assert meta["duration"] > 4.5
