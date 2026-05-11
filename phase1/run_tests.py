"""Parallel test runner: runs pipeline + compare for all test videos and prints summary."""

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent / "tests"

VIDEOS = [
    ("0532", "DJI_20260503142617_0532_D"),
    ("0533", "DJI_20260503150415_0533_D"),
    ("0534", "DJI_20260503154223_0534_D"),
    ("0535", "DJI_20260505141553_0535_D"),
    ("0536", "DJI_20260505145356_0536_D"),
    ("0537", "DJI_20260505153140_0537_D"),
]


def _check_roi_cache():
    cache_path = Path(__file__).resolve().parent.parent / "phase2" / "rois_cache.json"
    if not cache_path.exists():
        return set()
    cache = json.loads(cache_path.read_text())
    return set(cache.keys())


def run_one(tag, stem, output_root, vision):
    from phase1.analyze import run_analysis
    from phase1.compare import compare_with_reference

    vid_path = str(TESTS_DIR / f"{stem}.MP4")
    ref_path = str(TESTS_DIR / f"{stem}_highlight.MP4")
    out_dir = str(output_root / f"output_{tag}")

    ranked = run_analysis(
        vid_path,
        output_dir=out_dir,
        vision=vision,
    )

    result = compare_with_reference(vid_path, ref_path, pipeline_segments=ranked)
    return tag, result


def main():
    parser = argparse.ArgumentParser(description="Run pipeline tests on all videos in parallel")
    parser.add_argument("--no-vision", action="store_true", help="Disable vision analysis")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="Max parallel workers")
    parser.add_argument("-o", "--output", default=None, help="Output root directory")
    args = parser.parse_args()

    vision = not args.no_vision
    output_root = Path(args.output) if args.output else Path(__file__).resolve().parent.parent

    if vision:
        cached = _check_roi_cache()
        uncached = [(tag, stem) for tag, stem in VIDEOS if f"{stem}.MP4" not in cached]
        if uncached:
            print(f"{len(uncached)} videos need ROI calibration (interactive):\n")
            from phase2.player_motion import select_rois
            for tag, stem in uncached:
                vid_path = str(TESTS_DIR / f"{stem}.MP4")
                print(f"  [{tag}] Calibrating ROIs for {stem}...")
                select_rois(vid_path)
            print()

    print(f"=== Running {len(VIDEOS)} tests (vision={vision}, workers={args.jobs}) ===\n")
    t0 = time.time()

    futures = {}
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for tag, stem in VIDEOS:
            fut = pool.submit(run_one, tag, stem, output_root, vision)
            futures[fut] = tag

        results = {}
        for fut in as_completed(futures):
            tag = futures[fut]
            try:
                _, result = fut.result()
                results[tag] = result
                print(f"  [{tag}] done — coverage={result['coverage']*100:.1f}%")
            except Exception as e:
                print(f"  [{tag}] FAILED: {e}")
                results[tag] = None

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.1f}s\n")

    print(f"{'Tag':>6} | {'Segments':>8} | {'Ref':>4} | {'Matched':>7} | {'Coverage':>8} | {'Precision':>9} | {'F1':>6}")
    print("-" * 65)

    total_pipe = total_ref = total_matched = 0
    for tag, _ in VIDEOS:
        r = results.get(tag)
        if r is None:
            print(f"{tag:>6} | {'FAILED':>8} |      |         |          |           |")
            continue
        pipe = r["pipeline_count"]
        ref = r["reference_count"]
        matched = r["matched"]
        cov = r["coverage"]
        prec = r["precision"]
        f1 = r["f1"]
        print(f"{tag:>6} | {pipe:>8} | {ref:>4} | {matched:>7} | {cov*100:>7.1f}% | {prec*100:>8.1f}% | {f1:>5.3f}")
        total_pipe += pipe
        total_ref += ref
        total_matched += matched

    if total_ref > 0:
        cov = total_matched / total_ref
        prec = total_matched / total_pipe if total_pipe > 0 else 0
        f1 = 2 * prec * cov / (prec + cov) if (prec + cov) > 0 else 0
        print("-" * 65)
        print(f"{'Total':>6} | {total_pipe:>8} | {total_ref:>4} | {total_matched:>7} | {cov*100:>7.1f}% | {prec*100:>8.1f}% | {f1:>5.3f}")


if __name__ == "__main__":
    main()
