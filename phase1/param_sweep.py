"""Parameter sweep for rally segmentation pipeline.

Extracts audio and detects hits once per video, precomputes reference
mappings, then sweeps segmentation and score-cutoff parameters.
"""

import itertools
import sys
import time
from pathlib import Path

import numpy as np
import librosa

from phase1.extract_audio import extract_audio
from phase1.detect_hits import detect_hits
from phase1.segment_points import segment_points
from phase1.rank_points import rank_points

# ---------------------------------------------------------------------------
TESTS_DIR = Path(__file__).resolve().parent.parent / "tests"

VIDEOS = [
    ("0532", "DJI_20260503142617_0532_D"),
    ("0533", "DJI_20260503150415_0533_D"),
    ("0534", "DJI_20260503154223_0534_D"),
    ("0535", "DJI_20260505141553_0535_D"),
    ("0536", "DJI_20260505145356_0536_D"),
    ("0537", "DJI_20260505153140_0537_D"),
]

SILENCE_GAPS = [5, 6, 7, 8]
MIN_DURATIONS = [4, 5, 6, 7, 8]
MIN_HIT_COUNTS = [4, 5, 6, 7, 8]
SCORE_CUTOFFS = [0.0, 0.5, 1.0, 1.5, 2.0]


def precompute(videos):
    """Extract audio, detect hits, and compute reference mappings once."""
    cache = {}
    for tag, stem in videos:
        vid_path = str(TESTS_DIR / f"{stem}.MP4")
        ref_path = str(TESTS_DIR / f"{stem}_highlight.MP4")
        print(f"[{tag}] Extracting audio & detecting hits ...")
        t0 = time.time()

        # Original video
        orig_audio = extract_audio(vid_path)
        hit_times, hit_energies, sr = detect_hits(orig_audio)

        # Reference video — extract segments with loose params
        ref_audio = extract_audio(ref_path)
        ref_hits, ref_energies, _ = detect_hits(ref_audio)
        ref_points = segment_points(
            ref_hits, ref_energies,
            silence_gap=3.0, min_duration=2.0, min_hit_count=2,
        )

        # Compute reference-to-original time mappings via cross-correlation
        hop = 4096
        y_ref, _ = librosa.load(ref_audio, sr=22050)
        y_orig, _ = librosa.load(orig_audio, sr=22050)
        env_ref = librosa.onset.onset_strength(y=y_ref, sr=22050, hop_length=hop)
        env_orig = librosa.onset.onset_strength(y=y_orig, sr=22050, hop_length=hop)
        frame_dur = hop / 22050

        mappings = []
        for p in ref_points:
            start_frame = int(p["start"] / frame_dur)
            end_frame = min(int(p["end"] / frame_dur), len(env_ref))
            snippet = env_ref[start_frame:end_frame]
            if len(snippet) < 3:
                continue
            corr = np.correlate(env_orig, snippet, mode="valid")
            best_offset = int(np.argmax(corr))
            orig_time = best_offset * frame_dur
            mappings.append(round(orig_time, 1))

        # Deduplicate by 10s window
        seen = set()
        unique_times = []
        for t in mappings:
            key = round(t / 10) * 10
            if key not in seen:
                seen.add(key)
                unique_times.append(t)

        elapsed = time.time() - t0
        print(f"  {len(hit_times)} hits, {len(unique_times)} ref rallies in {elapsed:.1f}s")

        cache[tag] = {
            "hit_times": hit_times,
            "hit_energies": hit_energies,
            "ref_times": unique_times,  # mapped original-video times for each ref rally
        }
    return cache


def match_segments(ref_times, pipeline_segments, tolerance=20.0):
    """Count how many reference rallies are matched by pipeline segments."""
    matched = 0
    for t in ref_times:
        for seg in pipeline_segments:
            if seg["start"] - tolerance <= t <= seg["end"] + tolerance:
                matched += 1
                break
    return matched


def main():
    print("=== Parameter Sweep ===\n")
    cache = precompute(VIDEOS)

    combos = list(itertools.product(SILENCE_GAPS, MIN_DURATIONS, MIN_HIT_COUNTS, SCORE_CUTOFFS))
    print(f"\nSweeping {len(combos)} parameter combinations ...\n")

    results = []
    for i, (sg, md, mhc, sc) in enumerate(combos):
        total_pipeline = 0
        total_ref = 0
        total_matched = 0

        for tag, info in cache.items():
            points = segment_points(
                info["hit_times"],
                info["hit_energies"],
                silence_gap=sg,
                min_duration=md,
                min_hit_count=mhc,
            )
            ranked = rank_points(points)

            if sc > 0:
                ranked = [r for r in ranked if r["score"] >= sc]

            m = match_segments(info["ref_times"], ranked)
            total_pipeline += len(ranked)
            total_ref += len(info["ref_times"])
            total_matched += m

        cov = total_matched / total_ref if total_ref > 0 else 0
        prec = total_matched / total_pipeline if total_pipeline > 0 else 0
        f1 = 2 * prec * cov / (prec + cov) if (prec + cov) > 0 else 0
        results.append((sg, md, mhc, sc, total_pipeline, total_ref, total_matched, cov, prec, f1))

        if (i + 1) % 100 == 0:
            print(f"  ... {i+1}/{len(combos)} done")

    # Sort: coverage >= 0.9 first, then by precision desc
    results.sort(key=lambda r: (r[7] >= 0.9, r[8], r[7]), reverse=True)

    print(f"\n{'gap':>4} {'dur':>4} {'hits':>5} {'sc_cut':>6} | {'pipe':>5} {'ref':>4} {'match':>5} | {'cov%':>6} {'prec%':>6} {'F1':>6}")
    print("-" * 72)
    for sg, md, mhc, sc, tp, tr, tm, cov, prec, f1 in results[:80]:
        marker = " *" if cov >= 0.9 and prec >= 0.5 else ""
        print(f"{sg:4} {md:4} {mhc:5} {sc:6.1f} | {tp:5} {tr:4} {tm:5} | {cov*100:5.1f}% {prec*100:5.1f}% {f1:5.3f}{marker}")

    winners = [r for r in results if r[7] >= 0.9 and r[8] >= 0.5]
    print(f"\n=== {len(winners)} combinations meet coverage>=90% AND precision>=50% ===")
    if winners:
        best = max(winners, key=lambda r: r[9])
        print(f"Best F1: gap={best[0]}, dur={best[1]}, hits={best[2]}, score_cutoff={best[3]:.1f}")
        print(f"  Pipeline={best[4]}, Ref={best[5]}, Matched={best[6]}")
        print(f"  Coverage={best[7]*100:.1f}%, Precision={best[8]*100:.1f}%, F1={best[9]:.3f}")
    else:
        close = sorted(results, key=lambda r: r[9], reverse=True)[:5]
        print("Top 5 by F1:")
        for r in close:
            print(f"  gap={r[0]}, dur={r[1]}, hits={r[2]}, sc={r[3]:.1f} => cov={r[7]*100:.1f}%, prec={r[8]*100:.1f}%, F1={r[9]:.3f}")


if __name__ == "__main__":
    main()
