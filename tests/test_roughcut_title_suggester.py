# Version: 03.01.30
# Phase: PHASE2
import unittest

from core.roughcut import (
    ChapterMetadata,
    RoughCutResult,
    RoughCutSegment,
    RoughCutTitleSuggestion,
    build_title_suggestions,
    roughcut_result_from_dict,
    run_roughcut_pipeline,
)


class RoughCutTitleSuggesterTests(unittest.TestCase):
    def test_local_title_suggestions_are_stored_on_pipeline_result(self):
        result = run_roughcut_pipeline(
            [
                {"start": 0.0, "end": 2.0, "text": "차량 외부 디자인을 자세히 봅니다"},
                {"start": 3.0, "end": 5.0, "text": "실내 공간과 편의 기능을 확인합니다"},
            ],
            settings={"roughcut_title_suggestions_enabled": True},
        )

        self.assertTrue(result.title_suggestions)
        self.assertIsInstance(result.title_suggestions[0], RoughCutTitleSuggestion)
        self.assertTrue(result.title_suggestions[0].expected_reach)

    def test_restore_title_suggestion_state_fields(self):
        result = roughcut_result_from_dict({
            "title_suggestions": [{
                "title_id": "title_001",
                "title": "EV6 실내 리뷰",
                "score": 0.9,
                "expected_reach": "높음",
                "copied": True,
                "applied": False,
            }]
        })

        self.assertTrue(result.title_suggestions[0].copied)
        self.assertFalse(result.title_suggestions[0].applied)
        self.assertEqual(result.title_suggestions[0].expected_reach, "높음")

    def test_llm_title_suggestions_parse_expected_reach(self):
        base = RoughCutResult(
            segments=(RoughCutSegment("major_A", 0.0, 6.0, title="외부 리뷰", tags=("EV6",)),),
            chapters=(ChapterMetadata("chapter_0001", "외부", 0.0, 6.0, tags=("외부",)),),
            video_summary="EV6 리뷰",
        )

        suggestions = build_title_suggestions(
            base,
            settings={"roughcut_llm_enabled": True},
            llm_client=lambda _prompt: {
                "titles": [{
                    "title": "EV6 외부 디자인 장단점 총정리",
                    "score": 0.93,
                    "reason": "핵심 키워드 포함",
                    "expected_reach": "높음",
                    "tags": ["EV6", "외부"],
                }]
            },
        )

        self.assertEqual(suggestions[0].source, "llm")
        self.assertEqual(suggestions[0].expected_reach, "높음")
        self.assertEqual(suggestions[0].tags, ("EV6", "외부"))


if __name__ == "__main__":
    unittest.main()
