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
      WebkitAppRegion: 'drag' as any,
    }}>
      <h1 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 48,
        fontWeight: 700,
        color: 'var(--color-terre)',
        letterSpacing: '-0.02em',
      }}>
        Breakpoint
      </h1>

      <p style={{ color: 'var(--color-text-secondary)', fontSize: 14 }}>
        Tennis highlight extraction
      </p>

      <button
        onClick={handleOpen}
        style={{
          padding: '12px 32px',
          background: 'var(--color-terre)',
          color: '#fff',
          borderRadius: 'var(--radius-md)',
          fontSize: 15,
          fontWeight: 600,
          transition: 'background 0.15s',
          WebkitAppRegion: 'no-drag' as any,
        }}
        onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-terre-dark)'}
        onMouseLeave={(e) => e.currentTarget.style.background = 'var(--color-terre)'}
      >
        Open Video
      </button>

      {recent.length > 0 && (
        <div style={{ marginTop: 16, textAlign: 'center', WebkitAppRegion: 'no-drag' as any }}>
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
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-cream-dark)'}
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
