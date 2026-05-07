import subprocess
import sys
from pathlib import Path


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
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_audio.py <video_path> [output_path]")
        sys.exit(1)
    out = extract_audio(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"Audio extracted to: {out}")
