---
title: Breakpoint CV Rally Pipeline — Design
date: 2026-05-05
status: Approved
---

# Breakpoint — CV Rally Pipeline 设计

## 1. 目标与非目标

### 目标（MVP）
- **输入**：1080p、tripod broadcast view 的网球比赛/对拉视频，10min – 1h
- **输出 1：完整集锦**（5–8 min）— 保留所有 ≥ 4 拍的 rally 和制胜分
- **输出 2：社交短片**（60–90 s）— 从集锦中挑选 5–10 个最炸裂镜头
- **用户体验**：上传 → 自动处理 → UI 预览/编辑候选 → 一键合成下载

### 非目标
- 多用户、云存储、付费功能
- 训练自有模型（直接用 abdullahtarek 的 YOLOv5 球检测权重）
- 移动端、实时直播、多机位融合
- 球员身份识别（"我"的高光）— 留 v2
- 战术分析、配速、热区图

### 成功标准
- 集锦时长在手工剪辑 ±20% 范围内
- 3 个测试视频对**平均召回 ≥ 80%**，**没有任何一个 < 70%**
- 全片端到端处理 ≤ 30 min（NVIDIA 4060 GPU）

### 已验证的关键假设
- YOLOv5 球检测器（abdullahtarek/tennis_analysis Google Drive 权重）在 DJI 高点广角 8.4 s 样本上的检测率 = **79.4%**，最长连续命中 122 帧（2 s）。显著优于 TrackNet 的 40.5%。结论：方案可行。

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (clip_app.html)                                    │
│  上传 → 进度 → 候选预览/编辑 → 渲染 → 下载                    │
└──────────────┬──────────────────────────────────────────────┘
               │ HTTP（现有 server.py 扩展）
┌──────────────▼──────────────────────────────────────────────┐
│  Pipeline Orchestrator (Python)                              │
│  把视频切成 task → 调度 5 个独立 stage → 持久化中间产物        │
└──────────────┬──────────────────────────────────────────────┘
               │
   ┌───────────┼───────────┬──────────────┬───────────────┐
   ▼           ▼           ▼              ▼               ▼
[Stage 1]  [Stage 2]   [Stage 3]      [Stage 4]      [Stage 5]
 解码抽帧    球检测       球员检测       Rally切分     渲染输出
 ffmpeg →   YOLOv5      YOLOv8n       启发式规则      ffmpeg
 帧序列     ball.csv    players.csv   segments.json  highlight.mp4
                                                     short.mp4
```

### 设计原则
- **每个 stage 输入/输出都是文件**（CSV / JSON / video），不是内存对象
- **Stage 之间无共享状态**——任何 stage 改算法都不影响别的
- **失败可恢复**——重跑只需要从失败的 stage 开始
- **可绕过**——用户手动编辑 segments.json 后只需重跑 Stage 5

### 与现有代码的关系
- `apps/review-tool/server.py`：保留，扩展 `/api/analyze` 改为调用新 pipeline；旧的音频 onset 代码完全废弃
- `apps/review-tool/clip_app.html`：保留，只改候选数据字段（增加 rally 长度、最大球速、单/双打等）
- `skills/tennis-match-video-editing/tools/render_from_manifest.py`：保留 render 部分，分析部分换掉
- 新代码全部放 `skills/tennis-match-video-editing/cv_pipeline/`

---

## 3. 各 Stage 详细设计

### Stage 1：解码 (`decode.py`)
- **输入**：源视频
- **输出**：`meta.json`（fps、宽高、总帧数）
- **实现**：不抽帧到磁盘；下游 stage 各自用 OpenCV VideoCapture 流式读
- **理由**：38 min × 60 fps × 1080p ≈ 137k 帧，全抽出 100 GB+；流式读省盘且不慢

### Stage 2：球检测 (`detect_ball.py`)
- **输入**：源视频
- **输出**：`ball.csv`（列：`frame, t, x, y, conf`，无球行 x/y 留空）
- **模型**：YOLOv5（abdullahtarek 权重，~173 MB），conf ≥ 0.15
- **GPU 性能**：4060 上 ~30 fps，38 min 视频约 13 min
- **后处理**：
  - **空间一致性过滤**：相邻 3 帧球位置跳变 > 200 px → 丢弃中间帧（YOLO 假阳性通常孤立）
  - **不做插值**：保持"无球"信号给下游使用

### Stage 3：球员检测 (`detect_players.py`)
- **输入**：源视频
- **输出**：`players.csv`（列：`frame, n_players, p1_x, p1_y, p2_x, p2_y, p3_x, p3_y, p4_x, p4_y`，缺失留空）
- **模型**：YOLOv8n（COCO 预训练，class=person），每 5 帧采样
- **过滤**：
  - 取 y 坐标最靠下的最多 4 个 person
  - MVP 用「画面下半部分 + 排除 bbox 高度异常的 person」过滤裁判/观众
  - 球场 keypoint 区域过滤留 v2
- **降级容忍**：偶尔检测到 1 或 3 个不报错，记录 `n_players` 实际值即可
- **GPU 性能**：~5 fps × 跳帧 5 = ~8 min/38 min 视频

### Stage 4：Rally 切分 (`segment_rallies.py`)
- **输入**：`ball.csv`、`players.csv`、`meta.json`
- **输出**：`segments.json`（rally 列表，schema 见 §4）
- **算法**：
  1. 滑窗看球的 detected 序列，连续可见 ≥ 90 帧（≈1.5 s @ 60fps）= 一个 rally 候选
  2. rally 内根据球 y 方向反转计算"拍数"（沿用 ameynarwadkar 的 `get_ball_shot_frames` 逻辑）
  3. 过滤：拍数 < 4 丢弃
  4. **边界精化**：rally 起点向前找球员第一次明显移动；终点向后找球员第一次连续静止 ≥ 1 s
  5. **逐 rally 单/双打判定**：rally 时间窗内 `n_players` 的众数 = 2 → `singles`；= 4 → `doubles`；= 1/3 → `unknown`（仍保留 rally）
  6. **球员静止判定按 match_type 走**：单打 2 人都静止，双打 4 人都静止
  7. **score 排名**：`score = n_hits × 0.5 + max_ball_speed × 0.3 + rally_duration × 0.2`
- **明确不做**：bounce 检测、谁赢分判定、win-the-point — v2 再加

### Stage 5：渲染 (`render.py`)
- **输入**：源视频、`segments.json`（或用户编辑过的 `segments.user.json`）、模式
- **输出**：`highlight.mp4` 或 `short.mp4`
- **算法**：
  - **highlight 模式**：所有 `kept=true` 的 rally 按时间顺序拼接（ffmpeg cut + concat，沿用 `render_from_manifest.py`）
  - **short 模式**：按 score 排序取前 N 个，使总时长在 60–90 s 之间

---

## 4. 数据流 & 中间产物

### 目录结构（每个视频一个 job）
```
jobs/<video_id>/
├── source.mp4                   # symlink / 路径引用，不复制
├── meta.json                    # {fps, w, h, n_frames}
├── ball.csv
├── players.csv
├── segments.json                # Stage 4 输出
├── segments.user.json           # 用户在 UI 编辑后的版本（可选）
├── highlight.mp4
├── short.mp4
└── log.txt                      # 每个 stage 的耗时和错误
```

### Stage 依赖图
```
Stage 1 ──→ meta.json ────────────────────┐
Stage 2 ──→ ball.csv ──┐                  │
Stage 3 ──→ players.csv┴──→ Stage 4 ──→ segments.json ──→ Stage 5
```
Stage 2 和 Stage 3 互不依赖，MVP 串行执行。

### segments.json schema
```json
{
  "fps": 59.94,
  "rallies": [
    {
      "id": "R001",
      "start_t": 367.9,
      "end_t": 376.3,
      "n_hits": 7,
      "max_ball_speed_kmh": 142.3,
      "score": 8.7,
      "match_type": "singles",
      "kept": true
    }
  ]
}
```
**`kept` 字段的设计**：用户在 UI 勾掉某些段后，前端只改 `kept`，回传后端，Stage 5 只渲染 `kept=true` 的段。零状态、零冲突。

---

## 5. 错误处理 & 降级

**核心原则**：算法错误不应该让整个 pipeline 崩。每个 stage 都可能部分失败。

| 失败场景 | 行为 | 用户可见 |
|---|---|---|
| Stage 2 球检测率 < 30% | Stage 4 仍跑，segments 标记 `low_confidence: true` | UI 显示警告 |
| Stage 3 平均 n_players < 1.5 | 跳过"球员静止"边界精化，只用球检测做切分 | 透明，log 记录 |
| Stage 4 切出 0 个 rally | 不报错，返回空 segments，UI 提示放宽参数（≥4 拍 → ≥2 拍） | UI 显示"未找到 rally" + 重试按钮 |
| Stage 5 ffmpeg 失败 | 重试一次（不同 preset），再失败才报错 | UI 显示具体 ffmpeg stderr |
| GPU OOM | 自动 fallback 到 CPU + warn | UI 显示"GPU 不可用，估算时间 ×6" |
| 用户中途取消 | 复用 `server.py` 现有 `/api/cancel`，杀子进程，保留中间产物 | 立即响应 |

### 不做（YAGNI）
- 自动调参 — 参数固定，调不好让用户在 UI 改
- 单 stage 内部断点续传 — 重跑成本可接受（最贵的 Stage 2 ~13 min）
- 后台任务队列 — 同时只允许一个 job

### 关键日志
每个 stage 必须打印：输入文件大小、输出文件大小、耗时、关键统计（球检测率、rally 数量、最长 rally）。让用户从 log 一眼看出哪个 stage 出了问题。

---

## 6. 测试策略

### Tier 1：单元测试
- **Stage 2**：跑已知有球/无球的 5 s 片段，断言检测率落在合理区间
- **Stage 3**：单打片段 mode(n_players)=2，双打片段 mode=4
- **Stage 4**：构造合成 ball.csv（手写 ≥90 帧连续 + 一段空）→ 断言切出 1 个 rally
- **Stage 5**：固定 segments.json → 断言输出视频时长 ±0.5 s

### Tier 2：端到端回归
- **Golden 测试集** — 3 个视频对，路径配置在 `tests/fixtures.local.json`（gitignore），schema 在 `tests/fixtures.json` 提交：

  ```json
  [
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
  ```
- **每个视频独立 `golden_segments.json`** 提交到 repo
- **回归断言**：3 个视频全部跑，每个的 IoU > 0.85（rally 边界允许 ±1 s 漂移）
- **触发**：手动 `python tests/regression.py`，不接 CI（GPU 不在 CI 里）

### Tier 3：与手工剪辑对比 — 主质量指标
- `compare_to_manual.py` 跑 3 个视频对，输出表格：

  ```
  video_id    召回   精度   时长差   手工段数  自动段数
  dji_0532    ...
  dji_0533    ...
  dji_0534    ...
  ```
- **判定**：3 个视频平均召回 ≥ 80%，且无任何一个 < 70%
- 单/双打覆盖：3 个视频中可能混合单打和双打，pipeline 自己逐 rally 判定 — 通过测试即代表两种场景都能 work

### 不做
- 视觉回归测试（YOLOv5 输出非确定性，且跑一次太慢）
- UI 自动化测试（手动点几下更快）
- CI/CD 集成（GPU 资源限制）

---

## 7. 关键开放问题（实现阶段需要决策）

1. **Stage 2 GPU 部署**：当前 venv 是 CPU 版 PyTorch，需要重装 CUDA 版（~2.5 GB 下载）— 实现 Stage 2 之前完成
2. **YOLOv8n 球员模型选择**：MVP 用 COCO 预训练的 yolov8n（小模型，5 fps 够），如不够准再考虑 yolov8s
3. **score 公式权重**：`0.5/0.3/0.2` 是初值，实现后用 3 个 golden 视频调
4. **rally 切分阈值**（连续 90 帧）：初值，跑完 golden 视频后调

## 8. 参考与依赖

- 上游球检测仓库：[abdullahtarek/tennis_analysis](https://github.com/abdullahtarek/tennis_analysis)
- Fork（被 brainstorm 提及）：[ameynarwadkar/Tennis-Analysis-System](https://github.com/ameynarwadkar/Tennis-Analysis-System)（Apache-2.0）
- 球检测训练数据集：[viren-dhanwani/tennis-ball-detection](https://universe.roboflow.com/viren-dhanwani/tennis-ball-detection)
- YOLOv5 权重 173 MB：[Google Drive](https://drive.google.com/file/d/1UZwiG1jkWgce9lNhxJ2L0NVjX1vGM05U/view)
- 已废弃方案参考：CourtCheck（无 license，只参考思路不抄代码）；TrackNetV3（在 DJI 视角检测率仅 40.5%，已淘汰）
