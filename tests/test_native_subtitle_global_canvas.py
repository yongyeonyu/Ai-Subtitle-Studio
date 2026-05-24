import os
import unittest
from unittest.mock import patch

from core import native_subtitle_global_canvas as native
from core.native_swift_subtitle_global_canvas import summarize_global_canvas_via_swift


class NativeSubtitleGlobalCanvasTests(unittest.TestCase):
    def test_global_canvas_summary_reports_occupancy_and_gaps(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_GLOBAL_CANVAS")
        rows = [
            {"start": 0.0, "end": 1.0, "text": "A"},
            {"start": 0.5, "end": 1.5, "text": "B"},
            {"start": 3.0, "end": 4.0, "text": "C"},
            {"start": 2.0, "end": 2.0, "text": "invalid"},
        ]
        try:
            os.environ["AI_SUBTITLE_NATIVE_GLOBAL_CANVAS"] = "1"
            summary = native.global_canvas_summary(rows, duration=4.0, bin_count=4)
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_GLOBAL_CANVAS", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_GLOBAL_CANVAS"] = previous

        self.assertEqual(summary["schema"], "ai_subtitle_studio.subtitle_global_canvas.summary.v1")
        self.assertEqual(summary["native_backend"], "cpp")
        self.assertEqual(summary["segment_count"], 4)
        self.assertEqual(summary["valid_segment_count"], 3)
        self.assertEqual(summary["invalid_duration_count"], 1)
        self.assertEqual(summary["occupied_bin_count"], 3)
        self.assertEqual(summary["dense_bin_count"], 1)
        self.assertEqual(summary["max_bin_active"], 2)
        self.assertEqual(summary["max_active_bin_index"], 0)
        self.assertEqual(summary["coverage_duration"], 2.5)
        self.assertEqual(summary["coverage_ratio"], 0.625)
        self.assertEqual(summary["longest_empty_span_sec"], 1.5)
        self.assertEqual(summary["longest_empty_start_sec"], 1.5)
        self.assertEqual(summary["longest_empty_end_sec"], 3.0)
        self.assertEqual(summary["max_active_segments"], 2)
        self.assertFalse(summary["stable_for_global_canvas"])

    def test_global_canvas_summary_falls_back_to_python_when_native_disabled(self):
        rows = [
            {"start": 0.0, "end": 1.0, "text": "A"},
            {"start": 2.0, "end": 3.0, "text": "B"},
        ]
        with patch("core.native_subtitle_global_canvas.native_subtitle_global_canvas_enabled", return_value=False):
            summary = native.global_canvas_summary(rows, duration=4.0, bin_count=4)

        self.assertEqual(summary["native_backend"], "python")
        self.assertEqual(summary["segment_count"], 2)
        self.assertEqual(summary["occupied_bin_count"], 2)
        self.assertEqual(summary["coverage_ratio"], 0.5)
        self.assertEqual(summary["longest_empty_span_sec"], 1.0)
        self.assertEqual(summary["longest_empty_start_sec"], 1.0)
        self.assertEqual(summary["longest_empty_end_sec"], 2.0)
        self.assertEqual(summary["max_active_bin_index"], 0)
        self.assertTrue(summary["stable_for_global_canvas"])

    def test_global_canvas_merged_segments_compacts_lane_without_changing_text_order(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_GLOBAL_CANVAS")
        rows = [
            {"start": 2.0, "end": 2.4, "text": "뒤", "lane": "SUBTITLE"},
            {"start": 0.0, "end": 1.0, "text": "앞", "lane": "SUBTITLE"},
            {"start": 1.02, "end": 1.4, "text": "중간", "lane": "SUBTITLE"},
            {"start": 1.5, "end": 1.8, "text": "대기", "lane": "STT1"},
        ]
        try:
            os.environ["AI_SUBTITLE_NATIVE_GLOBAL_CANVAS"] = "1"
            merged = native.global_canvas_merged_segments(
                rows,
                lanes=("SUBTITLE",),
                output_lane="SUBTITLE",
                max_gap_sec=0.05,
                include_text=True,
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_GLOBAL_CANVAS", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_GLOBAL_CANVAS"] = previous

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["start"], 0.0)
        self.assertEqual(merged[0]["end"], 1.4)
        self.assertEqual(merged[0]["text"], "앞 중간")
        self.assertEqual(merged[0]["count"], 2)
        self.assertEqual(merged[1]["text"], "뒤")

    def test_global_canvas_merged_segments_python_fallback_keeps_silence_textless(self):
        rows = [
            {"start": 0.0, "end": 0.5, "lane": "SILENCE"},
            {"start": 0.52, "end": 1.0, "lane": "SILENCE", "text": "ignored"},
        ]
        with patch("core.native_subtitle_global_canvas.native_subtitle_global_canvas_enabled", return_value=False):
            merged = native.global_canvas_merged_segments(
                rows,
                lanes=("SILENCE",),
                output_lane="SILENCE",
                max_gap_sec=0.05,
                include_text=False,
            )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["lane"], "SILENCE")
        self.assertEqual(merged[0]["count"], 2)
        self.assertNotIn("text", merged[0])

    def test_swift_global_canvas_summary_bridge_shapes_subtitle_core_payload(self):
        rows = [{"start": 0.0, "end": 1.0, "text": "테스트"}]
        with patch(
            "core.native_swift_subtitle_global_canvas.run_subtitle_core_operation_via_swift",
            return_value={
                "schema": "ai_subtitle_studio.subtitle_global_canvas.summary.v1",
                "segment_count": 1,
                "backend": "swift",
            },
        ) as run_operation:
            result = summarize_global_canvas_via_swift(rows, duration=10.0, bin_count=24)

        self.assertEqual(result["backend"], "swift")
        run_operation.assert_called_once()
        operation, payload = run_operation.call_args.args[:2]
        self.assertEqual(operation, "subtitle_global_canvas_summary")
        self.assertEqual(payload["segments"], rows)
        self.assertEqual(payload["duration"], 10.0)
        self.assertEqual(payload["bin_count"], 24)

    def test_swift_global_canvas_summary_bridge_can_request_merged_segments(self):
        rows = [{"start": 0.0, "end": 1.0, "text": "테스트", "lane": "SUBTITLE"}]
        with patch(
            "core.native_swift_subtitle_global_canvas.run_subtitle_core_operation_via_swift",
            return_value={
                "schema": "ai_subtitle_studio.subtitle_global_canvas.summary.v1",
                "segment_count": 1,
                "backend": "swift",
                "merged_segments": [{"start": 0.0, "end": 1.0, "lane": "SUBTITLE", "text": "테스트", "count": 1}],
            },
        ) as run_operation:
            result = summarize_global_canvas_via_swift(
                rows,
                duration=10.0,
                bin_count=24,
                include_merged_segments=True,
                lanes=("SUBTITLE",),
                output_lane="SUBTITLE",
                max_gap_sec=0.1,
            )

        self.assertEqual(result["merged_segments"][0]["text"], "테스트")
        payload = run_operation.call_args.args[1]
        self.assertTrue(payload["include_merged_segments"])
        self.assertEqual(payload["allowed_lanes"], ["SUBTITLE"])
        self.assertEqual(payload["merge_gap_sec"], 0.1)


if __name__ == "__main__":
    unittest.main()
