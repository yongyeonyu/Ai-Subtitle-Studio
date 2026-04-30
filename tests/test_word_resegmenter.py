# Version: 03.01.23
# Phase: PHASE2
import unittest

from core.engine.word_resegmenter import resegment_by_word_timestamps
from core.subtitle_quality.timestamp_regrouper import regroup_by_word_timestamps


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


if __name__ == "__main__":
    unittest.main()
