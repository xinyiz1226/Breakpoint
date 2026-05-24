import type { ProgressStep, Segment } from '../state/AppState'

interface AnalysisStageView {
  title: string
  detail: string
  stageLabel: string
  progressLabel: string
  progress: number
  subProgress: { current: number; total: number; label: string } | null
}

const ANALYSIS_STAGES = [
  { title: '正在读取整场视频', detail: '正在准备比赛素材，导入后会自动进入下一步。', stageLabel: '读取中' },
  { title: '正在定位比赛片段', detail: '正在把完整视频整理成可确认的候选片段。', stageLabel: '定位中' },
  { title: '正在筛选精彩瞬间', detail: '正在逐组确认可分享的高光片段，请保持窗口打开。', stageLabel: '筛选中' },
  { title: '正在准备确认列表', detail: '即将进入剪辑页，你可以确认片段并导出合集。', stageLabel: '准备中' },
] as const

export function getAnalysisStageNumber(step: ProgressStep | null): number {
  if (!step) return 0
  return Math.min(Math.max(Math.floor(step.step), 1), ANALYSIS_STAGES.length)
}

interface AnalysisVisualBar {
  index: number
  active: boolean
  done: boolean
  height: number
}

interface AnalysisVisualState {
  scanPercent: number
  activeStage: number
  activeSegment: number
  segmentTotal: number
  headline: string
  detail: string
  bars: AnalysisVisualBar[]
}

const VISUAL_BAR_HEIGHTS = [18, 26, 16, 34, 22, 30, 20, 38, 24, 32, 18, 28]

export function getAnalysisVisualState(step: ProgressStep | null): AnalysisVisualState {
  const activeStage = getAnalysisStageNumber(step)
  const total = Math.max(step?.total ?? 4, 1)
  const progress = Math.min(Math.max((step?.step ?? 0) / total, 0), 1)
  const segmentTotal = Math.max(step?.subTotal ?? 12, 1)
  const activeSegment = Math.min(Math.max(step?.subCurrent ?? 1, 1), segmentTotal)
  const currentPercent = Math.round(progress * 100)
  const activeBar = Math.min(activeSegment, VISUAL_BAR_HEIGHTS.length)

  return {
    scanPercent: Math.round(progress * 1000) / 10,
    activeStage,
    activeSegment,
    segmentTotal,
    headline: activeStage === 3 ? '正在筛选精彩片段' : '正在分析视频',
    detail: `片段 ${activeSegment} / ${segmentTotal} · 当前 ${currentPercent}%`,
    bars: VISUAL_BAR_HEIGHTS.map((height, index) => {
      const barIndex = index + 1
      return {
        index: barIndex,
        active: barIndex === activeBar,
        done: barIndex < activeBar,
        height,
      }
    }),
  }
}

export function getAnalysisStageView(step: ProgressStep | null): AnalysisStageView {
  if (!step) {
    return {
      title: '准备开始处理',
      detail: '导入视频后会自动开始分析。',
      stageLabel: '等待视频',
      progressLabel: '0 / 4',
      progress: 0,
      subProgress: null,
    }
  }

  const total = Math.max(step.total, 1)
  const stepIndex = getAnalysisStageNumber(step) - 1
  const stage = ANALYSIS_STAGES[stepIndex]
  const subProgress = step.subCurrent != null && step.subTotal != null
    ? {
        current: step.subCurrent,
        total: step.subTotal,
        label: `${step.subCurrent} / ${step.subTotal} 组`,
      }
    : null

  return {
    title: stage.title,
    detail: stage.detail,
    stageLabel: stage.stageLabel,
    progressLabel: `${step.step} / ${total}${subProgress ? ` · ${subProgress.label}` : ''}`,
    progress: Math.min(Math.max(step.step / total, 0), 1),
    subProgress,
  }
}

export function formatClipDuration(seconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(safeSeconds / 60)
  const remainder = safeSeconds % 60
  return `${minutes}:${remainder.toString().padStart(2, '0')}`
}

export function getReviewTaskSummary(segments: Pick<Segment, 'included' | 'start' | 'end' | 'startAdjusted' | 'endAdjusted'>[]) {
  const selected = segments.filter((segment) => segment.included)
  const selectedDuration = selected.reduce((sum, segment) => {
    const start = segment.startAdjusted ?? segment.start
    const end = segment.endAdjusted ?? segment.end
    return sum + Math.max(end - start, 0)
  }, 0)

  return {
    selectedCount: selected.length,
    totalCount: segments.length,
    selectedDurationLabel: formatClipDuration(selectedDuration),
    instruction: '挑选视频片段，确认保留后导出精彩合集。',
  }
}

export function getExportActionCopy(selectedCount: number, exporting: boolean): string {
  if (exporting) return `正在导出 ${selectedCount} 个回合`
  if (selectedCount === 0) return '选择回合后导出'
  return '导出已选择的回合'
}
