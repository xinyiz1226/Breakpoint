import type { VideoRecord } from '../state/AppState'
import { useCopy, type Copy } from '../i18n'

interface Props {
  videos: VideoRecord[]
  activeVideoId: string | null
  onSelect: (videoId: string) => void
  onRetry: (videoId: string) => void
}

function statusLabel(video: VideoRecord, copy: Copy): string {
  if (video.status === 'running') return copy.batch.running
  if (video.status === 'done') return copy.batch.done
  if (video.status === 'error') return copy.batch.failed
  return copy.batch.pending
}

function statusColor(video: VideoRecord): string {
  if (video.status === 'running') return 'var(--color-accent)'
  if (video.status === 'done') return 'var(--color-green-light)'
  if (video.status === 'error') return 'var(--color-danger)'
  return 'var(--color-text-secondary)'
}

export default function BatchVideoList({ videos, activeVideoId, onSelect, onRetry }: Props) {
  const copy = useCopy()
  const doneCount = videos.filter((video) => video.status === 'done').length

  return (
    <aside style={panelStyle}>
      <div style={headerStyle}>
        <h2 style={titleStyle}>{copy.batch.title}</h2>
        <p style={subtitleStyle}>{copy.batch.successfulVideos(doneCount, videos.length)}</p>
      </div>

      <div style={listStyle}>
        {videos.map((video, index) => {
          const isActive = video.id === activeVideoId
          const color = statusColor(video)
          return (
            <div
              key={video.id}
              onClick={() => onSelect(video.id)}
              style={{
                ...cardStyle,
                borderColor: isActive ? 'var(--color-accent)' : '#e5d2bd',
                borderWidth: isActive ? 2 : 1,
                background: isActive ? '#fff7ef' : 'var(--color-surface)',
              }}
            >
              <div style={progressPillStyle}>{copy.batch.videoProgress(index + 1, videos.length)}</div>
              <div style={cardContentStyle}>
                <div style={cardTitleStyle}>{video.displayName}</div>
                <div style={cardPathStyle}>{video.path}</div>
                {video.errorMessage && <div style={errorStyle}>{video.errorMessage}</div>}
              </div>
              <div style={statusWrapStyle}>
                <strong style={{ ...statusStyle, color }}>{statusLabel(video, copy)}</strong>
                {video.status === 'error' && (
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={(event) => {
                      event.stopPropagation()
                      onRetry(video.id)
                    }}
                    onKeyDown={(event) => {
                      if (event.key !== 'Enter' && event.key !== ' ') return
                      event.stopPropagation()
                      onRetry(video.id)
                    }}
                    style={retryStyle}
                  >
                    {copy.batch.retryVideo}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </aside>
  )
}

const panelStyle: React.CSSProperties = { width: 320, minWidth: 280, maxWidth: 360, margin: 16, marginRight: 0, border: '1px solid #e5d2bd', borderRadius: 10, background: 'rgba(255,250,244,0.92)', display: 'flex', flexDirection: 'column', minHeight: 0, boxShadow: '0 12px 28px rgba(50,35,20,0.06)' }
const headerStyle: React.CSSProperties = { padding: '18px 16px 10px' }
const titleStyle: React.CSSProperties = { fontFamily: 'var(--font-display)', fontSize: 23, fontWeight: 900, color: 'var(--color-text)', margin: 0, letterSpacing: '-0.04em' }
const subtitleStyle: React.CSSProperties = { fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4, marginBottom: 0 }
const listStyle: React.CSSProperties = { flex: 1, overflowY: 'auto', minHeight: 0, padding: '0 16px 16px' }
const cardStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'auto 1fr auto', alignItems: 'start', gap: 10, border: '1px solid #e5d2bd', borderRadius: 8, padding: 12, cursor: 'pointer', marginBottom: 10, transition: 'border-color 0.15s, background 0.15s' }
const progressPillStyle: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-secondary)', border: '1px solid #e1cbb5', borderRadius: 999, padding: '3px 7px', whiteSpace: 'nowrap' }
const cardContentStyle: React.CSSProperties = { minWidth: 0 }
const cardTitleStyle: React.CSSProperties = { fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 900, color: 'var(--color-text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }
const cardPathStyle: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-secondary)', marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }
const errorStyle: React.CSSProperties = { color: 'var(--color-danger)', fontSize: 11, lineHeight: 1.45, marginTop: 8 }
const statusWrapStyle: React.CSSProperties = { display: 'grid', gap: 8, justifyItems: 'end', textAlign: 'right' }
const statusStyle: React.CSSProperties = { fontSize: 11, fontWeight: 900, whiteSpace: 'nowrap' }
const retryStyle: React.CSSProperties = { fontSize: 11, fontWeight: 900, color: 'var(--color-accent)', textDecoration: 'underline', cursor: 'pointer' }
