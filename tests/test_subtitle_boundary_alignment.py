import unittest

from core.cut_boundary import magnetize_segments_to_cut_boundaries
from core.engine.subtitle_timing import (
    align_stt_candidates_to_subtitle_segments,
    align_stt_preview_to_subtitle_segments,
)
from ui.timeline.timeline_analysis import (
    editor_analysis_markers,
    subtitle_detection_segments_for_editor,
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

    def test_stt_preview_lanes_preserve_candidate_timing(self):
        preview = [
            {"start": 0.9, "end": 4.1, "text": "STT2 전체", "stt_preview_source": "STT2"},
        ]
        subtitles = [
            {"start": 1.0, "end": 2.0, "text": "첫 자막"},
            {"start": 2.0, "end": 4.0, "text": "둘째 자막"},
        ]

        aligned = align_stt_preview_to_subtitle_segments(preview, subtitles)

        self.assertEqual(aligned[0]["text"], "STT2 전체")
        self.assertEqual((aligned[0]["start"], aligned[0]["end"]), (0.9, 4.1))
        self.assertTrue(aligned[0]["stt_preview_preserved_candidate_timing"])

    def test_non_stt_preview_rows_align_to_final_subtitle_union(self):
        preview = [
            {"start": 0.9, "end": 4.1, "text": "보조 표시", "stt_preview_source": "AUX"},
        ]
        subtitles = [
            {"start": 1.0, "end": 2.0, "text": "첫 자막"},
            {"start": 2.0, "end": 4.0, "text": "둘째 자막"},
        ]

        aligned = align_stt_preview_to_subtitle_segments(preview, subtitles)

        self.assertEqual(aligned[0]["text"], "보조 표시")
        self.assertEqual((aligned[0]["start"], aligned[0]["end"]), (1.0, 4.0))
        self.assertTrue(aligned[0]["preview_aligned_to_subtitle_segments"])

    def test_analysis_lanes_ignore_stt_candidate_timing(self):
        segments = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "메인 자막",
                "quality": {"confidence_label": "yellow", "confidence_score": 72},
            },
            {
                "start": 0.5,
                "end": 4.0,
                "text": "STT1 원본",
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT1",
            },
        ]

        detection = subtitle_detection_segments_for_editor(segments, [], [], 5.0)
        analysis = editor_analysis_markers(segments, [], [], 5.0)

        self.assertFalse(any(row.get("kind") == "stt_candidate" for row in detection))
        self.assertTrue(any(row.get("start") == 1.0 and row.get("end") == 2.0 for row in detection))
        self.assertTrue(any(row.get("kind") == "silence" and row.get("start") <= 2.0 and row.get("end") >= 4.0 for row in analysis))


if __name__ == "__main__":
    unittest.main()
