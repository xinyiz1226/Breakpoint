---
name: tennis-match-video-editing
description: Edit a full high-angle amateur tennis match video into a highlight-focused final video. Use when the user wants end-to-end video editing from raw footage to exported deliverable, with removal of non-rally and low-value points, retention of high-value winning points, and output resolution identical to source.
---

# Tennis Match Video Editing

## Workflow

Use this skill to transform a full-match raw video into a playable edited match highlight video.

1. Confirm or infer input basics: source file, total duration, target platform, target final duration, language preference, and whether to preserve key-score context.
2. Read [editing-principles.md](references/editing-principles.md) before making clip decisions.
3. Use [input-template.md](references/input-template.md) when the user provides an incomplete brief.
4. Use [sample-project.md](references/sample-project.md) as a structure reference for timeline decisions and delivery format.
5. Build a clip decision list first, then render the final output video.
6. To draft the clip list automatically, run [generate_manifest_draft.py](tools/generate_manifest_draft.py) on the source video. The draft generator pre-filters audio (highpass + lowpass + spectral denoise) to suppress voice and ambient noise, detects ball-impact onsets, and groups onsets into rhythm-based rally sequences as candidate clips.
7. For automatic rendering, run [render_from_manifest.py](tools/render_from_manifest.py) on the manifest. See [auto-render-guide.md](references/auto-render-guide.md).
8. Apply dual-path execution: automatic render first; if unstable or ambiguous, fall back to semi-automatic review of the candidate manifest or to CapCut/Jianying manual export.
9. Treat the auto draft as candidate-only. Recall is high (typical KEEP+REVIEW coverage ~85-90%) but ranked KEEP precision is limited; human review of the candidate list is recommended before final render.
10. Return bilingual output by default: Chinese primary result plus concise English summary.

## Default Stance

- Treat input as a full high-angle amateur tennis match recording.
- Prioritize watchability and rally quality over full match completeness.
- Remove dead time and low-value points by default.
- Keep high-value points and strong tactical exchanges.
- Never change output resolution from source resolution.
- Write the final edited video to the same directory as the source video unless the user explicitly overrides it.
- If uncertainty is high on a point, mark for manual review instead of hard-cut.

## Required Output

Return these sections for each task:

1. `【任务配置 / Task Config】`: source basics, target duration, platform, language mode, and processing path.
2. `【筛选阈值 / Selection Thresholds】`: concise keep/drop criteria used in this run.
3. `【删除清单 / Drop List】`: clip id, start/end, action, reason, tags.
4. `【保留清单 / Keep List】`: clip id, start/end, action, reason, tags, suggested clip length.
5. `【待复核片段 / Review Queue】`: uncertain clips with review notes.
6. `【时间线方案 / Timeline Plan】`: ordered final sequence and pacing guidance.
7. `【导出参数 / Export Settings】`: codec, fps handling, audio target, and strict resolution lock.
8. `【交付清单 / Deliverables】`: final video path/name and edit log summary.
9. `【英文摘要 / English Summary】`: short mirrored summary of key decisions.

## Editing Rules

Drop by default:

- Ball pickup, long reset, side switch, scoreboard-only waiting, and non-rally dead air.
- Serve fault segments that do not lead to valid rally.
- Immediate low-value unforced-error points with no tactical buildup.

Keep by priority:

- Aces and direct serve winners.
- Multi-shot rally winners with visible pressure shift.
- Angle creation winners and court-opening patterns.
- Net approach and volley winners.
- Deep-placement winners and clear tactical construction.
- High-speed winners with obvious execution quality.

Boundary rule:

- If point ends on error but the winner was built by strong prior pressure, keep as forced-error highlight.

## Technical Rules

- Input is raw full-match video; output is a playable edited video file.
- Default output location is the same directory as the source video.
- Output resolution must exactly match source width and height.
- No upscaling, no downscaling.
- Keep source frame rate unless user explicitly requests conversion.
- Default container: mp4.
- If automatic path fails quality checks, output semi-automatic CapCut/Jianying timeline package with manual export checklist.
