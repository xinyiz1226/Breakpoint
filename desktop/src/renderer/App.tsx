import { useCallback, useEffect, useState } from 'react'
import { AppProvider, useAppState, applyAutoInclude } from './state/AppState'
import WelcomeScreen from './components/WelcomeScreen'
import VideoPlayer from './components/VideoPlayer'
import ProgressOverlay from './components/ProgressOverlay'
import Toolbar from './components/Toolbar'
import Timeline from './components/Timeline'
import SegmentList from './components/SegmentList'

function AppInner() {
  const { state, dispatch } = useAppState()
  const [seekTarget, setSeekTarget] = useState<number | null>(null)
  const [seekCounter, setSeekCounter] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [autoPlay, setAutoPlay] = useState(false)

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
      } else if (event.type === 'complete') {
        cleanup()
        window.api.loadReport(videoPath).then((segments) => {
          if (segments) {
            dispatch({
              type: 'ANALYSIS_DONE',
              segments: applyAutoInclude(segments.map((s) => ({ ...s, included: false }))),
            })
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
    if (existing) {
      dispatch({
        type: 'LOAD_SEGMENTS',
        segments: applyAutoInclude(existing.map((s) => ({ ...s, included: false }))),
      })
    } else {
      startAnalysis(path)
    }
  }, [dispatch, startAnalysis])

  const handleOpenNewVideo = useCallback(async () => {
    const path = await window.api.openFileDialog()
    if (path) handleVideoSelected(path)
  }, [handleVideoSelected])

  const [exportProgress, setExportProgress] = useState<number | null>(null)
  const [exportMessage, setExportMessage] = useState<string | null>(null)

  useEffect(() => {
    if (exportMessage) {
      const timer = setTimeout(() => setExportMessage(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [exportMessage])

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
    setExportMessage(null)

    const cleanup = window.api.onExportProgress((event) => {
      setExportProgress(Math.min(event.time / totalDuration, 1))
    })

    const result = await window.api.exportHighlights(state.videoPath, activeSegments)
    cleanup()
    setExportProgress(null)

    if (result.error) {
      setExportMessage(`Export failed: ${result.error}`)
    } else if (!result.cancelled) {
      setExportMessage('Export complete')
    }
  }, [state.videoPath, state.segments])

  if (!state.videoPath) {
    return <WelcomeScreen onVideoSelected={handleVideoSelected} />
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
        WebkitAppRegion: 'drag' as any,
      }}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 16, color: 'var(--color-terre)', fontWeight: 600 }}>
          Breakpoint
        </span>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 8, WebkitAppRegion: 'no-drag' as any }}>
          <button onClick={handleOpenNewVideo} style={{ fontSize: 12, color: 'var(--color-text-secondary)', padding: '2px 8px' }}>
            Open Video
          </button>
          <button onClick={() => startAnalysis(state.videoPath!)} style={{ fontSize: 12, color: 'var(--color-text-secondary)', padding: '2px 8px' }}>
            Re-analyze
          </button>
        </div>
      </div>

      {state.analysisStatus === 'done' && (
        <Toolbar
          onExport={handleExport}
          onCancelExport={() => window.api.cancelExport()}
          filename={state.videoPath.split(/[\\/]/).pop() ?? ''}
          exportProgress={exportProgress}
          exportMessage={exportMessage}
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

      <ProgressOverlay />
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
