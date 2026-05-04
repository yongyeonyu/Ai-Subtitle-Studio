# Version: 03.14.31
# Phase: PHASE2
import unittest

import numpy as np

from ui.editor.live_microphone_session import (
    append_waveform_preview,
    normalized_audio_level,
    pcm16_samples_from_bytes,
)


class LiveMicrophoneSessionHelperTests(unittest.TestCase):
    def test_pcm16_samples_from_bytes_normalizes_int16_range(self):
        raw = np.array([-32768, 0, 16384, 32767], dtype=np.int16).tobytes()

        samples = pcm16_samples_from_bytes(raw)

        self.assertEqual(samples.dtype, np.float32)
        self.assertAlmostEqual(float(samples[0]), -1.0, places=4)
        self.assertAlmostEqual(float(samples[1]), 0.0, places=4)
        self.assertAlmostEqual(float(samples[2]), 0.5, places=3)
        self.assertGreater(float(samples[3]), 0.99)

    def test_normalized_audio_level_is_zero_for_empty_input(self):
        self.assertEqual(normalized_audio_level(np.zeros(0, dtype=np.float32)), 0.0)

    def test_append_waveform_preview_keeps_recent_points_only(self):
        base = [0.1] * 12
        incoming = np.linspace(-1.0, 1.0, 800, dtype=np.float32)

        merged = append_waveform_preview(base, incoming, max_points=32)

        self.assertLessEqual(len(merged), 32)
        self.assertTrue(any(abs(value) > 0.2 for value in merged))
        self.assertTrue(all(-1.0 <= float(value) <= 1.0 for value in merged))


if __name__ == "__main__":
    unittest.main()
