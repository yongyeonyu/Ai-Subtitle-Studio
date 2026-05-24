import Foundation

public enum SubtitleLoraSelectiveMergeNative {
    public static let schema = "ai_subtitle_studio.subtitle_lora.selective_merge.v1"
    public static let settingsSchema = "ai_subtitle_studio.subtitle_lora.merge_settings.v1"
    public static let packagingModeSchema = "ai_subtitle_studio.subtitle_lora.packaging_mode.v1"
    public static let packagingCandidateScoreSchema = "ai_subtitle_studio.subtitle_lora.packaging_candidate_score.v1"
    public static let packagingReasonsSchema = "ai_subtitle_studio.subtitle_lora.packaging_reasons.v1"

    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        let rows = SubtitleAssemblyValue.dictionaryRows(payload["rows"])
        let settings = payload["settings"] as? [String: Any] ?? [:]
        let mergeSettings = payload["merge_settings"] as? [String: Any] ?? [:]

        var selected = Set<Int>()
        var reasonsMap: [String: [String]] = [:]

        for (index, row) in rows.enumerated() {
            let reasons = readabilityMergeReasons(row: row, settings: settings, mergeSettings: mergeSettings)
            if reasons.isEmpty {
                continue
            }
            reasonsMap[String(index)] = reasons
            selected.insert(index)
            if index > 0 {
                selected.insert(index - 1)
            }
            if index + 1 < rows.count {
                selected.insert(index + 1)
            }
        }

        return [
            "schema": schema,
            "backend": "swift",
            "selected_indexes": selected.sorted(),
            "reasons_map": reasonsMap,
            "row_count": rows.count,
        ]
    }

    public static func mergeSettings(payload: [String: Any]) -> [String: Any] {
        let settings = payload["settings"] as? [String: Any] ?? payload
        let loraFloorChars = max(8, Int(SubtitleAssemblyValue.number(settings["subtitle_lora_split_floor_chars"], fallback: 20.0)))
        let maxChars = max(loraFloorChars, Int(SubtitleAssemblyValue.number(settings["split_length_threshold"], fallback: 20.0)))
        let minDuration = max(
            SubtitleAssemblyValue.number(settings["sub_min_duration"], fallback: 0.3),
            SubtitleAssemblyValue.number(settings["subtitle_lora_micro_merge_min_duration"], fallback: 0.8)
        )
        let gapBreak = max(
            SubtitleAssemblyValue.number(settings["sub_gap_break_sec"], fallback: 1.5),
            SubtitleAssemblyValue.number(settings["subtitle_lora_micro_merge_gap_sec"], fallback: 1.8)
        )
        let wordGap = max(
            SubtitleAssemblyValue.number(settings["word_timing_gap_break_sec"], fallback: 0.65),
            SubtitleAssemblyValue.number(settings["subtitle_lora_micro_merge_word_gap_sec"], fallback: 1.2)
        )
        let continuous = max(
            SubtitleAssemblyValue.number(settings["continuous_threshold"], fallback: 2.0),
            SubtitleAssemblyValue.number(settings["subtitle_lora_micro_merge_continuous_sec"], fallback: 3.0),
            gapBreak
        )
        return [
            "schema": settingsSchema,
            "backend": "swift",
            "split_length_threshold": maxChars,
            "sub_min_duration": rounded(minDuration),
            "sub_gap_break_sec": rounded(gapBreak),
            "word_timing_gap_break_sec": rounded(wordGap),
            "continuous_threshold": rounded(continuous),
        ]
    }

    public static func packagingMode(payload: [String: Any]) -> [String: Any] {
        let settings = payload["settings"] as? [String: Any] ?? payload
        let raw = SubtitleAssemblyValue.string(settings["subtitle_lora_packaging_mode"]).lowercased()
        let mode: String
        if ["readability", "readability_selective", "selective"].contains(raw) {
            mode = "readability_selective"
        } else {
            mode = "full"
        }
        return [
            "schema": packagingModeSchema,
            "backend": "swift",
            "mode": mode,
        ]
    }

    public static func packagingCandidateScore(payload: [String: Any]) -> [String: Any] {
        let lineLengths = intArray(payload["line_lengths"]).map { max(1, $0) }
        if lineLengths.isEmpty {
            return [
                "schema": packagingCandidateScoreSchema,
                "backend": "swift",
                "score": -1.0e300,
                "valid": false,
            ]
        }
        let pattern = SubtitleAssemblyValue.string(payload["pattern"])
        let strategy = SubtitleAssemblyValue.string(payload["strategy"])
        let currentPattern = SubtitleAssemblyValue.string(payload["current_pattern"])
        let targetPatterns = SubtitleAssemblyValue.stringArray(payload["target_patterns"], fallback: [])
        let targetLineCount = max(0, Int(SubtitleAssemblyValue.number(payload["target_line_count"], fallback: 0.0)))
        let threshold = max(1, Int(SubtitleAssemblyValue.number(payload["threshold"], fallback: 20.0)))
        let maxLine = lineLengths.max() ?? 1
        let minLine = lineLengths.min() ?? 1

        var score = 0.0
        if !targetPatterns.isEmpty {
            if pattern == targetPatterns[0] {
                score += 240.0
            } else if targetPatterns.contains(pattern) {
                score += 180.0
            }
        }
        if targetLineCount > 0 {
            score += max(0.0, 48.0 - Double(abs(lineLengths.count - targetLineCount)) * 20.0)
        }
        switch strategy {
        case "lora_ground_truth_line_break":
            score += 30.0
        case "lora_line_count":
            score += 18.0
        case "balanced":
            score += 8.0
        case "rule_greedy":
            score += 4.0
        default:
            break
        }
        let overflow = max(0, maxLine - threshold)
        score -= Double(overflow) * 10.0
        if lineLengths.count > 2 {
            score -= Double(lineLengths.count - 2) * 24.0
        }
        score -= Double(maxLine - minLine) * 0.6
        if lineLengths.count >= 2 {
            score += 6.0
        }
        if pattern == currentPattern {
            score -= 6.0
        }
        return [
            "schema": packagingCandidateScoreSchema,
            "backend": "swift",
            "score": score,
            "valid": true,
        ]
    }

    public static func packagingReasons(payload: [String: Any]) -> [String: Any] {
        let threshold = max(8, Int(SubtitleAssemblyValue.number(payload["threshold"], fallback: 20.0)))
        let chars = max(0, Int(SubtitleAssemblyValue.number(payload["chars"], fallback: 0.0)))
        let lineCount = max(0, Int(SubtitleAssemblyValue.number(payload["line_count"], fallback: 0.0)))
        let currentPattern = SubtitleAssemblyValue.string(payload["current_pattern"])
        let targetPatterns = SubtitleAssemblyValue.stringArray(payload["target_patterns"], fallback: [])
        let targetLineCount = max(0, Int(SubtitleAssemblyValue.number(payload["target_line_count"], fallback: 0.0)))
        let qualityLabel = SubtitleAssemblyValue.string(payload["quality_label"]).lowercased()
        let qualityScore = SubtitleAssemblyValue.number(payload["quality_score"], fallback: 0.0)
        let qualityMaxScore = SubtitleAssemblyValue.number(payload["quality_max_score"], fallback: 84.0)

        var reasons: [String] = []
        if lineCount <= 1 && chars >= max(10, Int(Double(threshold) * 0.88)) {
            reasons.append("single_line_overflow")
        }
        if !targetPatterns.isEmpty && !targetPatterns.contains(currentPattern) {
            reasons.append("pattern_mismatch")
        }
        if targetLineCount >= 2 && lineCount < targetLineCount {
            reasons.append("line_count_target")
        }
        if qualityLabel == "yellow" || qualityLabel == "red" {
            reasons.append("quality_\(qualityLabel)")
        } else if qualityScore > 0.0 && qualityScore < qualityMaxScore {
            reasons.append("low_quality_score")
        }
        return [
            "schema": packagingReasonsSchema,
            "backend": "swift",
            "reasons": reasons,
        ]
    }

    private static func readabilityMergeReasons(
        row: [String: Any],
        settings: [String: Any],
        mergeSettings: [String: Any]
    ) -> [String] {
        let threshold = max(8, Int(SubtitleAssemblyValue.number(mergeSettings["split_length_threshold"], fallback: 20.0)))
        let chars = compactTextLength(row["text"])
        let duration = max(0.1, segmentDuration(row))
        let cps = Double(chars) / duration
        let maxCPS = max(1.0, SubtitleAssemblyValue.number(settings["sub_max_cps"], fallback: 12.0))
        let minDuration = max(0.05, SubtitleAssemblyValue.number(mergeSettings["sub_min_duration"], fallback: 0.3))
        let floorChars = max(2, Int(Double(threshold) * 0.45))
        let qualityLabel = segmentQualityLabel(row)
        let qualityScore = segmentQualityScore(row)
        let uncertainty = row["_uncertainty_policy"] as? [String: Any] ?? [:]
        let uncertaintyBucket = SubtitleAssemblyValue.string(uncertainty["bucket"]).lowercased()
        let uncertaintyReasons = uncertaintyReasonSet(uncertainty)

        var reasons: [String] = []
        if duration < minDuration || chars <= floorChars {
            reasons.append("micro_fragment")
        }
        if cps > maxCPS * 1.04 {
            reasons.append("high_cps")
        }
        if chars > Int(Double(threshold) * 1.12) {
            reasons.append("long_text")
        }
        if qualityLabel == "yellow" || qualityLabel == "red" {
            reasons.append("quality_\(qualityLabel)")
        } else {
            let qualityMax = SubtitleAssemblyValue.number(settings["subtitle_lora_selective_quality_max_score"], fallback: 82.0)
            if qualityScore > 0.0 && qualityScore < qualityMax {
                reasons.append("low_quality_score")
            }
        }
        if uncertaintyBucket == "precision" {
            reasons.append("precision_bucket")
        }
        for key in ["high_cps", "long_text", "quality_red", "quality_yellow"] {
            if uncertaintyReasons.contains(key) && !reasons.contains(key) {
                reasons.append(key)
            }
        }
        return reasons
    }

    private static func segmentQualityLabel(_ row: [String: Any]) -> String {
        let quality = row["quality"] as? [String: Any] ?? [:]
        let value = SubtitleAssemblyValue.string(quality["confidence_label"]).isEmpty
            ? SubtitleAssemblyValue.string(row["subtitle_confidence_label"])
            : SubtitleAssemblyValue.string(quality["confidence_label"])
        return value.lowercased()
    }

    private static func segmentQualityScore(_ row: [String: Any]) -> Double {
        let quality = row["quality"] as? [String: Any] ?? [:]
        let raw = quality.keys.contains("confidence_score") ? quality["confidence_score"] : row["subtitle_confidence_score"]
        var value = SubtitleAssemblyValue.number(raw, fallback: 0.0)
        if value >= 0.0 && value <= 1.0 {
            value *= 100.0
        }
        return max(0.0, min(100.0, value))
    }

    private static func segmentDuration(_ row: [String: Any]) -> Double {
        let start = SubtitleAssemblyValue.number(row["start"], fallback: 0.0)
        let end = SubtitleAssemblyValue.number(row["end"], fallback: start)
        return max(0.0, end - start)
    }

    private static func intArray(_ value: Any?) -> [Int] {
        if let values = value as? [Int] {
            return values
        }
        if let values = value as? [Any] {
            return values.map { Int(SubtitleAssemblyValue.number($0, fallback: 0.0)) }
        }
        return []
    }

    private static func compactTextLength(_ value: Any?) -> Int {
        SubtitleAssemblyValue.string(value).filter { !$0.isWhitespace }.count
    }

    private static func uncertaintyReasonSet(_ uncertainty: [String: Any]) -> Set<String> {
        guard let rows = uncertainty["reasons"] as? [Any] else {
            return []
        }
        var out = Set<String>()
        for item in rows {
            guard let row = item as? [String: Any] else {
                continue
            }
            let reason = SubtitleAssemblyValue.string(row["reason"]).lowercased()
            if !reason.isEmpty {
                out.insert(reason)
            }
        }
        return out
    }

    private static func rounded(_ value: Double) -> Double {
        (value * 1_000.0).rounded() / 1_000.0
    }
}
