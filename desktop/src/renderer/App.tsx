import { useCallback, useEffect, useState } from 'react'
import { AppProvider, useAppState, applyAutoInclude } from './state/AppState'
import WelcomeScreen from './components/WelcomeScreen'
import VideoPlayer from './components/VideoPlayer'
import AnalysisScreen from './components/AnalysisScreen'
import Toolbar from './components/Toolbar'
import Timeline from './components/Timeline'
import SegmentList from './components/SegmentList'
import { hasReusableAnalysisReport } from './analysisFlow'

function AppInner() {
  const { state, dispatch } = useAppState()
  const [seekTarget, setSeekTarget] = useState<number | null>(null)
  const [seekCounter, setSeekCounter] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [autoPlay, setAutoPlay] = useState(false)
  const [resourceError, setResourceError] = useState<string | null>(null)

  useEffect(() => {
    window.api.checkResources().then((res) => {
      if (!res.ok) {
        setResourceError(`Installer missing bundled resources: ${res.missing.join(', ')}`)
      }
    })
  }, [])

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
            dispatch({ type: 'ANALYSIS_ERROR', message: 'Report file not found' })
          }
        })
      } else if (event.type === 'error') {
        cleanup()
        dispatch({ type: 'ANALYSIS_ERROR', message: event.message ?? 'Unknown error' })
      }
    })

    const result = await window.api.runAnalysis(videoPath)
    if (result.error) {
      cleanup()
      dispatch({ type: 'ANALYSIS_ERROR', message: result.error })
    }
  }, [dispatch, state.currentStep])

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
      setExportResult({ status: 'error', message: `导出失败：${result.error}` })
    } else if (!result.cancelled) {
      setExportResult({ status: 'complete', message: '精彩合集已导出', outputPath: result.outputPath })
    }
  }, [state.videoPath, state.segments])

  const handleReturnWelcome = useCallback(() => {
    setExportProgress(null)
    setExportResult(null)
    dispatch({ type: 'CLOSE_VIDEO' })
  }, [dispatch])

  if (resourceError) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <div style={{ textAlign: 'center', maxWidth: 480 }}>
          <h2 style={{ color: 'var(--color-accent)', fontFamily: 'var(--font-display)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>Resource Error</h2>
          <p style={{ color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>{resourceError}</p>
        </div>
      </div>
    )
  }

  if (!state.videoPath) {
    return <WelcomeScreen onVideoSelected={handleVideoSelected} />
  }

  if (state.analysisStatus === 'running' || state.analysisStatus === 'error') {
    return (
      <AnalysisScreen
        step={state.currentStep}
        errorMessage={state.errorMessage}
        onCancel={() => {
          window.api.cancelAnalysis()
          dispatch({ type: 'ANALYSIS_ERROR', message: 'Cancelled' })
        }}
        onReturnWelcome={handleReturnWelcome}
        onRetry={() => startAnalysis(state.videoPath!)}
      />
    )
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div style={{
        padding: '8px 16px',
        fontFamily: 'var(--font-mono)',
        fontSize: 13,
        color: 'var(--color-text-secondary)',
        borderBottom: '1px solid var(--color-border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        WebkitAppRegion: 'drag',
      } as React.CSSProperties}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: 8, color: 'var(--color-text)' }}>
          <span style={{ width: 8, height: 8, background: 'var(--color-accent)', borderRadius: '50%', display: 'inline-block' }} />
          BREAKPOINT
        </span>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 8, WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
          <button onClick={handleReturnWelcome} style={{ fontSize: 11, fontFamily: 'var(--font-display)', fontWeight: 700, letterSpacing: '0.06em', color: 'var(--color-text-secondary)', padding: '2px 8px' }}>
            返回欢迎页
          </button>
          <button onClick={() => startAnalysis(state.videoPath!)} style={{ fontSize: 11, fontFamily: 'var(--font-display)', fontWeight: 700, letterSpacing: '0.06em', color: 'var(--color-text-secondary)', padding: '2px 8px' }}>
            重新处理
          </button>
        </div>
      </div>

      {state.analysisStatus === 'done' && (
        <Toolbar
          onExport={handleExport}
          onCancelExport={() => window.api.cancelExport()}
          onOpenExportFile={(outputPath) => window.api.openPath(outputPath)}
          filename={state.videoPath.split(/[\\/]/).pop() ?? ''}
          exportProgress={exportProgress}
          exportResult={exportResult}
        />
      )}

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div style={{ flex: 2, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
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
        </div>

        {state.analysisStatus === 'done' && (
          <div style={{ flex: 1, minWidth: 240, maxWidth: 400, borderLeft: '1px solid var(--color-border)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <SegmentList onSeek={doSeek} onSeekAndPlay={doSeekAndPlay} currentTime={currentTime} />
          </div>
        )}
      </div>

      {state.analysisStatus === 'done' && (
        <Timeline onSeek={doSeek} />
      )}

    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <AppInner />
    </AppProvider>
  )
}
