import unittest

from core.cut_boundary import magnetize_segments_to_cut_boundaries
from core.engine.subtitle_timing import (
    align_stt_candidates_to_subtitle_segments,
    align_stt_preview_to_subtitle_segments,
)


class SubtitleBoundaryAlignmentTests(unittest.TestCase):
    def test_confirmed_cut_stays_hard_after_provisional_snap(self):
        rows = magnetize_segments_to_cut_boundaries(
            [{"start": 0.0, "end": 10.0, "text": "긴 자막"}],
            confirmed_boundaries=[{"timeline_sec": 5.0, "fps": 30.0}],
            provisional_boundaries=[{"timeline_sec": 4.9, "fps": 30.0, "status": "provisional"}],
            primary_fps=30.0,
            provisional_window_sec=0.35,
            confirmed_window_sec=0.60,
        )

        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(row["end"] <= 5.0 or row["start"] >= 5.0)

    def test_stt_candidates_align_to_final_subtitle_union_without_text_changes(self):
        segments = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "첫 자막",
                "stt_candidates": [
                    {"source": "STT1", "start": 1.08, "end": 1.92, "text": "후보 하나"},
                    {"source": "STT2", "start": 0.8, "end": 4.2, "text": "합쳐진 후보"},
                ],
            },
            {"start": 2.0, "end": 4.0, "text": "둘째 자막"},
        ]

        aligned = align_stt_candidates_to_subtitle_segments(segments)
        stt1, stt2 = aligned[0]["stt_candidates"]

        self.assertEqual(stt1["text"], "후보 하나")
        self.assertEqual((stt1["start"], stt1["end"]), (1.0, 2.0))
        self.assertEqual(stt2["text"], "합쳐진 후보")
        self.assertEqual((stt2["start"], stt2["end"]), (1.0, 4.0))
        self.assertTrue(stt2["stt_alignment_preserved_text"])

    def test_stt_preview_lanes_align_to_final_subtitle_union(self):
        preview = [
            {"start": 0.9, "end": 4.1, "text": "STT2 전체", "stt_preview_source": "STT2"},
        ]
        subtitles = [
            {"start": 1.0, "end": 2.0, "text": "첫 자막"},
            {"start": 2.0, "end": 4.0, "text": "둘째 자막"},
        ]

        aligned = align_stt_preview_to_subtitle_segments(preview, subtitles)

        self.assertEqual(aligned[0]["text"], "STT2 전체")
        self.assertEqual((aligned[0]["start"], aligned[0]["end"]), (1.0, 4.0))
        self.assertTrue(aligned[0]["stt_preview_aligned_to_subtitle_segments"])


if __name__ == "__main__":
    unittest.main()
