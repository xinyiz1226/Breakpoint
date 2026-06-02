import Foundation
import Observation

@Observable
class AnalysisViewModel {
    var currentStep: AnalysisStep?
    var subProgress: Double?
    var errorMessage: String?
    var result: AnalysisResult?

    private var pipeline: AnalysisPipeline?

    var overallProgress: Double {
        guard let step = currentStep else { return 0 }
        let base = Double(step.stepNumber - 1) / Double(AnalysisStep.totalSteps)
        let stepContribution = (subProgress ?? 0.5) / Double(AnalysisStep.totalSteps)
        return base + stepContribution
    }

    func startAnalysis(videoURL: URL) {
        errorMessage = nil
        result = nil
        currentStep = nil
        subProgress = nil

        let newPipeline = AnalysisPipeline()
        pipeline = newPipeline

        Task {
            do {
                let rallies = try await newPipeline.analyze(videoURL: videoURL, enableVision: true) { [weak self] progress in
                    Task { @MainActor in
                        self?.currentStep = progress.step
                        self?.subProgress = progress.subProgress
                    }
                }

                await MainActor.run {
                    self.result = AnalysisResult(rallies: applyAutoInclude(rallies), videoDuration: 0)
                }
            } catch is CancellationError {
                // Cancelled, do nothing
            } catch {
                await MainActor.run {
                    self.errorMessage = error.localizedDescription
                }
            }
        }
    }

    func cancel() {
        Task {
            await pipeline?.cancel()
        }
        pipeline = nil
    }
}

/// Auto-include rallies based on tier (matching desktop behavior).
func applyAutoInclude(_ rallies: [Rally]) -> [Rally] {
    rallies.map { rally in
        var r = rally
        r.included = rally.tier == .highlight || rally.tier == .keep
        return r
    }
}
