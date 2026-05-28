import type { ProgressStep } from '../state/AppState'
import { useCopy } from '../i18n'
import { getAnalysisStageNumber, getAnalysisStageView } from '../viewModels/flowCopy'

interface Props {
  step: ProgressStep | null
  errorMessage: string | null
  onCancel: () => void
  onReturnWelcome: () => void
  onRetry: () => void
}

export default function AnalysisProgressPanel({ step, errorMessage, onCancel, onReturnWelcome, onRetry }: Props) {
  const copy = useCopy()
  const view = getAnalysisStageView(step, copy)
  const activeStage = getAnalysisStageNumber(step)
  const stages = copy.analysisPanel.stages
  const subProgressRatio = view.subProgress
    ? Math.min(Math.max(view.subProgress.current / Math.max(view.subProgress.total, 1), 0), 1)
    : 0

  if (errorMessage) {
    return (
      <div style={{ padding: 'clamp(20px, 3vw, 42px) clamp(8px, 1.4vw, 16px)' }}>
        <div style={{ color: 'var(--color-accent)', fontFamily: 'var(--font-display)', fontWeight: 900, letterSpacing: '0.16em', textTransform: 'uppercase', marginBottom: 16 }}>{copy.analysisPanel.failedEyebrow}</div>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(26px, 4vw, 48px)', lineHeight: 0.98, letterSpacing: '-0.045em', margin: '0 0 16px', color: 'var(--color-text)' }}>{copy.analysisPanel.failedTitle}</h1>
        <p style={{ color: 'var(--color-text-secondary)', lineHeight: 1.7, marginBottom: 24 }}>{errorMessage}</p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button onClick={onRetry} style={{ padding: '10px 18px', borderRadius: 999, background: 'var(--color-accent)', color: '#fff', border: 'none', fontWeight: 800 }}>{copy.analysisPanel.retry}</button>
          <button onClick={onReturnWelcome} style={{ padding: '10px 18px', borderRadius: 999, background: 'transparent', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)', fontWeight: 800 }}>{copy.analysisPanel.returnWelcome}</button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: 'clamp(20px, 3vw, 42px) clamp(8px, 1.4vw, 16px)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--color-accent)', fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 900, letterSpacing: '0.16em', textTransform: 'uppercase', marginBottom: 16 }}>
        <span style={{ width: 30, height: 2, background: 'var(--color-accent)' }} />
        {copy.analysisPanel.autoStart}
      </div>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(28px, 4.4vw, 56px)', lineHeight: 0.96, letterSpacing: '-0.045em', margin: '0 0 16px', color: 'var(--color-text)' }}>
        {copy.analysisPanel.headline.split('\n').map((line, index) => (
          <span key={line}>{index > 0 && <br />}{line}</span>
        ))}
      </h1>
      <p style={{ color: 'var(--color-text-secondary)', lineHeight: 1.7, margin: '0 0 26px', maxWidth: 560, fontSize: 'clamp(12px, 1.05vw, 14px)' }}>{copy.analysisPanel.intro}</p>
      <div style={{ border: '1px solid var(--color-border)', borderRadius: 12, padding: 22, background: 'rgba(250,247,242,0.72)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: 12, marginBottom: 12, color: 'var(--color-text-secondary)' }}>
          <span>{view.stageLabel}{view.subProgress ? ` · ${view.subProgress.label}` : ''}</span>
          <strong style={{ color: 'var(--color-text)' }}>{Math.round(view.progress * 100)}%</strong>
        </div>
        <div style={{ height: 9, background: 'var(--color-border)', borderRadius: 999, overflow: 'hidden', marginBottom: 18 }}>
          <div style={{ width: `${view.progress * 100}%`, height: '100%', background: 'linear-gradient(90deg, var(--color-green), var(--color-accent))', transition: 'width 0.3s ease' }} />
        </div>
        {stages.map((stage, index) => {
          const stageNumber = index + 1
          const done = activeStage > stageNumber
          const current = activeStage === stageNumber
          const color = done ? 'var(--color-green-light)' : current ? 'var(--color-accent)' : 'var(--color-olive)'
          const status = done ? copy.analysisPanel.statusDone : current ? copy.analysisPanel.statusCurrent : copy.analysisPanel.statusNext
          return (
            <div key={stage.title} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 14, alignItems: 'start', padding: '14px 0', borderTop: '1px solid var(--color-border)' }}>
              <strong style={{ color }}>{done ? '✓' : stageNumber}</strong>
              <span>
                <strong>{stage.title}</strong><br />
                <small style={{ color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>{stage.detail}</small>
                {current && activeStage === 3 && view.subProgress && (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 7, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-secondary)' }}>
                      <span>{copy.analysisPanel.subProgressTitle}</span>
                      <strong style={{ color: 'var(--color-text)' }}>{view.subProgress.label}</strong>
                    </div>
                    <div style={{ height: 7, borderRadius: 999, background: 'var(--color-border)', overflow: 'hidden' }}>
                      <div style={{ width: `${subProgressRatio * 100}%`, height: '100%', background: 'var(--color-accent)', transition: 'width 0.3s ease' }} />
                    </div>
                  </div>
                )}
              </span>
              <strong style={{ color, fontSize: 11 }}>{status}</strong>
            </div>
          )
        })}
      </div>
      <button onClick={onCancel} style={{ marginTop: 18, padding: '10px 20px', borderRadius: 999, border: '1px solid var(--color-border)', background: 'transparent', color: 'var(--color-text-secondary)', fontWeight: 800 }}>{copy.analysisPanel.cancel}</button>
    </div>
  )
}
