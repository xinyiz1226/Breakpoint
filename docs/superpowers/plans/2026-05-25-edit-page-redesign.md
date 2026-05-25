# Edit Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the post-analysis edit page into a reference-style confirmation page with a large preview, bottom match map, fixed rally queue, inline trimming, and right-side export CTA.

**Architecture:** Keep the existing Electron/React renderer state and export pipeline. Add view-model helpers for generated rally titles and map tone, replace the right `SegmentList` with a queue/export panel, replace the bottom `Timeline` with a reference-style match map, and wire both into `App.tsx`.

**Tech Stack:** Electron, React 18, TypeScript, Vite, existing Node-based renderer flow test script.

---

## File Structure

- Modify `desktop/src/renderer/viewModels/flowCopy.ts`: add pure helpers for rally title, tone, adjusted time range, and export copy used by the redesigned components.
- Modify `desktop/scripts/renderer-flow.test.mjs`: add tests for generated titles, tone, and adjusted range formatting.
- Modify `desktop/src/renderer/state/AppState.tsx`: add a `RESTORE_RECOMMENDED` reducer action that reapplies the score threshold without clearing trim edits.
- Create `desktop/src/renderer/components/RallyQueue.tsx`: right-side queue, batch actions, selected-card trim editor, export summary, progress, and result display.
- Create `desktop/src/renderer/components/MatchMap.tsx`: bottom full-match vertical bar map with `只看建议保留` filter.
- Modify `desktop/src/renderer/App.tsx`: remove top `Toolbar`, use the new confirmation layout, wire export props into `RallyQueue`, and use `MatchMap`.
- Optional deletion after wiring: `desktop/src/renderer/components/SegmentList.tsx`, `desktop/src/renderer/components/Timeline.tsx`, and `desktop/src/renderer/components/Toolbar.tsx` if no imports remain.

## Task 1: Add Rally View-Model Helpers

**Files:**
- Modify: `desktop/src/renderer/viewModels/flowCopy.ts`
- Modify: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing tests for rally titles and time helpers**

Add `getRallyTitle`, `getSegmentTone`, and `getAdjustedTimeRange` to the destructuring block in `desktop/scripts/renderer-flow.test.mjs`:

```js
const {
  getAnalysisStageView,
  getAnalysisStageNumber,
  getReviewTaskSummary,
  getExportActionCopy,
  formatClipDuration,
  getRallyTitle,
  getSegmentTone,
  getAdjustedTimeRange,
} = loadTsModule(path.join('src', 'renderer', 'viewModels', 'flowCopy.ts'))
```

Add these assertions after the existing `formatClipDuration` assertion:

```js
const highMultiHitSegment = {
  index: 7,
  start: 1463,
  end: 1484,
  score: 2.6,
  included: true,
  features: { hit_count: 18 },
}
assert.equal(getRallyTitle(highMultiHitSegment), '多拍高强度回合 #08')
assert.equal(getSegmentTone(highMultiHitSegment), 'highlight')
assert.deepEqual(plain(getAdjustedTimeRange({
  index: 2,
  start: 70,
  end: 95,
  score: 2.1,
  included: true,
  startAdjusted: 72.2,
  endAdjusted: 93.7,
  features: {},
})), {
  start: 72.2,
  end: 93.7,
  duration: 21.5,
  label: '1:12 - 1:33',
})

assert.equal(getRallyTitle({
  index: 3,
  start: 20,
  end: 25,
  score: 1.8,
  included: true,
  features: { hit_count: 5 },
}), '短回合 #04')
assert.equal(getSegmentTone({
  index: 3,
  start: 20,
  end: 25,
  score: 1.8,
  included: true,
  features: { hit_count: 5 },
}), 'keep')

assert.equal(getRallyTitle({
  index: 4,
  start: 40,
  end: 55,
  score: 1.1,
  included: false,
  features: {},
}), '普通回合 #05')
assert.equal(getSegmentTone({
  index: 4,
  start: 40,
  end: 55,
  score: 1.1,
  included: false,
  features: {},
}), 'discarded')
```

- [ ] **Step 2: Run the failing renderer flow test**

Run:

```powershell
Set-Location desktop
npm run test:renderer-flow
```

Expected: the test fails because `getRallyTitle`, `getSegmentTone`, and `getAdjustedTimeRange` are not exported.

- [ ] **Step 3: Implement the helper exports**

Append these helpers to `desktop/src/renderer/viewModels/flowCopy.ts` after `getExportActionCopy`:

```ts
export type SegmentTone = 'highlight' | 'keep' | 'discarded'

function formatSegmentNumber(index: number): string {
  return `#${String(index + 1).padStart(2, '0')}`
}

export function getAdjustedTimeRange(segment: Pick<Segment, 'start' | 'end' | 'startAdjusted' | 'endAdjusted'>) {
  const start = segment.startAdjusted ?? segment.start
  const end = segment.endAdjusted ?? segment.end
  const duration = Math.max(end - start, 0)
  return {
    start,
    end,
    duration,
    label: `${formatClipDuration(start)} - ${formatClipDuration(end)}`,
  }
}

export function getSegmentTone(segment: Pick<Segment, 'score' | 'included'>): SegmentTone {
  if (!segment.included) return 'discarded'
  if (segment.score > 2.3) return 'highlight'
  return 'keep'
}

export function getRallyTitle(segment: Pick<Segment, 'index' | 'start' | 'end' | 'score' | 'features'>): string {
  const duration = Math.max(segment.end - segment.start, 0)
  const hitCount = segment.features.hit_count ?? 0
  const parts: string[] = []

  if (hitCount >= 14) parts.push('多拍')
  if (segment.score > 2.3) parts.push('高强度')
  if (duration <= 8) parts.push('短')

  if (parts.length > 0) {
    return `${parts.join('')}回合 ${formatSegmentNumber(segment.index)}`
  }

  const fallback = segment.score > 1.7 ? '推荐回合' : '普通回合'
  return `${fallback} ${formatSegmentNumber(segment.index)}`
}
```

- [ ] **Step 4: Run the renderer flow test**

Run:

```powershell
npm run test:renderer-flow
```

Expected: all assertions pass.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add desktop\src\renderer\viewModels\flowCopy.ts desktop\scripts\renderer-flow.test.mjs
git commit -m "feat(renderer): add rally review view helpers" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 2: Add Recommended Selection State Action

**Files:**
- Modify: `desktop/src/renderer/state/AppState.tsx`
- Modify: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Add a source-level regression assertion**

Append this assertion after the existing `appSource` assertions in `desktop/scripts/renderer-flow.test.mjs`:

```js
const appStateSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'state', 'AppState.tsx'), 'utf8')
assert.match(appStateSource, /RESTORE_RECOMMENDED/)
assert.match(appStateSource, /case 'RESTORE_RECOMMENDED'/)
assert.match(appStateSource, /included: s\.score > INCLUDE_THRESHOLD/)
assert.doesNotMatch(appStateSource, /case 'RESTORE_RECOMMENDED':[\s\S]*startAdjusted: undefined/)
```

- [ ] **Step 2: Run the failing renderer flow test**

Run:

```powershell
Set-Location desktop
npm run test:renderer-flow
```

Expected: the test fails because `RESTORE_RECOMMENDED` is not present.

- [ ] **Step 3: Implement the reducer action**

In `desktop/src/renderer/state/AppState.tsx`, add the action type after `RESET_ALL`:

```ts
  | { type: 'RESTORE_RECOMMENDED' }
```

Add this case after `RESET_ALL`:

```ts
    case 'RESTORE_RECOMMENDED':
      return { ...state, segments: state.segments.map((s) => ({ ...s, included: s.score > INCLUDE_THRESHOLD })) }
```

Keep `RESET_ALL` unchanged so it still resets trim edits and inclusion together.

- [ ] **Step 4: Run the renderer flow test**

Run:

```powershell
npm run test:renderer-flow
```

Expected: all assertions pass.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add desktop\src\renderer\state\AppState.tsx desktop\scripts\renderer-flow.test.mjs
git commit -m "feat(renderer): restore recommended rally selection" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 3: Build the Right-Side Rally Queue

**Files:**
- Create: `desktop/src/renderer/components/RallyQueue.tsx`

- [ ] **Step 1: Create the component with queue, trim controls, and export CTA**

Create `desktop/src/renderer/components/RallyQueue.tsx` with this implementation:

```tsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { useAppState, Segment } from '../state/AppState'
import { getAdjustedTimeRange, getExportActionCopy, getRallyTitle, getReviewTaskSummary, getSegmentTone } from '../viewModels/flowCopy'

interface Props {
  onSeek: (time: number) => void
  onSeekAndPlay: (time: number) => void
  currentTime: number
  onExport: () => void
  onCancelExport: () => void
  onOpenExportFile: (outputPath: string) => void
  exportProgress: number | null
  exportResult: { status: 'complete' | 'error'; message: string; outputPath?: string } | null
}

function formatTimePrecise(s: number): string {
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1)
  return `${m}:${sec.padStart(4, '0')}`
}

function scoreColor(score: number): string {
  if (score > 2.3) return '#cc4e0e'
  if (score > 1.7) return '#00503c'
  return '#a89f91'
}

export default function RallyQueue({
  onSeek,
  onSeekAndPlay,
  currentTime,
  onExport,
  onCancelExport,
  onOpenExportFile,
  exportProgress,
  exportResult,
}: Props) {
  const { state, dispatch } = useAppState()
  const { segments, selectedSegmentIndex } = state
  const summary = getReviewTaskSummary(segments)
  const exporting = exportProgress !== null
  const itemRefs = useRef<(HTMLDivElement | null)[]>([])

  useEffect(() => {
    const selectedEl = selectedSegmentIndex != null ? itemRefs.current[selectedSegmentIndex] : null
    const scroller = selectedEl?.parentElement
    if (selectedEl && scroller) {
      const selectedTop = selectedEl.offsetTop
      const selectedBottom = selectedTop + selectedEl.offsetHeight
      if (selectedTop < scroller.scrollTop) {
        scroller.scrollTo({ top: selectedTop - 8, behavior: 'smooth' })
      } else if (selectedBottom > scroller.scrollTop + scroller.clientHeight) {
        scroller.scrollTo({ top: selectedBottom - scroller.clientHeight + 8, behavior: 'smooth' })
      }
    }
  }, [selectedSegmentIndex])

  return (
    <aside style={panelStyle}>
      <div style={headerStyle}>
        <div>
          <h2 style={titleStyle}>回合队列</h2>
          <p style={subtitleStyle}>{summary.selectedCount} 个回合将被导出</p>
        </div>
      </div>

      <div style={batchGridStyle}>
        <button onClick={() => dispatch({ type: 'INCLUDE_ALL' })} style={batchBtnStyle}>全选</button>
        <button onClick={() => dispatch({ type: 'RESTORE_RECOMMENDED' })} style={batchBtnStyle}>推荐</button>
        <button onClick={() => dispatch({ type: 'EXCLUDE_ALL' })} style={batchBtnStyle}>清空</button>
      </div>

      <div style={listStyle}>
        {segments.length === 0 ? (
          <div style={emptyStyle}>没有可确认的回合片段。</div>
        ) : segments.map((segment, index) => {
          const isSelected = index === selectedSegmentIndex
          return (
            <div key={segment.index} ref={(el) => { itemRefs.current[index] = el }} style={{ marginBottom: 10 }}>
              <RallyCard
                segment={segment}
                index={index}
                isSelected={isSelected}
                onSelect={() => {
                  dispatch({ type: 'SELECT_SEGMENT', index })
                  onSeekAndPlay(segment.startAdjusted ?? segment.start)
                }}
                onToggle={() => dispatch({ type: 'TOGGLE_INCLUDE', index })}
              />
              {isSelected && (
                <TrimEditor segment={segment} index={index} currentTime={currentTime} onSeek={onSeek} />
              )}
            </div>
          )
        })}
      </div>

      <div style={exportBoxStyle}>
        {exporting && (
          <div style={progressTrackStyle}>
            <div style={{ ...progressFillStyle, width: `${(exportProgress ?? 0) * 100}%` }} />
          </div>
        )}
        <p style={exportSummaryStyle}>
          已选择 {summary.selectedCount} 个回合。确认列表后，将它们合成为一个精彩合集。
        </p>
        <p style={exportMetaStyle}>合集约 {summary.selectedDurationLabel}</p>
        {exportResult && (
          <div style={{
            ...exportResultStyle,
            color: exportResult.status === 'error' ? 'var(--color-danger)' : 'var(--color-green-light)',
          }}>
            <span>{exportResult.message}</span>
            {exportResult.outputPath && (
              <button onClick={() => onOpenExportFile(exportResult.outputPath!)} style={linkBtnStyle}>打开</button>
            )}
          </div>
        )}
        {exporting ? (
          <button onClick={onCancelExport} style={{ ...exportBtnStyle, background: 'var(--color-danger)' }}>
            取消导出
          </button>
        ) : (
          <button onClick={onExport} disabled={summary.selectedCount === 0} style={{
            ...exportBtnStyle,
            background: summary.selectedCount > 0 ? 'var(--color-accent)' : '#d8cfc2',
            cursor: summary.selectedCount > 0 ? 'pointer' : 'not-allowed',
          }}>
            {getExportActionCopy(summary.selectedCount, false)} ↗
          </button>
        )}
      </div>
    </aside>
  )
}

function RallyCard({
  segment,
  index,
  isSelected,
  onSelect,
  onToggle,
}: {
  segment: Segment
  index: number
  isSelected: boolean
  onSelect: () => void
  onToggle: () => void
}) {
  const range = getAdjustedTimeRange(segment)
  const tone = getSegmentTone(segment)
  const borderColor = isSelected ? 'var(--color-accent)' : '#e5d2bd'

  return (
    <div onClick={onSelect} style={{
      ...cardStyle,
      borderColor,
      borderWidth: isSelected ? 2 : 1,
      opacity: segment.included ? 1 : 0.58,
      background: isSelected ? '#fff7ef' : 'var(--color-surface)',
    }}>
      <input
        type="checkbox"
        checked={segment.included}
        onChange={(event) => {
          event.stopPropagation()
          onToggle()
        }}
        onClick={(event) => event.stopPropagation()}
        style={checkboxStyle}
      />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={cardTitleStyle}>{getRallyTitle(segment)}</div>
        <div style={cardMetaStyle}>
          #{String(index + 1).padStart(2, '0')} · {range.label} · {range.duration.toFixed(1)}s
        </div>
        <div style={{ ...badgeStyle, color: scoreColor(segment.score) }}>
          {tone === 'highlight' ? '高分推荐' : tone === 'keep' ? '建议保留' : '已剔除'} · {segment.features.hit_count ?? '?'} 次击球 · 强度 {segment.score.toFixed(2)}
        </div>
      </div>
    </div>
  )
}

function TrimEditor({
  segment,
  index,
  currentTime,
  onSeek,
}: {
  segment: Segment
  index: number
  currentTime: number
  onSeek: (time: number) => void
}) {
  const { dispatch } = useAppState()
  const effectiveStart = segment.startAdjusted ?? segment.start
  const effectiveEnd = segment.endAdjusted ?? segment.end
  const isEdited = segment.startAdjusted != null || segment.endAdjusted != null
  const padding = 15
  const rangeStart = Math.max(0, segment.start - padding)
  const rangeEnd = segment.end + padding
  const rangeWidth = rangeEnd - rangeStart
  const barRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState<'start' | 'end' | null>(null)

  const timeToPercent = (time: number) => ((time - rangeStart) / rangeWidth) * 100
  const percentToTime = (percent: number) => rangeStart + (percent / 100) * rangeWidth
  const clampStart = (time: number) => Math.min(Math.max(time, rangeStart), effectiveEnd - 0.5)
  const clampEnd = (time: number) => Math.max(Math.min(time, rangeEnd), effectiveStart + 0.5)
  const updateStart = (time: number) => {
    const next = Math.round(clampStart(time) * 10) / 10
    dispatch({ type: 'ADJUST_SEGMENT', index, start: next })
    onSeek(next)
  }
  const updateEnd = (time: number) => {
    const next = Math.round(clampEnd(time) * 10) / 10
    dispatch({ type: 'ADJUST_SEGMENT', index, end: next })
    onSeek(next)
  }

  const handleMouseDown = useCallback((edge: 'start' | 'end') => (event: React.MouseEvent) => {
    event.preventDefault()
    event.stopPropagation()
    setDragging(edge)
    const bar = barRef.current
    if (!bar) return

    const onMove = (moveEvent: MouseEvent) => {
      const rect = bar.getBoundingClientRect()
      const percent = Math.max(0, Math.min(100, ((moveEvent.clientX - rect.left) / rect.width) * 100))
      const time = percentToTime(percent)
      if (edge === 'start') updateStart(time)
      else updateEnd(time)
    }

    const onUp = () => {
      setDragging(null)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [effectiveStart, effectiveEnd, rangeStart, rangeEnd, rangeWidth])

  const startPct = timeToPercent(effectiveStart)
  const endPct = timeToPercent(effectiveEnd)

  return (
    <div style={trimBoxStyle} onClick={(event) => event.stopPropagation()}>
      <div style={trimHeaderStyle}>
        <span>开始 <b>{formatTimePrecise(effectiveStart)}</b></span>
        <span>结束 <b>{formatTimePrecise(effectiveEnd)}</b></span>
      </div>
      <div style={trimControlsStyle}>
        <div style={nudgeGroupStyle}>
          <button onClick={() => updateStart(effectiveStart - 0.1)} style={nudgeBtnStyle}>-</button>
          <button onClick={() => updateStart(effectiveStart + 0.1)} style={nudgeBtnStyle}>+</button>
        </div>
        <div ref={barRef} style={barStyle}>
          <div style={{
            ...originalRangeStyle,
            left: `${timeToPercent(segment.start)}%`,
            width: `${timeToPercent(segment.end) - timeToPercent(segment.start)}%`,
          }} />
          <div style={{
            ...activeRangeStyle,
            left: `${startPct}%`,
            width: `${endPct - startPct}%`,
          }} />
          <div onMouseDown={handleMouseDown('start')} style={{
            ...handleStyle,
            left: `${startPct}%`,
            background: dragging === 'start' ? 'var(--color-accent-hover)' : '#202020',
          }} />
          <div onMouseDown={handleMouseDown('end')} style={{
            ...handleStyle,
            left: `${endPct}%`,
            background: dragging === 'end' ? 'var(--color-accent-hover)' : '#202020',
          }} />
          {currentTime >= rangeStart && currentTime <= rangeEnd && (
            <div style={{ ...playheadStyle, left: `${timeToPercent(currentTime)}%` }} />
          )}
        </div>
        <div style={nudgeGroupStyle}>
          <button onClick={() => updateEnd(effectiveEnd - 0.1)} style={nudgeBtnStyle}>-</button>
          <button onClick={() => updateEnd(effectiveEnd + 0.1)} style={nudgeBtnStyle}>+</button>
        </div>
      </div>
      <div style={trimFooterStyle}>
        <span>左侧按钮微调开始，右侧按钮微调结束</span>
        {isEdited && (
          <button onClick={() => dispatch({ type: 'ADJUST_SEGMENT', index, start: undefined, end: undefined })} style={resetBtnStyle}>
            重置
          </button>
        )}
      </div>
    </div>
  )
}

const panelStyle: React.CSSProperties = { width: 390, minWidth: 340, maxWidth: 430, margin: 16, marginLeft: 0, border: '1px solid #e5d2bd', borderRadius: 10, background: 'rgba(255,250,244,0.92)', display: 'flex', flexDirection: 'column', minHeight: 0, boxShadow: '0 12px 28px rgba(50,35,20,0.06)' }
const headerStyle: React.CSSProperties = { padding: '20px 18px 10px' }
const titleStyle: React.CSSProperties = { fontFamily: 'var(--font-display)', fontSize: 25, fontWeight: 900, color: 'var(--color-text)', margin: 0, letterSpacing: '-0.04em' }
const subtitleStyle: React.CSSProperties = { fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4 }
const batchGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, padding: '10px 18px 14px' }
const batchBtnStyle: React.CSSProperties = { border: '1px solid #e1cbb5', borderRadius: 4, background: 'var(--color-surface)', padding: '9px 0', fontFamily: 'var(--font-display)', fontWeight: 800, color: 'var(--color-text)' }
const listStyle: React.CSSProperties = { flex: 1, overflowY: 'auto', minHeight: 0, padding: '0 18px 12px' }
const emptyStyle: React.CSSProperties = { padding: 18, border: '1px dashed #e1cbb5', borderRadius: 8, color: 'var(--color-text-secondary)', fontSize: 13 }
const cardStyle: React.CSSProperties = { display: 'flex', gap: 12, border: '1px solid #e5d2bd', borderRadius: 8, padding: 12, cursor: 'pointer', transition: 'border-color 0.15s, background 0.15s, opacity 0.15s' }
const checkboxStyle: React.CSSProperties = { width: 22, height: 22, accentColor: 'var(--color-green)', flexShrink: 0 }
const cardTitleStyle: React.CSSProperties = { fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 900, color: 'var(--color-text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }
const cardMetaStyle: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 4 }
const badgeStyle: React.CSSProperties = { fontSize: 11, fontWeight: 700, marginTop: 6 }
const trimBoxStyle: React.CSSProperties = { border: '1px solid #efb58d', borderTop: 0, borderRadius: '0 0 8px 8px', background: '#fff3e8', padding: 12 }
const trimHeaderStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 10 }
const trimControlsStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: '36px 1fr 36px', gap: 10, alignItems: 'center' }
const nudgeGroupStyle: React.CSSProperties = { display: 'grid', gridTemplateRows: '1fr 1fr', gap: 4 }
const nudgeBtnStyle: React.CSSProperties = { width: 30, height: 24, borderRadius: 999, border: '1px solid #e1cbb5', background: '#fff', fontWeight: 900 }
const barStyle: React.CSSProperties = { position: 'relative', height: 26, borderRadius: 999, background: '#dfd6c9', userSelect: 'none' }
const originalRangeStyle: React.CSSProperties = { position: 'absolute', top: 10, height: 6, borderRadius: 999, background: '#bcb2a4' }
const activeRangeStyle: React.CSSProperties = { position: 'absolute', top: 10, height: 6, borderRadius: 999, background: 'linear-gradient(90deg, var(--color-green), var(--color-accent))' }
const handleStyle: React.CSSProperties = { position: 'absolute', top: 2, width: 14, height: 22, marginLeft: -7, borderRadius: 6, cursor: 'ew-resize', boxShadow: '0 2px 5px rgba(0,0,0,0.25)' }
const playheadStyle: React.CSSProperties = { position: 'absolute', top: -2, width: 2, height: 30, background: '#ffffff', boxShadow: '0 0 4px rgba(0,0,0,0.4)', pointerEvents: 'none' }
const trimFooterStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginTop: 9, fontSize: 10, color: 'var(--color-text-secondary)' }
const resetBtnStyle: React.CSSProperties = { border: '1px solid #e1cbb5', borderRadius: 999, background: '#fff', padding: '4px 9px', color: 'var(--color-danger)', fontWeight: 800 }
const exportBoxStyle: React.CSSProperties = { margin: 18, marginTop: 0, padding: 14, border: '1px solid #efb58d', borderRadius: 8, background: '#fff3e8', flexShrink: 0 }
const progressTrackStyle: React.CSSProperties = { height: 4, background: '#e1cbb5', borderRadius: 999, overflow: 'hidden', marginBottom: 10 }
const progressFillStyle: React.CSSProperties = { height: '100%', background: 'var(--color-accent)', transition: 'width 0.3s ease-out' }
const exportSummaryStyle: React.CSSProperties = { fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.5, margin: 0 }
const exportMetaStyle: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 6, marginBottom: 10 }
const exportResultStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, fontSize: 12, fontWeight: 800, marginBottom: 10 }
const linkBtnStyle: React.CSSProperties = { border: '1px solid #e1cbb5', borderRadius: 999, background: '#fff', padding: '4px 10px', fontWeight: 800 }
const exportBtnStyle: React.CSSProperties = { width: '100%', borderRadius: 4, border: 0, color: '#fff', padding: '14px 16px', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 900, letterSpacing: '0.04em' }
```

- [ ] **Step 2: Run TypeScript build**

Run:

```powershell
Set-Location desktop
npm run build
```

Expected: the build fails only if the new component has type or hook dependency errors. Fix errors in `RallyQueue.tsx` before continuing.

- [ ] **Step 3: Commit Task 3**

Run:

```powershell
git add desktop\src\renderer\components\RallyQueue.tsx
git commit -m "feat(renderer): add rally queue panel" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 4: Build the Full-Match Map

**Files:**
- Create: `desktop/src/renderer/components/MatchMap.tsx`

- [ ] **Step 1: Create the match map component**

Create `desktop/src/renderer/components/MatchMap.tsx` with this implementation:

```tsx
import { useMemo, useState } from 'react'
import { INCLUDE_THRESHOLD, useAppState } from '../state/AppState'
import { getAdjustedTimeRange, getSegmentTone } from '../viewModels/flowCopy'

interface Props {
  onSeek: (time: number) => void
}

function toneColor(tone: ReturnType<typeof getSegmentTone>): string {
  if (tone === 'highlight') return 'var(--color-accent)'
  if (tone === 'keep') return 'var(--color-green)'
  return '#c1b8aa'
}

export default function MatchMap({ onSeek }: Props) {
  const { state, dispatch } = useAppState()
  const { segments, selectedSegmentIndex, videoDuration } = state
  const [recommendedOnly, setRecommendedOnly] = useState(false)

  const visibleSegments = useMemo(() => {
    return recommendedOnly ? segments.filter((segment) => segment.score > INCLUDE_THRESHOLD || segment.included) : segments
  }, [recommendedOnly, segments])

  if (videoDuration <= 0 || segments.length === 0) return null

  return (
    <section style={mapShellStyle}>
      <div style={mapHeaderStyle}>
        <div>
          <h2 style={mapTitleStyle}>整场比赛地图</h2>
          <p style={mapSubtitleStyle}>高条是建议保留的回合，灰色是已剔除的等待、拉球和间歇片段。</p>
        </div>
        <div style={legendStyle}>
          <span style={legendItemStyle}><i style={{ ...legendDotStyle, background: 'var(--color-accent)' }} />高光</span>
          <span style={legendItemStyle}><i style={{ ...legendDotStyle, background: 'var(--color-green)' }} />可保留</span>
          <span style={legendItemStyle}><i style={{ ...legendDotStyle, background: '#c1b8aa' }} />已剔除</span>
        </div>
      </div>

      <div style={barViewportStyle}>
        {visibleSegments.map((segment) => {
          const originalIndex = segments.indexOf(segment)
          const range = getAdjustedTimeRange(segment)
          const left = (segment.start / videoDuration) * 100
          const width = Math.max(((segment.end - segment.start) / videoDuration) * 100, 0.55)
          const isSelected = originalIndex === selectedSegmentIndex
          const tone = getSegmentTone(segment)
          const height = tone === 'highlight' ? 58 : tone === 'keep' ? 46 : 24

          return (
            <button
              key={segment.index}
              title={`#${String(originalIndex + 1).padStart(2, '0')} · ${range.label} · 强度 ${segment.score.toFixed(2)}`}
              onClick={() => {
                dispatch({ type: 'SELECT_SEGMENT', index: originalIndex })
                onSeek(segment.startAdjusted ?? segment.start)
              }}
              style={{
                ...barStyle,
                left: `${left}%`,
                width: `${width}%`,
                height,
                background: toneColor(tone),
                outline: isSelected ? '2px solid #222' : 'none',
                opacity: segment.included ? 1 : 0.58,
              }}
            >
              {isSelected && <span style={timeMarkerStyle}>{range.label.split(' - ')[0]}</span>}
            </button>
          )
        })}
      </div>

      <div style={mapFooterStyle}>
        <div style={progressLineStyle}>
          <span style={{
            ...progressFillLineStyle,
            width: `${Math.min((visibleSegments.length / Math.max(segments.length, 1)) * 100, 100)}%`,
          }} />
        </div>
        <button onClick={() => setRecommendedOnly((value) => !value)} style={filterBtnStyle}>
          {recommendedOnly ? '显示全部回合' : '只看建议保留'}
        </button>
      </div>
    </section>
  )
}

const mapShellStyle: React.CSSProperties = { margin: '0 16px 16px', border: '1px solid #e5d2bd', borderRadius: 10, background: 'rgba(255,250,244,0.9)', padding: 20, boxShadow: '0 12px 28px rgba(50,35,20,0.05)' }
const mapHeaderStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 18 }
const mapTitleStyle: React.CSSProperties = { fontFamily: 'var(--font-display)', fontSize: 23, fontWeight: 900, color: 'var(--color-text)', letterSpacing: '-0.04em', margin: 0 }
const mapSubtitleStyle: React.CSSProperties = { fontSize: 13, color: 'var(--color-text-secondary)', marginTop: 6 }
const legendStyle: React.CSSProperties = { display: 'flex', gap: 14, alignItems: 'center', fontSize: 11, color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }
const legendItemStyle: React.CSSProperties = { display: 'inline-flex', gap: 5, alignItems: 'center' }
const legendDotStyle: React.CSSProperties = { width: 8, height: 8, borderRadius: '50%', display: 'inline-block' }
const barViewportStyle: React.CSSProperties = { position: 'relative', height: 132, border: '1px solid #ead8c5', borderRadius: 7, background: 'repeating-linear-gradient(90deg, rgba(0,0,0,0.04) 0, rgba(0,0,0,0.04) 1px, transparent 1px, transparent 48px)', overflow: 'hidden' }
const barStyle: React.CSSProperties = { position: 'absolute', bottom: 22, minWidth: 7, border: 0, borderRadius: 3, cursor: 'pointer', padding: 0, transition: 'height 0.15s, opacity 0.15s, outline 0.15s' }
const timeMarkerStyle: React.CSSProperties = { position: 'absolute', top: -25, left: '50%', transform: 'translateX(-50%)', background: '#222', color: '#fff', borderRadius: 3, padding: '3px 5px', fontFamily: 'var(--font-mono)', fontSize: 10, whiteSpace: 'nowrap' }
const mapFooterStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 16, marginTop: 14 }
const progressLineStyle: React.CSSProperties = { flex: 1, height: 7, borderRadius: 999, background: '#dfd6c9', overflow: 'hidden' }
const progressFillLineStyle: React.CSSProperties = { display: 'block', height: '100%', background: 'linear-gradient(90deg, var(--color-green), var(--color-accent))' }
const filterBtnStyle: React.CSSProperties = { border: '1px solid #e1cbb5', borderRadius: 4, background: 'var(--color-surface)', padding: '9px 13px', fontFamily: 'var(--font-display)', fontWeight: 900, color: 'var(--color-text)' }
```

- [ ] **Step 2: Run TypeScript build**

Run:

```powershell
Set-Location desktop
npm run build
```

Expected: the build fails only if the new component has type errors. Fix errors in `MatchMap.tsx` before continuing.

- [ ] **Step 3: Commit Task 4**

Run:

```powershell
git add desktop\src\renderer\components\MatchMap.tsx
git commit -m "feat(renderer): add confirmation match map" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 5: Wire the Confirmation Layout in App

**Files:**
- Modify: `desktop/src/renderer/App.tsx`

- [ ] **Step 1: Replace component imports**

In `desktop/src/renderer/App.tsx`, replace these imports:

```ts
import Toolbar from './components/Toolbar'
import Timeline from './components/Timeline'
import SegmentList from './components/SegmentList'
```

with:

```ts
import RallyQueue from './components/RallyQueue'
import MatchMap from './components/MatchMap'
```

- [ ] **Step 2: Replace the edit-page JSX**

Replace the JSX returned after the analysis screens with this structure:

```tsx
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--color-bg)' }}>
      <div style={{
        padding: '4px 16px',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        color: 'var(--color-text-secondary)',
        borderBottom: '1px solid #e5d2bd',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        WebkitAppRegion: 'drag',
      } as React.CSSProperties}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 900, letterSpacing: '-0.02em', color: 'var(--color-text)' }}>
          Breakpoint · 确认回合片段
        </span>
        <div style={{ display: 'flex', gap: 8, WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
          <button onClick={handleReturnWelcome} style={topBtnStyle}>返回欢迎页</button>
          <button onClick={() => startAnalysis(state.videoPath!)} style={topBtnStyle}>重新处理</button>
        </div>
      </div>

      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', minHeight: 0 }}>
        <main style={{ display: 'grid', gridTemplateRows: 'minmax(0, 1fr) auto', minWidth: 0, minHeight: 0 }}>
          <section style={{ margin: 16, marginBottom: 16, borderRadius: 9, overflow: 'hidden', background: '#063b2d', minHeight: 0 }}>
            <VideoPlayer
              videoPath={state.videoPath}
              seekTo={seekTarget}
              seekKey={seekCounter}
              autoPlay={autoPlay}
              pauseAt={state.selectedSegmentIndex != null ? (() => {
                const seg = state.segments[state.selectedSegmentIndex!]
                return seg.endAdjusted ?? seg.end
              })() : null}
              onTimeUpdate={(t) => setCurrentTime(t)}
              onDurationChange={(d) => dispatch({ type: 'SET_DURATION', duration: d })}
            />
          </section>

          {state.analysisStatus === 'done' && (
            <MatchMap onSeek={doSeek} />
          )}
        </main>

        {state.analysisStatus === 'done' && (
          <RallyQueue
            onSeek={doSeek}
            onSeekAndPlay={doSeekAndPlay}
            currentTime={currentTime}
            onExport={handleExport}
            onCancelExport={() => window.api.cancelExport()}
            onOpenExportFile={(outputPath) => window.api.openPath(outputPath)}
            exportProgress={exportProgress}
            exportResult={exportResult}
          />
        )}
      </div>
    </div>
  )
```

Add this style constant before `export default function App()`:

```ts
const topBtnStyle: React.CSSProperties = {
  fontSize: 11,
  fontFamily: 'var(--font-display)',
  fontWeight: 800,
  letterSpacing: '0.04em',
  color: 'var(--color-green-dark)',
  padding: '3px 9px',
  border: '1px solid #e1cbb5',
  borderRadius: 999,
  background: 'var(--color-surface)',
}
```

- [ ] **Step 3: Run TypeScript build**

Run:

```powershell
Set-Location desktop
npm run build
```

Expected: the build passes or reports only stale imports. Remove stale imports before continuing.

- [ ] **Step 4: Commit Task 5**

Run:

```powershell
git add desktop\src\renderer\App.tsx
git commit -m "feat(renderer): wire edit confirmation layout" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 6: Remove Obsolete Edit Components if Unused

**Files:**
- Delete if unused: `desktop/src/renderer/components/SegmentList.tsx`
- Delete if unused: `desktop/src/renderer/components/Timeline.tsx`
- Delete if unused: `desktop/src/renderer/components/Toolbar.tsx`

- [ ] **Step 1: Check for remaining imports**

Run:

```powershell
rg "SegmentList|Timeline|Toolbar" desktop\src\renderer
```

Expected: no matches after Task 5. If matches remain in `App.tsx`, finish the import replacement before deletion.

- [ ] **Step 2: Delete unused files**

Run:

```powershell
Remove-Item desktop\src\renderer\components\SegmentList.tsx
Remove-Item desktop\src\renderer\components\Timeline.tsx
Remove-Item desktop\src\renderer\components\Toolbar.tsx
```

- [ ] **Step 3: Run renderer tests and build**

Run:

```powershell
Set-Location desktop
npm run test:renderer-flow
npm run build
```

Expected: tests and build pass.

- [ ] **Step 4: Commit Task 6**

Run:

```powershell
git add desktop\src\renderer\components\SegmentList.tsx desktop\src\renderer\components\Timeline.tsx desktop\src\renderer\components\Toolbar.tsx
git commit -m "refactor(renderer): remove old edit review components" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 7: Final Verification

**Files:**
- Verify: `desktop/src/renderer/App.tsx`
- Verify: `desktop/src/renderer/components/RallyQueue.tsx`
- Verify: `desktop/src/renderer/components/MatchMap.tsx`
- Verify: `desktop/src/renderer/viewModels/flowCopy.ts`
- Verify: `desktop/src/renderer/state/AppState.tsx`

- [ ] **Step 1: Run renderer flow tests**

Run:

```powershell
Set-Location desktop
npm run test:renderer-flow
```

Expected: all assertions pass.

- [ ] **Step 2: Run production build**

Run:

```powershell
npm run build
```

Expected: TypeScript compilation and Vite build complete successfully.

- [ ] **Step 3: Inspect changed files**

Run:

```powershell
git --no-pager diff --stat HEAD~6..HEAD
git --no-pager diff --check
```

Expected: only edit-page redesign files are changed, and `diff --check` reports no whitespace errors.

- [ ] **Step 4: Manual smoke test in dev server**

Run:

```powershell
npm run dev
```

Expected manual behavior:

1. Import a video with an existing or newly generated report.
2. Analysis completion opens the redesigned confirmation page.
3. Right queue shows generated titles and `全选 / 推荐 / 清空`.
4. `推荐` reapplies the score threshold without clearing adjusted trim values.
5. Clicking a queue card seeks and plays the selected rally.
6. Dragging trim handles and pressing `- / +` seek to the edited boundary.
7. Bottom map bars select and seek to rallies.
8. `只看建议保留` toggles the map contents.
9. Export uses only included segments and adjusted boundaries.

- [ ] **Step 5: Commit verification fixes if needed**

If verification required small fixes, commit them with:

```powershell
git add desktop\src\renderer desktop\scripts\renderer-flow.test.mjs
git commit -m "fix(renderer): polish edit confirmation flow" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

Skip this commit if Task 7 required no code changes.

## Self-Review

- Spec coverage: layout, generated titles, `推荐` batch action, inline trim nudge buttons, map colors/filter, right-side export area, existing export data flow, and edge cases are covered by Tasks 1-7.
- Completeness scan: this plan contains concrete file paths, code snippets, commands, and expected outcomes.
- Type consistency: the new components use existing `Segment`, `useAppState`, `startAdjusted`, `endAdjusted`, `included`, `score`, `features.hit_count`, and `videoDuration` names from `AppState.tsx`.
