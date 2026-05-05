from cv_pipeline.detect_ball import filter_jumps


def test_filter_jumps_drops_isolated_outlier():
    # frame, x, y; middle frame is a 300px jump from neighbors
    raw = [
        (0, 100.0, 100.0, 0.5),
        (1, 105.0, 102.0, 0.5),
        (2, 500.0, 400.0, 0.5),  # outlier
        (3, 110.0, 105.0, 0.5),
        (4, 115.0, 108.0, 0.5),
    ]
    out = filter_jumps(raw, max_jump=200.0)
    frames_out = [r[0] for r in out]
    assert 2 not in frames_out
    assert frames_out == [0, 1, 3, 4]


def test_filter_jumps_keeps_smooth_trajectory():
    raw = [(i, 100.0 + i * 10, 100.0, 0.5) for i in range(10)]
    out = filter_jumps(raw, max_jump=200.0)
    assert len(out) == 10
