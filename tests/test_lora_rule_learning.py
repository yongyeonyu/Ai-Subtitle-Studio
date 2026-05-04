import tempfile
import unittest
from pathlib import Path

from core.personalization.lora_models import TruthTableRow
from core.personalization.lora_rule_learning import (
    apply_split_rule_update_review,
    build_split_rule_update_review,
    learn_rules_from_truth_table,
)
from core.personalization.lora_storage import append_truth_table_rows, initialize_lora_personalization_store, load_learned_rules


class LoraRuleLearningTests(unittest.TestCase):
    def test_learn_rules_from_truth_table_saves_split_and_line_break_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            rows = [
                TruthTableRow(
                    media_id="media-001",
                    media_path="/tmp/a.mp4",
                    subtitle_path="/tmp/a.srt",
                    segment_id="seg-1",
                    start_sec=1.0,
                    end_sec=3.0,
                    raw_ground_truth_text="오늘은 그러니까\n여기까지 할게요.",
                    speech_training_text="오늘은 그러니까\n여기까지 할게요.",
                    line_break_pattern="8|8",
                    punctuation_pattern=".",
                    detected_split_rule="그러니까",
                ).to_record(),
                TruthTableRow(
                    media_id="media-002",
                    media_path="/tmp/b.mp4",
                    subtitle_path="/tmp/b.srt",
                    segment_id="seg-2",
                    start_sec=5.0,
                    end_sec=7.0,
                    raw_ground_truth_text="하지만 다음엔 더 잘할게요.",
                    speech_training_text="하지만 다음엔 더 잘할게요.",
                    line_break_pattern="12",
                    punctuation_pattern=".",
                    detected_split_rule="하지만",
                ).to_record(),
                TruthTableRow(
                    media_id="media-003",
                    media_path="/tmp/c.mp4",
                    subtitle_path="/tmp/c.srt",
                    segment_id="seg-3",
                    start_sec=9.0,
                    end_sec=11.0,
                    raw_ground_truth_text="아니 그러니까\n진짜 여기까지예요.",
                    speech_training_text="아니 그러니까\n진짜 여기까지예요.",
                    line_break_pattern="7|9",
                    punctuation_pattern=".",
                    detected_split_rule="그러니까",
                ).to_record(),
            ]
            append_truth_table_rows(rows, tmpdir)

            result = learn_rules_from_truth_table(tmpdir)
            split_payload = load_learned_rules("split", tmpdir)
            line_payload = load_learned_rules("line_break", tmpdir)

            self.assertEqual(result["split_rule_count"], 2)
            self.assertEqual(split_payload["items"][0]["rule_text"], "그러니까")
            self.assertEqual(split_payload["items"][0]["frequency"], 2)
            self.assertGreater(split_payload["items"][0]["confidence"], 0.6)
            self.assertEqual(line_payload["items"][0]["rule_text"], "8|8")
            self.assertIn("summary", split_payload["metadata"])

    def test_apply_split_rule_update_review_rewrites_temp_config_with_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            rows = [
                TruthTableRow(
                    media_id="media-001",
                    media_path="/tmp/a.mp4",
                    subtitle_path="/tmp/a.srt",
                    segment_id="seg-1",
                    start_sec=1.0,
                    end_sec=3.0,
                    raw_ground_truth_text="오늘은 그러니까\n여기까지 할게요.",
                    speech_training_text="오늘은 그러니까\n여기까지 할게요.",
                    line_break_pattern="8|8",
                    punctuation_pattern=".",
                    detected_split_rule="그러니까",
                ).to_record(),
                TruthTableRow(
                    media_id="media-002",
                    media_path="/tmp/b.mp4",
                    subtitle_path="/tmp/b.srt",
                    segment_id="seg-2",
                    start_sec=5.0,
                    end_sec=7.0,
                    raw_ground_truth_text="하지만 다음엔 더 잘할게요.",
                    speech_training_text="하지만 다음엔 더 잘할게요.",
                    line_break_pattern="12",
                    punctuation_pattern=".",
                    detected_split_rule="하지만",
                ).to_record(),
            ]
            append_truth_table_rows(rows, tmpdir)
            learn_rules_from_truth_table(tmpdir)

            config_path = Path(tmpdir) / "config.py"
            config_path.write_text(
                "\n".join(
                    [
                        'DEFAULT_SPLIT_RULES = [',
                        '    "는데", "은데", "지만"',
                        ']',
                        'DEFAULT_SPLIT_PUNCTUATION = [".", "!", "?"]',
                    ]
                ),
                encoding="utf-8",
            )

            review = build_split_rule_update_review(store_dir=tmpdir, config_path=config_path, top_n=2)
            self.assertEqual(review["proposed_rules"], ["그러니까", "하지만"])
            self.assertTrue(review["needs_update"])

            applied = apply_split_rule_update_review(store_dir=tmpdir, config_path=config_path, top_n=2)
            updated_text = config_path.read_text(encoding="utf-8")

            self.assertTrue(Path(applied["backup_path"]).exists())
            self.assertIn('"그러니까"', updated_text)
            self.assertIn('"하지만"', updated_text)


if __name__ == "__main__":
    unittest.main()
