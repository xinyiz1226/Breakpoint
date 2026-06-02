import SwiftUI

struct EditorView: View {
    @Binding var navigationState: NavigationState
    @State private var viewModel: EditorViewModel
    @State private var exportViewModel = ExportViewModel()

    init(navigationState: Binding<NavigationState>) {
        _navigationState = navigationState
        let result = navigationState.wrappedValue.analysisResult ?? AnalysisResult(rallies: [], videoDuration: 0)
        _viewModel = State(initialValue: EditorViewModel(
            videoURL: navigationState.wrappedValue.videoURL!,
            result: result
        ))
    }

    var body: some View {
        VStack(spacing: 0) {
            headerBar

            GeometryReader { geo in
                if geo.size.width > 700 {
                    // iPad landscape: side-by-side
                    HStack(spacing: 0) {
                        mainContent
                        sidePanel
                            .frame(width: 320)
                    }
                } else {
                    // iPhone: stacked
                    VStack(spacing: 0) {
                        mainContent
                        sidePanel
                            .frame(height: 300)
                    }
                }
            }
        }
        .background(Color(.systemBackground))
    }

    private var headerBar: some View {
        HStack {
            Text("BREAKPOINT")
                .font(.system(size: 14, weight: .black))
                .tracking(0.5)

            Spacer()

            Button(String(localized: "editor.back")) {
                navigationState.screen = .welcome
            }
            .font(.caption)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial)
    }

    private var mainContent: some View {
        VStack(spacing: 0) {
            VideoPlayerView(
                videoURL: viewModel.videoURL,
                seekTarget: viewModel.seekTarget,
                pauseAt: viewModel.pauseAtTime,
                onTimeUpdate: { viewModel.currentTime = $0 },
                onDurationChange: { viewModel.videoDuration = $0 }
            )
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .padding()

            MatchMapView(
                rallies: viewModel.rallies,
                duration: viewModel.videoDuration,
                currentTime: viewModel.currentTime,
                onSeek: { viewModel.seek(to: $0) }
            )
            .frame(height: 60)
            .padding(.horizontal)
            .padding(.bottom, 8)
        }
    }

    private var sidePanel: some View {
        RallyQueueView(
            rallies: $viewModel.rallies,
            currentTime: viewModel.currentTime,
            onSeek: { viewModel.seek(to: $0) },
            onSeekAndPlay: { viewModel.seekAndPlay(to: $0) },
            onExport: { exportViewModel.export(videoURL: viewModel.videoURL, rallies: viewModel.rallies) },
            exportProgress: exportViewModel.progress,
            exportResult: exportViewModel.result
        )
    }
}
