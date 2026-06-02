import Foundation
import AVFoundation

/// Extracts raw PCM audio samples from a video file using AVAssetReader.
struct AudioExtractor {
    struct AudioData {
        let samples: [Float]
        let sampleRate: Double
    }

    /// Extract mono PCM float audio from the given video URL.
    static func extract(from videoURL: URL) async throws -> AudioData {
        let asset = AVURLAsset(url: videoURL)
        guard let audioTrack = try await asset.loadTracks(withMediaType: .audio).first else {
            throw AnalysisError.noAudioTrack
        }

        let outputSettings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVLinearPCMBitDepthKey: 32,
            AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false,
            AVSampleRateKey: 22050,
            AVNumberOfChannelsKey: 1,
        ]

        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(track: audioTrack, outputSettings: outputSettings)
        output.alwaysCopiesSampleData = false
        reader.add(output)

        guard reader.startReading() else {
            throw AnalysisError.audioReadFailed(reader.error?.localizedDescription ?? "Unknown")
        }

        var samples: [Float] = []
        while let buffer = output.copyNextSampleBuffer(),
              let blockBuffer = CMSampleBufferGetDataBuffer(buffer) {
            var length = 0
            var dataPointer: UnsafeMutablePointer<Int8>?
            CMBlockBufferGetDataPointer(blockBuffer, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length, dataPointerOut: &dataPointer)

            if let dataPointer {
                let floatCount = length / MemoryLayout<Float>.size
                let floatPointer = UnsafeRawPointer(dataPointer).bindMemory(to: Float.self, capacity: floatCount)
                samples.append(contentsOf: UnsafeBufferPointer(start: floatPointer, count: floatCount))
            }
        }

        if reader.status == .failed {
            throw AnalysisError.audioReadFailed(reader.error?.localizedDescription ?? "Unknown")
        }

        return AudioData(samples: samples, sampleRate: 22050)
    }
}

enum AnalysisError: LocalizedError {
    case noAudioTrack
    case audioReadFailed(String)
    case cancelled

    var errorDescription: String? {
        switch self {
        case .noAudioTrack:
            return "No audio track found in video"
        case .audioReadFailed(let detail):
            return "Audio extraction failed: \(detail)"
        case .cancelled:
            return "Analysis was cancelled"
        }
    }
}
