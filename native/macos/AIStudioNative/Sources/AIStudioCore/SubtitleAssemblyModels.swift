import Foundation

public enum SubtitleAssemblySchemas {
    public static let plan = "ai_subtitle_studio.subtitle_assembly.plan.v1"
    public static let qualityGate = "ai_subtitle_studio.subtitle_assembly.quality_gate.v1"
    public static let llmContextPack = "ai_subtitle_studio.subtitle_llm_context_pack.v1"
    public static let llmContextGate = "ai_subtitle_studio.subtitle_llm_context_gate.v1"
}

public enum SubtitleAssemblyDefaults {
    public static let candidateVariant = "mode_swift_assembled"
    public static let qualityBaselineVariants = ["mode_fast", "mode_auto", "mode_high"]
    public static let preferredSourceVariants = [
        "mode_high_full_core_overlap",
        "mode_high_piecewise_drift",
        "mode_high",
        "mode_auto",
        "mode_fast",
    ]

    public static var stageRows: [[String: Any]] {
        [
            [
                "id": "media_audio_prepare",
                "owner": "python_ffmpeg_swift_manifest",
                "role": "extract_and_chunk_audio",
                "quality_sensitive": false,
            ],
            [
                "id": "stt_primary",
                "owner": "whisperkit_persistent",
                "role": "primary_stt_ane_gpu",
                "quality_sensitive": true,
            ],
            [
                "id": "stt_secondary_recheck",
                "owner": "mlx_or_whisperkit_secondary",
                "role": "selective_stt2_rescue",
                "quality_sensitive": true,
            ],
            [
                "id": "word_timing_precision",
                "owner": "whisperkit_word_timestamps",
                "role": "selected_word_timing_refine",
                "quality_sensitive": true,
            ],
            [
                "id": "subtitle_policy",
                "owner": "python_lora_deep_llm",
                "role": "split_merge_context_policy",
                "quality_sensitive": true,
            ],
            [
                "id": "final_anchor_guard",
                "owner": "swift_assembled_contract_python_guard",
                "role": "preserve_selected_stt_text_and_timing",
                "quality_sensitive": true,
            ],
            [
                "id": "benchmark_quality_gate",
                "owner": "swift_quality_floor",
                "role": "candidate_score_must_not_drop_below_fast_auto_high",
                "quality_sensitive": true,
            ],
        ]
    }
}

enum SubtitleAssemblyValue {
    static func string(_ value: Any?) -> String {
        guard let value else {
            return ""
        }
        return String(describing: value).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func stringArray(_ value: Any?, fallback: [String]) -> [String] {
        if let values = value as? [String] {
            let cleaned = values.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
            return cleaned.isEmpty ? fallback : cleaned
        }
        if let values = value as? [Any] {
            let cleaned = values.map { string($0) }.filter { !$0.isEmpty }
            return cleaned.isEmpty ? fallback : cleaned
        }
        let single = string(value)
        return single.isEmpty ? fallback : [single]
    }

    static func dictionaryRows(_ value: Any?) -> [[String: Any]] {
        if let rows = value as? [[String: Any]] {
            return rows
        }
        guard let anyRows = value as? [Any] else {
            return []
        }
        return anyRows.compactMap { $0 as? [String: Any] }
    }

    static func number(_ value: Any?, fallback: Double = 0.0) -> Double {
        if let value = value as? Double {
            return value
        }
        if let value = value as? Float {
            return Double(value)
        }
        if let value = value as? Int {
            return Double(value)
        }
        if let value = value as? NSNumber {
            return value.doubleValue
        }
        if let value = value as? String, let number = Double(value) {
            return number
        }
        return fallback
    }

    static func nestedNumber(_ row: [String: Any], key: String, fallback: Double = 0.0) -> Double {
        if row.keys.contains(key) {
            return number(row[key], fallback: fallback)
        }
        if let quality = row["quality"] as? [String: Any], quality.keys.contains(key) {
            return number(quality[key], fallback: fallback)
        }
        if let readability = row["readability"] as? [String: Any], readability.keys.contains(key) {
            return number(readability[key], fallback: fallback)
        }
        return fallback
    }
}
