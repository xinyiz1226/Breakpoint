import numpy as np
import pytest
from engine.segmentation import segment_points
from engine.ranking import rank_points, compute_features, normalize


class TestSegmentPoints:
    def test_empty_input(self):
        assert segment_points(np.array([]), np.array([])) == []

    def test_too_few_hits(self):
        times = np.array([1.0, 2.0, 3.0])
        energies = np.array([0.5, 0.5, 0.5])
        assert segment_points(times, energies, min_hit_count=4) == []

    def test_single_rally(self):
        times = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        energies = np.array([0.5, 0.6, 0.7, 0.6, 0.5])
        points = segment_points(times, energies, silence_gap=6.0)
        assert len(points) == 1
        assert points[0]["start"] < times[0]
        assert points[0]["end"] > times[-1]
        assert len(points[0]["hit_times"]) == 5

    def test_two_rallies_split_by_silence(self):
        times = np.array([10.0, 11.0, 12.0, 13.0, 14.0,
                          30.0, 31.0, 32.0, 33.0, 34.0])
        energies = np.ones(10)
        points = segment_points(times, energies, silence_gap=6.0)
        assert len(points) == 2
        assert points[0]["end"] < points[1]["start"]

    def test_short_rally_filtered(self):
        times = np.array([10.0, 10.5, 11.0, 11.5, 12.0])
        energies = np.ones(5)
        points = segment_points(times, energies, min_duration=10.0)
        assert len(points) == 0

    def test_split_oversized_segment(self):
        times = np.array([0, 1, 2, 3, 4, 5, 10, 15, 20, 25, 30, 35, 40.0])
        energies = np.ones(len(times))
        points = segment_points(times, energies, silence_gap=50, max_duration=25, min_hit_count=2)
        assert len(points) >= 2

    def test_total_duration_clamps_end(self):
        times = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        energies = np.ones(5)
        points = segment_points(times, energies, total_duration=14.5)
        assert len(points) == 1
        assert points[0]["end"] <= 14.5


class TestRankPoints:
    def _make_point(self, start, end, n_hits=6):
        times = np.linspace(start + 0.5, end - 0.5, n_hits).tolist()
        return {
            "start": start,
            "end": end,
            "hit_times": times,
            "hit_energies": [0.5] * n_hits,
        }

    def test_empty(self):
        assert rank_points([]) == []

    def test_single_point(self):
        ranked = rank_points([self._make_point(0, 10)])
        assert len(ranked) == 1
        assert "score" in ranked[0]
        assert "features" in ranked[0]

    def test_sorted_descending(self):
        p1 = self._make_point(0, 10, n_hits=4)
        p2 = self._make_point(20, 30, n_hits=10)
        ranked = rank_points([p1, p2])
        assert ranked[0]["score"] >= ranked[1]["score"]
        assert ranked[0]["features"]["hit_count"] == 10

    def test_with_vision_data(self):
        points = [self._make_point(0, 10), self._make_point(20, 30)]
        vision = [
            {"player_motion_max": 100.0, "player_motion_var": 50.0},
            {"player_motion_max": 10.0, "player_motion_var": 5.0},
        ]
        ranked = rank_points(points, vision_data=vision)
        assert ranked[0]["features"]["player_motion_max"] == 100.0

    def test_preserves_player_identity_data(self):
        players = {
            "player_1": {"detected": True, "side": "near"},
            "player_2": {"detected": True, "side": "far"},
        }
        ranked = rank_points(
            [self._make_point(0, 10)],
            vision_data=[{
                "player_motion_max": 1.0,
                "player_motion_var": 0.1,
                "players": players,
            }],
        )

        assert ranked[0]["players"] == players


class TestComputeFeatures:
    def test_single_hit(self):
        p = {"start": 0, "end": 5, "hit_times": [2.0], "hit_energies": [0.8]}
        f = compute_features(p)
        assert f["hit_count"] == 1
        assert f["duration"] == 5

    def test_with_vision(self):
        p = {"start": 0, "end": 5, "hit_times": [1.0, 2.0], "hit_energies": [0.5, 0.6]}
        v = {"player_motion_max": 42.0, "player_motion_var": 7.0}
        f = compute_features(p, vision=v)
        assert f["player_motion_max"] == 42.0


class TestNormalize:
    def test_uniform(self):
        assert normalize([5.0, 5.0, 5.0]) == [0.5, 0.5, 0.5]

    def test_range(self):
        result = normalize([0.0, 5.0, 10.0])
        assert result[0] == 0.0
        assert result[2] == 1.0
