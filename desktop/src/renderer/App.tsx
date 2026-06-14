import { useCallback, useEffect, useRef, useState } from 'react'
import { AppProvider, useAppState } from './state/AppState'
import WelcomeScreen from './components/WelcomeScreen'
import VideoPlayer from './components/VideoPlayer'
import AnalysisScreen from './components/AnalysisScreen'
import RallyQueue from './components/RallyQueue'
import MatchMap from './components/MatchMap'
import BatchVideoList from './components/BatchVideoList'
import { hasReusableAnalysisReport } from './analysisFlow'
import { createRalliesForVideo, createVideoRecords, getExportClips } from './batchFlow'
import type { VideoRecord } from './state/AppState'
import { LanguageProvider, useCopy, useLanguage, LANGUAGE_LABELS, type Language } from './i18n'
import { getExportActionCopy } from './viewModels/flowCopy'

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
  const [exportProgress, setExportProgress] = useState<number | null>(null)
  const [exportResult, setExportResult] = useState<{ status: 'complete' | 'error'; message: string; outputPath?: string } | null>(null)
  const batchCancelledRef = useRef(false)
  const batchRunIdRef = useRef(0)

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

  const isCurrentBatchRun = useCallback((runId: number) => (
    batchRunIdRef.current === runId && !batchCancelledRef.current
  ), [])

  const analyzeVideo = useCallback(async (video: VideoRecord, runId: number) => {
    if (!isCurrentBatchRun(runId)) return false
    dispatch({ type: 'VIDEO_ANALYSIS_START', videoId: video.id })

    const existing = await window.api.loadReport(video.path)
    if (!isCurrentBatchRun(runId)) return false
    if (hasReusableAnalysisReport(existing)) {
      const rallies = createRalliesForVideo(video, existing)
      dispatch({ type: 'VIDEO_ANALYSIS_DONE', videoId: video.id, rallies })
      return true
    }

    const cleanup = window.api.onAnalysisProgress((event) => {
      if (!isCurrentBatchRun(runId)) {
        cleanup()
        return
      }
      if (event.type === 'step') {
        dispatch({
          type: 'VIDEO_ANALYSIS_STEP',
          videoId: video.id,
          step: { step: event.step!, total: event.total!, label: event.label! },
        })
      } else if (event.type === 'step_done') {
        dispatch({
          type: 'VIDEO_ANALYSIS_STEP',
          videoId: video.id,
          step: {
            step: event.step!,
            total: event.total ?? 4,
            label: event.label ?? '',
            elapsed: event.elapsed,
          },
        })
      } else if (event.type === 'progress') {
        dispatch({ type: 'VIDEO_ANALYSIS_SUB_PROGRESS', videoId: video.id, current: event.current!, total: event.sub_total! })
      } else if (event.type === 'complete') {
        cleanup()
      } else if (event.type === 'error') {
        cleanup()
        dispatch({ type: 'VIDEO_ANALYSIS_ERROR', videoId: video.id, message: event.message ?? copy.app.unknownError })
      }
    })

    const result = await window.api.runAnalysis(video.path)
    cleanup()
    if (!isCurrentBatchRun(runId)) return false
    if (result.error) {
      dispatch({ type: 'VIDEO_ANALYSIS_ERROR', videoId: video.id, message: result.error })
      return false
    }

    const report = await window.api.loadReport(video.path)
    if (!isCurrentBatchRun(runId)) return false
    if (!hasReusableAnalysisReport(report)) {
      dispatch({ type: 'VIDEO_ANALYSIS_ERROR', videoId: video.id, message: copy.app.reportMissing })
      return false
    }

    const rallies = createRalliesForVideo(video, report)
    dispatch({ type: 'VIDEO_ANALYSIS_DONE', videoId: video.id, rallies })
    return true
  }, [copy.app.reportMissing, copy.app.unknownError, dispatch, isCurrentBatchRun])

  const startBatchAnalysis = useCallback(async (videosToAnalyze: VideoRecord[]) => {
    batchRunIdRef.current += 1
    const runId = batchRunIdRef.current
    batchCancelledRef.current = false
    dispatch({ type: 'BATCH_ANALYSIS_START' })
    for (const video of videosToAnalyze) {
      if (batchCancelledRef.current || batchRunIdRef.current !== runId) break
      await analyzeVideo(video, runId)
      if (batchCancelledRef.current || batchRunIdRef.current !== runId) break
    }
    if (!batchCancelledRef.current && batchRunIdRef.current === runId) {
      dispatch({ type: 'BATCH_ANALYSIS_DONE' })
    }
  }, [analyzeVideo, dispatch])

  const handleVideosSelected = useCallback(async (paths: string[]) => {
    batchRunIdRef.current += 1
    batchCancelledRef.current = true
    await window.api.cancelAnalysis()
    const videos = createVideoRecords(paths)
    dispatch({ type: 'CREATE_BATCH', videos })
    setExportResult(null)
    startBatchAnalysis(videos)
  }, [dispatch, startBatchAnalysis])

  const handleRetryVideo = useCallback(async (videoId: string) => {
    const video = state.videos.find((item) => item.id === videoId)
    if (!video) {
      setExportResult({ status: 'error', message: `${copy.app.exportFailedPrefix}${copy.app.unknownError}` })
      return
    }
    await window.api.cancelAnalysis()
    dispatch({ type: 'VIDEO_ANALYSIS_RETRY', videoId })
    startBatchAnalysis([video])
  }, [copy.app.exportFailedPrefix, copy.app.unknownError, dispatch, startBatchAnalysis, state.videos])

  const handleExport = useCallback(async () => {
    const clips = getExportClips(state.rallies, state.videos)
    if (clips.length === 0) {
      setExportResult({ status: 'error', message: getExportActionCopy(0, false, copy) })
      return
    }

    const totalDuration = clips.reduce((sum, clip) => sum + (clip.end - clip.start), 0)
    setExportProgress(0)
    setExportResult(null)

    const cleanup = window.api.onExportProgress((event) => {
      setExportProgress(Math.min(event.time / totalDuration, 1))
    })

    const result = await window.api.exportHighlights(clips)
    cleanup()
    setExportProgress(null)

    if (result.error) {
      setExportResult({ status: 'error', message: `${copy.app.exportFailedPrefix}${result.error}` })
    } else if (!result.cancelled) {
      setExportResult({ status: 'complete', message: copy.app.exportComplete, outputPath: result.outputPath })
    }
  }, [copy, state.rallies, state.videos])

  const handleReturnWelcome = useCallback(() => {
    batchRunIdRef.current += 1
    batchCancelledRef.current = true
    window.api.cancelAnalysis()
    setSeekTarget(null)
    setSeekCounter(0)
    setCurrentTime(0)
    setAutoPlay(false)
    setExportProgress(null)
    setExportResult(null)
    dispatch({ type: 'CLOSE_VIDEO' })
  }, [dispatch])

  const activeVideo = state.videos.find((video) => video.id === state.activeVideoId) ?? null
  const selectedRally = state.selectedRallyId ? state.rallies.find((rally) => rally.id === state.selectedRallyId) : null
  const runningVideoIndex = state.videos.findIndex((video) => video.status === 'running')
  const runningVideo = runningVideoIndex >= 0 ? state.videos[runningVideoIndex] : null
  const batchLabel = runningVideoIndex >= 0 ? copy.batch.videoProgress(runningVideoIndex + 1, state.videos.length) : undefined

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

  if (state.videos.length === 0) {
    return <WelcomeScreen onVideosSelected={handleVideosSelected} languageSwitch={languageSwitch} />
  }

  if (state.analysisStatus === 'running' || state.analysisStatus === 'error') {
    return (
      <AnalysisScreen
        step={runningVideo?.currentStep ?? state.currentStep}
        errorMessage={state.errorMessage ?? runningVideo?.errorMessage ?? null}
        onCancel={() => {
          batchRunIdRef.current += 1
          batchCancelledRef.current = true
          window.api.cancelAnalysis()
          if (runningVideo) {
            dispatch({ type: 'VIDEO_ANALYSIS_ERROR', videoId: runningVideo.id, message: copy.app.cancelled })
          }
          dispatch({ type: 'BATCH_ANALYSIS_ERROR', message: copy.app.cancelled })
        }}
        onReturnWelcome={handleReturnWelcome}
        onRetry={() => {
          if (runningVideo) handleRetryVideo(runningVideo.id)
        }}
        batchLabel={batchLabel}
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
          {activeVideo && <button onClick={() => handleRetryVideo(activeVideo.id)} style={topBtnStyle}>{copy.app.rerunAnalysis}</button>}
        </div>
      </div>

      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr) auto', minHeight: 0 }}>
        <BatchVideoList
          videos={state.videos}
          activeVideoId={state.activeVideoId}
          onSelect={(videoId) => dispatch({ type: 'SET_ACTIVE_VIDEO', id: videoId })}
          onRetry={handleRetryVideo}
        />

        <main style={{ display: 'grid', gridTemplateRows: 'minmax(0, 1fr) auto', minWidth: 0, minHeight: 0 }}>
          <section style={{ margin: 16, marginBottom: 16, borderRadius: 9, overflow: 'hidden', background: '#063b2d', minHeight: 0 }}>
            {activeVideo && (
              <VideoPlayer
                videoPath={activeVideo.path}
                seekTo={seekTarget}
                seekKey={seekCounter}
                autoPlay={autoPlay}
                pauseAt={selectedRally ? selectedRally.endAdjusted ?? selectedRally.end : null}
                onTimeUpdate={(t) => setCurrentTime(t)}
                onDurationChange={(duration) => dispatch({ type: 'SET_VIDEO_DURATION', videoId: activeVideo.id, duration })}
              />
            )}
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
