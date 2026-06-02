import XCTest
@testable import BreakpointEngine

final class SegmentationTests: XCTestCase {
    func testBasicSegmentation() {
        // Simulate hits every ~2s with a 7s gap creating two segments
        let hitTimes: [Double] = [1, 2.5, 4, 5.5, 7,     // segment 1: 5 hits
                                   14, 15.5, 17, 18.5, 20] // segment 2: 5 hits (gap=7s > 6s)
        let hitEnergies = [Double](repeating: 0.5, count: hitTimes.count)

        let segments = Segmentation.segment(hitTimes: hitTimes, hitEnergies: hitEnergies)

        XCTAssertEqual(segments.count, 2)
        XCTAssertEqual(segments[0].hitTimes.count, 5)
        XCTAssertEqual(segments[1].hitTimes.count, 5)
    }

    func testMinHitsFilter() {
        // Only 2 hits — should be filtered out (min is 3)
        let hitTimes: [Double] = [1, 3]
        let hitEnergies: [Double] = [0.5, 0.5]

        let segments = Segmentation.segment(hitTimes: hitTimes, hitEnergies: hitEnergies)
        XCTAssertTrue(segments.isEmpty)
    }

    func testDurationFilter() {
        // Hits too close together (< 3s duration after buffer)
        let hitTimes: [Double] = [10, 10.5, 11]
        let hitEnergies: [Double] = [0.5, 0.5, 0.5]

        let params = Segmentation.Parameters(buffer: 0.5, minDuration: 5.0)
        let segments = Segmentation.segment(hitTimes: hitTimes, hitEnergies: hitEnergies, parameters: params)
        XCTAssertTrue(segments.isEmpty)
    }

    func testBufferApplication() {
        let hitTimes: [Double] = [10, 12, 14, 16, 18]
        let hitEnergies = [Double](repeating: 0.5, count: 5)

        let params = Segmentation.Parameters(buffer: 2.0)
        let segments = Segmentation.segment(hitTimes: hitTimes, hitEnergies: hitEnergies, parameters: params)

        XCTAssertEqual(segments.count, 1)
        XCTAssertEqual(segments[0].start, 8.0) // 10 - 2.0
        XCTAssertEqual(segments[0].end, 20.0)  // 18 + 2.0
    }
}

final class RankingTests: XCTestCase {
    func testRankingOrder() {
        let segments: [Segmentation.RawSegment] = [
            .init(start: 0, end: 10, hitTimes: [1, 2, 3], hitEnergies: [0.2, 0.2, 0.2]),
            .init(start: 20, end: 35, hitTimes: Array(stride(from: 21.0, to: 34.0, by: 1.0)),
                  hitEnergies: [Double](repeating: 0.8, count: 13)),
        ]

        let rallies = Ranking.rank(segments: segments)

        XCTAssertEqual(rallies.count, 2)
        // Second segment has more hits + higher energy → higher score
        XCTAssertGreaterThan(rallies[0].score, rallies[1].score)
    }

    func testAutoInclude() {
        let rallies = [
            Rally(id: 1, start: 0, end: 10, score: 0.8, features: .init(hitCount: 5, avgEnergy: 0.5, motionScore: nil)),
            Rally(id: 2, start: 20, end: 30, score: 0.5, features: .init(hitCount: 4, avgEnergy: 0.4, motionScore: nil)),
            Rally(id: 3, start: 40, end: 50, score: 0.2, features: .init(hitCount: 3, avgEnergy: 0.3, motionScore: nil)),
        ]

        let result = applyAutoInclude(rallies)

        XCTAssertTrue(result[0].included)  // highlight tier
        XCTAssertTrue(result[1].included)  // keep tier
        XCTAssertFalse(result[2].included) // cut tier
    }
}

final class HitDetectorTests: XCTestCase {
    func testEmptyInput() {
        let hits = HitDetector.detect(samples: [], sampleRate: 22050)
        XCTAssertTrue(hits.isEmpty)
    }

    func testShortInput() {
        // Too short for any meaningful FFT
        let hits = HitDetector.detect(samples: [Float](repeating: 0, count: 100), sampleRate: 22050)
        XCTAssertTrue(hits.isEmpty)
    }
}
