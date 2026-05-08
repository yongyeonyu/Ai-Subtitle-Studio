import unittest

import numpy as np

from ui.timeline.timeline_waveform import (
    WAVEFORM_SAMPLE_RATE,
    _decode_f32le_samples,
    _downsample_waveform_samples,
    _ffmpeg_waveform_cmd,
)


class TimelineWaveformWorkerTests(unittest.TestCase):
    def test_decode_f32le_samples_from_pipe_bytes(self):
        original = np.array([-0.25, 0.5, 1.0], dtype=np.float32)

        decoded = _decode_f32le_samples(original.tobytes())

        np.testing.assert_allclose(decoded, original)
        self.assertEqual(decoded.dtype, np.float32)

    def test_downsample_waveform_samples_normalizes_peaks(self):
        samples = np.zeros(WAVEFORM_SAMPLE_RATE, dtype=np.float32)
        samples[100:110] = 0.5
        samples[1000:1010] = -1.0

        waveform, duration = _downsample_waveform_samples(samples)

        self.assertAlmostEqual(duration, 1.0, places=3)
        self.assertEqual(len(waveform), 100)
        self.assertAlmostEqual(float(waveform.max()), 1.0, places=6)

    def test_ffmpeg_waveform_cmd_streams_to_stdout(self):
        cmd = _ffmpeg_waveform_cmd("/tmp/input.mp4")

        self.assertIn("pipe:1", cmd)
        self.assertIn("-nostdin", cmd)
        self.assertNotIn(".raw", " ".join(cmd))


if __name__ == "__main__":
    unittest.main()
