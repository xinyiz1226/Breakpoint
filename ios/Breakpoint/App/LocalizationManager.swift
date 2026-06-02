import SwiftUI
import Observation

@Observable
final class LocalizationManager {
    static let shared = LocalizationManager()

    var language: AppLanguage = .system {
        didSet { updateLocale() }
    }

    var locale: Locale = .current

    private init() {
        updateLocale()
    }

    private func updateLocale() {
        switch language {
        case .english:
            locale = Locale(identifier: "en")
        case .chinese:
            locale = Locale(identifier: "zh-Hans")
        case .system:
            locale = .current
        }
    }
}

enum AppLanguage: String, CaseIterable {
    case system
    case english
    case chinese

    var displayName: String {
        switch self {
        case .system: "Auto"
        case .english: "EN"
        case .chinese: "中文"
        }
    }
}
