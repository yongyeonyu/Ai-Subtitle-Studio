import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.benchmark_subtitle_pipeline_variants import (
    _copy_chunk_dir,
    _compact_text,
    _rank_rows,
    _base_benchmark_settings,
    _chunk_extraction_signature,
    _variant_chunk_settings,
    benchmark_mode_lora_deep_profiles,
    benchmark_mode_lora_packaging_profiles,
    benchmark_mode_lora_selective_profiles,
    benchmark_mode_profiles,
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
                "mode_high_piecewise_drift",
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

        high_drift = by_name["mode_high_piecewise_drift"]
        self.assertEqual(high_drift.method, "selective_ensemble")
        self.assertTrue(bool(high_drift.overrides.get("subtitle_timing_piecewise_drift_enabled")))

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
        high_drift_settings = _variant_chunk_settings(base, by_name["mode_high_piecewise_drift"].overrides)

        self.assertTrue(bool(auto_settings.get("audio_chunk_routing_enabled")))
        self.assertTrue(bool(auto_settings.get("audio_chunk_route_vad_enabled")))
        self.assertTrue(bool(auto_split_settings.get("audio_chunk_route_split_enabled")))
        self.assertTrue(bool(auto_drift_settings.get("subtitle_timing_piecewise_drift_enabled")))
        self.assertTrue(bool(auto_split_drift_settings.get("audio_chunk_route_split_enabled")))
        self.assertFalse(bool(high_settings.get("audio_chunk_routing_enabled")))
        self.assertNotEqual(base_sig, _chunk_extraction_signature(auto_settings))
        self.assertNotEqual(_chunk_extraction_signature(auto_settings), _chunk_extraction_signature(auto_split_settings))
        self.assertEqual(_chunk_extraction_signature(auto_settings), _chunk_extraction_signature(auto_drift_settings))
        self.assertEqual(_chunk_extraction_signature(auto_split_settings), _chunk_extraction_signature(auto_split_drift_settings))
        self.assertNotEqual(base_sig, _chunk_extraction_signature(high_settings))
        self.assertEqual(_chunk_extraction_signature(high_settings), _chunk_extraction_signature(high_drift_settings))

    def test_variant_chunk_signature_ignores_packaging_only_changes(self):
        base = _base_benchmark_settings("current")
        signature = _chunk_extraction_signature(base)
        packaging_only = _variant_chunk_settings(base, {"subtitle_lora_packaging_enabled": False})

        self.assertEqual(signature, _chunk_extraction_signature(packaging_only))

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
