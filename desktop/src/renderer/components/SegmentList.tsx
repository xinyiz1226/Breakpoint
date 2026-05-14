import { useState, useRef, useCallback, useEffect, createRef } from 'react'
import { useAppState, Segment } from '../state/AppState'

function formatTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function formatTimePrecise(s: number): string {
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1)
  return `${m}:${sec.padStart(4, '0')}`
}

function scoreColor(score: number): string {
  if (score > 2.3) return '#C75B2F'
  if (score > 1.7) return '#5A8C6F'
  return '#A0937D'
}

interface Props {
  onSeek: (time: number) => void
  onSeekAndPlay: (time: number) => void
  currentTime: number
}

export default function SegmentList({ onSeek, onSeekAndPlay, currentTime }: Props) {
  const { state, dispatch } = useAppState()
  const { segments, selectedSegmentIndex } = state
  const itemRefs = useRef<(HTMLDivElement | null)[]>([])

  useEffect(() => {
    if (selectedSegmentIndex != null && itemRefs.current[selectedSegmentIndex]) {
      itemRefs.current[selectedSegmentIndex]!.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [selectedSegmentIndex])

  if (segments.length === 0) return null

  return (
    <div style={{
      background: 'var(--color-cream)',
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      minHeight: 0,
    }}>
      <div style={{ flexShrink: 0 }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 12px 3px 12px',
          fontSize: 11,
          color: 'var(--color-terre)',
          whiteSpace: 'nowrap',
        }}>
          <span onClick={() => dispatch({ type: 'INCLUDE_ALL' })} style={{ cursor: 'pointer' }}>All</span>
          <span style={{ color: 'var(--color-border)' }}>|</span>
          <span onClick={() => dispatch({ type: 'EXCLUDE_ALL' })} style={{ cursor: 'pointer' }}>None</span>
          <span style={{ color: 'var(--color-border)' }}>|</span>
          <span onClick={() => dispatch({ type: 'RESET_ALL' })} style={{ cursor: 'pointer' }}>Reset</span>
        </div>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '0 12px 4px 12px',
          fontSize: 10,
          color: 'var(--color-text-secondary)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          whiteSpace: 'nowrap',
          borderBottom: '1px solid var(--color-border)',
        }}>
          <span style={{ width: 15, flexShrink: 0 }} />
          <span style={{ width: 28 }}>#</span>
          <span style={{ width: 56 }}>Start</span>
          <span style={{ width: 48 }}>Dur</span>
          <span style={{ width: 36 }}>Hits</span>
          <span>Score</span>
        </div>
      </div>
      <div style={{
        flex: 1,
        overflowY: 'auto',
        minHeight: 0,
      }}>
      {segments.map((seg, i) => {
        const isSelected = i === selectedSegmentIndex
        const isEdited = seg.startAdjusted != null || seg.endAdjusted != null
        return (
          <div key={i} ref={(el) => { itemRefs.current[i] = el }}>
            <div
              onClick={() => {
                dispatch({ type: 'SELECT_SEGMENT', index: i })
                onSeekAndPlay(seg.startAdjusted ?? seg.start)
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 12px',
                cursor: 'pointer',
                background: isSelected ? 'var(--color-cream-dark)' : 'transparent',
                opacity: seg.included ? 1 : 0.45,
                fontSize: 13,
                fontFamily: 'var(--font-mono)',
                borderLeft: isSelected ? '3px solid var(--color-terre)' : '3px solid transparent',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
              }}
            >
              <input
                type="checkbox"
                checked={seg.included}
                onChange={(e) => {
                  e.stopPropagation()
                  dispatch({ type: 'TOGGLE_INCLUDE', index: i })
                }}
                onClick={(e) => e.stopPropagation()}
                style={{ accentColor: 'var(--color-terre)', width: 15, height: 15, cursor: 'pointer', flexShrink: 0 }}
              />
              <span style={{ width: 28, color: 'var(--color-text-secondary)' }}>{i + 1}</span>
              <span style={{ width: 56 }}>
                {formatTime(seg.startAdjusted ?? seg.start)}
              </span>
              <span style={{ width: 48, color: 'var(--color-text-secondary)' }}>
                {((seg.endAdjusted ?? seg.end) - (seg.startAdjusted ?? seg.start)).toFixed(1)}s
              </span>
              <span style={{ width: 36, color: 'var(--color-text-secondary)' }}>
                {seg.features.hit_count ?? '?'}
              </span>
              <span style={{ color: scoreColor(seg.score), fontWeight: 500 }}>
                {seg.score.toFixed(2)}
              </span>
              {isEdited && (
                <span title="edited" style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: 'var(--color-terre)',
                  flexShrink: 0,
                }} />
              )}
            </div>

            {isSelected && (
              <TrimEditor
                segment={seg}
                index={i}
                currentTime={currentTime}
                onSeek={onSeek}
              />
            )}
          </div>
        )
      })}
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
  onSeek: (t: number) => void
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

  const timeToPercent = (t: number) => ((t - rangeStart) / rangeWidth) * 100
  const percentToTime = (pct: number) => rangeStart + (pct / 100) * rangeWidth

  const handleMouseDown = useCallback((edge: 'start' | 'end') => (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragging(edge)

    const bar = barRef.current
    if (!bar) return

    const onMove = (ev: MouseEvent) => {
      const rect = bar.getBoundingClientRect()
      const pct = Math.max(0, Math.min(100, ((ev.clientX - rect.left) / rect.width) * 100))
      const t = Math.round(percentToTime(pct) * 10) / 10

      if (edge === 'start') {
        const maxStart = (segment.endAdjusted ?? segment.end) - 0.5
        const clamped = Math.min(t, maxStart)
        dispatch({ type: 'ADJUST_SEGMENT', index, start: clamped })
        onSeek(clamped)
      } else {
        const minEnd = (segment.startAdjusted ?? segment.start) + 0.5
        const clamped = Math.max(t, minEnd)
        dispatch({ type: 'ADJUST_SEGMENT', index, end: clamped })
        onSeek(clamped)
      }
    }

    const onUp = () => {
      setDragging(null)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [dispatch, index, segment, rangeStart, rangeWidth])

  const handleReset = () => {
    dispatch({ type: 'ADJUST_SEGMENT', index, start: undefined, end: undefined })
  }

  const startPct = timeToPercent(effectiveStart)
  const endPct = timeToPercent(effectiveEnd)

  return (
    <div style={{
      padding: '10px 16px 14px 19px',
      background: 'var(--color-cream-dark)',
      borderLeft: '3px solid var(--color-terre)',
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
    }}>
      {/* Draggable range bar */}
      <div
        ref={barRef}
        style={{
          position: 'relative',
          height: 28,
          background: 'var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          overflow: 'visible',
          cursor: 'default',
          userSelect: 'none',
        }}
      >
        {/* Original range ghost */}
        <div style={{
          position: 'absolute',
          left: `${timeToPercent(segment.start)}%`,
          width: `${timeToPercent(segment.end) - timeToPercent(segment.start)}%`,
          height: '100%',
          background: 'var(--color-gold-light)',
          opacity: 0.3,
          borderRadius: 2,
        }} />

        {/* Active range fill */}
        <div style={{
          position: 'absolute',
          left: `${startPct}%`,
          width: `${endPct - startPct}%`,
          height: '100%',
          background: 'var(--color-terre)',
          opacity: 0.45,
          borderRadius: 2,
        }} />

        {/* Start handle */}
        <div
          onMouseDown={handleMouseDown('start')}
          style={{
            position: 'absolute',
            left: `${startPct}%`,
            top: -2,
            width: 8,
            height: 32,
            marginLeft: -4,
            background: dragging === 'start' ? 'var(--color-terre-dark)' : 'var(--color-terre)',
            borderRadius: 3,
            cursor: 'ew-resize',
            zIndex: 2,
            boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
            transition: dragging ? 'none' : 'left 0.05s ease-out',
          }}
        />

        {/* End handle */}
        <div
          onMouseDown={handleMouseDown('end')}
          style={{
            position: 'absolute',
            left: `${endPct}%`,
            top: -2,
            width: 8,
            height: 32,
            marginLeft: -4,
            background: dragging === 'end' ? 'var(--color-terre-dark)' : 'var(--color-terre)',
            borderRadius: 3,
            cursor: 'ew-resize',
            zIndex: 2,
            boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
            transition: dragging ? 'none' : 'left 0.05s ease-out',
          }}
        />

        {/* Current playhead */}
        {currentTime >= rangeStart && currentTime <= rangeEnd && (
          <div style={{
            position: 'absolute',
            left: `${timeToPercent(currentTime)}%`,
            width: 2,
            height: '100%',
            background: '#fff',
            boxShadow: '0 0 4px rgba(0,0,0,0.4)',
            zIndex: 1,
            pointerEvents: 'none',
          }} />
        )}
      </div>

      {/* Info row */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        color: 'var(--color-text-secondary)',
      }}>
        <span style={{ color: 'var(--color-terre)', fontWeight: 500 }}>
          {formatTimePrecise(effectiveStart)}
        </span>
        <span>—</span>
        <span style={{ color: 'var(--color-terre)', fontWeight: 500 }}>
          {formatTimePrecise(effectiveEnd)}
        </span>
        <span>({(effectiveEnd - effectiveStart).toFixed(1)}s)</span>

        <div style={{ flex: 1 }} />

        {isEdited && (
          <button onClick={handleReset} style={{ ...trimBtn, color: 'var(--color-danger)' }}>
            Reset
          </button>
        )}
      </div>

      {isEdited && (
        <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', opacity: 0.6 }}>
          original: {formatTimePrecise(segment.start)} – {formatTimePrecise(segment.end)}
        </div>
      )}
    </div>
  )
}

const trimBtn: React.CSSProperties = {
  fontSize: 11,
  padding: '3px 8px',
  color: 'var(--color-text)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--color-cream)',
  fontFamily: 'var(--font-body)',
}
