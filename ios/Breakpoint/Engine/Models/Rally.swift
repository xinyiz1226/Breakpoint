import Foundation

struct Rally: Identifiable, Codable, Equatable {
    let id: Int
    var start: Double
    var end: Double
    var score: Double
    var features: RallyFeatures
    var included: Bool = false
    var startAdjusted: Double?
    var endAdjusted: Double?

    var effectiveStart: Double { startAdjusted ?? start }
    var effectiveEnd: Double { endAdjusted ?? end }
    var duration: Double { effectiveEnd - effectiveStart }

    var tier: Tier {
        if score >= 0.7 { return .highlight }
        if score >= 0.4 { return .keep }
        return .cut
    }

    enum Tier: String, Codable {
        case highlight, keep, cut
    }
}

struct RallyFeatures: Codable, Equatable {
    let hitCount: Int
    let avgEnergy: Double?
    let motionScore: Double?

    enum CodingKeys: String, CodingKey {
        case hitCount = "hit_count"
        case avgEnergy = "avg_energy"
        case motionScore = "motion_score"
    }
}
