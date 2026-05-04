import json
import tempfile
import unittest
from pathlib import Path

from core.personalization.lora_models import (
    ExcludedParentheticalRow,
    LearnedRuleEntry,
    TrainingQueueItem,
    TrialRecord,
    TruthTableRow,
)
from core.personalization.lora_storage import (
    append_excluded_parentheticals,
    append_prompt_trials,
    append_setting_trials,
    append_truth_table_rows,
    compact_lora_personalization_store,
    initialize_lora_personalization_store,
    load_best_settings,
    load_dedupe_index,
    load_learned_rules,
    load_training_queue,
    refresh_lora_personalization_manifest,
    save_best_settings,
    save_learned_rules,
    save_training_queue,
    store_paths,
)


class LoraPersonalizationStorageTests(unittest.TestCase):
    def test_initialize_store_creates_phase3_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)

            self.assertTrue(paths["root"].exists())
            self.assertTrue(paths["manifest"].exists())
            self.assertTrue(paths["truth_table"].exists())
            self.assertTrue(paths["training_queue"].exists())
            self.assertTrue(paths["learned_split_rules"].exists())
            self.assertTrue(paths["learned_line_break_rules"].exists())
            self.assertTrue(paths["setting_trials"].exists())
            self.assertTrue(paths["prompt_trials"].exists())
            self.assertTrue(paths["best_settings"].exists())
            self.assertTrue(paths["excluded_parentheticals"].exists())
            self.assertTrue(paths["dedupe_index"].exists())
            self.assertTrue(paths["trained_adapters"].exists())
            self.assertEqual(manifest["counts"]["truth_table_rows"], 0)
            self.assertEqual(manifest["counts"]["queue_items"], 0)

    def test_models_and_appenders_dedupe_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            truth_row = TruthTableRow(
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                segment_id="seg-1",
                start_sec=1.0,
                end_sec=3.0,
                raw_ground_truth_text="(박수) 안녕하세요!",
                speech_training_text="안녕하세요!",
                excluded_parenthetical_text="박수",
                detected_split_rule="요",
                speaker_or_voice_hint="spk1",
            ).to_record()
            excluded_row = ExcludedParentheticalRow(
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                segment_id="seg-1",
                original_text="(박수) 안녕하세요!",
                excluded_text="박수",
                kept_text="안녕하세요!",
            ).to_record()
            setting_trial = TrialRecord(
                trial_type="setting",
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                config={"audio_preset": "clear_voice", "stt_quality_preset": "precise"},
                status="complete",
                score=97.8,
                metrics={"cer": 0.03, "line_break_match": 1.0},
                reason="Best CER and line break match",
            ).to_record()
            prompt_trial = TrialRecord(
                trial_type="prompt",
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                config={"provider": "openai", "model": "gpt-5.5"},
                prompt_template_id="subtitle_qa_v1",
                prompt_text="Keep spoken style and avoid invention.",
                status="complete",
                score=98.2,
                metrics={"punctuation_match": 1.0},
            ).to_record()

            truth_result_first = append_truth_table_rows([truth_row], tmpdir)
            truth_result_second = append_truth_table_rows([truth_row], tmpdir)
            excluded_result = append_excluded_parentheticals([excluded_row, excluded_row], tmpdir)
            setting_result = append_setting_trials([setting_trial, setting_trial], tmpdir)
            prompt_result = append_prompt_trials([prompt_trial, prompt_trial], tmpdir)

            self.assertEqual(truth_result_first["appended_rows"], 1)
            self.assertEqual(truth_result_second["appended_rows"], 0)
            self.assertEqual(excluded_result["appended_rows"], 1)
            self.assertEqual(setting_result["appended_rows"], 1)
            self.assertEqual(prompt_result["appended_rows"], 1)

            manifest = refresh_lora_personalization_manifest(tmpdir)
            self.assertEqual(manifest["counts"]["truth_table_rows"], 1)
            self.assertEqual(manifest["counts"]["excluded_parenthetical_rows"], 1)
            self.assertEqual(manifest["counts"]["setting_trial_rows"], 1)
            self.assertEqual(manifest["counts"]["prompt_trial_rows"], 1)

            dedupe = load_dedupe_index(tmpdir)
            self.assertEqual(len(dedupe["entries"]["truth_table"]), 1)
            self.assertEqual(len(dedupe["entries"]["excluded_parentheticals"]), 1)

    def test_queue_rules_best_settings_and_compaction_work(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)

            queue_item = TrainingQueueItem(
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                job_type="optimize_settings",
                status="waiting",
                priority=10,
            ).to_record()
            queue_payload = save_training_queue([queue_item], tmpdir)
            self.assertEqual(len(queue_payload["items"]), 1)
            self.assertEqual(len(load_training_queue(tmpdir)["items"]), 1)

            split_rule = LearnedRuleEntry(
                rule_text="그러니까",
                rule_type="split_rule",
                frequency=7,
                confidence=0.92,
                examples=["오늘은 그러니까 여기까지"],
                source_media_refs=["media-001"],
            ).to_record()
            line_break_rule = LearnedRuleEntry(
                rule_text="18|12",
                rule_type="line_break_rule",
                frequency=5,
                confidence=0.88,
                examples=["첫 줄 열여덟 글자 / 둘째 줄 열두 글자"],
                source_media_refs=["media-001"],
            ).to_record()
            save_learned_rules("split", [split_rule], tmpdir)
            save_learned_rules("line_break", [line_break_rule], tmpdir)
            self.assertEqual(len(load_learned_rules("split", tmpdir)["items"]), 1)
            self.assertEqual(len(load_learned_rules("line_break", tmpdir)["items"]), 1)

            best_settings = save_best_settings(
                {
                    "global_recommended_defaults": {"audio_preset": "clear_voice"},
                    "by_media_id": {"media-001": {"audio_preset": "clear_voice", "score": 97.8}},
                },
                tmpdir,
            )
            self.assertEqual(best_settings["global_recommended_defaults"]["audio_preset"], "clear_voice")
            self.assertIn("media-001", load_best_settings(tmpdir)["by_media_id"])

            duplicate_trial = TrialRecord(
                trial_type="setting",
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                config={"audio_preset": "clear_voice"},
                status="complete",
                score=97.8,
            ).to_record()
            with paths["setting_trials"].open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(duplicate_trial, ensure_ascii=False) + "\n")
                handle.write(json.dumps(duplicate_trial, ensure_ascii=False) + "\n")

            compact_result = compact_lora_personalization_store(tmpdir)
            self.assertEqual(compact_result["removed_counts"]["setting_trials"], 1)

            lines = paths["setting_trials"].read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            manifest = refresh_lora_personalization_manifest(tmpdir)
            self.assertEqual(manifest["counts"]["queue_items"], 1)
            self.assertEqual(manifest["counts"]["learned_split_rules"], 1)
            self.assertEqual(manifest["counts"]["learned_line_break_rules"], 1)


if __name__ == "__main__":
    unittest.main()
