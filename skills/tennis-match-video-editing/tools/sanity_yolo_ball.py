"""YOLO ball-detection sanity check on DJI sample.

Mirrors sanity_tracknet.py so detection rates are directly comparable:
- cuts the same 8.4s window from source
- runs YOLO ball detector frame-by-frame
- writes overlay video, CSV, and a summary
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from pathlib import Path

import cv2
from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--start", type=float, default=367.9)
    ap.add_argument("--duration", type=float, default=8.4)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--conf", type=float, default=0.15)
    ap.add_argument("--device", default="0", help='"0" for GPU, "cpu" for CPU')
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sample_path = out_dir / "sample.mp4"
    overlay_path = out_dir / "overlay.mp4"
    csv_path = out_dir / "detections.csv"

    print(f"[1/3] Cutting {args.duration:.0f}s sample from {args.start:.1f}s...")
    cmd = [
        args.ffmpeg, "-y", "-loglevel", "error",
        "-ss", str(args.start),
        "-i", args.video,
        "-t", str(args.duration),
        "-vf", "scale=1280:720",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-an",
        str(sample_path),
    ]
    t0 = time.time()
    r = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        print("ffmpeg failed:", r.stderr)
        sys.exit(1)
    print(f"      done in {time.time()-t0:.1f}s -> {sample_path}")

    print(f"[2/3] Loading model from {args.weights} on device={args.device}")
    model = YOLO(args.weights)

    cap = cv2.VideoCapture(str(sample_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"      sample {W}x{H} @ {fps:.2f}fps, {n_total} frames, conf>={args.conf}")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(overlay_path), fourcc, fps, (W, H))

    rows = []
    n_detected = 0
    t0 = time.time()
    last_log = t0
    fi = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        results = model.predict(frame, conf=args.conf, device=args.device, verbose=False)[0]
        x = y = None
        best_conf = 0.0
        for box in results.boxes:
            c = float(box.conf[0])
            if c > best_conf:
                best_conf = c
                xyxy = box.xyxy[0].tolist()
                x = (xyxy[0] + xyxy[2]) / 2
                y = (xyxy[1] + xyxy[3]) / 2
        detected = x is not None
        if detected:
            n_detected += 1
            cv2.rectangle(
                frame,
                (int(x - 15), int(y - 15)),
                (int(x + 15), int(y + 15)),
                (0, 255, 255), 2,
            )
            cv2.putText(frame, f"{best_conf:.2f}", (int(x) + 18, int(y)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        cv2.putText(frame, f"f={fi} t={fi/fps:5.2f}s  detected={'Y' if detected else 'N'}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        writer.write(frame)
        rows.append((fi, fi / fps,
                     x if x is not None else "",
                     y if y is not None else "",
                     int(detected),
                     f"{best_conf:.3f}" if detected else ""))
        fi += 1
        now = time.time()
        if now - last_log > 5:
            elapsed = now - t0
            rate = fi / elapsed if elapsed > 0 else 0
            eta = (n_total - fi) / rate if rate else 0
            print(f"      frame {fi}/{n_total}  inf {rate:.1f}fps  "
                  f"detected {n_detected}/{fi} ({n_detected/fi*100:.0f}%)  ETA {eta:.0f}s")
            last_log = now

    cap.release(); writer.release()
    elapsed = time.time() - t0

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "t", "x", "y", "detected", "conf"])
        w.writerows(rows)

    detected_flags = [r[4] for r in rows]
    n = len(detected_flags)
    n_det = sum(detected_flags)
    rate = n_det / n * 100 if n else 0

    gaps, runs = [], []
    cur_run = cur_gap = 0
    for d in detected_flags:
        if d:
            cur_run += 1
            if cur_gap > 0:
                gaps.append(cur_gap); cur_gap = 0
        else:
            cur_gap += 1
            if cur_run > 0:
                runs.append(cur_run); cur_run = 0
    if cur_run: runs.append(cur_run)
    if cur_gap: gaps.append(cur_gap)

    print()
    print("=" * 60)
    print(f"[3/3] SUMMARY (YOLO  vs TrackNet 40.5%)")
    print(f"  Frames analyzed:     {n}")
    print(f"  Frames with ball:    {n_det}  ({rate:.1f}%)")
    print(f"  Inference:           {elapsed:.1f}s ({n/elapsed:.1f} fps)")
    if runs:
        print(f"  Detection runs:      n={len(runs)}, max={max(runs)}, mean={sum(runs)/len(runs):.1f}")
    if gaps:
        print(f"  Miss gaps:           n={len(gaps)}, max={max(gaps)}, mean={sum(gaps)/len(gaps):.1f}")
    print(f"  Overlay:             {overlay_path}")
    print(f"  CSV:                 {csv_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
