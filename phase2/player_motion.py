import json
import cv2
import numpy as np
from pathlib import Path


CACHE_PATH = Path(__file__).resolve().parent / "rois_cache.json"


def select_rois(video_path: str) -> dict:
    video_name = Path(video_path).name
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text())
        if video_name in cache:
            print(f"  Using cached ROIs for {video_name}")
            return cache[video_name]

    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"Cannot read first frame from {video_path}")

    print("Select NEAR-SIDE player region (bottom of court), then press ENTER/SPACE.")
    near = cv2.selectROI("Select Near-Side ROI", frame, showCrosshair=True)
    print("Select FAR-SIDE player region (top of court), then press ENTER/SPACE.")
    far = cv2.selectROI("Select Far-Side ROI", frame, showCrosshair=True)
    cv2.destroyAllWindows()

    rois = {"near": list(near), "far": list(far)}

    cache = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text())
    cache[video_name] = rois
    CACHE_PATH.write_text(json.dumps(cache, indent=2))
    print(f"  ROIs saved to {CACHE_PATH}")

    return rois


def _roi_foreground_ratio(mask, roi):
    x, y, w, h = roi
    if w == 0 or h == 0:
        return 0.0
    crop = mask[y:y+h, x:x+w]
    return float(np.count_nonzero(crop)) / (w * h)


def analyze_motion(video_path: str, segments: list[dict], rois: dict) -> list[dict]:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    near_roi = rois["near"]
    far_roi = rois["far"]
    sample_interval = 2

    results = []
    for seg_idx, seg in enumerate(segments):
        warmup_start = max(0, seg["start"] - 0.5)
        warmup_frames = int((seg["start"] - warmup_start) * fps)

        start_frame = int(warmup_start * fps)
        end_frame = int(seg["end"] * fps)

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        mog = cv2.createBackgroundSubtractorMOG2(history=30, varThreshold=50, detectShadows=False)

        motion_values = []
        frame_count = 0
        total_frames = end_frame - start_frame

        while frame_count < total_frames:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1

            if frame_count <= warmup_frames:
                mog.apply(frame)
                continue

            if frame_count % sample_interval != 0:
                mog.apply(frame)
                continue

            mask = mog.apply(frame)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            near_ratio = _roi_foreground_ratio(mask, near_roi)
            far_ratio = _roi_foreground_ratio(mask, far_roi)
            motion_values.append(max(near_ratio, far_ratio))

        if motion_values:
            results.append({
                "player_motion_max": round(float(np.max(motion_values)), 6),
                "player_motion_var": round(float(np.var(np.diff(motion_values))), 8) if len(motion_values) > 1 else 0.0,
            })
        else:
            results.append({"player_motion_max": 0.0, "player_motion_var": 0.0})

        if (seg_idx + 1) % 10 == 0 or seg_idx == len(segments) - 1:
            print(f"  Motion analysis: {seg_idx + 1}/{len(segments)} segments")

    cap.release()
    return results


def _roi_frame_diff(gray, prev_gray, roi):
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
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
    from extract_audio import extract_audio
    from detect_hits import detect_hits
    from segment_points import segment_points

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
