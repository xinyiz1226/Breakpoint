import { useAppState, Segment } from '../state/AppState'

function scoreColor(score: number): string {
  if (score > 2.3) return '#C75B2F'
  if (score > 1.7) return '#5A8C6F'
  return '#A0937D'
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

interface Props {
  onSeek: (time: number) => void
}

export default function Timeline({ onSeek }: Props) {
  const { state, dispatch } = useAppState()
  const { segments, selectedSegmentIndex, videoDuration } = state

  if (videoDuration <= 0 || segments.length === 0) return null

  return (
    <div style={{
      padding: '8px 16px',
      borderTop: '1px solid var(--color-border)',
      background: 'var(--color-cream)',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 4,
      }}>
        <span style={{ fontSize: 11, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Timeline
        </span>
        <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--color-text-secondary)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: '#C75B2F', opacity: 0.7, display: 'inline-block' }} />
            High
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: '#5A8C6F', opacity: 0.7, display: 'inline-block' }} />
            Mid
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: '#A0937D', opacity: 0.7, display: 'inline-block' }} />
            Low
          </span>
        </div>
      </div>
      <div style={{
        position: 'relative',
        height: 32,
        background: 'var(--color-cream-dark)',
        borderRadius: 'var(--radius-sm)',
        overflow: 'hidden',
      }}>
        {segments.map((seg, i) => {
          const left = (seg.start / videoDuration) * 100
          const width = ((seg.end - seg.start) / videoDuration) * 100
          const isSelected = i === selectedSegmentIndex
          return (
            <div
              key={i}
              onClick={() => {
                dispatch({ type: 'SELECT_SEGMENT', index: i })
                onSeek(seg.startAdjusted ?? seg.start)
              }}
              title={`${formatTime(seg.start)} – ${formatTime(seg.end)} (score: ${seg.score.toFixed(2)})`}
              style={{
                position: 'absolute',
                left: `${left}%`,
                width: `${Math.max(width, 0.3)}%`,
                height: '100%',
                background: scoreColor(seg.score),
                opacity: seg.included ? 0.7 : 0.3,
                border: seg.included ? 'none' : '1px dashed rgba(0,0,0,0.3)',
                boxSizing: 'border-box' as const,
                cursor: 'pointer',
                outline: isSelected ? '2px solid var(--color-text)' : 'none',
                outlineOffset: -2,
                transition: 'opacity 0.15s',
              }}
            />
          )
        })}
      </div>

      {selectedSegmentIndex != null && (
        <DetailBar segment={segments[selectedSegmentIndex]} index={selectedSegmentIndex} />
      )}
    </div>
  )
}

function DetailBar({ segment, index }: { segment: Segment; index: number }) {
  return (
    <div style={{
      display: 'flex',
      gap: 24,
      padding: '8px 0 4px',
      fontSize: 12,
      fontFamily: 'var(--font-mono)',
      color: 'var(--color-text-secondary)',
    }}>
      <span>#{index + 1}</span>
      <span>{formatTime(segment.start)} – {formatTime(segment.end)}</span>
      <span>{(segment.end - segment.start).toFixed(1)}s</span>
      <span>{segment.features.hit_count ?? '?'} hits</span>
      <span style={{ color: scoreColor(segment.score) }}>
        score {segment.score.toFixed(3)}
      </span>
      {!segment.included && <span style={{ color: 'var(--color-text-secondary)', opacity: 0.6 }}>excluded</span>}
    </div>
  )
}
