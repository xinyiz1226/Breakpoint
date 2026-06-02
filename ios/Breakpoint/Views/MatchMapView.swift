import SwiftUI

struct MatchMapView: View {
    let rallies: [Rally]
    let duration: Double
    let currentTime: Double
    let onSeek: (Double) -> Void

    var body: some View {
        GeometryReader { geo in
            let width = geo.size.width
            let height = geo.size.height

            ZStack(alignment: .leading) {
                // Background track
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.tertiarySystemFill))

                // Rally segments
                ForEach(rallies) { rally in
                    let x = duration > 0 ? (rally.effectiveStart / duration) * width : 0
                    let w = duration > 0 ? max(2, ((rally.effectiveEnd - rally.effectiveStart) / duration) * width) : 2

                    RoundedRectangle(cornerRadius: 2)
                        .fill(colorForTier(rally.tier))
                        .frame(width: w, height: height * 0.6)
                        .offset(x: x)
                        .onTapGesture {
                            onSeek(rally.effectiveStart)
                        }
                }

                // Playhead
                if duration > 0 {
                    let playheadX = (currentTime / duration) * width
                    Rectangle()
                        .fill(Color.primary)
                        .frame(width: 2, height: height)
                        .offset(x: playheadX)
                }
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        let fraction = max(0, min(1, value.location.x / width))
                        onSeek(fraction * duration)
                    }
            )
        }
    }

    private func colorForTier(_ tier: Rally.Tier) -> Color {
        switch tier {
        case .highlight: .orange
        case .keep: .green
        case .cut: .gray.opacity(0.5)
        }
    }
}
