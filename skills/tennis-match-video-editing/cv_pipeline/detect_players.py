"""Stage 3: YOLOv8n person detection, sampled every N frames.

Output CSV columns:
    frame, n_players, p1_x, p1_y, p2_x, p2_y, p3_x, p3_y, p4_x, p4_y
Coordinates are bbox center. Empty cells when fewer than 4 persons.
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import cv2

from . import paths


def filter_persons(persons: list[tuple], frame_h: int, max_n: int = 4) -> list[tuple]:
    """Filter person bboxes: keep only those mostly in lower half, cap at max_n by y2 desc.

    persons: list of (x1, y1, x2, y2, conf).
    """
    half = frame_h / 2
    in_lower = [p for p in persons if (p[1] + p[3]) / 2 > half]
    in_lower.sort(key=lambda p: p[3], reverse=True)  # bottom first
    return in_lower[:max_n]


def detect(video: Path, out_csv: Path, every: int = 5, device: str = "0",
           log_every: float = 30.0) -> dict:
    """Run YOLOv8n every `every` frames → write players.csv. Returns summary."""
    if every < 1:
        raise ValueError(f"every must be >= 1, got {every}")

    from ultralytics import YOLO

    if not paths.YOLOV8N_PERSON.exists():
        # ultralytics downloads yolov8n.pt to CWD by default; redirect to WEIGHTS_DIR for determinism
        paths.YOLOV8N_PERSON.parent.mkdir(parents=True, exist_ok=True)
        import os
        # ultralytics' YOLO("yolov8n.pt") auto-downloads to CWD if not present;
        # do that, then move into WEIGHTS_DIR for next time.
        prev_cwd = Path.cwd()
        os.chdir(paths.YOLOV8N_PERSON.parent)
        try:
            model = YOLO("yolov8n.pt")
        finally:
            os.chdir(prev_cwd)
    else:
        model = YOLO(str(paths.YOLOV8N_PERSON))

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cv2 cannot open: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    n_counts: list[int] = []
    t0 = time.time()
    last_log = t0
    fi = 0
    with out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "n_players",
                    "p1_x", "p1_y", "p2_x", "p2_y",
                    "p3_x", "p3_y", "p4_x", "p4_y"])
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if fi % every == 0:
                results = model.predict(frame, conf=0.35, classes=[0], device=device, verbose=False)[0]
                persons = []
                for box in results.boxes:
                    xyxy = box.xyxy[0].tolist()
                    persons.append((xyxy[0], xyxy[1], xyxy[2], xyxy[3], float(box.conf[0])))
                kept = filter_persons(persons, frame_h=h, max_n=4)
                row = [fi, len(kept)]
                for p in kept:
                    cx = (p[0] + p[2]) / 2
                    cy = (p[1] + p[3]) / 2
                    row.extend([f"{cx:.1f}", f"{cy:.1f}"])
                row.extend([""] * (10 - len(row)))
                w.writerow(row)
                n_counts.append(len(kept))
            fi += 1
            if time.time() - last_log > log_every:
                elapsed = time.time() - t0
                rate = fi / elapsed
                print(f"  [{fi}/{n_total}] {rate:.1f} fps, ETA {(n_total-fi)/rate:.0f}s")
                last_log = time.time()
    cap.release()

    elapsed = time.time() - t0
    avg_n = sum(n_counts) / len(n_counts) if n_counts else 0.0
    return {
        "n_frames_processed": fi,
        "n_samples": len(n_counts),
        "avg_n_players": round(avg_n, 2),
        "elapsed_s": round(elapsed, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--device", default="0")
    args = ap.parse_args()
    summary = detect(args.video, args.out, every=args.every, device=args.device)
    print(f"  {summary['n_samples']} samples, avg n_players={summary['avg_n_players']}, "
          f"{summary['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
