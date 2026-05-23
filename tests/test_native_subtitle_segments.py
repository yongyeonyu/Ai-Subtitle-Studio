import os
import unittest
from unittest.mock import patch

from core import native_subtitle_segments as native
from core.native_swift_subtitle_segments import summarize_segments_via_swift


class NativeSubtitleSegmentsTests(unittest.TestCase):
    def test_segment_summary_reports_save_reopen_invariants(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_SEGMENTS")
        rows = [
            {"start": 0.0, "end": 1.0, "text": "첫 문장"},
            {"start": 0.9, "end": 2.0, "text": ""},
            {"start": 1.8, "end": 1.7, "text": "잘못된 길이"},
            {"start": 1.6, "end": 2.4, "text": "역순"},
        ]
        try:
            os.environ["AI_SUBTITLE_NATIVE_SEGMENTS"] = "1"
            summary = native.segment_summary(rows)
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_SEGMENTS", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_SEGMENTS"] = previous

        self.assertEqual(summary["schema"], "ai_subtitle_studio.subtitle_segments.summary.v1")
        self.assertEqual(summary["native_backend"], "cpp")
        self.assertEqual(summary["segment_count"], 4)
        self.assertEqual(summary["invalid_duration_count"], 1)
        self.assertEqual(summary["non_monotonic_count"], 1)
        self.assertEqual(summary["overlap_count"], 3)
        self.assertEqual(summary["empty_text_count"], 1)
        self.assertFalse(summary["stable_for_save_reopen"])

    def test_segment_summary_falls_back_to_python_when_native_disabled(self):
        rows = [
            {"start": 0.0, "end": 1.0, "text": "A"},
            {"start": 1.25, "end": 2.0, "text": "BC"},
        ]
        with patch("core.native_subtitle_segments.native_subtitle_segments_enabled", return_value=False):
            summary = native.segment_summary(rows)

        self.assertEqual(summary["native_backend"], "python")
        self.assertEqual(summary["segment_count"], 2)
        self.assertEqual(summary["invalid_duration_count"], 0)
        self.assertEqual(summary["max_gap"], 0.25)
        self.assertTrue(summary["stable_for_save_reopen"])

    def test_swift_segments_summary_bridge_shapes_subtitle_core_payload(self):
        rows = [{"start": 0.0, "end": 1.0, "text": "테스트"}]
        with patch(
            "core.native_swift_subtitle_segments.run_subtitle_core_operation_via_swift",
            return_value={
                "schema": "ai_subtitle_studio.subtitle_segments.summary.v1",
                "segment_count": 1,
                "backend": "swift",
            },
        ) as run_operation:
            result = summarize_segments_via_swift(rows)

        self.assertEqual(result["backend"], "swift")
        run_operation.assert_called_once()
        operation, payload = run_operation.call_args.args[:2]
        self.assertEqual(operation, "subtitle_segments_summary")
        self.assertEqual(payload["segments"], rows)


if __name__ == "__main__":
    unittest.main()
