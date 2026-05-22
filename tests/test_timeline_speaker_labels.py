# Version: 03.02.04
# Phase: PHASE2
import unittest
from unittest.mock import patch

from ui.timeline.speaker_labels import (
    current_speaker_settings,
    speaker_label_for_segment,
    speaker_rows_for_segment,
)


class TimelineSpeakerLabelsTests(unittest.TestCase):
    def test_speaker_id_uses_current_custom_name(self):
        settings = {"spk1_id": "00", "spk1_name": "소설가유모씨"}
        self.assertEqual(
            speaker_label_for_segment(settings, {"speaker": "SPEAKER_00"}),
            "소설가유모씨",
        )

    def test_missing_speaker_defaults_to_current_speaker_one_name(self):
        settings = {"spk1_id": "00", "spk1_name": "소설가유모씨"}
        self.assertEqual(
            speaker_label_for_segment(settings, {}),
            "소설가유모씨",
        )

    def test_saved_speaker_name_overrides_stale_owner_settings(self):
        with patch(
            "ui.timeline.speaker_labels.load_settings",
            return_value={"spk1_id": "00", "spk1_name": "소설가유모씨"},
        ):
            merged = current_speaker_settings({"spk1_id": "00", "spk1_name": "홍길동"})
        self.assertEqual(merged["spk1_name"], "소설가유모씨")

    def test_two_speaker_segment_uses_configured_names_as_rows(self):
        settings = {
            "spk1_id": "00",
            "spk1_name": "인터뷰어",
            "spk1_color": "#579DFF",
            "spk2_id": "01",
            "spk2_name": "게스트",
            "spk2_color": "#75C76B",
        }

        rows = speaker_rows_for_segment(
            settings,
            {"speaker": "00", "speaker_list": ["SPEAKER_00", "SPEAKER_01"]},
        )

        self.assertEqual([row["name"] for row in rows], ["인터뷰어", "게스트"])
        self.assertEqual([row["color"] for row in rows], ["#579DFF", "#75C76B"])


if __name__ == "__main__":
    unittest.main()
