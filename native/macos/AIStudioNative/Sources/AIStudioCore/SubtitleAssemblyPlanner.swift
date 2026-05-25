import Foundation

public enum SubtitleAssemblyPlanner {
    public static func plan(payload: [String: Any]) -> [String: Any] {
        let available = SubtitleAssemblyValue.dictionaryRows(payload["available_variants"])
        let availableNames = Set(available.map { SubtitleAssemblyValue.string($0["name"]) }.filter { !$0.isEmpty })
        let sourceVariant = selectSourceVariant(availableNames: availableNames)
        let baselines = SubtitleAssemblyValue.stringArray(
            payload["quality_baseline_variants"],
            fallback: SubtitleAssemblyDefaults.qualityBaselineVariants
        )
        let candidate = SubtitleAssemblyValue.string(payload["candidate_variant"]).isEmpty
            ? SubtitleAssemblyDefaults.candidateVariant
            : SubtitleAssemblyValue.string(payload["candidate_variant"])

        return [
            "schema": SubtitleAssemblySchemas.plan,
            "candidate_variant": candidate,
            "source_variant": sourceVariant,
            "fallback_variant": "mode_high",
            "assembly_owner": "swift",
            "stages": SubtitleAssemblyDefaults.stageRows,
            "settings_overrides": settingsOverrides(sourceVariant: sourceVariant),
            "quality_floor": [
                "baseline_variants": baselines,
                "metric": "quality_score",
                "comparison": "candidate_must_be_at_least_best_baseline",
                "minimum_delta": 0.0,
            ],
            "promotion_rule": [
                "requires_benchmark": true,
                "candidate_variant": candidate,
                "baseline_variants": baselines,
                "failure_action": "keep_existing_fast_auto_high_paths",
            ],
        ]
    }

    private static func selectSourceVariant(availableNames: Set<String>) -> String {
        for name in SubtitleAssemblyDefaults.preferredSourceVariants where availableNames.contains(name) {
            return name
        }
        return "mode_high"
    }

    private static func settingsOverrides(sourceVariant: String) -> [String: Any] {
        [
            "native_subtitle_assembly_enabled": true,
            "native_subtitle_assembly_source_variant": sourceVariant,
            "native_subtitle_assembly_quality_floor": "best_fast_auto_high",
            "native_resource_allocator_worker_plan_enabled": true,
            "runtime_hardware_acceleration_enabled": true,
            "stt_backend_policy": "native",
            "whisperkit_native_auto_enabled": true,
            "stt_accelerator_distribution": "ane+gpu",
            "audio_torch_gpu_enabled": true,
            "ffmpeg_videotoolbox_decode_enabled": true,
            "scan_cut_pioneer_pipe_hwaccel_enabled": true,
            "lora_gpu_acceleration_enabled": true,
            "subtitle_final_stt_anchor_guard_enabled": true,
            "subtitle_final_stt_anchor_guard_insert_missing_enabled": true,
            "subtitle_llm_prev_next_context_enabled": true,
            "subtitle_llm_context_candidate_limit": 5,
            "subtitle_llm_context_min_current_similarity": 0.86,
            "subtitle_llm_context_neighbor_reject_margin": 0.06,
            "subtitle_output_selector_enabled": true,
            "stt_word_timestamps_precision_max_segments": 48,
            "stt_word_timestamps_precision_min_similarity": 0.36,
            "stt_word_timestamps_precision_max_timing_shift_sec": 0.28,
        ]
    }
}
