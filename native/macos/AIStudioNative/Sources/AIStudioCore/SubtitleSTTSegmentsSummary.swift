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
        var timelineFeedSignature = TimelineFeedSignature()
        var stt2FirstStart: Double?
        var stt2LastEnd: Double?
        var currentSTT2RunStart: Double?
        var currentSTT2RunEnd: Double?
        var currentSTT2RunCount = 0
        var longestSTT2RunSec = 0.0
        var longestSTT2RunStart = 0.0
        var longestSTT2RunEnd = 0.0
        var longestSTT2RunCount = 0

        func flushSTT2Run() {
            guard let runStart = currentSTT2RunStart, let runEnd = currentSTT2RunEnd else {
                return
            }
            let runSec = max(0.0, runEnd - runStart)
            if runSec > longestSTT2RunSec || (abs(runSec - longestSTT2RunSec) <= 0.000_000_001 && currentSTT2RunCount > longestSTT2RunCount) {
                longestSTT2RunSec = runSec
                longestSTT2RunStart = runStart
                longestSTT2RunEnd = runEnd
                longestSTT2RunCount = currentSTT2RunCount
            }
            currentSTT2RunStart = nil
            currentSTT2RunEnd = nil
            currentSTT2RunCount = 0
        }

        for segment in segments {
            let start = doubleValue(segment["start"], default: 0.0)
            let end = doubleValue(segment["end"], default: start)
            let duration = max(0.0, end - start)
            let source = canonicalSource(segment)
            let sourceCode = sourceCode(source)
            let isSTT2Source = source == "STT2" || source == "RECHECK"
            let recheckApplied = boolValue(segment["stt_recheck_applied"])
            let wordPrecisionApplied = boolValue(segment["stt_word_precision_applied"])
            let secondaryHintApplied = boolValue(segment["stt_route_secondary_recheck_hint"])
            count += 1
            // 변경 금지: STT1/STT2 후보 lane과 timeline/editor feed가 같은 입력인지 증명하는 네이티브 계약입니다.
            // C++/Python fallback과 같은 값 순서와 millisecond 반올림을 유지해야 싱크 드리프트를 재현 없이 잡을 수 있습니다.
            timelineFeedSignature.combine(milliseconds(start))
            timelineFeedSignature.combine(milliseconds(end))
            timelineFeedSignature.combine(Int64(sourceCode))
            timelineFeedSignature.combine(recheckApplied ? 1 : 0)
            timelineFeedSignature.combine(wordPrecisionApplied ? 1 : 0)
            timelineFeedSignature.combine(secondaryHintApplied ? 1 : 0)

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

            // 변경 금지: 이 값은 STT2 정책을 넓히는 스위치가 아니라 X5/Macau 자막-에디터 싱크 원인 추적용 진단 계약입니다.
            // STT2/RECHECK가 연속 선택된 구간만 run으로 묶어 Swift/C++/Python fallback과 벤치마크 artifact가 같은 사실을 기록합니다.
            if isSTT2Source {
                if stt2FirstStart == nil {
                    stt2FirstStart = start
                }
                stt2LastEnd = max(stt2LastEnd ?? end, end)
                if currentSTT2RunStart == nil {
                    currentSTT2RunStart = start
                    currentSTT2RunEnd = end
                    currentSTT2RunCount = 1
                } else {
                    currentSTT2RunEnd = max(currentSTT2RunEnd ?? end, end)
                    currentSTT2RunCount += 1
                }
            } else {
                flushSTT2Run()
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

            if recheckApplied {
                recheckAppliedCount += 1
            }
            if wordPrecisionApplied {
                wordPrecisionCount += 1
            }
            if secondaryHintApplied {
                secondaryHintCount += 1
            }
            if !previousSource.isEmpty && !source.isEmpty && previousSource != source {
                sourceSwitchCount += 1
            }

            previousStart = start
            previousEnd = end
            previousSource = source
        }
        flushSTT2Run()

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
            "stt2_first_start": round6(stt2FirstStart ?? 0.0),
            "stt2_last_end": round6(stt2LastEnd ?? 0.0),
            "longest_stt2_run_sec": round6(longestSTT2RunSec),
            "longest_stt2_run_start": round6(longestSTT2RunStart),
            "longest_stt2_run_end": round6(longestSTT2RunEnd),
            "longest_stt2_run_count": longestSTT2RunCount,
            "stt2_active": stt2SelectedCount > 0 || recheckAppliedCount > 0,
            "selective_recheck_active": recheckAppliedCount > 0,
            "stable_for_timeline_feed": invalidDurationCount == 0 && nonMonotonicCount == 0,
            "timeline_feed_signature": timelineFeedSignature.hexString,
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

    private static func sourceCode(_ source: String) -> Int {
        switch source {
        case "STT1":
            return 1
        case "STT2":
            return 2
        case "RECHECK":
            return 3
        default:
            return 0
        }
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

    private static func milliseconds(_ value: Double) -> Int64 {
        guard value.isFinite else { return 0 }
        return Int64((value * 1_000.0).rounded(.toNearestOrAwayFromZero))
    }
}

private struct TimelineFeedSignature {
    private var hash: UInt64 = 1_469_598_103_934_665_603
    private let prime: UInt64 = 1_099_511_628_211

    mutating func combine(_ value: Int64) {
        hash ^= UInt64(bitPattern: value)
        hash &*= prime
    }

    var hexString: String {
        String(format: "%016llx", hash)
    }
}
