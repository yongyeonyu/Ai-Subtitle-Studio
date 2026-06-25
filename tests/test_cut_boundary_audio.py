import unittest

from core.cut_boundary import normalize_cut_boundaries
from core.cut_boundary_audio import (
    AUDIO_GAIN_BOUNDARY_SOURCE,
    AUDIO_GAIN_LINE_COLOR,
    AUDIO_SPECTRAL_BOUNDARY_SOURCE,
    AUDIO_SPECTRAL_LINE_COLOR,
    audio_spectral_flux_from_pcm16le,
    build_audio_gain_boundary_rows,
    build_audio_spectral_flux_boundary_rows,
    detect_audio_gain_changes,
    detect_audio_spectral_flux_changes,
)


class CutBoundaryAudioTests(unittest.TestCase):
    def test_detect_audio_gain_changes_finds_sustained_volume_shift(self):
        levels = [(idx + 0.5, -36.0 if idx < 8 else -18.0) for idx in range(16)]

        candidates = detect_audio_gain_changes(
            levels,
            threshold_db=10.0,
            min_gap_sec=4.0,
            context_windows=2,
            duration_sec=16.0,
        )

        self.assertGreaterEqual(len(candidates), 1)
        self.assertGreaterEqual(candidates[0]["local_sec"], 6.0)
        self.assertLessEqual(candidates[0]["local_sec"], 9.0)
        self.assertGreaterEqual(candidates[0]["score"], 10.0)

    def test_audio_gain_rows_are_neon_green_provisional_hints(self):
        rows = build_audio_gain_boundary_rows(
            [
                {
                    "local_sec": 8.0,
                    "score": 18.0,
                    "before_db": -36.0,
                    "after_db": -18.0,
                    "delta_db": 18.0,
                }
            ],
            clip_offset=100.0,
            clip_idx=2,
            fps=60.0,
            source_path="/tmp/sample.mp4",
            threshold_db=10.0,
            window_sec=2.0,
            sample_rate=4000,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], AUDIO_GAIN_BOUNDARY_SOURCE)
        self.assertEqual(rows[0]["status"], "provisional")
        self.assertFalse(rows[0]["verified"])
        self.assertEqual(rows[0]["line_color"], AUDIO_GAIN_LINE_COLOR)
        self.assertEqual(rows[0]["line_style"], "dash")
        self.assertIn(rows[0]["deep_boundary_decision"], {"verify", "keep"})
        self.assertGreater(rows[0]["deep_boundary_score"], 0.0)
        self.assertAlmostEqual(rows[0]["timeline_sec"], 108.0, places=3)

    def test_verified_visual_cut_drops_stale_audio_provisional_paint(self):
        rows = normalize_cut_boundaries(
            [
                {
                    "timeline_sec": 180.21336750307566,
                    "timeline_frame": 10802,
                    "fps": 59.940059661865234,
                    "source": "visual",
                    "status": "verified",
                    "verified": True,
                    "boundary_kind": "audio",
                    "provisional_type": "audio_gain",
                    "line_color": AUDIO_GAIN_LINE_COLOR,
                    "line_style": "solid",
                    "audio_gain_db_delta": 13.638,
                }
            ],
            primary_fps=59.940059661865234,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "visual")
        self.assertEqual(rows[0]["status"], "verified")
        self.assertEqual(rows[0]["boundary_kind"], "visual")
        self.assertEqual(rows[0]["audio_gain_db_delta"], 13.638)
        self.assertNotIn("provisional_type", rows[0])
        self.assertNotIn("line_color", rows[0])
        self.assertNotIn("line_style", rows[0])

    def test_spectral_flux_rows_capture_frequency_change_as_audio_hint(self):
        try:
            import numpy as np
        except Exception as exc:
            self.skipTest(f"numpy unavailable: {exc}")

        sample_rate = 4000
        tones = []
        for frequency in (220, 1200, 220):
            t = np.arange(sample_rate, dtype=np.float32) / float(sample_rate)
            tones.append((np.sin(2.0 * np.pi * frequency * t) * 0.45 * 32767.0).astype("<i2"))
        pcm = np.concatenate(tones).tobytes()

        flux_levels = audio_spectral_flux_from_pcm16le(
            pcm,
            sample_rate=sample_rate,
            window_sec=0.25,
        )
        candidates = detect_audio_spectral_flux_changes(
            flux_levels,
            threshold_multiplier=2.0,
            min_gap_sec=0.4,
            duration_sec=3.0,
            edge_guard_sec=0.0,
        )

        self.assertTrue(any(0.9 <= float(candidate["local_sec"]) <= 1.3 for candidate in candidates))
        rows = build_audio_spectral_flux_boundary_rows(
            candidates[:1],
            clip_offset=10.0,
            clip_idx=1,
            fps=30.0,
            source_path="/tmp/sample.mp4",
            threshold_multiplier=2.0,
            window_sec=0.25,
            sample_rate=sample_rate,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], AUDIO_SPECTRAL_BOUNDARY_SOURCE)
        self.assertEqual(rows[0]["line_color"], AUDIO_SPECTRAL_LINE_COLOR)
        self.assertEqual(rows[0]["provisional_type"], "audio_spectral_flux")
        self.assertGreater(rows[0]["audio_spectral_flux_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
