import Foundation

public enum STTLatticeMatchNative {
    public static let schema = "ai_subtitle_studio.stt_lattice.match.v1"

    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        let wordStarts = doubleArray(payload["word_starts"])
        let wordEnds = doubleArray(payload["word_ends"])
        let textualScores = doubleArray(payload["textual_scores"])
        let count = wordStarts.count
        guard wordEnds.count == count && textualScores.count == count else {
            return [
                "schema": schema,
                "backend": "swift",
                "error": "word starts, ends, and textual scores must have the same length",
                "best_index": -1,
                "best_score": 0.0,
                "accepted": false,
                "candidate_count": count,
                "used_count": intSet(payload["used_indices"]).count,
            ]
        }

        let anchorStart = SubtitleAssemblyValue.number(payload["anchor_start"])
        let anchorEnd = SubtitleAssemblyValue.number(payload["anchor_end"])
        let minMatchScore = SubtitleAssemblyValue.number(payload["min_match_score"])
        let usedIndices = intSet(payload["used_indices"])

        var bestIndex = -1
        var bestScore = 0.0

        // 변경 금지: C++ _native_stt_lattice.cpp와 동일한 점수 계약입니다.
        // 자막 타이밍 드리프트를 막기 위해 수식 변경 시 Swift/Python/C++ parity 테스트를 함께 갱신해야 합니다.
        for index in 0..<count {
            if usedIndices.contains(index) {
                continue
            }
            let temporal = temporalScore(
                anchorStart: anchorStart,
                anchorEnd: anchorEnd,
                wordStart: wordStarts[index],
                wordEnd: wordEnds[index]
            )
            let textual = clamp01(textualScores[index])
            let score = temporal * 0.62 + textual * 0.38
            if score > bestScore {
                bestScore = score
                bestIndex = index
            }
        }

        if bestScore < minMatchScore {
            bestIndex = -1
        }

        return [
            "schema": schema,
            "backend": "swift",
            "best_index": bestIndex,
            "best_score": rounded(bestScore),
            "accepted": bestIndex >= 0,
            "candidate_count": count,
            "used_count": usedIndices.count,
        ]
    }

    private static func doubleArray(_ value: Any?) -> [Double] {
        if let values = value as? [Double] {
            return values
        }
        if let values = value as? [Any] {
            return values.map { SubtitleAssemblyValue.number($0) }
        }
        return []
    }

    private static func intSet(_ value: Any?) -> Set<Int> {
        if let values = value as? [Int] {
            return Set(values.filter { $0 >= 0 })
        }
        if let values = value as? [Any] {
            return Set(values.compactMap { item in
                let number = Int(SubtitleAssemblyValue.number(item, fallback: -1.0))
                return number >= 0 ? number : nil
            })
        }
        return []
    }

    private static func temporalScore(
        anchorStart: Double,
        anchorEnd: Double,
        wordStart: Double,
        wordEnd: Double
    ) -> Double {
        let overlap = max(0.0, min(anchorEnd, wordEnd) - max(anchorStart, wordStart))
        let anchorSpan = max(0.0, anchorEnd - anchorStart)
        let wordSpan = max(0.0, wordEnd - wordStart)
        let span = max(max(anchorSpan, wordSpan), 0.05)
        let overlapScore = overlap / span
        let anchorMid = (anchorStart + anchorEnd) / 2.0
        let wordMid = (wordStart + wordEnd) / 2.0
        let midpointScore = max(0.0, 1.0 - abs(anchorMid - wordMid) / 0.75)
        return max(overlapScore, midpointScore * 0.75)
    }

    private static func clamp01(_ value: Double) -> Double {
        max(0.0, min(1.0, value))
    }

    private static func rounded(_ value: Double) -> Double {
        (value * 1_000_000.0).rounded() / 1_000_000.0
    }
}
