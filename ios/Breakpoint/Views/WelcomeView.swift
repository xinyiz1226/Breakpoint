import SwiftUI
import PhotosUI

struct WelcomeView: View {
    @Binding var navigationState: NavigationState
    @State private var selectedItem: PhotosPickerItem?
    @State private var showFilePicker = false
    @State private var recentProjects: [RecentProject] = []

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 16) {
                Text("BREAKPOINT")
                    .font(.system(size: 32, weight: .black, design: .default))
                    .tracking(2)

                Text(String(localized: "welcome.subtitle"))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Spacer().frame(height: 48)

            VStack(spacing: 12) {
                PhotosPicker(selection: $selectedItem, matching: .videos) {
                    Label(String(localized: "welcome.openVideo"), systemImage: "film")
                        .frame(maxWidth: 260)
                }
                .buttonStyle(.borderedProminent)
                .tint(.green)
                .controlSize(.large)

                Button {
                    showFilePicker = true
                } label: {
                    Label(String(localized: "welcome.importFile"), systemImage: "folder")
                        .frame(maxWidth: 260)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }

            if !recentProjects.isEmpty {
                recentProjectsList
            }

            Spacer()

            LanguageSwitcher()
                .padding(.bottom, 24)
        }
        .padding()
        .fileImporter(isPresented: $showFilePicker, allowedContentTypes: [.movie, .video, .mpeg4Movie]) { result in
            if case .success(let url) = result {
                startWithVideo(url: url)
            }
        }
        .onChange(of: selectedItem) { _, newItem in
            Task {
                if let newItem, let url = await loadVideoURL(from: newItem) {
                    startWithVideo(url: url)
                }
            }
        }
        .onAppear {
            recentProjects = ProjectStore.shared.recentProjects
        }
    }

    private var recentProjectsList: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(String(localized: "welcome.recent"))
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.top, 32)

            ForEach(recentProjects.prefix(5)) { project in
                Button {
                    startWithVideo(url: project.videoURL)
                } label: {
                    HStack {
                        Image(systemName: "film")
                        Text(project.name)
                            .lineLimit(1)
                        Spacer()
                        Text(project.dateString)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    .padding(.vertical, 4)
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: 300)
    }

    private func startWithVideo(url: URL) {
        navigationState.videoURL = url
        navigationState.screen = .analysis
        ProjectStore.shared.addRecent(url: url)
    }

    private func loadVideoURL(from item: PhotosPickerItem) async -> URL? {
        guard let data = try? await item.loadTransferable(type: Data.self) else { return nil }
        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".mp4")
        try? data.write(to: tempURL)
        return tempURL
    }
}

struct LanguageSwitcher: View {
    @Bindable private var manager = LocalizationManager.shared

    var body: some View {
        HStack(spacing: 8) {
            ForEach(AppLanguage.allCases, id: \.self) { lang in
                Button(lang.displayName) {
                    manager.language = lang
                }
                .buttonStyle(.bordered)
                .tint(manager.language == lang ? .green : .gray)
                .controlSize(.small)
            }
        }
    }
}
