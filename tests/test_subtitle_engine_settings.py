# Version: 03.08.09
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
