import { useRef, useState, useEffect, useCallback } from 'react'

interface Props {
  videoPath: string
  onTimeUpdate?: (time: number) => void
  onDurationChange?: (duration: number) => void
  seekTo?: number | null
  seekKey?: number
  autoPlay?: boolean
  pauseAt?: number | null
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export default function VideoPlayer({ videoPath, onTimeUpdate, onDurationChange, seekTo, seekKey, autoPlay, pauseAt }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)

  const togglePlay = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) { v.play(); setPlaying(true) }
    else { v.pause(); setPlaying(false) }
  }, [])

  const skip = useCallback((delta: number) => {
    const v = videoRef.current
    if (!v) return
    v.currentTime = Math.max(0, Math.min(v.duration, v.currentTime + delta))
  }, [])

  useEffect(() => {
    if (seekTo != null && videoRef.current) {
      videoRef.current.currentTime = seekTo
      if (autoPlay) {
        videoRef.current.play()
      }
    }
  }, [seekTo, seekKey, autoPlay])

  const pauseAtRef = useRef<number | null>(null)
  const pauseFiredRef = useRef(false)
  pauseAtRef.current = pauseAt ?? null

  useEffect(() => {
    pauseFiredRef.current = false
  }, [seekKey])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.code === 'Space') { e.preventDefault(); togglePlay() }
      if (e.code === 'ArrowLeft') { e.preventDefault(); skip(-5) }
      if (e.code === 'ArrowRight') { e.preventDefault(); skip(5) }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [togglePlay, skip])

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    if (videoRef.current) videoRef.current.currentTime = ratio * duration
  }

  const src = videoPath.startsWith('file://') ? videoPath : `file:///${videoPath.replace(/\\/g, '/')}`

  return (
    <div style={playerRootStyle}>
      <div style={videoViewportStyle}>
        <video
          ref={videoRef}
          src={src}
          style={videoElementStyle}
          onTimeUpdate={() => {
            const v = videoRef.current
            if (!v) return
            const t = v.currentTime
            setCurrentTime(t)
            onTimeUpdate?.(t)
            if (pauseAtRef.current != null && !pauseFiredRef.current && t >= pauseAtRef.current && !v.paused) {
              pauseFiredRef.current = true
              v.pause()
            }
          }}
          onLoadedMetadata={() => {
            const d = videoRef.current?.duration ?? 0
            setDuration(d)
            onDurationChange?.(d)
          }}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onClick={togglePlay}
        />
      </div>

      <div style={controlBarStyle}>
        <button onClick={() => skip(-10)} style={controlBtn} title="Back 10s">
          ⏪
        </button>
        <button onClick={togglePlay} style={{ ...controlBtn, fontSize: 18, width: 36 }}>
          {playing ? '⏸' : '▶'}
        </button>
        <button onClick={() => skip(10)} style={controlBtn} title="Forward 10s">
          ⏩
        </button>

        <span style={{ color: '#ccc', fontSize: 12, fontFamily: 'var(--font-mono)', minWidth: 48, textAlign: 'center' }}>
          {formatTime(currentTime)}
        </span>

        <div
          onClick={handleSeek}
          style={{
            flex: 1,
            height: 6,
            background: 'rgba(255,255,255,0.2)',
            borderRadius: 3,
            cursor: 'pointer',
          }}
        >
          <div style={{
            width: `${duration > 0 ? (currentTime / duration) * 100 : 0}%`,
            height: '100%',
            background: 'var(--color-accent)',
            borderRadius: 3,
            transition: 'width 0.1s linear',
          }} />
        </div>

        <span style={{ color: '#ccc', fontSize: 12, fontFamily: 'var(--font-mono)', minWidth: 48, textAlign: 'center' }}>
          {formatTime(duration)}
        </span>
      </div>
    </div>
  )
}

const playerRootStyle: React.CSSProperties = {
  flex: '1 1 0',
  minHeight: 0,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
  background: '#000',
}

const videoViewportStyle: React.CSSProperties = {
  flex: '1 1 0',
  minHeight: 0,
  minWidth: 0,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}

const videoElementStyle: React.CSSProperties = {
  display: 'block',
  width: '100%',
  height: '100%',
  maxWidth: '100%',
  maxHeight: '100%',
  objectFit: 'contain',
}

const controlBarStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 16px',
  background: 'rgba(0,0,0,0.85)',
  flexShrink: 0,
}

const controlBtn: React.CSSProperties = {
  color: '#fff',
  fontSize: 14,
  width: 32,
  height: 32,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}
