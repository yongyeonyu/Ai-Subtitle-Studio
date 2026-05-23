import Foundation

public enum SubtitleWaveformSummaryNative {
    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        let waveform = floatArray(payload["waveform"])
        let duration = doubleValue(payload["duration"], default: 0.0)
        let threshold = max(0.0, doubleValue(payload["speech_threshold"], default: 0.02))

        var maxPeak = 0.0
        var sumPeak = 0.0
        var speechLikeCount = 0
        for value in waveform {
            let peak = Double(abs(value.isFinite ? value : 0.0))
            if peak > maxPeak {
                maxPeak = peak
            }
            sumPeak += peak
            if peak >= threshold {
                speechLikeCount += 1
            }
        }

        let count = waveform.count
        let meanPeak = count > 0 ? sumPeak / Double(count) : 0.0
        let speechRatio = count > 0 ? Double(speechLikeCount) / Double(count) : 0.0
        return [
            "schema": "ai_subtitle_studio.subtitle_waveform.summary.v1",
            "backend": "swift",
            "sample_count": count,
            "duration": duration,
            "max_peak": round6(maxPeak),
            "mean_peak": round6(meanPeak),
            "speech_like_count": speechLikeCount,
            "speech_like_ratio": round6(speechRatio),
            "accelerator_summary": [
                "compute_task": "subtitle_waveform",
                "swift_vector_summary": true,
                "accelerate_candidate": true,
                "gpu_task_count": 0,
                "ane_task_count": 0,
                "metal_task_count": 0,
                "metal_claims_ane": false,
            ],
        ]
    }

    private static func floatArray(_ value: Any?) -> [Float] {
        if let numbers = value as? [NSNumber] {
            return numbers.map { $0.floatValue }
        }
        guard let values = value as? [Any] else {
            return []
        }
        var out: [Float] = []
        out.reserveCapacity(values.count)
        for item in values {
            if let number = item as? NSNumber {
                out.append(number.floatValue)
            } else if let text = item as? String, let number = Float(text) {
                out.append(number)
            }
        }
        return out
    }

    private static func doubleValue(_ value: Any?, default fallback: Double) -> Double {
        if let number = value as? NSNumber {
            return number.doubleValue
        }
        if let text = value as? String, let number = Double(text) {
            return number
        }
        return fallback
    }

    private static func round6(_ value: Double) -> Double {
        guard value.isFinite else { return 0.0 }
        return (value * 1_000_000.0).rounded() / 1_000_000.0
    }
}
