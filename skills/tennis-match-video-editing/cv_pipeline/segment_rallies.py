"""Stage 4: heuristic rally segmentation.

Reads ball.csv + players.csv → writes segments.json with kept=True for all.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RallyParams:
    min_run_frames: int = 90       # ≥1.5s @ 60fps; ≥3s @ 30fps
    min_hits: int = 4              # filter rallies with < 4 hits
    min_frames_between_hits: int = 12  # avoid double-counting jitter
    pre_pad_s: float = 1.0
    post_pad_s: float = 1.5
    # static_window_s is reserved for boundary refinement (use player-stillness
    # to trim the rally end). Not used in the MVP — pre_pad_s / post_pad_s are
    # constant. Tracked as a Plan B/C tuning lever for the highlight-too-long
    # finding from Task 9 acceptance.
    static_window_s: float = 1.0


def _read_ball_csv(csv_path: Path) -> list[tuple[int, float | None, float | None]]:
    """Returns list of (frame, x_or_None, y_or_None). Order = file order."""
    rows: list[tuple[int, float | None, float | None]] = []
    with csv_path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            f_idx = int(row["frame"])
            x = float(row["x"]) if row["x"] else None
            y = float(row["y"]) if row["y"] else None
            rows.append((f_idx, x, y))
    return rows


def find_continuous_runs(ball_csv: Path, min_run_frames: int = 90,
                          max_gap: int = 10) -> list[tuple[int, int]]:
    """Return [(start_frame, end_frame), ...] for ball-visible runs.

    A "run" allows up to `max_gap` consecutive missing frames (smoothes YOLO drops).
    Run ends when gap exceeds max_gap consecutive missing frames.
    """
    rows = _read_ball_csv(ball_csv)
    runs = []
    cur_start = None
    cur_gap = 0
    last_seen = None
    for f_idx, x, y in rows:
        seen = x is not None and y is not None
        if seen:
            if cur_start is None:
                cur_start = f_idx
            cur_gap = 0
            last_seen = f_idx
        else:
            if cur_start is not None:
                cur_gap += 1
                if cur_gap > max_gap:
                    if last_seen - cur_start + 1 >= min_run_frames:
                        runs.append((cur_start, last_seen))
                    cur_start = None
                    cur_gap = 0
    if cur_start is not None and last_seen is not None:
        if last_seen - cur_start + 1 >= min_run_frames:
            runs.append((cur_start, last_seen))
    return runs


def count_hits_in_run(ball_csv: Path, run: tuple[int, int],
                      min_frames_between: int = 12) -> int:
    """Count y-direction reversals in [start, end].

    A "hit" = sign change of dy averaged over a 5-frame rolling window.
    Each hit must be >= min_frames_between frames away from the last to avoid jitter.
    """
    rows = _read_ball_csv(ball_csv)
    ys = [(f, y) for f, x, y in rows if run[0] <= f <= run[1] and y is not None]
    if len(ys) < 10:
        return 0

    # Rolling mean of y over 5 frames
    window = 5
    rolling = []
    for i in range(len(ys)):
        lo = max(0, i - window + 1)
        rolling.append(statistics.mean(y for _, y in ys[lo:i + 1]))
    deltas = [rolling[i] - rolling[i - 1] for i in range(1, len(rolling))]

    hits = 0
    last_hit_frame = -10_000
    for i in range(1, len(deltas)):
        # sign change?
        if deltas[i - 1] * deltas[i] < 0:
            cur_frame = ys[i + 1][0]
            if cur_frame - last_hit_frame >= min_frames_between:
                hits += 1
                last_hit_frame = cur_frame
    return hits


def _read_players_in_window(players_csv: Path | None,
                            f_start: int, f_end: int) -> tuple[str, list[int]]:
    """Returns (match_type, n_players_per_sample). match_type ∈ singles/doubles/unknown."""
    if players_csv is None or not players_csv.exists():
        return "unknown", []
    counts = []
    with players_csv.open() as f:
        r = csv.DictReader(f)
        for row in r:
            f_idx = int(row["frame"])
            if f_start <= f_idx <= f_end:
                counts.append(int(row["n_players"]))
    if not counts:
        return "unknown", []
    # statistics.mode in Python 3.8+ returns the smallest value when there are
    # ties (e.g. [2,2,4,4] → 2), which biases toward "singles" in ambiguous frames.
    mode = statistics.mode(counts)
    if mode == 2:
        return "singles", counts
    if mode == 4:
        return "doubles", counts
    return "unknown", counts


def segment(ball_csv: Path, players_csv: Path | None, meta: dict,
            out_segments: Path, params: RallyParams = None) -> dict:
    """Full Stage-4 pipeline. Returns the dict written to out_segments."""
    if params is None:
        params = RallyParams()
    if "fps" not in meta:
        raise ValueError(f"meta dict missing required 'fps' key (got keys: {sorted(meta)})")
    fps = float(meta["fps"])

    runs = find_continuous_runs(ball_csv, min_run_frames=params.min_run_frames)
    rallies = []
    kept_idx = 0
    for f_start, f_end in runs:
        n_hits = count_hits_in_run(
            ball_csv, (f_start, f_end),
            min_frames_between=params.min_frames_between_hits,
        )
        if n_hits < params.min_hits:
            continue
        match_type, _ = _read_players_in_window(players_csv, f_start, f_end)

        start_t = max(0.0, f_start / fps - params.pre_pad_s)
        end_t = f_end / fps + params.post_pad_s

        # Score formula: n_hits weighted highest, then duration (which includes
        # pre_pad+post_pad ≈ 2.5s of margin — small constant offset is intentional).
        # max_ball_speed_kmh placeholder for v2.
        score = (
            n_hits * 0.5
            + (end_t - start_t) * 0.2
        )

        kept_idx += 1
        rallies.append({
            "id": f"R{kept_idx:03d}",
            "start_t": round(start_t, 3),
            "end_t": round(end_t, 3),
            "n_hits": n_hits,
            "max_ball_speed_kmh": 0.0,
            "score": round(score, 3),
            "match_type": match_type,
            "kept": True,
        })

    payload = {
        "fps": fps,
        "rallies": rallies,
    }
    out_segments.parent.mkdir(parents=True, exist_ok=True)
    out_segments.write_text(json.dumps(payload, indent=2))
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ball", required=True, type=Path)
    ap.add_argument("--players", type=Path, default=None)
    ap.add_argument("--meta", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--min-run-frames", type=int, default=90)
    ap.add_argument("--min-hits", type=int, default=4)
    args = ap.parse_args()
    if args.min_run_frames <= 0:
        ap.error("--min-run-frames must be > 0")
    if args.min_hits <= 0:
        ap.error("--min-hits must be > 0")
    with open(args.meta) as f:
        meta = json.load(f)
    payload = segment(
        ball_csv=args.ball,
        players_csv=args.players,
        meta=meta,
        out_segments=args.out,
        params=RallyParams(min_run_frames=args.min_run_frames, min_hits=args.min_hits),
    )
    print(f"  {len(payload['rallies'])} rallies kept")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
