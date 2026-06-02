import SwiftUI

@main
struct BreakpointApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.locale, LocalizationManager.shared.locale)
        }
    }
}
