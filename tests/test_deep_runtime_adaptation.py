import unittest

from core.personalization.deep_runtime_adaptation import adapt_runtime_settings_from_deep_events, summarize_deep_runtime_events


class DeepRuntimeAdaptationTests(unittest.TestCase):
    def test_summarizes_recent_quality_and_llm_failures(self):
        rows = [
            {
                "event_type": "quality_self_review",
                "decision": {"confidence_score": 58.0, "confidence_label": "red", "flags": ["high_cps"]},
                "features": {"cps": 19.0, "max_cps_setting": 12},
                "hard_case": True,
            },
            {"event_type": "llm_rollback", "decision": {"reason": "similarity"}, "features": {}},
            {"event_type": "llm_gate", "decision": {"call_llm": False}, "features": {}},
        ]

        summary = summarize_deep_runtime_events(rows)

        self.assertEqual(summary["event_count"], 3)
        self.assertGreater(summary["bad_quality_ratio"], 0)
        self.assertGreater(summary["llm_rollback_ratio"], 0)
        self.assertGreater(summary["llm_gate_skip_ratio"], 0)

    def test_summarizes_context_consistency_risks(self):
        rows = [
            {
                "event_type": "context_consistency",
                "decision": {"flags": ["repeat_previous", "overlap_previous"], "score": 76.0},
                "features": {"cps": 8.0, "max_cps_setting": 12},
                "hard_case": True,
            },
            {
                "event_type": "context_consistency",
                "decision": {"flags": ["cps_jump"], "score": 82.0},
                "features": {"cps": 18.0, "max_cps_setting": 12},
                "hard_case": True,
            },
            {
                "event_type": "context_repair",
                "decision": {
                    "applied": True,
                    "dropped_repeats": 1,
                    "shifted_starts": 1,
                    "extended_cps_segments": 1,
                    "dropped_hallucinations": 1,
                    "before_score": 80.0,
                    "after_score": 96.0,
                },
                "features": {"cps": 8.0, "max_cps_setting": 12},
                "hard_case": True,
            },
        ]

        summary = summarize_deep_runtime_events(rows)

        self.assertEqual(summary["counts"]["context_events"], 3)
        self.assertGreater(summary["context_repeat_ratio"], 0)
        self.assertGreater(summary["context_overlap_ratio"], 0)
        self.assertGreater(summary["context_cps_jump_ratio"], 0)
        self.assertGreater(summary["context_hallucination_ratio"], 0)

    def test_summarizes_lora_style_risks(self):
        rows = [
            {
                "event_type": "lora_style_consistency",
                "decision": {"flags": ["excluded_phrase", "style_cps_drift"], "score": 62.0},
                "features": {"cps": 22.0, "max_cps_setting": 12},
                "hard_case": True,
            },
        ]

        summary = summarize_deep_runtime_events(rows)

        self.assertGreater(summary["lora_style_risk_ratio"], 0)
        self.assertGreater(summary["lora_style_excluded_ratio"], 0)
        self.assertGreater(summary["lora_style_cps_ratio"], 0)
        self.assertEqual(summary["counts"]["lora_style_drift"], 1)

    def test_summarizes_subtitle_bundle_policy_events(self):
        rows = [
            {
                "event_type": "subtitle_bundle_policy",
                "decision": {"reason": "max_sec", "duration_sec": 360.0, "target_sec": 180.0},
                "features": {},
                "hard_case": True,
            },
            {
                "event_type": "subtitle_bundle_policy",
                "decision": {"reason": "confirmed_cut", "duration_sec": 95.0, "target_sec": 180.0},
                "features": {},
                "hard_case": False,
            },
        ]

        summary = summarize_deep_runtime_events(rows)

        self.assertGreater(summary["subtitle_bundle_max_ratio"], 0)
        self.assertGreater(summary["subtitle_bundle_cut_ratio"], 0)
        self.assertEqual(summary["counts"]["subtitle_bundle_events"], 2)

    def test_empty_store_keeps_settings_unchanged(self):
        import tempfile

        from core.personalization.lora_storage import initialize_lora_personalization_store

        rows = [
            {
                "event_type": "quality_self_review",
                "decision": {"confidence_score": 58.0, "confidence_label": "red", "flags": ["high_cps"]},
                "features": {"cps": 18.0, "max_cps_setting": 12},
                "hard_case": True,
            },
            {"event_type": "llm_rollback", "decision": {"reason": "similarity"}, "features": {}},
            {"event_type": "llm_verifier", "decision": {"accepted": False}, "features": {}},
            {"event_type": "hard_case_sample", "decision": {"reasons": ["high_cps"]}, "features": {"cps": 20.0, "max_cps_setting": 12}, "hard_case": True},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            settings, meta = adapt_runtime_settings_from_deep_events(
                {
                    "deep_runtime_adaptation_enabled": True,
                    "deep_runtime_adaptation_min_events": 1,
                    "split_length_threshold": 16,
                },
                store_dir=tmpdir,
            )

            summary = summarize_deep_runtime_events(rows)
            self.assertGreater(summary["high_cps_ratio"], 0)
            self.assertFalse(meta["applied"])
            self.assertEqual(settings["split_length_threshold"], 16)

    def test_adaptation_from_supplied_store_rows(self):
        import tempfile

        from core.personalization.lora_storage import append_deep_policy_events, initialize_lora_personalization_store

        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            append_deep_policy_events(
                [
                    {
                        "schema": "ai_subtitle_studio.deep_policy_event.v1",
                        "event_type": "quality_self_review",
                        "decision": {"confidence_score": 55.0, "confidence_label": "red", "flags": ["high_cps"]},
                        "features": {"cps": 20.0, "max_cps_setting": 12},
                        "hard_case": True,
                    },
                    {
                        "schema": "ai_subtitle_studio.deep_policy_event.v1",
                        "event_type": "llm_rollback",
                        "decision": {"reason": "similarity"},
                        "features": {},
                        "hard_case": True,
                    },
                ],
                tmpdir,
            )

            settings, meta = adapt_runtime_settings_from_deep_events(
                {
                    "deep_runtime_adaptation_enabled": True,
                    "deep_runtime_adaptation_min_events": 1,
                    "split_length_threshold": 16,
                    "sub_max_cps": 13,
                    "llm_confidence_gate_min_lora_score": 82.0,
                    "llm_confidence_gate_max_compact_ratio": 1.45,
                    "llm_verifier_min_similarity": 0.86,
                    "llm_verifier_max_length_delta_ratio": 0.16,
                },
                store_dir=tmpdir,
            )

            self.assertTrue(meta["applied"])
            self.assertLess(settings["split_length_threshold"], 16)
            self.assertLess(settings["sub_max_cps"], 13)
            self.assertGreater(settings["llm_confidence_gate_min_lora_score"], 82.0)
            self.assertGreater(settings["llm_verifier_min_similarity"], 0.86)

    def test_context_risks_adapt_sequence_and_context_settings(self):
        import tempfile

        from core.personalization.lora_storage import append_deep_policy_events, initialize_lora_personalization_store

        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            append_deep_policy_events(
                [
                    {
                        "schema": "ai_subtitle_studio.deep_policy_event.v1",
                        "event_type": "context_consistency",
                        "decision": {"flags": ["repeat_previous", "overlap_previous"], "score": 72.0},
                        "features": {"cps": 8.0, "max_cps_setting": 12},
                        "hard_case": True,
                    },
                    {
                        "schema": "ai_subtitle_studio.deep_policy_event.v1",
                        "event_type": "context_consistency",
                        "decision": {"flags": ["cps_jump"], "score": 80.0},
                        "features": {"cps": 19.0, "max_cps_setting": 12},
                        "hard_case": True,
                    },
                ],
                tmpdir,
            )

            settings, meta = adapt_runtime_settings_from_deep_events(
                {
                    "deep_runtime_adaptation_enabled": True,
                    "deep_runtime_adaptation_min_events": 1,
                    "subtitle_context_score_penalty_weight": 0.32,
                    "subtitle_context_repeat_window_sec": 4.0,
                    "subtitle_context_near_duplicate_ratio": 0.94,
                    "subtitle_context_cps_jump_ratio": 2.6,
                    "sub_dedup_window": 0.5,
                    "deep_sequence_smoothing_enabled": True,
                    "deep_sequence_max_shift_sec": 0.18,
                    "deep_sequence_bridge_gap_sec": 0.3,
                    "split_length_threshold": 16,
                },
                store_dir=tmpdir,
            )

            self.assertTrue(meta["applied"])
            self.assertGreater(settings["subtitle_context_score_penalty_weight"], 0.32)
            self.assertGreater(settings["sub_dedup_window"], 0.5)
            self.assertLess(settings["subtitle_context_near_duplicate_ratio"], 0.94)
            self.assertGreater(settings["deep_sequence_max_shift_sec"], 0.18)
            self.assertLess(settings["subtitle_context_cps_jump_ratio"], 2.6)

    def test_lora_style_risks_adapt_style_settings(self):
        import tempfile

        from core.personalization.lora_storage import append_deep_policy_events, initialize_lora_personalization_store

        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            append_deep_policy_events(
                [
                    {
                        "schema": "ai_subtitle_studio.deep_policy_event.v1",
                        "event_type": "lora_style_consistency",
                        "decision": {"flags": ["excluded_phrase", "style_cps_drift"], "score": 62.0},
                        "features": {"cps": 22.0, "max_cps_setting": 12},
                        "hard_case": True,
                    },
                    {
                        "schema": "ai_subtitle_studio.deep_policy_event.v1",
                        "event_type": "quality_self_review",
                        "decision": {"confidence_score": 88.0, "confidence_label": "green", "flags": []},
                        "features": {"cps": 8.0, "max_cps_setting": 12},
                        "hard_case": False,
                    },
                ],
                tmpdir,
            )

            settings, meta = adapt_runtime_settings_from_deep_events(
                {
                    "deep_runtime_adaptation_enabled": True,
                    "deep_runtime_adaptation_min_events": 1,
                    "subtitle_lora_style_score_penalty_weight": 0.22,
                    "subtitle_lora_style_min_profile_score": 28.0,
                    "subtitle_lora_style_max_cps_ratio": 2.0,
                    "llm_confidence_gate_min_lora_score": 82.0,
                },
                store_dir=tmpdir,
            )

            self.assertTrue(meta["applied"])
            self.assertGreater(settings["subtitle_lora_style_score_penalty_weight"], 0.22)
            self.assertGreater(settings["subtitle_lora_style_min_profile_score"], 28.0)
            self.assertLess(settings["subtitle_lora_style_max_cps_ratio"], 2.0)
            self.assertGreater(settings["llm_confidence_gate_min_lora_score"], 82.0)

    def test_subtitle_bundle_events_adapt_bundle_settings(self):
        import tempfile

        from core.personalization.lora_storage import append_deep_policy_events, initialize_lora_personalization_store

        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            append_deep_policy_events(
                [
                    {
                        "schema": "ai_subtitle_studio.deep_policy_event.v1",
                        "event_type": "subtitle_bundle_policy",
                        "decision": {"reason": "max_sec", "duration_sec": 360.0, "target_sec": 180.0},
                        "features": {},
                        "hard_case": True,
                    },
                    {
                        "schema": "ai_subtitle_studio.deep_policy_event.v1",
                        "event_type": "subtitle_bundle_policy",
                        "decision": {"reason": "confirmed_cut", "duration_sec": 120.0, "target_sec": 180.0},
                        "features": {},
                        "hard_case": False,
                    },
                ],
                tmpdir,
            )

            settings, meta = adapt_runtime_settings_from_deep_events(
                {
                    "deep_runtime_adaptation_enabled": True,
                    "deep_runtime_adaptation_min_events": 1,
                    "subtitle_bundle_target_sec": 180,
                    "subtitle_bundle_max_sec": 300,
                    "subtitle_bundle_min_sec": 90,
                    "chunk_time_limit": 180,
                },
                store_dir=tmpdir,
            )

            self.assertTrue(meta["applied"])
            self.assertLess(settings["subtitle_bundle_target_sec"], 180)
            self.assertLess(settings["subtitle_bundle_max_sec"], 300)
            self.assertEqual(settings["chunk_time_limit"], int(round(settings["subtitle_bundle_target_sec"])))
            self.assertTrue(settings["subtitle_bundle_use_confirmed_cuts"])


if __name__ == "__main__":
    unittest.main()
