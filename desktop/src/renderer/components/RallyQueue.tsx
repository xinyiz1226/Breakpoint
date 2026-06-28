import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAppState, type RallySegment, type VideoRecord } from '../state/AppState'
import { useCopy, type Copy } from '../i18n'
import { getSortedRallies } from '../batchFlow'
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

function formatTimePrecise(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const remainder = (seconds % 60).toFixed(1)
  return `${minutes}:${remainder.padStart(4, '0')}`
}

function scoreColor(score: number): string {
  if (score > 2.3) return '#cc4e0e'
  if (score > 1.7) return '#00503c'
  return '#a89f91'
}

function toneLabel(segment: RallySegment, copy: Copy): string {
  const tone = getSegmentTone(segment)
  if (tone === 'highlight') return copy.rallyQueue.toneHighlight
  if (tone === 'keep') return copy.rallyQueue.toneKeep
  return copy.rallyQueue.toneDiscarded
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
  const copy = useCopy()
  const { state, dispatch } = useAppState()
  const { videos, rallies, selectedRallyId } = state
  const segments = useMemo(() => getSortedRallies(rallies, videos), [rallies, videos])
  const videosById: Map<string, VideoRecord> = new Map(videos.map((video) => [video.id, video]))
  const summary = getReviewTaskSummary(segments, copy)
  const exporting = exportProgress !== null
  const exportProgressRatio = Math.max(0, Math.min(exportProgress ?? 0, 1))
  const itemRefs = useRef<(HTMLDivElement | null)[]>([])

  useEffect(() => {
    const selectedIndex = segments.findIndex((segment) => segment.id === selectedRallyId)
    const selectedEl = selectedIndex >= 0 ? itemRefs.current[selectedIndex] : null
    const scroller = selectedEl?.parentElement
    if (!selectedEl || !scroller) return

    const selectedTop = selectedEl.offsetTop
    const selectedBottom = selectedTop + selectedEl.offsetHeight
    if (selectedTop < scroller.scrollTop) {
      scroller.scrollTo({ top: selectedTop - 8, behavior: 'smooth' })
    } else if (selectedBottom > scroller.scrollTop + scroller.clientHeight) {
      scroller.scrollTo({ top: selectedBottom - scroller.clientHeight + 8, behavior: 'smooth' })
    }
  }, [segments, selectedRallyId])

  return (
    <aside style={panelStyle}>
      <div style={headerStyle}>
        <h2 style={titleStyle}>{copy.rallyQueue.title}</h2>
        <p style={subtitleStyle}>
          {copy.rallyQueue.exportCount(summary.selectedCount, summary.totalCount)}
        </p>
      </div>

      <div style={batchGridStyle}>
        <button onClick={() => dispatch({ type: 'INCLUDE_ALL' })} style={batchBtnStyle}>{copy.rallyQueue.includeAll}</button>
        <button onClick={() => dispatch({ type: 'RESTORE_RECOMMENDED' })} style={batchBtnStyle}>{copy.rallyQueue.restoreRecommended}</button>
        <button onClick={() => dispatch({ type: 'EXCLUDE_ALL' })} style={batchBtnStyle}>{copy.rallyQueue.excludeAll}</button>
      </div>

      <div style={listStyle}>
        {segments.length === 0 ? (
          <div style={emptyStyle}>{copy.rallyQueue.empty}</div>
        ) : segments.map((segment, index) => {
          const isSelected = segment.id === selectedRallyId
          return (
            <div key={segment.id} ref={(el) => { itemRefs.current[index] = el }} style={itemWrapStyle}>
              <RallyCard
                segment={segment}
                isSelected={isSelected}
                onSelect={() => {
                  dispatch({ type: 'SELECT_RALLY', id: segment.id })
                  dispatch({ type: 'SET_ACTIVE_VIDEO', id: segment.videoId })
                  onSeekAndPlay(segment.startAdjusted ?? segment.start)
                }}
                onToggle={() => dispatch({ type: 'TOGGLE_INCLUDE', id: segment.id })}
                sourceLabel={copy.rallyQueue.sourceLabel(videosById.get(segment.videoId)?.displayName ?? segment.videoId)}
                copy={copy}
              />
              {isSelected && (
                <TrimEditor segment={segment} currentTime={currentTime} onSeek={onSeek} copy={copy} />
              )}
            </div>
          )
        })}
      </div>

      <div style={exportBoxStyle}>
        {exporting && (
          <div style={progressTrackStyle}>
            <div style={{ ...progressFillStyle, width: `${exportProgressRatio * 100}%` }} />
          </div>
        )}
        <p style={exportSummaryStyle}>
          {copy.rallyQueue.exportSummary(summary.selectedCount)}
        </p>
        <p style={exportMetaStyle}>{copy.rallyQueue.exportDuration(summary.selectedDurationLabel)}</p>
        {exportResult && (
          <div style={{
            ...exportResultStyle,
            color: exportResult.status === 'error' ? 'var(--color-danger)' : 'var(--color-green-light)',
          }}>
            <span>{exportResult.message}</span>
            {exportResult.outputPath && (
              <button onClick={() => onOpenExportFile(exportResult.outputPath!)} style={linkBtnStyle}>{copy.rallyQueue.openExport}</button>
            )}
          </div>
        )}
        {exporting ? (
          <button onClick={onCancelExport} style={{ ...exportBtnStyle, background: 'var(--color-danger)' }}>
            {copy.rallyQueue.cancelExport}
          </button>
        ) : (
          <button
            onClick={onExport}
            disabled={summary.selectedCount === 0}
            style={{
              ...exportBtnStyle,
              background: summary.selectedCount > 0 ? 'var(--color-accent)' : '#d8cfc2',
              cursor: summary.selectedCount > 0 ? 'pointer' : 'not-allowed',
            }}
          >
            {getExportActionCopy(summary.selectedCount, false, copy)} ↗
          </button>
        )}
      </div>
    </aside>
  )
}

function RallyCard({
  segment,
  isSelected,
  onSelect,
  onToggle,
  sourceLabel,
  copy,
}: {
  segment: RallySegment
  isSelected: boolean
  onSelect: () => void
  onToggle: () => void
  sourceLabel: string
  copy: Copy
}) {
  const range = getAdjustedTimeRange(segment)
  const isEdited = segment.startAdjusted != null || segment.endAdjusted != null
  const borderColor = isSelected ? 'var(--color-accent)' : '#e5d2bd'

  return (
    <div
      onClick={onSelect}
      style={{
        ...cardStyle,
        borderColor,
        borderWidth: isSelected ? 2 : 1,
        opacity: segment.included ? 1 : 0.58,
        background: isSelected ? '#fff7ef' : 'var(--color-surface)',
        fontWeight: segment.included ? 800 : 500,
      }}
    >
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
      <div style={cardContentStyle}>
        <div style={cardTitleStyle}>
          {getRallyTitle(segment, copy)}
          {isEdited && <span style={editedDotStyle} title={copy.common.edited} />}
        </div>
        <div style={sourceStyle}>{sourceLabel}</div>
        <div style={cardMetaStyle}>
          #{String(segment.sourceIndex + 1).padStart(2, '0')} · {range.label} · {range.duration.toFixed(1)}s
        </div>
        <div style={{ ...badgeStyle, color: scoreColor(segment.score) }}>
          {toneLabel(segment, copy)} · {copy.rallyQueue.hits(segment.features.hit_count ?? copy.common.hitCountUnknown)} · {copy.rallyQueue.intensity(segment.score.toFixed(2))}
        </div>
      </div>
    </div>
  )
}

function TrimEditor({
  segment,
  currentTime,
  onSeek,
  copy,
}: {
  segment: RallySegment
  currentTime: number
  onSeek: (time: number) => void
  copy: Copy
}) {
  const { dispatch } = useAppState()
  const effectiveStart = segment.startAdjusted ?? segment.start
  const effectiveEnd = segment.endAdjusted ?? segment.end
  const isEdited = segment.startAdjusted != null || segment.endAdjusted != null
  const padding = 15
  const minDuration = 0.5
  const rangeStart = Math.max(0, segment.start - padding)
  const rangeEnd = segment.end + padding
  const rangeWidth = Math.max(rangeEnd - rangeStart, minDuration)
  const barRef = useRef<HTMLDivElement>(null)
  const dragCleanupRef = useRef<(() => void) | null>(null)
  const [dragging, setDragging] = useState<'start' | 'end' | null>(null)

  const timeToPercent = useCallback((time: number) => ((time - rangeStart) / rangeWidth) * 100, [rangeStart, rangeWidth])
  const percentToTime = useCallback((percent: number) => rangeStart + (percent / 100) * rangeWidth, [rangeStart, rangeWidth])
  const clampStart = useCallback((time: number) => Math.min(Math.max(time, rangeStart), effectiveEnd - minDuration), [effectiveEnd, rangeStart])
  const clampEnd = useCallback((time: number) => Math.max(Math.min(time, rangeEnd), effectiveStart + minDuration), [effectiveStart, rangeEnd])

  const updateStart = useCallback((time: number) => {
    const next = Math.round(clampStart(time) * 10) / 10
    dispatch({ type: 'ADJUST_RALLY', id: segment.id, start: next })
    onSeek(next)
  }, [clampStart, dispatch, onSeek, segment.id])

  const updateEnd = useCallback((time: number) => {
    const next = Math.round(clampEnd(time) * 10) / 10
    dispatch({ type: 'ADJUST_RALLY', id: segment.id, end: next })
    onSeek(next)
  }, [clampEnd, dispatch, onSeek, segment.id])

  const cleanupDrag = useCallback(() => {
    dragCleanupRef.current?.()
    dragCleanupRef.current = null
    setDragging(null)
  }, [])

  useEffect(() => {
    return () => {
      dragCleanupRef.current?.()
      dragCleanupRef.current = null
    }
  }, [])

  const handleMouseDown = useCallback((edge: 'start' | 'end') => (event: React.MouseEvent) => {
    event.preventDefault()
    event.stopPropagation()
    const bar = barRef.current
    if (!bar) return

    cleanupDrag()
    setDragging(edge)
    const onMove = (moveEvent: MouseEvent) => {
      const rect = bar.getBoundingClientRect()
      const percent = Math.max(0, Math.min(100, ((moveEvent.clientX - rect.left) / rect.width) * 100))
      const time = percentToTime(percent)
      if (edge === 'start') updateStart(time)
      else updateEnd(time)
    }

    const onUp = () => {
      cleanupDrag()
    }

    dragCleanupRef.current = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [cleanupDrag, percentToTime, updateEnd, updateStart])

  const handleReset = () => {
    dispatch({ type: 'ADJUST_RALLY', id: segment.id, start: undefined, end: undefined })
    onSeek(segment.start)
  }

  const startPct = timeToPercent(effectiveStart)
  const endPct = timeToPercent(effectiveEnd)

  return (
    <div style={trimBoxStyle} onClick={(event) => event.stopPropagation()}>
      <div style={trimHeaderStyle}>
        <span>{copy.rallyQueue.start} <b>{formatTimePrecise(effectiveStart)}</b></span>
        <span>{copy.rallyQueue.end} <b>{formatTimePrecise(effectiveEnd)}</b></span>
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
          <div
            onMouseDown={handleMouseDown('start')}
            style={{
              ...handleStyle,
              left: `${startPct}%`,
              background: dragging === 'start' ? 'var(--color-accent-hover)' : '#202020',
            }}
          />
          <div
            onMouseDown={handleMouseDown('end')}
            style={{
              ...handleStyle,
              left: `${endPct}%`,
              background: dragging === 'end' ? 'var(--color-accent-hover)' : '#202020',
            }}
          />
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
        <span>{copy.rallyQueue.trimHelp(formatTimePrecise(segment.start), formatTimePrecise(segment.end))}</span>
        {isEdited && (
          <button onClick={handleReset} style={resetBtnStyle}>
            {copy.rallyQueue.reset}
          </button>
        )}
      </div>
    </div>
  )
}

const panelStyle: React.CSSProperties = { width: 390, minWidth: 340, maxWidth: 430, margin: 16, marginLeft: 0, border: '1px solid #e5d2bd', borderRadius: 10, background: 'rgba(255,250,244,0.92)', display: 'flex', flexDirection: 'column', minHeight: 0, boxShadow: '0 12px 28px rgba(50,35,20,0.06)' }
const headerStyle: React.CSSProperties = { padding: '20px 18px 10px' }
const titleStyle: React.CSSProperties = { fontFamily: 'var(--font-display)', fontSize: 25, fontWeight: 900, color: 'var(--color-text)', margin: 0, letterSpacing: '-0.04em' }
const subtitleStyle: React.CSSProperties = { fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4, marginBottom: 0 }
const batchGridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, padding: '10px 18px 14px' }
const batchBtnStyle: React.CSSProperties = { border: '1px solid #e1cbb5', borderRadius: 4, background: 'var(--color-surface)', padding: '9px 0', fontFamily: 'var(--font-display)', fontWeight: 800, color: 'var(--color-text)' }
const listStyle: React.CSSProperties = { flex: 1, overflowY: 'auto', minHeight: 0, padding: '0 18px 12px' }
const itemWrapStyle: React.CSSProperties = { marginBottom: 10 }
const emptyStyle: React.CSSProperties = { padding: 18, border: '1px dashed #e1cbb5', borderRadius: 8, color: 'var(--color-text-secondary)', fontSize: 13 }
const cardStyle: React.CSSProperties = { display: 'flex', gap: 12, border: '1px solid #e5d2bd', borderRadius: 8, padding: 12, cursor: 'pointer', transition: 'border-color 0.15s, background 0.15s, opacity 0.15s' }
const checkboxStyle: React.CSSProperties = { width: 22, height: 22, accentColor: 'var(--color-green)', flexShrink: 0, cursor: 'pointer' }
const cardContentStyle: React.CSSProperties = { minWidth: 0, flex: 1 }
const cardTitleStyle: React.CSSProperties = { fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 900, color: 'var(--color-text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }
const sourceStyle: React.CSSProperties = { fontSize: 10, color: 'var(--color-text-secondary)', marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }
const cardMetaStyle: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 4 }
const badgeStyle: React.CSSProperties = { fontSize: 11, fontWeight: 700, marginTop: 6 }
const editedDotStyle: React.CSSProperties = { width: 6, height: 6, borderRadius: '50%', background: 'var(--color-accent)', display: 'inline-block', marginLeft: 6, verticalAlign: 'middle' }
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
