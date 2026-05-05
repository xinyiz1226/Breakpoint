"""Stage 5: render highlight or short video via ffmpeg cut + concat."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from . import paths


def _select_for_short(rallies: list[dict], target_min: float = 60.0,
                      target_max: float = 90.0) -> list[dict]:
    """Pick top-N by score so total duration falls in [target_min, target_max]."""
    sorted_r = sorted(rallies, key=lambda r: r["score"], reverse=True)
    picked = []
    total = 0.0
    for r in sorted_r:
        d = r["end_t"] - r["start_t"]
        if total + d > target_max:
            continue
        picked.append(r)
        total += d
        if total >= target_min:
            break
    # restore time order so the short reads chronologically
    picked.sort(key=lambda r: r["start_t"])
    return picked


def render(source_video: Path, segments_json: Path, out: Path,
           mode: str = "highlight", crf: int = 18, preset: str = "medium") -> dict:
    """Render highlight ('all kept rallies in time order') or short ('top-N by score')."""
    if mode not in ("highlight", "short"):
        raise ValueError(f"unknown mode: {mode}")

    with segments_json.open() as f:
        data = json.load(f)
    rallies = [r for r in data["rallies"] if r.get("kept", True)]
    if not rallies:
        raise RuntimeError("no rallies marked kept=True")

    if mode == "short":
        rallies = _select_for_short(rallies)

    with tempfile.TemporaryDirectory(prefix="bp_render_") as tmp:
        tmpdir = Path(tmp)
        clip_paths: list[Path] = []
        for i, r in enumerate(rallies):
            clip_out = tmpdir / f"clip_{i:03d}.mp4"
            cmd = [
                paths.FFMPEG, "-y", "-loglevel", "error",
                "-ss", f"{r['start_t']:.3f}",
                "-i", str(source_video),
                "-t", f"{r['end_t'] - r['start_t']:.3f}",
                "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
                "-c:a", "aac", "-b:a", "128k",
                str(clip_out),
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
            except FileNotFoundError:
                raise RuntimeError(f"ffmpeg not found: {paths.FFMPEG}")
            if res.returncode != 0:
                raise RuntimeError(f"ffmpeg cut failed for {r['id']}: {res.stderr}")
            clip_paths.append(clip_out)

        concat_list = tmpdir / "list.txt"
        with concat_list.open("w") as f:
            f.write("\n".join(f"file '{p.as_posix()}'" for p in clip_paths) + "\n")
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            paths.FFMPEG, "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy", str(out),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError(f"ffmpeg not found: {paths.FFMPEG}")
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {res.stderr}")

    return {"output": str(out), "n_clips": len(rallies)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--segments", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--mode", choices=["highlight", "short"], default="highlight")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    args = ap.parse_args()
    summary = render(args.video, args.segments, args.out, mode=args.mode,
                     crf=args.crf, preset=args.preset)
    print(f"  rendered {summary['n_clips']} clips → {summary['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
