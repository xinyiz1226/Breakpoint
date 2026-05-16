export {}

interface ProgressEvent {
  type: 'step' | 'step_done' | 'complete' | 'error' | 'progress' | 'stderr'
  step?: number
  total?: number
  label?: string
  elapsed?: number
  detail?: Record<string, number>
  report_path?: string
  segment_count?: number
  message?: string
  current?: number
  sub_total?: number
}

interface Segment {
  index: number
  start: number
  end: number
  score: number
  features: Record<string, number>
}

declare global {
  interface Window {
    api: {
      openFileDialog: () => Promise<string | null>
      getRecentProjects: () => Promise<string[]>
      checkResources: () => Promise<{ ok: boolean; missing: string[] }>
      runAnalysis: (videoPath: string) => Promise<{ error?: string }>
      cancelAnalysis: () => Promise<void>
      cancelExport: () => Promise<void>
      loadReport: (videoPath: string) => Promise<Segment[] | null>
      exportHighlights: (videoPath: string, segments: { start: number; end: number }[]) =>
        Promise<{ error?: string; cancelled?: boolean; outputPath?: string }>
      onAnalysisProgress: (callback: (event: ProgressEvent) => void) => () => void
      onExportProgress: (callback: (event: { time: number }) => void) => () => void
    }
  }
}
