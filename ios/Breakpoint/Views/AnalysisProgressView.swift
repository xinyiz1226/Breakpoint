import SwiftUI

struct AnalysisProgressView: View {
    @Binding var navigationState: NavigationState
    @State private var viewModel = AnalysisViewModel()

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            if let error = viewModel.errorMessage {
                errorView(error)
            } else {
                progressView
            }

            Spacer()
        }
        .padding()
        .onAppear {
            if let url = navigationState.videoURL {
                viewModel.startAnalysis(videoURL: url)
            }
        }
        .onChange(of: viewModel.result) { _, result in
            if let result {
                navigationState.analysisResult = result
                navigationState.screen = .editor
            }
        }
    }

    private var progressView: some View {
        VStack(spacing: 20) {
            Text("BREAKPOINT")
                .font(.system(size: 24, weight: .black))
                .tracking(1.5)

            if let step = viewModel.currentStep {
                VStack(spacing: 12) {
                    Text(step.label)
                        .font(.headline)

                    Text("\(step.stepNumber) / \(AnalysisStep.totalSteps)")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    ProgressView(value: viewModel.overallProgress)
                        .progressViewStyle(.linear)
                        .frame(maxWidth: 260)

                    if let sub = viewModel.subProgress {
                        ProgressView(value: sub)
                            .progressViewStyle(.linear)
                            .frame(maxWidth: 200)
                            .tint(.green.opacity(0.6))
                    }
                }
            } else {
                ProgressView()
                Text(String(localized: "analysis.preparing"))
                    .foregroundStyle(.secondary)
            }

            Button(String(localized: "common.cancel"), role: .cancel) {
                viewModel.cancel()
                navigationState.screen = .welcome
            }
            .buttonStyle(.bordered)
            .padding(.top, 12)
        }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.largeTitle)
                .foregroundStyle(.red)

            Text(String(localized: "analysis.error"))
                .font(.headline)

            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            HStack(spacing: 12) {
                Button(String(localized: "common.back")) {
                    navigationState.screen = .welcome
                }
                .buttonStyle(.bordered)

                Button(String(localized: "analysis.retry")) {
                    if let url = navigationState.videoURL {
                        viewModel.startAnalysis(videoURL: url)
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(.green)
            }
        }
    }
}
