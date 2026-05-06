import unittest

from core.cut_boundary_audio import AUDIO_GAIN_BOUNDARY_SOURCE, AUDIO_GAIN_LINE_COLOR
from core.cut_boundary_fusion import (
    FUSED_BOUNDARY_SOURCE,
    SILENCE_BOUNDARY_SOURCE,
    STT_CONTEXT_BOUNDARY_SOURCE,
    build_roughcut_fusion_boundary_rows,
    build_silence_boundary_rows,
    build_stt_context_shift_boundary_rows,
    fuse_cut_boundary_rows,
)
from core.roughcut.pipeline import _hard_cut_times_from_scene_changes


class CutBoundaryFusionTests(unittest.TestCase):
    def test_visual_and_audio_rows_fuse_into_hard_boundary(self):
        rows = fuse_cut_boundary_rows(
            [
                {"time": 10.0, "source": "visual", "score": 500.0, "status": "confirmed", "verified": True},
                {
                    "time": 10.35,
                    "source": AUDIO_GAIN_BOUNDARY_SOURCE,
                    "audio_gain_db_delta": 14.0,
                    "status": "provisional",
                    "verified": False,
                },
            ],
            settings={"scan_cut_audio_gain_threshold_db": 10.0, "cut_boundary_fusion_window_sec": 0.8},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], FUSED_BOUNDARY_SOURCE)
        self.assertEqual(rows[0]["fusion_sources"], ["audio", "visual"])
        self.assertEqual(rows[0]["fusion_decision"], "keep")
        self.assertTrue(rows[0]["hard_cut_allowed"])
        self.assertIn(10.0, _hard_cut_times_from_scene_changes(rows, media_duration=30.0))

    def test_audio_only_boundary_stays_neon_green_provisional_hint(self):
        rows = fuse_cut_boundary_rows(
            [
                {
                    "time": 12.0,
                    "source": AUDIO_GAIN_BOUNDARY_SOURCE,
                    "audio_gain_db_delta": 18.0,
                    "status": "provisional",
                    "verified": False,
                }
            ],
            settings={"scan_cut_audio_gain_threshold_db": 10.0},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["line_color"], AUDIO_GAIN_LINE_COLOR)
        self.assertEqual(rows[0]["status"], "provisional")
        self.assertFalse(rows[0]["hard_cut_allowed"])
        self.assertEqual(_hard_cut_times_from_scene_changes(rows, media_duration=30.0), ())

    def test_silence_gap_rows_are_roughcut_boundaries_not_hard_cuts(self):
        rows = build_silence_boundary_rows(
            [
                {"start": 0.0, "end": 2.0, "text": "앞부분"},
                {"start": 5.0, "end": 7.0, "text": "뒷부분"},
            ],
            min_silence_sec=1.0,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], SILENCE_BOUNDARY_SOURCE)
        self.assertAlmostEqual(rows[0]["timeline_sec"], 3.5)
        self.assertFalse(rows[0]["hard_cut_allowed"])

    def test_stt_context_shift_rows_capture_topic_changes(self):
        rows = build_stt_context_shift_boundary_rows(
            [
                {"start": 0.0, "end": 2.0, "text": "차량 외부 디자인을 살펴봅니다"},
                {"start": 2.2, "end": 4.0, "text": "다음으로 실내 공간과 편의 기능을 봅니다"},
            ],
            threshold=0.55,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], STT_CONTEXT_BOUNDARY_SOURCE)
        self.assertGreaterEqual(rows[0]["topic_shift_score"], 0.55)
        self.assertFalse(rows[0]["hard_cut_allowed"])

    def test_roughcut_fusion_combines_video_audio_silence_and_context(self):
        rows = build_roughcut_fusion_boundary_rows(
            [
                {"start": 0.0, "end": 2.0, "text": "차량 외부 디자인을 살펴봅니다"},
                {"start": 5.0, "end": 7.0, "text": "다음으로 실내 공간과 편의 기능을 봅니다"},
            ],
            [
                {"time": 5.1, "source": "visual", "score": 160.0},
                {"time": 5.0, "source": AUDIO_GAIN_BOUNDARY_SOURCE, "audio_gain_db_delta": 15.0},
            ],
            media_duration=20.0,
            settings={
                "roughcut_silence_gap_prefer_sec": 1.0,
                "roughcut_context_shift_boundary_threshold": 0.55,
                "cut_boundary_fusion_window_sec": 2.0,
                "scan_cut_audio_gain_threshold_db": 10.0,
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fusion_sources"], ["audio", "silence", "stt_context", "visual"])
        self.assertTrue(rows[0]["hard_cut_allowed"])


if __name__ == "__main__":
    unittest.main()
