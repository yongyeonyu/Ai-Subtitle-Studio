import Foundation

public enum SubtitleAssemblyQualityGate {
    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        let rows = benchmarkRows(payload)
        let candidateName = SubtitleAssemblyValue.string(payload["candidate_variant"]).isEmpty
            ? SubtitleAssemblyDefaults.candidateVariant
            : SubtitleAssemblyValue.string(payload["candidate_variant"])
        let baselineNames = Set(
            SubtitleAssemblyValue.stringArray(
                payload["baseline_variants"],
                fallback: SubtitleAssemblyDefaults.qualityBaselineVariants
            )
        )

        guard let candidate = rows.first(where: { SubtitleAssemblyValue.string($0["name"]) == candidateName }) else {
            return error("missing_candidate", candidateName: candidateName, baselineNames: Array(baselineNames).sorted())
        }
        let baselines = rows.filter { baselineNames.contains(SubtitleAssemblyValue.string($0["name"])) }
        guard let bestBaseline = baselines.max(by: { qualityScore($0) < qualityScore($1) }) else {
            return error("missing_baseline", candidateName: candidateName, baselineNames: Array(baselineNames).sorted())
        }

        let candidateQuality = qualityScore(candidate)
        let baselineQuality = qualityScore(bestBaseline)
        let qualityDelta = candidateQuality - baselineQuality
        let passed = qualityDelta >= 0.0
        return [
            "schema": SubtitleAssemblySchemas.qualityGate,
            "passed": passed,
            "reason": passed ? "candidate_not_below_best_fast_auto_high" : "quality_score_below_best_fast_auto_high",
            "candidate_variant": candidateName,
            "baseline_variant": SubtitleAssemblyValue.string(bestBaseline["name"]),
            "candidate_quality_score": round3(candidateQuality),
            "baseline_quality_score": round3(baselineQuality),
            "quality_delta": round3(qualityDelta),
            "baseline_variants": Array(baselineNames).sorted(),
        ]
    }

    private static func benchmarkRows(_ payload: [String: Any]) -> [[String: Any]] {
        let ranked = SubtitleAssemblyValue.dictionaryRows(payload["ranked_results"])
        if !ranked.isEmpty {
            return ranked
        }
        return SubtitleAssemblyValue.dictionaryRows(payload["results"])
    }

    private static func qualityScore(_ row: [String: Any]) -> Double {
        SubtitleAssemblyValue.nestedNumber(row, key: "quality_score")
    }

    private static func round3(_ value: Double) -> Double {
        (value * 1000.0).rounded() / 1000.0
    }

    private static func error(_ reason: String, candidateName: String, baselineNames: [String]) -> [String: Any] {
        [
            "schema": SubtitleAssemblySchemas.qualityGate,
            "passed": false,
            "reason": reason,
            "candidate_variant": candidateName,
            "baseline_variants": baselineNames,
        ]
    }
}
