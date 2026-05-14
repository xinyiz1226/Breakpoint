import { useAppState } from '../state/AppState'

export default function ProgressOverlay() {
  const { state, dispatch } = useAppState()

  if (state.analysisStatus !== 'running') return null

  const step = state.currentStep

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(253, 251, 248, 0.92)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 100,
      gap: 16,
    }}>
      <h2 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 24,
        color: 'var(--color-terre)',
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
              background: 'var(--color-terre)',
              transition: 'width 0.3s ease',
            }} />
          </div>
          <p style={{
            fontSize: 12,
            color: 'var(--color-text-secondary)',
            fontFamily: 'var(--font-mono)',
          }}>
            Step {Math.ceil(step.step)} / {step.total}
            {step.elapsed != null && ` — ${step.elapsed.toFixed(1)}s`}
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
          fontSize: 13,
          color: 'var(--color-text-secondary)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-md)',
        }}
      >
        Cancel
      </button>
    </div>
  )
}
