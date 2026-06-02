import Foundation

/// Segments hit events into individual rallies/points.
/// Port of engine/segmentation.py.
struct Segmentation {
    struct Parameters {
        var silenceGap: Double = 6.0
        var buffer: Double = 1.5
        var minHits: Int = 3
        var minDuration: Double = 3.0
        var maxDuration: Double = 120.0
    }

    struct RawSegment {
        var start: Double
        var end: Double
        var hitTimes: [Double]
        var hitEnergies: [Double]
    }

    /// Split hit events into rally segments using silence gaps.
    static func segment(
        hitTimes: [Double],
        hitEnergies: [Double],
        parameters: Parameters = Parameters()
    ) -> [RawSegment] {
        guard hitTimes.count >= 2 else { return [] }

        var segments: [RawSegment] = []
        var currentHits: [Double] = [hitTimes[0]]
        var currentEnergies: [Double] = [hitEnergies[0]]

        for i in 1..<hitTimes.count {
            let gap = hitTimes[i] - hitTimes[i - 1]
            if gap >= parameters.silenceGap {
                // End current segment
                if currentHits.count >= parameters.minHits {
                    let start = max(0, currentHits.first! - parameters.buffer)
                    let end = currentHits.last! + parameters.buffer
                    segments.append(RawSegment(
                        start: start,
                        end: end,
                        hitTimes: currentHits,
                        hitEnergies: currentEnergies
                    ))
                }
                currentHits = [hitTimes[i]]
                currentEnergies = [hitEnergies[i]]
            } else {
                currentHits.append(hitTimes[i])
                currentEnergies.append(hitEnergies[i])
            }
        }

        // Final segment
        if currentHits.count >= parameters.minHits {
            let start = max(0, currentHits.first! - parameters.buffer)
            let end = currentHits.last! + parameters.buffer
            segments.append(RawSegment(
                start: start,
                end: end,
                hitTimes: currentHits,
                hitEnergies: currentEnergies
            ))
        }

        // Filter by duration
        return segments.filter { seg in
            let duration = seg.end - seg.start
            return duration >= parameters.minDuration && duration <= parameters.maxDuration
        }
    }
}
