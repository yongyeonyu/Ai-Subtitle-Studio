import unittest
from unittest import mock

from core.pipeline.pipeline_helpers import PipelineHelpersMixin


class _SpeakerRuntimeHarness(PipelineHelpersMixin):
    def __init__(self):
        self.min_speakers = 1
        self.max_speakers = 1
        self._effective_min_speakers = 1
        self._effective_max_speakers = 1
        self._speaker_map = []


class PipelineSpeakerDiarizationTests(unittest.TestCase):
    @mock.patch("core.pipeline.pipeline_helpers.automatic_speaker_ceiling", return_value=2)
    @mock.patch("core.pipeline.pipeline_helpers.load_settings", return_value={"speaker_diarization_auto_enabled": True})
    def test_preflight_runtime_override_escalates_local_two_speaker_detection(self, _mock_settings, _mock_ceiling):
        harness = _SpeakerRuntimeHarness()

        min_speakers, max_speakers = harness._apply_speaker_preflight_runtime_override(
            {
                "enabled": True,
                "lane": "targeted_diarization",
                "estimated_speaker_count": 2,
            }
        )

        self.assertEqual((min_speakers, max_speakers), (1, 2))
        self.assertTrue(harness._speaker_diarization_enabled())

    def test_runtime_speaker_diarization_groups_adjacent_turns_into_two_line_dialogue(self):
        harness = _SpeakerRuntimeHarness()
        harness._effective_max_speakers = 2
        harness._speaker_map = [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
        ]

        result = harness._apply_runtime_speaker_diarization(
            [
                {"start": 0.0, "end": 0.9, "text": "아이스로 드릴까요?"},
                {"start": 1.0, "end": 1.3, "text": "네네"},
            ]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "- 아이스로 드릴까요?\n- 네네")
        self.assertEqual(result[0]["speaker_list"], ["00", "01"])

    @mock.patch(
        "core.pipeline.pipeline_helpers.load_settings",
        return_value={"spk1_id": "00", "spk2_id": "01"},
    )
    def test_inline_dialogue_line_is_restored_even_when_diarizer_lumps_the_window(self, _mock_settings):
        harness = _SpeakerRuntimeHarness()
        harness._effective_max_speakers = 2
        harness._speaker_map = [
            {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
        ]

        result = harness._apply_runtime_speaker_diarization(
            [
                {"start": 0.0, "end": 2.0, "text": "- 아이스로 드릴까요? - 네네"},
            ]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "- 아이스로 드릴까요?\n- 네네")
        self.assertEqual(result[0]["speaker_list"], ["00", "01"])

    @mock.patch(
        "core.pipeline.pipeline_helpers.load_settings",
        return_value={"spk1_id": "00", "spk2_id": "01"},
    )
    def test_inline_dialogue_line_is_restored_even_without_speaker_map(self, _mock_settings):
        harness = _SpeakerRuntimeHarness()
        harness._effective_max_speakers = 2
        harness._speaker_map = []

        result = harness._apply_runtime_speaker_diarization(
            [
                {"start": 0.0, "end": 2.0, "text": "- 아이스로 드릴까요? - 네네"},
            ]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "- 아이스로 드릴까요?\n- 네네")
        self.assertEqual(result[0]["speaker_list"], ["00", "01"])


if __name__ == "__main__":
    unittest.main()
