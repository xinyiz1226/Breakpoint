import { createContext, useContext, useReducer, ReactNode } from 'react'

const INCLUDE_THRESHOLD = 1.7

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

interface AppState {
  videoPath: string | null
  analysisStatus: 'idle' | 'running' | 'done' | 'error'
  currentStep: ProgressStep | null
  errorMessage: string | null
  segments: Segment[]
  selectedSegmentIndex: number | null
  videoDuration: number
}

type Action =
  | { type: 'SET_VIDEO'; path: string }
  | { type: 'CLOSE_VIDEO' }
  | { type: 'ANALYSIS_START' }
  | { type: 'ANALYSIS_STEP'; step: ProgressStep }
  | { type: 'ANALYSIS_SUB_PROGRESS'; current: number; total: number }
  | { type: 'ANALYSIS_DONE'; segments: Segment[] }
  | { type: 'ANALYSIS_ERROR'; message: string }
  | { type: 'SELECT_SEGMENT'; index: number | null }
  | { type: 'TOGGLE_INCLUDE'; index: number }
  | { type: 'INCLUDE_ALL' }
  | { type: 'EXCLUDE_ALL' }
  | { type: 'RESET_ALL' }
  | { type: 'ADJUST_SEGMENT'; index: number; start?: number | undefined; end?: number | undefined }
  | { type: 'SET_DURATION'; duration: number }
  | { type: 'LOAD_SEGMENTS'; segments: Segment[] }

function applyAutoInclude(segments: Segment[]): Segment[] {
  return segments.map((s) => ({ ...s, included: s.score > INCLUDE_THRESHOLD }))
}

const initialState: AppState = {
  videoPath: null,
  analysisStatus: 'idle',
  currentStep: null,
  errorMessage: null,
  segments: [],
  selectedSegmentIndex: null,
  videoDuration: 0,
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
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
    case 'TOGGLE_INCLUDE':
      return { ...state, segments: state.segments.map((s, i) => i === action.index ? { ...s, included: !s.included } : s) }
    case 'INCLUDE_ALL':
      return { ...state, segments: state.segments.map((s) => ({ ...s, included: true })) }
    case 'EXCLUDE_ALL':
      return { ...state, segments: state.segments.map((s) => ({ ...s, included: false })) }
    case 'RESET_ALL':
      return { ...state, segments: applyAutoInclude(state.segments.map((s) => ({ ...s, startAdjusted: undefined, endAdjusted: undefined }))) }
    case 'ADJUST_SEGMENT':
      return {
        ...state,
        segments: state.segments.map((s, i) =>
          i === action.index
            ? {
                ...s,
                startAdjusted: 'start' in action ? action.start : s.startAdjusted,
                endAdjusted: 'end' in action ? action.end : s.endAdjusted,
              }
            : s
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

export { INCLUDE_THRESHOLD, applyAutoInclude }
export type { Segment, ProgressStep, AppState, Action }
