import SwiftUI
import AVKit

struct VideoPlayerView: UIViewControllerRepresentable {
    let videoURL: URL
    var seekTarget: Double?
    var pauseAt: Double?
    var onTimeUpdate: (Double) -> Void
    var onDurationChange: (Double) -> Void

    func makeUIViewController(context: Context) -> AVPlayerViewController {
        let controller = AVPlayerViewController()
        let player = AVPlayer(url: videoURL)
        controller.player = player
        controller.showsPlaybackControls = true

        // Time observer
        let interval = CMTime(seconds: 0.1, preferredTimescale: 600)
        player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { time in
            let seconds = CMTimeGetSeconds(time)
            guard seconds.isFinite else { return }
            onTimeUpdate(seconds)

            // Pause at boundary if set
            if let pauseAt, seconds >= pauseAt {
                player.pause()
            }
        }

        // Duration
        Task {
            if let duration = try? await player.currentItem?.asset.load(.duration) {
                let seconds = CMTimeGetSeconds(duration)
                if seconds.isFinite {
                    await MainActor.run { onDurationChange(seconds) }
                }
            }
        }

        return controller
    }

    func updateUIViewController(_ controller: AVPlayerViewController, context: Context) {
        if let seekTarget {
            let time = CMTime(seconds: seekTarget, preferredTimescale: 600)
            controller.player?.seek(to: time, toleranceBefore: .zero, toleranceAfter: .zero)
        }
    }
}
