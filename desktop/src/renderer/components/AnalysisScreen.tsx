import type { CSSProperties } from 'react'
import type { ProgressStep } from '../state/AppState'
import AnalysisCourtVisual from './AnalysisCourtVisual'
import AnalysisProgressPanel from './AnalysisProgressPanel'

interface Props {
  step: ProgressStep | null
  errorMessage: string | null
  onCancel: () => void
  onReturnWelcome: () => void
  onRetry: () => void
}

export default function AnalysisScreen({ step, errorMessage, onCancel, onReturnWelcome, onRetry }: Props) {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'grid',
      gridTemplateRows: '34px 1fr',
      background: 'radial-gradient(900px 460px at 8% -10%, rgba(204,78,14,0.12), transparent 64%), radial-gradient(720px 440px at 100% 0, rgba(0,80,60,0.13), transparent 60%), var(--color-bg)',
    }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: '82px 1fr 82px',
        alignItems: 'center',
        padding: '0 14px',
        borderBottom: '1px solid var(--color-border)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--color-text-secondary)',
        WebkitAppRegion: 'drag',
      } as CSSProperties}>
        <div style={{ display: 'flex', gap: 8 }}>
          <span style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--color-accent)' }} />
          <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#d89423' }} />
          <span style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--color-green-light)' }} />
        </div>
        <div style={{ textAlign: 'center' }}>Breakpoint · {errorMessage ? '分析遇到问题' : '正在分析视频'}</div>
        <div style={{ textAlign: 'right' }}>v0.1.6</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1.12fr 0.95fr', gap: 28, padding: 28, minHeight: 0 }}>
        <AnalysisCourtVisual />
        <AnalysisProgressPanel
          step={step}
          errorMessage={errorMessage}
          onCancel={onCancel}
          onReturnWelcome={onReturnWelcome}
          onRetry={onRetry}
        />
      </div>
    </div>
  )
}
