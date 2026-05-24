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
                "matched_reference_indices": [],
                "max_start_error_sec": 0.0,
                "max_end_error_sec": 0.0,
                "max_pair_timing_error_sec": 0.0,
                "worst_match_hypothesis_index": -1,
                "worst_match_reference_index": -1,
            ]
        }

        var totalTimingError = 0.0
        var totalOverlapScore = 0.0
        var matchedPairs = 0
        var matchedReferenceIndices: [Int] = []
        var maxStartError = 0.0
        var maxEndError = 0.0
        var maxPairTimingError = 0.0
        var worstMatchHypothesisIndex = -1
        var worstMatchReferenceIndex = -1

        for (hypothesisIndex, hyp) in hypothesis.enumerated() {
            guard let match = bestReference(for: hyp, reference: reference) else {
                continue
            }
            let ref = match.row
            let startError = abs(hyp.start - ref.start)
            let endError = abs(hyp.end - ref.end)
            let pairTimingError = (startError + endError) / 2.0
            let span = max(0.001, max(hyp.end - hyp.start, ref.end - ref.start))
            // 변경 금지: 평균 MAE 뒤에 숨는 자막 타이밍 drift를 X5/실앱 artifact에서 찾기 위한 계약입니다.
            // C++ helper와 같은 match owner를 기준으로 최대 start/end/pair 오차와 pair index를 기록합니다.
            maxStartError = max(maxStartError, startError)
            maxEndError = max(maxEndError, endError)
            if pairTimingError > maxPairTimingError {
                maxPairTimingError = pairTimingError
                worstMatchHypothesisIndex = hypothesisIndex
                worstMatchReferenceIndex = match.index
            }
            totalTimingError += pairTimingError
            totalOverlapScore += min(1.0, overlap(hyp, ref) / span)
            matchedPairs += 1
            matchedReferenceIndices.append(match.index)
        }

        let denominator = max(1, matchedPairs)
        return [
            "schema": "ai_subtitle_studio.subtitle_timing.metrics.v1",
            "timing_mae_sec": totalTimingError / Double(denominator),
            "overlap_score": (totalOverlapScore / Double(denominator)) * 100.0,
            "matched_pairs": matchedPairs,
            "matched_reference_indices": matchedReferenceIndices,
            "max_start_error_sec": maxStartError,
            "max_end_error_sec": maxEndError,
            "max_pair_timing_error_sec": maxPairTimingError,
            "worst_match_hypothesis_index": worstMatchHypothesisIndex,
            "worst_match_reference_index": worstMatchReferenceIndex,
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

    private static func bestReference(for hyp: TimingRow, reference: [TimingRow]) -> (row: TimingRow, index: Int)? {
        let hypMid = (hyp.start + hyp.end) / 2.0
        var bestRow: TimingRow?
        var bestIndex: Int?
        var bestScore = -1.0
        for (index, ref) in reference.enumerated() {
            let refMid = (ref.start + ref.end) / 2.0
            let proximity = max(0.0, 1.0 - abs(hypMid - refMid) / 4.0)
            let score = overlap(hyp, ref) * 2.0 + proximity
            if score > bestScore {
                bestScore = score
                bestRow = ref
                bestIndex = index
            }
        }
        guard let row = bestRow, let index = bestIndex else {
            return nil
        }
        return (row, index)
    }

    private static func overlap(_ left: TimingRow, _ right: TimingRow) -> Double {
        max(0.0, min(left.end, right.end) - max(left.start, right.start))
    }
}
