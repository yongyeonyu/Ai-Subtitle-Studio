import unittest
from unittest import mock

from core.engine.subtitle_prompts import _build_llm_prompt
from core.native_swift_subtitle_llm_context import (
    build_subtitle_llm_context_packs_via_swift,
    evaluate_subtitle_llm_context_gate_via_swift,
    format_subtitle_llm_context_for_prompt,
)


class SubtitleLLMContextPolicyTests(unittest.TestCase):
    def test_context_pack_uses_previous_current_next_with_vad(self):
        segments = [
            {"start": 90.0, "end": 92.0, "text": "아까 뭐래", "stt_selected_source": "STT1"},
            {
                "start": 94.9,
                "end": 99.5,
                "text": "커피지와 같이 여기 맞는데 아 가자",
                "stt_selected_source": "STT1",
                "stt_candidates": [
                    {"source": "STT1", "text": "커피지와 같이 여기 맞는데 아 가자"},
                    {"source": "STT2", "text": "커피지와 같이 여기 맞는데 가자"},
                ],
            },
            {"start": 100.0, "end": 102.0, "text": "그냥 가져가", "stt_selected_source": "STT2"},
        ]

        with mock.patch("core.native_swift_subtitle_llm_context.run_subtitle_core_operation_via_swift", return_value=None):
            packs = build_subtitle_llm_context_packs_via_swift(
                segments,
                [{"start": 94.8, "end": 99.7}],
                settings={"subtitle_llm_context_candidate_limit": 5},
            )

        self.assertEqual(len(packs), 3)
        window = packs[1]["window"]
        self.assertEqual(window["previous"]["text"], "아까 뭐래")
        self.assertEqual(window["current"]["selected_source"], "STT1")
        self.assertEqual(window["next"]["text"], "그냥 가져가")
        self.assertEqual(packs[1]["vad"]["speech_overlap_ratio"], 1.0)

    def test_prompt_includes_swift_context_lock(self):
        pack = {
            "schema": "ai_subtitle_studio.subtitle_llm_context_pack.v1",
            "index": 1,
            "window": {
                "previous": {"text": "아까 뭐래"},
                "current": {"text": "커피지와 같이 여기 맞는데 아 가자", "candidates": []},
                "next": {"text": "그냥 가져가"},
            },
            "vad": {"speech_overlap_ratio": 1.0, "hints": [{"start": 94.8, "end": 99.7}]},
            "constraints": {"previous_next_are_context_only": True},
        }

        prompt = _build_llm_prompt(
            "커피지와 같이 여기 맞는데 아 가자",
            20,
            {},
            "",
            settings={},
            candidate_options=[],
            context_pack=pack,
        )

        self.assertIn("[이전/현재/다음 STT/VAD 문맥 - Swift]", prompt)
        self.assertIn("previous/next는 문맥 참고용", prompt)
        self.assertIn("커피지와 같이 여기 맞는데 아 가자", prompt)
        self.assertIn("nas_50_reference_split.v1", prompt)
        self.assertIn("9~17자", prompt)

    def test_context_gate_rejects_previous_subtitle_takeover(self):
        segments = [
            {"start": 90.0, "end": 92.0, "text": "아까 뭐래 네 커피지인데 어 어디"},
            {"start": 94.9, "end": 99.5, "text": "커피지와 같이 여기 맞는데 아 가자"},
            {"start": 100.0, "end": 102.0, "text": "그냥 가져가"},
        ]

        with mock.patch("core.native_swift_subtitle_llm_context.run_subtitle_core_operation_via_swift", return_value=None):
            pack = build_subtitle_llm_context_packs_via_swift(segments)[1]
            rejected = evaluate_subtitle_llm_context_gate_via_swift(
                "커피지와 같이 여기 맞는데 아 가자",
                ["아까 뭐래 네 커피지인데 어 어디"],
                pack,
            )
            accepted = evaluate_subtitle_llm_context_gate_via_swift(
                "커피지와 같이 여기 맞는데 아 가자",
                ["커피지와 같이 여기 맞는데 아 가자"],
                pack,
            )

        self.assertFalse(rejected["accepted"])
        self.assertEqual(rejected["reason"], "neighbor_context_takeover")
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["reason"], "stt_vad_context_supported")

    def test_formatter_is_empty_without_context(self):
        self.assertEqual(format_subtitle_llm_context_for_prompt(None), "")


if __name__ == "__main__":
    unittest.main()
