import json
from pathlib import Path

from engine.ffutil import run_ffmpeg


def export_clips(
    video_path: str,
    ranked_points: list[dict],
    output_dir: str,
    top_n: int = 10,
) -> list[str]:
    """Export top-N clips from the original video without re-encoding."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    clips = ranked_points[:top_n]
    # Sort by timestamp for chronological output
    clips_sorted = sorted(clips, key=lambda x: x["start"])
    exported = []

    for i, point in enumerate(clips_sorted):
        start = point["start"]
        duration = point["end"] - point["start"]
        clip_path = str(out / f"clip_{i+1:02d}_{start:.0f}s.mp4")

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", video_path,
            "-t", str(duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            clip_path,
        ]
        run_ffmpeg(cmd)
        exported.append(clip_path)

    report_path = str(out / "report.json")
    report = []
    for i, point in enumerate(clips_sorted):
        report.append({
            "index": i + 1,
            "start": point["start"],
            "end": point["end"],
            "score": point["score"],
            "features": point["features"],
        })
    Path(report_path).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    exported.append(report_path)

    return exported


def export_compilation(
    video_path: str,
    ranked_points: list[dict],
    output_path: str,
    top_n: int = 10,
) -> str:
    """Export a single compiled highlight video."""
    clips = ranked_points[:top_n]
    # Sort by time for chronological compilation
    clips_sorted = sorted(clips, key=lambda x: x["start"])

    filter_parts = []
    inputs = []
    for i, point in enumerate(clips_sorted):
        start = point["start"]
        duration = point["end"] - point["start"]
        inputs.extend(["-ss", str(start), "-t", str(duration), "-i", video_path])
        filter_parts.append(f"[{i}:v][{i}:a]")

    filter_str = "".join(filter_parts) + f"concat=n={len(clips_sorted)}:v=1:a=1[outv][outa]"

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_str,
        "-map", "[outv]", "-map", "[outa]",
        output_path,
    ]
    run_ffmpeg(cmd)
    return output_path
