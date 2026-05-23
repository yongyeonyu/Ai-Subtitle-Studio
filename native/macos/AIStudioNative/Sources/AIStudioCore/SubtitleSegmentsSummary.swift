import Foundation

public enum SubtitleSegmentsSummaryNative {
    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        let segments = (payload["segments"] as? [[String: Any]]) ?? []
        var count = 0
        var invalidDurationCount = 0
        var nonMonotonicCount = 0
        var overlapCount = 0
        var emptyTextCount = 0
        var totalDuration = 0.0
        var maxGap = 0.0
        var totalChars = 0
        var maxChars = 0
        var previousStart: Double?
        var previousEnd: Double?
        var firstStart: Double?
        var lastEnd: Double?

        for segment in segments {
            let start = doubleValue(segment["start"], default: 0.0)
            let end = doubleValue(segment["end"], default: start)
            let text = stringValue(segment["text"]).trimmingCharacters(in: .whitespacesAndNewlines)
            let chars = text.count
            count += 1
            totalChars += chars
            maxChars = max(maxChars, chars)
            if text.isEmpty {
                emptyTextCount += 1
            }
            if !(end > start) {
                invalidDurationCount += 1
            } else {
                totalDuration += end - start
            }
            if let previousStart, start < previousStart {
                nonMonotonicCount += 1
            }
            if let previousEnd {
                if start < previousEnd {
                    overlapCount += 1
                } else {
                    maxGap = max(maxGap, start - previousEnd)
                }
            }
            if firstStart == nil {
                firstStart = start
            }
            previousStart = start
            previousEnd = end
            lastEnd = end
        }

        let avgChars = count > 0 ? Double(totalChars) / Double(count) : 0.0
        return [
            "schema": "ai_subtitle_studio.subtitle_segments.summary.v1",
            "backend": "swift",
            "segment_count": count,
            "invalid_duration_count": invalidDurationCount,
            "non_monotonic_count": nonMonotonicCount,
            "overlap_count": overlapCount,
            "empty_text_count": emptyTextCount,
            "total_duration": round6(totalDuration),
            "first_start": round6(firstStart ?? 0.0),
            "last_end": round6(lastEnd ?? 0.0),
            "max_gap": round6(maxGap),
            "max_chars": maxChars,
            "avg_chars": round6(avgChars),
            "stable_for_save_reopen": invalidDurationCount == 0 && nonMonotonicCount == 0,
            "accelerator_summary": [
                "compute_task": "subtitle_segments",
                "swift_vector_summary": true,
                "gpu_task_count": 0,
                "ane_task_count": 0,
                "metal_task_count": 0,
                "metal_claims_ane": false,
            ],
        ]
    }

    private static func doubleValue(_ value: Any?, default fallback: Double) -> Double {
        if let number = value as? NSNumber {
            let out = number.doubleValue
            return out.isFinite ? out : fallback
        }
        if let text = value as? String, let number = Double(text), number.isFinite {
            return number
        }
        return fallback
    }

    private static func stringValue(_ value: Any?) -> String {
        guard let value else {
            return ""
        }
        return String(describing: value)
    }

    private static func round6(_ value: Double) -> Double {
        guard value.isFinite else { return 0.0 }
        return (value * 1_000_000.0).rounded() / 1_000_000.0
    }
}
