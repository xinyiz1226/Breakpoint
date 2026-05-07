import argparse
import json
import time
from pathlib import Path

from extract_audio import extract_audio
from detect_hits import detect_hits
from segment_points import segment_points
from rank_points import rank_points
from export_clips import export_clips, export_compilation


def run_pipeline(
    video_path: str,
    output_dir: str = "output",
    top_n: int = 0,
    silence_gap: float = 6.0,
    buffer: float = 1.5,
    compile_video: bool = True,
):
    video = Path(video_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[1/5] Extracting audio from {video.name}...")
    t0 = time.time()
    audio_path = extract_audio(video_path, str(out / "audio.wav"))
    print(f"  Done in {time.time() - t0:.1f}s")

    print("[2/5] Detecting hits...")
    t0 = time.time()
    hit_times, hit_energies, sr = detect_hits(audio_path)
    print(f"  Found {len(hit_times)} hits in {time.time() - t0:.1f}s")

    print("[3/5] Segmenting points...")
    points = segment_points(hit_times, hit_energies, silence_gap=silence_gap, buffer=buffer)
    print(f"  Found {len(points)} points/rallies")

    print("[4/5] Ranking points...")
    ranked = rank_points(points)
    n = top_n if top_n > 0 else len(ranked)
    for i, p in enumerate(ranked[:n]):
        dur = p["end"] - p["start"]
        hits = p["features"]["hit_count"]
        print(f"  #{i+1}: {p['start']:.1f}s-{p['end']:.1f}s ({dur:.1f}s, {hits} hits, score={p['score']:.3f})")

    print(f"[5/5] Exporting {n} clips...")
    t0 = time.time()
    clips_dir = str(out / "clips")
    exported = export_clips(video_path, ranked, clips_dir, n)
    print(f"  Exported {len(exported)} files in {time.time() - t0:.1f}s")

    if compile_video:
        print("  Compiling highlight video...")
        comp_path = str(out / "highlights.mp4")
        export_compilation(video_path, ranked, comp_path, n)
        print(f"  Saved to {comp_path}")

    full_report = str(out / "full_report.json")
    report_data = [{
        "index": i + 1,
        "start": p["start"],
        "end": p["end"],
        "score": p["score"],
        "features": p["features"],
    } for i, p in enumerate(ranked)]
    Path(full_report).write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
    print(f"\nFull report saved to {full_report}")
    print(f"Total points: {len(ranked)}, exported top {min(top_n, len(ranked))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tennis highlight extraction pipeline")
    parser.add_argument("video", help="Path to input video file")
    parser.add_argument("-o", "--output", default="output", help="Output directory")
    parser.add_argument("-n", "--top-n", type=int, default=0, help="Number of top highlights (0 = all)")
    parser.add_argument("--silence-gap", type=float, default=6.0, help="Silence gap threshold (seconds)")
    parser.add_argument("--buffer", type=float, default=1.5, help="Buffer before/after each point (seconds)")
    parser.add_argument("--no-compile", action="store_true", help="Skip compilation into single video")
    args = parser.parse_args()

    run_pipeline(
        args.video,
        output_dir=args.output,
        top_n=args.top_n,
        silence_gap=args.silence_gap,
        buffer=args.buffer,
        compile_video=not args.no_compile,
    )
