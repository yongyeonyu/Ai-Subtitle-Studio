import unittest

from core.engine.subtitle_accuracy_pipeline import (
    append_accuracy_decision,
    annotate_subtitle_auto_review,
    annotate_subtitle_completion_report,
    annotate_subtitle_context_consistency,
    annotate_subtitle_lora_style_consistency,
    annotate_subtitle_stage_confidence,
    llm_gate_decision,
    llm_minimize_decision,
    repair_subtitle_context_consistency,
    select_best_subtitle_output,
    subtitle_accuracy_metrics,
    subtitle_auto_review_items,
    subtitle_auto_review_summary,
    subtitle_completion_report,
    subtitle_context_consistency_metrics,
    subtitle_decision_explanations,
    subtitle_lora_style_consistency_metrics,
    subtitle_output_variant_score,
    subtitle_stage_confidence,
    verify_llm_chunks_for_subtitle,
)


class SubtitleAccuracyPipelineTests(unittest.TestCase):
    def test_llm_gate_skips_when_lora_confidence_is_high(self):
        decision = llm_gate_decision(
            {"start": 0.0, "end": 2.0, "text": "오늘은 행사장에 왔습니다"},
            {
                "llm_confidence_gate_enabled": True,
                "llm_confidence_gate_min_lora_score": 82.0,
                "llm_confidence_gate_max_compact_ratio": 1.45,
                "sub_max_duration": 6.0,
            },
            {"top_score": 94.0},
            text="오늘은 행사장에 왔습니다",
            threshold=16,
            duration=2.0,
        )

        self.assertFalse(decision["call_llm"])
        self.assertGreater(decision["confidence"], 0.5)

    def test_llm_minimize_records_avoided_call_for_strong_gate_skip(self):
        gate = llm_gate_decision(
            {"start": 0.0, "end": 2.0, "text": "오늘은 행사장에 왔습니다"},
            {
                "llm_confidence_gate_enabled": True,
                "llm_confidence_gate_min_lora_score": 82.0,
                "llm_minimize_min_gate_confidence": 0.7,
                "llm_minimize_required_signal_score": 82.0,
                "sub_max_duration": 6.0,
            },
            {"top_score": 94.0},
            text="오늘은 행사장에 왔습니다",
            threshold=16,
            duration=2.0,
        )
        minimize = llm_minimize_decision(
            {"_uncertainty_policy": {"bucket": "easy"}},
            {"llm_minimize_enabled": True, "llm_minimize_min_gate_confidence": 0.7, "llm_minimize_required_signal_score": 82.0},
            gate,
        )

        self.assertTrue(minimize["skip_llm"])
        self.assertTrue(minimize["avoided_call"])
        self.assertEqual(minimize["reason"], "skip_llm:strong_lora_deep_signal")
        self.assertEqual(minimize["uncertainty_bucket"], "easy")

    def test_llm_minimize_keeps_llm_for_gate_requested_regions(self):
        gate = llm_gate_decision(
            {"start": 0.0, "end": 7.0, "text": "이 문장은 너무 길어서 분리가 필요합니다"},
            {"llm_confidence_gate_min_lora_score": 82.0, "sub_max_duration": 6.0},
            {"top_score": 20.0},
            text="이 문장은 너무 길어서 분리가 필요합니다",
            threshold=8,
            duration=7.0,
        )
        minimize = llm_minimize_decision({}, {"llm_minimize_enabled": True}, gate)

        self.assertFalse(minimize["skip_llm"])
        self.assertFalse(minimize["avoided_call"])
        self.assertEqual(minimize["reason"], "gate_requested_llm")

    def test_llm_gate_calls_when_text_is_long_or_lora_is_weak(self):
        decision = llm_gate_decision(
            {"start": 0.0, "end": 7.0, "text": "이 문장은 너무 길어서 분리가 필요합니다 그리고 근거도 약합니다"},
            {"llm_confidence_gate_min_lora_score": 82.0, "sub_max_duration": 6.0},
            {"top_score": 20.0},
            text="이 문장은 너무 길어서 분리가 필요합니다 그리고 근거도 약합니다",
            threshold=12,
            duration=7.0,
        )

        self.assertTrue(decision["call_llm"])
        self.assertIn("low_lora_score", decision["reasons"])

    def test_llm_gate_skips_when_deep_or_stt_signal_is_strong(self):
        decision = llm_gate_decision(
            {
                "start": 0.0,
                "end": 2.0,
                "text": "짧고 안정적인 후보입니다",
                "_stt_lattice_policy": {"confidence": 0.94, "accepted": True},
                "_deep_candidate_selector_policy": {"confidence": 0.91},
            },
            {"llm_confidence_gate_min_lora_score": 82.0, "sub_max_duration": 6.0},
            {"top_score": 20.0},
            text="짧고 안정적인 후보입니다",
            threshold=16,
            duration=2.0,
        )

        self.assertFalse(decision["call_llm"])
        self.assertNotIn("low_lora_score", decision["reasons"])
        self.assertGreaterEqual(decision["combined_signal_score"], 94.0)

    def test_llm_verifier_rejects_hallucinated_or_timecoded_output(self):
        chunks, meta = verify_llm_chunks_for_subtitle(
            "안녕하세요 반갑습니다",
            ["[00:01.0] 안녕하세요", "Thank you for watching"],
            {"llm_verifier_enabled": True},
            {"top_score": 93.0},
        )

        self.assertIsNone(chunks)
        self.assertFalse(meta["accepted"])

    def test_llm_verifier_accepts_source_preserving_split(self):
        chunks, meta = verify_llm_chunks_for_subtitle(
            "처음입니다 다음입니다",
            ["처음입니다", "다음입니다"],
            {"llm_verifier_min_similarity": 0.86},
            {"top_score": 93.0},
        )

        self.assertEqual(chunks, ["처음입니다", "다음입니다"])
        self.assertTrue(meta["accepted"])

    def test_llm_verifier_rejects_number_changes(self):
        chunks, meta = verify_llm_chunks_for_subtitle(
            "이 영상은 24분입니다",
            ["이 영상은 44분입니다"],
            {"llm_verifier_min_similarity": 0.5},
            {"top_score": 93.0},
        )

        self.assertIsNone(chunks)
        self.assertFalse(meta["accepted"])
        self.assertEqual(meta["reason"], "source_preservation:number_changed")

    def test_llm_verifier_rejects_added_proper_nouns(self):
        chunks, meta = verify_llm_chunks_for_subtitle(
            "행사장에 도착했습니다",
            ["BMW 행사장에 도착했습니다"],
            {"llm_verifier_min_similarity": 0.5},
            {"top_score": 93.0},
        )

        self.assertIsNone(chunks)
        self.assertEqual(meta["reason"], "source_preservation:proper_noun_changed")

    def test_llm_verifier_rejects_interjection_deletion(self):
        chunks, meta = verify_llm_chunks_for_subtitle(
            "아 진짜 좋네요",
            ["진짜 좋네요"],
            {"llm_verifier_min_similarity": 0.5},
            {"top_score": 93.0},
        )

        self.assertIsNone(chunks)
        self.assertEqual(meta["reason"], "source_preservation:interjection_deleted")

    def test_llm_verifier_rejects_added_content_tokens(self):
        chunks, meta = verify_llm_chunks_for_subtitle(
            "좋습니다",
            ["현대차가 좋습니다"],
            {"llm_verifier_min_similarity": 0.5},
            {"top_score": 93.0},
        )

        self.assertIsNone(chunks)
        self.assertEqual(meta["reason"], "source_preservation:added_content_token")

    def test_accuracy_metrics_count_gate_skips_and_rollbacks(self):
        gate = {"schema": "ai_subtitle_studio.subtitle_accuracy_pipeline.v1", "task": "llm_gate", "call_llm": False}
        rollback = {"schema": "ai_subtitle_studio.subtitle_accuracy_pipeline.v1", "task": "llm_rollback", "reason": "similarity"}
        segment = append_accuracy_decision({"start": 0.0, "end": 1.0, "text": "테스트"}, gate)
        segment = append_accuracy_decision(segment, rollback)

        summary = subtitle_accuracy_metrics([segment], {"sub_max_cps": 12, "sub_max_duration": 6})

        self.assertEqual(summary["total_segments"], 1)
        self.assertEqual(summary["llm_gate_skipped_segments"], 1)
        self.assertEqual(summary["llm_verifier_rollbacks"], 1)

    def test_decision_explanations_show_gate_lora_and_rollback_reasons(self):
        gate = {"schema": "ai_subtitle_studio.subtitle_accuracy_pipeline.v1", "task": "llm_gate", "call_llm": False, "reason": "skip_llm:high_lora_confidence", "confidence": 0.91}
        candidate = {"schema": "ai_subtitle_studio.llm_candidate_policy.v1", "task": "llm_candidate_policy", "accepted": True, "reason": "candidate_match", "selected_candidate_id": "A"}
        verifier = {"schema": "ai_subtitle_studio.subtitle_accuracy_pipeline.v1", "task": "llm_verifier", "accepted": False, "reason": "similarity:0.5", "similarity": 0.5}
        rollback = {"schema": "ai_subtitle_studio.subtitle_accuracy_pipeline.v1", "task": "llm_rollback", "fallback": "safe_split"}
        segment = append_accuracy_decision({
            "start": 0.0,
            "end": 1.0,
            "text": "테스트",
            "_lora_generation_profile": {"top_score": 95.0},
            "_cut_boundary_guard_policy": {"action": "clamped_to_cut_scene"},
        }, gate)
        segment = append_accuracy_decision(segment, candidate)
        segment = append_accuracy_decision(segment, verifier)
        segment = append_accuracy_decision(segment, rollback)

        explanations = subtitle_decision_explanations([segment])

        self.assertEqual(explanations[0]["lora_score"], 95.0)
        self.assertIn("llm_skipped", explanations[0]["actions"])
        self.assertIn("llm_candidate:candidate_match", explanations[0]["actions"])
        self.assertIn("rollback:safe_split", explanations[0]["actions"])
        self.assertIn("cut_boundary:clamped_to_cut_scene", explanations[0]["actions"])
        self.assertEqual(explanations[0]["llm_candidate_policy"]["selected_candidate_id"], "A")
        self.assertEqual(explanations[0]["llm_verifier"]["reason"], "similarity:0.5")

    def test_output_variant_selector_prefers_higher_quality_lower_risk(self):
        weak = {
            "name": "weak",
            "segments": [
                {"start": 0.0, "end": 0.5, "text": "너무긴자막입니다", "quality": {"confidence_score": 58.0, "confidence_label": "red"}},
            ],
        }
        strong = {
            "name": "strong",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": "좋은 자막", "quality": {"confidence_score": 91.0, "confidence_label": "green"}},
            ],
        }

        selected, decision = select_best_subtitle_output([weak, strong], {"sub_max_cps": 12, "sub_max_duration": 6})

        self.assertEqual(selected[0]["text"], "좋은 자막")
        self.assertEqual(decision["selected_index"], 1)
        self.assertGreater(subtitle_output_variant_score(strong["segments"])["score"], subtitle_output_variant_score(weak["segments"])["score"])

    def test_context_consistency_penalizes_adjacent_repeats_and_overlaps(self):
        metrics = subtitle_context_consistency_metrics(
            [
                {"start": 0.0, "end": 1.0, "text": "같은 자막"},
                {"start": 0.8, "end": 1.8, "text": "같은 자막"},
            ],
            {"subtitle_context_consistency_enabled": True},
        )

        self.assertLess(metrics["score"], 100.0)
        self.assertEqual(metrics["repeated_segments"], 1)
        self.assertEqual(metrics["overlap_segments"], 1)

    def test_context_consistency_annotates_risky_segments_for_learning(self):
        annotated = annotate_subtitle_context_consistency(
            [
                {"start": 0.0, "end": 1.0, "text": "같은 자막"},
                {"start": 0.8, "end": 1.8, "text": "같은 자막"},
            ],
            {"subtitle_context_consistency_enabled": True},
        )

        self.assertNotIn("_context_consistency_policy", annotated[0])
        policy = annotated[1]["_context_consistency_policy"]
        self.assertEqual(policy["task"], "context_consistency")
        self.assertIn("repeat_previous", policy["flags"])
        self.assertIn("overlap_previous", policy["flags"])

    def test_context_repair_drops_exact_repeats_and_fixes_overlaps(self):
        repaired, decision = repair_subtitle_context_consistency(
            [
                {"start": 0.0, "end": 1.0, "text": "같은 자막"},
                {"start": 0.8, "end": 1.8, "text": "같은 자막"},
                {"start": 1.7, "end": 2.4, "text": "다른 자막"},
            ],
            {
                "subtitle_context_consistency_enabled": True,
                "subtitle_context_repair_enabled": True,
                "sub_min_duration": 0.2,
            },
        )

        self.assertTrue(decision["applied"])
        self.assertEqual(decision["dropped_repeats"], 1)
        self.assertEqual(len(repaired), 2)
        self.assertGreaterEqual(repaired[1]["start"], repaired[0]["end"])
        self.assertGreater(decision["after_score"], decision["before_score"])

    def test_context_repair_extends_cps_jump_into_safe_gap(self):
        repaired, decision = repair_subtitle_context_consistency(
            [
                {"start": 0.0, "end": 2.0, "text": "느린 자막"},
                {"start": 3.0, "end": 3.2, "text": "갑자기너무빠른자막입니다"},
                {"start": 4.0, "end": 5.0, "text": "다음 자막"},
            ],
            {
                "subtitle_context_consistency_enabled": True,
                "subtitle_context_repair_enabled": True,
                "subtitle_context_repair_cps_jumps_enabled": True,
                "subtitle_context_repair_cps_max_extend_sec": 0.4,
                "sub_max_cps": 12,
            },
        )

        self.assertTrue(decision["applied"])
        self.assertEqual(decision["extended_cps_segments"], 1)
        self.assertGreater(repaired[1]["end"], 3.2)
        self.assertLessEqual(repaired[1]["end"], 3.6)

    def test_context_repair_drops_empty_and_placeholder_hallucinations(self):
        repaired, decision = repair_subtitle_context_consistency(
            [
                {"start": 0.0, "end": 0.4, "text": ""},
                {"start": 0.5, "end": 1.5, "text": "Thank you for watching!"},
                {"start": 1.6, "end": 2.6, "text": "정상 자막"},
            ],
            {
                "subtitle_context_consistency_enabled": True,
                "subtitle_context_repair_enabled": True,
                "subtitle_context_repair_drop_empty_enabled": True,
                "subtitle_context_repair_drop_hallucinations_enabled": True,
            },
        )

        self.assertTrue(decision["applied"])
        self.assertEqual(decision["dropped_empty"], 1)
        self.assertEqual(decision["dropped_hallucinations"], 1)
        self.assertEqual([row["text"] for row in repaired], ["정상 자막"])

    def test_lora_style_consistency_flags_excluded_and_style_drift(self):
        profile = {
            "top_score": 94.0,
            "examples": [{"output": "짧은 자막", "cps": 8.0}, {"output": "행사장 도착", "cps": 9.0}],
            "exclusions": [{"text": "삭제표현"}],
        }
        annotated = annotate_subtitle_lora_style_consistency(
            [
                {
                    "start": 0.0,
                    "end": 0.8,
                    "text": "삭제표현이 포함된 너무 긴 자막입니다",
                    "_lora_generation_profile": profile,
                },
            ],
            {
                "subtitle_lora_style_consistency_enabled": True,
                "subtitle_lora_style_max_length_drift_ratio": 0.5,
                "subtitle_lora_style_max_cps_ratio": 1.2,
                "sub_max_cps": 12,
            },
        )

        policy = annotated[0]["_lora_style_policy"]
        self.assertEqual(policy["task"], "lora_style_consistency")
        self.assertIn("excluded_phrase", policy["flags"])
        self.assertIn("style_length_drift", policy["flags"])

        metrics = subtitle_lora_style_consistency_metrics(annotated, {"subtitle_lora_style_consistency_enabled": True})
        self.assertEqual(metrics["style_drift_segments"], 1)
        self.assertEqual(metrics["excluded_phrase_segments"], 1)
        self.assertLess(metrics["score"], 100.0)

    def test_output_variant_selector_penalizes_lora_style_drift(self):
        profile = {
            "top_score": 95.0,
            "examples": [{"output": "행사장 도착", "cps": 8.0}, {"output": "무대 시작", "cps": 8.5}],
            "exclusions": [{"text": "삭제표현"}],
        }
        drift = {
            "name": "style_drift",
            "segments": [
                {
                    "start": 0.0,
                    "end": 0.8,
                    "text": "삭제표현이 포함된 너무 긴 자막입니다",
                    "quality": {"confidence_score": 92.0, "confidence_label": "green"},
                    "_lora_generation_profile": profile,
                },
            ],
        }
        stable = {
            "name": "style_stable",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.2,
                    "text": "행사장 도착",
                    "quality": {"confidence_score": 92.0, "confidence_label": "green"},
                    "_lora_generation_profile": profile,
                },
            ],
        }

        selected, decision = select_best_subtitle_output(
            [drift, stable],
            {
                "sub_max_cps": 12,
                "subtitle_lora_style_score_penalty_weight": 0.35,
                "subtitle_lora_style_max_length_drift_ratio": 0.5,
            },
        )

        self.assertEqual(selected[0]["text"], "행사장 도착")
        self.assertEqual(decision["selected_index"], 1)
        self.assertGreater(decision["variants"][0]["score"], decision["variants"][1]["score"])

    def test_output_variant_selector_uses_context_consistency_score(self):
        repeated = {
            "name": "repeated",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "반복 자막", "quality": {"confidence_score": 92.0, "confidence_label": "green"}},
                {"start": 1.1, "end": 2.0, "text": "반복 자막", "quality": {"confidence_score": 92.0, "confidence_label": "green"}},
            ],
        }
        stable = {
            "name": "stable",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "첫 번째 자막", "quality": {"confidence_score": 92.0, "confidence_label": "green"}},
                {"start": 1.1, "end": 2.0, "text": "두 번째 자막", "quality": {"confidence_score": 92.0, "confidence_label": "green"}},
            ],
        }

        selected, decision = select_best_subtitle_output([repeated, stable], {"sub_max_cps": 12})

        self.assertEqual(selected[0]["text"], "첫 번째 자막")
        self.assertEqual(decision["selected_index"], 1)
        self.assertGreater(
            decision["variants"][0]["score_meta"]["metrics"]["context_consistency_score"],
            decision["variants"][1]["score_meta"]["metrics"]["context_consistency_score"],
        )

    def test_auto_review_collects_only_risky_subtitle_rows(self):
        rollback = {"schema": "ai_subtitle_studio.subtitle_accuracy_pipeline.v1", "task": "llm_rollback", "fallback": "safe_split"}
        risky = append_accuracy_decision(
            {
                "start": 1.0,
                "end": 1.4,
                "text": "너무빠른자막입니다",
                "quality": {"confidence_score": 44.0, "confidence_label": "red"},
                "_lora_generation_profile": {"top_score": 35.0},
                "stt_ensemble_needs_llm_review": True,
                "stt_candidates": [
                    {"source": "STT1", "text": "여기로 가자", "score": 0.84},
                    {"source": "STT2", "text": "이거로 하자", "score": 0.82},
                ],
                "_cut_boundary_guard_policy": {"action": "clamped_to_cut_scene", "confidence": 45.0},
            },
            rollback,
        )
        safe = {
            "start": 2.0,
            "end": 4.0,
            "text": "안정적인 자막",
            "quality": {"confidence_score": 96.0, "confidence_label": "green"},
            "_lora_generation_profile": {"top_score": 92.0},
        }

        items = subtitle_auto_review_items(
            [safe, risky],
            {"sub_max_cps": 12, "sub_max_duration": 6, "subtitle_auto_review_lora_min_score": 58},
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["index"], 1)
        self.assertEqual(items[0]["severity"], "red")
        self.assertIn("quality_red", items[0]["issue_types"])
        self.assertIn("stt_candidate_conflict", items[0]["issue_types"])
        self.assertIn("llm_rollback", items[0]["issue_types"])
        self.assertIn("cut_boundary_crossing", items[0]["issue_types"])
        self.assertIn("high_cps", items[0]["issue_types"])

    def test_auto_review_annotation_persists_summary_and_row_flags(self):
        rows = annotate_subtitle_auto_review(
            [
                {"start": 0.0, "end": 1.0, "text": "정상 자막", "quality": {"confidence_score": 95.0, "confidence_label": "green"}},
                {
                    "start": 1.0,
                    "end": 1.5,
                    "text": "확인필요자막입니다",
                    "quality": {"confidence_score": 55.0, "confidence_label": "yellow"},
                    "_llm_rollback_policy": {"reason": "similarity", "fallback": "safe_split"},
                },
            ],
            {"sub_max_cps": 12, "subtitle_auto_review_seconds_per_item": 10},
        )
        summary = subtitle_auto_review_summary(rows, {"sub_max_cps": 12})

        self.assertIn("subtitle_auto_review_summary", rows[0])
        self.assertNotIn("subtitle_auto_review", rows[0])
        self.assertEqual(rows[1]["subtitle_auto_review_severity"], "red")
        self.assertIn("llm_rollback", rows[1]["subtitle_auto_review_reasons"])
        self.assertEqual(summary["issue_count"], 1)
        self.assertEqual(summary["severity_counts"]["red"], 1)

    def test_stage_confidence_exposes_cut_stt_llm_lora_and_final_labels(self):
        segment = append_accuracy_decision(
            {
                "start": 0.0,
                "end": 1.0,
                "text": "확인 필요",
                "score": 0.91,
                "_lora_generation_profile": {"top_score": 90.0},
                "_cut_boundary_guard_policy": {"action": "clamped_to_cut_scene", "confidence": 45.0},
                "quality": {"confidence_score": 88.0, "confidence_label": "green"},
            },
            {"schema": "ai_subtitle_studio.subtitle_accuracy_pipeline.v1", "task": "llm_gate", "call_llm": False, "confidence": 0.91},
        )

        confidence = subtitle_stage_confidence(segment, {})

        self.assertEqual(confidence["stage_order"], ["cut", "stt", "llm", "lora", "final"])
        self.assertEqual(confidence["stages"]["cut"]["label"], "red")
        self.assertEqual(confidence["stages"]["stt"]["label"], "green")
        self.assertEqual(confidence["stages"]["llm"]["label"], "green")
        self.assertEqual(confidence["stages"]["lora"]["label"], "green")
        self.assertEqual(confidence["overall_label"], "red")

    def test_stage_confidence_annotation_adds_summary_counts(self):
        rows = annotate_subtitle_stage_confidence(
            [
                {"start": 0.0, "end": 1.0, "text": "좋음", "quality": {"confidence_score": 95.0, "confidence_label": "green"}},
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "롤백",
                    "_llm_rollback_policy": {"reason": "similarity", "fallback": "safe_split"},
                    "quality": {"confidence_score": 70.0, "confidence_label": "yellow"},
                },
            ],
            {},
        )

        self.assertEqual(rows[0]["subtitle_confidence_summary"]["total_segments"], 2)
        self.assertEqual(rows[1]["subtitle_confidence_label"], "red")
        self.assertEqual(rows[1]["subtitle_stage_confidence"]["stages"]["llm"]["label"], "red")

    def test_completion_report_summarizes_review_cost_and_recommendations(self):
        rows = annotate_subtitle_auto_review(
            [
                {"start": 0.0, "end": 1.0, "text": "좋은 자막", "quality": {"confidence_score": 95.0, "confidence_label": "green"}, "_lora_generation_profile": {"top_score": 92.0}},
                {
                    "start": 1.0,
                    "end": 1.4,
                    "text": "너무빠른자막입니다",
                    "quality": {"confidence_score": 45.0, "confidence_label": "red"},
                    "_llm_rollback_policy": {"reason": "similarity", "fallback": "safe_split"},
                },
            ],
            {"sub_max_cps": 12},
        )
        rows = annotate_subtitle_stage_confidence(rows, {})

        report = subtitle_completion_report(rows, {"sub_max_cps": 12})
        annotated = annotate_subtitle_completion_report(rows, {"sub_max_cps": 12})

        self.assertEqual(report["total_subtitles"], 2)
        self.assertEqual(report["red_risk_rows"], 1)
        self.assertEqual(report["llm_rollback_count"], 1)
        self.assertGreater(report["estimated_review_sec"], 0)
        self.assertIn("Review red auto-review rows first.", report["recommended_actions"])
        self.assertIn("subtitle_completion_report", annotated[0])


if __name__ == "__main__":
    unittest.main()
