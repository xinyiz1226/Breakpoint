from cv_pipeline.detect_players import filter_persons


def test_filter_persons_keeps_lower_half_only():
    # bbox = (x1, y1, x2, y2, conf), frame is 1080 tall
    persons = [
        (100, 100, 150, 200, 0.9),   # upper half — reject (spectator)
        (100, 600, 180, 900, 0.9),   # lower half — keep
        (300, 700, 380, 950, 0.9),   # lower half — keep
    ]
    kept = filter_persons(persons, frame_h=1080, max_n=4)
    assert len(kept) == 2
    assert (100, 600, 180, 900, 0.9) in kept


def test_filter_persons_caps_at_max_n_by_y():
    persons = [(0, y, 50, y + 100, 0.9) for y in range(600, 1100, 50)]  # 10 boxes lower half
    kept = filter_persons(persons, frame_h=1080, max_n=4)
    assert len(kept) == 4
    # should keep the lowest (largest y2)
    y2_vals = sorted([p[3] for p in kept], reverse=True)
    assert y2_vals == sorted(y2_vals, reverse=True)
