# -*- coding: utf-8 -*-
# 
# Copyright (C) 2026 Zhang Xinyi <xinyi.zhang@outlook.com>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import numpy as np


def _trim_sparse_head(hit_times_seg, avg_gap_threshold=3.0):
    """Find the index where dense hitting starts.

    If the first few hits have gaps much larger than the rest,
    skip them — they're likely from an adjacent court.
    """
    n = len(hit_times_seg)
    if n < 4:
        return 0

    gaps = [hit_times_seg[i] - hit_times_seg[i - 1] for i in range(1, n)]
    median_gap = float(np.median(gaps))
    if median_gap <= 0:
        return 0

    trim_idx = 0
    for i, g in enumerate(gaps):
        if g > median_gap * avg_gap_threshold:
            trim_idx = i + 1
        else:
            break

    return trim_idx


def segment_points(
    hit_times: np.ndarray,
    hit_energies: np.ndarray,
    silence_gap: float = 6.0,
    buffer: float = 1.5,
    min_duration: float = 4.0,
    max_duration: float = 25.0,
    min_hit_count: int = 4,
    total_duration: float | None = None,
) -> list[dict]:
    """Segment hits into individual points/rallies.

    Returns list of dicts with keys: start, end, hit_times, hit_energies.
    """
    if len(hit_times) == 0:
        return []

    segments = []
    seg_start_idx = 0

    for i in range(1, len(hit_times)):
        if hit_times[i] - hit_times[i - 1] >= silence_gap:
            segments.append((seg_start_idx, i))
            seg_start_idx = i
    segments.append((seg_start_idx, len(hit_times)))

    # Split oversized segments at the largest internal gap
    refined = []
    for start_idx, end_idx in segments:
        _split_segment(hit_times, start_idx, end_idx, max_duration, buffer, refined)

    points = []
    for start_idx, end_idx in refined:
        # Trim sparse leading hits (likely from adjacent court)
        trim = _trim_sparse_head(hit_times[start_idx:end_idx])
        start_idx += trim

        if end_idx - start_idx < min_hit_count:
            continue

        t_start = max(0, hit_times[start_idx] - buffer)
        t_end = hit_times[end_idx - 1] + buffer
        if total_duration is not None:
            t_end = min(t_end, total_duration)

        if t_end - t_start < min_duration:
            continue

        points.append({
            "start": round(float(t_start), 2),
            "end": round(float(t_end), 2),
            "hit_times": hit_times[start_idx:end_idx].tolist(),
            "hit_energies": hit_energies[start_idx:end_idx].tolist(),
        })

    return points


def _split_segment(hit_times, start_idx, end_idx, max_duration, buffer, out):
    duration = hit_times[end_idx - 1] - hit_times[start_idx] + 2 * buffer
    if duration <= max_duration or end_idx - start_idx < 2:
        out.append((start_idx, end_idx))
        return
    # Find the largest gap within this segment to split on
    best_gap_idx = start_idx + 1
    best_gap = 0
    for i in range(start_idx + 1, end_idx):
        gap = hit_times[i] - hit_times[i - 1]
        if gap > best_gap:
            best_gap = gap
            best_gap_idx = i
    _split_segment(hit_times, start_idx, best_gap_idx, max_duration, buffer, out)
    _split_segment(hit_times, best_gap_idx, end_idx, max_duration, buffer, out)


if __name__ == "__main__":
    import json, sys
    from engine.audio.detect_hits import detect_hits
    if len(sys.argv) < 2:
        print("Usage: python segment_points.py <audio_path>")
        sys.exit(1)
    times, energies, sr = detect_hits(sys.argv[1])
    points = segment_points(times, energies)
    print(f"Found {len(points)} points/rallies")
    for i, p in enumerate(points):
        dur = p["end"] - p["start"]
        print(f"  Point {i+1}: {p['start']:.1f}s - {p['end']:.1f}s ({dur:.1f}s, {len(p['hit_times'])} hits)")
