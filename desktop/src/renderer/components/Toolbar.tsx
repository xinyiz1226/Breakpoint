import { useAppState } from '../state/AppState'

interface Props {
  onOpenVideo: () => void
  onReanalyze: () => void
  onExport: () => void
}

export default function Toolbar({ onOpenVideo, onReanalyze, onExport }: Props) {
  const { state, dispatch } = useAppState()
  const includedCount = state.segments.filter((s) => s.included).length
  const totalCount = state.segments.length

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '6px 16px',
      borderBottom: '1px solid var(--color-border)',
      background: 'var(--color-cream)',
      fontSize: 13,
    }}>
      <button onClick={onOpenVideo} style={btnStyle}>
        Open Video
      </button>
      <button onClick={onReanalyze} style={btnStyle}>
        Re-analyze
      </button>

      <div style={{ flex: 1 }} />

      <span style={{
        fontSize: 12,
        color: 'var(--color-text-secondary)',
        fontFamily: 'var(--font-mono)',
      }}>
        {includedCount}/{totalCount} selected
      </span>

      <button onClick={onExport} disabled={includedCount === 0} style={{
        ...btnStyle,
        background: includedCount > 0 ? 'var(--color-terre)' : 'var(--color-border)',
        color: '#fff',
        padding: '4px 16px',
        borderRadius: 'var(--radius-sm)',
      }}>
        Export
      </button>
    </div>
  )
}

const btnStyle: React.CSSProperties = {
  fontSize: 13,
  padding: '4px 10px',
  color: 'var(--color-text)',
  borderRadius: 'var(--radius-sm)',
}
