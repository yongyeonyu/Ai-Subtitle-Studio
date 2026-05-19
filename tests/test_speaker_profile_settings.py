from __future__ import annotations

import os
import tempfile
import unittest

from core.audio import diarize
from core.speaker_profile_settings import (
    automatic_speaker_ceiling,
    materialize_automatic_speaker_settings,
    trained_speaker_profiles,
    visible_speaker_slots,
)


class SpeakerProfileSettingsTests(unittest.TestCase):
    def test_materialize_forces_auto_mode_and_keeps_legacy_count_hidden(self):
        data = materialize_automatic_speaker_settings(
            {
                "speaker_diarization_auto_enabled": False,
                "max_speakers": 3,
                "min_speakers": 2,
            }
        )

        self.assertTrue(data["speaker_diarization_auto_enabled"])
        self.assertEqual(data["min_speakers"], 1)
        self.assertEqual(data["max_speakers"], 1)

    def test_visible_slots_and_trained_profiles_follow_voice_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ("spk1_voice.wav", "spk2_guest.wav"):
                with open(os.path.join(tmpdir, name), "wb") as handle:
                    handle.write(b"RIFFstub")
            settings = materialize_automatic_speaker_settings(
                {
                    "spk1_name": "메인 진행자",
                    "spk2_name": "게스트",
                },
                voice_dir=tmpdir,
            )

            visible = visible_speaker_slots(settings, voice_dir=tmpdir)
            trained = trained_speaker_profiles(settings, voice_dir=tmpdir)

        self.assertEqual([row["id"] for row in visible], ["00", "01"])
        self.assertEqual([row["id"] for row in trained], ["00", "01"])
        self.assertTrue(settings["spk2_enabled"])

    def test_automatic_speaker_ceiling_expands_to_three_when_third_profile_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ("spk1_voice.wav", "spk3_guest.wav"):
                with open(os.path.join(tmpdir, name), "wb") as handle:
                    handle.write(b"RIFFstub")
            ceiling = automatic_speaker_ceiling(
                {
                    "spk3_name": "세 번째 화자",
                },
                voice_dir=tmpdir,
            )

        self.assertEqual(ceiling, 3)

    def test_materialize_clears_stale_voice_file_when_profile_audio_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = materialize_automatic_speaker_settings(
                {
                    "spk2_voice_file": "spk2_old.wav",
                },
                voice_dir=tmpdir,
            )

        self.assertNotIn("spk2_voice_file", settings)

    def test_reference_profile_matching_prefers_trained_speaker_ids(self):
        centroids = {
            0: diarize._normalize_embedding([1.0, 0.0, 0.0]),
            1: diarize._normalize_embedding([0.0, 1.0, 0.0]),
            2: diarize._normalize_embedding([0.0, 0.0, 1.0]),
        }
        mapping, details = diarize._match_reference_profiles(
            centroids,
            [
                {
                    "index": 2,
                    "id": "01",
                    "name": "게스트",
                    "embedding": diarize._normalize_embedding([0.0, 1.0, 0.0]),
                },
                {
                    "index": 1,
                    "id": "00",
                    "name": "진행자",
                    "embedding": diarize._normalize_embedding([1.0, 0.0, 0.0]),
                },
            ],
        )

        self.assertEqual(mapping[0], 0)
        self.assertEqual(mapping[1], 1)
        self.assertEqual([item["id"] for item in details], ["01", "00"])


if __name__ == "__main__":
    unittest.main()
