import os
import unittest
from unittest.mock import patch

from core import native_subtitle_stt_segments as native
from core.native_swift_subtitle_stt_segments import summarize_stt_segments_via_swift


class NativeSubtitleSTTSegmentsTests(unittest.TestCase):
    def test_stt_segments_summary_reports_stt2_lane_use(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_STT_SEGMENTS")
        rows = [
            {"start": 0.0, "end": 1.0, "text": "A", "stt_selected_source": "STT1"},
            {
                "start": 1.1,
                "end": 2.0,
                "text": "B",
                "stt_selected_source": "STT2",
                "stt_recheck_applied": True,
            },
            {"start": 1.9, "end": 2.5, "text": "C", "stt_ensemble_source": "STT1_SELECTIVE"},
            {
                "start": 2.7,
                "end": 3.0,
                "text": "D",
                "stt_ensemble_source": "STT2_SELECTIVE_RECHECK",
                "stt_word_precision_applied": True,
                "stt_route_secondary_recheck_hint": True,
            },
        ]
        try:
            os.environ["AI_SUBTITLE_NATIVE_STT_SEGMENTS"] = "1"
            summary = native.stt_segments_summary(rows)
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_STT_SEGMENTS", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_STT_SEGMENTS"] = previous

        self.assertEqual(summary["schema"], "ai_subtitle_studio.subtitle_stt_segments.summary.v1")
        self.assertEqual(summary["native_backend"], "cpp")
        self.assertEqual(summary["segment_count"], 4)
        self.assertEqual(summary["stt1_selected_count"], 2)
        self.assertEqual(summary["stt2_selected_count"], 2)
        self.assertEqual(summary["recheck_applied_count"], 1)
        self.assertEqual(summary["word_precision_count"], 1)
        self.assertEqual(summary["secondary_hint_count"], 1)
        self.assertEqual(summary["overlap_count"], 1)
        self.assertEqual(summary["source_switch_count"], 3)
        self.assertTrue(summary["stt2_active"])
        self.assertTrue(summary["selective_recheck_active"])
        self.assertTrue(summary["stable_for_timeline_feed"])

    def test_stt_segments_summary_falls_back_to_python_when_native_disabled(self):
        rows = [
            {"start": 0.0, "end": 1.0, "text": "A", "stt_selected_source": "STT1"},
            {"start": 1.25, "end": 2.0, "text": "B", "stt_selected_source": "STT2"},
        ]
        with patch("core.native_subtitle_stt_segments.native_subtitle_stt_segments_enabled", return_value=False):
            summary = native.stt_segments_summary(rows)

        self.assertEqual(summary["native_backend"], "python")
        self.assertEqual(summary["stt1_selected_count"], 1)
        self.assertEqual(summary["stt2_selected_count"], 1)
        self.assertEqual(summary["stt2_coverage_ratio"], 0.428571)
        self.assertTrue(summary["stt2_active"])

    def test_swift_stt_segments_summary_bridge_shapes_subtitle_core_payload(self):
        rows = [{"start": 0.0, "end": 1.0, "text": "테스트", "stt_selected_source": "STT2"}]
        with patch(
            "core.native_swift_subtitle_stt_segments.run_subtitle_core_operation_via_swift",
            return_value={
                "schema": "ai_subtitle_studio.subtitle_stt_segments.summary.v1",
                "segment_count": 1,
                "backend": "swift",
            },
        ) as run_operation:
            result = summarize_stt_segments_via_swift(rows)

        self.assertEqual(result["backend"], "swift")
        run_operation.assert_called_once()
        operation, payload = run_operation.call_args.args[:2]
        self.assertEqual(operation, "subtitle_stt_segments_summary")
        self.assertEqual(payload["segments"], rows)


if __name__ == "__main__":
    unittest.main()
