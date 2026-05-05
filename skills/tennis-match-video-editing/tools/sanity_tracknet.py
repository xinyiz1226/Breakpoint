"""TrackNet sanity check on a DJI sample.

Cuts a 30s segment from the source video, runs TrackNet ball detection on every
frame at 360x640, and writes:
  - an overlay video with detected ball circles
  - a CSV of (frame, t, x, y, detected) rows
  - a printed summary: detection rate, gap stats
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from scipy.spatial import distance


class ConvBlock(nn.Module):
    def __init__(self, in_c, out_c, k=3, p=1, s=1):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_c, out_c, k, stride=s, padding=p),
            nn.ReLU(),
            nn.BatchNorm2d(out_c),
        )

    def forward(self, x):
        return self.block(x)


class BallTrackerNet(nn.Module):
    def __init__(self, in_ch=9, out_ch=256):
        super().__init__()
        self.conv1 = ConvBlock(in_ch, 64)
        self.conv2 = ConvBlock(64, 64)
        self.pool1 = nn.MaxPool2d(2, 2)
        self.conv3 = ConvBlock(64, 128)
        self.conv4 = ConvBlock(128, 128)
        self.pool2 = nn.MaxPool2d(2, 2)
        self.conv5 = ConvBlock(128, 256)
        self.conv6 = ConvBlock(256, 256)
        self.conv7 = ConvBlock(256, 256)
        self.pool3 = nn.MaxPool2d(2, 2)
        self.conv8 = ConvBlock(256, 512)
        self.conv9 = ConvBlock(512, 512)
        self.conv10 = ConvBlock(512, 512)
        self.ups1 = nn.Upsample(scale_factor=2)
        self.conv11 = ConvBlock(512, 256)
        self.conv12 = ConvBlock(256, 256)
        self.conv13 = ConvBlock(256, 256)
        self.ups2 = nn.Upsample(scale_factor=2)
        self.conv14 = ConvBlock(256, 128)
        self.conv15 = ConvBlock(128, 128)
        self.ups3 = nn.Upsample(scale_factor=2)
        self.conv16 = ConvBlock(128, 64)
        self.conv17 = ConvBlock(64, 64)
        self.conv18 = ConvBlock(64, out_ch)

    def forward(self, x):
        x = self.conv1(x); x = self.conv2(x); x = self.pool1(x)
        x = self.conv3(x); x = self.conv4(x); x = self.pool2(x)
        x = self.conv5(x); x = self.conv6(x); x = self.conv7(x); x = self.pool3(x)
        x = self.conv8(x); x = self.conv9(x); x = self.conv10(x)
        x = self.ups1(x); x = self.conv11(x); x = self.conv12(x); x = self.conv13(x)
        x = self.ups2(x); x = self.conv14(x); x = self.conv15(x)
        x = self.ups3(x); x = self.conv16(x); x = self.conv17(x)
        return self.conv18(x)


class BallDetector:
    def __init__(self, weights_path: str, device: str = "cpu"):
        self.device = device
        self.model = BallTrackerNet(in_ch=9, out_ch=256)
        state = torch.load(weights_path, map_location=device)
        self.model.load_state_dict(state)
        self.model.to(device).eval()
        self.W, self.H = 640, 360
        self.buf: deque = deque(maxlen=3)
        self.prev = [None, None]

    def step(self, frame_bgr):
        self.buf.append(frame_bgr)
        if len(self.buf) < 3:
            return None
        f2, f1, f0 = list(self.buf)
        a = cv2.resize(f0, (self.W, self.H))
        b = cv2.resize(f1, (self.W, self.H))
        c = cv2.resize(f2, (self.W, self.H))
        x = np.concatenate((a, b, c), axis=2).astype(np.float32) / 255.0
        x = np.rollaxis(x, 2, 0)
        x = np.expand_dims(x, 0)
        with torch.no_grad():
            t = torch.from_numpy(x).float().to(self.device)
            out = self.model(t)
            label = out.argmax(dim=1).cpu().numpy()
        xy = self._post(label)
        self.prev = list(xy) if xy[0] is not None else self.prev
        return xy

    def _post(self, fmap, scale_x=None, scale_y=None, max_dist=80):
        fmap = (fmap * 255).reshape(self.H, self.W).astype(np.uint8)
        _, heat = cv2.threshold(fmap, 127, 255, cv2.THRESH_BINARY)
        circles = cv2.HoughCircles(
            heat, cv2.HOUGH_GRADIENT, dp=1, minDist=1,
            param1=50, param2=2, minRadius=1, maxRadius=7,
        )
        if circles is None:
            return (None, None)
        # scale back to original frame size
        sx = scale_x or self.scale_x
        sy = scale_y or self.scale_y
        if self.prev[0] is not None:
            for cx, cy, _ in circles[0]:
                X, Y = cx * sx, cy * sy
                if distance.euclidean((X, Y), self.prev) < max_dist * max(sx, sy) / 2:
                    return (X, Y)
            return (None, None)
        cx, cy, _ = circles[0][0]
        return (cx * sx, cy * sy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--start", type=float, default=370.0, help="start sec in source")
    ap.add_argument("--duration", type=float, default=30.0, help="seconds to test")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sample_path = out_dir / "sample.mp4"
    overlay_path = out_dir / "overlay.mp4"
    csv_path = out_dir / "detections.csv"

    # 1. Cut sample with ffmpeg, downscale to 720p so opencv decodes faster.
    print(f"[1/3] Cutting {args.duration:.0f}s sample from {args.start:.1f}s...")
    import subprocess
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

    # 2. Run TrackNet on every frame.
    cap = cv2.VideoCapture(str(sample_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[2/3] Loaded sample {W}x{H} @ {fps:.2f}fps, {n_total} frames")

    det = BallDetector(args.weights, device="cpu")
    det.scale_x = W / det.W
    det.scale_y = H / det.H

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
        xy = det.step(frame)
        x, y = (xy if xy else (None, None))
        detected = x is not None
        if detected:
            n_detected += 1
            cv2.circle(frame, (int(x), int(y)), 12, (0, 255, 255), 2)
            cv2.circle(frame, (int(x), int(y)), 2, (0, 0, 255), -1)
        # HUD
        cv2.putText(frame, f"f={fi} t={fi/fps:5.2f}s  detected={'Y' if detected else 'N'}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        writer.write(frame)
        rows.append((fi, fi / fps, x if x is not None else "", y if y is not None else "", int(detected)))
        fi += 1
        now = time.time()
        if now - last_log > 5:
            elapsed = now - t0
            rate = fi / elapsed if elapsed > 0 else 0
            eta = (n_total - fi) / rate if rate else 0
            print(f"      frame {fi}/{n_total}  inf {rate:.1f}fps  detected so far {n_detected}/{fi} ({n_detected/fi*100:.0f}%)  ETA {eta:.0f}s")
            last_log = now

    cap.release(); writer.release()
    elapsed = time.time() - t0

    # 3. CSV + summary.
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "t", "x", "y", "detected"])
        w.writerows(rows)

    detected_flags = [r[4] for r in rows]
    n = len(detected_flags)
    n_det = sum(detected_flags)
    rate = n_det / n * 100 if n else 0

    # contiguous detection / gap stats
    gaps = []
    runs = []
    cur_run = 0
    cur_gap = 0
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
    print(f"[3/3] SUMMARY")
    print(f"  Frames analyzed:     {n}")
    print(f"  Frames with ball:    {n_det}  ({rate:.1f}%)")
    print(f"  Inference time:      {elapsed:.1f}s ({n/elapsed:.1f} fps)")
    if runs:
        print(f"  Detection runs:      n={len(runs)}, max={max(runs)}, mean={sum(runs)/len(runs):.1f} frames")
    if gaps:
        print(f"  Miss gaps:           n={len(gaps)}, max={max(gaps)}, mean={sum(gaps)/len(gaps):.1f} frames")
    print(f"  Overlay video:       {overlay_path}")
    print(f"  Detections CSV:      {csv_path}")
    print("=" * 60)
    print()
    if rate < 30:
        print("VERDICT: ❌ Detection rate too low. TrackNet does not generalize to this camera angle.")
    elif rate < 60:
        print("VERDICT: ⚠️  Marginal. Could be useful for trim refinement but not for full tracking.")
    else:
        print("VERDICT: ✅ Looks usable. Worth proceeding to bounce/trim integration.")


if __name__ == "__main__":
    main()
