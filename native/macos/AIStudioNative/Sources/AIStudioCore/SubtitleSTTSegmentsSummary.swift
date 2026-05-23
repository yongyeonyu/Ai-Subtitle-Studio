import Foundation

public enum SubtitleSTTSegmentsSummaryNative {
    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        let segments = (payload["segments"] as? [[String: Any]]) ?? []
        var count = 0
        var stt1SelectedCount = 0
        var stt2SelectedCount = 0
        var recheckAppliedCount = 0
        var wordPrecisionCount = 0
        var secondaryHintCount = 0
        var unknownSourceCount = 0
        var invalidDurationCount = 0
        var nonMonotonicCount = 0
        var overlapCount = 0
        var sourceSwitchCount = 0
        var totalDuration = 0.0
        var stt1Duration = 0.0
        var stt2Duration = 0.0
        var previousStart: Double?
        var previousEnd: Double?
        var previousSource = ""

        for segment in segments {
            let start = doubleValue(segment["start"], default: 0.0)
            let end = doubleValue(segment["end"], default: start)
            let duration = max(0.0, end - start)
            let source = canonicalSource(segment)
            count += 1

            if !(end > start) {
                invalidDurationCount += 1
            } else {
                totalDuration += duration
            }
            if let previousStart, start < previousStart {
                nonMonotonicCount += 1
            }
            if let previousEnd, start < previousEnd {
                overlapCount += 1
            }

            switch source {
            case "STT2", "RECHECK":
                stt2SelectedCount += 1
                stt2Duration += duration
            case "STT1":
                stt1SelectedCount += 1
                stt1Duration += duration
            default:
                unknownSourceCount += 1
            }

            if boolValue(segment["stt_recheck_applied"]) {
                recheckAppliedCount += 1
            }
            if boolValue(segment["stt_word_precision_applied"]) {
                wordPrecisionCount += 1
            }
            if boolValue(segment["stt_route_secondary_recheck_hint"]) {
                secondaryHintCount += 1
            }
            if !previousSource.isEmpty && !source.isEmpty && previousSource != source {
                sourceSwitchCount += 1
            }

            previousStart = start
            previousEnd = end
            previousSource = source
        }

        let stt2CoverageRatio = totalDuration > 0.0 ? stt2Duration / totalDuration : 0.0
        return [
            "schema": "ai_subtitle_studio.subtitle_stt_segments.summary.v1",
            "backend": "swift",
            "segment_count": count,
            "stt1_selected_count": stt1SelectedCount,
            "stt2_selected_count": stt2SelectedCount,
            "recheck_applied_count": recheckAppliedCount,
            "word_precision_count": wordPrecisionCount,
            "secondary_hint_count": secondaryHintCount,
            "unknown_source_count": unknownSourceCount,
            "invalid_duration_count": invalidDurationCount,
            "non_monotonic_count": nonMonotonicCount,
            "overlap_count": overlapCount,
            "source_switch_count": sourceSwitchCount,
            "total_duration": round6(totalDuration),
            "stt1_duration": round6(stt1Duration),
            "stt2_duration": round6(stt2Duration),
            "stt2_coverage_ratio": round6(stt2CoverageRatio),
            "stt2_active": stt2SelectedCount > 0 || recheckAppliedCount > 0,
            "selective_recheck_active": recheckAppliedCount > 0,
            "stable_for_timeline_feed": invalidDurationCount == 0 && nonMonotonicCount == 0,
            "accelerator_summary": [
                "compute_task": "subtitle_stt_segments",
                "swift_vector_summary": true,
                "gpu_task_count": 0,
                "ane_task_count": 0,
                "metal_task_count": 0,
                "metal_claims_ane": false,
            ],
        ]
    }

    private static func canonicalSource(_ segment: [String: Any]) -> String {
        let keys = ["stt_selected_source", "stt_source", "stt_preview_source", "stt_ensemble_source", "source"]
        for key in keys {
            let source = stringValue(segment[key]).trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
            if source.contains("STT2") {
                return "STT2"
            }
            if source.contains("RECHECK") {
                return "RECHECK"
            }
            if source.contains("STT1") {
                return "STT1"
            }
        }
        return ""
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

    private static func boolValue(_ value: Any?) -> Bool {
        if let value = value as? Bool {
            return value
        }
        if let number = value as? NSNumber {
            return number.boolValue
        }
        let text = stringValue(value).trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return ["1", "true", "yes", "y", "on"].contains(text)
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
