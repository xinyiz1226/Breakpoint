"""Run all 5 stages sequentially for one source video.

Usage:
    python -m cv_pipeline.run_pipeline \
        --video /path/to/source.mp4 \
        --job-dir /path/to/jobs/abc123 \
        [--device 0|cpu] [--render-mode highlight|short|both]

Each stage's output goes into job-dir. Re-running a stage just overwrites its file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from . import decode, detect_ball, detect_players, segment_rallies, render
from .segment_rallies import RallyParams


def _job_id_for(video: Path) -> str:
    h = hashlib.sha1(str(video.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"{video.stem}_{h}"


def run(video: Path, job_dir: Path, device: str = "0",
        render_mode: str = "highlight",
        skip: tuple[str, ...] = ()) -> dict:
    job_dir.mkdir(parents=True, exist_ok=True)
    log_path = job_dir / "log.txt"
    log_lines = [f"=== Pipeline run @ {time.strftime('%Y-%m-%d %H:%M:%S')} ==="]

    def log(line: str) -> None:
        print(line)
        log_lines.append(line)

    timings: dict[str, float] = {}
    try:
        # Stage 1
        if "decode" not in skip:
            t0 = time.time()
            log(f"[1/5] decode -> meta.json")
            meta = decode.probe(video, job_dir / "meta.json")
            timings["decode"] = time.time() - t0
            log(f"      {meta['w']}x{meta['h']} @ {meta['fps']:.2f}fps "
                f"{meta['n_frames']} frames ({timings['decode']:.1f}s)")
        else:
            meta_path = job_dir / "meta.json"
            if not meta_path.exists():
                raise FileNotFoundError(
                    f"--skip decode requires existing {meta_path}; "
                    f"run without --skip decode first to populate it"
                )
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise RuntimeError(f"corrupted {meta_path}: {e}") from None

        # Stage 2
        if "ball" not in skip:
            t0 = time.time()
            log(f"[2/5] detect_ball -> ball.csv (device={device})")
            s = detect_ball.detect(video, job_dir / "ball.csv", device=device)
            timings["ball"] = time.time() - t0
            log(f"      {s['n_detected_filtered']}/{s['n_frames']} "
                f"({s['detection_rate']*100:.1f}%) in {timings['ball']:.0f}s "
                f"({s['fps_inference']:.1f} fps)")

        # Stage 3
        if "players" not in skip:
            t0 = time.time()
            log(f"[3/5] detect_players -> players.csv")
            s = detect_players.detect(video, job_dir / "players.csv", device=device)
            timings["players"] = time.time() - t0
            log(f"      {s['n_samples']} samples, avg n_players={s['avg_n_players']} "
                f"in {timings['players']:.0f}s")

        # Stage 4
        if "segment" not in skip:
            t0 = time.time()
            log(f"[4/5] segment_rallies -> segments.json")
            # Adjust min_run_frames to fps (1.5s window)
            min_run = max(45, int(meta["fps"] * 1.5))
            payload = segment_rallies.segment(
                ball_csv=job_dir / "ball.csv",
                players_csv=job_dir / "players.csv",
                meta=meta,
                out_segments=job_dir / "segments.json",
                params=RallyParams(min_run_frames=min_run, min_hits=4),
            )
            timings["segment"] = time.time() - t0
            log(f"      {len(payload['rallies'])} rallies in {timings['segment']:.1f}s")

        # Stage 5
        if "render" not in skip:
            t0 = time.time()
            # Prefer user-edited segments file if it exists; otherwise use the auto-generated one.
            segments_user = job_dir / "segments.user.json"
            segments_in = segments_user if segments_user.exists() else job_dir / "segments.json"
            if segments_in == segments_user:
                log(f"      using user-edited {segments_user.name}")
            if render_mode in ("highlight", "both"):
                label = "[5/5]" if render_mode == "highlight" else "[5/5 a]"
                log(f"{label} render highlight -> highlight.mp4")
                render.render(video, segments_in,
                              job_dir / "highlight.mp4", mode="highlight")
            if render_mode in ("short", "both"):
                label = "[5/5]" if render_mode == "short" else "[5/5 b]"
                log(f"{label} render short -> short.mp4")
                render.render(video, segments_in,
                              job_dir / "short.mp4", mode="short")
            timings["render"] = time.time() - t0
            log(f"      render done in {timings['render']:.0f}s")

        log(f"--- Total: {sum(timings.values()):.0f}s ---")
        return {"job_dir": str(job_dir), "timings": timings}
    except Exception as exc:
        log(f"!!! Pipeline failed in stage: {type(exc).__name__}: {exc}")
        raise
    finally:
        log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--job-dir", type=Path, default=None)
    ap.add_argument("--device", default="0")
    ap.add_argument("--render-mode", choices=["highlight", "short", "both"],
                    default="highlight")
    ap.add_argument("--skip", nargs="+", default=[],
                    choices=["decode", "ball", "players", "segment", "render"],
                    help="stages to skip; requires at least one value when used")
    args = ap.parse_args()
    job_dir = args.job_dir or (Path("jobs") / _job_id_for(args.video))
    run(args.video, job_dir, device=args.device,
        render_mode=args.render_mode, skip=tuple(args.skip))
    return 0


if __name__ == "__main__":
    sys.exit(main())
