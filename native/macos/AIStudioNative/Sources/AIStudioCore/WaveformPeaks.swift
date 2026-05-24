import Foundation
import Accelerate

public struct WaveformPeakResult: Codable, Equatable, Sendable {
    public var waveform: [Float]
    public var duration: Double

    public init(waveform: [Float], duration: Double) {
        self.waveform = waveform
        self.duration = duration
    }
}

public enum WaveformPeaks {
    public static func downsampleF32LE(
        _ data: Data,
        sampleRate: Int = 2_000,
        pointsPerSecond: Int = 100,
        duration: Double? = nil
    ) -> WaveformPeakResult {
        let samples = decodeF32LE(data)
        return downsample(samples, sampleRate: sampleRate, pointsPerSecond: pointsPerSecond, duration: duration)
    }

    public static func decodeF32LE(_ data: Data) -> [Float] {
        guard data.count >= 4 else { return [] }
        let count = data.count / 4
        return data.withUnsafeBytes { rawBuffer in
            guard let base = rawBuffer.bindMemory(to: UInt8.self).baseAddress else { return [] }
            var out: [Float] = []
            out.reserveCapacity(count)
            for index in 0..<count {
                let offset = index * 4
                let bits = UInt32(base[offset])
                    | (UInt32(base[offset + 1]) << 8)
                    | (UInt32(base[offset + 2]) << 16)
                    | (UInt32(base[offset + 3]) << 24)
                let value = Float(bitPattern: bits)
                out.append(value.isFinite ? value : 0)
            }
            return out
        }
    }

    public static func downsample(
        _ samples: [Float],
        sampleRate: Int = 2_000,
        pointsPerSecond: Int = 100,
        duration: Double? = nil
    ) -> WaveformPeakResult {
        guard samples.count >= 2, sampleRate > 0, pointsPerSecond > 0 else {
            return WaveformPeakResult(waveform: [], duration: 0)
        }

        var dur = duration ?? 0
        if dur <= 0 {
            dur = Double(samples.count) / Double(sampleRate)
        }
        let totalPoints = max(1, Int(dur * Double(pointsPerSecond)))
        let chunk = max(1, samples.count / totalPoints)
        let trimmedCount = (samples.count / chunk) * chunk
        guard trimmedCount > 0 else {
            return WaveformPeakResult(waveform: [], duration: 0)
        }

        var peaks: [Float] = []
        peaks.reserveCapacity(min(totalPoints, trimmedCount / chunk))
        var cursor = 0
        while cursor + chunk <= trimmedCount && peaks.count < totalPoints {
            let end = cursor + chunk
            // 변경 금지: waveform downsample은 timeline UI를 바꾸지 않는 순수
            // compute hot path다. Swift native 경로에서는 Accelerate/vDSP로
            // chunk 절대 피크만 계산하고, 정규화/길이 계약은 Python/C++와
            // 동일하게 유지해야 한다.
            let peak = vDSP.maximumMagnitude(samples[cursor..<end])
            peaks.append(peak)
            cursor = end
        }

        if let maxPeak = peaks.max(), maxPeak > 0.000001 {
            peaks = peaks.map { $0 / maxPeak }
        }

        return WaveformPeakResult(waveform: peaks, duration: dur)
    }
}
