import json
import tempfile
import unittest

from core.personalization.deep_policy_learning import (
    build_deep_policy_event_rows,
    build_hard_case_training_queue_items,
    build_user_edit_metric_event_rows,
    record_deep_policy_events_for_segments,
    record_user_edit_metric_events_for_truth_rows,
)
from core.personalization.lora_storage import initialize_lora_personalization_store, load_training_queue, store_paths


class DeepPolicyLearningTests(unittest.TestCase):
    def test_builds_policy_events_from_runtime_segment_metadata(self):
        rows = build_deep_policy_event_rows(
            [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "BMW X5 주행 소음",
                    "_deep_rerank_policy": {"best_score": 0.91, "margin": 0.12, "model": "test-model"},
                    "_deep_timing_policy": {"start_shift": 0.02, "end_shift": 0.04, "model": "test-model"},
                    "_stt_lattice_policy": {"enabled": True, "accepted": True, "replacements": 1, "confidence": 0.83},
                    "stt_ensemble_needs_llm_review": True,
                    "quality": {"confidence_score": 61.0, "confidence_label": "red", "flags": ["high_cps"]},
                    "_output_selector_policy": {
                        "task": "output_variant_selector",
                        "selected_index": 1,
                        "selected_name": "llm_source_gap_only",
                        "selected_score": 91.0,
                    },
                    "_context_consistency_policy": {
                        "task": "context_consistency",
                        "model": "context_sequence_heuristic_v1",
                        "flags": ["repeat_previous"],
                        "score": 78.0,
                    },
                    "_context_repair_policy": {
                        "task": "context_repair",
                        "model": "context_sequence_heuristic_v1",
                        "applied": True,
                        "dropped_repeats": 1,
                        "before_score": 82.0,
                        "after_score": 94.0,
                    },
                    "_lora_style_policy": {
                        "task": "lora_style_consistency",
                        "model": "lora_style_drift_heuristic_v1",
                        "flags": ["excluded_phrase"],
                        "score": 70.0,
                    },
                    "_subtitle_bundle_policy": {
                        "task": "subtitle_bundle_policy",
                        "model": "cut_lora_deep_bundle_policy_v1",
                        "reason": "confirmed_cut",
                        "duration_sec": 120.0,
                        "target_sec": 180.0,
                    },
                    "_cut_boundary_guard_policy": {
                        "task": "subtitle_cut_boundary_guard",
                        "action": "clamped_to_cut_scene",
                        "confidence": 72.0,
                        "scene_end": 3.0,
                    },
                    "_user_edit_metrics": {
                        "schema": "ai_subtitle_studio.user_edit_metrics.v1",
                        "task": "user_edit_metrics",
                        "changed": True,
                        "severity": "large",
                        "edit_burden_score": 54.0,
                        "text": {"edit_ratio": 0.22},
                        "timing": {"move_distance_sec": 0.4},
                        "split_merge": {"split_added": True},
                        "style": {"style_correction_count": 2},
                    },
                    "_llm_candidate_policy": {
                        "task": "llm_candidate_policy",
                        "accepted": False,
                        "reason": "not_candidate_or_minimal_edit:similarity:0.4",
                        "selected_candidate_id": "A",
                    },
                    "_lora_segment_settings": {"split_length_threshold": 14},
                    "_lora_generation_profile": {
                        "top_score": 90.0,
                        "_deep_setting_policy": {"confidence": 0.9, "applied_keys": ["split_length_threshold"]},
                    },
                    "_accuracy_decision_graph": {
                        "schema": "ai_subtitle_studio.subtitle_accuracy_pipeline.v1",
                        "decisions": [
                            {"task": "llm_gate", "call_llm": False, "confidence": 0.91},
                            {"task": "llm_rollback", "reason": "similarity:0.5", "fallback": "word_timing_split"},
                        ],
                    },
                }
            ],
            {
                "sub_max_cps": 12,
                "split_length_threshold": 16,
                "deep_hard_case_mining_enabled": True,
                "deep_quality_event_logging_enabled": True,
            },
            media_id="media-1",
            media_path="/tmp/a.mp4",
        )

        event_types = {row["event_type"] for row in rows}
        self.assertIn("subtitle_rerank", event_types)
        self.assertIn("timing_adjustment", event_types)
        self.assertIn("stt_lattice", event_types)
        self.assertIn("quality_self_review", event_types)
        self.assertIn("setting_policy", event_types)
        self.assertIn("output_variant_selector", event_types)
        self.assertIn("context_consistency", event_types)
        self.assertIn("context_repair", event_types)
        self.assertIn("lora_style_consistency", event_types)
        self.assertIn("subtitle_bundle_policy", event_types)
        self.assertIn("subtitle_cut_boundary_guard", event_types)
        self.assertIn("user_edit_metrics", event_types)
        self.assertIn("llm_candidate_policy", event_types)
        self.assertIn("llm_gate", event_types)
        self.assertIn("llm_rollback", event_types)
        self.assertIn("decision_explanation", event_types)
        self.assertIn("hard_case_sample", event_types)
        self.assertTrue(all(row["media_id"] == "media-1" for row in rows))
        explanation = next(row for row in rows if row["event_type"] == "decision_explanation")
        self.assertIn("llm_skipped", explanation["decision"]["actions"])
        self.assertIn("llm_candidate_rejected:not_candidate_or_minimal_edit:similarity:0.4", explanation["decision"]["actions"])
        self.assertIn("rollback:word_timing_split", explanation["decision"]["actions"])
        self.assertTrue(explanation["hard_case"])

    def test_records_policy_events_into_lora_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            result = record_deep_policy_events_for_segments(
                [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "테스트 자막",
                        "_deep_sequence_policy": {"changes": [{"type": "high_cps_extend"}], "model": "test-model"},
                    }
                ],
                {
                    "deep_policy_event_logging_enabled": True,
                    "subtitle_decision_explanation_logging_enabled": False,
                },
                store_dir=tmpdir,
            )
            paths = store_paths(tmpdir)
            lines = [json.loads(line) for line in paths["deep_policy_events"].read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(result["status"], "recorded")
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["event_type"], "sequence_smoothing")

    def test_hard_case_rows_are_prioritized_into_training_queue(self):
        rows = build_deep_policy_event_rows(
            [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "롤백 자막",
                    "_accuracy_decision_graph": {
                        "decisions": [
                            {"task": "llm_rollback", "reason": "similarity:0.5", "fallback": "word_timing_split"},
                        ],
                    },
                },
                {
                    "start": 1.2,
                    "end": 1.8,
                    "text": "스타일 이탈",
                    "_lora_style_policy": {"flags": ["style_cps_drift"], "score": 70.0},
                },
            ],
            {"sub_max_cps": 12, "subtitle_decision_explanation_logging_enabled": False},
            media_id="media-hard",
            media_path="/tmp/hard.mp4",
        )

        queue_items = build_hard_case_training_queue_items(rows)

        self.assertGreaterEqual(len(queue_items), 2)
        self.assertEqual(queue_items[0]["job_type"], "hard_case_subtitle_policy")
        self.assertLessEqual(queue_items[0]["priority"], queue_items[-1]["priority"])
        self.assertIn("llm_rollback", queue_items[0]["payload"]["hard_case_reasons"])

    def test_recording_policy_events_upserts_hard_case_training_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            result = record_deep_policy_events_for_segments(
                [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "검증 실패",
                        "_accuracy_decision_graph": {
                            "decisions": [
                                {"task": "llm_verifier", "accepted": False, "reason": "proper_noun_changed"},
                            ],
                        },
                    }
                ],
                {
                    "deep_policy_event_logging_enabled": True,
                    "subtitle_decision_explanation_logging_enabled": False,
                    "hardcase_training_queue_enabled": True,
                },
                store_dir=tmpdir,
            )
            queue = load_training_queue(tmpdir)

        self.assertEqual(result["status"], "recorded")
        self.assertGreaterEqual(result["queued_hard_cases"], 1)
        self.assertEqual(queue["items"][0]["job_type"], "hard_case_subtitle_policy")

    def test_records_decision_explanation_for_each_final_subtitle(self):
        rows = build_deep_policy_event_rows(
            [
                {
                    "start": 0.0,
                    "end": 1.2,
                    "text": "테스트 자막",
                    "_lora_generation_profile": {"top_score": 91.0, "used_kinds": {"truth_table": 2}},
                    "_accuracy_decision_graph": {
                        "decisions": [
                            {"task": "llm_gate", "call_llm": False, "reason": "skip_llm:high_lora_confidence", "confidence": 0.9}
                        ]
                    },
                }
            ],
            {
                "deep_policy_event_logging_enabled": True,
                "subtitle_decision_explanation_logging_enabled": True,
            },
        )

        explanations = [row for row in rows if row["event_type"] == "decision_explanation"]
        self.assertEqual(len(explanations), 1)
        self.assertEqual(explanations[0]["decision"]["lora_score"], 91.0)
        self.assertIn("llm_skipped", explanations[0]["decision"]["actions"])
        self.assertFalse(explanations[0]["hard_case"])

    def test_user_edit_metric_truth_rows_feed_deep_learning_and_queue(self):
        truth_rows = [
            {
                "media_id": "media-edit",
                "media_path": "/tmp/edit.mp4",
                "segment_id": "seg-1",
                "start_sec": 1.0,
                "end_sec": 2.4,
                "speech_training_text": "수정된\n자막입니다.",
                "settings_snapshot": {"split_length_threshold": 14},
                "user_edit_metrics": {
                    "schema": "ai_subtitle_studio.user_edit_metrics.v1",
                    "task": "user_edit_metrics",
                    "changed": True,
                    "severity": "large",
                    "edit_burden_score": 62.0,
                    "text": {"edit_ratio": 0.31},
                    "timing": {"move_distance_sec": 0.52},
                    "split_merge": {"split_added": True, "merge_likely": False},
                    "style": {"style_correction_count": 2},
                },
            }
        ]

        rows = build_user_edit_metric_event_rows(truth_rows, {"user_edit_metrics_hard_case_score": 24.0})

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "user_edit_metrics")
        self.assertTrue(rows[0]["hard_case"])
        self.assertEqual(rows[0]["applied_settings"]["split_length_threshold"], 14)

    def test_records_user_edit_metrics_into_deep_policy_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            result = record_user_edit_metric_events_for_truth_rows(
                [
                    {
                        "media_id": "media-edit",
                        "media_path": "/tmp/edit.mp4",
                        "segment_id": "seg-1",
                        "start_sec": 1.0,
                        "end_sec": 2.4,
                        "speech_training_text": "수정된 자막입니다.",
                        "user_edit_metrics": {
                            "schema": "ai_subtitle_studio.user_edit_metrics.v1",
                            "task": "user_edit_metrics",
                            "changed": True,
                            "severity": "large",
                            "edit_burden_score": 70.0,
                            "text": {"edit_ratio": 0.35},
                            "timing": {"move_distance_sec": 0.6},
                            "split_merge": {"split_added": False, "merge_likely": True},
                            "style": {"style_correction_count": 1},
                        },
                    }
                ],
                {"user_edit_metrics_deep_event_enabled": True},
                store_dir=tmpdir,
            )
            paths = store_paths(tmpdir)
            lines = [json.loads(line) for line in paths["deep_policy_events"].read_text(encoding="utf-8").splitlines() if line.strip()]
            queue = load_training_queue(tmpdir)

        self.assertEqual(result["status"], "recorded")
        self.assertEqual(result["appended_rows"], 1)
        self.assertEqual(lines[0]["event_type"], "user_edit_metrics")
        self.assertEqual(queue["items"][0]["job_type"], "hard_case_subtitle_policy")


if __name__ == "__main__":
    unittest.main()
