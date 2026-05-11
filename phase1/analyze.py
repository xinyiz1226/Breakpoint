import argparse
import json
import time
from pathlib import Path

from phase1.extract_audio import extract_audio
from phase1.detect_hits import detect_hits
from phase1.segment_points import segment_points
from phase1.rank_points import rank_points


def run_analysis(
    video_path: str,
    output_dir: str | None = None,
    silence_gap: float = 6.0,
    buffer: float = 1.5,
    vision: bool = True,
    vision_keep: float = 0.7,
) -> list[dict]:
    video = Path(video_path)
    if output_dir is None:
        output_dir = str(video.parent / f"output_{video.stem}")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Extracting audio from {video.name}...")
    t0 = time.time()
    audio_path = extract_audio(video_path, str(out / "audio.wav"))
    print(f"  Done in {time.time() - t0:.1f}s")

    print("[2/4] Detecting hits...")
    t0 = time.time()
    hit_times, hit_energies, sr = detect_hits(audio_path)
    print(f"  Found {len(hit_times)} hits in {time.time() - t0:.1f}s")

    print("[3/4] Segmenting points...")
    points = segment_points(hit_times, hit_energies, silence_gap=silence_gap, buffer=buffer)
    print(f"  Found {len(points)} points/rallies")

    vision_data = None
    if vision:
        from phase2.player_motion import select_rois, analyze_motion
        print("[3.5/4] Analyzing player motion (vision)...")
        t0 = time.time()
        rois = select_rois(video_path)
        vision_data = analyze_motion(video_path, points, rois)
        print(f"  Done in {time.time() - t0:.1f}s")

    print("[4/4] Ranking points...")
    ranked = rank_points(points, vision_data=vision_data)
    if vision_data and len(ranked) > 1:
        keep_count = max(1, int(len(ranked) * vision_keep))
        removed = len(ranked) - keep_count
        ranked = ranked[:keep_count]
        print(f"  Vision filter: kept top {keep_count}, removed bottom {removed}")

    for i, p in enumerate(ranked):
        dur = p["end"] - p["start"]
        hits = p["features"]["hit_count"]
        print(f"  #{i+1}: {p['start']:.1f}s-{p['end']:.1f}s ({dur:.1f}s, {hits} hits, score={p['score']:.3f})")

    report_path = str(out / "full_report.json")
    report_data = [{
        "index": i + 1,
        "start": p["start"],
        "end": p["end"],
        "score": p["score"],
        "features": p["features"],
    } for i, p in enumerate(ranked)]
    Path(report_path).write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
    print(f"\nTimeline saved to {report_path}")
    print(f"Total points: {len(ranked)}")

    return ranked


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tennis highlight analysis — audio + vision")
    parser.add_argument("video", help="Path to input video file")
    parser.add_argument("-o", "--output", default=None, help="Output directory (default: output_<video_stem>)")
    parser.add_argument("--silence-gap", type=float, default=6.0, help="Silence gap threshold (seconds)")
    parser.add_argument("--buffer", type=float, default=1.5, help="Buffer before/after each point (seconds)")
    parser.add_argument("--no-vision", action="store_true", help="Disable vision-based player motion analysis")
    parser.add_argument("--vision-keep", type=float, default=0.7, help="Fraction of segments to keep after vision ranking (0-1, default 0.7)")
    parser.add_argument("--reference", help="Hand-edited reference video for comparison")
    args = parser.parse_args()

    ranked = run_analysis(
        args.video,
        output_dir=args.output,
        silence_gap=args.silence_gap,
        buffer=args.buffer,
        vision=not args.no_vision,
        vision_keep=args.vision_keep,
    )

    if args.reference:
        from phase1.compare import compare_with_reference, print_report
        print("\n[Compare] Comparing with reference video...")
        result = compare_with_reference(args.video, args.reference, pipeline_segments=ranked)
        print_report(result)
