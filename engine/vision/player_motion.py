# -*- coding: utf-8 -*-
# 
# Copyright (C) 2026 Zhang Xinyi <xinyi.zhang@outlook.com>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import json
import cv2
import numpy as np
from pathlib import Path


import tempfile
CACHE_PATH = Path(tempfile.gettempdir()) / "breakpoint_rois_cache.json"


def _detect_court_corners(frame):
    """Auto-detect tennis court corners using white lines on blue court surface."""
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    court_mask = cv2.inRange(hsv, (90, 40, 50), (130, 255, 255))
    court_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    court_mask = cv2.morphologyEx(court_mask, cv2.MORPH_CLOSE, court_kernel, iterations=3)
    court_mask = cv2.morphologyEx(court_mask, cv2.MORPH_OPEN, court_kernel, iterations=2)

    dilated_court = cv2.dilate(court_mask, court_kernel, iterations=3)
    white_mask = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))
    white_mask = cv2.bitwise_and(white_mask, dilated_court)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    edges = cv2.Canny(white_mask, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60,
                            minLineLength=80, maxLineGap=30)
    if lines is None or len(lines) < 4:
        return None

    # Baselines: near-horizontal (<10° or >170°)
    # Sidelines: diagonal (20-80° or 100-160°)
    baselines = []
    sidelines = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180
        length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        mid_y = (y1 + y2) / 2
        mid_x = (x1 + x2) / 2
        if angle < 10 or angle > 170:
            baselines.append((x1, y1, x2, y2, length, angle, mid_y, mid_x))
        elif 20 <= angle <= 80 or 100 <= angle <= 160:
            sidelines.append((x1, y1, x2, y2, length, angle, mid_y, mid_x))

    if len(baselines) < 2 or len(sidelines) < 2:
        return None

    # Split baselines into far (top) and near (bottom) by y-position
    baseline_ys = sorted(set(int(l[6]) for l in baselines))
    if len(baseline_ys) < 2:
        return None
    y_gap = max(baseline_ys) - min(baseline_ys)
    if y_gap < 200:
        return None
    y_split = (min(baseline_ys) + max(baseline_ys)) / 2
    top_baselines = [l for l in baselines if l[6] < y_split]
    bot_baselines = [l for l in baselines if l[6] >= y_split]
    if not top_baselines or not bot_baselines:
        return None

    def _cluster_baselines(candidates):
        sorted_by_y = sorted(candidates, key=lambda l: l[6])
        clusters = []
        for l in sorted_by_y:
            if clusters and abs(l[6] - clusters[-1][-1][6]) < 30:
                clusters[-1].append(l)
            else:
                clusters.append([l])
        return clusters

    bot_clusters = _cluster_baselines(bot_baselines)
    bot_clusters.reverse()
    best_total_b = max(sum(l[4] for l in c) for c in bot_clusters)
    min_len_b = best_total_b * 0.15
    bot_cluster = next(c for c in bot_clusters if sum(l[4] for l in c) >= min_len_b)
    bot_line = max(bot_cluster, key=lambda l: l[4])

    top_clusters = _cluster_baselines(top_baselines)
    dominant_top = max(top_clusters, key=lambda c: sum(l[4] for l in c))
    dominant_y = int(np.mean([l[6] for l in dominant_top]))

    from scipy.ndimage import gaussian_filter1d
    from scipy.signal import find_peaks
    proj = np.sum(white_mask > 0, axis=1).astype(float)
    proj_smooth = gaussian_filter1d(proj, sigma=3)
    dominant_min_y = int(min(l[6] for l in dominant_top))
    search_top = max(0, dominant_min_y - 150)
    search_bot = dominant_min_y - 10
    if search_bot > search_top:
        sub = proj_smooth[search_top:search_bot]
        peaks, _ = find_peaks(sub, height=80, prominence=15)
        if len(peaks) > 0:
            best_peak = peaks[np.argmin(np.abs(search_top + peaks - dominant_min_y))]
            far_baseline_y = search_top + best_peak
            synthetic_top = (
                int(bot_line[0]), far_baseline_y,
                int(bot_line[2]), far_baseline_y,
                int(bot_line[4]), 0.0, float(far_baseline_y), float((bot_line[0] + bot_line[2]) / 2)
            )
            top_line = synthetic_top
        else:
            top_line = max(dominant_top, key=lambda l: l[4])
    else:
        top_line = max(dominant_top, key=lambda l: l[4])
    court_height = bot_line[6] - top_line[6]

    def line_params(l):
        x1, y1, x2, y2 = l[:4]
        a = y2 - y1
        b = x1 - x2
        c = a * x1 + b * y1
        return a, b, c

    def intersect(l1, l2):
        a1, b1, c1 = line_params(l1)
        a2, b2, c2 = line_params(l2)
        det = a1 * b2 - a2 * b1
        if abs(det) < 1e-6:
            return None
        x = (c1 * b2 - c2 * b1) / det
        y = (a1 * c2 - a2 * c1) / det
        return [int(round(x)), int(round(y))]

    # Score each sideline by how well its intersections with the baselines
    # land near the baseline endpoints (within frame, near baseline y)
    def score_sideline(sl):
        pt_top = intersect(top_line, sl)
        pt_bot = intersect(bot_line, sl)
        if pt_top is None or pt_bot is None:
            return -1
        # Intersection y should be close to the baseline y
        dy_top = abs(pt_top[1] - top_line[6])
        dy_bot = abs(pt_bot[1] - bot_line[6])
        if dy_top > 100 or dy_bot > 100:
            return -1
        # Intersection x should be within frame (with margin)
        if pt_top[0] < -50 or pt_top[0] > w + 50:
            return -1
        if pt_bot[0] < -50 or pt_bot[0] > w + 50:
            return -1
        return sl[4]  # use length as score among valid sidelines

    scored = [(score_sideline(sl), sl) for sl in sidelines]
    valid = [(s, sl) for s, sl in scored if s > 0]
    if len(valid) < 2:
        return None

    # Split valid sidelines into left/right by their intersection x with bot baseline
    for i, (s, sl) in enumerate(valid):
        pt_bot = intersect(bot_line, sl)
        valid[i] = (s, sl, pt_bot[0])  # add bot_x

    bot_mid_x = (bot_line[0] + bot_line[2]) / 2
    left_valid = [(s, sl) for s, sl, bx in valid if bx < bot_mid_x]
    right_valid = [(s, sl) for s, sl, bx in valid if bx >= bot_mid_x]

    if not left_valid or not right_valid:
        return None

    # Pick outermost sidelines (leftmost left, rightmost right)
    left_line = min(left_valid, key=lambda x: intersect(bot_line, x[1])[0])[1]
    right_line = max(right_valid, key=lambda x: intersect(bot_line, x[1])[0])[1]

    tl = intersect(top_line, left_line)
    tr = intersect(top_line, right_line)
    bl = intersect(bot_line, left_line)
    br = intersect(bot_line, right_line)

    if any(p is None for p in [tl, tr, bl, br]):
        return None

    margin = -100
    for pt in [tl, tr, bl, br]:
        if pt[0] < margin or pt[0] > w - margin or pt[1] < margin or pt[1] > h - margin:
            return None

    pts = np.array([tl, tr, br, bl], dtype=np.float64)
    area = 0.5 * abs(
        (pts[0][0] * pts[1][1] - pts[1][0] * pts[0][1]) +
        (pts[1][0] * pts[2][1] - pts[2][0] * pts[1][1]) +
        (pts[2][0] * pts[3][1] - pts[3][0] * pts[2][1]) +
        (pts[3][0] * pts[0][1] - pts[0][0] * pts[3][1])
    )
    frame_area = h * w
    if area < 0.05 * frame_area or area > 0.60 * frame_area:
        return None

    return {"tl": tl, "tr": tr, "bl": bl, "br": br}


def _corners_to_rois(corners):
    """Split court corners into near (bottom) and far (top) trapezoid ROIs."""
    tl, tr, bl, br = corners["tl"], corners["tr"], corners["bl"], corners["br"]
    # Net line = midpoints of sidelines
    mid_left = [int((tl[0] + bl[0]) / 2), int((tl[1] + bl[1]) / 2)]
    mid_right = [int((tr[0] + br[0]) / 2), int((tr[1] + br[1]) / 2)]

    far = [tl, tr, mid_right, mid_left]   # top half
    near = [mid_left, mid_right, br, bl]   # bottom half

    return {"near": near, "far": far, "format": "polygon"}


def _manual_select_corners(frame):
    """Interactive 4-point selection as fallback."""
    points = []
    clone = frame.copy()
    labels = ["top-left", "top-right", "bottom-right", "bottom-left"]

    def click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append([x, y])
            cv2.circle(clone, (x, y), 5, (0, 255, 0), -1)
            if len(points) > 1:
                cv2.line(clone, tuple(points[-2]), tuple(points[-1]), (0, 255, 0), 2)
            if len(points) == 4:
                cv2.line(clone, tuple(points[3]), tuple(points[0]), (0, 255, 0), 2)
            cv2.imshow("Select Court Corners", clone)

    cv2.namedWindow("Select Court Corners", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Select Court Corners", click)

    print("Click the 4 court corners in order: top-left, top-right, bottom-right, bottom-left")
    print("Press any key when done.")

    while True:
        cv2.imshow("Select Court Corners", clone)
        key = cv2.waitKey(50)
        if len(points) == 4 and key != -1:
            break

    cv2.destroyAllWindows()

    if len(points) != 4:
        raise RuntimeError("Need exactly 4 points for court corners")

    return {"tl": points[0], "tr": points[1], "bl": points[3], "br": points[2]}


def _convert_legacy_roi(roi_data):
    """Convert old [x, y, w, h] format to polygon format."""
    if roi_data.get("format") == "polygon":
        return roi_data
    near = roi_data["near"]
    far = roi_data["far"]
    x, y, w, h = near
    near_poly = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    x, y, w, h = far
    far_poly = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return {"near": near_poly, "far": far_poly, "format": "polygon"}


def select_rois(video_path: str) -> dict:
    video_name = Path(video_path).name
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text())
        if video_name in cache:
            roi_data = cache[video_name]
            roi_data = _convert_legacy_roi(roi_data)
            if roi_data is not cache.get(video_name):
                cache[video_name] = roi_data
                CACHE_PATH.write_text(json.dumps(cache, indent=2))
            print(f"  Using cached ROIs for {video_name}")
            return roi_data

    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"Cannot read first frame from {video_path}")

    print("  Attempting auto-detection of court corners...")
    corners = _detect_court_corners(frame)

    if corners is not None:
        print("  Court auto-detected successfully.")

    if corners is None:
        print("  Auto-detection failed. Skipping vision analysis.")
        return None

    rois = _corners_to_rois(corners)

    cache = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text())
    cache[video_name] = rois
    CACHE_PATH.write_text(json.dumps(cache, indent=2))
    print(f"  ROIs saved to {CACHE_PATH}")

    return rois


def _make_polygon_mask(shape, polygon):
    """Create a binary mask from a list of [x,y] points."""
    mask = np.zeros(shape[:2], dtype=np.uint8)
    pts = np.array(polygon, dtype=np.int32)
    cv2.fillPoly(mask, [pts], 255)
    return mask


def _roi_foreground_ratio(fg_mask, roi):
    if isinstance(roi[0], (list, tuple)):
        poly_mask = _make_polygon_mask(fg_mask.shape, roi)
        area = cv2.countNonZero(poly_mask)
        if area == 0:
            return 0.0
        masked = cv2.bitwise_and(fg_mask, poly_mask)
        return float(cv2.countNonZero(masked)) / area
    # Legacy rectangular fallback
    x, y, w, h = roi
    if w == 0 or h == 0:
        return 0.0
    crop = fg_mask[y:y+h, x:x+w]
    return float(np.count_nonzero(crop)) / (w * h)


def _scale_roi(roi, scale):
    """Scale polygon ROI coordinates by a factor."""
    return [[int(x * scale), int(y * scale)] for x, y in roi]


def _build_roi_cache(frame_shape, near_roi, far_roi):
    near_mask = _make_polygon_mask(frame_shape, near_roi)
    far_mask = _make_polygon_mask(frame_shape, far_roi)
    return {
        "near_mask": near_mask,
        "near_area": int(cv2.countNonZero(near_mask)),
        "far_mask": far_mask,
        "far_area": int(cv2.countNonZero(far_mask)),
    }


def _roi_foreground_ratio_cached(fg_mask, roi_mask, roi_area):
    if roi_area == 0:
        return 0.0
    masked = cv2.bitwise_and(fg_mask, roi_mask)
    return float(cv2.countNonZero(masked)) / roi_area


def _run_segment(cap, fps, scale, target_w, target_height, kernel,
                 sample_interval, seg, roi_cache):
    warmup_start = max(0.0, seg["start"] - 0.5)
    warmup_frames = int((seg["start"] - warmup_start) * fps)
    start_frame = int(warmup_start * fps)
    end_frame = int(seg["end"] * fps)

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    mog = cv2.createBackgroundSubtractorMOG2(history=30, varThreshold=50, detectShadows=False)

    motion_values: list[float] = []
    frame_count = 0
    total_frames = end_frame - start_frame

    while frame_count < total_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1

        if scale < 1.0:
            frame = cv2.resize(frame, (target_w, target_height), interpolation=cv2.INTER_AREA)

        if frame_count <= warmup_frames:
            mog.apply(frame)
            continue
        if frame_count % sample_interval != 0:
            mog.apply(frame)
            continue

        mask = mog.apply(frame)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        near_ratio = _roi_foreground_ratio_cached(mask, roi_cache["near_mask"], roi_cache["near_area"])
        far_ratio = _roi_foreground_ratio_cached(mask, roi_cache["far_mask"], roi_cache["far_area"])
        motion_values.append(max(near_ratio, far_ratio))

    if motion_values:
        return {
            "player_motion_max": round(float(np.max(motion_values)), 6),
            "player_motion_var": round(float(np.var(np.diff(motion_values))), 8) if len(motion_values) > 1 else 0.0,
        }
    return {"player_motion_max": 0.0, "player_motion_var": 0.0}


def analyze_motion(
    video_path: str,
    segments: list[dict],
    rois: dict,
    target_height: int = 540,
    progress_callback=None,
    _force_workers: int | None = None,
) -> list[dict]:
    if not segments:
        return []

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cap.release()

    scale = target_height / orig_h if orig_h > target_height else 1.0
    target_w = int(orig_w * scale) if scale < 1.0 else None
    kernel_size = 3 if scale < 0.75 else 5

    if scale < 1.0:
        near_roi = _scale_roi(rois["near"], scale)
        far_roi = _scale_roi(rois["far"], scale)
        frame_shape = (target_height, target_w)
    else:
        near_roi = rois["near"]
        far_roi = rois["far"]
        frame_shape = (orig_h, orig_w)

    roi_cache = _build_roi_cache(frame_shape, near_roi, far_roi)

    cap = cv2.VideoCapture(video_path)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    sample_interval = 4

    results: list[dict] = []
    for seg_idx, seg in enumerate(segments):
        result = _run_segment(
            cap, fps, scale, target_w, target_height, kernel,
            sample_interval, seg, roi_cache,
        )
        results.append(result)

        if (seg_idx + 1) % 10 == 0 or seg_idx == len(segments) - 1:
            print(f"  Motion analysis: {seg_idx + 1}/{len(segments)} segments")
        if progress_callback:
            progress_callback(seg_idx + 1, len(segments))

    cap.release()
    return results


def _roi_frame_diff(gray, prev_gray, roi):
    if isinstance(roi[0], (list, tuple)):
        poly_mask = _make_polygon_mask(gray.shape, roi)
        diff = cv2.absdiff(gray, prev_gray)
        masked = cv2.bitwise_and(diff, diff, mask=poly_mask)
        area = cv2.countNonZero(poly_mask)
        if area == 0:
            return 0.0
        return float(np.sum(masked)) / area
    # Legacy rectangular fallback
    x, y, w, h = roi
    if w == 0 or h == 0:
        return 0.0
    diff = cv2.absdiff(gray[y:y+h, x:x+w], prev_gray[y:y+h, x:x+w])
    return float(np.mean(diff))


def filter_hits_by_vision(
    video_path: str,
    hit_times: np.ndarray,
    hit_energies: np.ndarray,
    rois: dict,
    window_frames: int = 8,
    motion_threshold: float = 0.0,
    debug: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    near_roi = rois["near"]
    far_roi = rois["far"]
    motion_values = []

    for hit_idx, t in enumerate(hit_times):
        start_frame = max(0, int((t - window_frames / fps) * fps))
        n_frames = 2 * window_frames

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        prev_gray = None
        peak = 0.0

        for _ in range(n_frames):
            ret, frame = cap.read()
            if not ret:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                near_diff = _roi_frame_diff(gray, prev_gray, near_roi)
                far_diff = _roi_frame_diff(gray, prev_gray, far_roi)
                peak = max(peak, near_diff, far_diff)
            prev_gray = gray

        motion_values.append(peak)
        if debug and (hit_idx + 1) % 50 == 0:
            print(f"  Hit filter: {hit_idx + 1}/{len(hit_times)}")

    cap.release()

    motion_arr = np.array(motion_values)
    if debug:
        print(f"\n  Motion stats: min={motion_arr.min():.2f} max={motion_arr.max():.2f} "
              f"mean={motion_arr.mean():.2f} median={np.median(motion_arr):.2f}")
        percentiles = [10, 25, 50, 75, 90]
        pvals = np.percentile(motion_arr, percentiles)
        print(f"  Percentiles: " + " ".join(f"p{p}={v:.2f}" for p, v in zip(percentiles, pvals)))

    if motion_threshold <= 0:
        if debug:
            for i, (t, m) in enumerate(zip(hit_times, motion_values)):
                print(f"  hit {i+1}: t={t:.2f}s motion={m:.2f}")
        return hit_times, hit_energies

    keep = motion_arr >= motion_threshold
    filtered_times = hit_times[keep]
    filtered_energies = hit_energies[keep]
    removed = len(hit_times) - len(filtered_times)
    print(f"  Vision filter: {removed}/{len(hit_times)} hits removed (threshold={motion_threshold:.2f})")
    return filtered_times, filtered_energies


if __name__ == "__main__":
    import sys
    from engine.audio.extract import extract_audio
    from engine.audio.detect_hits import detect_hits
    from engine.segmentation import segment_points

    if len(sys.argv) < 2:
        print("Usage: python player_motion.py <video_path> [--filter-debug]")
        sys.exit(1)

    video_path = sys.argv[1]
    filter_debug = "--filter-debug" in sys.argv

    print("[1/3] Extracting audio...")
    audio_path = extract_audio(video_path)
    print("[2/3] Detecting hits...")
    hit_times, hit_energies, sr = detect_hits(audio_path)
    print(f"  Found {len(hit_times)} hits")

    print("[3/3] ROI selection + hit filter debug...")
    rois = select_rois(video_path)

    if filter_debug:
        filter_hits_by_vision(video_path, hit_times, hit_energies, rois, debug=True)
    else:
        points = segment_points(hit_times, hit_energies)
        print(f"  Found {len(points)} segments")
        print("Analyzing player motion...")
        motion_data = analyze_motion(video_path, points, rois)
        print("\nResults:")
        for i, (seg, motion) in enumerate(zip(points, motion_data)):
            dur = seg["end"] - seg["start"]
            print(f"  #{i+1}: {seg['start']:.1f}s-{seg['end']:.1f}s ({dur:.1f}s) "
                  f"motion_max={motion['player_motion_max']:.4f} "
                  f"motion_var={motion['player_motion_var']:.6f}")
