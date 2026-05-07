import json
import tempfile
import unittest

from core.personalization.editor_truth_capture import capture_editor_truth_records
from core.personalization.lora_storage import store_paths
from core.personalization.subtitle_pattern_index import (
    match_subtitle_pattern,
    save_subtitle_pattern_index,
)


class SubtitlePatternIndexTests(unittest.TestCase):
    def test_compact_truth_capture_stores_patterns_without_full_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            segments = [
                {
                    "line": 0,
                    "start": 1.0,
                    "end": 2.4,
                    "text": "안녕하세요 오늘은 테스트입니다.",
                    "speaker": "SPEAKER_01",
                    "original_text": "안녕하세요 오늘은 테스틉니다",
                    "stt_candidates": [{"source": "STT1", "text": "안녕하세요 오늘은 테스틉니다"}],
                },
                {
                    "line": 1,
                    "start": 2.62,
                    "end": 4.0,
                    "text": "짧은 무음 뒤에도 이어집니다.",
                },
            ]

            result = capture_editor_truth_records(
                segments,
                settings={"lora_store_full_text_enabled": False, "user_edit_metrics_enabled": False},
                store_dir=tmpdir,
                refresh_bundle=False,
            )

            self.assertEqual(result["appended_rows"], 2)
            rows = [
                json.loads(line)
                for line in store_paths(tmpdir)["truth_table"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(rows[0]["raw_ground_truth_text"], "")
            self.assertEqual(rows[0]["speech_training_text"], "")
            self.assertEqual(rows[0]["speaker_or_voice_hint"], "")
            self.assertGreater(rows[0]["char_count"], 0)
            self.assertEqual(rows[0]["store_mode"], "compact_pattern")
            self.assertNotIn("text", rows[0]["stt_candidate_snapshot"]["candidates"][0])

    def test_pattern_match_prefers_continuous_short_silence_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            capture_editor_truth_records(
                [
                    {"start": 1.0, "end": 2.2, "text": "짧은 무음은 이어집니다."},
                    {"start": 2.45, "end": 3.6, "text": "다음 자막이 먼저 나옵니다."},
                    {"start": 3.85, "end": 5.0, "text": "넷플릭스처럼 이어집니다."},
                ],
                settings={"lora_store_full_text_enabled": False, "user_edit_metrics_enabled": False},
                store_dir=tmpdir,
                refresh_bundle=False,
            )
            index = save_subtitle_pattern_index(tmpdir, force=True)

            self.assertGreater(index["pattern_count"], 0)
            matched = match_subtitle_pattern(
                {"start": 10.0, "end": 11.2, "text": "비슷한 길이 자막입니다."},
                {"lora_pattern_index_enabled": True},
                store_dir=tmpdir,
                index=index,
            )

            self.assertGreaterEqual(matched["settings"]["sub_gap_break_sec"], 1.45)
            self.assertGreaterEqual(matched["settings"]["continuous_threshold"], 2.0)
            self.assertGreater(matched["settings"]["gap_pull_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
