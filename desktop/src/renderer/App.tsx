import { useCallback, useEffect, useState } from 'react'
import { AppProvider, useAppState, applyAutoInclude } from './state/AppState'
import WelcomeScreen from './components/WelcomeScreen'
import VideoPlayer from './components/VideoPlayer'
import AnalysisScreen from './components/AnalysisScreen'
import RallyQueue from './components/RallyQueue'
import MatchMap from './components/MatchMap'
import { hasReusableAnalysisReport } from './analysisFlow'
import { LanguageProvider, useCopy, useLanguage, LANGUAGE_LABELS, type Language } from './i18n'

function AppInner() {
  const { state, dispatch } = useAppState()
  const copy = useCopy()
  const { language, setLanguage } = useLanguage()
  const languageSwitch = <LanguageSwitch language={language} onChange={setLanguage} />
  const [seekTarget, setSeekTarget] = useState<number | null>(null)
  const [seekCounter, setSeekCounter] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [autoPlay, setAutoPlay] = useState(false)
  const [resourceError, setResourceError] = useState<string | null>(null)

  useEffect(() => {
    window.api.checkResources().then((res) => {
      if (!res.ok) {
        setResourceError(`${copy.app.missingResources} ${res.missing.join(', ')}`)
      }
    })
  }, [copy.app.missingResources])

  const doSeek = useCallback((t: number) => {
    setAutoPlay(false)
    setSeekTarget(t)
    setSeekCounter((c) => c + 1)
  }, [])

  const doSeekAndPlay = useCallback((t: number) => {
    setAutoPlay(true)
    setSeekTarget(t)
    setSeekCounter((c) => c + 1)
  }, [])

  const startAnalysis = useCallback(async (videoPath: string) => {
    dispatch({ type: 'ANALYSIS_START' })

    const cleanup = window.api.onAnalysisProgress((event) => {
      if (event.type === 'step') {
        dispatch({
          type: 'ANALYSIS_STEP',
          step: { step: event.step!, total: event.total!, label: event.label! },
        })
      } else if (event.type === 'step_done') {
        dispatch({
          type: 'ANALYSIS_STEP',
          step: {
            step: event.step!,
            total: state.currentStep?.total ?? 4,
            label: state.currentStep?.label ?? '',
            elapsed: event.elapsed,
          },
        })
      } else if (event.type === 'progress') {
        dispatch({ type: 'ANALYSIS_SUB_PROGRESS', current: event.current!, total: event.sub_total! })
      } else if (event.type === 'complete') {
        cleanup()
        const reportSource = event.report_path ?? videoPath
        window.api.loadReport(reportSource).then((segments) => {
          if (segments) {
            dispatch({
              type: 'ANALYSIS_DONE',
              segments: applyAutoInclude(segments.map((s) => ({ ...s, included: false }))),
            })
          } else {
            dispatch({ type: 'ANALYSIS_ERROR', message: copy.app.reportMissing })
          }
        })
      } else if (event.type === 'error') {
        cleanup()
        dispatch({ type: 'ANALYSIS_ERROR', message: event.message ?? copy.app.unknownError })
      }
    })

    const result = await window.api.runAnalysis(videoPath)
    if (result.error) {
      cleanup()
      dispatch({ type: 'ANALYSIS_ERROR', message: result.error })
    }
  }, [copy.app.reportMissing, copy.app.unknownError, dispatch, state.currentStep])

  const handleVideoSelected = useCallback(async (path: string) => {
    dispatch({ type: 'SET_VIDEO', path })

    const existing = await window.api.loadReport(path)
    if (hasReusableAnalysisReport(existing)) {
      dispatch({
        type: 'LOAD_SEGMENTS',
        segments: applyAutoInclude(existing.map((s) => ({ ...s, included: false }))),
      })
    } else {
      startAnalysis(path)
    }
  }, [dispatch, startAnalysis])

  const [exportProgress, setExportProgress] = useState<number | null>(null)
  const [exportResult, setExportResult] = useState<{ status: 'complete' | 'error'; message: string; outputPath?: string } | null>(null)

  const handleExport = useCallback(async () => {
    if (!state.videoPath) return
    const activeSegments = state.segments
      .filter((s) => s.included)
      .map((s) => ({
        start: s.startAdjusted ?? s.start,
        end: s.endAdjusted ?? s.end,
      }))
    if (activeSegments.length === 0) return

    const totalDuration = activeSegments.reduce((sum, s) => sum + (s.end - s.start), 0)
    setExportProgress(0)
    setExportResult(null)

    const cleanup = window.api.onExportProgress((event) => {
      setExportProgress(Math.min(event.time / totalDuration, 1))
    })

    const result = await window.api.exportHighlights(state.videoPath, activeSegments)
    cleanup()
    setExportProgress(null)

    if (result.error) {
      setExportResult({ status: 'error', message: `${copy.app.exportFailedPrefix}${result.error}` })
    } else if (!result.cancelled) {
      setExportResult({ status: 'complete', message: copy.app.exportComplete, outputPath: result.outputPath })
    }
  }, [copy.app.exportComplete, copy.app.exportFailedPrefix, state.videoPath, state.segments])

  const handleReturnWelcome = useCallback(() => {
    window.api.cancelAnalysis()
    setSeekTarget(null)
    setSeekCounter(0)
    setCurrentTime(0)
    setAutoPlay(false)
    setExportProgress(null)
    setExportResult(null)
    dispatch({ type: 'CLOSE_VIDEO' })
  }, [dispatch])

  if (resourceError) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <div style={{ textAlign: 'center', maxWidth: 480 }}>
          <h2 style={{ color: 'var(--color-accent)', fontFamily: 'var(--font-display)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>{copy.app.resourceErrorTitle}</h2>
          <p style={{ color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>{resourceError}</p>
        </div>
      </div>
    )
  }

  if (!state.videoPath) {
    return <WelcomeScreen onVideoSelected={handleVideoSelected} languageSwitch={languageSwitch} />
  }

  if (state.analysisStatus === 'running' || state.analysisStatus === 'error') {
    return (
      <AnalysisScreen
        step={state.currentStep}
        errorMessage={state.errorMessage}
        onCancel={() => {
          window.api.cancelAnalysis()
          dispatch({ type: 'ANALYSIS_ERROR', message: copy.app.cancelled })
        }}
        onReturnWelcome={handleReturnWelcome}
        onRetry={() => startAnalysis(state.videoPath!)}
        languageSwitch={languageSwitch}
      />
    )
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--color-bg)' }}>
      <div style={{
        padding: '4px 16px',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        color: 'var(--color-text-secondary)',
        borderBottom: '1px solid #e5d2bd',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        WebkitAppRegion: 'drag',
      } as React.CSSProperties}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 900, letterSpacing: '-0.02em', color: 'var(--color-text)' }}>
          {copy.common.appName} · {copy.app.reviewTitle}
        </span>
        <div style={{ display: 'flex', gap: 8, WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
          {languageSwitch}
          <button onClick={handleReturnWelcome} style={topBtnStyle}>{copy.app.returnWelcome}</button>
          <button onClick={() => startAnalysis(state.videoPath!)} style={topBtnStyle}>{copy.app.rerunAnalysis}</button>
        </div>
      </div>

      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', minHeight: 0 }}>
        <main style={{ display: 'grid', gridTemplateRows: 'minmax(0, 1fr) auto', minWidth: 0, minHeight: 0 }}>
          <section style={{ margin: 16, marginBottom: 16, borderRadius: 9, overflow: 'hidden', background: '#063b2d', minHeight: 0 }}>
            <VideoPlayer
              videoPath={state.videoPath}
              seekTo={seekTarget}
              seekKey={seekCounter}
              autoPlay={autoPlay}
              pauseAt={state.selectedSegmentIndex != null ? (() => {
                const seg = state.segments[state.selectedSegmentIndex!]
                return seg.endAdjusted ?? seg.end
              })() : null}
              onTimeUpdate={(t) => setCurrentTime(t)}
              onDurationChange={(d) => dispatch({ type: 'SET_DURATION', duration: d })}
            />
          </section>

          {state.analysisStatus === 'done' && (
            <MatchMap onSeek={doSeek} />
          )}
        </main>

        {state.analysisStatus === 'done' && (
          <RallyQueue
            onSeek={doSeek}
            onSeekAndPlay={doSeekAndPlay}
            currentTime={currentTime}
            onExport={handleExport}
            onCancelExport={() => window.api.cancelExport()}
            onOpenExportFile={(outputPath) => window.api.openPath(outputPath)}
            exportProgress={exportProgress}
            exportResult={exportResult}
          />
        )}
      </div>
    </div>
  )
}

function LanguageSwitch({ language, onChange }: { language: Language; onChange: (language: Language) => void }) {
  return (
    <div style={{ display: 'inline-flex', gap: 4, WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
      {(['en', 'zh'] as Language[]).map((item) => (
        <button
          key={item}
          onClick={() => onChange(item)}
          aria-label={language === item ? `${LANGUAGE_LABELS[item]} selected` : `Switch to ${LANGUAGE_LABELS[item]}`}
          style={{
            ...topBtnStyle,
            background: language === item ? 'var(--color-green)' : 'var(--color-surface)',
            color: language === item ? '#fff' : 'var(--color-green-dark)',
          }}
        >
          {LANGUAGE_LABELS[item]}
        </button>
      ))}
    </div>
  )
}

const topBtnStyle: React.CSSProperties = {
  fontSize: 11,
  fontFamily: 'var(--font-display)',
  fontWeight: 800,
  letterSpacing: '0.04em',
  color: 'var(--color-green-dark)',
  padding: '3px 9px',
  border: '1px solid #e1cbb5',
  borderRadius: 999,
  background: 'var(--color-surface)',
}

export default function App() {
  return (
    <LanguageProvider>
      <AppProvider>
        <AppInner />
      </AppProvider>
    </LanguageProvider>
  )
}
