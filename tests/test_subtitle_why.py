import unittest

from core.engine.subtitle_why import build_subtitle_why_payload, format_subtitle_why_text


class SubtitleWhyTests(unittest.TestCase):
    def test_builds_why_payload_with_lora_stt_llm_and_cut_evidence(self):
        segment = {
            "segment_id": "seg-why",
            "start": 1.0,
            "end": 2.8,
            "text": "테스트 자막",
            "_lora_generation_profile": {
                "top_score": 91.5,
                "used_kinds": {"truth_table": 2},
                "applied_settings": {"split_length_threshold": 14},
                "examples": [
                    {"kind": "truth_table", "text": "비슷한 자막", "score": 92.0, "line_break_pattern": "5|5"}
                ],
            },
            "stt_candidates": [
                {"source": "STT1", "text": "테스트 자막", "score": 0.9},
                {"source": "STT2", "text": "테스트 자막입니다", "score": 0.7},
            ],
            "stt_selected_source": "STT1",
            "_accuracy_decision_graph": {
                "decisions": [
                    {"task": "llm_gate", "call_llm": False, "reason": "skip_llm:high_lora_deep_stt_confidence", "confidence": 0.91}
                ]
            },
            "_cut_boundary_guard_policy": {
                "action": "clamped_to_cut_scene",
                "confidence": 72.0,
                "scene_end": 3.0,
                "evidence": {"combined_confidence": 72.0, "lora_score": 91.5},
            },
        }

        payload = build_subtitle_why_payload(segment, index=3)
        text = format_subtitle_why_text(payload)

        self.assertEqual(payload["schema"], "ai_subtitle_studio.subtitle_why_panel.v1")
        self.assertEqual(payload["segment_id"], "seg-why")
        self.assertEqual(payload["lora"]["examples"][0]["text"], "비슷한 자막")
        self.assertTrue(payload["stt_candidates"][0]["selected"])
        self.assertFalse(payload["llm"]["called"])
        self.assertEqual(payload["cut_boundary"]["action"], "clamped_to_cut_scene")
        self.assertIn("LoRA 근거", text)
        self.assertIn("skip_llm:high_lora_deep_stt_confidence", text)
        self.assertIn("combined_confidence", text)


if __name__ == "__main__":
    unittest.main()
