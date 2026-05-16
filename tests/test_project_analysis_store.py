import unittest
from unittest.mock import patch

from core.project.project_analysis_store import (
    ensure_project_analysis_store,
    mirror_project_voice_activity_analysis,
    normalize_project_voice_activity_segment,
    normalize_project_voice_activity_segments,
    store_project_stt_candidate_tracks,
    store_project_voice_activity_segments,
)
from core.project.project_assets import copy_project_track_rows_with_counts


class _StreamingRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def __bool__(self):
        raise AssertionError("project analysis rows should not be truth-tested")

    def __iter__(self):
        return iter(self._rows)


class ProjectAnalysisStoreTests(unittest.TestCase):
    def test_ensure_project_analysis_store_initializes_analysis_slots(self):
        project = {"editor_state": {}}

        analysis, editor_analysis = ensure_project_analysis_store(project)

        self.assertIs(project["analysis"], analysis)
        self.assertIs(project["editor_state"]["analysis"], editor_analysis)

    def test_store_project_voice_activity_segments_can_copy_rows_without_aliasing(self):
        project = {}
        rows = [{"start": 0.5, "end": 1.25, "label": "voice"}]

        stored = store_project_voice_activity_segments(
            project,
            rows,
            copy_rows=True,
            timebase={"primary_fps": 30.0},
        )
        rows[0]["start"] = 9.0

        self.assertEqual(stored[0]["start"], 0.5)
        self.assertEqual(project["analysis"]["voice_activity_schema"], "subtitle_detection.v1")
        self.assertEqual(project["analysis"]["voice_activity_timebase"]["primary_fps"], 30.0)
        self.assertIsNot(project["analysis"]["voice_activity_segments"][0], rows[0])

    def test_store_project_voice_activity_segments_accepts_streaming_rows_without_truth_testing(self):
        project = {}
        rows = _StreamingRows([{"start": 0.5, "end": 1.25, "label": "voice"}])

        stored = store_project_voice_activity_segments(project, rows, copy_rows=False)

        self.assertEqual(stored[0]["label"], "voice")
        self.assertIs(stored[0], project["analysis"]["voice_activity_segments"][0])

    def test_store_project_stt_candidate_tracks_can_copy_rows_and_count_tracks(self):
        project = {}
        tracks = {
            "STT1": [{"text": "후보 일"}],
            "STT2": [{"text": "후보 이"}],
        }

        stored = store_project_stt_candidate_tracks(project, tracks, copy_tracks=True)
        tracks["STT1"][0]["text"] = "변경"

        self.assertEqual(stored["STT1"][0]["text"], "후보 일")
        self.assertEqual(project["analysis"]["stt_candidate_counts"], {"STT1": 1, "STT2": 1})
        self.assertIsNot(project["analysis"]["stt_candidate_tracks"]["STT1"][0], tracks["STT1"][0])

    def test_store_project_stt_candidate_tracks_copy_tracks_uses_combined_copy_count_helper(self):
        project = {}
        tracks = {"STT1": [{"text": "후보 일"}]}

        expected_tracks, expected_counts = copy_project_track_rows_with_counts(tracks)
        with patch(
            "core.project.project_analysis_store.copy_project_track_rows_with_counts",
            return_value=(expected_tracks, expected_counts),
        ) as helper:
            stored = store_project_stt_candidate_tracks(project, tracks, copy_tracks=True)

        helper.assert_called_once_with(tracks)
        self.assertEqual(stored, expected_tracks)
        self.assertEqual(project["analysis"]["stt_candidate_counts"], expected_counts)

    def test_mirror_project_voice_activity_analysis_copies_list_without_aliasing_rows(self):
        shared_row = {"start": 0.5, "end": 1.25, "label": "voice"}
        project = {
            "analysis": {
                "voice_activity_segments": [shared_row],
                "voice_activity_schema": "subtitle_detection.v1",
            },
            "editor_state": {},
        }

        mirrored = mirror_project_voice_activity_analysis(
            project,
            rows=project["analysis"]["voice_activity_segments"],
            timebase={"primary_fps": 30.0},
        )

        self.assertEqual(mirrored[0]["label"], "voice")
        self.assertIsNot(mirrored, project["analysis"]["voice_activity_segments"])
        self.assertIs(mirrored[0], shared_row)
        self.assertEqual(project["editor_state"]["analysis"]["voice_activity_schema"], "subtitle_detection.v1")
        self.assertEqual(project["editor_state"]["analysis"]["voice_activity_timebase"]["primary_fps"], 30.0)

    def test_normalize_project_voice_activity_segment_can_override_time_without_id(self):
        normalized = normalize_project_voice_activity_segment(
            {"start": 0.2, "end": 0.7, "label": "voice", "priority": "4"},
            1,
            start=0.5,
            end=1.25,
            include_id=False,
        )

        self.assertEqual(normalized["index"], 2)
        self.assertEqual(normalized["start"], 0.5)
        self.assertEqual(normalized["end"], 1.25)
        self.assertEqual(normalized["priority"], "4")
        self.assertNotIn("id", normalized)

    def test_normalize_project_voice_activity_segments_can_coerce_priority_without_mutating_input(self):
        rows = [
            {"start": 0.2, "end": 0.7, "label": "voice", "priority": "4"},
            {"start": 1.0, "end": 1.5, "label": "music"},
        ]

        normalized = normalize_project_voice_activity_segments(rows, priority_as_int=True)

        self.assertEqual(normalized[0]["priority"], 4)
        self.assertEqual(normalized[1]["priority"], 0)
        self.assertEqual(rows[0]["priority"], "4")

    def test_normalize_project_voice_activity_segments_accepts_streaming_rows_without_truth_testing(self):
        rows = _StreamingRows([{"start": 0.2, "end": 0.7, "label": "voice", "priority": "4"}])

        normalized = normalize_project_voice_activity_segments(rows, priority_as_int=True)

        self.assertEqual(normalized[0]["priority"], 4)


if __name__ == "__main__":
    unittest.main()
