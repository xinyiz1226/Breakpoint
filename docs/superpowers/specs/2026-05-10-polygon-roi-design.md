# Design: Court Auto-Detection with Polygon ROI

## Date: 2026-05-10

## Context

Current ROI selection uses `cv2.selectROI()` which only supports rectangles. Tennis courts in perspective view are trapezoidal, so rectangular ROIs include irrelevant areas (adjacent courts, ground outside lines), reducing motion detection accuracy.

The drone footage (DJI, ~4m height, 1080p60) has fully visible white court lines in every frame.

## Design

### Court Detection Pipeline

1. **Extract first frame** from video
2. **White line extraction**: Convert to HSV, threshold for white pixels (high V, low S), morphological cleanup
3. **Line detection**: Canny edge detection → HoughLinesP to find straight lines
4. **Corner estimation**: Cluster detected lines into ~4 dominant directions (two baselines + two sidelines), compute intersections to get the 4 outer court corners
5. **Net line**: Midpoints of left-side pair and right-side pair → divides court into near/far trapezoids
6. **Cache**: Save 4-point polygons per video to `rois_cache.json`

### Fallback

If auto-detection fails (not enough lines detected, intersection geometry invalid), fall back to interactive 4-point selection via `cv2.setMouseCallback` — user clicks 4 corners on the frame.

### ROI Format Change

**Before**: `{"near": [x, y, w, h], "far": [x, y, w, h]}`
**After**: `{"near": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]], "far": [...], "format": "polygon"}`

Old rectangular entries detected by absence of `"format"` key — auto-converted on next run.

### Motion Analysis Changes

- `_roi_foreground_ratio(mask, roi)`: Generate polygon mask via `cv2.fillPoly()`, apply with `cv2.bitwise_and`, count nonzero within polygon area
- `_roi_frame_diff(gray, prev_gray, roi)`: Same polygon masking approach
- `filter_hits_by_vision()`: Same changes

### Files Modified

- `phase2/player_motion.py`: All changes (detection, masking, caching)
- `phase2/rois_cache.json`: Format migration

## Verification

1. Run on a test video, confirm court corners are detected correctly
2. Compare motion analysis output before/after to verify polygon masking works
3. Run `phase1/run_tests.py` to check overall pipeline quality
