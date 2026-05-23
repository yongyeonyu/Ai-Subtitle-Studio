# Version: 03.13.02
# Phase: PHASE2
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.personalization.lora_models import LearnedRuleEntry
from core.personalization.lora_storage import initialize_lora_personalization_store, save_learned_rules
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

    def test_runtime_lora_prompt_uses_editor_learned_start_and_line_break_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            initialize_lora_personalization_store(tmp)
            save_learned_rules(
                "line_break",
                [
                    LearnedRuleEntry(
                        rule_text="8|8",
                        rule_type="line_break_rule",
                        frequency=3,
                        confidence=0.9,
                    ).to_record()
                ],
                tmp,
                metadata={
                    "summary": {
                        "editor_word_boundaries": {
                            "top_subtitle_start_words": [{"word": "그러니까", "frequency": 3}],
                            "top_line_start_words": [{"word": "여기까지", "frequency": 2}],
                            "top_line_break_before_words": [{"word": "오늘은", "frequency": 2}],
                            "top_line_break_pairs": [{"pair": "오늘은->여기까지", "frequency": 2}],
                        }
                    }
                },
            )
            settings = {
                "editor_lora_runtime_enabled": True,
                "split_length_threshold": 20,
            }
            prompt = build_runtime_lora_prompt("오늘은 여기까지 말할게요", {}, settings, store_dir=tmp)

        self.assertIn("에디터에서 학습한 자막 시작 단어", prompt)
        self.assertIn("그러니까", prompt)
        self.assertIn("오늘은->여기까지", prompt)
        self.assertIn("새 자막 시작단어 후보", prompt)

    def test_runtime_lora_prompt_strips_quote_marks_from_examples(self):
        settings = {
            "editor_lora_runtime_enabled": True,
            "split_length_threshold": 20,
            "_lora_generation_profile": {
                "examples": [{"text": "\"왜?\"", "line_break_pattern": "1|1"}],
            },
        }
        retrieval = {
            "score_model": "hybrid",
            "index_doc_count": 3,
            "query_facets": {},
            "items": [
                {
                    "kind": "truth_table",
                    "retrieval_score": 91.0,
                    "payload": {
                        "speech_training_text": "\"티박스가 있어\"",
                        "line_break_pattern": "1|1",
                    },
                }
            ],
        }

        with patch("core.personalization.runtime_lora_context.retrieve_lora_context", return_value=retrieval):
            prompt = build_runtime_lora_prompt("왜? 티박스가 있어", {}, settings)

        self.assertIn("왜?, line=1|1", prompt)
        self.assertIn("ground truth: 티박스가 있어, line=1|1", prompt)
        self.assertNotIn("\"왜?\"", prompt)
        self.assertNotIn("\"티박스가 있어\"", prompt)


if __name__ == "__main__":
    unittest.main()
