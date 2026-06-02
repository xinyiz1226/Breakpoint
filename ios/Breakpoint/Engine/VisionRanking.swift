import Foundation
import Vision
import AVFoundation

/// Analyzes player motion intensity using Vision body pose detection.
/// Replaces the OpenCV optical flow approach from the desktop engine.
struct VisionRanking {
    /// Compute a motion score for a rally by analyzing body pose movement across frames.
    static func analyzeMotion(
        videoURL: URL,
        segment: Segmentation.RawSegment,
        samplesPerSegment: Int = 10
    ) async throws -> Double {
        let asset = AVURLAsset(url: videoURL)
        let generator = AVAssetImageGenerator(asset: asset)
        generator.requestedTimeToleranceBefore = CMTime(seconds: 0.1, preferredTimescale: 600)
        generator.requestedTimeToleranceAfter = CMTime(seconds: 0.1, preferredTimescale: 600)
        generator.appliesPreferredTrackTransform = true

        let duration = segment.end - segment.start
        let step = duration / Double(samplesPerSegment + 1)

        var previousPoints: [VNHumanBodyPoseObservation.JointName: CGPoint] = [:]
        var totalMotion: Double = 0
        var frameCount = 0

        for i in 1...samplesPerSegment {
            let time = CMTime(seconds: segment.start + step * Double(i), preferredTimescale: 600)

            let (cgImage, _) = try await generator.image(at: time)

            let request = VNDetectHumanBodyPoseRequest()
            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            try handler.perform([request])

            guard let observation = request.results?.first else { continue }

            let jointNames: [VNHumanBodyPoseObservation.JointName] = [
                .leftAnkle, .rightAnkle, .leftWrist, .rightWrist,
                .leftHip, .rightHip, .leftShoulder, .rightShoulder
            ]

            var currentPoints: [VNHumanBodyPoseObservation.JointName: CGPoint] = [:]
            for joint in jointNames {
                if let point = try? observation.recognizedPoint(joint),
                   point.confidence > 0.3 {
                    currentPoints[joint] = point.location
                }
            }

            if !previousPoints.isEmpty {
                var frameMotion: Double = 0
                var matchedJoints = 0
                for (joint, currentPos) in currentPoints {
                    if let prevPos = previousPoints[joint] {
                        let dx = Double(currentPos.x - prevPos.x)
                        let dy = Double(currentPos.y - prevPos.y)
                        frameMotion += sqrt(dx * dx + dy * dy)
                        matchedJoints += 1
                    }
                }
                if matchedJoints > 0 {
                    totalMotion += frameMotion / Double(matchedJoints)
                    frameCount += 1
                }
            }

            previousPoints = currentPoints
        }

        return frameCount > 0 ? totalMotion / Double(frameCount) : 0
    }
}
