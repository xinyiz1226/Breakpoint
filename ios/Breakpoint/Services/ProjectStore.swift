import Foundation
import SwiftUI

struct RecentProject: Identifiable, Codable {
    var id: String { videoPath }
    let videoPath: String
    let name: String
    let lastOpened: Date

    var videoURL: URL { URL(fileURLWithPath: videoPath) }
    var dateString: String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: lastOpened, relativeTo: Date())
    }
}

@Observable
class ProjectStore {
    static let shared = ProjectStore()

    private let key = "recentProjects"
    var recentProjects: [RecentProject] = []

    private init() {
        load()
    }

    func addRecent(url: URL) {
        let project = RecentProject(
            videoPath: url.path,
            name: url.deletingPathExtension().lastPathComponent,
            lastOpened: Date()
        )

        recentProjects.removeAll { $0.videoPath == project.videoPath }
        recentProjects.insert(project, at: 0)
        if recentProjects.count > 20 {
            recentProjects = Array(recentProjects.prefix(20))
        }
        save()
    }

    private func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let projects = try? JSONDecoder().decode([RecentProject].self, from: data) else { return }
        recentProjects = projects
    }

    private func save() {
        guard let data = try? JSONEncoder().encode(recentProjects) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }
}
