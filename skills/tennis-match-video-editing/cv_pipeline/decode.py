"""Stage 1: probe video metadata.

Doesn't extract frames to disk (downstream stages use OpenCV streaming).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from . import paths


def probe(video: Path, out_meta: Path) -> dict:
    """Run ffprobe → write meta.json. Returns the dict."""
    cmd = [
        paths.FFPROBE, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,nb_frames,codec_name:format=duration",
        "-of", "json",
        str(video),
    ]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError(f"ffprobe binary not found: {paths.FFPROBE!r}") from None
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr}")
    raw = json.loads(r.stdout)
    stream = raw["streams"][0]
    fmt = raw["format"]

    num, den = stream["r_frame_rate"].split("/")
    fps = float(num) / float(den) if float(den) > 0 else 0.0

    n_frames = stream.get("nb_frames")
    duration = float(fmt.get("duration", 0))
    if n_frames in (None, "N/A"):
        n_frames = int(round(duration * fps))
    else:
        n_frames = int(n_frames)

    meta = {
        "video_path": Path(video).as_posix(),
        "w": int(stream["width"]),
        "h": int(stream["height"]),
        "fps": fps,
        "n_frames": n_frames,
        "duration": duration,
        "codec": stream.get("codec_name"),
        "elapsed_s": round(time.time() - t0, 3),
    }
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(meta, indent=2))
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    meta = probe(args.video, args.out)
    print(f"  {meta['w']}x{meta['h']} @ {meta['fps']:.2f}fps "
          f"{meta['n_frames']} frames {meta['duration']:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
