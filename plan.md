# Breakpoint: Tennis Highlight Extraction Plan

输入：网球比赛视频（DJI 无人机固定机位 ~4米高，1080p60，无比分板、无解说、无观众，纯现场原声）

输出：自动剪辑的精彩片段合集

---

## Phase 1 — Audio-Based Point Segmentation (MVP) ✅ 已完成

目标：仅通过音频信号，将比赛切分为逐分片段，导出所有有效回合。

### 1.1 击球音检测 (Hit Detection)
- 使用 onset detection（短时能量突变 / spectral flux）检测击球瞬间
- **分窗检测**：将音频按 60s 窗口切分，每个窗口独立做 onset detection，避免全局阈值漏检较安静片段的击球
- 频段过滤：击球声集中在低中频，带通滤波 200-4000Hz
- 工具：`librosa.onset.onset_detect` + Butterworth 带通滤波 + delta=0.2

### 1.2 分段 (Point Segmentation)
- 检测击球之间的长静音间隔（>6秒），作为每一分的分界
- **最大时长限制**：超过 25s 的片段在最大内部间隔处递归拆分（实际回合不超过此时长）
- **最小击球数过滤**：丢弃 hit_count < 4 的片段（发球失误、隔壁场地误检等）
- **最小时长过滤**：丢弃 <4s 的片段
- **密度修剪**：片段开头若有稀疏击球（间隔远大于中位数的 3 倍），自动截掉前段
- 输出每一分的起止时间戳列表

### 1.3 输出
- 导出所有有效片段（不限数量），按原片时间戳顺序排列
- 时间戳列表（JSON）
- 使用 `ffmpeg` 裁剪对应视频片段（`-c copy` 不重编码）
- 可选：合并为单个精彩集锦视频（`ffmpeg concat`）

### 1.4 质量比对工具
- `phase1/compare.py`：输入原片 + 手工剪辑视频，通过音频指纹交叉关联自动比对覆盖率
- 用于评估 pipeline 质量和调参效果
- CLI：`py -3.12 phase1/compare.py ORIGINAL REFERENCE`
- 也可通过 `pipeline.py --reference REFERENCE` 在 pipeline 结束后自动比对

---

## Phase 2 — Vision-Based Enhancement ⚙️ 进行中

目标：通过视觉分析过滤误检、增强片段质量判断。固定广播视角（DJI 无人机 ~4米高），无镜头切换。

### 2.1 球员运动强度分析 ✅ 已完成

**目标**：检测球员大幅移动（救球、飞扑、大范围跑动）。

**方案**：
- 背景减除（`cv2.createBackgroundSubtractorMOG2`）提取前景掩码
- 球场两端各设一个 ROI，首帧交互标定（`cv2.selectROI`），结果缓存到 `rois_cache.json`
- 每个片段独立创建 MOG2 实例，每 2 帧采样一次
- 形态学开运算去噪

**输出特征**：
- `player_motion_max`: 片段内球员运动幅度峰值
- `player_motion_var`: 运动幅度方差

**文件**：`phase2/player_motion.py`

### 2.2 上网检测（待定）

- 追踪球员质心 y 坐标，检测底线→网前移动
- 在 2.1 基础上扩展，复用背景减除结果

### 2.3 球速估算（实验性，待定）

- 帧差分追踪球的帧间位移，估算相对速度
- 识别暴力击球和放小球

### 2.4 Pipeline 集成 ✅ 已完成

- `pipeline.py --vision` 开关启用视觉分析
- 在 segment 之后、输出之前插入视觉分析
- 视觉特征可选地加入评分权重

---

## Phase 3 — Smart Compilation（待定）

目标：智能组合精彩片段，输出成品视频。

### 3.1 多样性选择
- 避免选取多个相似回合
- 兼顾不同类型的精彩（长回合、暴力击球、精彩救球等）

### 3.2 转场 & 后期
- 片段间淡入淡出
- 关键击球慢动作回放（可选）

### 3.3 导出
- 合并为最终精彩集锦视频，保留现场原声

---

## Web UI ✅ 已完成

Flask + 纯 HTML/JS 的交互式编辑界面：
- 上传视频 → 自动分析 → 展示片段列表
- 每个片段可预览播放、拖拽调整时间戳
- 加入候选列表 → 导出合并视频
- 深色主题，网球绿色点缀

**文件**：`web/app.py` + `web/templates/index.html`

---

## Tech Stack

- Python 3.12
- `librosa` — 音频分析
- `ffmpeg` — 音视频处理
- `opencv-python` — 视觉分析（Phase 2）
- `numpy`, `scipy` — 数值计算
- `Flask` — Web UI
