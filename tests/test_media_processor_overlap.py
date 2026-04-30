# Version: 03.01.22
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
        self.assertEqual([w["word"] for w in deduped[0]["asr_metadata"]["words"]], ["새", "단어"])

    def test_parse_whisper_payload_attaches_asr_metadata(self):
        payload = {
            "backend": "unit-test",
            "language_probability": 0.93,
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "테스트",
                    "avg_logprob": -0.2,
                    "compression_ratio": 1.1,
                    "no_speech_prob": 0.03,
                    "temperature": 0.0,
                    "words": [
                        {"word": "테스트", "start": 0.1, "end": 0.9, "confidence": 0.88},
                    ],
                }
            ],
        }

        parsed = self.processor._parse_whisper_payload(
            payload,
            {"input_path": "/tmp/chunk.wav", "ov_start_offset": 10.0},
            vad_strict=[{"start": 10.0, "end": 11.0, "review_vad": True}],
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["start"], 10.1)
        self.assertEqual(parsed[0]["end"], 10.9)
        self.assertEqual(parsed[0]["asr_metadata"]["backend"], "unit-test")
        self.assertEqual(parsed[0]["asr_metadata"]["language_probability"], 0.93)
        self.assertEqual(parsed[0]["asr_metadata"]["words"][0]["start"], 10.1)
        self.assertEqual(parsed[0]["asr_metadata"]["vad_alignment"]["vad_aligned"], True)
        self.assertEqual(parsed[0]["quality"]["vad_alignment_score"], 100.0)

    def test_quality_presets_set_overlap_per_mode(self):
        fast = apply_stt_quality_preset({}, "fast")
        balanced = apply_stt_quality_preset({}, "balanced")
        precise = apply_stt_quality_preset({}, "precise")

        self.assertEqual(fast["whisper_chunk_overlap_sec"], 0.5)
        self.assertLess(fast["whisper_chunk_overlap_sec"], balanced["whisper_chunk_overlap_sec"])
        self.assertLess(balanced["whisper_chunk_overlap_sec"], precise["whisper_chunk_overlap_sec"])
        self.assertEqual(precise["whisper_chunk_overlap_sec"], 3.0)

    def test_quality_review_forces_precise_overlap(self):
        overlap = self.processor._chunk_overlap_sec({
            "whisper_chunk_overlap_sec": 0.5,
            "subtitle_quality_auto_check_after_generate": True,
        })

        self.assertEqual(overlap, 3.0)


if __name__ == "__main__":
    unittest.main()
