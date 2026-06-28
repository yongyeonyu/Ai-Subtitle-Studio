import unittest

from core.project.nle_runtime_cutover import (
    NLE_RUNTIME_CUTOVER_SCHEMA,
    nle_final_overlay_segments_from_editor_rows,
    nle_global_canvas_segments_from_editor_rows,
    nle_save_export_segments_from_editor_rows,
    nle_timeline_canvas_segments_from_editor_rows,
)


class ProjectNleRuntimeCutoverTests(unittest.TestCase):
    def test_final_overlay_cutover_projects_only_final_rows_from_nle_caption_state(self):
        rows = [
            {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
            {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
            {"id": "stt_1", "start": 1.1, "end": 1.8, "text": "raw", "_live_stt_preview": True},
            {
                "id": "caption_2",
                "start": 2.0,
                "end": 3.0,
                "text": "second",
                "speaker": "01",
                "stt_candidates": [{"source": "STT2", "text": "second raw"}],
            },
        ]

        overlay = nle_final_overlay_segments_from_editor_rows(rows, primary_fps=30.0, center_sec=1.5)

        self.assertEqual([row["text"] for row in overlay], ["first", "second"])
        self.assertEqual([row["start_frame"] for row in overlay], [0, 60])
        self.assertEqual([row["end_frame"] for row in overlay], [30, 90])
        self.assertTrue(all(row["_nle_runtime_surface"] == "final_overlay" for row in overlay))
        self.assertTrue(all(row["_nle_runtime_schema"] == NLE_RUNTIME_CUTOVER_SCHEMA for row in overlay))
        self.assertFalse(any(row.get("is_gap") for row in overlay))
        self.assertFalse(any(row.get("_live_stt_preview") for row in overlay))
        self.assertFalse(any("stt_candidates" in row for row in overlay))

    def test_final_overlay_cutover_keeps_context_window_bounded(self):
        rows = [
            {"id": f"caption_{index}", "start": float(index), "end": float(index) + 0.5, "text": f"seg {index}"}
            for index in range(30)
        ]

        overlay = nle_final_overlay_segments_from_editor_rows(
            rows,
            primary_fps=30.0,
            center_sec=15.0,
            before_sec=2.0,
            after_sec=2.0,
            max_segments=5,
        )

        self.assertLessEqual(len(overlay), 5)
        self.assertTrue(any(row["start"] <= 15.0 < row["end"] or abs(row["start"] - 15.0) < 1.0 for row in overlay))

    def test_global_canvas_cutover_projects_final_rows_without_context_window(self):
        rows = [
            {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first"},
            {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
            {"id": "stt_1", "start": 1.1, "end": 1.8, "text": "raw", "_live_stt_preview": True},
            {"id": "draft_1", "start": 1.2, "end": 1.9, "text": "draft", "_live_subtitle_preview": True},
            {"id": "caption_2", "start": 100.0, "end": 101.0, "text": "last"},
        ]

        global_rows = nle_global_canvas_segments_from_editor_rows(rows, primary_fps=30.0)

        self.assertEqual([row["text"] for row in global_rows], ["first", "last"])
        self.assertEqual([row["_nle_runtime_surface"] for row in global_rows], ["global_canvas", "global_canvas"])
        self.assertTrue(all(row["_nle_runtime_schema"] == NLE_RUNTIME_CUTOVER_SCHEMA for row in global_rows))
        self.assertFalse(any(row.get("is_gap") for row in global_rows))
        self.assertFalse(any(row.get("_live_stt_preview") or row.get("_live_subtitle_preview") for row in global_rows))
        self.assertEqual([row["start_frame"] for row in global_rows], [0, 3000])

    def test_timeline_canvas_cutover_preserves_preview_and_gap_rows(self):
        rows = [
            {
                "id": "caption_1",
                "line": 5,
                "start": 0.0,
                "end": 1.0,
                "text": "final",
                "stt_candidates": [{"source": "STT1", "text": "candidate"}],
            },
            {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
            {
                "id": "stt_1",
                "line": 9,
                "start": 1.1,
                "end": 1.8,
                "text": "raw",
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT1",
            },
        ]

        timeline_rows = nle_timeline_canvas_segments_from_editor_rows(rows, primary_fps=30.0)

        self.assertEqual([row["id"] for row in timeline_rows], ["caption_1", "gap_1", "stt_1"])
        self.assertEqual(timeline_rows[0]["line"], 5)
        self.assertEqual(timeline_rows[0]["_nle_runtime_surface"], "timeline_canvas")
        self.assertEqual(timeline_rows[0]["_nle_runtime_schema"], NLE_RUNTIME_CUTOVER_SCHEMA)
        self.assertEqual(timeline_rows[0]["stt_candidates"][0]["source"], "STT1")
        self.assertTrue(timeline_rows[1]["is_gap"])
        self.assertEqual(timeline_rows[1]["_nle_runtime_surface"], "timeline_canvas_gap")
        self.assertTrue(timeline_rows[2]["_live_stt_preview"])
        self.assertEqual(timeline_rows[2]["_nle_runtime_surface"], "timeline_canvas_preview")

    def test_save_export_cutover_projects_final_rows_without_candidates_or_gaps(self):
        rows = [
            {
                "id": "caption_1",
                "start": 0.0,
                "end": 1.0,
                "text": "first",
                "stt_candidates": [{"source": "STT1", "text": "raw"}],
            },
            {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
            {"id": "preview_1", "start": 1.1, "end": 1.8, "text": "preview", "_live_subtitle_preview": True},
            {"id": "caption_2", "start": 2.0, "end": 3.0, "text": "second"},
        ]

        export_rows = nle_save_export_segments_from_editor_rows(rows, primary_fps=30.0)

        self.assertEqual([row["text"] for row in export_rows], ["first", "second"])
        self.assertEqual([row["_nle_runtime_surface"] for row in export_rows], ["save_export", "save_export"])
        self.assertTrue(all(row["_nle_runtime_schema"] == NLE_RUNTIME_CUTOVER_SCHEMA for row in export_rows))
        self.assertFalse(any(row.get("is_gap") for row in export_rows))
        self.assertFalse(any(row.get("_live_subtitle_preview") for row in export_rows))
        self.assertFalse(any("stt_candidates" in row for row in export_rows))

    def test_runtime_reference_tracks_never_promote_to_final_surfaces_even_with_text(self):
        rows = [
            {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "final"},
            {
                "id": "vad_1",
                "start": 1.0,
                "end": 2.0,
                "text": "speech",
                "_nle_runtime_track": "VAD",
                "_nle_runtime_role": "runtime_reference_only",
                "_nle_save_export_authority": False,
            },
            {
                "id": "stt1_1",
                "start": 2.0,
                "end": 3.0,
                "text": "raw stt1",
                "_nle_runtime_track": "STT1",
                "_nle_runtime_role": "runtime_reference_only",
                "_nle_save_export_authority": False,
            },
            {
                "id": "stt2_1",
                "start": 3.0,
                "end": 4.0,
                "text": "raw stt2",
                "_nle_runtime_track": "STT2",
                "_nle_runtime_role": "runtime_reference_only",
                "_nle_save_export_authority": False,
            },
        ]

        overlay = nle_final_overlay_segments_from_editor_rows(rows, primary_fps=30.0, center_sec=0.5)
        global_rows = nle_global_canvas_segments_from_editor_rows(rows, primary_fps=30.0)
        export_rows = nle_save_export_segments_from_editor_rows(rows, primary_fps=30.0)
        timeline_rows = nle_timeline_canvas_segments_from_editor_rows(rows, primary_fps=30.0)

        self.assertEqual([row["text"] for row in overlay], ["final"])
        self.assertEqual([row["text"] for row in global_rows], ["final"])
        self.assertEqual([row["text"] for row in export_rows], ["final"])
        self.assertEqual([row["text"] for row in timeline_rows], ["final", "speech", "raw stt1", "raw stt2"])
        self.assertEqual(
            [row["_nle_runtime_surface"] for row in timeline_rows],
            ["timeline_canvas", "timeline_canvas_preview", "timeline_canvas_preview", "timeline_canvas_preview"],
        )

    def test_save_export_cutover_accepts_vector_canvas_time_rows(self):
        rows = [
            {
                "id": "caption_1",
                "kind": "subtitle_segment",
                "time": {
                    "unit": "frame",
                    "start_frame": 60,
                    "end_frame": 120,
                    "timeline_frame_rate": 60.0,
                },
                "text": "vector first",
                "speaker": "00",
            },
            {
                "id": "caption_2",
                "kind": "subtitle_segment",
                "time": {
                    "unit": "frame",
                    "start_frame": 120,
                    "end_frame": 180,
                    "timeline_frame_rate": 60.0,
                },
                "text": "vector second",
                "speaker": "01",
            },
        ]

        export_rows = nle_save_export_segments_from_editor_rows(rows, primary_fps=30.0)

        self.assertEqual([row["text"] for row in export_rows], ["vector first", "vector second"])
        self.assertEqual([row["start_frame"] for row in export_rows], [30, 60])
        self.assertEqual([row["end_frame"] for row in export_rows], [60, 90])
        self.assertEqual([row["start"] for row in export_rows], [1.0, 2.0])
        self.assertEqual([row["end"] for row in export_rows], [2.0, 3.0])

    def test_final_overlay_cutover_repairs_one_frame_micro_overlap_to_shared_boundary(self):
        rows = [
            {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first"},
            {"id": "caption_2", "start": 0.96, "end": 2.0, "text": "second"},
        ]

        overlay = nle_final_overlay_segments_from_editor_rows(rows, primary_fps=30.0, center_sec=1.0)

        self.assertEqual([row["text"] for row in overlay], ["first", "second"])
        self.assertEqual([row["start_frame"] for row in overlay], [0, 30])
        self.assertEqual([row["end_frame"] for row in overlay], [30, 60])
        self.assertEqual(overlay[1]["start"], 1.0)
        self.assertEqual(overlay[1]["_nle_runtime_overlap_repaired"], "shared_boundary")

    def test_save_export_cutover_repairs_srt_quantized_micro_overlap_at_60fps(self):
        rows = [
            {"id": "caption_1", "start": 162.233, "end": 163.633, "text": "first"},
            {"id": "caption_2", "start": 163.6, "end": 166.9, "text": "second"},
        ]

        export_rows = nle_save_export_segments_from_editor_rows(rows, primary_fps=60.0)

        self.assertEqual([row["text"] for row in export_rows], ["first", "second"])
        self.assertEqual(export_rows[0]["end_frame"], export_rows[1]["start_frame"])
        self.assertGreater(export_rows[1]["end_frame"], export_rows[1]["start_frame"])
        self.assertEqual(export_rows[1]["_nle_runtime_overlap_repaired"], "shared_boundary")

    def test_save_export_cutover_repairs_two_frame_quantized_overlap_at_5994fps(self):
        fps = 60000 / 1001
        rows = [
            {
                "id": "caption_1",
                "time": {"unit": "frame", "start_frame": 20000, "end_frame": 20108, "timeline_frame_rate": fps},
                "text": "first",
            },
            {
                "id": "caption_2",
                "time": {"unit": "frame", "start_frame": 20106, "end_frame": 20280, "timeline_frame_rate": fps},
                "text": "second",
            },
        ]

        export_rows = nle_save_export_segments_from_editor_rows(rows, primary_fps=fps)

        self.assertEqual([row["text"] for row in export_rows], ["first", "second"])
        self.assertEqual(export_rows[0]["end_frame"], export_rows[1]["start_frame"])
        self.assertEqual(export_rows[1]["_nle_runtime_overlap_repaired"], "shared_boundary")

    def test_global_canvas_cutover_drops_unfixable_overlap_instead_of_drawing_two_final_rows(self):
        rows = [
            {"id": "caption_1", "start": 0.0, "end": 2.0, "text": "first"},
            {"id": "caption_2", "start": 1.0, "end": 3.0, "text": "second"},
            {"id": "caption_3", "start": 3.0, "end": 4.0, "text": "third"},
        ]

        global_rows = nle_global_canvas_segments_from_editor_rows(rows, primary_fps=30.0)

        self.assertEqual([row["text"] for row in global_rows], ["first", "third"])
        self.assertEqual([row["_nle_runtime_surface"] for row in global_rows], ["global_canvas", "global_canvas"])

    def test_timeline_canvas_cutover_drops_unfixable_final_overlap_but_keeps_stt_preview(self):
        rows = [
            {"id": "caption_1", "start": 0.0, "end": 2.0, "text": "first"},
            {"id": "caption_2", "start": 1.0, "end": 3.0, "text": "second"},
            {
                "id": "stt_1",
                "start": 1.2,
                "end": 1.8,
                "text": "raw",
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT2",
            },
            {"id": "caption_3", "start": 3.0, "end": 4.0, "text": "third"},
        ]

        timeline_rows = nle_timeline_canvas_segments_from_editor_rows(rows, primary_fps=30.0)

        self.assertEqual([row["id"] for row in timeline_rows], ["caption_1", "stt_1", "caption_3"])
        self.assertEqual([row["text"] for row in timeline_rows if row.get("_live_stt_preview")], ["raw"])
        self.assertEqual(
            [row["_nle_runtime_surface"] for row in timeline_rows],
            ["timeline_canvas", "timeline_canvas_preview", "timeline_canvas"],
        )

    def test_save_export_cutover_rejects_unfixable_final_overlap(self):
        rows = [
            {"id": "caption_1", "start": 0.0, "end": 2.0, "text": "first"},
            {"id": "caption_2", "start": 1.0, "end": 3.0, "text": "second"},
        ]

        with self.assertRaisesRegex(ValueError, "nle_save_export_final_overlap"):
            nle_save_export_segments_from_editor_rows(rows, primary_fps=30.0)

    def test_save_export_cutover_preserves_vector_time_final_overlap_guard(self):
        rows = [
            {
                "id": "caption_1",
                "time": {"unit": "frame", "start_frame": 0, "end_frame": 120, "timeline_frame_rate": 60.0},
                "text": "first",
            },
            {
                "id": "caption_2",
                "time": {"unit": "frame", "start_frame": 117, "end_frame": 180, "timeline_frame_rate": 60.0},
                "text": "second",
            },
        ]

        with self.assertRaisesRegex(ValueError, "nle_save_export_final_overlap"):
            nle_save_export_segments_from_editor_rows(rows, primary_fps=60.0)

    def test_save_export_cutover_rejects_micro_overlap_that_would_collapse_segment(self):
        rows = [
            {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first"},
            {"id": "caption_2", "start": 0.96, "end": 1.0, "text": "second"},
        ]

        with self.assertRaisesRegex(ValueError, "nle_save_export_final_overlap"):
            nle_save_export_segments_from_editor_rows(rows, primary_fps=30.0)


if __name__ == "__main__":
    unittest.main()
