import unittest

from core.cut_boundary import magnetize_segments_to_cut_boundaries
from core.cut_boundary import snap_late_segment_starts_to_confirmed_cuts
from core.engine.subtitle_timing import (
    _selected_stt_candidate_span,
    align_stt_candidates_to_subtitle_segments,
    align_stt_preview_to_subtitle_segments,
    apply_final_gap_settings,
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

    def test_confirmed_cut_pulls_late_start_when_previous_subtitle_overlaps_cut(self):
        rows = snap_late_segment_starts_to_confirmed_cuts(
            [
                {"start": 31.22, "end": 35.54, "text": "컷 직전 자막"},
                {"start": 35.63, "end": 39.94, "text": "컷 직후 자막"},
            ],
            [{"timeline_sec": 35.2, "fps": 60.0, "status": "confirmed"}],
            primary_fps=60.0,
        )

        self.assertAlmostEqual(rows[0]["end"], 35.2, places=3)
        self.assertAlmostEqual(rows[1]["start"], 35.2, places=3)
        self.assertEqual(rows[1]["_cut_boundary_start_snap_policy"]["task"], "subtitle_cut_boundary_start_snap")

    def test_confirmed_cut_magnetize_pulls_late_start_after_split_trimmed_previous(self):
        rows = magnetize_segments_to_cut_boundaries(
            [
                {"start": 31.22, "end": 35.54, "text": "컷 직전 자막"},
                {"start": 35.95, "end": 39.94, "text": "컷 직후 늦은 자막"},
            ],
            confirmed_boundaries=[{"timeline_sec": 35.2, "fps": 60.0, "status": "confirmed"}],
            provisional_boundaries=[],
            primary_fps=60.0,
        )

        self.assertAlmostEqual(rows[0]["end"], 35.2, places=3)
        self.assertAlmostEqual(rows[1]["start"], 35.2, places=3)
        self.assertEqual(rows[1]["_cut_boundary_start_snap_policy"]["source"], "confirmed_visual_cut")

    def test_confirmed_cut_does_not_pull_late_start_without_previous_overlap(self):
        rows = snap_late_segment_starts_to_confirmed_cuts(
            [
                {"start": 31.22, "end": 34.9, "text": "컷 전에 끝난 자막"},
                {"start": 35.95, "end": 39.94, "text": "컷 뒤 침묵 후 자막"},
            ],
            [{"timeline_sec": 35.2, "fps": 60.0, "status": "confirmed"}],
            primary_fps=60.0,
        )

        self.assertAlmostEqual(rows[0]["end"], 34.9, places=3)
        self.assertAlmostEqual(rows[1]["start"], 35.95, places=3)
        self.assertNotIn("_cut_boundary_start_snap_policy", rows[1])

    def test_confirmed_cut_does_not_push_start_that_is_well_before_cut(self):
        rows = snap_late_segment_starts_to_confirmed_cuts(
            [
                {"start": 77.9, "end": 81.7, "text": "컷보다 먼저 시작한 자막"},
            ],
            [{"timeline_sec": 78.9, "fps": 60.0, "status": "confirmed"}],
            primary_fps=60.0,
        )

        self.assertAlmostEqual(rows[0]["start"], 77.9, places=3)
        self.assertNotIn("_cut_boundary_start_snap_policy", rows[0])

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
        self.assertEqual(aligned[0], preview[0])
        self.assertNotIn("timeline_start", aligned[0])
        self.assertNotIn("timeline_end", aligned[0])

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

    def test_final_gap_settings_keep_generated_subtitle_inside_selected_stt_window(self):
        segments = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "확정 자막",
                "stt_selected_source": "STT1",
                "stt_candidates": [
                    {"source": "STT1", "start": 1.1, "end": 1.9, "text": "확정 자막"},
                ],
            },
        ]

        adjusted = apply_final_gap_settings(
            segments,
            {"single_subtitle_end": 0.4, "sub_min_duration": 0.1},
            force=True,
        )

        self.assertEqual((adjusted[0]["start"], adjusted[0]["end"]), (1.1, 1.9))

    def test_aligned_candidate_rows_keep_raw_stt_bounds_for_later_clamp(self):
        segments = [
            {
                "start": 1.0,
                "end": 2.3,
                "text": "확정 자막",
                "stt_selected_source": "STT1",
                "stt_candidates": [
                    {"source": "STT1", "start": 1.1, "end": 1.9, "text": "확정 자막"},
                ],
            },
        ]

        aligned = align_stt_candidates_to_subtitle_segments(segments)
        candidate = aligned[0]["stt_candidates"][0]

        self.assertEqual((candidate["start"], candidate["end"]), (1.0, 2.3))
        self.assertEqual((candidate["original_start"], candidate["original_end"]), (1.1, 1.9))

        adjusted = apply_final_gap_settings(aligned, {"sub_min_duration": 0.1}, force=True)

        self.assertEqual((adjusted[0]["start"], adjusted[0]["end"]), (1.1, 1.9))

    def test_word_matched_final_subtitle_prefers_chunk_word_span_over_whole_candidate(self):
        segment = {
            "start": 140.9,
            "end": 141.8,
            "text": "말린 과일이네",
            "_stt_original_candidate_start": 136.0,
            "_stt_original_candidate_end": 143.0,
            "_stt_word_match_timing_policy": {"task": "stt_chunk_word_timing_match"},
            "words": [
                {"word": "말린", "start": 140.9, "end": 141.2},
                {"word": "과일이네", "start": 141.24, "end": 141.8},
            ],
        }

        self.assertEqual(_selected_stt_candidate_span(segment), (140.9, 141.8))

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
