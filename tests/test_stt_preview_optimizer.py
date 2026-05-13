# Version: 03.10.03
# Phase: PHASE2

import unittest
from unittest.mock import patch

from core.pipeline.stt_preview_optimizer import optimize_stt_preview_segments, raw_stt_preview_segments
from core.cut_boundary import magnetize_segments_to_cut_boundaries


class SttPreviewOptimizerTest(unittest.TestCase):
    def test_raw_preview_candidates_are_available_before_optimizer(self):
        result = raw_stt_preview_segments(
            [{"start": 0.5, "end": 1.25, "text": "즉시 후보"}],
            source_label="STT2",
            clip_offset=10.0,
            clip_idx=3,
            clip_path="/tmp/clip.mp4",
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "즉시 후보")
        self.assertEqual(result[0]["stt_preview_source"], "STT2")
        self.assertFalse(result[0]["stt_preview_optimized"])
        self.assertEqual(result[0]["stt_preview_optimizer"], "raw_realtime")
        self.assertAlmostEqual(result[0]["start"], 10.5)
        self.assertAlmostEqual(result[0]["end"], 11.25)
        self.assertEqual(result[0]["_clip_idx"], 3)
        self.assertEqual(result[0]["_clip_file"], "/tmp/clip.mp4")

    def test_preview_candidates_run_through_candidate_rules_optimizer(self):
        raw = [{"start": 1.0, "end": 3.0, "text": "원본 후보"}]
        optimized = [{"start": 1.0, "end": 2.0, "text": "정리 후보"}]

        with patch("core.engine.subtitle_engine.optimize_stt_candidate_segments", return_value=optimized) as optimize:
            result = optimize_stt_preview_segments(raw, source_label="STT2", vad_segments=[{"start": 1.0, "end": 3.0}])

        optimize.assert_called_once()
        self.assertEqual(result[0]["text"], "정리 후보")
        self.assertEqual(result[0]["stt_preview_source"], "STT2")
        self.assertTrue(result[0]["stt_pending"])
        self.assertTrue(result[0]["_live_stt_preview"])
        self.assertTrue(result[0]["stt_preview_optimized"])
        self.assertEqual(result[0]["stt_preview_optimizer"], "subtitle_split_gap_rules")
        self.assertIn("stt_score", result[0])
        self.assertIn("stt_score_color", result[0])

    def test_multiclip_preview_keeps_clip_metadata_after_optimization(self):
        optimized = [{"start": 0.5, "end": 1.25, "text": "클립 후보"}]

        with patch("core.engine.subtitle_engine.optimize_stt_candidate_segments", return_value=optimized):
            result = optimize_stt_preview_segments(
                [{"start": 0.5, "end": 1.25, "text": "raw"}],
                source_label="STT1",
                clip_offset=10.0,
                clip_idx=2,
                clip_path="/tmp/a.mp4",
            )

        self.assertAlmostEqual(result[0]["start"], 10.5)
        self.assertAlmostEqual(result[0]["end"], 11.25)
        self.assertEqual(result[0]["_clip_idx"], 2)
        self.assertEqual(result[0]["_clip_file"], "/tmp/a.mp4")

    def test_preview_candidates_snap_near_confirmed_and_provisional_cut_boundaries(self):
        optimized = [{"start": 2.76, "end": 3.18, "text": "클립 후보"}]

        with patch("core.engine.subtitle_engine.optimize_stt_candidate_segments", return_value=optimized):
            result = optimize_stt_preview_segments(
                [{"start": 2.76, "end": 3.18, "text": "raw"}],
                source_label="STT1",
                cut_boundaries=[{"timeline_sec": 3.0, "timeline_frame": 72, "fps": 24.0}],
                provisional_cut_boundaries=[{"timeline_sec": 2.8, "timeline_frame": 67, "fps": 24.0, "status": "provisional"}],
            )

        self.assertAlmostEqual(result[0]["start"], 67.0 / 24.0, places=6)
        self.assertAlmostEqual(result[0]["end"], 3.0, places=3)

    def test_magnetize_prefers_provisional_start_and_confirmed_end(self):
        result = magnetize_segments_to_cut_boundaries(
            [{"start": 2.77, "end": 3.12, "text": "후보"}],
            confirmed_boundaries=[{"timeline_sec": 3.0, "timeline_frame": 72, "fps": 24.0}],
            provisional_boundaries=[{"timeline_sec": 2.8, "timeline_frame": 67, "fps": 24.0, "status": "provisional"}],
            primary_fps=24.0,
            provisional_window_sec=0.05,
            confirmed_window_sec=0.25,
        )

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["start"], 67.0 / 24.0, places=6)
        self.assertAlmostEqual(result[0]["end"], 3.0, places=6)
        self.assertTrue(result[0]["cut_boundary_magnetized"])


if __name__ == "__main__":
    unittest.main()
