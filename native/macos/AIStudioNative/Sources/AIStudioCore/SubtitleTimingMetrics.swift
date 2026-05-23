import Foundation

public enum SubtitleTimingMetricsNative {
    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        let hypothesis = rows(payload["hypothesis"])
        let reference = rows(payload["reference"])
        guard !hypothesis.isEmpty, !reference.isEmpty else {
            return [
                "schema": "ai_subtitle_studio.subtitle_timing.metrics.v1",
                "timing_mae_sec": 0.0,
                "overlap_score": 0.0,
                "matched_pairs": 0,
            ]
        }

        var totalTimingError = 0.0
        var totalOverlapScore = 0.0
        var matchedPairs = 0

        for hyp in hypothesis {
            guard let ref = bestReference(for: hyp, reference: reference) else {
                continue
            }
            let startError = abs(hyp.start - ref.start)
            let endError = abs(hyp.end - ref.end)
            let span = max(0.001, max(hyp.end - hyp.start, ref.end - ref.start))
            totalTimingError += (startError + endError) / 2.0
            totalOverlapScore += min(1.0, overlap(hyp, ref) / span)
            matchedPairs += 1
        }

        let denominator = max(1, matchedPairs)
        return [
            "schema": "ai_subtitle_studio.subtitle_timing.metrics.v1",
            "timing_mae_sec": totalTimingError / Double(denominator),
            "overlap_score": (totalOverlapScore / Double(denominator)) * 100.0,
            "matched_pairs": matchedPairs,
        ]
    }

    private struct TimingRow {
        let start: Double
        let end: Double
    }

    private static func rows(_ value: Any?) -> [TimingRow] {
        SubtitleAssemblyValue.dictionaryRows(value).compactMap { row in
            let text = SubtitleAssemblyValue.string(row["text"])
            guard !text.isEmpty else {
                return nil
            }
            let start = SubtitleAssemblyValue.number(row["start"])
            let end = SubtitleAssemblyValue.number(row["end"], fallback: start)
            return TimingRow(start: start, end: end)
        }
    }

    private static func bestReference(for hyp: TimingRow, reference: [TimingRow]) -> TimingRow? {
        let hypMid = (hyp.start + hyp.end) / 2.0
        var bestRow: TimingRow?
        var bestScore = -1.0
        for ref in reference {
            let refMid = (ref.start + ref.end) / 2.0
            let proximity = max(0.0, 1.0 - abs(hypMid - refMid) / 4.0)
            let score = overlap(hyp, ref) * 2.0 + proximity
            if score > bestScore {
                bestScore = score
                bestRow = ref
            }
        }
        return bestRow
    }

    private static func overlap(_ left: TimingRow, _ right: TimingRow) -> Double {
        max(0.0, min(left.end, right.end) - max(left.start, right.start))
    }
}
