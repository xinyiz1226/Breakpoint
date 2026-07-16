interface AnalysisSegment {
  analysis_version?: number
  player_identity_status?: 'complete' | 'skipped_court_detection' | 'disabled'
  index: number
  start: number
  end: number
  score: number
  features: Record<string, number>
  players?: {
    player_1?: { detected?: boolean }
    player_2?: { detected?: boolean }
  }
}

export function hasReusableAnalysisReport(segments: AnalysisSegment[] | null): segments is AnalysisSegment[] {
  return Array.isArray(segments)
    && segments.length > 0
    && segments.every((segment) => (
      segment.analysis_version === 2
      && (
        segment.player_identity_status === 'skipped_court_detection'
        || (
          segment.player_identity_status === 'complete'
          && typeof segment.players?.player_1?.detected === 'boolean'
          && typeof segment.players?.player_2?.detected === 'boolean'
        )
      )
    ))
}
