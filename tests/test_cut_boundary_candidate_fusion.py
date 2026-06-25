import unittest

from core.cut_boundary_audio import AUDIO_GAIN_BOUNDARY_SOURCE, AUDIO_SPECTRAL_BOUNDARY_SOURCE
from core.cut_boundary_candidate_fusion import (
    FUSED_PIONEER_DETECTOR,
    FUSED_PIONEER_SOURCE,
    candidate_time_sec,
    fuse_cut_boundary_candidate_rows,
)


class CutBoundaryCandidateFusionTests(unittest.TestCase):
    def test_visual_packet_and_audio_hints_cluster_into_one_pioneer_candidate(self):
        rows = fuse_cut_boundary_candidate_rows(
            [
                {"timeline_sec": 4.0, "source": "grid_profile_v3_parallel", "score": 120.0},
                {"timeline_sec": 4.12, "source": AUDIO_GAIN_BOUNDARY_SOURCE, "audio_gain_db_delta": 14.0},
                {"timeline_sec": 4.20, "source": "packet_energy_scout", "packet_score": 2.4},
                {
                    "timeline_sec": 4.25,
                    "source": AUDIO_SPECTRAL_BOUNDARY_SOURCE,
                    "audio_spectral_flux_score": 3.0,
                },
                {"timeline_sec": 9.0, "source": AUDIO_GAIN_BOUNDARY_SOURCE, "audio_gain_db_delta": 3.0},
            ],
            fps=30.0,
            window_sec=0.35,
        )

        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["source"], "grid_profile_v3_parallel")
        self.assertEqual(first["fusion_source"], FUSED_PIONEER_SOURCE)
        self.assertEqual(first["fusion_detector"], FUSED_PIONEER_DETECTOR)
        self.assertEqual(first["fusion_sources"], ["audio", "audio_spectral", "packet", "visual"])
        self.assertEqual(first["fusion_decision"], "keep")
        self.assertEqual(first["fusion_confidence"], "high")
        self.assertEqual(first["fusion_evidence_count"], 4)
        self.assertTrue(first["refine_pending"])
        self.assertFalse(first["verified"])

        second = rows[1]
        self.assertEqual(second["fusion_sources"], ["audio"])
        self.assertEqual(second["fusion_confidence"], "low")
        self.assertFalse(second["hard_cut_allowed"])

    def test_candidate_time_can_fallback_to_frame_fields(self):
        self.assertAlmostEqual(candidate_time_sec({"timeline_frame": 90, "fps": 30.0}), 3.0)


if __name__ == "__main__":
    unittest.main()
