import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
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

function toneHeight(tone: ReturnType<typeof getSegmentTone>): number {
  if (tone === 'highlight') return 58
  if (tone === 'keep') return 46
  return 24
}

export default function MatchMap({ onSeek }: Props) {
  const { state, dispatch } = useAppState()
  const { segments, selectedSegmentIndex, videoDuration } = state
  const [recommendedOnly, setRecommendedOnly] = useState(false)

  const visibleSegments = useMemo(() => {
    return segments
      .map((segment, originalIndex) => ({ segment, originalIndex }))
      .filter(({ segment }) => !recommendedOnly || segment.score > INCLUDE_THRESHOLD || segment.included)
  }, [recommendedOnly, segments])

  if (videoDuration <= 0 || segments.length === 0) return null
  const safeDuration = Math.max(videoDuration, 1)

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
        {visibleSegments.map(({ segment, originalIndex }) => {
          const range = getAdjustedTimeRange(segment)
          const left = (segment.start / safeDuration) * 100
          const width = Math.max(((segment.end - segment.start) / safeDuration) * 100, 0.55)
          const isSelected = originalIndex === selectedSegmentIndex
          const tone = getSegmentTone(segment)

          return (
            <button
              key={originalIndex}
              title={`#${String(originalIndex + 1).padStart(2, '0')} · ${range.label} · 强度 ${segment.score.toFixed(2)}`}
              onClick={() => {
                dispatch({ type: 'SELECT_SEGMENT', index: originalIndex })
                onSeek(range.start)
              }}
              style={{
                ...barStyle,
                left: `${left}%`,
                width: `${width}%`,
                height: toneHeight(tone),
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

const mapShellStyle: CSSProperties = { margin: '0 16px 16px', border: '1px solid #e5d2bd', borderRadius: 10, background: 'rgba(255,250,244,0.9)', padding: 20, boxShadow: '0 12px 28px rgba(50,35,20,0.05)' }
const mapHeaderStyle: CSSProperties = { display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 18 }
const mapTitleStyle: CSSProperties = { fontFamily: 'var(--font-display)', fontSize: 23, fontWeight: 900, color: 'var(--color-text)', letterSpacing: '-0.04em', margin: 0 }
const mapSubtitleStyle: CSSProperties = { fontSize: 13, color: 'var(--color-text-secondary)', marginTop: 6 }
const legendStyle: CSSProperties = { display: 'flex', gap: 14, alignItems: 'center', fontSize: 11, color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }
const legendItemStyle: CSSProperties = { display: 'inline-flex', gap: 5, alignItems: 'center' }
const legendDotStyle: CSSProperties = { width: 8, height: 8, borderRadius: '50%', display: 'inline-block' }
const barViewportStyle: CSSProperties = { position: 'relative', height: 132, border: '1px solid #ead8c5', borderRadius: 7, background: 'repeating-linear-gradient(90deg, rgba(0,0,0,0.04) 0, rgba(0,0,0,0.04) 1px, transparent 1px, transparent 48px)', overflow: 'hidden' }
const barStyle: CSSProperties = { position: 'absolute', bottom: 22, minWidth: 7, border: 0, borderRadius: 3, cursor: 'pointer', padding: 0, transition: 'height 0.15s, opacity 0.15s, outline 0.15s' }
const timeMarkerStyle: CSSProperties = { position: 'absolute', top: -25, left: '50%', transform: 'translateX(-50%)', background: '#222', color: '#fff', borderRadius: 3, padding: '3px 5px', fontFamily: 'var(--font-mono)', fontSize: 10, whiteSpace: 'nowrap' }
const mapFooterStyle: CSSProperties = { display: 'flex', alignItems: 'center', gap: 16, marginTop: 14 }
const progressLineStyle: CSSProperties = { flex: 1, height: 7, borderRadius: 999, background: '#dfd6c9', overflow: 'hidden' }
const progressFillLineStyle: CSSProperties = { display: 'block', height: '100%', background: 'linear-gradient(90deg, var(--color-green), var(--color-accent))' }
const filterBtnStyle: CSSProperties = { border: '1px solid #e1cbb5', borderRadius: 4, background: 'var(--color-surface)', padding: '9px 13px', fontFamily: 'var(--font-display)', fontWeight: 900, color: 'var(--color-text)' }
