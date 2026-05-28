import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { useCopy } from '../i18n'

interface Props {
  onVideoSelected: (path: string) => void
  languageSwitch: ReactNode
}

const heroPanel: CSSProperties = {
  position: 'relative',
  background: 'linear-gradient(135deg, #033629 0%, #0a2e22 40%, #1a1008 70%, #3a1a08 100%)',
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'center',
  padding: 48,
  overflow: 'hidden',
  WebkitAppRegion: 'drag',
} as CSSProperties

const actionPanel: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'center',
  padding: 48,
  position: 'relative',
  background: 'var(--color-bg)',
  WebkitAppRegion: 'drag',
} as CSSProperties

export default function WelcomeScreen({ onVideoSelected, languageSwitch }: Props) {
  const copy = useCopy()
  const [recent, setRecent] = useState<string[]>([])
  const [appVersion, setAppVersion] = useState('')
  const [dragOver, setDragOver] = useState(false)

  useEffect(() => {
    window.api.getRecentProjects().then(setRecent)
    window.api.getAppVersion().then(setAppVersion)
  }, [])

  const handleOpen = async () => {
    const path = await window.api.openFileDialog()
    if (path) onVideoSelected(path)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) onVideoSelected((file as any).path)
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', height: '100vh' }}>
      {/* Hero panel */}
      <div style={heroPanel}>
        {/* Court texture overlay */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: 'repeating-linear-gradient(0deg, transparent, transparent 48px, rgba(255,255,255,0.03) 48px, rgba(255,255,255,0.03) 50px), repeating-linear-gradient(90deg, transparent, transparent 48px, rgba(255,255,255,0.03) 48px, rgba(255,255,255,0.03) 50px)',
        }} />
        {/* Warm glow */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: 'radial-gradient(ellipse 120% 80% at 70% 60%, rgba(204,78,14,0.15), transparent 70%), radial-gradient(ellipse 80% 100% at 30% 80%, rgba(204,78,14,0.08), transparent 60%)',
        }} />

        <div style={{ position: 'relative', zIndex: 2 }}>
          <svg width="40" height="40" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" style={{ marginBottom: 32, opacity: 0.9 }}>
            <circle cx="16" cy="16" r="14" fill="none" stroke="#fff" strokeWidth="2.4"/>
            <path d="M10 4.5Q16 14 10 27.5" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round"/>
            <path d="M22 4.5Q16 14 22 27.5" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round"/>
          </svg>

          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 700,
            letterSpacing: '0.22em', textTransform: 'uppercase', color: '#cc4e0e',
            marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <span style={{ width: 28, height: 2, background: '#cc4e0e', display: 'inline-block' }} />
            {copy.welcome.eyebrow}
          </div>

          <h1 style={{
            fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: 48,
            lineHeight: 0.95, letterSpacing: '-0.03em', color: '#fff', textTransform: 'uppercase',
            marginBottom: 16,
          }}>
            BREAK<span style={{ color: '#cc4e0e' }}>POINT</span><span style={{ color: '#cc4e0e' }}>.</span>
          </h1>

          <p style={{ fontSize: 14, color: 'rgba(255,255,255,0.5)', maxWidth: 300, lineHeight: 1.7 }}>
            {copy.welcome.description}
          </p>

          <div style={{
            marginTop: 40, display: 'inline-flex', alignItems: 'center', gap: 8,
            fontFamily: 'var(--font-mono)', fontSize: 11, color: 'rgba(255,255,255,0.3)', letterSpacing: '0.04em',
          }}>
            <span style={{ width: 6, height: 6, background: '#068d6d', borderRadius: '50%', display: 'inline-block' }} />
            v{appVersion || '0.0.0'} — {copy.common.desktop}
          </div>
        </div>
      </div>

      {/* Action panel */}
      <div style={actionPanel}>
        <div style={{ position: 'relative', zIndex: 2, maxWidth: 360, WebkitAppRegion: 'no-drag' } as CSSProperties}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 24 }}>
            {languageSwitch}
          </div>

          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 700,
            letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--color-text-secondary)',
            marginBottom: 20,
          }}>
            {copy.welcome.startLabel}
          </div>

          <button onClick={handleOpen} style={{
            display: 'flex', alignItems: 'center', gap: 14, width: '100%',
            padding: '18px 20px', background: 'var(--color-surface)',
            border: '1.5px solid var(--color-border)', borderRadius: 'var(--radius-md)',
            cursor: 'pointer', textAlign: 'left', transition: 'border-color 0.15s, box-shadow 0.15s',
          }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--color-accent)'; e.currentTarget.style.boxShadow = '0 2px 12px rgba(204,78,14,0.08)' }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--color-border)'; e.currentTarget.style.boxShadow = 'none' }}
          >
            <div style={{
              width: 40, height: 40, background: 'var(--color-accent)', borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                <polyline points="14,2 14,8 20,8"/>
                <line x1="12" y1="18" x2="12" y2="12"/>
                <polyline points="9,15 12,12 15,15"/>
              </svg>
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 13, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--color-text)' }}>
                {copy.welcome.importTitle}
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                {copy.welcome.importDetail}
              </div>
            </div>
          </button>

          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            style={{
              marginTop: 12, border: `1.5px dashed ${dragOver ? 'var(--color-accent)' : 'var(--color-border)'}`,
              borderRadius: 'var(--radius-md)', padding: '24px 20px', textAlign: 'center',
              background: dragOver ? 'rgba(204,78,14,0.04)' : 'transparent', transition: 'all 0.2s',
            }}
          >
            <p style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>{copy.welcome.dropHint}</p>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'rgba(110,110,110,0.6)', marginTop: 4 }}>.mp4 · .mov · .avi · .mkv</p>
          </div>

          {recent.length > 0 && (
            <div style={{ marginTop: 32 }}>
              <div style={{
                fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 700,
                letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--color-text-secondary)',
                marginBottom: 10,
              }}>
                {copy.welcome.recentTitle}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {recent.slice(0, 5).map((p) => (
                  <button
                    key={p}
                    onClick={() => onVideoSelected(p)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '8px 10px', borderRadius: 'var(--radius-sm)',
                      cursor: 'pointer', textAlign: 'left', width: '100%',
                      border: 'none', background: 'transparent', transition: 'background 0.1s',
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-surface)'}
                    onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-green)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                      <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                    </svg>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-green-dark)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.split(/[\\/]/).pop()}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Keyboard shortcuts */}
        <div style={{
          position: 'absolute', bottom: 20, left: 48, right: 48,
          display: 'flex', gap: 20, WebkitAppRegion: 'no-drag',
        } as CSSProperties}>
          {[[ 'Ctrl+O', copy.welcome.shortcutImport ], [ 'Ctrl+Q', copy.welcome.shortcutQuit ]].map(([key, label]) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--color-text-secondary)' }}>
              <kbd style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 5px',
                border: '1px solid var(--color-border)', borderRadius: 3, background: 'var(--color-surface)',
              }}>{key}</kbd>
              {label}
            </div>
          ))}
        </div>

        {/* Court accent line */}
        <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 3, background: 'var(--color-accent)' }} />
      </div>
    </div>
  )
}
