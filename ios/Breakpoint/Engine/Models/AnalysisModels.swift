import Foundation

struct AnalysisResult: Equatable {
    var rallies: [Rally]
    var videoDuration: Double
}

enum AnalysisStep: Equatable {
    case extractingAudio
    case detectingHits
    case segmentingPoints
    case analyzingMotion
    case rankingPoints

    var label: String {
        switch self {
        case .extractingAudio: return String(localized: "analysis.step.extractAudio")
        case .detectingHits: return String(localized: "analysis.step.detectHits")
        case .segmentingPoints: return String(localized: "analysis.step.segmentPoints")
        case .analyzingMotion: return String(localized: "analysis.step.analyzeMotion")
        case .rankingPoints: return String(localized: "analysis.step.rankPoints")
        }
    }

    var stepNumber: Int {
        switch self {
        case .extractingAudio: return 1
        case .detectingHits: return 2
        case .segmentingPoints: return 3
        case .analyzingMotion: return 4
        case .rankingPoints: return 5
        }
    }

    static var totalSteps: Int { 5 }
}

struct AnalysisProgress: Equatable {
    var step: AnalysisStep
    var subProgress: Double?
    var elapsed: Double?
}
