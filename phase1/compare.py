import argparse
import json
import numpy as np
import librosa
from pathlib import Path

from extract_audio import extract_audio
from detect_hits import detect_hits
from segment_points import segment_points
from rank_points import rank_points


def compare_with_reference(
    video_path: str,
    reference_path: str,
    pipeline_segments: list[dict] | None = None,
    match_tolerance: float = 20.0,
) -> dict:
    ref_audio = extract_audio(reference_path)
    ref_hits, ref_energies, _ = detect_hits(ref_audio)
    ref_points = segment_points(
        ref_hits, ref_energies,
        silence_gap=3.0, min_duration=2.0, min_hit_count=2,
    )

    if pipeline_segments is None:
        orig_audio = extract_audio(video_path)
        orig_hits, orig_energies, _ = detect_hits(orig_audio)
        orig_points = segment_points(orig_hits, orig_energies)
        pipeline_segments = rank_points(orig_points)

    orig_audio = extract_audio(video_path)
    hop = 4096
    sr = 22050
    y_ref, _ = librosa.load(ref_audio, sr=sr)
    y_orig, _ = librosa.load(orig_audio, sr=sr)
    env_ref = librosa.onset.onset_strength(y=y_ref, sr=sr, hop_length=hop)
    env_orig = librosa.onset.onset_strength(y=y_orig, sr=sr, hop_length=hop)
    frame_dur = hop / sr

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
        mappings.append({
            "ref_start": p["start"],
            "ref_end": p["end"],
            "mapped_orig_time": round(orig_time, 1),
        })

    # Deduplicate by 10s window
    seen = set()
    unique = []
    for m in mappings:
        key = round(m["mapped_orig_time"] / 10) * 10
        if key not in seen:
            seen.add(key)
            unique.append(m)

    # Match against pipeline
    ranked_by_score = sorted(pipeline_segments, key=lambda x: x["score"], reverse=True)
    details = []
    matched = 0
    missed = []

    for m in unique:
        t = m["mapped_orig_time"]
        best = None
        best_dist = float("inf")
        for seg in pipeline_segments:
            dist = min(abs(seg["start"] - t), abs(seg["end"] - t))
            if seg["start"] - match_tolerance <= t <= seg["end"] + match_tolerance and dist < best_dist:
                best = seg
                best_dist = dist

        rank = None
        if best:
            matched += 1
            rank = next(
                (i + 1 for i, s in enumerate(ranked_by_score) if s["start"] == best["start"]),
                None,
            )

        detail = {
            **m,
            "matched": best is not None,
            "pipeline_start": best["start"] if best else None,
            "pipeline_end": best["end"] if best else None,
            "pipeline_score": best["score"] if best else None,
            "pipeline_rank": rank,
        }
        details.append(detail)
        if not best:
            missed.append(m)

    coverage = matched / len(unique) if unique else 0.0
    return {
        "reference_count": len(unique),
        "pipeline_count": len(pipeline_segments),
        "matched": matched,
        "missed": missed,
        "coverage": round(coverage, 4),
        "details": details,
    }


def print_report(result: dict):
    print(f"\nReference rallies: {result['reference_count']}")
    print(f"Pipeline segments: {result['pipeline_count']}")
    print(f"Matched: {result['matched']}/{result['reference_count']} "
          f"({result['coverage'] * 100:.1f}%)")
    print("\nDetails:")
    for d in result["details"]:
        t = d["mapped_orig_time"]
        if d["matched"]:
            print(f"  ~{t:.0f}s -> Pipeline {d['pipeline_start']:.1f}-{d['pipeline_end']:.1f}s "
                  f"(rank #{d['pipeline_rank']}, score={d['pipeline_score']:.3f})")
        else:
            print(f"  ~{t:.0f}s -> MISSING")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare pipeline output with hand-edited reference")
    parser.add_argument("video", help="Original video path")
    parser.add_argument("reference", help="Hand-edited reference video path")
    parser.add_argument("--tolerance", type=float, default=20.0, help="Match tolerance in seconds")
    args = parser.parse_args()

    print("Analyzing reference video...")
    result = compare_with_reference(args.video, args.reference, match_tolerance=args.tolerance)
    print_report(result)
