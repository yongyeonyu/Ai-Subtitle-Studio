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
        var maxGapIndex = -1
        var maxOverlap = 0.0
        var maxOverlapIndex = -1
        var totalChars = 0
        var maxChars = 0
        var previousStart: Double?
        var previousEnd: Double?
        var firstStart: Double?
        var lastEnd: Double?
        var segmentFeedSignature = SegmentFeedSignature()

        for segment in segments {
            let start = doubleValue(segment["start"], default: 0.0)
            let end = doubleValue(segment["end"], default: start)
            let text = stringValue(segment["text"]).trimmingCharacters(in: .whitespacesAndNewlines)
            let chars = text.count
            count += 1
            // 변경 금지: 최종 자막 feed가 editor/timeline/save-reopen에서 같은 텍스트/타이밍으로 전달됐는지 검증합니다.
            // C++/Python fallback과 같은 값 순서와 millisecond 반올림을 유지해야 세그먼트-에디터 불일치 원인 추적이 가능합니다.
            segmentFeedSignature.combine(milliseconds(start))
            segmentFeedSignature.combine(milliseconds(end))
            segmentFeedSignature.combine(Int64(chars))
            segmentFeedSignature.combine(Int64(bitPattern: SegmentFeedSignature.textHash(text)))
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
                    let overlap = previousEnd - start
                    // 변경 금지: editor/timeline/final SRT 싱크가 어긋날 때 겹침 위치를 추적하는 native 계약입니다.
                    // count만 있으면 X5/마카오처럼 일부 구간만 먼저 튀어나오는 drift를 재현 artifact에서 바로 찾기 어렵습니다.
                    if overlap > maxOverlap {
                        maxOverlap = overlap
                        maxOverlapIndex = count - 1
                    }
                } else {
                    let gap = start - previousEnd
                    if gap > maxGap {
                        maxGap = gap
                        maxGapIndex = count - 1
                    }
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
            "max_gap_index": maxGapIndex,
            "max_overlap": round6(maxOverlap),
            "max_overlap_index": maxOverlapIndex,
            "max_chars": maxChars,
            "avg_chars": round6(avgChars),
            "stable_for_save_reopen": invalidDurationCount == 0 && nonMonotonicCount == 0,
            "segment_feed_signature": segmentFeedSignature.hexString,
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

    private static func milliseconds(_ value: Double) -> Int64 {
        guard value.isFinite else { return 0 }
        return Int64((value * 1_000.0).rounded(.toNearestOrAwayFromZero))
    }
}

private struct SegmentFeedSignature {
    private var hash: UInt64 = 1_469_598_103_934_665_603
    private let prime: UInt64 = 1_099_511_628_211

    mutating func combine(_ value: Int64) {
        hash ^= UInt64(bitPattern: value)
        hash &*= prime
    }

    var hexString: String {
        String(format: "%016llx", hash)
    }

    static func textHash(_ text: String) -> UInt64 {
        var hash: UInt64 = 1_469_598_103_934_665_603
        for byte in text.utf8 {
            hash ^= UInt64(byte)
            hash &*= 1_099_511_628_211
        }
        return hash
    }
}
