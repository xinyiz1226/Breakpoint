import { createContext, useContext, useReducer, ReactNode } from 'react'

const INCLUDE_THRESHOLD = 1.7
const MIN_SEGMENT_DURATION = 0.5

type VideoAnalysisStatus = 'pending' | 'running' | 'done' | 'error'

interface Segment {
  index: number
  start: number
  end: number
  score: number
  features: Record<string, number>
  included: boolean
  startAdjusted?: number
  endAdjusted?: number
}

interface ProgressStep {
  step: number
  total: number
  label: string
  elapsed?: number
  subCurrent?: number
  subTotal?: number
}

interface VideoRecord {
  id: string
  path: string
  displayName: string
  order: number
  status: VideoAnalysisStatus
  errorMessage: string | null
  currentStep: ProgressStep | null
  duration: number
  rallyCount: number
}

interface RallySegment {
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

interface AppState {
  videos: VideoRecord[]
  activeVideoId: string | null
  selectedRallyId: string | null
  analysisStatus: 'idle' | 'running' | 'done' | 'error'
  currentStep: ProgressStep | null
  errorMessage: string | null
  rallies: RallySegment[]
  videoPath: string | null
  segments: Segment[]
  selectedSegmentIndex: number | null
  videoDuration: number
}

type Action =
  | { type: 'CREATE_BATCH'; videos: VideoRecord[] }
  | { type: 'CLOSE_BATCH' }
  | { type: 'BATCH_ANALYSIS_START' }
  | { type: 'BATCH_ANALYSIS_DONE' }
  | { type: 'BATCH_ANALYSIS_ERROR'; message: string }
  | { type: 'VIDEO_ANALYSIS_START'; videoId: string }
  | { type: 'VIDEO_ANALYSIS_RETRY'; videoId: string }
  | { type: 'VIDEO_ANALYSIS_STEP'; videoId: string; step: ProgressStep }
  | { type: 'VIDEO_ANALYSIS_SUB_PROGRESS'; videoId: string; current: number; total: number }
  | { type: 'VIDEO_ANALYSIS_DONE'; videoId: string; rallies: RallySegment[] }
  | { type: 'VIDEO_ANALYSIS_ERROR'; videoId: string; message: string }
  | { type: 'SET_VIDEO_DURATION'; videoId: string; duration: number }
  | { type: 'SET_ACTIVE_VIDEO'; id: string | null }
  | { type: 'SELECT_RALLY'; id: string | null }
  | { type: 'TOGGLE_INCLUDE'; id: string; index?: never }
  | { type: 'INCLUDE_ALL' }
  | { type: 'EXCLUDE_ALL' }
  | { type: 'RESTORE_RECOMMENDED' }
  | { type: 'ADJUST_RALLY'; id: string; start?: number | undefined; end?: number | undefined }
  | { type: 'SET_VIDEO'; path: string }
  | { type: 'CLOSE_VIDEO' }
  | { type: 'ANALYSIS_START' }
  | { type: 'ANALYSIS_STEP'; step: ProgressStep }
  | { type: 'ANALYSIS_SUB_PROGRESS'; current: number; total: number }
  | { type: 'ANALYSIS_DONE'; segments: Segment[] }
  | { type: 'ANALYSIS_ERROR'; message: string }
  | { type: 'SELECT_SEGMENT'; index: number | null }
  | { type: 'TOGGLE_INCLUDE'; index: number; id?: never }
  | { type: 'RESET_ALL' }
  | { type: 'ADJUST_SEGMENT'; index: number; start?: number | undefined; end?: number | undefined }
  | { type: 'SET_DURATION'; duration: number }
  | { type: 'LOAD_SEGMENTS'; segments: Segment[] }

function applyAutoInclude<T extends { score: number; included: boolean }>(rallies: T[]): T[] {
  return rallies.map((rally) => ({ ...rally, included: rally.score > INCLUDE_THRESHOLD }))
}

function hasActionValue(action: Extract<Action, { type: 'ADJUST_RALLY' }> | Extract<Action, { type: 'ADJUST_SEGMENT' }>, key: 'start' | 'end'): boolean {
  return Object.prototype.hasOwnProperty.call(action, key)
}

function applyRallyAdjustment(rally: RallySegment, action: Extract<Action, { type: 'ADJUST_RALLY' }>): RallySegment {
  const hasStart = hasActionValue(action, 'start')
  const hasEnd = hasActionValue(action, 'end')
  let startAdjusted = hasStart ? action.start : rally.startAdjusted
  let endAdjusted = hasEnd ? action.end : rally.endAdjusted
  const effectiveStart = startAdjusted ?? rally.start
  const effectiveEnd = endAdjusted ?? rally.end

  if (effectiveEnd - effectiveStart < MIN_SEGMENT_DURATION) {
    if (hasStart && !hasEnd) {
      startAdjusted = effectiveEnd - MIN_SEGMENT_DURATION
    } else {
      endAdjusted = effectiveStart + MIN_SEGMENT_DURATION
    }
  }

  return { ...rally, startAdjusted, endAdjusted }
}

function applySegmentAdjustment(segment: Segment, action: Extract<Action, { type: 'ADJUST_SEGMENT' }>): Segment {
  const hasStart = hasActionValue(action, 'start')
  const hasEnd = hasActionValue(action, 'end')
  let startAdjusted = hasStart ? action.start : segment.startAdjusted
  let endAdjusted = hasEnd ? action.end : segment.endAdjusted
  const effectiveStart = startAdjusted ?? segment.start
  const effectiveEnd = endAdjusted ?? segment.end

  if (effectiveEnd - effectiveStart < MIN_SEGMENT_DURATION) {
    if (hasStart && !hasEnd) {
      startAdjusted = effectiveEnd - MIN_SEGMENT_DURATION
    } else {
      endAdjusted = effectiveStart + MIN_SEGMENT_DURATION
    }
  }

  return { ...segment, startAdjusted, endAdjusted }
}

const initialState: AppState = {
  videos: [],
  activeVideoId: null,
  selectedRallyId: null,
  analysisStatus: 'idle',
  currentStep: null,
  errorMessage: null,
  rallies: [],
  videoPath: null,
  segments: [],
  selectedSegmentIndex: null,
  videoDuration: 0,
}

function updateVideo(state: AppState, videoId: string, updater: (video: VideoRecord) => VideoRecord): AppState {
  return {
    ...state,
    videos: state.videos.map((video) => video.id === videoId ? updater(video) : video),
  }
}

function clearVideoRalliesForRerun(state: AppState, videoId: string): AppState {
  const selectedRallyBelongsToVideo = state.selectedRallyId
    ? state.rallies.some((rally) => rally.id === state.selectedRallyId && rally.videoId === videoId)
    : false

  return {
    ...state,
    rallies: state.rallies.filter((rally) => rally.videoId !== videoId),
    selectedRallyId: selectedRallyBelongsToVideo ? null : state.selectedRallyId,
  }
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'CREATE_BATCH':
      return { ...initialState, videos: action.videos, activeVideoId: action.videos[0]?.id ?? null }
    case 'CLOSE_BATCH':
      return initialState
    case 'BATCH_ANALYSIS_START':
      return { ...state, analysisStatus: 'running', currentStep: null, errorMessage: null }
    case 'BATCH_ANALYSIS_DONE':
      return { ...state, analysisStatus: 'done', currentStep: null }
    case 'BATCH_ANALYSIS_ERROR':
      return { ...state, analysisStatus: 'error', errorMessage: action.message, currentStep: null }
    case 'VIDEO_ANALYSIS_START':
    case 'VIDEO_ANALYSIS_RETRY':
      return updateVideo(
        clearVideoRalliesForRerun({ ...state, analysisStatus: 'running', errorMessage: null }, action.videoId),
        action.videoId,
        (video) => ({
          ...video,
          status: 'running',
          errorMessage: null,
          currentStep: null,
          rallyCount: 0,
        }),
      )
    case 'VIDEO_ANALYSIS_STEP':
      return updateVideo({ ...state, currentStep: action.step }, action.videoId, (video) => ({
        ...video,
        currentStep: { ...action.step, subCurrent: undefined, subTotal: undefined },
      }))
    case 'VIDEO_ANALYSIS_SUB_PROGRESS':
      return updateVideo(state, action.videoId, (video) => {
        const currentStep = video.currentStep
          ? { ...video.currentStep, subCurrent: action.current, subTotal: action.total }
          : null
        return { ...video, currentStep }
      })
    case 'VIDEO_ANALYSIS_DONE':
      return updateVideo(
        {
          ...state,
          rallies: [
            ...state.rallies.filter((rally) => rally.videoId !== action.videoId),
            ...action.rallies,
          ],
        },
        action.videoId,
        (video) => ({ ...video, status: 'done', errorMessage: null, currentStep: null, rallyCount: action.rallies.length }),
      )
    case 'VIDEO_ANALYSIS_ERROR':
      return updateVideo(state, action.videoId, (video) => ({
        ...video,
        status: 'error',
        errorMessage: action.message,
        currentStep: null,
      }))
    case 'SET_VIDEO_DURATION':
      return updateVideo(state, action.videoId, (video) => ({ ...video, duration: action.duration }))
    case 'SET_ACTIVE_VIDEO':
      return { ...state, activeVideoId: action.id }
    case 'SELECT_RALLY':
      return { ...state, selectedRallyId: action.id }
    case 'TOGGLE_INCLUDE':
      if ('id' in action) {
        return { ...state, rallies: state.rallies.map((rally) => rally.id === action.id ? { ...rally, included: !rally.included } : rally) }
      }
      return { ...state, segments: state.segments.map((segment, index) => index === action.index ? { ...segment, included: !segment.included } : segment) }
    case 'INCLUDE_ALL':
      return {
        ...state,
        rallies: state.rallies.map((rally) => ({ ...rally, included: true })),
        segments: state.segments.map((segment) => ({ ...segment, included: true })),
      }
    case 'EXCLUDE_ALL':
      return {
        ...state,
        rallies: state.rallies.map((rally) => ({ ...rally, included: false })),
        segments: state.segments.map((segment) => ({ ...segment, included: false })),
      }
    case 'RESET_ALL':
      return { ...state, segments: applyAutoInclude(state.segments.map((segment) => ({ ...segment, startAdjusted: undefined, endAdjusted: undefined }))) }
    case 'RESTORE_RECOMMENDED':
      return {
        ...state,
        rallies: state.rallies.map((rally) => ({ ...rally, included: rally.score > INCLUDE_THRESHOLD })),
        segments: state.segments?.map((segment) => ({ ...segment, included: segment.score > INCLUDE_THRESHOLD })),
      }
    case 'ADJUST_RALLY':
      return { ...state, rallies: state.rallies.map((rally) => rally.id === action.id ? applyRallyAdjustment(rally, action) : rally) }
    case 'SET_VIDEO':
      return { ...initialState, videoPath: action.path }
    case 'CLOSE_VIDEO':
      return initialState
    case 'ANALYSIS_START':
      return { ...state, analysisStatus: 'running', currentStep: null, errorMessage: null }
    case 'ANALYSIS_STEP':
      return { ...state, currentStep: { ...action.step, subCurrent: undefined, subTotal: undefined } }
    case 'ANALYSIS_SUB_PROGRESS':
      return state.currentStep
        ? { ...state, currentStep: { ...state.currentStep, subCurrent: action.current, subTotal: action.total } }
        : state
    case 'ANALYSIS_DONE':
      return { ...state, analysisStatus: 'done', currentStep: null, segments: action.segments }
    case 'ANALYSIS_ERROR':
      return { ...state, analysisStatus: 'error', currentStep: null, errorMessage: action.message }
    case 'SELECT_SEGMENT':
      return { ...state, selectedSegmentIndex: action.index }
    case 'ADJUST_SEGMENT':
      return {
        ...state,
        segments: state.segments.map((segment, index) =>
          index === action.index
            ? applySegmentAdjustment(segment, action)
            : segment
        ),
      }
    case 'SET_DURATION':
      return { ...state, videoDuration: action.duration }
    case 'LOAD_SEGMENTS':
      return { ...state, analysisStatus: 'done', segments: action.segments }
    default:
      return state
  }
}

const AppContext = createContext<{ state: AppState; dispatch: React.Dispatch<Action> } | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  return <AppContext.Provider value={{ state, dispatch }}>{children}</AppContext.Provider>
}

export function useAppState() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useAppState must be used within AppProvider')
  return ctx
}

export { INCLUDE_THRESHOLD, MIN_SEGMENT_DURATION, applyAutoInclude, reducer }
export type { Action, AppState, ProgressStep, RallySegment, Segment, VideoAnalysisStatus, VideoRecord }
