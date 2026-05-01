import unittest

from core.audio.stt_ensemble import merge_stt_outputs, text_similarity
from core.settings import get_model_key
from core.subtitle_quality.vad_alignment_checker import adjust_segments_to_vad_boundaries


class STTEnsembleTests(unittest.TestCase):
    def test_merge_keeps_two_candidates_for_overlapping_segments(self):
        primary = [
            {"start": 0.0, "end": 1.2, "text": "안녕하세요", "avg_logprob": -0.2, "no_speech_prob": 0.02},
        ]
        secondary = [
            {"start": 0.05, "end": 1.25, "text": "안녕 하세요", "avg_logprob": -0.4, "no_speech_prob": 0.03},
        ]

        merged = merge_stt_outputs(primary, secondary)

        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]["stt_candidates"]), 2)
        self.assertEqual(merged[0]["stt_ensemble_source"], "STT1")
        self.assertEqual(merged[0]["text"], "안녕하세요")
        self.assertAlmostEqual(merged[0]["start"], 0.0)
        self.assertAlmostEqual(merged[0]["end"], 1.2)
        self.assertGreater(merged[0]["stt_ensemble_similarity"], 0.8)

    def test_merge_preserves_secondary_only_segments(self):
        merged = merge_stt_outputs(
            [{"start": 0.0, "end": 1.0, "text": "첫 문장"}],
            [{"start": 2.0, "end": 3.0, "text": "두 번째 문장"}],
        )

        self.assertEqual([seg["text"] for seg in merged], ["첫 문장", "두 번째 문장"])
        self.assertEqual(merged[1]["stt_ensemble_source"], "STT2")

    def test_merge_drops_secondary_duplicate_even_when_text_differs(self):
        merged = merge_stt_outputs(
            [{"start": 10.0, "end": 12.0, "text": "망고 보여 봐"}],
            [{"start": 10.1, "end": 12.1, "text": "방금 보아 봐 말린 과일이네"}],
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["stt_ensemble_source"], "STT1")
        self.assertEqual(merged[0]["text"], "망고 보여 봐")

    def test_secondary_overlap_never_trims_primary_segment(self):
        merged = merge_stt_outputs(
            [{"start": 0.0, "end": 4.0, "text": "STT1 기준 문장"}],
            [{"start": 3.6, "end": 5.0, "text": "STT2 겹친 문장"}],
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["stt_ensemble_source"], "STT1")
        self.assertEqual(merged[0]["text"], "STT1 기준 문장")
        self.assertAlmostEqual(merged[0]["start"], 0.0)
        self.assertAlmostEqual(merged[0]["end"], 4.0)

    def test_secondary_insert_only_when_primary_has_real_gap(self):
        merged = merge_stt_outputs(
            [
                {"start": 0.0, "end": 1.0, "text": "첫 문장"},
                {"start": 3.0, "end": 4.0, "text": "셋째 문장"},
            ],
            [{"start": 1.4, "end": 2.3, "text": "빠진 둘째 문장", "avg_logprob": -0.3}],
        )

        self.assertEqual([seg["text"] for seg in merged], ["첫 문장", "빠진 둘째 문장", "셋째 문장"])
        self.assertEqual(merged[1]["stt_ensemble_source"], "STT2")
        self.assertEqual(merged[1]["stt_ensemble_inserted_from_stt2"], True)
        self.assertEqual(merged[1]["stt_ensemble_needs_llm_review"], True)

    def test_model_key_includes_secondary_stt_when_ensemble_enabled(self):
        key = get_model_key(
            {
                "selected_whisper_model": "large-v3",
                "selected_whisper_model_secondary": "ghost613/faster-whisper-large-v3-turbo-korean",
                "stt_ensemble_enabled": True,
                "selected_model": "exaone3.5",
                "max_speakers": 1,
            }
        )

        self.assertIn("large-v3+ghost613/faster-whisper-large-v3-turbo-korean", key)

    def test_text_similarity_compacts_whitespace_and_punctuation(self):
        self.assertGreater(text_similarity("안녕 하세요!", "안녕하세요"), 0.9)

    def test_vad_post_alignment_snaps_ensemble_boundaries(self):
        segments = [
            {
                "start": 0.0,
                "end": 1.5,
                "text": "안녕하세요",
                "stt_candidates": [{"source": "STT1", "text": "안녕하세요"}],
            }
        ]
        vad = [{"start": 0.18, "end": 1.18, "post_stt_align": True, "vad_word_filter": False}]

        adjusted, count = adjust_segments_to_vad_boundaries(segments, vad, max_shift_sec=0.7, edge_pad_sec=0.04)

        self.assertEqual(count, 1)
        self.assertAlmostEqual(adjusted[0]["start"], 0.14)
        self.assertAlmostEqual(adjusted[0]["end"], 1.22)
        self.assertEqual(adjusted[0]["asr_metadata"]["vad_alignment"]["vad_aligned"], True)


if __name__ == "__main__":
    unittest.main()
