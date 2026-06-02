import Foundation

/// Ranks rally segments by combined audio and motion features.
/// Port of engine/ranking.py.
struct Ranking {
    /// Rank segments and assign scores, optionally incorporating vision motion data.
    static func rank(
        segments: [Segmentation.RawSegment],
        motionScores: [Double]? = nil,
        visionKeep: Double = 0.7
    ) -> [Rally] {
        guard !segments.isEmpty else { return [] }

        // Compute audio-based features
        var rallies: [Rally] = segments.enumerated().map { index, seg in
            let hitCount = seg.hitTimes.count
            let avgEnergy = seg.hitEnergies.isEmpty ? 0 : seg.hitEnergies.reduce(0, +) / Double(seg.hitEnergies.count)
            let duration = seg.end - seg.start
            let hitDensity = Double(hitCount) / duration

            // Base score from audio features
            var score = normalize(hitDensity, min: 0.2, max: 2.0) * 0.4
                + normalize(avgEnergy, min: 0, max: 1) * 0.3
                + normalize(Double(hitCount), min: 3, max: 30) * 0.3

            // Incorporate vision score if available
            if let motionScores, index < motionScores.count {
                let motionScore = motionScores[index]
                score = score * 0.5 + normalize(motionScore, min: 0, max: 0.1) * 0.5
            }

            return Rally(
                id: index + 1,
                start: seg.start,
                end: seg.end,
                score: min(1.0, max(0, score)),
                features: RallyFeatures(
                    hitCount: hitCount,
                    avgEnergy: avgEnergy,
                    motionScore: motionScores?[safe: index]
                )
            )
        }

        // Sort by score descending
        rallies.sort { $0.score > $1.score }

        // Apply vision keep filter
        if motionScores != nil && rallies.count > 1 {
            let keepCount = max(1, Int(Double(rallies.count) * visionKeep))
            rallies = Array(rallies.prefix(keepCount))
        }

        return rallies
    }

    private static func normalize(_ value: Double, min: Double, max: Double) -> Double {
        guard max > min else { return 0 }
        return Swift.min(1.0, Swift.max(0, (value - min) / (max - min)))
    }
}

private extension Array {
    subscript(safe index: Int) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
