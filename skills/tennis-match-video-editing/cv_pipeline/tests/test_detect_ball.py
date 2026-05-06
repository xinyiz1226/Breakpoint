from cv_pipeline.detect_ball import filter_jumps, filter_static_detections


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


def test_filter_static_drops_long_static_run():
    """30+ consecutive frames at the same position get dropped (false positive)."""
    rows = (
        # 5 normal frames
        [(i, 100.0 + i * 10, 200.0, 0.5) for i in range(5)] +
        # 30 static frames at position (500, 300) — will be dropped
        [(5 + i, 500.0 + (i % 3), 300.0 + (i % 2), 0.5) for i in range(30)] +
        # 5 more normal frames
        [(35 + i, 600.0 + i * 10, 200.0, 0.5) for i in range(5)]
    )
    out = filter_static_detections(rows, window=30, max_movement=5.0)
    # 5 + 30 + 5 = 40 input → 5 + 5 = 10 output (the 30 static dropped)
    frames_out = [r[0] for r in out]
    # The static block 5..34 should be dropped
    for f in range(5, 35):
        assert f not in frames_out, f"frame {f} should be dropped (static)"
    # The non-static frames should remain
    for f in [0, 1, 2, 3, 4, 35, 36, 37, 38, 39]:
        assert f in frames_out


def test_filter_static_keeps_moving_ball():
    """Ball moving 10+ px per frame is never marked static."""
    rows = [(i, 100.0 + i * 10, 200.0 + i * 5, 0.5) for i in range(40)]
    out = filter_static_detections(rows, window=30, max_movement=5.0)
    assert len(out) == 40


def test_filter_static_short_run_kept():
    """A static run shorter than window stays."""
    rows = [(i, 500.0, 300.0, 0.5) for i in range(20)]  # 20 < 30 window
    out = filter_static_detections(rows, window=30, max_movement=5.0)
    assert len(out) == 20

