import Foundation
import AVFoundation

/// Main analysis pipeline orchestrator.
/// Mirrors engine/pipeline.py — wires together audio extraction, hit detection,
/// segmentation, vision ranking, and final ranking.
actor AnalysisPipeline {
    private var isCancelled = false

    func cancel() {
        isCancelled = true
    }

    /// Run the full analysis pipeline, yielding progress updates via AsyncStream.
    func run(videoURL: URL, enableVision: Bool = true) -> AsyncThrowingStream<AnalysisProgress, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    try await self.execute(videoURL: videoURL, enableVision: enableVision, continuation: continuation)
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    /// Returns the final ranked rallies after the pipeline completes.
    func analyze(videoURL: URL, enableVision: Bool = true, onProgress: @escaping (AnalysisProgress) -> Void) async throws -> [Rally] {
        // Step 1: Extract audio
        try checkCancellation()
        onProgress(AnalysisProgress(step: .extractingAudio))
        let audioData = try await AudioExtractor.extract(from: videoURL)

        // Step 2: Detect hits
        try checkCancellation()
        onProgress(AnalysisProgress(step: .detectingHits))
        let hits = HitDetector.detect(samples: audioData.samples, sampleRate: audioData.sampleRate)

        let hitTimes = hits.map(\.time)
        let hitEnergies = hits.map(\.energy)

        // Step 3: Segment points
        try checkCancellation()
        onProgress(AnalysisProgress(step: .segmentingPoints))
        let segments = Segmentation.segment(hitTimes: hitTimes, hitEnergies: hitEnergies)

        // Step 4: Vision ranking (optional)
        var motionScores: [Double]? = nil
        if enableVision && !segments.isEmpty {
            try checkCancellation()
            onProgress(AnalysisProgress(step: .analyzingMotion))
            motionScores = []
            for (i, segment) in segments.enumerated() {
                try checkCancellation()
                let score = try await VisionRanking.analyzeMotion(videoURL: videoURL, segment: segment)
                motionScores?.append(score)
                onProgress(AnalysisProgress(
                    step: .analyzingMotion,
                    subProgress: Double(i + 1) / Double(segments.count)
                ))
            }
        }

        // Step 5: Rank
        try checkCancellation()
        onProgress(AnalysisProgress(step: .rankingPoints))
        let rallies = Ranking.rank(segments: segments, motionScores: motionScores)

        return rallies
    }

    private func execute(
        videoURL: URL,
        enableVision: Bool,
        continuation: AsyncThrowingStream<AnalysisProgress, Error>.Continuation
    ) async throws {
        let rallies = try await analyze(videoURL: videoURL, enableVision: enableVision) { progress in
            continuation.yield(progress)
        }
        // Final yield with completion info embedded in the last step
        continuation.yield(AnalysisProgress(step: .rankingPoints, subProgress: 1.0))
        continuation.finish()
    }

    private func checkCancellation() throws {
        if isCancelled {
            throw AnalysisError.cancelled
        }
    }
}
