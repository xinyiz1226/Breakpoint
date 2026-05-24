import { useAppState } from '../state/AppState'
import { getExportActionCopy, getReviewTaskSummary } from '../viewModels/flowCopy'

interface Props {
  onExport: () => void
  onCancelExport: () => void
  onOpenExportFile: (outputPath: string) => void
  filename: string
  exportProgress: number | null
  exportResult: { status: 'complete' | 'error'; message: string; outputPath?: string } | null
}

export default function Toolbar({ onExport, onCancelExport, onOpenExportFile, filename, exportProgress, exportResult }: Props) {
  const { state } = useAppState()
  const summary = getReviewTaskSummary(state.segments)
  const exporting = exportProgress !== null
  const actionCopy = getExportActionCopy(summary.selectedCount, exporting)

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      padding: '10px 16px',
      borderBottom: '1px solid var(--color-border)',
      background: 'var(--color-bg)',
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
          background: 'var(--color-accent)',
          transition: 'width 0.3s ease-out',
        }} />
      )}

      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{
          fontFamily: 'var(--font-display)',
          fontSize: 15,
          fontWeight: 900,
          letterSpacing: '-0.02em',
          color: 'var(--color-green-dark)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {summary.instruction}
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--color-text-secondary)',
          marginTop: 3,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {filename} · 已选择 {summary.selectedCount}/{summary.totalCount} 个回合 · 合集约 {summary.selectedDurationLabel}
        </div>
      </div>

      <span style={{
        fontSize: 12,
        color: 'var(--color-text-secondary)',
        fontFamily: 'var(--font-mono)',
      }}>
        {exporting ? `${Math.round((exportProgress ?? 0) * 100)}%` : ''}
      </span>

      {exportResult && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          color: exportResult.status === 'error' ? 'var(--color-danger)' : 'var(--color-green-light)',
          fontWeight: 700,
          fontSize: 12,
          whiteSpace: 'nowrap',
        }}>
          <span>{exportResult.message}</span>
          {exportResult.outputPath && (
            <button onClick={() => onOpenExportFile(exportResult.outputPath!)} style={secondaryBtnStyle}>
              打开导出文件
            </button>
          )}
        </div>
      )}

      {exporting ? (
        <button onClick={onCancelExport} style={{
          ...btnStyle,
          background: 'var(--color-danger, #c44)',
          color: '#fff',
          padding: '4px 16px',
          borderRadius: 'var(--radius-sm)',
        }}>
          取消导出
        </button>
      ) : (
        <button onClick={onExport} disabled={summary.selectedCount === 0} style={{
          ...btnStyle,
          background: summary.selectedCount > 0 ? 'var(--color-accent)' : 'var(--color-border)',
          color: '#fff',
          padding: '9px 18px',
          borderRadius: 999,
          minWidth: 148,
        }}>
          {actionCopy}
        </button>
      )}
    </div>
  )
}

const btnStyle: React.CSSProperties = {
  fontFamily: 'var(--font-display)',
  fontSize: 12,
  fontWeight: 700,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  padding: '4px 10px',
  color: 'var(--color-text)',
  borderRadius: 'var(--radius-sm)',
}

const secondaryBtnStyle: React.CSSProperties = {
  fontFamily: 'var(--font-display)',
  fontSize: 11,
  fontWeight: 800,
  letterSpacing: '0.04em',
  color: 'var(--color-green-dark)',
  border: '1px solid var(--color-border)',
  borderRadius: 999,
  background: 'var(--color-surface)',
  padding: '6px 12px',
}
