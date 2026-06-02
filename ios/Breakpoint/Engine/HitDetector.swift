import Foundation
import Accelerate

/// Detects ball hit events from audio using spectral flux onset detection.
/// Port of engine/audio/detect_hits.py using Accelerate/vDSP.
struct HitDetector {
    struct HitEvent {
        let time: Double
        let energy: Double
    }

    /// Parameters matching the Python engine defaults.
    struct Parameters {
        var hopLength: Int = 512
        var nFFT: Int = 2048
        var prePeakDistance: Int = 5
        var peakThresholdMultiplier: Float = 1.5
        var minEnergy: Float = 0.01
    }

    /// Detect hits from PCM audio samples.
    static func detect(
        samples: [Float],
        sampleRate: Double,
        parameters: Parameters = Parameters()
    ) -> [HitEvent] {
        let spectralFlux = computeSpectralFlux(
            samples: samples,
            nFFT: parameters.nFFT,
            hopLength: parameters.hopLength
        )

        let peaks = pickPeaks(
            flux: spectralFlux,
            distance: parameters.prePeakDistance,
            thresholdMultiplier: parameters.peakThresholdMultiplier,
            minEnergy: parameters.minEnergy
        )

        let hopDuration = Double(parameters.hopLength) / sampleRate
        return peaks.map { index in
            HitEvent(
                time: Double(index) * hopDuration,
                energy: Double(spectralFlux[index])
            )
        }
    }

    /// Compute Short-Time Fourier Transform magnitude difference (spectral flux).
    private static func computeSpectralFlux(samples: [Float], nFFT: Int, hopLength: Int) -> [Float] {
        let frameCount = max(0, (samples.count - nFFT) / hopLength + 1)
        guard frameCount > 1 else { return [] }

        let halfN = nFFT / 2 + 1
        var flux = [Float](repeating: 0, count: frameCount)

        let log2n = vDSP_Length(log2(Double(nFFT)))
        guard let fftSetup = vDSP_create_fftsetup(log2n, FFTRadix(kFFTRadix2)) else {
            return []
        }
        defer { vDSP_destroy_fftsetup(fftSetup) }

        var window = [Float](repeating: 0, count: nFFT)
        vDSP_hann_window(&window, vDSP_Length(nFFT), Int32(vDSP_HANN_NORM))

        var prevMagnitudes = [Float](repeating: 0, count: halfN)
        var real = [Float](repeating: 0, count: halfN)
        var imag = [Float](repeating: 0, count: halfN)
        var frame = [Float](repeating: 0, count: nFFT)

        for i in 0..<frameCount {
            let start = i * hopLength
            let end = min(start + nFFT, samples.count)
            let available = end - start

            frame = [Float](repeating: 0, count: nFFT)
            frame.replaceSubrange(0..<available, with: samples[start..<end])

            // Apply window
            vDSP_vmul(frame, 1, window, 1, &frame, 1, vDSP_Length(nFFT))

            // FFT
            frame.withUnsafeMutableBufferPointer { framePtr in
                real.withUnsafeMutableBufferPointer { realPtr in
                    imag.withUnsafeMutableBufferPointer { imagPtr in
                        var splitComplex = DSPSplitComplex(
                            realp: realPtr.baseAddress!,
                            imagp: imagPtr.baseAddress!
                        )
                        framePtr.baseAddress!.withMemoryRebound(to: DSPComplex.self, capacity: halfN) { complexPtr in
                            vDSP_ctoz(complexPtr, 2, &splitComplex, 1, vDSP_Length(halfN))
                        }
                        vDSP_fft_zrip(fftSetup, &splitComplex, 1, log2n, FFTDirection(FFT_FORWARD))
                    }
                }
            }

            // Compute magnitudes
            var magnitudes = [Float](repeating: 0, count: halfN)
            real.withUnsafeBufferPointer { realPtr in
                imag.withUnsafeBufferPointer { imagPtr in
                    var splitComplex = DSPSplitComplex(
                        realp: UnsafeMutablePointer(mutating: realPtr.baseAddress!),
                        imagp: UnsafeMutablePointer(mutating: imagPtr.baseAddress!)
                    )
                    vDSP_zvmags(&splitComplex, 1, &magnitudes, 1, vDSP_Length(halfN))
                }
            }
            // Square root for actual magnitudes
            var count = Int32(halfN)
            vvsqrtf(&magnitudes, magnitudes, &count)

            // Spectral flux: sum of positive differences
            if i > 0 {
                var diff = [Float](repeating: 0, count: halfN)
                vDSP_vsub(prevMagnitudes, 1, magnitudes, 1, &diff, 1, vDSP_Length(halfN))
                // Half-wave rectification: keep only positive
                var zero: Float = 0
                vDSP_vthres(diff, 1, &zero, &diff, 1, vDSP_Length(halfN))
                // Sum
                var sum: Float = 0
                vDSP_sve(diff, 1, &sum, vDSP_Length(halfN))
                flux[i] = sum
            }

            prevMagnitudes = magnitudes
        }

        return flux
    }

    /// Adaptive peak picking with local threshold.
    private static func pickPeaks(
        flux: [Float],
        distance: Int,
        thresholdMultiplier: Float,
        minEnergy: Float
    ) -> [Int] {
        guard flux.count > 2 * distance else { return [] }

        var peaks: [Int] = []
        let windowSize = distance * 2 + 1

        for i in distance..<(flux.count - distance) {
            let value = flux[i]
            guard value > minEnergy else { continue }

            // Check if local maximum
            let start = i - distance
            let end = i + distance + 1
            let window = Array(flux[start..<min(end, flux.count)])
            var maxVal: Float = 0
            vDSP_maxv(window, 1, &maxVal, vDSP_Length(window.count))
            guard value >= maxVal else { continue }

            // Adaptive threshold: mean of local window * multiplier
            var mean: Float = 0
            let adaptiveStart = max(0, i - windowSize)
            let adaptiveEnd = min(flux.count, i + windowSize)
            let adaptiveSlice = Array(flux[adaptiveStart..<adaptiveEnd])
            vDSP_meanv(adaptiveSlice, 1, &mean, vDSP_Length(adaptiveSlice.count))

            if value > mean * thresholdMultiplier {
                // Ensure minimum distance from last peak
                if let lastPeak = peaks.last, i - lastPeak < distance {
                    if value > flux[lastPeak] {
                        peaks[peaks.count - 1] = i
                    }
                } else {
                    peaks.append(i)
                }
            }
        }

        return peaks
    }
}
