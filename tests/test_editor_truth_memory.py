import tempfile
import unittest

from core.personalization.editor_truth_memory import (
    append_editor_truth_patterns,
    apply_recent_editor_truth_patterns,
    build_editor_truth_patterns,
    load_editor_truth_patterns,
)


class EditorTruthMemoryTests(unittest.TestCase):
    def test_builds_patterns_from_user_edited_truth_rows(self):
        patterns = build_editor_truth_patterns(
            [
                {
                    "media_id": "m1",
                    "segment_id": "s1",
                    "speech_training_text": "안녕하세요",
                    "extra": {"source_before_edit": "안녕 하세요", "trigger": "manual_save"},
                }
            ]
        )

        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["source_text"], "안녕 하세요")
        self.assertEqual(patterns[0]["corrected_text"], "안녕하세요")
        self.assertEqual(patterns[0]["replacement"], {})

    def test_recent_truth_exact_match_applies_corrected_subtitle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            append_editor_truth_patterns(
                [
                    {
                        "media_id": "m1",
                        "segment_id": "s1",
                        "speech_training_text": "안녕하세요",
                        "extra": {"source_before_edit": "안녕 하세요"},
                    }
                ],
                store_dir=tmpdir,
            )

            text, meta = apply_recent_editor_truth_patterns("안녕 하세요", store_dir=tmpdir)

            self.assertEqual(text, "안녕하세요")
            self.assertTrue(meta["applied"])
            self.assertEqual(meta["reason"], "exact_source_match")

    def test_recent_truth_replacement_applies_to_similar_later_subtitle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = append_editor_truth_patterns(
                [
                    {
                        "media_id": "m1",
                        "segment_id": "s1",
                        "speech_training_text": "유스 어드벤처 2026입니다",
                        "extra": {"source_before_edit": "유스 어드벤쳐 2026입니다"},
                    }
                ],
                store_dir=tmpdir,
            )

            text, meta = apply_recent_editor_truth_patterns("오늘은 유스 어드벤쳐 2026입니다", store_dir=tmpdir)

            self.assertEqual(result["appended_patterns"], 1)
            self.assertEqual(len(load_editor_truth_patterns(tmpdir)), 1)
            self.assertEqual(text, "오늘은 유스 어드벤처 2026입니다")
            self.assertEqual(meta["reason"], "replacement_pattern")


if __name__ == "__main__":
    unittest.main()
