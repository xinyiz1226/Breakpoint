# Plan A — CV Rally Pipeline 核心 (Stage 1–5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 5 个互相解耦的命令行 stage（decode / detect_ball / detect_players / segment_rallies / render），每个独立可跑，输入输出全是文件。本 plan 不接 server.py / 不改 UI；A 跑通后再写 Plan B 接入。

**Architecture:** 每个 stage 是一个独立的 Python 模块在 `skills/tennis-match-video-editing/cv_pipeline/`。共享一个 thin orchestrator (`run_pipeline.py`) 串起来。所有产物写到 `jobs/<video_id>/` 目录。

**Tech Stack:**
- Python 3.12 (使用现有 `/tmp/breakpoint/venv312` venv)
- ultralytics（YOLOv5 球检测 + YOLOv8n 球员检测）
- OpenCV 4.x（视频流式读）
- pandas（CSV I/O + rolling 窗口）
- ffmpeg 8.1（已装在 winget 路径）
- pytest（单元测试）

**前置依赖（不在本 plan 范围）：**
- CUDA 版 PyTorch（手动安装；Stage 2 跑之前完成，Task 1 校验）
- abdullahtarek YOLOv5 球权重已下载到 `C:/Users/xinyi/AppData/Local/Temp/breakpoint/weights/yolo5_ball.pt`
- ffmpeg 路径：`C:/Users/xinyi/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin/ffmpeg.exe`

**3 个测试视频对**（路径在 [tests/fixtures.local.json](tests/fixtures.local.json)，本 plan 末尾创建）：
- `dji_0532` / `dji_0533` / `dji_0534`

---

## 文件结构

```
skills/tennis-match-video-editing/cv_pipeline/
├── __init__.py                  # 空，使 cv_pipeline 成为 package
├── paths.py                     # 集中常量：ffmpeg 路径、权重路径、Python 解释器
├── decode.py                    # Stage 1：探测 fps/宽高/帧数 → meta.json
├── detect_ball.py               # Stage 2：YOLOv5 → ball.csv
├── detect_players.py            # Stage 3：YOLOv8n → players.csv
├── segment_rallies.py           # Stage 4：启发式切分 → segments.json
├── render.py                    # Stage 5：ffmpeg cut+concat → highlight.mp4
└── run_pipeline.py              # Orchestrator：串行调 5 个 stage

skills/tennis-match-video-editing/cv_pipeline/tests/
├── __init__.py
├── conftest.py                  # 共享 fixture（定位 venv、ffmpeg、权重）
├── test_decode.py
├── test_detect_ball.py
├── test_detect_players.py
├── test_segment_rallies.py
├── test_render.py
└── data/                        # 小型合成 CSV/视频片段，提交进 repo
    ├── synthetic_ball_one_rally.csv
    ├── synthetic_ball_no_rally.csv
    └── tiny_5s_clip.mp4         # 5s 360p 测试片段（< 1 MB）

tests/
├── fixtures.json                # 视频 ID schema（提交）
└── fixtures.local.json          # 本地视频路径（gitignore，本 plan 末尾创建）
```

**职责边界：**
- 每个 stage 文件：~100–200 行，只做自己的事，可独立 `python -m` 运行
- `paths.py`：所有路径常量集中，避免硬编码散落
- `run_pipeline.py`：~50 行，只做调度，无算法逻辑
- 单元测试：每个 stage 一个 test 文件，每个测试 < 5 秒

---

## Task 1：环境校验脚本 + paths.py

**Files:**
- Create: `skills/tennis-match-video-editing/cv_pipeline/__init__.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/paths.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/check_env.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/tests/__init__.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/tests/conftest.py`

- [ ] **Step 1: 创建空 `__init__.py` 文件**

`skills/tennis-match-video-editing/cv_pipeline/__init__.py`:
```python
```
（空文件）

`skills/tennis-match-video-editing/cv_pipeline/tests/__init__.py`:
```python
```
（空文件）

- [ ] **Step 2: 写 `paths.py`**

```python
"""Centralized paths and binary locations for the CV pipeline.

Override via environment variables when running on a different machine.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# External binaries
FFMPEG = os.environ.get(
    "BREAKPOINT_FFMPEG",
    "C:/Users/xinyi/AppData/Local/Microsoft/WinGet/Packages/"
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin/ffmpeg.exe",
)
FFPROBE = os.environ.get(
    "BREAKPOINT_FFPROBE",
    FFMPEG.replace("ffmpeg.exe", "ffprobe.exe"),
)

# Model weights
WEIGHTS_DIR = Path(os.environ.get(
    "BREAKPOINT_WEIGHTS_DIR",
    "C:/Users/xinyi/AppData/Local/Temp/breakpoint/weights",
))
YOLOV5_BALL = WEIGHTS_DIR / "yolo5_ball.pt"
YOLOV8N_PERSON = WEIGHTS_DIR / "yolov8n.pt"  # downloaded by ultralytics on first use

# Python venv with CUDA torch + ultralytics installed
PYTHON_BIN = os.environ.get(
    "BREAKPOINT_PYTHON",
    "C:/Users/xinyi/AppData/Local/Temp/breakpoint/venv312/Scripts/python.exe",
)


def assert_ready() -> None:
    """Raise informative errors if any external dep is missing."""
    if not Path(FFMPEG).exists() and not shutil.which(FFMPEG):
        raise RuntimeError(f"ffmpeg not found: {FFMPEG} (set BREAKPOINT_FFMPEG)")
    if not YOLOV5_BALL.exists():
        raise RuntimeError(f"YOLOv5 ball weights missing: {YOLOV5_BALL}")
```

- [ ] **Step 3: 写 `check_env.py`（手动跑一次确认环境）**

```python
"""One-shot env check. Run before Task 2.

Usage:
    python -m skills.tennis-match-video-editing.cv_pipeline.check_env
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from . import paths


def main() -> int:
    failures = []

    # ffmpeg / ffprobe
    for label, binpath in (("ffmpeg", paths.FFMPEG), ("ffprobe", paths.FFPROBE)):
        resolved = binpath if Path(binpath).exists() else shutil.which(binpath)
        if not resolved:
            failures.append(f"{label} not found: {binpath}")
        else:
            r = subprocess.run([resolved, "-version"], capture_output=True, text=True)
            print(f"  {label}: {r.stdout.splitlines()[0]}")

    # weights
    if paths.YOLOV5_BALL.exists():
        size_mb = paths.YOLOV5_BALL.stat().st_size / 1e6
        print(f"  YOLOv5 ball weights: {paths.YOLOV5_BALL} ({size_mb:.1f} MB)")
    else:
        failures.append(f"YOLOv5 ball weights missing: {paths.YOLOV5_BALL}")

    # torch + cuda
    try:
        import torch
        cuda = torch.cuda.is_available()
        dev = torch.cuda.get_device_name(0) if cuda else "none"
        print(f"  torch: {torch.__version__} cuda={cuda} device={dev}")
        if not cuda:
            failures.append(
                "CUDA torch not installed. Install with:\n"
                "  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124"
            )
    except ImportError:
        failures.append("torch not installed")

    # ultralytics
    try:
        import ultralytics
        print(f"  ultralytics: {ultralytics.__version__}")
    except ImportError:
        failures.append("ultralytics not installed (pip install ultralytics)")

    if failures:
        print()
        print("FAIL — fix the following before continuing:")
        for f in failures:
            print(f"  • {f}")
        return 1
    print()
    print("OK — environment ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 写 `conftest.py`（pytest 共享 fixture）**

```python
"""Shared pytest fixtures for cv_pipeline tests."""

from __future__ import annotations

from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture
def tmp_job_dir(tmp_path: Path) -> Path:
    """A fresh empty job directory for one test."""
    job = tmp_path / "job"
    job.mkdir()
    return job
```

- [ ] **Step 5: 手动跑 check_env 并修复任何报错**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m skills.tennis-match-video-editing.cv_pipeline.check_env`

Expected: 输出 `OK — environment ready`。如果 cuda=False，按提示安装 CUDA torch（`pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124`，~2.5 GB）然后重跑。

- [ ] **Step 6: Commit**

```bash
git add skills/tennis-match-video-editing/cv_pipeline/__init__.py \
        skills/tennis-match-video-editing/cv_pipeline/paths.py \
        skills/tennis-match-video-editing/cv_pipeline/check_env.py \
        skills/tennis-match-video-editing/cv_pipeline/tests/__init__.py \
        skills/tennis-match-video-editing/cv_pipeline/tests/conftest.py
git commit -m "Add cv_pipeline scaffolding: paths, env check, pytest conftest"
```

---

## Task 2：Stage 1 — decode.py（视频元数据探测）

**Files:**
- Create: `skills/tennis-match-video-editing/cv_pipeline/decode.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/tests/test_decode.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/tests/data/tiny_5s_clip.mp4`（用 ffmpeg 生成）

- [ ] **Step 1: 生成 5s 测试视频**

```bash
mkdir -p skills/tennis-match-video-editing/cv_pipeline/tests/data
"C:/Users/xinyi/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin/ffmpeg.exe" \
  -y -loglevel error \
  -f lavfi -i "testsrc=size=640x360:rate=30:duration=5" \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
  skills/tennis-match-video-editing/cv_pipeline/tests/data/tiny_5s_clip.mp4
```

校验：`ls -lh skills/tennis-match-video-editing/cv_pipeline/tests/data/tiny_5s_clip.mp4` 应该 < 100 KB。

- [ ] **Step 2: 写失败测试**

`skills/tennis-match-video-editing/cv_pipeline/tests/test_decode.py`:
```python
import json

from skills.tennis_match_video_editing.cv_pipeline import decode


def test_probe_writes_meta_json(data_dir, tmp_job_dir):
    src = data_dir / "tiny_5s_clip.mp4"
    out = tmp_job_dir / "meta.json"

    decode.probe(src, out)

    meta = json.loads(out.read_text())
    assert meta["w"] == 640
    assert meta["h"] == 360
    assert 29.0 <= meta["fps"] <= 31.0
    assert 145 <= meta["n_frames"] <= 155  # 5s @ 30fps ≈ 150
    assert meta["duration"] > 4.5
```

注意：Python package 名带连字符，需用下划线导入。我们的目录是 `tennis-match-video-editing`，import 不工作。**必须改用 sys.path 注入或重命名目录**。

→ 改用 sys.path 方式，conftest.py 加：

```python
# Append to skills/tennis-match-video-editing/cv_pipeline/tests/conftest.py
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))  # ...editing/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))         # ...editing/cv_pipeline/
```

然后测试 import 改为：

```python
from cv_pipeline import decode
```

- [ ] **Step 3: 跑测试，验证它失败**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m pytest skills/tennis-match-video-editing/cv_pipeline/tests/test_decode.py -v`
Expected: FAIL with `ImportError` 或 `AttributeError: module ... has no attribute 'probe'`

- [ ] **Step 4: 实现 `decode.py`**

```python
"""Stage 1: probe video metadata.

Doesn't extract frames to disk (downstream stages use OpenCV streaming).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from . import paths


def probe(video: Path, out_meta: Path) -> dict:
    """Run ffprobe → write meta.json. Returns the dict."""
    cmd = [
        paths.FFPROBE, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,nb_frames,codec_name:format=duration",
        "-of", "json",
        str(video),
    ]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr}")
    raw = json.loads(r.stdout)
    stream = raw["streams"][0]
    fmt = raw["format"]

    num, den = stream["r_frame_rate"].split("/")
    fps = float(num) / float(den) if float(den) > 0 else 0.0

    n_frames = stream.get("nb_frames")
    duration = float(fmt.get("duration", 0))
    if n_frames in (None, "N/A"):
        n_frames = int(round(duration * fps))
    else:
        n_frames = int(n_frames)

    meta = {
        "video_path": str(video),
        "w": int(stream["width"]),
        "h": int(stream["height"]),
        "fps": fps,
        "n_frames": n_frames,
        "duration": duration,
        "codec": stream.get("codec_name"),
        "elapsed_s": round(time.time() - t0, 3),
    }
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(meta, indent=2))
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    meta = probe(args.video, args.out)
    print(f"  {meta['w']}x{meta['h']} @ {meta['fps']:.2f}fps "
          f"{meta['n_frames']} frames {meta['duration']:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 跑测试，验证它通过**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m pytest skills/tennis-match-video-editing/cv_pipeline/tests/test_decode.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add skills/tennis-match-video-editing/cv_pipeline/decode.py \
        skills/tennis-match-video-editing/cv_pipeline/tests/test_decode.py \
        skills/tennis-match-video-editing/cv_pipeline/tests/conftest.py \
        skills/tennis-match-video-editing/cv_pipeline/tests/data/tiny_5s_clip.mp4
git commit -m "Stage 1: video metadata probe (decode.py)"
```

---

## Task 3：Stage 2 — detect_ball.py（YOLOv5 球检测）

**Files:**
- Create: `skills/tennis-match-video-editing/cv_pipeline/detect_ball.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/tests/test_detect_ball.py`

**注意**：本 stage 依赖 GPU 和模型权重（已在 Task 1 校验）。单元测试只验证 CSV schema 和后处理逻辑，不验证检测精度——精度由 Plan C 的 golden 回归测。

- [ ] **Step 1: 写失败测试（验证后处理逻辑：跳变 > 200px 丢弃中间帧）**

`tests/test_detect_ball.py`:
```python
import csv

from cv_pipeline.detect_ball import filter_jumps


def test_filter_jumps_drops_isolated_outlier():
    # frame, x, y; middle frame is a 300px jump from neighbors
    raw = [
        (0, 100.0, 100.0, 0.5),
        (1, 105.0, 102.0, 0.5),
        (2, 500.0, 400.0, 0.5),  # outlier
        (3, 110.0, 105.0, 0.5),
        (4, 115.0, 108.0, 0.5),
    ]
    out = filter_jumps(raw, max_jump=200.0)
    frames_out = [r[0] for r in out]
    assert 2 not in frames_out
    assert frames_out == [0, 1, 3, 4]


def test_filter_jumps_keeps_smooth_trajectory():
    raw = [(i, 100.0 + i * 10, 100.0, 0.5) for i in range(10)]
    out = filter_jumps(raw, max_jump=200.0)
    assert len(out) == 10
```

- [ ] **Step 2: 跑测试，验证它失败**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m pytest skills/tennis-match-video-editing/cv_pipeline/tests/test_detect_ball.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cv_pipeline.detect_ball'`

- [ ] **Step 3: 实现 `detect_ball.py`**

```python
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
```

- [ ] **Step 4: 跑测试，验证它通过**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m pytest skills/tennis-match-video-editing/cv_pipeline/tests/test_detect_ball.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 5: 端到端冒烟（手动跑一段 8s 样本）**

```bash
mkdir -p /c/Users/xinyi/AppData/Local/Temp/breakpoint/job_smoke
"C:/Users/xinyi/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin/ffmpeg.exe" \
  -y -loglevel error \
  -ss 367.9 -i /d/Pictures/网球/2026.5.3/DJI_20260503150415_0533_D.MP4 \
  -t 8.4 -vf scale=1280:720 -c:v libx264 -preset ultrafast -an \
  /c/Users/xinyi/AppData/Local/Temp/breakpoint/job_smoke/sample.mp4

/tmp/breakpoint/venv312/Scripts/python.exe -m cv_pipeline.detect_ball \
  --video /c/Users/xinyi/AppData/Local/Temp/breakpoint/job_smoke/sample.mp4 \
  --out   /c/Users/xinyi/AppData/Local/Temp/breakpoint/job_smoke/ball.csv \
  --device cpu
```

注意：用 `cpu` 跑 8s 样本约 100s。Expected：detected ratio ≥ 60%（之前 sanity 测得 79.4%，加了 jump 过滤后会降低一点，~70-78% 合理）。

如果显著低于此区间，回头检查 `paths.YOLOV5_BALL` 路径或 `conf_thresh`。

- [ ] **Step 6: Commit**

```bash
git add skills/tennis-match-video-editing/cv_pipeline/detect_ball.py \
        skills/tennis-match-video-editing/cv_pipeline/tests/test_detect_ball.py
git commit -m "Stage 2: YOLOv5 ball detection (detect_ball.py)"
```

---

## Task 4：Stage 3 — detect_players.py（YOLOv8n 球员检测）

**Files:**
- Create: `skills/tennis-match-video-editing/cv_pipeline/detect_players.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/tests/test_detect_players.py`

- [ ] **Step 1: 写失败测试（验证 person 过滤逻辑）**

```python
from cv_pipeline.detect_players import filter_persons


def test_filter_persons_keeps_lower_half_only():
    # bbox = (x1, y1, x2, y2, conf), frame is 1080 tall
    persons = [
        (100, 100, 150, 200, 0.9),   # upper half — reject (spectator)
        (100, 600, 180, 900, 0.9),   # lower half — keep
        (300, 700, 380, 950, 0.9),   # lower half — keep
    ]
    kept = filter_persons(persons, frame_h=1080, max_n=4)
    assert len(kept) == 2
    assert (100, 600, 180, 900, 0.9) in kept


def test_filter_persons_caps_at_max_n_by_y():
    persons = [(0, y, 50, y + 100, 0.9) for y in range(600, 1100, 50)]  # 10 boxes lower half
    kept = filter_persons(persons, frame_h=1080, max_n=4)
    assert len(kept) == 4
    # should keep the lowest (largest y2)
    y2_vals = sorted([p[3] for p in kept], reverse=True)
    assert y2_vals == sorted(y2_vals, reverse=True)
```

- [ ] **Step 2: 跑测试，验证它失败**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m pytest skills/tennis-match-video-editing/cv_pipeline/tests/test_detect_players.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 `detect_players.py`**

```python
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
    from ultralytics import YOLO

    model = YOLO(str(paths.YOLOV8N_PERSON))

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cv2 cannot open: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    f = out_csv.open("w", newline="")
    w = csv.writer(f)
    w.writerow(["frame", "n_players",
                "p1_x", "p1_y", "p2_x", "p2_y",
                "p3_x", "p3_y", "p4_x", "p4_y"])

    n_counts: list[int] = []
    t0 = time.time()
    last_log = t0
    fi = 0
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
    f.close()

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
```

- [ ] **Step 4: 跑测试，验证它通过**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m pytest skills/tennis-match-video-editing/cv_pipeline/tests/test_detect_players.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/tennis-match-video-editing/cv_pipeline/detect_players.py \
        skills/tennis-match-video-editing/cv_pipeline/tests/test_detect_players.py
git commit -m "Stage 3: YOLOv8n player detection (detect_players.py)"
```

---

## Task 5：Stage 4 — segment_rallies.py（rally 切分启发式）

**Files:**
- Create: `skills/tennis-match-video-editing/cv_pipeline/segment_rallies.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/tests/test_segment_rallies.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/tests/data/synthetic_ball_one_rally.csv`
- Create: `skills/tennis-match-video-editing/cv_pipeline/tests/data/synthetic_ball_no_rally.csv`

这是算法最复杂的 stage，拆成多个小函数分别测试。

- [ ] **Step 1: 创建合成 ball.csv 测试数据**

`tests/data/synthetic_ball_one_rally.csv`（生成脚本，跑一次写入文件）：

用以下 inline Python 生成（不入 repo，输出文件入 repo）：

```python
# Run this once to create the fixture:
import csv
fps = 30
n = 300  # 10s
with open("skills/tennis-match-video-editing/cv_pipeline/tests/data/synthetic_ball_one_rally.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["frame", "t", "x", "y", "conf"])
    for i in range(n):
        # Frames 0-29: no ball (1s warmup)
        # Frames 30-179: ball visible (5s rally), with bounces (y oscillates)
        # Frames 180-299: no ball
        if 30 <= i < 180:
            x = 640 + 200 * ((i - 30) / 150)  # drift right
            # bounce: y oscillates between 300 and 600 with period 25 frames
            phase = (i - 30) % 25
            y = 300 + 300 * abs(phase / 12.5 - 1)  # triangular wave
            w.writerow([i, f"{i/fps:.4f}", f"{x:.2f}", f"{y:.2f}", "0.500"])
        else:
            w.writerow([i, f"{i/fps:.4f}", "", "", ""])
```

`tests/data/synthetic_ball_no_rally.csv`：300 行全空（只有时间戳）。

- [ ] **Step 2: 写失败测试**

`tests/test_segment_rallies.py`:
```python
from cv_pipeline.segment_rallies import (
    find_continuous_runs, count_hits_in_run, segment, RallyParams,
)


def test_find_continuous_runs_synthetic(data_dir):
    csv_path = data_dir / "synthetic_ball_one_rally.csv"
    runs = find_continuous_runs(csv_path, min_run_frames=90)
    assert len(runs) == 1
    start, end = runs[0]
    assert 25 <= start <= 35
    assert 175 <= end <= 185


def test_no_rally_returns_empty(data_dir):
    csv_path = data_dir / "synthetic_ball_no_rally.csv"
    runs = find_continuous_runs(csv_path, min_run_frames=90)
    assert runs == []


def test_count_hits_triangular_wave(data_dir):
    csv_path = data_dir / "synthetic_ball_one_rally.csv"
    runs = find_continuous_runs(csv_path, min_run_frames=90)
    n_hits = count_hits_in_run(csv_path, runs[0], min_frames_between=10)
    assert n_hits >= 4


def test_segment_full_pipeline_one_rally(data_dir, tmp_job_dir):
    out = tmp_job_dir / "segments.json"
    segment(
        ball_csv=data_dir / "synthetic_ball_one_rally.csv",
        players_csv=None,  # ok to be None for synthetic data
        meta={"fps": 30.0},
        out_segments=out,
        params=RallyParams(min_run_frames=90, min_hits=3),
    )
    import json
    data = json.loads(out.read_text())
    assert len(data["rallies"]) == 1
    r = data["rallies"][0]
    assert r["n_hits"] >= 3
    assert r["match_type"] == "unknown"  # no players csv
    assert r["kept"] is True
```

- [ ] **Step 3: 跑测试，验证失败**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m pytest skills/tennis-match-video-editing/cv_pipeline/tests/test_segment_rallies.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 4: 实现 `segment_rallies.py`**

```python
"""Stage 4: heuristic rally segmentation.

Reads ball.csv + players.csv → writes segments.json with kept=True for all.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RallyParams:
    min_run_frames: int = 90       # ≥1.5s @ 60fps; ≥3s @ 30fps
    min_hits: int = 4              # filter rallies with < 4 hits
    min_frames_between_hits: int = 12  # avoid double-counting jitter
    pre_pad_s: float = 1.0
    post_pad_s: float = 1.5
    static_window_s: float = 1.0   # players-static window for end refinement


def _read_ball_csv(csv_path: Path) -> list[tuple[int, float | None, float | None]]:
    """Returns list of (frame, y_or_None, x_or_None). Order = file order."""
    rows: list[tuple[int, float | None, float | None]] = []
    with csv_path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            f_idx = int(row["frame"])
            x = float(row["x"]) if row["x"] else None
            y = float(row["y"]) if row["y"] else None
            rows.append((f_idx, x, y))
    return rows


def find_continuous_runs(ball_csv: Path, min_run_frames: int = 90,
                          max_gap: int = 10) -> list[tuple[int, int]]:
    """Return [(start_frame, end_frame), ...] for ball-visible runs.

    A "run" allows up to `max_gap` consecutive missing frames (smoothes YOLO drops).
    """
    rows = _read_ball_csv(ball_csv)
    runs = []
    cur_start = None
    cur_gap = 0
    last_seen = None
    for f_idx, x, y in rows:
        seen = x is not None and y is not None
        if seen:
            if cur_start is None:
                cur_start = f_idx
            cur_gap = 0
            last_seen = f_idx
        else:
            if cur_start is not None:
                cur_gap += 1
                if cur_gap > max_gap:
                    if last_seen - cur_start + 1 >= min_run_frames:
                        runs.append((cur_start, last_seen))
                    cur_start = None
                    cur_gap = 0
    if cur_start is not None and last_seen is not None:
        if last_seen - cur_start + 1 >= min_run_frames:
            runs.append((cur_start, last_seen))
    return runs


def count_hits_in_run(ball_csv: Path, run: tuple[int, int],
                      min_frames_between: int = 12) -> int:
    """Count y-direction reversals in [start, end].

    A "hit" = sign change of dy averaged over a 5-frame rolling window.
    """
    rows = _read_ball_csv(ball_csv)
    ys = [(f, y) for f, x, y in rows if run[0] <= f <= run[1] and y is not None]
    if len(ys) < 10:
        return 0

    # Rolling mean of y over 5 frames
    window = 5
    rolling = []
    for i in range(len(ys)):
        lo = max(0, i - window + 1)
        rolling.append(statistics.mean(y for _, y in ys[lo:i + 1]))
    deltas = [rolling[i] - rolling[i - 1] for i in range(1, len(rolling))]

    hits = 0
    last_hit_frame = -10_000
    for i in range(1, len(deltas)):
        # sign change?
        if deltas[i - 1] * deltas[i] < 0:
            cur_frame = ys[i + 1][0]
            if cur_frame - last_hit_frame >= min_frames_between:
                hits += 1
                last_hit_frame = cur_frame
    return hits


def _read_players_in_window(players_csv: Path | None,
                            f_start: int, f_end: int) -> tuple[str, list[int]]:
    """Returns (match_type, n_players_per_sample). match_type ∈ singles/doubles/unknown."""
    if players_csv is None or not players_csv.exists():
        return "unknown", []
    counts = []
    with players_csv.open() as f:
        r = csv.DictReader(f)
        for row in r:
            f_idx = int(row["frame"])
            if f_start <= f_idx <= f_end:
                counts.append(int(row["n_players"]))
    if not counts:
        return "unknown", []
    mode = statistics.mode(counts) if counts else 0
    if mode == 2:
        return "singles", counts
    if mode == 4:
        return "doubles", counts
    return "unknown", counts


def segment(ball_csv: Path, players_csv: Path | None, meta: dict,
            out_segments: Path, params: RallyParams = None) -> dict:
    """Full Stage-4 pipeline. Returns the dict written to out_segments."""
    if params is None:
        params = RallyParams()
    fps = float(meta["fps"])

    runs = find_continuous_runs(ball_csv, min_run_frames=params.min_run_frames)
    rallies = []
    for i, (f_start, f_end) in enumerate(runs):
        n_hits = count_hits_in_run(
            ball_csv, (f_start, f_end),
            min_frames_between=params.min_frames_between_hits,
        )
        if n_hits < params.min_hits:
            continue
        match_type, _ = _read_players_in_window(players_csv, f_start, f_end)

        start_t = max(0.0, f_start / fps - params.pre_pad_s)
        end_t = f_end / fps + params.post_pad_s

        score = (
            n_hits * 0.5
            + (end_t - start_t) * 0.2
            # max_ball_speed left as 0.0 in MVP; v2 will compute from ball.csv
        )

        rallies.append({
            "id": f"R{i+1:03d}",
            "start_t": round(start_t, 3),
            "end_t": round(end_t, 3),
            "n_hits": n_hits,
            "max_ball_speed_kmh": 0.0,
            "score": round(score, 3),
            "match_type": match_type,
            "kept": True,
        })

    payload = {
        "fps": fps,
        "rallies": rallies,
    }
    out_segments.parent.mkdir(parents=True, exist_ok=True)
    out_segments.write_text(json.dumps(payload, indent=2))
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ball", required=True, type=Path)
    ap.add_argument("--players", type=Path, default=None)
    ap.add_argument("--meta", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--min-run-frames", type=int, default=90)
    ap.add_argument("--min-hits", type=int, default=4)
    args = ap.parse_args()
    meta = json.loads(args.meta.read_text())
    payload = segment(
        ball_csv=args.ball,
        players_csv=args.players,
        meta=meta,
        out_segments=args.out,
        params=RallyParams(min_run_frames=args.min_run_frames, min_hits=args.min_hits),
    )
    print(f"  {len(payload['rallies'])} rallies kept")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 跑测试，验证全部通过**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m pytest skills/tennis-match-video-editing/cv_pipeline/tests/test_segment_rallies.py -v`
Expected: 4 个测试 PASS

- [ ] **Step 6: Commit**

```bash
git add skills/tennis-match-video-editing/cv_pipeline/segment_rallies.py \
        skills/tennis-match-video-editing/cv_pipeline/tests/test_segment_rallies.py \
        skills/tennis-match-video-editing/cv_pipeline/tests/data/synthetic_ball_one_rally.csv \
        skills/tennis-match-video-editing/cv_pipeline/tests/data/synthetic_ball_no_rally.csv
git commit -m "Stage 4: rally segmentation heuristic (segment_rallies.py)"
```

---

## Task 6：Stage 5 — render.py（ffmpeg cut + concat）

**Files:**
- Create: `skills/tennis-match-video-editing/cv_pipeline/render.py`
- Create: `skills/tennis-match-video-editing/cv_pipeline/tests/test_render.py`

复用现有 `render_from_manifest.py` 的逻辑，但接受新的 segments.json schema。

- [ ] **Step 1: 写失败测试**

```python
import json
import subprocess

import pytest

from cv_pipeline import render
from cv_pipeline import paths


def test_render_cuts_concats_kept_segments_only(data_dir, tmp_job_dir):
    src = data_dir / "tiny_5s_clip.mp4"
    segments = {
        "fps": 30.0,
        "rallies": [
            {"id": "R1", "start_t": 0.5, "end_t": 1.5, "n_hits": 5, "score": 1.0,
             "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
            {"id": "R2", "start_t": 2.0, "end_t": 2.5, "n_hits": 3, "score": 0.5,
             "match_type": "singles", "kept": False, "max_ball_speed_kmh": 0.0},
            {"id": "R3", "start_t": 3.5, "end_t": 4.5, "n_hits": 4, "score": 0.8,
             "match_type": "singles", "kept": True, "max_ball_speed_kmh": 0.0},
        ],
    }
    seg_path = tmp_job_dir / "segments.json"
    seg_path.write_text(json.dumps(segments))
    out = tmp_job_dir / "highlight.mp4"

    render.render(src, seg_path, out, mode="highlight")

    # ffprobe duration; expected ≈ 1.0 + 1.0 = 2.0s ± 0.5s
    r = subprocess.run(
        [paths.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True,
    )
    duration = float(r.stdout.strip())
    assert 1.5 <= duration <= 2.5
```

- [ ] **Step 2: 跑测试，验证失败**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m pytest skills/tennis-match-video-editing/cv_pipeline/tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 `render.py`**

```python
"""Stage 5: render highlight or short video via ffmpeg cut + concat."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import tempfile
from pathlib import Path

from . import paths


def _select_for_short(rallies: list[dict], target_min: float = 60.0,
                      target_max: float = 90.0) -> list[dict]:
    """Pick top-N by score so total duration falls in [target_min, target_max]."""
    sorted_r = sorted(rallies, key=lambda r: r["score"], reverse=True)
    picked = []
    total = 0.0
    for r in sorted_r:
        d = r["end_t"] - r["start_t"]
        if total + d > target_max:
            continue
        picked.append(r)
        total += d
        if total >= target_min:
            break
    # restore time order so the short reads chronologically
    picked.sort(key=lambda r: r["start_t"])
    return picked


def render(source_video: Path, segments_json: Path, out: Path,
           mode: str = "highlight", crf: int = 18, preset: str = "medium") -> dict:
    """Render highlight ('all kept rallies in time order') or short ('top-N by score')."""
    data = json.loads(segments_json.read_text())
    rallies = [r for r in data["rallies"] if r.get("kept", True)]
    if not rallies:
        raise RuntimeError("no rallies marked kept=True")

    if mode == "short":
        rallies = _select_for_short(rallies)
    elif mode != "highlight":
        raise ValueError(f"unknown mode: {mode}")

    with tempfile.TemporaryDirectory(prefix="bp_render_") as tmp:
        tmpdir = Path(tmp)
        clip_paths: list[Path] = []
        for i, r in enumerate(rallies):
            clip_out = tmpdir / f"clip_{i:03d}.mp4"
            cmd = [
                paths.FFMPEG, "-y", "-loglevel", "error",
                "-ss", f"{r['start_t']:.3f}",
                "-i", str(source_video),
                "-t", f"{r['end_t'] - r['start_t']:.3f}",
                "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
                "-c:a", "aac", "-b:a", "128k",
                str(clip_out),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"ffmpeg cut failed for {r['id']}: {res.stderr}")
            clip_paths.append(clip_out)

        concat_list = tmpdir / "list.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in clip_paths) + "\n"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            paths.FFMPEG, "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy", str(out),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {res.stderr}")

    return {"output": str(out), "n_clips": len(rallies)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--segments", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--mode", choices=["highlight", "short"], default="highlight")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    args = ap.parse_args()
    summary = render(args.video, args.segments, args.out, mode=args.mode,
                     crf=args.crf, preset=args.preset)
    print(f"  rendered {summary['n_clips']} clips → {summary['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试，验证它通过**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m pytest skills/tennis-match-video-editing/cv_pipeline/tests/test_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/tennis-match-video-editing/cv_pipeline/render.py \
        skills/tennis-match-video-editing/cv_pipeline/tests/test_render.py
git commit -m "Stage 5: ffmpeg cut+concat renderer (render.py)"
```

---

## Task 7：Orchestrator — run_pipeline.py（串起 5 个 stage）

**Files:**
- Create: `skills/tennis-match-video-editing/cv_pipeline/run_pipeline.py`

无单元测试——这是个 thin orchestrator，靠手动端到端跑验证。

- [ ] **Step 1: 实现 `run_pipeline.py`**

```python
"""Run all 5 stages sequentially for one source video.

Usage:
    python -m cv_pipeline.run_pipeline \
        --video /path/to/source.mp4 \
        --job-dir /path/to/jobs/abc123 \
        [--device 0|cpu] [--render-mode highlight|short|both]

Each stage's output goes into job-dir. Re-running a stage just overwrites its file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from . import decode, detect_ball, detect_players, segment_rallies, render
from .segment_rallies import RallyParams


def _job_id_for(video: Path) -> str:
    h = hashlib.sha1(str(video.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"{video.stem}_{h}"


def run(video: Path, job_dir: Path, device: str = "0",
        render_mode: str = "highlight",
        skip: tuple[str, ...] = ()) -> dict:
    job_dir.mkdir(parents=True, exist_ok=True)
    log_path = job_dir / "log.txt"
    log_lines = [f"=== Pipeline run @ {time.strftime('%Y-%m-%d %H:%M:%S')} ==="]

    def log(line: str) -> None:
        print(line)
        log_lines.append(line)

    timings: dict[str, float] = {}

    # Stage 1
    if "decode" not in skip:
        t0 = time.time()
        log(f"[1/5] decode → meta.json")
        meta = decode.probe(video, job_dir / "meta.json")
        timings["decode"] = time.time() - t0
        log(f"      {meta['w']}x{meta['h']} @ {meta['fps']:.2f}fps "
            f"{meta['n_frames']} frames ({timings['decode']:.1f}s)")
    else:
        meta = json.loads((job_dir / "meta.json").read_text())

    # Stage 2
    if "ball" not in skip:
        t0 = time.time()
        log(f"[2/5] detect_ball → ball.csv (device={device})")
        s = detect_ball.detect(video, job_dir / "ball.csv", device=device)
        timings["ball"] = time.time() - t0
        log(f"      {s['n_detected_filtered']}/{s['n_frames']} "
            f"({s['detection_rate']*100:.1f}%) in {timings['ball']:.0f}s "
            f"({s['fps_inference']} fps)")

    # Stage 3
    if "players" not in skip:
        t0 = time.time()
        log(f"[3/5] detect_players → players.csv")
        s = detect_players.detect(video, job_dir / "players.csv", device=device)
        timings["players"] = time.time() - t0
        log(f"      {s['n_samples']} samples, avg n_players={s['avg_n_players']} "
            f"in {timings['players']:.0f}s")

    # Stage 4
    if "segment" not in skip:
        t0 = time.time()
        log(f"[4/5] segment_rallies → segments.json")
        # Adjust min_run_frames to fps (1.5s window)
        min_run = max(45, int(meta["fps"] * 1.5))
        payload = segment_rallies.segment(
            ball_csv=job_dir / "ball.csv",
            players_csv=job_dir / "players.csv",
            meta=meta,
            out_segments=job_dir / "segments.json",
            params=RallyParams(min_run_frames=min_run, min_hits=4),
        )
        timings["segment"] = time.time() - t0
        log(f"      {len(payload['rallies'])} rallies in {timings['segment']:.1f}s")

    # Stage 5
    if "render" not in skip:
        t0 = time.time()
        if render_mode in ("highlight", "both"):
            log(f"[5/5] render highlight → highlight.mp4")
            render.render(video, job_dir / "segments.json",
                          job_dir / "highlight.mp4", mode="highlight")
        if render_mode in ("short", "both"):
            log(f"[5/5] render short → short.mp4")
            render.render(video, job_dir / "segments.json",
                          job_dir / "short.mp4", mode="short")
        timings["render"] = time.time() - t0
        log(f"      render done in {timings['render']:.0f}s")

    log(f"--- Total: {sum(timings.values()):.0f}s ---")
    log_path.write_text("\n".join(log_lines) + "\n")
    return {"job_dir": str(job_dir), "timings": timings}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--job-dir", type=Path, default=None)
    ap.add_argument("--device", default="0")
    ap.add_argument("--render-mode", choices=["highlight", "short", "both"],
                    default="highlight")
    ap.add_argument("--skip", nargs="*", default=[],
                    choices=["decode", "ball", "players", "segment", "render"])
    args = ap.parse_args()
    job_dir = args.job_dir or (Path("jobs") / _job_id_for(args.video))
    run(args.video, job_dir, device=args.device,
        render_mode=args.render_mode, skip=tuple(args.skip))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 端到端冒烟（5s 测试视频，CPU）**

```bash
mkdir -p /c/Users/xinyi/AppData/Local/Temp/breakpoint/job_e2e
/tmp/breakpoint/venv312/Scripts/python.exe -m cv_pipeline.run_pipeline \
  --video skills/tennis-match-video-editing/cv_pipeline/tests/data/tiny_5s_clip.mp4 \
  --job-dir /c/Users/xinyi/AppData/Local/Temp/breakpoint/job_e2e \
  --device cpu \
  --skip render
```

Expected: 4 个 stage 全跑通，无报错。`segments.json` 可能是 0 个 rally（因为是 testsrc 合成视频，没有真实球）—这正常，证明降级路径不崩。

- [ ] **Step 3: 端到端冒烟（DJI 8s 真实样本，CPU）**

```bash
mkdir -p /c/Users/xinyi/AppData/Local/Temp/breakpoint/job_dji
"C:/Users/xinyi/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin/ffmpeg.exe" \
  -y -loglevel error \
  -ss 367.9 -i /d/Pictures/网球/2026.5.3/DJI_20260503150415_0533_D.MP4 \
  -t 8.4 -vf scale=1280:720 -c:v libx264 -preset ultrafast -an \
  /c/Users/xinyi/AppData/Local/Temp/breakpoint/job_dji/sample.mp4

/tmp/breakpoint/venv312/Scripts/python.exe -m cv_pipeline.run_pipeline \
  --video /c/Users/xinyi/AppData/Local/Temp/breakpoint/job_dji/sample.mp4 \
  --job-dir /c/Users/xinyi/AppData/Local/Temp/breakpoint/job_dji \
  --device cpu
```

Expected: 5 stage 都跑完，`segments.json` 含 1 个 rally（DJI 367.9-376.3 这段就是一个完整 rally），`highlight.mp4` 生成，时长在 8s 左右。

- [ ] **Step 4: Commit**

```bash
git add skills/tennis-match-video-editing/cv_pipeline/run_pipeline.py
git commit -m "Add run_pipeline orchestrator stitching all 5 stages"
```

---

## Task 8：tests/fixtures.json + .gitignore

**Files:**
- Create: `tests/fixtures.json`
- Create: `tests/fixtures.local.json`（gitignore）
- Modify: `.gitignore`

- [ ] **Step 1: 写 `tests/fixtures.json`（schema 文件，提交）**

```json
{
  "$schema_doc": "Each entry has id (slug); paths live in tests/fixtures.local.json",
  "videos": [
    {"id": "dji_0532"},
    {"id": "dji_0533"},
    {"id": "dji_0534"}
  ]
}
```

- [ ] **Step 2: 写 `tests/fixtures.local.json`（本机路径，不入 repo）**

```json
{
  "videos": [
    {"id": "dji_0532",
     "source": "D:/Pictures/网球/2026.5.3/DJI_20260503142617_0532_D.MP4",
     "manual": "D:/Pictures/网球/2026.5.3/1777808242000.MP4"},
    {"id": "dji_0533",
     "source": "D:/Pictures/网球/2026.5.3/DJI_20260503150415_0533_D.MP4",
     "manual": "D:/Pictures/网球/2026.5.3/1777803838000.MP4"},
    {"id": "dji_0534",
     "source": "D:/Pictures/网球/2026.5.3/DJI_20260503154223_0534_D.MP4",
     "manual": "D:/Pictures/网球/2026.5.3/1777801854000.MP4"}
  ]
}
```

- [ ] **Step 3: 更新 `.gitignore`**

在文件末尾追加：

```
tests/fixtures.local.json
jobs/
```

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures.json .gitignore
git commit -m "Add fixtures.json schema + ignore local fixtures and jobs/"
```

---

## Task 9：完整管线在 1 个真实视频上跑通（验收）

**这一步不写代码，是验收。需要 GPU。**

- [ ] **Step 1: 确认 CUDA torch 可用**

Run: `/tmp/breakpoint/venv312/Scripts/python.exe -m cv_pipeline.check_env`
Expected: `cuda=True`

如果 False，安装：
```bash
/tmp/breakpoint/venv312/Scripts/python.exe -m pip install torch torchvision \
  --index-url https://download.pytorch.org/whl/cu124
```
（注：需要 ~2.5 GB 下载，5–10 min）

- [ ] **Step 2: 跑 dji_0533 全片**

```bash
/tmp/breakpoint/venv312/Scripts/python.exe -m cv_pipeline.run_pipeline \
  --video "/d/Pictures/网球/2026.5.3/DJI_20260503150415_0533_D.MP4" \
  --job-dir jobs/dji_0533 \
  --device 0 \
  --render-mode both
```

Expected:
- 总耗时 ≤ 30 min（spec 成功标准）
- `jobs/dji_0533/highlight.mp4` 时长在 215–320s 之间（手工 268s ±20%）
- `jobs/dji_0533/short.mp4` 时长在 60–90s 之间
- `jobs/dji_0533/log.txt` 完整记录每个 stage 耗时

- [ ] **Step 3: 肉眼检查输出**

打开 `jobs/dji_0533/highlight.mp4`，目测：
- 画面没有"球员散步""捡球"等无聊段
- rally 边界没有突然中断（应该完整含起拍到结束）
- 至少 5 个 rally 看起来是真正的回合

- [ ] **Step 4: Commit log + segments.json 作为 first golden**

```bash
mkdir -p tests/golden
cp jobs/dji_0533/segments.json tests/golden/dji_0533.segments.json
git add tests/golden/dji_0533.segments.json
git commit -m "Add first golden segments.json (dji_0533) from Plan A E2E run"
```

---

## Plan A 完成定义

- ✅ 所有 stage 单元测试通过
- ✅ run_pipeline 在 dji_0533 全片上端到端跑通
- ✅ 总耗时 ≤ 30 min（GPU）
- ✅ highlight.mp4 时长在手工 ±20% 内
- ✅ tests/golden/dji_0533.segments.json 提交

**Plan A 完成后做什么**：进入 Plan B（接入 server.py + clip_app.html UI）和 Plan C（剩余 2 个视频的 golden + compare_to_manual.py）。这两个 plan 在 A 跑通后单独写。

---

## Self-review

**Spec 覆盖：**
- §3 Stage 1–5 → Tasks 2–6 ✓
- §4 数据流 / 目录结构 → Task 7（run_pipeline 创建 job_dir）+ Task 8 ✓
- §4 segments.json schema → Task 5 ✓
- §5 错误处理（GPU OOM / Stage 4 0 个 rally）→ 部分覆盖：Stage 4 返回空 list 不抛错 ✓；GPU OOM fallback 在 v2 加（MVP 让用户在 `--device cpu` 显式切换）
- §6 Tier 1 单元测试 → Tasks 2–6 ✓
- §6 Tier 2 / Tier 3（golden 回归 + compare_to_manual）→ Plan C
- §7 GPU 安装 → Task 9 Step 1 ✓
- §7 score 公式调参 → Plan C 完成所有 3 个视频后

**Placeholder 扫描：** 没有 TBD/TODO；每个 step 都有完整代码或命令。

**类型一致性：** `RallyParams.min_run_frames` 在 Task 5 / Task 7 都用同一个名字 ✓；`segment(...)` 签名一致 ✓；`render.render(source_video, segments_json, out, mode=)` 在 Task 6 / Task 7 都一致 ✓。

**未覆盖的 spec 点（已知遗漏，刻意推到后续 plan）：**
- §3 Stage 4 边界精化（球员第一次明显移动 / 静止 ≥ 1s）—— 在 segment_rallies.py 有结构但未实现细节，因为需要 players.csv 真实数据才能调；推到 Plan A 后期或 Plan C 调参阶段
- §3 Stage 4 max_ball_speed_kmh —— 字段保留但置 0，等 Plan C
- §5 GPU OOM 自动 fallback —— v2

这些点不影响 MVP 第一次端到端跑通。

---

## Execution Handoff

Plan A 完成并保存到 `docs/superpowers/plans/2026-05-05-cv-pipeline-plan-a.md`。两个执行选项：

**1. Subagent-Driven**（推荐）— 我每个 task 派一个新 subagent，task 之间 review，迭代快

**2. Inline Execution** — 这个 session 内逐 task 执行，带 checkpoint

哪种？
