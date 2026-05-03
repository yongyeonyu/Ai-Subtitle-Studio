# Version: 03.01.23
# Phase: PHASE2
import unittest
from unittest import mock

from core.engine import subtitle_engine
from core.engine.word_resegmenter import resegment_by_word_timestamps
from core.subtitle_quality.timestamp_regrouper import (
    regroup_by_word_timestamps,
    refine_segment_edges_with_context,
    snap_segments_to_word_vad_boundaries,
)


class WordResegmenterTests(unittest.TestCase):
    def test_splits_on_silence_gap(self):
        result = resegment_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 4.0,
                    "text": "안녕하세요 다음입니다",
                    "words": [
                        {"word": "안녕하세요", "start": 0.0, "end": 0.8},
                        {"word": "다음입니다", "start": 2.7, "end": 3.5},
                    ],
                }
            ],
            max_chars=30,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=1.5,
        )

        self.assertEqual([item["text"] for item in result], ["안녕하세요", "다음입니다"])

    def test_splits_on_punctuation_and_max_chars(self):
        result = resegment_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 4.0,
                    "text": "처음입니다, 다음 문장입니다",
                    "words": [
                        {"word": "처음입니다,", "start": 0.0, "end": 1.0},
                        {"word": "다음", "start": 1.1, "end": 1.7},
                        {"word": "문장입니다", "start": 1.8, "end": 2.6},
                    ],
                }
            ],
            max_chars=5,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=1.5,
        )

        self.assertEqual([item["text"] for item in result], ["처음입니다,", "다음 문장입니다"])

    def test_splits_when_duration_is_too_long(self):
        result = resegment_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 10.0,
                    "text": "하나 둘 셋 넷 다섯 여섯",
                    "words": [
                        {"word": "하나", "start": 0.0, "end": 1.0},
                        {"word": "둘", "start": 1.1, "end": 2.0},
                        {"word": "셋", "start": 2.1, "end": 3.0},
                        {"word": "넷", "start": 5.5, "end": 6.2},
                        {"word": "다섯", "start": 6.3, "end": 7.0},
                        {"word": "여섯", "start": 7.1, "end": 8.0},
                    ],
                }
            ],
            max_chars=20,
            max_duration=3.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=3.0,
        )

        self.assertGreaterEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "하나 둘 셋")

    def test_generates_words_when_missing(self):
        result = resegment_by_word_timestamps(
            [{"start": 0.0, "end": 2.0, "text": "없는 단어 타임스탬프"}],
            max_chars=3,
            max_duration=1.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=1.5,
        )

        self.assertTrue(result)
        self.assertTrue(all(item.get("words") for item in result))

    def test_timestamp_regrouper_merges_tiny_same_boundary_segments(self):
        result = regroup_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "아",
                    "speaker": "SPEAKER_00",
                    "words": [{"word": "아", "start": 0.0, "end": 0.2, "speaker": "SPEAKER_00"}],
                    "asr_metadata": {"_clip_idx": 0},
                },
                {
                    "start": 0.35,
                    "end": 1.0,
                    "text": "맞아요",
                    "speaker": "SPEAKER_00",
                    "words": [{"word": "맞아요", "start": 0.35, "end": 0.9, "speaker": "SPEAKER_00"}],
                    "asr_metadata": {"_clip_idx": 0},
                },
            ],
            max_chars=10,
            max_duration=4.0,
            max_cps=20,
            min_duration=0.5,
            gap_break_sec=1.5,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "아 맞아요")

    def test_timestamp_regrouper_does_not_merge_across_clip_boundary(self):
        result = regroup_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 0.2,
                    "text": "아",
                    "speaker": "SPEAKER_00",
                    "words": [{"word": "아", "start": 0.0, "end": 0.2, "speaker": "SPEAKER_00"}],
                    "asr_metadata": {"_clip_idx": 0},
                },
                {
                    "start": 0.35,
                    "end": 0.9,
                    "text": "맞아요",
                    "speaker": "SPEAKER_00",
                    "words": [{"word": "맞아요", "start": 0.35, "end": 0.9, "speaker": "SPEAKER_00"}],
                    "asr_metadata": {"_clip_idx": 1},
                },
            ],
            max_chars=10,
            max_duration=4.0,
            max_cps=20,
            min_duration=0.5,
            gap_break_sec=1.5,
        )

        self.assertEqual([item["text"] for item in result], ["아", "맞아요"])

    def test_timestamp_regrouper_prefers_word_gap_over_large_gap_setting(self):
        result = regroup_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "첫말 다음말",
                    "words": [
                        {"word": "첫말", "start": 0.2, "end": 0.6},
                        {"word": "다음말", "start": 1.35, "end": 1.9},
                    ],
                }
            ],
            max_chars=30,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=5.0,
            word_gap_break_sec=0.65,
        )

        self.assertEqual([item["text"] for item in result], ["첫말", "다음말"])
        self.assertAlmostEqual(result[0]["start"], 0.2)
        self.assertAlmostEqual(result[0]["end"], 0.6)
        self.assertAlmostEqual(result[1]["start"], 1.35)
        self.assertAlmostEqual(result[1]["end"], 1.9)

    def test_timestamp_regrouper_prefers_vad_boundary_over_gap_setting(self):
        result = regroup_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 2.5,
                    "text": "하나 둘",
                    "words": [
                        {"word": "하나", "start": 0.2, "end": 0.55},
                        {"word": "둘", "start": 0.72, "end": 1.05},
                    ],
                }
            ],
            max_chars=30,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.5,
            gap_break_sec=5.0,
            word_gap_break_sec=0.65,
            vad_segments=[
                {"start": 0.18, "end": 0.58},
                {"start": 0.70, "end": 1.08},
            ],
        )

        self.assertEqual([item["text"] for item in result], ["하나", "둘"])
        self.assertLess(result[0]["end"], result[1]["start"])

    def test_snap_segments_to_word_vad_boundaries_uses_word_edges_then_nearby_vad(self):
        result = snap_segments_to_word_vad_boundaries(
            [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "정확한 시간",
                    "words": [
                        {"word": "정확한", "start": 1.0, "end": 1.4},
                        {"word": "시간", "start": 1.5, "end": 2.0},
                    ],
                }
            ],
            vad_segments=[{"start": 0.96, "end": 2.04}],
            edge_pad_sec=0.04,
            max_edge_shift_sec=0.12,
        )

        self.assertAlmostEqual(result[0]["start"], 0.92)
        self.assertAlmostEqual(result[0]["end"], 2.08)
        self.assertEqual(result[0]["asr_metadata"]["word_vad_timing"]["source"], "whisper_words+vad")

    def test_refine_segment_edges_with_context_snaps_to_words_vad_and_frame(self):
        result = refine_segment_edges_with_context(
            [
                {
                    "start": 0.93,
                    "end": 2.11,
                    "text": "정확한 시간",
                    "words": [
                        {"word": "정확한", "start": 1.0, "end": 1.4},
                        {"word": "시간", "start": 1.5, "end": 2.0},
                    ],
                }
            ],
            vad_segments=[{"start": 0.98, "end": 2.03}],
            frame_rate=10.0,
        )

        self.assertAlmostEqual(result[0]["start"], 1.0)
        self.assertAlmostEqual(result[0]["end"], 2.1)
        self.assertEqual(result[0]["asr_metadata"]["precision_timing"]["source"], "words+vad+frame")

    def test_refine_segment_edges_with_context_keeps_neighbors_non_overlapping(self):
        result = refine_segment_edges_with_context(
            [
                {
                    "start": 0.0,
                    "end": 1.05,
                    "text": "첫말",
                    "words": [{"word": "첫말", "start": 0.1, "end": 1.0}],
                },
                {
                    "start": 1.02,
                    "end": 2.0,
                    "text": "둘째",
                    "words": [{"word": "둘째", "start": 1.02, "end": 1.95}],
                },
            ],
            frame_rate=30.0,
        )

        self.assertLessEqual(result[0]["end"], result[1]["start"])

    def test_llm_split_preserves_matched_word_timestamps(self):
        segment = {
            "start": 0.0,
            "end": 3.0,
            "text": "첫말 둘 셋",
            "words": [
                {"word": "첫말", "start": 0.1, "end": 0.6},
                {"word": "둘", "start": 1.0, "end": 1.3},
                {"word": "셋", "start": 1.4, "end": 1.8},
            ],
        }

        with mock.patch.object(subtitle_engine, "ask_exaone_to_split", return_value=["첫말", "둘 셋"]):
            result = subtitle_engine._process_one((segment, {}, 3, {}, "exaone3.5:7.8b", "", "", False))

        self.assertEqual([item["text"] for item in result], ["첫말", "둘 셋"])
        self.assertEqual([word["word"] for word in result[0]["words"]], ["첫말"])
        self.assertEqual([word["word"] for word in result[1]["words"]], ["둘", "셋"])
        self.assertAlmostEqual(result[1]["start"], 1.0)
        self.assertAlmostEqual(result[1]["end"], 1.8)


if __name__ == "__main__":
    unittest.main()
