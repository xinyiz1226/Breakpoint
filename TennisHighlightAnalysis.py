import argparse
import multiprocessing
import sys
from pathlib import Path

from engine.pipeline import run_analysis
from engine.export.compile import compile_highlights


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Tennis Highlight Analysis - end-to-end pipeline")
    parser.add_argument("video", help="Path to input video file")
    parser.add_argument("-o", "--output", default=None, help="Output directory (default: output_<video_stem>)")
    parser.add_argument("--silence-gap", type=float, default=6.0, help="Silence gap threshold (seconds)")
    parser.add_argument("--buffer", type=float, default=1.5, help="Buffer before/after each point (seconds)")
    parser.add_argument("--no-vision", action="store_true", help="Disable vision-based analysis")
    parser.add_argument("--vision-keep", type=float, default=0.7, help="Fraction of segments to keep after vision ranking (0-1, default 0.7)")
    parser.add_argument("--json-progress", action="store_true", help="Output JSON-line progress messages to stdout")
    parser.add_argument("--no-compile", action="store_true", help="Only analyze, skip highlight compilation")
    parser.add_argument("--reference", help="Hand-edited reference video for comparison")
    args = parser.parse_args()

    video = Path(args.video)
    if not video.exists():
        print(f"Error: video not found: {args.video}")
        sys.exit(1)

    output_dir = args.output if args.output else str(video.parent / f"output_{video.stem}")

    ranked = run_analysis(
        args.video,
        output_dir=output_dir,
        silence_gap=args.silence_gap,
        buffer=args.buffer,
        vision=not args.no_vision,
        vision_keep=args.vision_keep,
        json_progress=args.json_progress,
    )

    if not args.no_compile and ranked:
        timeline_path = str(Path(output_dir) / "full_report.json")
        compile_highlights(args.video, timeline_path)

    if args.reference:
        from tools.compare import compare_with_reference, print_report
        print("\n[Compare] Comparing with reference video...")
        result = compare_with_reference(args.video, args.reference, pipeline_segments=ranked)
        print_report(result)


if __name__ == "__main__":
    main()
