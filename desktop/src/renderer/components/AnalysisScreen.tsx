import type { CSSProperties, ReactNode } from 'react'
import type { ProgressStep } from '../state/AppState'
import { useCopy } from '../i18n'
import AnalysisCourtVisual from './AnalysisCourtVisual'
import AnalysisProgressPanel from './AnalysisProgressPanel'

interface Props {
  step: ProgressStep | null
  errorMessage: string | null
  onCancel: () => void
  onReturnWelcome: () => void
  onRetry: () => void
  batchLabel?: string
  languageSwitch: ReactNode
}

export default function AnalysisScreen({ step, errorMessage, onCancel, onReturnWelcome, onRetry, batchLabel, languageSwitch }: Props) {
  const copy = useCopy()

  return (
    <div style={{
      height: '100vh',
      overflow: 'hidden',
      display: 'grid',
      gridTemplateRows: '34px minmax(0, 1fr)',
      background: 'radial-gradient(900px 460px at 8% -10%, rgba(204,78,14,0.12), transparent 64%), radial-gradient(720px 440px at 100% 0, rgba(0,80,60,0.13), transparent 60%), var(--color-bg)',
    }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr auto',
        alignItems: 'center',
        gap: 12,
        padding: '0 14px',
        borderBottom: '1px solid var(--color-border)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--color-text-secondary)',
        WebkitAppRegion: 'drag',
      } as CSSProperties}>
        <div>{copy.common.appName} · {errorMessage ? copy.analysisScreen.problemTitle : copy.analysisScreen.runningTitle}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, WebkitAppRegion: 'no-drag' } as CSSProperties}>
          {languageSwitch}
          <span>v0.1.6</span>
        </div>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1.12fr) minmax(0, 0.95fr)',
        gap: 'clamp(12px, 2vw, 28px)',
        padding: 'clamp(12px, 2vw, 28px)',
        minHeight: 0,
        overflow: 'hidden',
      }}>
        <div style={{ minWidth: 0, minHeight: 0 }}>
          <AnalysisCourtVisual />
        </div>
        <div style={{ minWidth: 0, minHeight: 0, overflowY: 'auto' }}>
          <AnalysisProgressPanel
            step={step}
            errorMessage={errorMessage}
            onCancel={onCancel}
            onReturnWelcome={onReturnWelcome}
            onRetry={onRetry}
            batchLabel={batchLabel}
          />
        </div>
      </div>
    </div>
  )
}
