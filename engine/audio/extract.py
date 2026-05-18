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
import sys
from pathlib import Path

from engine.ffutil import run_ffmpeg


def extract_audio(video_path: str, output_path: str | None = None, sr: int = 22050) -> str:
    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if output_path is None:
        output_path = str(video.with_suffix(".wav"))

    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", str(sr), "-ac", "1",
        output_path,
    ]
    run_ffmpeg(cmd)
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_audio.py <video_path> [output_path]")
        sys.exit(1)
    out = extract_audio(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"Audio extracted to: {out}")
