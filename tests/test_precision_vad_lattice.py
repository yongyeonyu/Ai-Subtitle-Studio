import unittest

from core.subtitle_quality.precision_vad_lattice import (
    build_precision_vad_lattice_for_media,
    build_precision_voice_lattice,
)


class PrecisionVadLatticeTests(unittest.TestCase):
    def test_build_precision_voice_lattice_combines_measured_raw_and_existing_sources(self):
        lattice = build_precision_voice_lattice(
            [
                {"source": "measured_audio:silero", "weight": 1.0, "rows": [{"start": 1.00, "end": 1.90}]},
                {"source": "measured_audio:ten_vad", "weight": 0.95, "rows": [{"start": 1.04, "end": 1.86}]},
                {"source": "raw_audio:silero", "weight": 0.86, "rows": [{"start": 0.97, "end": 1.94}]},
                {"source": "existing_voice_activity", "weight": 0.78, "rows": [{"start": 1.02, "end": 1.88, "kind": "speech"}]},
            ]
        )

        self.assertEqual(len(lattice), 1)
        row = lattice[0]
        self.assertEqual(row["source"], "precision_voice_lattice")
        self.assertTrue(row["precision_lattice"])
        self.assertGreaterEqual(row["source_count"], 4)
        self.assertGreater(row["confidence"], 0.9)
        self.assertLessEqual(row["start"], 1.02)
        self.assertGreaterEqual(row["end"], 1.88)
        self.assertIn("measured_audio:silero", row["vad_sources"])
        self.assertIn("raw_audio:silero", row["vad_sources"])

    def test_build_precision_vad_lattice_for_media_runs_silero_and_ten_on_measured_and_raw_audio(self):
        calls = []

        def detector(wav_path, provider, settings):
            calls.append((wav_path, provider))
            if provider == "silero":
                return [{"start": 2.0, "end": 2.8}]
            return [{"start": 2.05, "end": 2.75}]

        result = build_precision_vad_lattice_for_media(
            "",
            settings={},
            existing_vad_segments=[{"start": 1.0, "end": 1.2}],
            existing_voice_activity_segments=[{"start": 3.0, "end": 3.4, "kind": "speech"}],
            audio_paths={
                "measured_audio_path": __file__,
                "raw_audio_path": __file__,
            },
            detector=detector,
            prepare_audio=False,
        )

        self.assertIn((__file__, "silero"), calls)
        self.assertIn((__file__, "ten_vad"), calls)
        self.assertEqual(result.source_counts["measured_audio:silero"], 1)
        self.assertEqual(result.source_counts["raw_audio:ten_vad"], 1)
        self.assertGreaterEqual(len(result.segments), 3)


if __name__ == "__main__":
    unittest.main()
