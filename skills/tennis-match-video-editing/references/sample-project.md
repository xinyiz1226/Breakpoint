# Sample Project

## Input

```text
Source video path: /videos/match_2026_05_01.mp4
Source duration: 01:32:10
Match type: singles
Platform: YouTube long-form
Target final duration: 09:00
Style: 70% high-energy, 30% documentary continuity
Keep key score context: no
Output directory: same as source video
Resolution rule: must match source
Language mode: Chinese primary + English summary
Execution path: automatic first, CapCut fallback
```

## Output Shape

```text
【任务配置 / Task Config】
- Source: /videos/match_2026_05_01.mp4
- Duration: 01:32:10
- Target final duration: 09:00
- Path: automatic render

【筛选阈值 / Selection Thresholds】
- Drop all dead-time utility segments.
- Drop serve-fault-only clips with no valid rally.
- Drop immediate unforced-error points without pressure buildup.
- Keep aces, long-rally winners, angle winners, net volley winners, deep-placement winners, and high-speed winners.

【删除清单 / Drop List】
- D-001 | 00:03:10-00:03:48 | DROP | ball pickup and reset | DEAD_TIME
- D-002 | 00:07:22-00:07:31 | DROP | double fault no rally | SERVE_FAULT
- D-003 | 00:12:41-00:12:47 | DROP | return into net, no buildup | LOW_VALUE_ERROR

【保留清单 / Keep List】
- K-001 | 00:15:02-00:15:12 | KEEP | ace on big point | ACE | 6-10s
- K-002 | 00:24:11-00:24:41 | KEEP | 14-shot rally with pressure change | LONG_RALLY_WIN | 18-25s
- K-003 | 00:39:30-00:39:44 | KEEP | wide-angle setup then winner | ANGLE_WIN | 8-14s
- K-004 | 00:51:08-00:51:20 | KEEP | approach and volley finish | NET_FINISH | 7-12s
- K-005 | 01:03:22-01:03:35 | KEEP | deep push then open-court finish | DEEP_PLACEMENT_WIN | 8-13s
- K-006 | 01:17:03-01:17:14 | KEEP | high-speed clean winner | HIGH_SPEED_WIN | 7-11s

【待复核片段 / Review Queue】
- R-001 | 00:58:04-00:58:18 | REVIEW | short rally but possible key tactical sequence

【时间线方案 / Timeline Plan】
- Open with K-001, K-002 as hook.
- Alternate short explosive points and long tactical points.
- Place K-006 near final minute as late peak.

【导出参数 / Export Settings】
- Format: mp4
- Codec: H.264
- Output directory: same as source video
- Resolution: SAME AS SOURCE (strict)
- FPS: SAME AS SOURCE
- Audio: normalize to consistent listening level

【交付清单 / Deliverables】
- Final video: /videos/match_2026_05_01_highlights.mp4
- Edit log: match_2026_05_01_edit_log.md

【英文摘要 / English Summary】
Final output removes dead-time and low-value errors, keeps high-impact winning points, preserves tactical variety, and exports in source-matching resolution.
```
