import { contextBridge, ipcRenderer } from 'electron'

export interface ProgressEvent {
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

contextBridge.exposeInMainWorld('api', {
  openFileDialog: () => ipcRenderer.invoke('open-file-dialog'),
  getRecentProjects: () => ipcRenderer.invoke('get-recent-projects'),
  getAppVersion: () => ipcRenderer.invoke('get-app-version') as Promise<string>,
  checkResources: () => ipcRenderer.invoke('check-resources') as Promise<{ ok: boolean; missing: string[] }>,
  openPath: (targetPath: string) => ipcRenderer.invoke('open-path', targetPath) as Promise<string>,
  runAnalysis: (videoPath: string) => ipcRenderer.invoke('run-analysis', videoPath),
  cancelAnalysis: () => ipcRenderer.invoke('cancel-analysis'),
  cancelExport: () => ipcRenderer.invoke('cancel-export'),
  loadReport: (videoPath: string) => ipcRenderer.invoke('load-report', videoPath),
  exportHighlights: (videoPath: string, segments: { start: number; end: number }[]) =>
    ipcRenderer.invoke('export-highlights', videoPath, segments),
  onAnalysisProgress: (callback: (event: ProgressEvent) => void) => {
    const handler = (_: unknown, data: ProgressEvent) => callback(data)
    ipcRenderer.on('analysis-progress', handler)
    return () => ipcRenderer.removeListener('analysis-progress', handler)
  },
  onExportProgress: (callback: (event: { time: number }) => void) => {
    const handler = (_: unknown, data: { time: number }) => callback(data)
    ipcRenderer.on('export-progress', handler)
    return () => ipcRenderer.removeListener('export-progress', handler)
  },
})
