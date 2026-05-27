import type { ProgressStep, Segment } from '../state/AppState'
import type { Copy } from '../i18n'

interface AnalysisStageView {
  title: string
  detail: string
  stageLabel: string
  progressLabel: string
  progress: number
  subProgress: { current: number; total: number; label: string } | null
}

export function getAnalysisStageNumber(step: ProgressStep | null): number {
  if (!step) return 0
  return Math.min(Math.max(Math.floor(step.step), 1), 4)
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

export function getAnalysisVisualState(step: ProgressStep | null, copy: Copy): AnalysisVisualState {
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
    headline: activeStage === 3 ? copy.flow.visualHeadlineFiltering : copy.flow.visualHeadlineAnalyzing,
    detail: copy.flow.visualDetail(activeSegment, segmentTotal, currentPercent),
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

export function getAnalysisStageView(step: ProgressStep | null, copy: Copy): AnalysisStageView {
  if (!step) {
    return {
      title: copy.flow.waitingTitle,
      detail: copy.flow.waitingDetail,
      stageLabel: copy.flow.waitingStageLabel,
      progressLabel: copy.flow.progressLabel(0, 4),
      progress: 0,
      subProgress: null,
    }
  }

  const total = Math.max(step.total, 1)
  const stepIndex = getAnalysisStageNumber(step) - 1
  const stage = copy.flow.stages[stepIndex]
  const subProgress = step.subCurrent != null && step.subTotal != null
    ? {
        current: step.subCurrent,
        total: step.subTotal,
        label: copy.flow.groupLabel(step.subCurrent, step.subTotal),
      }
    : null

  return {
    title: stage.title,
    detail: stage.detail,
    stageLabel: stage.stageLabel,
    progressLabel: copy.flow.progressLabel(step.step, total, subProgress?.label),
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

export function getReviewTaskSummary(
  segments: Pick<Segment, 'included' | 'start' | 'end' | 'startAdjusted' | 'endAdjusted'>[],
  copy: Copy,
) {
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
    instruction: copy.flow.reviewInstruction,
  }
}

export function getExportActionCopy(selectedCount: number, exporting: boolean, copy: Copy): string {
  if (exporting) return copy.flow.exporting(selectedCount)
  if (selectedCount === 0) return copy.flow.exportNoSelection
  return copy.flow.exportSelected
}

export type SegmentTone = 'highlight' | 'keep' | 'discarded'

function formatSegmentNumber(index: number): string {
  return `#${String(index + 1).padStart(2, '0')}`
}

export function getAdjustedTimeRange(segment: Pick<Segment, 'start' | 'end' | 'startAdjusted' | 'endAdjusted'>) {
  const start = segment.startAdjusted ?? segment.start
  const end = segment.endAdjusted ?? segment.end
  const duration = Math.max(end - start, 0)
  return {
    start,
    end,
    duration,
    label: `${formatClipDuration(start)} - ${formatClipDuration(end)}`,
  }
}

export function getSegmentTone(segment: Pick<Segment, 'score' | 'included'>): SegmentTone {
  if (!segment.included) return 'discarded'
  if (segment.score > 2.3) return 'highlight'
  return 'keep'
}

export function getRallyTitle(
  segment: Pick<Segment, 'index' | 'start' | 'end' | 'score' | 'features'>,
  copy: Copy,
): string {
  const duration = Math.max(segment.end - segment.start, 0)
  const hitCount = segment.features.hit_count ?? 0
  const parts: string[] = []

  if (hitCount >= 14) parts.push(copy.flow.rallyTitle.multiHit)
  if (segment.score > 2.3) parts.push(copy.flow.rallyTitle.highIntensity)
  if (duration <= 8) parts.push(copy.flow.rallyTitle.short)

  if (parts.length > 0) {
    const joined = parts.join(copy.flow.rallyTitle.suffix === '回合' ? '' : ' ')
    return copy.flow.rallyTitle.suffix === '回合'
      ? `${joined}${copy.flow.rallyTitle.suffix} ${formatSegmentNumber(segment.index)}`
      : `${joined} ${copy.flow.rallyTitle.suffix} ${formatSegmentNumber(segment.index)}`
  }

  const fallback = segment.score > 1.7 ? copy.flow.rallyTitle.recommended : copy.flow.rallyTitle.regular
  return `${fallback} ${formatSegmentNumber(segment.index)}`
}
