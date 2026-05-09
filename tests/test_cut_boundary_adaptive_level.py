import unittest

from core.cut_boundary import cut_boundary_adaptive_enabled, cut_boundary_level, cut_boundary_scan_profile


class CutBoundaryAdaptiveLevelTests(unittest.TestCase):
    def test_auto_level_uses_low_for_long_auto_media(self):
        settings = {
            "scan_cut_boundary_level": "auto",
            "subtitle_mode": "auto",
            "cut_boundary_media_duration_sec": 24 * 60 + 10,
        }

        self.assertTrue(cut_boundary_adaptive_enabled(settings))
        self.assertEqual(cut_boundary_level(settings), "low")
        profile = cut_boundary_scan_profile(settings)
        self.assertEqual(profile["resolved_level"], "low")
        self.assertTrue(profile["adaptive"])

    def test_auto_level_uses_medium_for_short_media(self):
        settings = {
            "scan_cut_boundary_level": "auto",
            "subtitle_mode": "auto",
            "cut_boundary_media_duration_sec": 5 * 60,
        }

        self.assertEqual(cut_boundary_level(settings), "medium")

    def test_auto_level_uses_medium_for_high_mode_even_when_long(self):
        settings = {
            "scan_cut_boundary_level": "auto",
            "subtitle_mode": "high",
            "cut_boundary_media_duration_sec": 60 * 60,
        }

        self.assertEqual(cut_boundary_level(settings), "medium")

    def test_explicit_level_ignores_stale_adaptive_flag(self):
        settings = {
            "scan_cut_boundary_level": "low",
            "cut_boundary_adaptive_level_enabled": True,
            "subtitle_mode": "high",
            "cut_boundary_media_duration_sec": 5 * 60,
        }

        self.assertFalse(cut_boundary_adaptive_enabled(settings))
        self.assertEqual(cut_boundary_level(settings), "low")


if __name__ == "__main__":
    unittest.main()
