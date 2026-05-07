# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
import unittest

from core.stt_mode import (
    FINAL_SUBTITLE_SOURCE,
    FINAL_SUBTITLE_STATUS,
    RAW_DICTATION_SOURCE,
    RAW_DICTATION_STATUS,
    STT_LORA_BUNDLE_SCHEMA,
    STT_MODE_LEARNING_SCHEMA,
    STT_MODE_STATE_SCHEMA,
    STT_WORK_SEGMENT_SOURCE,
    STT_WORK_STATUS,
    canonical_frame_timing,
)


class STTModeModelsTests(unittest.TestCase):
    def test_schema_and_source_constants_exist(self):
        self.assertEqual(STT_MODE_STATE_SCHEMA, "ai_subtitle_studio.stt_mode_state.v1")
        self.assertEqual(STT_MODE_LEARNING_SCHEMA, "ai_subtitle_studio.stt_mode_learning.v1")
        self.assertEqual(STT_LORA_BUNDLE_SCHEMA, "ai_subtitle_studio.stt_lora_bundle.v1")
        self.assertEqual(STT_WORK_SEGMENT_SOURCE, "stt_vad_ensemble")
        self.assertEqual(RAW_DICTATION_SOURCE, "human_dictation")
        self.assertEqual(FINAL_SUBTITLE_SOURCE, "human_dictation_resegmented")

    def test_required_status_values_are_defined(self):
        self.assertIn("empty", STT_WORK_STATUS)
        self.assertIn("listened", STT_WORK_STATUS)
        self.assertIn("input_done", STT_WORK_STATUS)
        self.assertIn("resegmented", STT_WORK_STATUS)
        self.assertIn("needs_review", STT_WORK_STATUS)
        self.assertIn("skipped", STT_WORK_STATUS)
        self.assertIn("locked", RAW_DICTATION_STATUS)
        self.assertIn("manual_edited", FINAL_SUBTITLE_STATUS)

    def test_canonical_frame_timing_derives_seconds_from_frames(self):
        timing = canonical_frame_timing(1.02, 2.04, frame_rate=25.0)

        self.assertEqual(timing["start_frame"], 25)
        self.assertEqual(timing["end_frame"], 51)
        self.assertEqual(timing["timeline_start_frame"], 25)
        self.assertEqual(timing["timeline_end_frame"], 51)
        self.assertEqual(timing["frame_range"]["unit"], "frame")
        self.assertEqual(timing["frame_range"]["start"], 25)
        self.assertEqual(timing["frame_range"]["end"], 51)
        self.assertAlmostEqual(timing["start"], 1.0)
        self.assertAlmostEqual(timing["end"], 2.04)


if __name__ == "__main__":
    unittest.main()
