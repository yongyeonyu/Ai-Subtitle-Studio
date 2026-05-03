# Version: 03.13.02
# Phase: PHASE2
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.runtime import config
from core.personalization.runtime_lora_context import build_runtime_lora_prompt
from core.utils import load_rules, load_subtitle_rules


class SubtitleRulesRuntimeTests(unittest.TestCase):
    def test_load_subtitle_rules_merges_split_defaults_with_rule_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules_path = Path(tmp) / "subtitle_rule.json"
            rules_path.write_text(
                json.dumps(
                    {
                        "end_words": ["맞죠"],
                        "start_words": ["근데"],
                        "split_rules": ["그러니까", "하지만"],
                        "split_punctuation": [",", "!"],
                        "max_chars": 17,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch("core.utils.DATASET_DIR", tmp), patch("core.utils.RULES_FILE", str(rules_path)):
                rules = load_subtitle_rules()
                split_rules, split_punctuation, max_chars = load_rules()

        self.assertIn("맞죠", rules["end_words"])
        self.assertIn("근데", rules["start_words"])
        self.assertIn("그러니까", rules["split_rules"])
        self.assertEqual(set(split_punctuation), {",", "!"})
        self.assertEqual(max_chars, 17)

    def test_runtime_lora_prompt_mentions_split_rule_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules_path = Path(tmp) / "subtitle_rule.json"
            rules_path.write_text(
                json.dumps(
                    {
                        "split_rules": ["그러니까", "하지만"],
                        "split_punctuation": [",", "!"],
                        "max_chars": 17,
                        "end_words": ["네요"],
                        "start_words": ["근데"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            settings = {
                "editor_lora_runtime_enabled": True,
                "split_length_threshold": 19,
            }
            with patch("core.utils.DATASET_DIR", tmp), patch("core.utils.RULES_FILE", str(rules_path)):
                prompt = build_runtime_lora_prompt("근데 그러니까 오늘은 여기까지네요", {}, settings)

        self.assertIn("자막 분리 규칙", prompt)
        self.assertIn("기본 분리 글자수=19자", prompt)
        self.assertIn("그러니까", prompt)
        self.assertIn(",", prompt)


if __name__ == "__main__":
    unittest.main()
