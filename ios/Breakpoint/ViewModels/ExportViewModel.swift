import Foundation
import AVFoundation
import Photos
import Observation

struct ExportResult: Equatable {
    let message: String
    let isError: Bool
    let outputURL: URL?
}

@Observable
class ExportViewModel {
    var progress: Double?
    var result: ExportResult?

    private var exportSession: AVAssetExportSession?

    func export(videoURL: URL, rallies: [Rally]) {
        let included = rallies.filter(\.included)
        guard !included.isEmpty else { return }

        progress = 0
        result = nil

        Task {
            do {
                let outputURL = try await compileHighlights(videoURL: videoURL, segments: included)
                await saveToPhotos(url: outputURL)
                await MainActor.run {
                    self.progress = nil
                    self.result = ExportResult(
                        message: String(localized: "export.complete"),
                        isError: false,
                        outputURL: outputURL
                    )
                }
            } catch {
                await MainActor.run {
                    self.progress = nil
                    self.result = ExportResult(
                        message: error.localizedDescription,
                        isError: true,
                        outputURL: nil
                    )
                }
            }
        }
    }

    func cancel() {
        exportSession?.cancelExport()
        exportSession = nil
        progress = nil
    }

    private func compileHighlights(videoURL: URL, segments: [Rally]) async throws -> URL {
        let asset = AVURLAsset(url: videoURL)
        let composition = AVMutableComposition()

        guard let videoTrack = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid),
              let audioTrack = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) else {
            throw ExportError.compositionFailed
        }

        let sourceVideoTracks = try await asset.loadTracks(withMediaType: .video)
        let sourceAudioTracks = try await asset.loadTracks(withMediaType: .audio)

        guard let sourceVideo = sourceVideoTracks.first else {
            throw ExportError.noVideoTrack
        }

        var insertTime = CMTime.zero

        let sorted = segments.sorted { $0.effectiveStart < $1.effectiveStart }
        for (i, segment) in sorted.enumerated() {
            let startTime = CMTime(seconds: segment.effectiveStart, preferredTimescale: 600)
            let endTime = CMTime(seconds: segment.effectiveEnd, preferredTimescale: 600)
            let timeRange = CMTimeRange(start: startTime, end: endTime)

            try videoTrack.insertTimeRange(timeRange, of: sourceVideo, at: insertTime)

            if let sourceAudio = sourceAudioTracks.first {
                try audioTrack.insertTimeRange(timeRange, of: sourceAudio, at: insertTime)
            }

            insertTime = CMTimeAdd(insertTime, CMTimeSubtract(endTime, startTime))

            await MainActor.run {
                self.progress = Double(i + 1) / Double(sorted.count)
            }
        }

        // Export
        let outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(videoURL.deletingPathExtension().lastPathComponent)_highlights.mp4")

        // Remove existing file
        try? FileManager.default.removeItem(at: outputURL)

        guard let session = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality) else {
            throw ExportError.exportSessionFailed
        }
        session.outputURL = outputURL
        session.outputFileType = .mp4
        exportSession = session

        await session.export()

        if session.status == .completed {
            return outputURL
        } else if session.status == .cancelled {
            throw AnalysisError.cancelled
        } else {
            throw ExportError.exportFailed(session.error?.localizedDescription ?? "Unknown")
        }
    }

    private func saveToPhotos(url: URL) async {
        let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard status == .authorized else { return }

        try? await PHPhotoLibrary.shared().performChanges {
            PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL: url)
        }
    }
}

enum ExportError: LocalizedError {
    case compositionFailed
    case noVideoTrack
    case exportSessionFailed
    case exportFailed(String)

    var errorDescription: String? {
        switch self {
        case .compositionFailed: return "Failed to create composition"
        case .noVideoTrack: return "No video track in source"
        case .exportSessionFailed: return "Failed to create export session"
        case .exportFailed(let detail): return "Export failed: \(detail)"
        }
    }
}
