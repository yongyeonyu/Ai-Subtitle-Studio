# Version: 03.00.19
# Phase: PHASE2
import unittest

from core.audio.media_processor import VideoProcessor
from core.audio.stt_quality_presets import apply_stt_quality_preset


class MediaProcessorOverlapTests(unittest.TestCase):
    def setUp(self):
        self.processor = VideoProcessor()

    def test_split_range_uses_real_overlap_between_chunks(self):
        chunks = self.processor._split_range_with_overlap(0.0, 80.0, max_chunk_dur=30.0, overlap_sec=3.0)

        self.assertEqual(chunks, [
            {"start": 0.0, "end": 30.0},
            {"start": 27.0, "end": 57.0},
            {"start": 54.0, "end": 80.0},
        ])

    def test_build_grouped_chunks_applies_overlap_to_long_vad_sector(self):
        chunks = self.processor._build_grouped_chunks(
            [{"start": 10.0, "end": 80.0}],
            total_dur=100.0,
            max_chunk_dur=30.0,
            margin=0.0,
            gap_merge_limit=0.0,
            settings={"whisper_chunk_overlap_sec": 2.0},
        )

        self.assertEqual(chunks[0], {"start": 10.0, "end": 40.0})
        self.assertEqual(chunks[1], {"start": 38.0, "end": 68.0})
        self.assertEqual(chunks[2], {"start": 66.0, "end": 80.0})

    def test_dedupe_overlapping_segments_uses_word_timestamps(self):
        chunk = [
            {
                "start": 27.0,
                "end": 32.0,
                "text": "중복 앞부분 새 단어",
                "words": [
                    {"word": "중복", "start": 27.0, "end": 28.0},
                    {"word": "앞부분", "start": 28.0, "end": 29.8},
                    {"word": "새", "start": 30.2, "end": 31.0},
                    {"word": "단어", "start": 31.0, "end": 32.0},
                ],
            }
        ]

        deduped = self.processor._dedupe_overlapping_segments(chunk, previous_end=30.0, dedup_window=0.5)

        self.assertEqual(len(deduped), 1)
        self.assertAlmostEqual(deduped[0]["start"], 30.2)
        self.assertEqual(deduped[0]["text"], "새 단어")
        self.assertEqual([w["word"] for w in deduped[0]["words"]], ["새", "단어"])

    def test_quality_presets_set_overlap_per_mode(self):
        fast = apply_stt_quality_preset({}, "fast")
        balanced = apply_stt_quality_preset({}, "balanced")
        precise = apply_stt_quality_preset({}, "precise")

        self.assertLess(fast["whisper_chunk_overlap_sec"], balanced["whisper_chunk_overlap_sec"])
        self.assertLess(balanced["whisper_chunk_overlap_sec"], precise["whisper_chunk_overlap_sec"])


if __name__ == "__main__":
    unittest.main()
