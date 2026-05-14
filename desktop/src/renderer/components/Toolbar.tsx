import { useAppState } from '../state/AppState'

interface Props {
  onExport: () => void
  onCancelExport: () => void
  filename: string
  exportProgress: number | null
  exportMessage: string | null
}

export default function Toolbar({ onExport, onCancelExport, filename, exportProgress, exportMessage }: Props) {
  const { state } = useAppState()
  const includedCount = state.segments.filter((s) => s.included).length
  const totalCount = state.segments.length
  const exporting = exportProgress !== null

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '6px 16px',
      borderBottom: '1px solid var(--color-border)',
      background: 'var(--color-cream)',
      fontSize: 13,
      position: 'relative',
    }}>
      {exporting && (
        <div style={{
          position: 'absolute',
          left: 0,
          bottom: 0,
          height: 3,
          width: `${(exportProgress ?? 0) * 100}%`,
          background: 'var(--color-terre)',
          transition: 'width 0.3s ease-out',
        }} />
      )}

      <div style={{ flex: 1 }} />

      <span style={{
        fontSize: 12,
        color: 'var(--color-text-secondary)',
        fontFamily: 'var(--font-mono)',
      }}>
        {exporting ? `Exporting... ${Math.round((exportProgress ?? 0) * 100)}%` : filename}
      </span>

      <div style={{ flex: 1 }} />

      {exportMessage && (
        <span style={{
          fontSize: 12,
          color: exportMessage.includes('failed') ? 'var(--color-danger)' : 'var(--color-green)',
          fontWeight: 500,
        }}>
          {exportMessage}
        </span>
      )}

      <span style={{
        fontSize: 12,
        color: 'var(--color-text-secondary)',
        fontFamily: 'var(--font-mono)',
      }}>
        {includedCount}/{totalCount} selected
      </span>

      {exporting ? (
        <button onClick={onCancelExport} style={{
          ...btnStyle,
          background: 'var(--color-danger, #c44)',
          color: '#fff',
          padding: '4px 16px',
          borderRadius: 'var(--radius-sm)',
        }}>
          Cancel
        </button>
      ) : (
        <button onClick={onExport} disabled={includedCount === 0} style={{
          ...btnStyle,
          background: includedCount > 0 ? 'var(--color-terre)' : 'var(--color-border)',
          color: '#fff',
          padding: '4px 16px',
          borderRadius: 'var(--radius-sm)',
        }}>
          Export
        </button>
      )}
    </div>
  )
}

const btnStyle: React.CSSProperties = {
  fontSize: 13,
  padding: '4px 10px',
  color: 'var(--color-text)',
  borderRadius: 'var(--radius-sm)',
}
