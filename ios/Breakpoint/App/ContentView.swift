import SwiftUI

struct ContentView: View {
    @State private var navigationState = NavigationState()

    var body: some View {
        Group {
            switch navigationState.screen {
            case .welcome:
                WelcomeView(navigationState: $navigationState)
            case .analysis:
                AnalysisProgressView(navigationState: $navigationState)
            case .editor:
                EditorView(navigationState: $navigationState)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: navigationState.screen)
    }
}

@Observable
class NavigationState {
    var screen: Screen = .welcome
    var videoURL: URL?
    var analysisResult: AnalysisResult?

    enum Screen: Equatable {
        case welcome
        case analysis
        case editor
    }
}
