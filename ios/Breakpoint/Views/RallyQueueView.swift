import SwiftUI

struct RallyQueueView: View {
    @Binding var rallies: [Rally]
    let currentTime: Double
    let onSeek: (Double) -> Void
    let onSeekAndPlay: (Double) -> Void
    let onExport: () -> Void
    let exportProgress: Double?
    let exportResult: ExportResult?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            rallyList
            Divider()
            exportBar
        }
        .background(Color(.secondarySystemBackground))
    }

    private var header: some View {
        HStack {
            Text(String(localized: "queue.title"))
                .font(.system(size: 13, weight: .bold))

            Spacer()

            let included = rallies.filter(\.included).count
            Text("\(included)/\(rallies.count)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private var rallyList: some View {
        ScrollView {
            LazyVStack(spacing: 4) {
                ForEach(Array(rallies.enumerated()), id: \.element.id) { index, rally in
                    RallyRow(
                        rally: rally,
                        isActive: currentTime >= rally.effectiveStart && currentTime <= rally.effectiveEnd,
                        onTap: { onSeekAndPlay(rally.effectiveStart) },
                        onToggle: { rallies[index].included.toggle() }
                    )
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
        }
    }

    private var exportBar: some View {
        VStack(spacing: 8) {
            if let progress = exportProgress {
                ProgressView(value: progress)
                    .progressViewStyle(.linear)
                    .padding(.horizontal, 12)
            }

            if let result = exportResult {
                Text(result.message)
                    .font(.caption)
                    .foregroundStyle(result.isError ? .red : .green)
            }

            Button {
                onExport()
            } label: {
                Label(String(localized: "queue.export"), systemImage: "square.and.arrow.up")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(.green)
            .disabled(rallies.filter(\.included).isEmpty || exportProgress != nil)
            .padding(.horizontal, 12)
            .padding(.bottom, 12)
        }
        .padding(.top, 8)
    }
}

struct RallyRow: View {
    let rally: Rally
    let isActive: Bool
    let onTap: () -> Void
    let onToggle: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Button(action: onToggle) {
                Image(systemName: rally.included ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(rally.included ? .green : .secondary)
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text("#\(rally.id)")
                        .font(.system(size: 12, weight: .bold, design: .monospaced))
                    tierBadge
                }
                Text(formatTimeRange(rally.effectiveStart, rally.effectiveEnd))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Text(String(format: "%.0f%%", rally.score * 100))
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(isActive ? Color.green.opacity(0.1) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .contentShape(Rectangle())
        .onTapGesture { onTap() }
    }

    private var tierBadge: some View {
        Text(rally.tier.rawValue.uppercased())
            .font(.system(size: 9, weight: .bold))
            .padding(.horizontal, 4)
            .padding(.vertical, 1)
            .background(tierColor.opacity(0.2))
            .foregroundStyle(tierColor)
            .clipShape(Capsule())
    }

    private var tierColor: Color {
        switch rally.tier {
        case .highlight: .orange
        case .keep: .green
        case .cut: .gray
        }
    }

    private func formatTimeRange(_ start: Double, _ end: Double) -> String {
        "\(formatTime(start)) – \(formatTime(end))"
    }

    private func formatTime(_ seconds: Double) -> String {
        let m = Int(seconds) / 60
        let s = Int(seconds) % 60
        return String(format: "%d:%02d", m, s)
    }
}
