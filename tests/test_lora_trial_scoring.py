import tempfile
import unittest

from core.personalization.lora_models import TruthTableRow
from core.personalization.lora_storage import initialize_lora_personalization_store, load_best_settings, store_paths
from core.personalization.lora_trial_scoring import (
    candidate_segments_to_rows,
    record_prompt_trial_result,
    record_setting_trial_result,
    score_candidate_rows,
)


class LoraTrialScoringTests(unittest.TestCase):
    def test_score_candidate_rows_returns_high_score_for_close_match(self):
        truth_rows = [
            TruthTableRow(
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                segment_id="seg-1",
                start_sec=1.0,
                end_sec=3.0,
                raw_ground_truth_text="(박수) 안녕하세요!",
                speech_training_text="안녕하세요!",
                excluded_parenthetical_text="박수",
                line_break_pattern="5",
                punctuation_pattern="!",
                detected_split_rule="",
            ).to_record(),
            TruthTableRow(
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                segment_id="seg-2",
                start_sec=3.2,
                end_sec=5.8,
                raw_ground_truth_text="오늘은 그러니까\n여기까지 할게요.",
                speech_training_text="오늘은 그러니까\n여기까지 할게요.",
                line_break_pattern="8|8",
                punctuation_pattern=".",
                detected_split_rule="그러니까",
            ).to_record(),
        ]
        candidate_rows = candidate_segments_to_rows(
            [
                {"start": 1.0, "end": 3.0, "text": "안녕하세요!"},
                {"start": 3.25, "end": 5.75, "text": "오늘은 그러니까\n여기까지 할게요."},
            ],
            media_id="media-001",
            media_path="/tmp/a.mp4",
            subtitle_path="/tmp/a.srt",
        )

        metrics = score_candidate_rows(truth_rows, candidate_rows)

        self.assertLess(metrics["character_error_rate"], 0.05)
        self.assertGreater(metrics["timing_overlap_score"], 0.9)
        self.assertGreater(metrics["line_break_match_score"], 0.9)
        self.assertGreater(metrics["final_score"], 90.0)

    def test_record_trial_results_updates_history_and_best_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            metrics = {
                "final_score": 96.5,
                "character_error_rate": 0.03,
                "eojeol_error_rate": 0.05,
                "timing_overlap_score": 0.98,
                "line_break_match_score": 1.0,
                "punctuation_match_score": 1.0,
                "parenthetical_exclusion_correctness": 1.0,
                "segment_split_merge_f1": 1.0,
            }

            setting_result = record_setting_trial_result(
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                config={"audio_preset": "clear_voice"},
                metrics=metrics,
                reason="Best overall score",
                store_dir=tmpdir,
            )
            prompt_result = record_prompt_trial_result(
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                config={"provider": "openai", "model": "gpt-5.5"},
                prompt_template_id="subtitle_qa_v2",
                prompt_text="Keep spoken style and avoid invention.",
                metrics={**metrics, "final_score": 97.2},
                reason="Best prompt score",
                store_dir=tmpdir,
            )

            self.assertEqual(setting_result["append_result"]["appended_rows"], 1)
            self.assertEqual(prompt_result["append_result"]["appended_rows"], 1)

            best_settings = load_best_settings(tmpdir)
            self.assertEqual(best_settings["by_media_id"]["media-001"]["config"]["audio_preset"], "clear_voice")
            self.assertEqual(best_settings["by_style_cluster"]["media-001"]["prompt_template_id"], "subtitle_qa_v2")

            paths = store_paths(tmpdir)
            self.assertEqual(len(paths["setting_trials"].read_text(encoding="utf-8").strip().splitlines()), 1)
            self.assertEqual(len(paths["prompt_trials"].read_text(encoding="utf-8").strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
