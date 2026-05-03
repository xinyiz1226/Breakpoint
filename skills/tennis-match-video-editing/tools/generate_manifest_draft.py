#!/usr/bin/env python3
"""Generate a draft highlight manifest using audio hit detection (primary)
and frame-difference motion (secondary).

Pipeline:
1. Extract mono PCM audio from the source via ffmpeg.
2. Detect sharp transient onsets (tennis ball impact sounds) by spectral flux.
3. Build a per-second hit-density signal and smooth it.
4. Find local peaks where hit density is high (rallies / serves).
5. Wrap a window around each peak, rank, and emit a manifest draft.

NOT a tennis classifier. It is an editor-assistant draft. Review before final render.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Candidate:
    peak_sec: float
    score: float
    hit_count: int
    start_sec: float
    end_sec: float


def seconds_to_ts(total_seconds: float) -> str:
    ms = int(round(max(total_seconds, 0.0) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def default_manifest_path(source: Path) -> Path:
    return source.with_name(f"{source.stem}_draft_manifest.json")


def default_signal_csv_path(source: Path) -> Path:
    return source.with_name(f"{source.stem}_audio_signal.csv")


def default_checklist_path(source: Path) -> Path:
    return source.with_name(f"{source.stem}_candidates.md")


def _ts_to_seconds(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(".") if "." in rest else (rest, "0")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def write_checklist_md(
    path: Path,
    source: Path,
    render_output: Path,
    manifest_path: Path,
    candidates_sorted: list[Candidate],
    keep_ids: set[int],
) -> None:
    lines: list[str] = []
    lines.append("# Tennis highlights — candidate clips")
    lines.append("")
    lines.append(f"- Source: `{source}`")
    lines.append(f"- Output: `{render_output}`")
    lines.append(f"- Manifest: `{manifest_path}`")
    lines.append("")
    lines.append("Tick the clips to include, save this file, then run:")
    lines.append("")
    lines.append(f"    render_from_manifest.py \"{path}\"")
    lines.append("")
    lines.append("Each line format (do not change the leading `- [ ] AUTO-NNN | start → end`):")
    lines.append("")
    for index, c in enumerate(candidates_sorted, start=1):
        clip_id = f"AUTO-{index:03d}"
        checked = "x" if id(c) in keep_ids else " "
        dur = max(c.end_sec - c.start_sec, 0.0)
        lines.append(
            f"- [{checked}] {clip_id} | {seconds_to_ts(c.start_sec)} → {seconds_to_ts(c.end_sec)} "
            f"| dur={dur:.1f}s | hits={c.hit_count} | score={c.score:.2f}"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def extract_mono_pcm(source: Path, sample_rate: int, audio_filter: str | None) -> np.ndarray:
    with tempfile.TemporaryDirectory(prefix="tennis_audio_") as tmp:
        wav_path = Path(tmp) / "audio.wav"
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
        ]
        if audio_filter:
            cmd.extend(["-af", audio_filter])
        cmd.extend(["-f", "wav", str(wav_path)])
        result = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg audio extract failed: {result.stderr.strip()}")
        with wave.open(str(wav_path), "rb") as fh:
            n = fh.getnframes()
            raw = fh.readframes(n)
            sw = fh.getsampwidth()
            sr = fh.getframerate()
        if sw != 2:
            raise RuntimeError(f"Unsupported sample width: {sw}")
        if sr != sample_rate:
            raise RuntimeError(f"Sample rate mismatch: got {sr}")
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return samples


def stft_mag(samples: np.ndarray, n_fft: int, hop: int) -> tuple[np.ndarray, int]:
    pad = (-len(samples)) % hop
    if pad:
        samples = np.concatenate([samples, np.zeros(pad, dtype=np.float32)])
    if len(samples) < n_fft:
        samples = np.concatenate([samples, np.zeros(n_fft - len(samples), dtype=np.float32)])
    window = np.hanning(n_fft).astype(np.float32)
    n_frames = 1 + (len(samples) - n_fft) // hop
    out = np.empty((n_frames, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_frames):
        seg = samples[i * hop : i * hop + n_fft] * window
        out[i] = np.abs(np.fft.rfft(seg))
    return out, n_frames


def detect_onsets(
    samples: np.ndarray,
    sample_rate: int,
    n_fft: int,
    hop: int,
    high_freq_hz: float,
    onset_min_separation_ms: float,
    onset_threshold_ratio: float,
) -> list[float]:
    mag, n_frames = stft_mag(samples, n_fft=n_fft, hop=hop)
    # Restrict to high-frequency band where racket impacts dominate.
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    band_mask = freqs >= high_freq_hz
    if not np.any(band_mask):
        band_mask = np.ones_like(freqs, dtype=bool)
    band = mag[:, band_mask]

    # Spectral flux: sum of positive change in band magnitude.
    diff = np.diff(band, axis=0, prepend=band[:1])
    flux = np.sum(np.maximum(diff, 0.0), axis=1)

    # Normalize and threshold.
    median = float(np.median(flux))
    mad = float(np.median(np.abs(flux - median)) + 1e-6)
    threshold = median + onset_threshold_ratio * mad

    frame_seconds = hop / sample_rate
    min_sep_frames = max(int(round((onset_min_separation_ms / 1000.0) / frame_seconds)), 1)

    onsets: list[float] = []
    last_onset_frame = -min_sep_frames
    for i in range(1, len(flux) - 1):
        if flux[i] < threshold:
            continue
        if flux[i] <= flux[i - 1] or flux[i] < flux[i + 1]:
            continue
        if i - last_onset_frame < min_sep_frames:
            if flux[i] > flux[last_onset_frame]:
                last_onset_frame = i
                onsets[-1] = i * frame_seconds
            continue
        onsets.append(i * frame_seconds)
        last_onset_frame = i
    return onsets


def detect_rally_sequences(
    onsets: list[float],
    min_hits: int,
    min_interval: float,
    max_interval: float,
    max_jitter: float,
) -> list[tuple[float, float, int, float]]:
    """Group onsets into rally-like sequences.

    A sequence is a chain where every consecutive interval is within
    [min_interval, max_interval]. Returns (first_onset, last_onset, hit_count, score).
    """
    if not onsets:
        return []
    sequences: list[tuple[float, float, int, float]] = []
    chain: list[float] = [onsets[0]]
    intervals: list[float] = []

    def flush(chain: list[float], intervals: list[float]) -> None:
        if len(chain) >= min_hits:
            mean = float(np.mean(intervals)) if intervals else 0.0
            std = float(np.std(intervals)) if intervals else 0.0
            jitter = std / mean if mean > 0 else 1.0
            if jitter <= max_jitter:
                # Score: more hits and steadier rhythm => higher score.
                score = len(chain) * (1.0 / (1.0 + jitter))
                sequences.append((chain[0], chain[-1], len(chain), score))

    for prev, curr in zip(onsets, onsets[1:]):
        gap = curr - prev
        if min_interval <= gap <= max_interval:
            chain.append(curr)
            intervals.append(gap)
        else:
            flush(chain, intervals)
            chain = [curr]
            intervals = []
    flush(chain, intervals)
    return sequences


def build_candidates_from_sequences(
    sequences: list[tuple[float, float, int, float]],
    duration: float,
    pre_pad: float,
    post_pad: float,
    min_separation: float,
) -> list[Candidate]:
    if not sequences:
        return []
    # Merge sequences whose padded windows overlap or are very close.
    sequences = sorted(sequences, key=lambda s: s[0])
    merged: list[tuple[float, float, int, float]] = []
    for first, last, hits, score in sequences:
        if not merged:
            merged.append((first, last, hits, score))
            continue
        prev_first, prev_last, prev_hits, prev_score = merged[-1]
        if first - prev_last <= min_separation:
            merged[-1] = (
                prev_first,
                last,
                prev_hits + hits,
                prev_score + score,
            )
        else:
            merged.append((first, last, hits, score))

    candidates: list[Candidate] = []
    for first, last, hits, score in merged:
        start = max(first - pre_pad, 0.0)
        end = min(last + post_pad, duration)
        candidates.append(
            Candidate(
                peak_sec=first,
                score=float(score),
                hit_count=int(hits),
                start_sec=start,
                end_sec=end,
            )
        )
    return candidates


def write_signal_csv(path: Path, onsets: list[float]) -> None:
    import csv

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["onset_timestamp", "delta_from_prev_sec"])
        prev: float | None = None
        for t in onsets:
            delta = "" if prev is None else f"{t - prev:.3f}"
            writer.writerow([seconds_to_ts(t), delta])
            prev = t


def write_manifest(
    source: Path,
    manifest_path: Path,
    render_output: Path,
    candidates: list[Candidate],
    keep_count: int,
) -> tuple[int, list[Candidate], set[int]]:
    ranked = sorted(candidates, key=lambda c: (c.score, c.hit_count), reverse=True)
    keep_ids = {id(c) for c in ranked[: max(keep_count, 0)]}

    sorted_by_start = sorted(candidates, key=lambda c: c.start_sec)
    clips = []
    for index, c in enumerate(sorted_by_start, start=1):
        action = "keep" if id(c) in keep_ids else "review"
        clips.append(
            {
                "id": f"AUTO-{index:03d}",
                "start": seconds_to_ts(c.start_sec),
                "end": seconds_to_ts(c.end_sec),
                "action": action,
                "reason": f"hits={c.hit_count} smoothed={c.score:.2f}",
                "tags": ["AUTO_DRAFT", "AUDIO_HIT"],
            }
        )

    payload = {
        "source": str(source),
        "output": str(render_output),
        "notes": {
            "generator": "generate_manifest_draft.py (audio-hit)",
            "warning": "Heuristic audio-hit draft. Review keep/review clips before final render.",
        },
        "clips": clips,
    }
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(clips), sorted_by_start, keep_ids


def main() -> int:
    p = argparse.ArgumentParser(description="Audio-hit-driven highlight draft generator")
    p.add_argument("source", type=Path)
    p.add_argument("--manifest", type=Path, default=None)
    p.add_argument("--signal-csv", type=Path, default=None)
    p.add_argument("--sample-rate", type=int, default=22050)
    p.add_argument(
        "--audio-filter",
        type=str,
        default="highpass=f=2500,lowpass=f=10000,afftdn=nf=-25",
        help="ffmpeg -af filter chain to suppress voice/ambient noise before onset detection",
    )
    p.add_argument("--no-denoise", action="store_true", help="Disable audio pre-filtering")
    p.add_argument("--n-fft", type=int, default=2048)
    p.add_argument("--hop", type=int, default=512)
    p.add_argument("--high-freq-hz", type=float, default=2000.0)
    p.add_argument("--onset-threshold-ratio", type=float, default=4.0)
    p.add_argument("--onset-min-separation-ms", type=float, default=120.0)
    p.add_argument("--rally-min-hits", type=int, default=3, help="Min consecutive hits to qualify as rally")
    p.add_argument("--rally-min-interval", type=float, default=0.45, help="Min seconds between rally hits")
    p.add_argument("--rally-max-interval", type=float, default=2.5, help="Max seconds between rally hits")
    p.add_argument("--rally-max-jitter", type=float, default=0.9, help="Max std/mean of intra-rally intervals")
    p.add_argument("--merge-gap", type=float, default=2.0, help="Merge sequences closer than this seconds")
    p.add_argument("--pre-pad", type=float, default=2.5)
    p.add_argument("--post-pad", type=float, default=4.0)
    p.add_argument("--max-candidates", type=int, default=120)
    p.add_argument("--keep-count", type=int, default=24)
    p.add_argument("--checklist", type=Path, default=None, help="Path to write markdown checklist (default: <stem>_candidates.md)")
    p.add_argument("--no-checklist", action="store_true", help="Skip writing the markdown checklist")
    args = p.parse_args()

    source = args.source.expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Source video not found: {source}")

    manifest_path = args.manifest.expanduser().resolve() if args.manifest else default_manifest_path(source)
    signal_csv = args.signal_csv.expanduser().resolve() if args.signal_csv else default_signal_csv_path(source)
    render_output = source.with_name(f"{source.stem}_highlights.mp4")

    print("Extracting audio...", file=sys.stderr)
    audio_filter = None if args.no_denoise else args.audio_filter
    if audio_filter:
        print(f"  audio filter: {audio_filter}", file=sys.stderr)
    samples = extract_mono_pcm(source, sample_rate=args.sample_rate, audio_filter=audio_filter)
    duration = len(samples) / args.sample_rate
    print(f"  duration={duration:.1f}s samples={len(samples)}", file=sys.stderr)

    print("Detecting onsets...", file=sys.stderr)
    onsets = detect_onsets(
        samples=samples,
        sample_rate=args.sample_rate,
        n_fft=args.n_fft,
        hop=args.hop,
        high_freq_hz=args.high_freq_hz,
        onset_min_separation_ms=args.onset_min_separation_ms,
        onset_threshold_ratio=args.onset_threshold_ratio,
    )
    print(f"  onsets detected: {len(onsets)}", file=sys.stderr)

    write_signal_csv(signal_csv, onsets)

    sequences = detect_rally_sequences(
        onsets=onsets,
        min_hits=args.rally_min_hits,
        min_interval=args.rally_min_interval,
        max_interval=args.rally_max_interval,
        max_jitter=args.rally_max_jitter,
    )
    print(f"  rally sequences: {len(sequences)}", file=sys.stderr)

    candidates = build_candidates_from_sequences(
        sequences=sequences,
        duration=duration,
        pre_pad=args.pre_pad,
        post_pad=args.post_pad,
        min_separation=args.merge_gap,
    )
    if not candidates:
        raise SystemExit("No rally sequences found. Try lowering --rally-min-hits or relaxing intervals.")

    candidates = sorted(candidates, key=lambda c: c.score, reverse=True)[: max(args.max_candidates, 0)]
    total, sorted_by_start, keep_ids = write_manifest(
        source=source,
        manifest_path=manifest_path,
        render_output=render_output,
        candidates=candidates,
        keep_count=args.keep_count,
    )
    keep_total = min(max(args.keep_count, 0), len(candidates))
    print(f"Draft manifest written: {manifest_path}")
    print(f"Audio signal csv: {signal_csv}")
    print(f"Candidates: {total} total, {keep_total} marked keep")

    if not args.no_checklist:
        checklist_path = args.checklist.expanduser().resolve() if args.checklist else default_checklist_path(source)
        write_checklist_md(
            path=checklist_path,
            source=source,
            render_output=render_output,
            manifest_path=manifest_path,
            candidates_sorted=sorted_by_start,
            keep_ids=keep_ids,
        )
        print(f"Checklist (tick to keep): {checklist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
