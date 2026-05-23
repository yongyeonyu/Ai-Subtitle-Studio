import os
import unittest
from unittest.mock import patch

import numpy as np

from core import native_subtitle_waveform as native
from core.native_swift_subtitle_waveform import summarize_waveform_via_swift
from ui.timeline.timeline_waveform import _downsample_waveform_samples


class NativeSubtitleWaveformTests(unittest.TestCase):
    def test_downsample_f32le_matches_python_reference(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_WAVEFORM")
        samples = np.zeros(2000, dtype=np.float32)
        samples[100:110] = 0.5
        samples[1000:1010] = -1.0
        try:
            os.environ["AI_SUBTITLE_NATIVE_WAVEFORM"] = "1"
            native_out = native.downsample_f32le(
                samples.tobytes(),
                sample_rate=2000,
                points_per_second=100,
                duration=None,
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_WAVEFORM", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_WAVEFORM"] = previous

        reference = _downsample_waveform_samples(samples)
        self.assertIsNotNone(native_out)
        np.testing.assert_allclose(native_out[0], reference[0], rtol=0, atol=1e-6)
        self.assertAlmostEqual(native_out[1], reference[1], places=6)

    def test_waveform_summary_reports_peak_and_speech_ratio(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_WAVEFORM")
        try:
            os.environ["AI_SUBTITLE_NATIVE_WAVEFORM"] = "1"
            result = native.waveform_summary(np.array([0.0, 0.25, -1.0, 0.01], dtype=np.float32), speech_threshold=0.02)
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_WAVEFORM", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_WAVEFORM"] = previous

        self.assertIsNotNone(result)
        self.assertEqual(result["schema"], "ai_subtitle_studio.subtitle_waveform.summary.v1")
        self.assertEqual(result["native_backend"], "cpp")
        self.assertEqual(result["sample_count"], 4)
        self.assertAlmostEqual(result["max_peak"], 1.0, places=6)
        self.assertEqual(result["speech_like_count"], 2)
        self.assertAlmostEqual(result["speech_like_ratio"], 0.5, places=6)

    def test_swift_waveform_summary_bridge_shapes_subtitle_core_payload(self):
        with patch(
            "core.native_swift_subtitle_waveform.run_subtitle_core_operation_via_swift",
            return_value={
                "schema": "ai_subtitle_studio.subtitle_waveform.summary.v1",
                "sample_count": 2,
                "backend": "swift",
            },
        ) as run_operation:
            result = summarize_waveform_via_swift(np.array([0.0, 1.0], dtype=np.float32), duration=1.0)

        self.assertEqual(result["backend"], "swift")
        run_operation.assert_called_once()
        operation, payload = run_operation.call_args.args[:2]
        self.assertEqual(operation, "subtitle_waveform_summary")
        self.assertEqual(payload["waveform"], [0.0, 1.0])
        self.assertEqual(payload["duration"], 1.0)


if __name__ == "__main__":
    unittest.main()
