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
import argparse
import json
from pathlib import Path

from engine.ffutil import run_ffmpeg


def compile_highlights(
    video_path: str,
    timeline_path: str,
    output_path: str | None = None,
) -> str:
    video = Path(video_path)
    timeline = Path(timeline_path)

    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not timeline.exists():
        raise FileNotFoundError(f"Timeline not found: {timeline_path}")

    if output_path is None:
        output_path = str(timeline.parent / f"{video.stem}_highlights.mp4")

    segments = json.loads(timeline.read_text())
    if not segments:
        raise ValueError("Timeline JSON is empty")

    clips = sorted(segments, key=lambda x: x["start"])

    filter_parts = []
    inputs = []
    for i, seg in enumerate(clips):
        start = seg["start"]
        duration = seg["end"] - seg["start"]
        inputs.extend(["-ss", str(start), "-t", str(duration), "-i", video_path])
        filter_parts.append(f"[{i}:v][{i}:a]")

    filter_str = "".join(filter_parts) + f"concat=n={len(clips)}:v=1:a=1[outv][outa]"

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_str,
        "-map", "[outv]", "-map", "[outa]",
        output_path,
    ]

    print(f"Compiling {len(clips)} segments into {output_path}...")
    run_ffmpeg(cmd)
    print(f"Done. Output: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile highlight video from timeline JSON")
    parser.add_argument("video", help="Path to original video file")
    parser.add_argument("timeline", help="Path to timeline JSON (full_report.json)")
    parser.add_argument("-o", "--output", default=None, help="Output path (default: <video_stem>_highlights.mp4)")
    args = parser.parse_args()

    compile_highlights(args.video, args.timeline, args.output)
