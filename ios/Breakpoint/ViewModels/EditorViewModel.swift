import Foundation
import Observation

@Observable
class EditorViewModel {
    let videoURL: URL
    var rallies: [Rally]
    var videoDuration: Double
    var currentTime: Double = 0
    var seekTarget: Double?
    var selectedRallyIndex: Int?

    var pauseAtTime: Double? {
        guard let index = selectedRallyIndex, index < rallies.count else { return nil }
        return rallies[index].effectiveEnd
    }

    init(videoURL: URL, result: AnalysisResult) {
        self.videoURL = videoURL
        self.rallies = result.rallies
        self.videoDuration = result.videoDuration
    }

    func seek(to time: Double) {
        seekTarget = time
        selectedRallyIndex = nil
    }

    func seekAndPlay(to time: Double) {
        // Find which rally starts at this time
        if let index = rallies.firstIndex(where: { $0.effectiveStart == time }) {
            selectedRallyIndex = index
        }
        seekTarget = time
    }
}
