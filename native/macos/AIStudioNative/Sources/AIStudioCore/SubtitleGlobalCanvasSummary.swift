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
        return [
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
            "avg_bin_active": round6(occupancy.average),
            "coverage_duration": round6(sweep.coverage),
            "coverage_ratio": round6(duration > 0.0 ? sweep.coverage / duration : 0.0),
            "longest_empty_span_sec": round6(sweep.longestGap),
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
    }

    private static func summarizeBins(_ bins: [Int]) -> (occupied: Int, dense: Int, maxActive: Int, average: Double) {
        var occupied = 0
        var dense = 0
        var maxActive = 0
        var total = 0
        for value in bins {
            if value > 0 {
                occupied += 1
            }
            if value > 1 {
                dense += 1
            }
            maxActive = max(maxActive, value)
            total += value
        }
        let average = bins.isEmpty ? 0.0 : Double(total) / Double(bins.count)
        return (occupied, dense, maxActive, average)
    }

    private static func summarizeCoverage(_ intervals: [(start: Double, end: Double)]) -> (coverage: Double, longestGap: Double, maxActive: Int) {
        let sorted = intervals.sorted { left, right in
            if left.start == right.start {
                return left.end < right.end
            }
            return left.start < right.start
        }
        var coverage = 0.0
        var longestGap = 0.0
        var maxActive = 0
        var mergedStart: Double?
        var mergedEnd: Double?
        var previousEnd: Double?
        var events: [(time: Double, delta: Int)] = []

        for interval in sorted {
            if let previousEnd, interval.start > previousEnd {
                longestGap = max(longestGap, interval.start - previousEnd)
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
        return (coverage, longestGap, maxActive)
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
