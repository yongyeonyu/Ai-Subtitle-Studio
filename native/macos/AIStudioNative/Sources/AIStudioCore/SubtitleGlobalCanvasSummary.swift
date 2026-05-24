import Foundation

public enum SubtitleGlobalCanvasSummaryNative {
    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        let segments = (payload["segments"] as? [[String: Any]]) ?? []
        let requestedDuration = doubleValue(payload["duration"], default: 0.0)
        let binCount = max(1, min(2048, intValue(payload["bin_count"], default: 120)))
        var intervals: [(start: Double, end: Double)] = []
        var invalidDurationCount = 0
        var nonMonotonicCount = 0
        var previousStart: Double?
        var maxEnd = 0.0

        for segment in segments {
            let start = max(0.0, doubleValue(segment["start"], default: 0.0))
            let end = max(0.0, doubleValue(segment["end"], default: start))
            if let previousStart, start < previousStart {
                nonMonotonicCount += 1
            }
            previousStart = start
            maxEnd = max(maxEnd, end)
            if end > start {
                intervals.append((start, end))
            } else {
                invalidDurationCount += 1
            }
        }

        let duration = max(requestedDuration, maxEnd)
        let binWidth = duration > 0.0 ? duration / Double(binCount) : 0.0
        var bins = Array(repeating: 0, count: binCount)
        if duration > 0.0 {
            for interval in intervals {
                let clippedStart = min(max(0.0, interval.start), duration)
                let clippedEnd = min(max(0.0, interval.end), duration)
                if clippedEnd <= clippedStart {
                    continue
                }
                let startBin = min(binCount - 1, max(0, Int(floor((clippedStart / duration) * Double(binCount)))))
                let endBinExclusive = min(binCount, max(startBin + 1, Int(ceil((clippedEnd / duration) * Double(binCount)))))
                if startBin < endBinExclusive {
                    for idx in startBin..<endBinExclusive {
                        bins[idx] += 1
                    }
                }
            }
        }

        let occupancy = summarizeBins(bins)
        let sweep = summarizeCoverage(intervals)
        var result: [String: Any] = [
            "schema": "ai_subtitle_studio.subtitle_global_canvas.summary.v1",
            "backend": "swift",
            "segment_count": segments.count,
            "valid_segment_count": intervals.count,
            "invalid_duration_count": invalidDurationCount,
            "non_monotonic_count": nonMonotonicCount,
            "duration": round6(duration),
            "bin_count": binCount,
            "bin_width_sec": round6(binWidth),
            "occupied_bin_count": occupancy.occupied,
            "empty_bin_count": max(0, binCount - occupancy.occupied),
            "dense_bin_count": occupancy.dense,
            "max_bin_active": occupancy.maxActive,
            "max_active_bin_index": occupancy.maxActiveBinIndex,
            "avg_bin_active": round6(occupancy.average),
            "coverage_duration": round6(sweep.coverage),
            "coverage_ratio": round6(duration > 0.0 ? sweep.coverage / duration : 0.0),
            "longest_empty_span_sec": round6(sweep.longestGap),
            "longest_empty_start_sec": round6(sweep.longestGapStart),
            "longest_empty_end_sec": round6(sweep.longestGapEnd),
            "max_active_segments": sweep.maxActive,
            "stable_for_global_canvas": invalidDurationCount == 0 && nonMonotonicCount == 0,
            "accelerator_summary": [
                "compute_task": "subtitle_global_canvas",
                "swift_vector_summary": true,
                "gpu_task_count": 0,
                "ane_task_count": 0,
                "metal_task_count": 0,
                "metal_claims_ane": false,
            ],
        ]
        if boolValue(payload["include_merged_segments"], default: false) {
            let allowedLanes = stringArray(payload["allowed_lanes"])
            let outputLane = stringValue(payload["output_lane"], default: "SUBTITLE")
            let maxGapSec = max(0.0, doubleValue(payload["merge_gap_sec"], default: 0.0))
            let includeText = boolValue(payload["include_text"], default: true)
            result["merged_segments"] = mergedSegments(
                segments,
                allowedLanes: allowedLanes.isEmpty ? ["SUBTITLE"] : allowedLanes,
                outputLane: outputLane,
                maxGapSec: maxGapSec,
                includeText: includeText
            )
        }
        return result
    }

    private static func summarizeBins(_ bins: [Int]) -> (occupied: Int, dense: Int, maxActive: Int, maxActiveBinIndex: Int, average: Double) {
        var occupied = 0
        var dense = 0
        var maxActive = 0
        var maxActiveBinIndex = -1
        var total = 0
        for (idx, value) in bins.enumerated() {
            if value > 0 {
                occupied += 1
            }
            if value > 1 {
                dense += 1
            }
            if value > maxActive {
                maxActive = value
                maxActiveBinIndex = value > 0 ? idx : -1
            }
            total += value
        }
        let average = bins.isEmpty ? 0.0 : Double(total) / Double(bins.count)
        return (occupied, dense, maxActive, maxActiveBinIndex, average)
    }

    private static func summarizeCoverage(_ intervals: [(start: Double, end: Double)]) -> (
        coverage: Double,
        longestGap: Double,
        longestGapStart: Double,
        longestGapEnd: Double,
        maxActive: Int
    ) {
        let sorted = intervals.sorted { left, right in
            if left.start == right.start {
                return left.end < right.end
            }
            return left.start < right.start
        }
        var coverage = 0.0
        var longestGap = 0.0
        var longestGapStart = 0.0
        var longestGapEnd = 0.0
        var maxActive = 0
        var mergedStart: Double?
        var mergedEnd: Double?
        var previousEnd: Double?
        var events: [(time: Double, delta: Int)] = []

        for interval in sorted {
            if let previousEnd, interval.start > previousEnd {
                let gap = interval.start - previousEnd
                // 변경 금지: global canvas의 빈 구간 위치를 데이터 계약으로 남깁니다.
                // UI 배치를 바꾸지 않고 X5/실앱 artifact에서 하단 minimap drift를 바로 찾기 위한 값입니다.
                if gap > longestGap {
                    longestGap = gap
                    longestGapStart = previousEnd
                    longestGapEnd = interval.start
                }
            }
            if mergedStart == nil {
                mergedStart = interval.start
                mergedEnd = interval.end
            } else if let currentEnd = mergedEnd, interval.start <= currentEnd {
                mergedEnd = max(currentEnd, interval.end)
            } else {
                coverage += max(0.0, (mergedEnd ?? 0.0) - (mergedStart ?? 0.0))
                mergedStart = interval.start
                mergedEnd = interval.end
            }
            previousEnd = max(previousEnd ?? interval.end, interval.end)
            events.append((interval.start, 1))
            events.append((interval.end, -1))
        }
        if let mergedStart, let mergedEnd {
            coverage += max(0.0, mergedEnd - mergedStart)
        }
        events.sort { left, right in
            if left.time == right.time {
                return left.delta < right.delta
            }
            return left.time < right.time
        }
        var active = 0
        for event in events {
            active += event.delta
            maxActive = max(maxActive, active)
        }
        return (coverage, longestGap, longestGapStart, longestGapEnd, maxActive)
    }

    private static func mergedSegments(
        _ segments: [[String: Any]],
        allowedLanes: [String],
        outputLane: String,
        maxGapSec: Double,
        includeText: Bool
    ) -> [[String: Any]] {
        struct Row {
            var start: Double
            var end: Double
            var text: String
            var order: Int
        }

        let allowed = Set(allowedLanes)
        var rows: [Row] = []
        for (idx, segment) in segments.enumerated() {
            let lane = stringValue(segment["lane"], default: "SUBTITLE")
            if !allowed.contains(lane) {
                continue
            }
            let start = max(0.0, doubleValue(segment["start"], default: 0.0))
            let end = max(start, doubleValue(segment["end"], default: start))
            if end <= start {
                continue
            }
            rows.append(Row(start: start, end: end, text: stringValue(segment["text"], default: "").trimmingCharacters(in: .whitespacesAndNewlines), order: idx))
        }
        rows.sort { left, right in
            if left.start == right.start {
                return left.order < right.order
            }
            return left.start < right.start
        }

        var mergedRows: [[String: Any]] = []
        for row in rows {
            if var previous = mergedRows.last,
               row.start <= (previous["end"] as? Double ?? 0.0) + maxGapSec {
                previous["end"] = max(previous["end"] as? Double ?? 0.0, row.end)
                if includeText && !row.text.isEmpty {
                    let previousText = (previous["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                    if !previousText.contains(row.text) {
                        previous["text"] = previousText.isEmpty ? row.text : "\(previousText) \(row.text)"
                    }
                }
                previous["count"] = (previous["count"] as? Int ?? 1) + 1
                mergedRows[mergedRows.count - 1] = previous
                continue
            }
            var item: [String: Any] = [
                "start": row.start,
                "end": row.end,
                "lane": outputLane,
                "count": 1,
            ]
            if includeText {
                item["text"] = row.text
            }
            mergedRows.append(item)
        }
        return mergedRows
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

    private static func stringValue(_ value: Any?, default fallback: String) -> String {
        if let text = value as? String {
            return text
        }
        if let number = value as? NSNumber {
            return number.stringValue
        }
        return fallback
    }

    private static func stringArray(_ value: Any?) -> [String] {
        guard let values = value as? [Any] else {
            return []
        }
        return values.map { stringValue($0, default: "") }.filter { !$0.isEmpty }
    }

    private static func boolValue(_ value: Any?, default fallback: Bool) -> Bool {
        if let flag = value as? Bool {
            return flag
        }
        if let number = value as? NSNumber {
            return number.boolValue
        }
        if let text = value as? String {
            let normalized = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if ["1", "true", "yes", "on"].contains(normalized) {
                return true
            }
            if ["0", "false", "no", "off"].contains(normalized) {
                return false
            }
        }
        return fallback
    }

    private static func intValue(_ value: Any?, default fallback: Int) -> Int {
        if let number = value as? NSNumber {
            return number.intValue
        }
        if let text = value as? String, let number = Int(text) {
            return number
        }
        return fallback
    }

    private static func round6(_ value: Double) -> Double {
        guard value.isFinite else { return 0.0 }
        return (value * 1_000_000.0).rounded() / 1_000_000.0
    }
}
