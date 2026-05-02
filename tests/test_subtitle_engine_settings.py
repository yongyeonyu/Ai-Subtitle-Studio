# Version: 03.10.03
# Phase: PHASE2
import unittest
import importlib
import json
import sys
import tempfile
from pathlib import Path

import config
from core.engine import subtitle_engine


class SubtitleEngineSettingsTests(unittest.TestCase):
    def test_final_gap_settings_apply_as_last_timing_pass(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "A"},
            {"start": 2.0, "end": 3.0, "text": "B"},
            {"start": 6.0, "end": 7.0, "text": "C"},
        ]

        adjusted = subtitle_engine.apply_final_gap_settings(
            segments,
            {
                "continuous_threshold": 1.5,
                "gap_push_rate": 0.8,
                "gap_pull_rate": 0.2,
                "single_subtitle_end": 0.2,
                "sub_min_duration": 0.2,
            },
        )

        self.assertEqual([seg["text"] for seg in adjusted], ["A", "B", "C"])
        self.assertAlmostEqual(adjusted[0]["end"], 1.8, places=3)
        self.assertAlmostEqual(adjusted[1]["start"], 1.8, places=3)
        self.assertAlmostEqual(adjusted[1]["end"], 3.2, places=3)
        self.assertAlmostEqual(adjusted[2]["start"], 5.8, places=3)
        self.assertTrue(all(seg.get("_final_gap_settings_applied") for seg in adjusted))

    def test_final_gap_settings_do_not_pull_across_multiclip_boundaries(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "A", "_clip_idx": 0},
            {"start": 2.0, "end": 3.0, "text": "B", "_clip_idx": 1},
        ]

        adjusted = subtitle_engine.apply_final_gap_settings(
            segments,
            {
                "continuous_threshold": 2.0,
                "gap_push_rate": 0.8,
                "gap_pull_rate": 0.2,
                "single_subtitle_end": 0.2,
            },
        )

        self.assertAlmostEqual(adjusted[0]["end"], 1.2, places=3)
        self.assertAlmostEqual(adjusted[1]["start"], 2.0, places=3)

    def test_final_gap_settings_are_idempotent_when_already_applied(self):
        segments = [
            {"start": 0.0, "end": 1.8, "text": "A", "_final_gap_settings_applied": True},
            {"start": 1.8, "end": 3.0, "text": "B", "_final_gap_settings_applied": True},
        ]

        adjusted = subtitle_engine.apply_final_gap_settings(
            segments,
            {"continuous_threshold": 2.0, "gap_push_rate": 0.8, "gap_pull_rate": 0.2},
        )

        self.assertAlmostEqual(adjusted[0]["end"], 1.8, places=3)
        self.assertAlmostEqual(adjusted[1]["start"], 1.8, places=3)

    def test_setting_int_uses_fallback_and_default_for_invalid_values(self):
        self.assertEqual(
            subtitle_engine._setting_int(
                {"llm_threads": "", "llm_workers": 7},
                "llm_threads",
                6,
                fallback_key="llm_workers",
            ),
            7,
        )
        self.assertEqual(
            subtitle_engine._setting_int(
                {"llm_threads": "bad", "llm_workers": 7},
                "llm_threads",
                6,
                fallback_key="llm_workers",
            ),
            6,
        )

    def test_setting_float_uses_default_for_blank_or_invalid_values(self):
        self.assertEqual(
            subtitle_engine._setting_float(
                {"sub_gap_break_sec": ""},
                "sub_gap_break_sec",
                1.5,
            ),
            1.5,
        )

    def test_local_ollama_workers_are_capped(self):
        workers, mode = subtitle_engine._effective_llm_workers(
            "gemma4:e4b",
            configured_workers=6,
            settings={"local_ollama_llm_max_workers": 2},
            segment_count=226,
        )

        self.assertEqual(mode, "local")
        self.assertEqual(workers, 2)

    def test_stt_candidate_optimizer_does_not_call_llm(self):
        segments = [
            {
                "start": 0.0,
                "end": 4.0,
                "text": "오늘은 비엠더블유 행사장에 왔습니다",
                "words": [
                    {"word": "오늘은", "start": 0.0, "end": 0.5},
                    {"word": "비엠더블유", "start": 0.55, "end": 1.2},
                    {"word": "행사장에", "start": 1.25, "end": 2.0},
                    {"word": "왔습니다", "start": 2.05, "end": 2.8},
                ],
            }
        ]

        with unittest.mock.patch("core.engine.subtitle_engine.ask_exaone_to_split") as ask_llm:
            result = subtitle_engine.optimize_stt_candidate_segments(segments)

        ask_llm.assert_not_called()
        self.assertTrue(result)
        self.assertTrue(all(seg.get("_final_gap_settings_applied") for seg in result))

    def test_api_models_use_single_worker(self):
        workers, mode = subtitle_engine._effective_llm_workers(
            "OpenAI GPT-5.2",
            configured_workers=6,
            settings={"local_ollama_llm_max_workers": 2},
            segment_count=226,
        )

        self.assertEqual(mode, "api")
        self.assertEqual(workers, 1)

    def test_module_import_survives_invalid_numeric_settings(self):
        original_dataset_dir = config.DATASET_DIR
        original_module = sys.modules.get("core.engine.subtitle_engine")
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "user_settings.json").write_text(
                json.dumps(
                    {
                        "llm_threads": "bad",
                        "sub_gap_break_sec": "bad",
                        "sub_max_cps": "",
                    }
                ),
                encoding="utf-8",
            )
            try:
                config.DATASET_DIR = tmp
                sys.modules.pop("core.engine.subtitle_engine", None)
                reloaded = importlib.import_module("core.engine.subtitle_engine")
                self.assertEqual(reloaded._EXAONE_WORKERS, 6)
                self.assertEqual(reloaded._GAP_BREAK_SEC, 1.5)
                self.assertEqual(reloaded._MAX_CPS, 12)
            finally:
                config.DATASET_DIR = original_dataset_dir
                sys.modules.pop("core.engine.subtitle_engine", None)
                if original_module is not None:
                    sys.modules["core.engine.subtitle_engine"] = original_module
        self.assertEqual(
            subtitle_engine._setting_float(
                {"sub_gap_break_sec": "bad"},
                "sub_gap_break_sec",
                1.5,
            ),
            1.5,
        )


if __name__ == "__main__":
    unittest.main()
