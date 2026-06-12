const AUTO_INCLUDE_THRESHOLD = 1.7

interface AnalysisSegment {
  index: number
  start: number
  end: number
  score: number
  features: Record<string, number>
}

export interface ExportClip {
  videoPath: string
  start: number
  end: number
}

export interface VideoRecord {
  id: string
  path: string
  displayName: string
  order: number
  status: 'pending' | 'running' | 'done' | 'error'
  errorMessage: string | null
  currentStep: unknown | null
  duration: number
  rallyCount: number
}

export interface RallySegment {
  id: string
  videoId: string
  sourceIndex: number
  index: number
  start: number
  end: number
  score: number
  features: Record<string, number>
  included: boolean
  startAdjusted?: number
  endAdjusted?: number
}

export function getVideoDisplayName(path: string): string {
  return path.split(/[\\/]/).pop() || path
}

export function createVideoRecords(paths: string[]): VideoRecord[] {
  return paths.map((path, order) => ({
    id: `video-${order + 1}`,
    path,
    displayName: getVideoDisplayName(path),
    order,
    status: 'pending',
    errorMessage: null,
    currentStep: null,
    duration: 0,
    rallyCount: 0,
  }))
}

export function createRalliesForVideo(video: VideoRecord, segments: AnalysisSegment[]): RallySegment[] {
  return segments.map((segment) => ({
    id: `${video.id}-rally-${segment.index}`,
    videoId: video.id,
    sourceIndex: segment.index,
    index: segment.index,
    start: segment.start,
    end: segment.end,
    score: segment.score,
    features: segment.features,
    included: segment.score > AUTO_INCLUDE_THRESHOLD,
  }))
}

export function getSortedRallies(rallies: RallySegment[], videos: VideoRecord[]): RallySegment[] {
  const orderByVideo = new Map(videos.map((video) => [video.id, video.order]))
  return rallies.slice().sort((a, b) => {
    const videoDelta = (orderByVideo.get(a.videoId) ?? Number.MAX_SAFE_INTEGER) - (orderByVideo.get(b.videoId) ?? Number.MAX_SAFE_INTEGER)
    if (videoDelta !== 0) return videoDelta
    return a.start - b.start
  })
}

export function getRalliesForVideo(rallies: RallySegment[], videoId: string): RallySegment[] {
  return rallies.filter((rally) => rally.videoId === videoId)
}

export function getExportClips(rallies: RallySegment[], videos: VideoRecord[]): ExportClip[] {
  const pathByVideo = new Map(videos.map((video) => [video.id, video.path]))
  return getSortedRallies(rallies.filter((rally) => rally.included), videos)
    .map((rally) => {
      const videoPath = pathByVideo.get(rally.videoId)
      if (!videoPath) return null
      return {
        videoPath,
        start: rally.startAdjusted ?? rally.start,
        end: rally.endAdjusted ?? rally.end,
      }
    })
    .filter((clip): clip is ExportClip => clip !== null && clip.end > clip.start)
}
