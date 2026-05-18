import { useEffect, useState } from 'react'

interface Props {
  onVideoSelected: (path: string) => void
}

export default function WelcomeScreen({ onVideoSelected }: Props) {
  const [recent, setRecent] = useState<string[]>([])

  useEffect(() => {
    window.api.getRecentProjects().then(setRecent)
  }, [])

  const handleOpen = async () => {
    const path = await window.api.openFileDialog()
    if (path) onVideoSelected(path)
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      gap: 32,
      WebkitAppRegion: 'drag',
    } as React.CSSProperties}>
      <h1 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 48,
        fontWeight: 900,
        color: 'var(--color-text)',
        letterSpacing: '-0.02em',
        textTransform: 'uppercase',
      }}>
        BREAK<span style={{ color: 'var(--color-accent)' }}>POINT</span><span style={{ color: 'var(--color-accent)' }}>.</span>
      </h1>

      <p style={{ color: 'var(--color-text-secondary)', fontSize: 14 }}>
        Tennis highlight extraction
      </p>

      <button
        onClick={handleOpen}
        style={{
          padding: '14px 28px',
          background: 'var(--color-accent)',
          color: '#fff',
          borderRadius: 'var(--radius-sm)',
          fontSize: 13,
          fontWeight: 700,
          fontFamily: 'var(--font-display)',
          letterSpacing: '0.08em',
          textTransform: 'uppercase' as const,
          transition: 'background 0.15s',
          WebkitAppRegion: 'no-drag',
        } as React.CSSProperties}
        onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-accent-hover)'}
        onMouseLeave={(e) => e.currentTarget.style.background = 'var(--color-accent)'}
      >
        Open Video
      </button>

      {recent.length > 0 && (
        <div style={{ marginTop: 16, textAlign: 'center', WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
          <p style={{
            fontSize: 12,
            color: 'var(--color-text-secondary)',
            marginBottom: 8,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}>
            Recent
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {recent.slice(0, 5).map((p) => (
              <button
                key={p}
                onClick={() => onVideoSelected(p)}
                style={{
                  fontSize: 13,
                  color: 'var(--color-green-dark)',
                  padding: '4px 8px',
                  borderRadius: 'var(--radius-sm)',
                  fontFamily: 'var(--font-mono)',
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-surface)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                {p.split(/[\\/]/).pop()}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
