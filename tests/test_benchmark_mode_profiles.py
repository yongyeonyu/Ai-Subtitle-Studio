import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from core.native_swift_subtitle_assembly import ASSEMBLED_VARIANT_NAME
from tools.apply_subtitle_benchmark_quality_gate import apply_gate
from tools.benchmark_subtitle_pipeline_variants import (
    _copy_chunk_dir,
    _compact_text,
    _enforce_swift_assembly_quality_floor,
    _native_global_canvas_summary_for_variant,
    _native_resource_summary_for_variant,
    _native_segments_summary_for_variant,
    _native_stt_segments_summary_for_variant,
    _rank_rows,
    _run_postprocess,
    _base_benchmark_settings,
    _chunk_extraction_signature,
    _variant_chunk_settings,
    benchmark_mode_lora_deep_profiles,
    benchmark_mode_lora_packaging_profiles,
    benchmark_mode_lora_selective_profiles,
    benchmark_mode_profiles,
    score_against_reference,
    score_readability,
)


class BenchmarkModeProfilesTests(unittest.TestCase):
    def test_mode_profiles_map_to_actual_fast_auto_high_paths(self):
        variants = benchmark_mode_profiles(_base_benchmark_settings("current"))
        by_name = {variant.name: variant for variant in variants}

        self.assertEqual(
            set(by_name),
            {
                "mode_fast",
                "mode_auto",
                "mode_auto_adaptive_split",
                "mode_auto_piecewise_drift",
                "mode_auto_adaptive_split_drift",
                "mode_high",
                "mode_high_full_core_overlap",
                "mode_high_piecewise_drift",
                ASSEMBLED_VARIANT_NAME,
            },
        )

        fast = by_name["mode_fast"]
        self.assertEqual(fast.method, "selective_ensemble")
        self.assertFalse(fast.run_llm)
        self.assertEqual(fast.overrides.get("subtitle_mode"), "fast")
        self.assertEqual(fast.overrides.get("stt_word_timestamps_mode"), "selective")
        self.assertFalse(bool(fast.overrides.get("subtitle_lora_micro_merge_enabled")))
        self.assertFalse(bool(fast.overrides.get("subtitle_lora_packaging_enabled")))
        self.assertFalse(bool(fast.overrides.get("subtitle_output_selector_enabled")))
        self.assertTrue(bool(fast.overrides.get("deep_timing_adjustment_enabled")))
        self.assertEqual(fast.overrides.get("subtitle_timing_anchor_max_start_lag_sec"), 0.06)
        self.assertEqual(fast.overrides.get("subtitle_timing_anchor_max_end_lag_sec"), 0.12)
        self.assertFalse(bool(fast.overrides.get("subtitle_cut_boundary_guard_enabled")))
        self.assertFalse(bool(fast.overrides.get("subtitle_bundle_use_confirmed_cuts")))
        self.assertFalse(bool(fast.overrides.get("subtitle_bundle_use_provisional_cuts")))
        self.assertTrue(bool(fast.overrides.get("stt_ensemble_enabled")))
        self.assertTrue(bool(fast.overrides.get("stt_ensemble_selective_enabled")))

        auto = by_name["mode_auto"]
        self.assertEqual(auto.method, "selective_ensemble")
        self.assertFalse(auto.run_llm)
        self.assertEqual(auto.overrides.get("subtitle_mode"), "auto")
        self.assertFalse(bool(auto.overrides.get("stt_word_timestamps_precision_enabled")))
        self.assertEqual(auto.overrides.get("cut_boundary_level"), "low")
        self.assertEqual(auto.overrides.get("stt_word_timestamps_precision_min_similarity"), 0.30)
        self.assertEqual(auto.overrides.get("stt_word_timestamps_precision_max_timing_shift_sec"), 0.35)
        self.assertEqual(auto.overrides.get("subtitle_timing_anchor_max_start_lag_sec"), 0.08)
        self.assertEqual(auto.overrides.get("subtitle_timing_anchor_max_end_lag_sec"), 0.14)
        self.assertTrue(bool(auto.overrides.get("subtitle_output_selector_enabled")))
        self.assertFalse(bool(auto.overrides.get("subtitle_lora_micro_merge_enabled")))
        self.assertTrue(bool(auto.overrides.get("subtitle_lora_packaging_enabled")))
        self.assertFalse(bool(auto.overrides.get("deep_timing_adjustment_enabled")))
        self.assertTrue(bool(auto.overrides.get("deep_subtitle_policy_enabled")))
        self.assertFalse(bool(auto.overrides.get("subtitle_bundle_use_provisional_cuts")))

        auto_split = by_name["mode_auto_adaptive_split"]
        self.assertEqual(auto_split.method, "selective_ensemble")
        self.assertTrue(bool(auto_split.overrides.get("audio_chunk_route_split_enabled")))
        self.assertEqual(auto_split.overrides.get("audio_chunk_route_max_span_sec"), 120.0)
        self.assertEqual(auto_split.overrides.get("audio_chunk_route_split_confidence_threshold"), 0.78)
        self.assertEqual(auto_split.overrides.get("audio_chunk_route_split_candidate_gap_max"), 0.07)
        self.assertEqual(auto_split.overrides.get("audio_chunk_route_split_preview_divergence_min"), 0.08)

        auto_drift = by_name["mode_auto_piecewise_drift"]
        self.assertEqual(auto_drift.method, "selective_ensemble")
        self.assertTrue(bool(auto_drift.overrides.get("subtitle_timing_piecewise_drift_enabled")))
        self.assertEqual(auto_drift.overrides.get("subtitle_timing_piecewise_drift_trigger_sec"), 0.05)
        self.assertEqual(auto_drift.overrides.get("subtitle_timing_piecewise_drift_max_shift_sec"), 0.10)

        auto_split_drift = by_name["mode_auto_adaptive_split_drift"]
        self.assertTrue(bool(auto_split_drift.overrides.get("audio_chunk_route_split_enabled")))
        self.assertTrue(bool(auto_split_drift.overrides.get("subtitle_timing_piecewise_drift_enabled")))

        high = by_name["mode_high"]
        self.assertEqual(high.method, "selective_ensemble")
        self.assertEqual(high.overrides.get("subtitle_mode"), "high")
        self.assertTrue(bool(high.overrides.get("stt_word_timestamps_precision_enabled")))
        self.assertEqual(high.overrides.get("cut_boundary_level"), "medium")
        self.assertEqual(high.overrides.get("stt_word_timestamps_precision_min_similarity"), 0.36)
        self.assertEqual(high.overrides.get("stt_word_timestamps_precision_max_timing_shift_sec"), 0.28)
        self.assertEqual(high.overrides.get("subtitle_timing_anchor_max_start_lag_sec"), 0.06)
        self.assertEqual(high.overrides.get("subtitle_timing_anchor_max_end_lag_sec"), 0.12)
        self.assertTrue(bool(high.overrides.get("subtitle_output_selector_enabled")))
        self.assertFalse(bool(high.overrides.get("subtitle_lora_micro_merge_enabled")))
        self.assertTrue(bool(high.overrides.get("subtitle_lora_packaging_enabled")))
        self.assertEqual(high.overrides.get("subtitle_lora_packaging_mode"), "readability_selective")
        self.assertTrue(bool(high.overrides.get("deep_timing_adjustment_enabled")))
        self.assertTrue(bool(high.overrides.get("deep_subtitle_policy_enabled")))
        self.assertFalse(bool(high.overrides.get("subtitle_bundle_use_provisional_cuts")))

        high_full_core = by_name["mode_high_full_core_overlap"]
        self.assertEqual(high_full_core.method, "selective_ensemble")
        self.assertEqual(high_full_core.overrides.get("benchmark_runtime_profile"), "apple_m_full_core_throughput")
        self.assertTrue(bool(high_full_core.overrides.get("apple_m_full_core_aggressive_enabled")))
        self.assertTrue(bool(high_full_core.overrides.get("stt_window_ensemble_enabled")))
        self.assertTrue(bool(high_full_core.overrides.get("stt_window_parallel_enabled")))
        self.assertEqual(high_full_core.overrides.get("stt_window_sec"), 180.0)
        self.assertEqual(high_full_core.overrides.get("stt_quarter_parallel_count"), 4)
        self.assertEqual(high_full_core.overrides.get("stt_quarter_parallel_max_workers"), 4)
        self.assertTrue(bool(high_full_core.overrides.get("stt_ensemble_selective_enabled")))
        self.assertFalse(bool(high_full_core.overrides.get("stt_ensemble_parallel_enabled")))

        high_drift = by_name["mode_high_piecewise_drift"]
        self.assertEqual(high_drift.method, "selective_ensemble")
        self.assertTrue(bool(high_drift.overrides.get("subtitle_timing_piecewise_drift_enabled")))

        assembled = by_name[ASSEMBLED_VARIANT_NAME]
        self.assertEqual(assembled.method, by_name["mode_high_full_core_overlap"].method)
        self.assertEqual(assembled.overrides.get("native_subtitle_assembly_source_variant"), "mode_high_full_core_overlap")
        self.assertTrue(bool(assembled.overrides.get("native_subtitle_assembly_enabled")))
        self.assertEqual(assembled.overrides.get("native_subtitle_assembly_quality_floor"), "best_fast_auto_high")
        self.assertTrue(bool(assembled.overrides.get("runtime_hardware_acceleration_enabled")))
        self.assertTrue(bool(assembled.overrides.get("whisperkit_native_auto_enabled")))
        self.assertEqual(assembled.overrides.get("stt_accelerator_distribution"), "gpu+npu+cpu")
        self.assertTrue(bool(assembled.overrides.get("audio_torch_gpu_enabled")))
        self.assertTrue(bool(assembled.overrides.get("ffmpeg_videotoolbox_decode_enabled")))
        self.assertTrue(bool(assembled.overrides.get("scan_cut_pioneer_pipe_hwaccel_enabled")))
        self.assertTrue(bool(assembled.overrides.get("lora_gpu_acceleration_enabled")))
        self.assertTrue(bool(assembled.overrides.get("subtitle_llm_prev_next_context_enabled")))
        self.assertEqual(assembled.overrides.get("subtitle_llm_context_min_current_similarity"), 0.86)
        self.assertEqual(assembled.overrides.get("subtitle_llm_context_neighbor_reject_margin"), 0.06)
        self.assertEqual(assembled.overrides.get("stt_word_timestamps_precision_max_segments"), 48)
        self.assertEqual(assembled.overrides.get("stt_word_timestamps_precision_min_similarity"), 0.36)
        self.assertEqual(assembled.overrides.get("stt_word_timestamps_precision_max_timing_shift_sec"), 0.28)
        plan = dict(assembled.overrides.get("native_subtitle_assembly_plan") or {})
        self.assertEqual(plan.get("candidate_variant"), ASSEMBLED_VARIANT_NAME)
        self.assertEqual(plan.get("source_variant"), "mode_high_full_core_overlap")
        self.assertEqual(
            dict(plan.get("quality_floor") or {}).get("baseline_variants"),
            ["mode_fast", "mode_auto", "mode_high"],
        )

    def test_native_resource_summary_keeps_compact_accelerator_counts(self):
        with mock.patch(
            "tools.benchmark_subtitle_pipeline_variants.plan_subtitle_resource_via_swift",
            return_value={
                "schema": "ai_subtitle_studio.subtitle_resource.plan.v1",
                "backend": "swift",
                "pressure_stage": "normal",
                "accelerator_summary": {
                    "gpu_task_count": 3,
                    "ane_task_count": 2,
                    "metal_task_count": 1,
                    "gpu_lanes_total": 12,
                    "ane_lanes_total": 10,
                    "max_gpu_lanes": 8,
                    "max_ane_lanes": 8,
                    "gpu_lane_capacity": 8,
                    "ane_model_lane_capacity": 8,
                    "gpu_lane_peak_ratio": 1.0,
                    "ane_model_lane_peak_ratio": 1.0,
                    "full_gpu_lane_task_count": 1,
                    "full_ane_model_lane_task_count": 1,
                    "gpu_lane_peak_saturated": True,
                    "ane_model_lane_peak_saturated": True,
                    "gpu_tasks": ["stt", "stt_precision", "vad"],
                    "ane_tasks": ["stt", "stt_precision"],
                    "metal_tasks": ["vad"],
                    "cpp_parity": True,
                    "metal_claims_ane": False,
                },
            },
        ):
            summary = _native_resource_summary_for_variant({"subtitle_mode": "high"}, run_llm=True)

        self.assertEqual(summary["backend"], "swift")
        self.assertEqual(summary["gpu_task_count"], 3)
        self.assertEqual(summary["ane_task_count"], 2)
        self.assertEqual(summary["metal_task_count"], 1)
        self.assertEqual(summary["gpu_lane_capacity"], 8)
        self.assertEqual(summary["ane_model_lane_capacity"], 8)
        self.assertEqual(summary["gpu_lane_peak_ratio"], 1.0)
        self.assertEqual(summary["ane_model_lane_peak_ratio"], 1.0)
        self.assertEqual(summary["full_gpu_lane_task_count"], 1)
        self.assertTrue(summary["gpu_lane_peak_saturated"])
        self.assertTrue(summary["ane_model_lane_peak_saturated"])
        self.assertTrue(summary["cpp_parity"])
        self.assertFalse(summary["metal_claims_ane"])
        self.assertIn("stt_precision", summary["ane_tasks"])

    def test_native_segments_summary_keeps_compact_invariant_counts(self):
        with mock.patch(
            "tools.benchmark_subtitle_pipeline_variants.summarize_segments_via_swift",
            return_value={
                "schema": "ai_subtitle_studio.subtitle_segments.summary.v1",
                "backend": "swift",
                "segment_count": 2,
                "invalid_duration_count": 0,
                "non_monotonic_count": 0,
                "overlap_count": 1,
                "empty_text_count": 0,
                "total_duration": 2.0,
                "first_start": 0.0,
                "last_end": 1.8,
                "max_gap": 0.0,
                "max_gap_index": -1,
                "max_overlap": 0.2,
                "max_overlap_index": 1,
                "max_chars": 5,
                "avg_chars": 4.5,
                "stable_for_save_reopen": True,
                "segment_feed_signature": "fedcba9876543210",
            },
        ):
            summary = _native_segments_summary_for_variant([{"start": 0.0, "end": 1.0, "text": "테스트"}])

        self.assertEqual(summary["backend"], "swift")
        self.assertEqual(summary["segment_count"], 2)
        self.assertEqual(summary["overlap_count"], 1)
        self.assertEqual(summary["segment_feed_signature"], "fedcba9876543210")
        self.assertTrue(summary["stable_for_save_reopen"])
        self.assertEqual(summary["max_gap_index"], -1)
        self.assertEqual(summary["max_overlap"], 0.2)
        self.assertEqual(summary["max_overlap_index"], 1)

    def test_native_stt_segments_summary_keeps_compact_stt2_counts(self):
        with mock.patch(
            "tools.benchmark_subtitle_pipeline_variants.summarize_stt_segments_via_swift",
            return_value={
                "schema": "ai_subtitle_studio.subtitle_stt_segments.summary.v1",
                "backend": "swift",
                "segment_count": 3,
                "stt1_selected_count": 1,
                "stt2_selected_count": 2,
                "recheck_applied_count": 2,
                "word_precision_count": 1,
                "secondary_hint_count": 0,
                "unknown_source_count": 0,
                "invalid_duration_count": 0,
                "non_monotonic_count": 0,
                "overlap_count": 0,
                "source_switch_count": 1,
                "total_duration": 3.0,
                "stt1_duration": 1.0,
                "stt2_duration": 2.0,
                "stt2_coverage_ratio": 0.666667,
                "stt2_first_start": 1.1,
                "stt2_last_end": 3.0,
                "longest_stt2_run_sec": 1.9,
                "longest_stt2_run_start": 1.1,
                "longest_stt2_run_end": 3.0,
                "longest_stt2_run_count": 2,
                "stt2_active": True,
                "selective_recheck_active": True,
                "stable_for_timeline_feed": True,
                "timeline_feed_signature": "0123456789abcdef",
            },
        ):
            summary = _native_stt_segments_summary_for_variant(
                [{"start": 0.0, "end": 1.0, "text": "테스트", "stt_selected_source": "STT2"}]
            )

        self.assertEqual(summary["backend"], "swift")
        self.assertEqual(summary["stt2_selected_count"], 2)
        self.assertEqual(summary["recheck_applied_count"], 2)
        self.assertEqual(summary["stt2_first_start"], 1.1)
        self.assertEqual(summary["stt2_last_end"], 3.0)
        self.assertEqual(summary["longest_stt2_run_sec"], 1.9)
        self.assertEqual(summary["longest_stt2_run_count"], 2)
        self.assertEqual(summary["timeline_feed_signature"], "0123456789abcdef")
        self.assertTrue(summary["stt2_active"])
        self.assertTrue(summary["stable_for_timeline_feed"])

    def test_native_global_canvas_summary_keeps_compact_occupancy_counts(self):
        with mock.patch(
            "tools.benchmark_subtitle_pipeline_variants.summarize_global_canvas_via_swift",
            return_value={
                "schema": "ai_subtitle_studio.subtitle_global_canvas.summary.v1",
                "backend": "swift",
                "segment_count": 3,
                "valid_segment_count": 3,
                "invalid_duration_count": 0,
                "non_monotonic_count": 0,
                "duration": 10.0,
                "bin_count": 5,
                "occupied_bin_count": 3,
                "empty_bin_count": 2,
                "dense_bin_count": 1,
                "max_bin_active": 2,
                "max_active_bin_index": 1,
                "avg_bin_active": 0.8,
                "coverage_duration": 4.0,
                "coverage_ratio": 0.4,
                "longest_empty_span_sec": 2.0,
                "longest_empty_start_sec": 4.0,
                "longest_empty_end_sec": 6.0,
                "max_active_segments": 2,
                "stable_for_global_canvas": True,
            },
        ):
            summary = _native_global_canvas_summary_for_variant(
                [{"start": 0.0, "end": 1.0, "text": "테스트"}],
                duration=10.0,
                bin_count=5,
            )

        self.assertEqual(summary["backend"], "swift")
        self.assertEqual(summary["occupied_bin_count"], 3)
        self.assertEqual(summary["dense_bin_count"], 1)
        self.assertEqual(summary["max_active_segments"], 2)
        self.assertEqual(summary["max_active_bin_index"], 1)
        self.assertEqual(summary["longest_empty_start_sec"], 4.0)
        self.assertEqual(summary["longest_empty_end_sec"], 6.0)
        self.assertTrue(summary["stable_for_global_canvas"])

    def test_quality_gate_tool_keeps_selective_variant_above_fast_loss(self):
        rows = [
            {
                "name": "phase1_parallel_full_stt1_stt2",
                "elapsed_sec": 10.0,
                "quality": {"quality_score": 71.563, "cer": 0.122, "timing_mae_sec": 0.739, "hypothesis_segments": 17},
                "readability": {"readability_score": 93.088},
                "final_segments": 17,
            },
            {
                "name": "phase1_serial_selective_stt2",
                "elapsed_sec": 31.0,
                "quality": {"quality_score": 72.986, "cer": 0.120, "timing_mae_sec": 0.647, "hypothesis_segments": 24},
                "readability": {"readability_score": 94.590},
                "final_segments": 24,
            },
        ]

        gated = apply_gate({"ranked_results": rows}, baseline_variant="auto")
        ranked = gated["ranked_results"]

        self.assertEqual(gated["baseline_variant"], "phase1_serial_selective_stt2")
        self.assertEqual(ranked[0]["name"], "phase1_serial_selective_stt2")
        self.assertFalse(ranked[1]["quality_gate_passed"])

    def test_score_against_reference_can_use_native_timing_metrics_without_changing_text_score(self):
        hypothesis = [{"start": 0.0, "end": 1.0, "text": "테스트"}]
        reference = [{"start": 0.0, "end": 1.0, "text": "테스트"}]

        with mock.patch(
            "tools.benchmark_subtitle_pipeline_variants.score_timing_metrics_via_swift",
            return_value=None,
        ), mock.patch(
            "tools.benchmark_subtitle_pipeline_variants.cpp_timing_metrics",
            return_value={
                "timing_mae_sec": 0.25,
                "overlap_score": 75.0,
                "matched_reference_indices": [0],
                "max_start_error_sec": 0.2,
                "max_end_error_sec": 0.3,
                "max_pair_timing_error_sec": 0.25,
                "worst_match_hypothesis_index": 0,
                "worst_match_reference_index": 0,
                "native_backend": "cpp",
            },
        ):
            score = score_against_reference(hypothesis, reference)

        self.assertEqual(score["timing_metrics_backend"], "cpp")
        self.assertEqual(score["timing_mae_sec"], 0.25)
        self.assertEqual(score["max_start_error_sec"], 0.2)
        self.assertEqual(score["max_end_error_sec"], 0.3)
        self.assertEqual(score["max_pair_timing_error_sec"], 0.25)
        self.assertEqual(score["worst_match_hypothesis_index"], 0)
        self.assertEqual(score["worst_match_reference_index"], 0)
        self.assertEqual(score["overlap_score"], 75.0)
        self.assertEqual(score["local_text_score"], 100.0)

    def test_best_mode_quality_gate_rejects_swift_assembled_below_fast_auto_high_floor(self):
        rows = [
            {"name": "mode_fast", "elapsed_sec": 9.0, "quality": {"quality_score": 75.0}, "readability": {"readability_score": 93.0}, "final_segments": 20},
            {"name": "mode_auto", "elapsed_sec": 12.0, "quality": {"quality_score": 80.0}, "readability": {"readability_score": 94.0}, "final_segments": 20},
            {"name": "mode_high", "elapsed_sec": 18.0, "quality": {"quality_score": 87.0}, "readability": {"readability_score": 95.0}, "final_segments": 20},
            {
                "name": ASSEMBLED_VARIANT_NAME,
                "elapsed_sec": 16.0,
                "quality": {"quality_score": 86.999},
                "readability": {"readability_score": 95.0},
                "final_segments": 20,
            },
        ]

        gated = apply_gate({"ranked_results": rows}, baseline_variant="best-mode")
        assembled = next(row for row in gated["ranked_results"] if row["name"] == ASSEMBLED_VARIANT_NAME)

        self.assertEqual(gated["baseline_variant"], "mode_high")
        self.assertTrue(bool(gated["strict_best_mode_floor"]))
        self.assertFalse(assembled["quality_gate_passed"])
        self.assertEqual(
            assembled["swift_assembly_quality_gate"]["reason"],
            "quality_score_below_best_fast_auto_high",
        )

    def test_best_mode_quality_gate_accepts_swift_assembled_at_fast_auto_high_floor(self):
        rows = [
            {"name": "mode_fast", "elapsed_sec": 9.0, "quality": {"quality_score": 75.0}, "readability": {"readability_score": 93.0}, "final_segments": 20},
            {"name": "mode_auto", "elapsed_sec": 12.0, "quality": {"quality_score": 80.0}, "readability": {"readability_score": 94.0}, "final_segments": 20},
            {"name": "mode_high", "elapsed_sec": 18.0, "quality": {"quality_score": 87.0}, "readability": {"readability_score": 95.0}, "final_segments": 20},
            {
                "name": ASSEMBLED_VARIANT_NAME,
                "elapsed_sec": 16.0,
                "quality": {"quality_score": 87.0},
                "readability": {"readability_score": 95.0},
                "final_segments": 20,
            },
        ]

        gated = apply_gate({"ranked_results": rows}, baseline_variant="best-mode")
        assembled = next(row for row in gated["ranked_results"] if row["name"] == ASSEMBLED_VARIANT_NAME)

        self.assertTrue(assembled["quality_gate_passed"])
        self.assertEqual(
            assembled["swift_assembly_quality_gate"]["reason"],
            "candidate_not_below_best_fast_auto_high",
        )

    def test_swift_assembled_benchmark_result_rolls_back_to_best_mode_when_floor_fails(self):
        rows = [
            {
                "name": "mode_high",
                "phase": "mode_profile",
                "elapsed_sec": 90.0,
                "final_segments": 56,
                "quality": {"quality_score": 87.5},
                "readability": {"readability_score": 94.7},
                "settings": {"subtitle_mode": "high"},
            },
            {
                "name": ASSEMBLED_VARIANT_NAME,
                "phase": "mode_profile",
                "elapsed_sec": 70.0,
                "final_segments": 57,
                "quality": {"quality_score": 87.4},
                "readability": {"readability_score": 94.6},
                "settings": {"native_subtitle_assembly_enabled": True},
            },
        ]
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, text in (("mode_high", "best"), (ASSEMBLED_VARIANT_NAME, "attempt")):
                folder = root / name
                folder.mkdir()
                (folder / "output_segments.json").write_text(text, encoding="utf-8")
                (folder / "raw_segments.json").write_text(text, encoding="utf-8")

            repaired = _enforce_swift_assembly_quality_floor(rows, root)

            assembled = next(row for row in repaired if row["name"] == ASSEMBLED_VARIANT_NAME)
            self.assertTrue(bool(assembled["native_subtitle_assembly_quality_floor_applied"]))
            self.assertEqual(assembled["native_subtitle_assembly_selected_result_variant"], "mode_high")
            self.assertEqual(assembled["quality"]["quality_score"], 87.5)
            self.assertEqual(assembled["candidate_attempt_quality"]["quality_score"], 87.4)
            self.assertEqual((root / ASSEMBLED_VARIANT_NAME / "output_segments.json").read_text(encoding="utf-8"), "best")
            self.assertEqual(
                (root / ASSEMBLED_VARIANT_NAME / "candidate_attempt_output_segments.json").read_text(encoding="utf-8"),
                "attempt",
            )

    def test_variant_chunk_settings_use_mode_specific_audio_path(self):
        base = _base_benchmark_settings("current")
        variants = benchmark_mode_profiles(base)
        by_name = {variant.name: variant for variant in variants}

        base_sig = _chunk_extraction_signature(base)
        auto_settings = _variant_chunk_settings(base, by_name["mode_auto"].overrides)
        auto_split_settings = _variant_chunk_settings(base, by_name["mode_auto_adaptive_split"].overrides)
        auto_drift_settings = _variant_chunk_settings(base, by_name["mode_auto_piecewise_drift"].overrides)
        auto_split_drift_settings = _variant_chunk_settings(base, by_name["mode_auto_adaptive_split_drift"].overrides)
        high_settings = _variant_chunk_settings(base, by_name["mode_high"].overrides)
        high_full_core_settings = _variant_chunk_settings(base, by_name["mode_high_full_core_overlap"].overrides)
        high_drift_settings = _variant_chunk_settings(base, by_name["mode_high_piecewise_drift"].overrides)

        self.assertTrue(bool(auto_settings.get("audio_chunk_routing_enabled")))
        self.assertTrue(bool(auto_settings.get("audio_chunk_route_vad_enabled")))
        self.assertTrue(bool(auto_split_settings.get("audio_chunk_route_split_enabled")))
        self.assertTrue(bool(auto_drift_settings.get("subtitle_timing_piecewise_drift_enabled")))
        self.assertTrue(bool(auto_split_drift_settings.get("audio_chunk_route_split_enabled")))
        self.assertTrue(bool(high_settings.get("audio_chunk_routing_enabled")))
        self.assertTrue(bool(high_settings.get("audio_chunk_route_vad_enabled")))
        self.assertNotEqual(base_sig, _chunk_extraction_signature(auto_settings))
        self.assertNotEqual(_chunk_extraction_signature(auto_settings), _chunk_extraction_signature(auto_split_settings))
        self.assertEqual(_chunk_extraction_signature(auto_settings), _chunk_extraction_signature(auto_drift_settings))
        self.assertEqual(_chunk_extraction_signature(auto_split_settings), _chunk_extraction_signature(auto_split_drift_settings))
        self.assertNotEqual(base_sig, _chunk_extraction_signature(high_settings))
        self.assertNotEqual(_chunk_extraction_signature(high_settings), _chunk_extraction_signature(high_full_core_settings))
        self.assertEqual(_chunk_extraction_signature(high_settings), _chunk_extraction_signature(high_drift_settings))

    def test_variant_chunk_signature_ignores_packaging_only_changes(self):
        base = _base_benchmark_settings("current")
        signature = _chunk_extraction_signature(base)
        packaging_only = _variant_chunk_settings(base, {"subtitle_lora_packaging_enabled": False})

        self.assertEqual(signature, _chunk_extraction_signature(packaging_only))

    def test_copy_chunk_dir_hardlinks_wavs_and_copies_metadata(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            wav = source / "vad_000_0.000.wav"
            meta = source / "vad_strict.json"
            wav.write_bytes(b"RIFF0000WAVEfmt ")
            meta.write_text("[]", encoding="utf-8")

            copied = _copy_chunk_dir(source, target)

            self.assertEqual(copied, target)
            self.assertTrue((target / wav.name).exists())
            self.assertTrue((target / meta.name).exists())
            self.assertEqual(os.stat(wav).st_ino, os.stat(target / wav.name).st_ino)
            self.assertNotEqual(os.stat(meta).st_ino, os.stat(target / meta.name).st_ino)

    def test_high_mode_can_enable_llm_when_explicit_model_is_supplied(self):
        variants = benchmark_mode_profiles(
            _base_benchmark_settings("current"),
            llm_model="OpenAI Codex ChatGPT",
        )
        by_name = {variant.name: variant for variant in variants}
        high = by_name["mode_high"]

        self.assertTrue(high.run_llm)
        self.assertEqual(high.overrides.get("selected_model"), "OpenAI Codex ChatGPT")
        self.assertEqual(high.overrides.get("selected_llm_provider"), "openai")

    @mock.patch(
        "tools.benchmark_subtitle_pipeline_variants.subtitle_engine.optimize_segments",
        return_value=[{"start": 411.76, "end": 413.74, "text": "- 아이스로 드릴까요? - 네네"}],
    )
    def test_run_postprocess_restores_inline_two_speaker_dialogue_in_auto_mode(self, _optimize_segments):
        settings = _base_benchmark_settings("current")
        settings["speaker_diarization_auto_enabled"] = True

        rows = _run_postprocess(
            [{"start": 411.76, "end": 413.74, "text": "- 아이스로 드릴까요? - 네네"}],
            [],
            settings,
            run_llm=False,
        )

        self.assertEqual(rows[0]["text"], "- 아이스로 드릴까요?\n- 네네")
        self.assertEqual(rows[0]["speaker_list"], ["00", "01"])

    def test_mode_lora_deep_profiles_cover_expected_ablation_paths(self):
        variants = benchmark_mode_lora_deep_profiles(_base_benchmark_settings("current"))
        by_name = {variant.name: variant for variant in variants}

        self.assertEqual(
            set(by_name),
            {
                "mode_fast_baseline",
                "mode_fast_lora_off",
                "mode_fast_deep_on",
                "mode_fast_lora_off_deep_on",
                "mode_auto_baseline",
                "mode_auto_lora_off",
                "mode_auto_deep_off",
                "mode_auto_lora_deep_off",
                "mode_high_baseline",
                "mode_high_lora_off",
                "mode_high_deep_off",
                "mode_high_lora_deep_off",
            },
        )

        fast_deep_on = by_name["mode_fast_deep_on"]
        self.assertEqual(fast_deep_on.method, "selective_ensemble")
        self.assertTrue(bool(fast_deep_on.overrides.get("deep_subtitle_policy_enabled")))
        self.assertTrue(bool(fast_deep_on.overrides.get("subtitle_output_selector_enabled")))

        auto_deep_off = by_name["mode_auto_deep_off"]
        self.assertEqual(auto_deep_off.method, "selective_ensemble")
        self.assertFalse(bool(auto_deep_off.overrides.get("deep_subtitle_policy_enabled")))
        self.assertFalse(bool(auto_deep_off.overrides.get("deep_timing_adjustment_enabled")))
        self.assertFalse(bool(auto_deep_off.overrides.get("subtitle_output_selector_enabled")))

        high_lora_deep_off = by_name["mode_high_lora_deep_off"]
        self.assertEqual(high_lora_deep_off.method, "selective_ensemble")
        self.assertFalse(bool(high_lora_deep_off.overrides.get("subtitle_lora_micro_merge_enabled")))
        self.assertFalse(bool(high_lora_deep_off.overrides.get("deep_segment_setting_policy_enabled")))

    def test_mode_lora_selective_profiles_cover_expected_ablation_paths(self):
        variants = benchmark_mode_lora_selective_profiles(_base_benchmark_settings("current"))
        by_name = {variant.name: variant for variant in variants}

        self.assertEqual(
            set(by_name),
            {
                "mode_fast_baseline",
                "mode_fast_lora_full",
                "mode_fast_lora_selective",
                "mode_auto_baseline",
                "mode_auto_lora_full",
                "mode_auto_lora_selective",
                "mode_high_baseline",
                "mode_high_lora_full",
                "mode_high_lora_selective",
            },
        )

        fast_selective = by_name["mode_fast_lora_selective"]
        self.assertEqual(fast_selective.method, "selective_ensemble")
        self.assertTrue(bool(fast_selective.overrides.get("subtitle_lora_micro_merge_enabled")))
        self.assertEqual(fast_selective.overrides.get("subtitle_lora_micro_merge_mode"), "readability_selective")

        auto_full = by_name["mode_auto_lora_full"]
        self.assertEqual(auto_full.method, "selective_ensemble")
        self.assertTrue(bool(auto_full.overrides.get("subtitle_lora_micro_merge_enabled")))
        self.assertEqual(auto_full.overrides.get("subtitle_lora_micro_merge_mode"), "full")

        high_selective = by_name["mode_high_lora_selective"]
        self.assertEqual(high_selective.method, "selective_ensemble")
        self.assertTrue(bool(high_selective.overrides.get("subtitle_lora_micro_merge_enabled")))
        self.assertEqual(high_selective.overrides.get("subtitle_lora_micro_merge_mode"), "readability_selective")

    def test_mode_lora_packaging_profiles_cover_expected_ablation_paths(self):
        variants = benchmark_mode_lora_packaging_profiles(_base_benchmark_settings("current"))
        by_name = {variant.name: variant for variant in variants}

        self.assertEqual(
            set(by_name),
            {
                "mode_fast_baseline",
                "mode_fast_packaging_full",
                "mode_fast_packaging_selective",
                "mode_auto_baseline",
                "mode_auto_packaging_full",
                "mode_auto_packaging_selective",
                "mode_high_baseline",
                "mode_high_packaging_full",
                "mode_high_packaging_selective",
            },
        )

        fast_full = by_name["mode_fast_packaging_full"]
        self.assertEqual(fast_full.method, "selective_ensemble")
        self.assertFalse(bool(fast_full.overrides.get("subtitle_lora_micro_merge_enabled")))
        self.assertTrue(bool(fast_full.overrides.get("subtitle_lora_packaging_enabled")))
        self.assertEqual(fast_full.overrides.get("subtitle_lora_packaging_mode"), "full")

        auto_selective = by_name["mode_auto_packaging_selective"]
        self.assertEqual(auto_selective.method, "selective_ensemble")
        self.assertTrue(bool(auto_selective.overrides.get("subtitle_lora_packaging_enabled")))
        self.assertEqual(auto_selective.overrides.get("subtitle_lora_packaging_mode"), "readability_selective")

        high_full = by_name["mode_high_packaging_full"]
        self.assertEqual(high_full.method, "selective_ensemble")
        self.assertFalse(bool(high_full.overrides.get("subtitle_lora_micro_merge_enabled")))
        self.assertTrue(bool(high_full.overrides.get("subtitle_lora_packaging_enabled")))

    def test_copy_chunk_dir_reuses_existing_target_when_source_is_missing(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "target"
            target.mkdir(parents=True)
            marker = target / "seed.txt"
            marker.write_text("ok", encoding="utf-8")

            reused = _copy_chunk_dir(root / "missing", target)

            self.assertEqual(reused, target)
            self.assertTrue(marker.exists())

    def test_readability_score_prefers_balanced_two_line_packaging(self):
        settings = {
            "subtitle_common_split_target_chars": 12,
            "subtitle_common_split_hard_max_chars": 18,
            "sub_max_cps": 16.0,
        }
        baseline = score_readability(
            [{"start": 0.0, "end": 3.0, "text": "자동차가 달리면 깨끗한 물이 남아요"}],
            settings,
        )
        packaged = score_readability(
            [{"start": 0.0, "end": 3.0, "text": "자동차가 달리면\n깨끗한 물이 남아요"}],
            settings,
        )

        self.assertGreater(float(packaged["readability_score"]), float(baseline["readability_score"]))
        self.assertEqual(int(packaged["two_line_segments"]), 1)

    def test_readability_score_penalizes_orphan_tail_line(self):
        settings = {
            "subtitle_common_split_target_chars": 12,
            "subtitle_common_split_hard_max_chars": 18,
            "sub_max_cps": 16.0,
        }
        balanced = score_readability(
            [{"start": 0.0, "end": 3.0, "text": "자동차가 달리면\n깨끗한 물이 남아요"}],
            settings,
        )
        orphan = score_readability(
            [{"start": 0.0, "end": 3.0, "text": "자동차가 달리면 깨끗한 물이\n남아요"}],
            settings,
        )

        self.assertGreater(float(balanced["readability_score"]), float(orphan["readability_score"]))
        self.assertEqual(int(orphan["orphan_line_segments"]), 1)

    def test_rank_rows_can_use_readability_objective(self):
        ranked = _rank_rows(
            [
                {
                    "name": "baseline",
                    "elapsed_sec": 10.0,
                    "error": "",
                    "quality": {"quality_score": 85.0},
                    "readability": {"readability_score": 70.0},
                },
                {
                    "name": "packaged",
                    "elapsed_sec": 11.0,
                    "error": "",
                    "quality": {"quality_score": 84.5},
                    "readability": {"readability_score": 92.0},
                },
            ],
            objective="readability",
        )

        self.assertEqual(ranked[0]["name"], "packaged")
        self.assertEqual(ranked[0]["primary_score_name"], "readability")

    def test_rank_rows_primary_first_prefers_higher_primary_score_over_faster_runtime(self):
        ranked = _rank_rows(
            [
                {
                    "name": "faster",
                    "elapsed_sec": 10.0,
                    "error": "",
                    "quality": {"quality_score": 85.0},
                    "readability": {"readability_score": 90.0},
                },
                {
                    "name": "slower_better",
                    "elapsed_sec": 12.0,
                    "error": "",
                    "quality": {"quality_score": 87.0},
                    "readability": {"readability_score": 94.0},
                },
            ],
            objective="readability",
            ranking_policy="primary_first",
        )

        self.assertEqual(ranked[0]["name"], "slower_better")
        self.assertEqual(ranked[0]["ranking_policy"], "primary_first")

    def test_reference_text_compaction_keeps_punctuation_but_ignores_parentheses(self):
        self.assertEqual(_compact_text("안녕(하세요)!..~"), "안녕하세요!..~")
        self.assertEqual(_compact_text("안녕 （하세요） !"), "안녕하세요!")


if __name__ == "__main__":
    unittest.main()
