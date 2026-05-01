# Version: 03.01.28
# Phase: PHASE2
import unittest

from core.roughcut import (
    DEFAULT_ROUGHCUT_PROMPT_V1,
    RoughCutDraftState,
    RoughCutMinorGroup,
    RoughCutTitleSuggestion,
    build_roughcut_prompt,
    merge_roughcut_settings,
    roughcut_result_from_dict,
    resolve_roughcut_llm_config,
    run_roughcut_llm_action,
)


class RoughCutModelsV2Tests(unittest.TestCase):
    def test_roughcut_result_restores_v1_payload_with_v2_defaults(self):
        result = roughcut_result_from_dict({
            "segments": [{"segment_id": "chapter_0001", "start": 0.0, "end": 2.0}],
            "chapters": [{"chapter_id": "chapter_0001", "title": "소개", "start": 0.0, "end": 2.0}],
            "edl": [{
                "source_path": "sample.mp4",
                "segment_id": "chapter_0001",
                "source_start": 0.0,
                "source_end": 2.0,
                "output_start": 0.0,
                "output_end": 2.0,
            }],
            "markdown_guide": "# guide",
        })

        self.assertEqual(result.schema_version, "roughcut_result.v1")
        self.assertEqual(result.markdown_guide, "# guide")
        self.assertEqual(result.segments[0].status, "confirmed")
        self.assertEqual(result.segments[0].minor_groups, ())

    def test_roughcut_result_restores_v2_minor_title_and_draft_state(self):
        result = roughcut_result_from_dict({
            "schema_version": "roughcut_result.v2",
            "segments": [{
                "segment_id": "major_A",
                "start": 0.0,
                "end": 10.0,
                "major_id": "A",
                "minor_groups": [{
                    "minor_id": "A1",
                    "major_id": "A",
                    "code": "A1",
                    "title": "외부",
                    "start": 0.0,
                    "end": 4.0,
                    "subtitle_ids": [1, 2],
                    "chapter_ids": ["chapter_0001"],
                    "tags": ["외부"],
                }],
            }],
            "chapters": [{
                "chapter_id": "chapter_0001",
                "title": "외부",
                "start": 0.0,
                "end": 4.0,
                "major_id": "A",
                "minor_code": "A1",
                "confidence": 0.82,
                "boundary_status": "provisional",
            }],
            "title_suggestions": [{
                "title_id": "title_001",
                "title": "EV6 외부 리뷰",
                "score": 0.91,
                "tags": ["EV6", "외부"],
            }],
            "draft_state": {
                "draft_id": "draft_001",
                "status": "review",
                "selected_major_id": "A",
            },
        })

        self.assertEqual(result.schema_version, "roughcut_result.v2")
        self.assertIsInstance(result.segments[0].minor_groups[0], RoughCutMinorGroup)
        self.assertEqual(result.chapters[0].minor_code, "A1")
        self.assertIsInstance(result.title_suggestions[0], RoughCutTitleSuggestion)
        self.assertIsInstance(result.draft_state, RoughCutDraftState)
        self.assertEqual(result.draft_state.selected_major_id, "A")

    def test_roughcut_settings_and_llm_fallback_contract(self):
        settings = merge_roughcut_settings({"roughcut_llm_enabled": False})
        prompt = build_roughcut_prompt("propose_major_segment", {"chunks": []}, token_budget=128)
        result = run_roughcut_llm_action("propose_major_segment", {"chunks": []}, settings=settings)

        self.assertIn("propose_major_segment", prompt)
        self.assertIn("중분류는 실제 러프컷 편집 최소 단위", prompt)
        self.assertIn("화면 전환, 주제 전환, 장소 전환", prompt)
        self.assertFalse(result.ok)
        self.assertFalse(result.used_llm)
        self.assertEqual(result.error, "llm_disabled")

    def test_roughcut_llm_config_inherits_or_overrides_subtitle_model(self):
        inherited = resolve_roughcut_llm_config({
            "selected_llm_provider": "openai",
            "selected_model": "gpt-test",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": False,
        })
        self.assertTrue(inherited.enabled)
        self.assertEqual(inherited.provider, "openai")
        self.assertEqual(inherited.model, "gpt-test")
        self.assertIn("응답은 반드시 JSON", inherited.prompt)

        override = resolve_roughcut_llm_config({
            "selected_llm_provider": "openai",
            "selected_model": "gpt-test",
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "exaone-test",
            "roughcut_llm_prompt": "custom roughcut prompt",
            "roughcut_llm_temperature": 1.5,
            "roughcut_llm_threads": 7,
        })
        self.assertEqual(override.provider, "ollama")
        self.assertEqual(override.model, "exaone-test")
        self.assertEqual(override.prompt, "custom roughcut prompt")
        self.assertEqual(override.temperature, 1.0)
        self.assertEqual(override.threads, 7)
        self.assertIn("중분류 A/B/C/D", DEFAULT_ROUGHCUT_PROMPT_V1)
        self.assertIn("단순한 말 끊김", DEFAULT_ROUGHCUT_PROMPT_V1)


if __name__ == "__main__":
    unittest.main()
