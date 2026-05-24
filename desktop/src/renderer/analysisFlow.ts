interface AnalysisSegment {
  index: number
  start: number
  end: number
  score: number
  features: Record<string, number>
}

export function hasReusableAnalysisReport(segments: AnalysisSegment[] | null): segments is AnalysisSegment[] {
  return Array.isArray(segments) && segments.length > 0
}
