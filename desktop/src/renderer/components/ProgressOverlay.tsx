import { useAppState } from '../state/AppState'

export default function ProgressOverlay() {
  const { state, dispatch } = useAppState()

  if (state.analysisStatus !== 'running') return null

  const step = state.currentStep

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(245, 240, 232, 0.92)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 100,
      gap: 16,
    }}>
      <h2 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 20,
        fontWeight: 800,
        color: 'var(--color-accent)',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}>
        Analyzing...
      </h2>

      {step && (
        <>
          <p style={{ fontSize: 15, color: 'var(--color-text)' }}>
            {step.label}
          </p>
          <div style={{
            width: 240,
            height: 4,
            background: 'var(--color-border)',
            borderRadius: 2,
            overflow: 'hidden',
          }}>
            <div style={{
              width: `${((step.step) / step.total) * 100}%`,
              height: '100%',
              background: 'var(--color-accent)',
              transition: 'width 0.3s ease',
            }} />
          </div>
          {step.subCurrent != null && step.subTotal != null && (
            <div style={{
              width: 240,
              height: 2,
              background: 'var(--color-border)',
              borderRadius: 1,
              overflow: 'hidden',
            }}>
              <div style={{
                width: `${(step.subCurrent / step.subTotal) * 100}%`,
                height: '100%',
                background: 'var(--color-accent)',
                opacity: 0.5,
                transition: 'width 0.15s ease',
              }} />
            </div>
          )}
          <p style={{
            fontSize: 12,
            color: 'var(--color-text-secondary)',
            fontFamily: 'var(--font-mono)',
          }}>
            Step {Math.ceil(step.step)} / {step.total}
            {step.elapsed != null && ` — ${step.elapsed.toFixed(1)}s`}
            {step.subCurrent != null && step.subTotal != null && (
              <> — Segment {step.subCurrent} / {step.subTotal}</>
            )}
          </p>
        </>
      )}

      <button
        onClick={() => {
          window.api.cancelAnalysis()
          dispatch({ type: 'ANALYSIS_ERROR', message: 'Cancelled' })
        }}
        style={{
          marginTop: 16,
          padding: '8px 24px',
          fontSize: 12,
          fontFamily: 'var(--font-display)',
          fontWeight: 700,
          letterSpacing: '0.06em',
          textTransform: 'uppercase' as const,
          color: 'var(--color-text-secondary)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
        }}
      >
        Cancel
      </button>
    </div>
  )
}
