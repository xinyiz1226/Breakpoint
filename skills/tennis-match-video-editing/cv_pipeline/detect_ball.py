"""Stage 2: YOLOv5 ball detection over the full video.

Output CSV columns: frame, t, x, y, conf
Empty rows mean "no ball detected" (do NOT interpolate).
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import cv2

from . import paths


def filter_jumps(rows: list[tuple], max_jump: float = 200.0) -> list[tuple]:
    """Drop frames whose ball is > max_jump px away from BOTH neighbors.

    rows: list of (frame, x, y, conf). Returns filtered list.
    """
    if len(rows) < 3:
        return list(rows)
    out = [rows[0]]
    for i in range(1, len(rows) - 1):
        prev = rows[i - 1]
        cur = rows[i]
        nxt = rows[i + 1]
        d_prev = ((cur[1] - prev[1]) ** 2 + (cur[2] - prev[2]) ** 2) ** 0.5
        d_next = ((cur[1] - nxt[1]) ** 2 + (cur[2] - nxt[2]) ** 2) ** 0.5
        if d_prev > max_jump and d_next > max_jump:
            continue
        out.append(cur)
    out.append(rows[-1])
    return out


def detect(video: Path, out_csv: Path, conf_thresh: float = 0.15,
           device: str = "0", log_every: float = 30.0) -> dict:
    """Run YOLOv5 across video → write ball.csv. Returns summary dict."""
    from ultralytics import YOLO

    model = YOLO(str(paths.YOLOV5_BALL))

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cv2 cannot open: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    raw_rows: list[tuple] = []
    n_detected = 0
    t0 = time.time()
    last_log = t0
    fi = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        results = model.predict(frame, conf=conf_thresh, device=device, verbose=False)[0]
        best = None
        for box in results.boxes:
            c = float(box.conf[0])
            if best is None or c > best[2]:
                xyxy = box.xyxy[0].tolist()
                best = ((xyxy[0] + xyxy[2]) / 2, (xyxy[1] + xyxy[3]) / 2, c)
        if best:
            n_detected += 1
            raw_rows.append((fi, best[0], best[1], best[2]))
        fi += 1
        if time.time() - last_log > log_every:
            elapsed = time.time() - t0
            rate = fi / elapsed
            print(f"  [{fi}/{n_total}] {rate:.1f} fps, "
                  f"detected {n_detected}/{fi} ({n_detected/fi*100:.0f}%), "
                  f"ETA {(n_total-fi)/rate:.0f}s")
            last_log = time.time()
    cap.release()
    elapsed = time.time() - t0

    filtered = filter_jumps(raw_rows, max_jump=200.0)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    detected_frames = {r[0] for r in filtered}
    with out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "t", "x", "y", "conf"])
        # Write a row per video frame; empty x/y when no detection
        det_map = {r[0]: r for r in filtered}
        for f_idx in range(fi):
            r = det_map.get(f_idx)
            if r:
                w.writerow([f_idx, f"{f_idx/fps:.4f}", f"{r[1]:.2f}", f"{r[2]:.2f}", f"{r[3]:.3f}"])
            else:
                w.writerow([f_idx, f"{f_idx/fps:.4f}", "", "", ""])

    return {
        "n_frames": fi,
        "n_detected_raw": n_detected,
        "n_detected_filtered": len(filtered),
        "detection_rate": len(filtered) / fi if fi else 0.0,
        "elapsed_s": round(elapsed, 1),
        "fps_inference": round(fi / elapsed, 1) if elapsed > 0 else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--conf", type=float, default=0.15)
    ap.add_argument("--device", default="0")
    args = ap.parse_args()
    summary = detect(args.video, args.out, conf_thresh=args.conf, device=args.device)
    print(f"  detected {summary['n_detected_filtered']}/{summary['n_frames']} "
          f"({summary['detection_rate']*100:.1f}%) in {summary['elapsed_s']}s "
          f"({summary['fps_inference']} fps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
