import tempfile
import unittest

from core.engine.subtitle_one_click_fix import (
    build_one_click_fix_request,
    reapply_similar_subtitle_style,
    subtitle_source_text_without_llm,
)
from core.personalization.editor_truth_memory import append_editor_truth_patterns


class SubtitleOneClickFixTests(unittest.TestCase):
    def test_restores_source_without_llm_from_quality_or_stt_candidate(self):
        self.assertEqual(
            subtitle_source_text_without_llm(
                {
                    "text": "LLM 결과",
                    "quality": {"auto_corrected_from": "원문 자막"},
                    "stt_candidates": [{"source": "STT1", "text": "STT 후보"}],
                }
            ),
            "원문 자막",
        )
        self.assertEqual(
            subtitle_source_text_without_llm(
                {
                    "text": "LLM 결과",
                    "stt_selected_source": "STT2",
                    "stt_candidates": [
                        {"source": "STT1", "text": "첫 후보"},
                        {"source": "STT2", "text": "선택 후보"},
                    ],
                }
            ),
            "선택 후보",
        )

    def test_reapplies_recent_editor_truth_style_pattern(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            append_editor_truth_patterns(
                [
                    {
                        "segment_id": "seg-style",
                        "speech_training_text": "유스 어드벤처 2026입니다",
                        "extra": {"source_before_edit": "유스 어드벤쳐 2026입니다"},
                    }
                ],
                store_dir=tmpdir,
            )

            updated, meta = reapply_similar_subtitle_style(
                "유스 어드벤쳐 2026입니다",
                {"editor_truth_runtime_min_similarity": 0.9},
                store_dir=tmpdir,
            )

            self.assertEqual(updated, "유스 어드벤처 2026입니다")
            self.assertTrue(meta["applied"])
            self.assertEqual(meta["task"], "reapply_similar_style")

    def test_builds_reprocess_request_metadata(self):
        request = build_one_click_fix_request(
            "recheck_cut_only",
            {"line": 4, "segment_id": "seg-cut", "start": 10.0, "end": 12.0, "text": "컷 확인"},
        )

        self.assertEqual(request["schema"], "ai_subtitle_studio.subtitle_one_click_fix.v1")
        self.assertEqual(request["label"], "이 컷만 다시 확인")
        self.assertEqual(request["line"], 4)
        self.assertTrue(request["request_id"])


if __name__ == "__main__":
    unittest.main()
