import copy
import math
import tempfile
import unittest
from pathlib import Path

from core.project.nle_dual_write import (
    apply_candidate_confirm_dual_write_pilot,
    apply_caption_delete_dual_write_pilot,
    apply_caption_merge_dual_write_pilot,
    apply_caption_move_commit_dual_write_pilot,
    apply_caption_move_dual_write_pilot,
    apply_caption_range_replace_dual_write_pilot,
    apply_caption_resize_dual_write_pilot,
    apply_caption_split_dual_write_pilot,
    apply_caption_text_edit_dual_write_pilot,
    apply_gap_delete_dual_write_pilot,
    apply_gap_generate_dual_write_pilot,
    apply_marker_edit_dual_write_pilot,
)
from core.project.nle_operations import NLEOperationValidationError
from core.project.nle_project_state import NLE_PROJECT_STATE_RUNTIME_KEY, project_segments_from_nle_state
from core.project.project_context import build_editor_state, project_segments_to_editor
from core.project.project_io import (
    clear_project_file_cache,
    read_project_file,
    read_project_storage_payload,
    write_project_file,
)


def _project_with_gap():
    return {
        "project_name": "nle_gap_delete_pilot",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {
                    "id": "caption_1",
                    "start": 0.0,
                    "end": 1.0,
                    "text": "first",
                    "speaker": "00",
                    "stt_candidates": [
                        {"source": "STT1", "start": 0.0, "end": 1.0, "text": "first raw", "score": 0.8}
                    ],
                },
                {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
                {
                    "id": "caption_2",
                    "start": 2.0,
                    "end": 3.0,
                    "text": "second",
                    "speaker": "01",
                    "stt_candidates": [
                        {"source": "STT2", "start": 2.0, "end": 3.0, "text": "second raw", "score": 0.7}
                    ],
                },
            ],
            stt_preview_segments=[
                {"start": 4.0, "end": 5.0, "text": "diagnostic", "stt_preview_source": "STT1"}
            ],
            cut_boundaries=[{"time": 2.0, "source": "visual", "status": "confirmed"}],
            primary_fps=30.0,
        ),
    }


def _project_with_three_captions():
    return {
        "project_name": "nle_caption_move_pilot",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
                {"id": "caption_2", "start": 1.0, "end": 2.0, "text": "second", "speaker": "01"},
                {"id": "caption_3", "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
            ],
            stt_preview_segments=[
                {"start": 4.0, "end": 5.0, "text": "diagnostic", "stt_preview_source": "STT1"}
            ],
            cut_boundaries=[{"time": 2.0, "source": "visual", "status": "confirmed"}],
            primary_fps=30.0,
        ),
    }


class NLEDualWritePilotTests(unittest.TestCase):
    def assert_final_projection_is_release_stable(self, result):
        self.assertEqual(result.after_projection.diff_summary, "ok")
        self.assertEqual(result.after_projection.invalid_duration_count, 0)
        self.assertEqual(result.after_projection.non_monotonic_count, 0)
        self.assertEqual(result.after_projection.overlap_count, 0)
        self.assertLessEqual(result.after_projection.max_active_segments, 1)
        self.assertTrue(result.after_projection.save_reload_stable)
        self.assertTrue(result.after_projection.global_canvas_stable)

    def assert_rows_match_frames(self, rows, expected):
        actual = [
            (
                row.get("id"),
                row.get("text", ""),
                row.get("start_frame"),
                row.get("end_frame"),
            )
            for row in rows
        ]
        self.assertEqual(actual, expected)

    def test_caption_move_dual_write_routes_through_nle_state_and_projects_legacy_rows(self):
        project = _project_with_gap()
        result = apply_caption_move_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            new_start=3.0,
            new_end=4.0,
            commit_boundary="release",
            commit_source="center",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        nle_rows = project_segments_from_nle_state(project)

        self.assertEqual(result.operation_family, "caption_move")
        self.assertEqual(result.operation.kind, "caption_move")
        self.assertEqual(result.operation.target_ids, ("subtitle_vector_0002",))
        self.assertEqual(result.after_projection.overlap_count, 0)
        self.assertEqual(result.after_projection.max_active_segments, 1)
        self.assertEqual(result.operation.metadata["commit_boundary"], "release")
        self.assertEqual(result.operation.metadata["commit_source"], "center")
        self.assertEqual([(row.get("id"), row["start_frame"], row["end_frame"]) for row in legacy_rows], [
            ("subtitle_vector_0001", 0, 30),
            ("gap_1", 30, 60),
            ("subtitle_vector_0002", 90, 120),
        ])
        self.assertEqual([(row.get("id"), row["start_frame"], row["end_frame"]) for row in nle_rows], [
            ("subtitle_vector_0001", 0, 30),
            ("gap_1", 30, 60),
            ("subtitle_vector_0002", 90, 120),
        ])
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "caption_move")
        self.assertFalse(result.operation.metadata["taption_reorder"])

    def test_caption_move_dual_write_supports_taption_neighbor_reorder_contract(self):
        project = _project_with_three_captions()
        result = apply_caption_move_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            new_start=2.0,
            new_end=3.0,
            reorder_neighbor_id="subtitle_vector_0003",
            commit_boundary="release",
            commit_source="center_reorder_right",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)

        self.assertEqual(result.operation.kind, "caption_move")
        self.assertTrue(result.operation.metadata["taption_reorder"])
        self.assertEqual(result.operation.metadata["reorder_direction"], "right")
        self.assertEqual(result.operation.metadata["commit_boundary"], "release")
        self.assertEqual(result.operation.metadata["commit_source"], "center_reorder_right")
        self.assertEqual(result.operation.undo_snapshot.ui_state_ref["commit_boundary"], "release")
        self.assertEqual(result.operation.undo_snapshot.ui_state_ref["commit_source"], "center_reorder_right")
        self.assertEqual([row.get("text") for row in legacy_rows], ["first", "third", "second"])
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in legacy_rows], [(0, 30), (30, 60), (60, 90)])
        self.assertEqual([row.get("id") for row in result.projected_rows], ["subtitle_vector_0001", "subtitle_vector_0003", "subtitle_vector_0002"])
        self.assertEqual([row.get("text") for row in result.projected_rows], ["first", "third", "second"])
        self.assertEqual(result.after_projection.overlap_count, 0)
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_taption_reorder"], True)

    def test_caption_move_dual_write_supports_taption_left_neighbor_reorder_contract(self):
        project = _project_with_three_captions()
        result = apply_caption_move_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            new_start=0.0,
            new_end=1.0,
            reorder_neighbor_id="subtitle_vector_0001",
            commit_boundary="release",
            commit_source="center_reorder_left",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)

        self.assertEqual(result.operation.kind, "caption_move")
        self.assertTrue(result.operation.metadata["taption_reorder"])
        self.assertEqual(result.operation.metadata["reorder_direction"], "left")
        self.assertEqual(result.operation.metadata["commit_boundary"], "release")
        self.assertEqual(result.operation.metadata["commit_source"], "center_reorder_left")
        self.assertEqual([row.get("text") for row in legacy_rows], ["second", "first", "third"])
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in legacy_rows], [(0, 30), (30, 60), (60, 90)])
        self.assertEqual([row.get("id") for row in result.projected_rows], ["subtitle_vector_0002", "subtitle_vector_0001", "subtitle_vector_0003"])
        self.assertEqual(result.after_projection.overlap_count, 0)
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_taption_reorder"], True)

    def test_caption_move_dual_write_rejects_final_overlap_without_reorder(self):
        project = _project_with_three_captions()

        with self.assertRaisesRegex(NLEOperationValidationError, "operation_projection_drift|operation_final_overlap"):
            apply_caption_move_dual_write_pilot(
                project,
                caption_id="subtitle_vector_0002",
                new_start=0.5,
                new_end=1.5,
            )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertEqual([(row.get("id"), row.get("start"), row.get("end")) for row in legacy_rows], [
            ("subtitle_vector_0001", 0.0, 1.0),
            ("subtitle_vector_0002", 1.0, 2.0),
            ("subtitle_vector_0003", 2.0, 3.0),
        ])

    def test_caption_move_commit_dual_write_adopts_center_gap_absorption_plan(self):
        project = _project_with_gap()
        committed_rows = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
            {"line": 2, "start": 1.0, "end": 2.0, "text": "second", "speaker": "01"},
        ]

        result = apply_caption_move_commit_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            committed_rows=committed_rows,
            committed_caption_line=2,
            commit_boundary="release",
            commit_source="center",
            commit_mode="center_gap_absorb",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertEqual(result.operation.kind, "caption_move")
        self.assertEqual(result.operation.target_ids, ("subtitle_vector_0002",))
        self.assertEqual(result.operation.metadata["commit_boundary"], "release")
        self.assertEqual(result.operation.metadata["commit_source"], "center")
        self.assertEqual(result.operation.metadata["commit_mode"], "center_gap_absorb")
        self.assertEqual(result.operation.metadata["deleted_row_count"], 1)
        self.assertEqual(result.operation.metadata["silence_gap_deleted_count"], 1)
        self.assert_final_projection_is_release_stable(result)
        self.assert_rows_match_frames(legacy_rows, [
            ("subtitle_vector_0001", "first", 0, 30),
            ("subtitle_vector_0002", "second", 30, 60),
        ])
        self.assertFalse(any(row.get("is_gap") for row in legacy_rows))
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_caption_move_commit_mode"], "center_gap_absorb")

    def test_caption_move_commit_dual_write_adopts_center_overwrite_trim_plan(self):
        project = _project_with_three_captions()
        committed_rows = [
            {"line": 0, "start": 0.0, "end": 0.5, "text": "first", "speaker": "00"},
            {"line": 1, "start": 0.5, "end": 1.5, "text": "second", "speaker": "01"},
            {"line": 2, "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
        ]

        result = apply_caption_move_commit_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            committed_rows=committed_rows,
            committed_caption_line=1,
            commit_boundary="release",
            commit_source="center",
            commit_mode="center_overwrite_trim",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertEqual(result.operation.kind, "caption_move")
        self.assertEqual(result.operation.metadata["commit_mode"], "center_overwrite_trim")
        self.assertEqual(result.operation.metadata["deleted_row_count"], 0)
        self.assertGreaterEqual(result.operation.metadata["changed_row_count"], 2)
        self.assert_final_projection_is_release_stable(result)
        self.assert_rows_match_frames(legacy_rows, [
            ("subtitle_vector_0001", "first", 0, 15),
            ("subtitle_vector_0002", "second", 15, 45),
            ("subtitle_vector_0003", "third", 60, 90),
        ])

    def test_caption_range_replace_dual_write_adopts_partial_insert_transaction(self):
        project = _project_with_three_captions()
        committed_rows = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
            {"line": 1, "start": 1.0, "end": 1.5, "text": "second-a", "speaker": "01"},
            {"line": 2, "start": 1.5, "end": 2.0, "text": "second-b", "speaker": "01"},
            {"line": 3, "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
        ]

        result = apply_caption_range_replace_dual_write_pilot(
            project,
            target_start=1.0,
            target_end=2.0,
            committed_rows=committed_rows,
            commit_boundary="release",
            commit_source="partial_insert_range_replace",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertEqual(result.operation_family, "caption_range_replace")
        self.assertEqual(result.operation.kind, "caption_range_replace")
        self.assertEqual(result.operation.target_ids, ("subtitle_vector_0002",))
        self.assertEqual(result.operation.metadata["commit_source"], "partial_insert_range_replace")
        self.assertEqual(result.operation.metadata["replaced_row_count"], 1)
        self.assert_final_projection_is_release_stable(result)
        self.assert_rows_match_frames(legacy_rows, [
            ("subtitle_vector_0001", "first", 0, 30),
            ("subtitle_vector_0002", "second-a", 30, 45),
            ("caption_range_replace_0003", "second-b", 45, 60),
            ("subtitle_vector_0003", "third", 60, 90),
        ])
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "caption_range_replace")

    def test_caption_range_replace_dual_write_rejects_outside_drift_without_mutating_project(self):
        project = _project_with_three_captions()
        before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        committed_rows = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "first changed", "speaker": "00"},
            {"line": 1, "start": 1.0, "end": 2.0, "text": "second fixed", "speaker": "01"},
            {"line": 2, "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
        ]

        with self.assertRaisesRegex(ValueError, "nle_caption_range_replace_outside_drift"):
            apply_caption_range_replace_dual_write_pilot(
                project,
                target_start=1.0,
                target_end=2.0,
                committed_rows=committed_rows,
                commit_boundary="release",
                commit_source="partial_insert_range_replace",
            )

        after_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertRowsAlmostEqual(after_rows, before_rows)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, project)

    def test_caption_move_commit_dual_write_adopts_diamond_delete_keep_left_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "caption-move-diamond-delete.aissproj"
            project = _project_with_three_captions()
            committed_rows = [
                {"line": 0, "start": 0.0, "end": 2.0, "text": "first", "speaker": "00"},
                {"line": 2, "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
            ]

            result = apply_caption_move_commit_dual_write_pilot(
                project,
                caption_id="subtitle_vector_0001",
                committed_rows=committed_rows,
                committed_caption_line=0,
                commit_boundary="release",
                commit_source="diamond_delete",
                commit_mode="diamond_delete_keep_left",
                project_path=str(project_path),
            )

            legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
            nle_rows = project_segments_from_nle_state(project)
            write_project_file(str(project_path), copy.deepcopy(project))
            storage = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            reopened = read_project_file(str(project_path))
            reopened_rows = project_segments_to_editor(reopened, include_analysis_candidates=False)

        self.assertEqual(result.operation.kind, "caption_move")
        self.assertEqual(result.operation.metadata["commit_source"], "diamond_delete")
        self.assertEqual(result.operation.metadata["commit_mode"], "diamond_delete_keep_left")
        self.assertEqual(result.operation.metadata["deleted_row_count"], 1)
        self.assertEqual(result.operation.metadata["changed_row_count"], 1)
        self.assert_final_projection_is_release_stable(result)
        self.assert_rows_match_frames(legacy_rows, [
            ("subtitle_vector_0001", "first", 0, 60),
            ("subtitle_vector_0003", "third", 60, 90),
        ])
        self.assert_rows_match_frames(nle_rows, [
            ("subtitle_vector_0001", "first", 0, 60),
            ("subtitle_vector_0003", "third", 60, 90),
        ])
        self.assertRowsAlmostEqual(reopened_rows, legacy_rows)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage)

    def test_caption_text_edit_dual_write_updates_text_without_timing_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "caption-text-edit.aissproj"
            project = _project_with_three_captions()
            result = apply_caption_text_edit_dual_write_pilot(
                project,
                caption_id="subtitle_vector_0002",
                new_text="second\u2028edited",
                commit_boundary="release",
                commit_source="timeline_inline_text",
                project_path=str(project_path),
            )

            legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
            nle_rows = project_segments_from_nle_state(project)
            write_project_file(str(project_path), copy.deepcopy(project))
            storage = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            reopened = read_project_file(str(project_path))
            reopened_rows = project_segments_to_editor(reopened, include_analysis_candidates=False)

        self.assertEqual(result.operation_family, "caption_text_edit")
        self.assertEqual(result.operation.kind, "caption_text_edit")
        self.assertEqual(result.operation.target_ids, ("subtitle_vector_0002",))
        self.assertEqual(result.operation.metadata["old_text"], "second")
        self.assertEqual(result.operation.metadata["new_text"], "second\nedited")
        self.assertEqual(result.operation.metadata["commit_boundary"], "release")
        self.assertEqual(result.operation.metadata["commit_source"], "timeline_inline_text")
        self.assert_final_projection_is_release_stable(result)
        self.assertEqual([row.get("text") for row in legacy_rows], ["first", "second\nedited", "third"])
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in legacy_rows], [(0, 30), (30, 60), (60, 90)])
        self.assertEqual([row.get("text") for row in nle_rows], ["first", "second\nedited", "third"])
        self.assertRowsAlmostEqual(reopened_rows, legacy_rows)
        self.assertEqual(reopened_rows[1]["text"], "second\nedited")
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage)
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "caption_text_edit")

    def test_caption_text_edit_dual_write_preserves_speaker_split_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "caption-text-edit-speakers.aissproj"
            project = _project_with_three_captions()
            result = apply_caption_text_edit_dual_write_pilot(
                project,
                caption_id="subtitle_vector_0002",
                new_text="- second\n- reply",
                new_speaker="01",
                new_speaker_list=["01", "00"],
                commit_boundary="release",
                commit_source="timeline_speaker_split",
                project_path=str(project_path),
            )

            legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
            nle_rows = project_segments_from_nle_state(project)
            write_project_file(str(project_path), copy.deepcopy(project))
            storage = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            reopened = read_project_file(str(project_path))
            reopened_rows = project_segments_to_editor(reopened, include_analysis_candidates=False)

        self.assertEqual(result.operation_family, "caption_text_edit")
        self.assertEqual(result.operation.kind, "caption_text_edit")
        self.assertEqual(result.operation.metadata["commit_source"], "timeline_speaker_split")
        self.assertEqual(result.operation.metadata["old_speaker"], "01")
        self.assertEqual(result.operation.metadata["new_speaker"], "01")
        self.assertEqual(result.operation.metadata["old_speaker_list"], ["01"])
        self.assertEqual(result.operation.metadata["new_speaker_list"], ["01", "00"])
        self.assert_final_projection_is_release_stable(result)
        self.assertEqual(legacy_rows[1]["text"], "- second\n- reply")
        self.assertEqual(legacy_rows[1]["speaker"], "01")
        self.assertEqual(legacy_rows[1]["speaker_list"], ["01", "00"])
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in legacy_rows], [(0, 30), (30, 60), (60, 90)])
        self.assertEqual(nle_rows[1]["speaker_list"], ["01", "00"])
        self.assertRowsAlmostEqual(reopened_rows, legacy_rows)
        self.assertEqual(reopened_rows[1]["speaker_list"], ["01", "00"])
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage)

    def test_caption_resize_dual_write_trims_neighbor_and_preserves_disk_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "caption-resize.aissproj"
            project = _project_with_three_captions()
            result = apply_caption_resize_dual_write_pilot(
                project,
                caption_id="subtitle_vector_0002",
                new_start=0.5,
                new_end=2.0,
                edge="square_left",
                project_path=str(project_path),
            )

            legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
            nle_rows = project_segments_from_nle_state(project)
            write_project_file(str(project_path), copy.deepcopy(project))
            storage = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            reopened = read_project_file(str(project_path))
            reopened_rows = project_segments_to_editor(reopened, include_analysis_candidates=False)

        self.assertEqual(result.operation_family, "caption_resize")
        self.assertEqual(result.operation.kind, "caption_resize")
        self.assertEqual(result.operation.target_ids, ("subtitle_vector_0002",))
        self.assertEqual(result.operation.metadata["edge"], "square_left")
        self.assertEqual(result.operation.metadata["trimmed_neighbor_count"], 1)
        self.assertEqual(result.operation.metadata["deleted_neighbor_count"], 0)
        self.assert_final_projection_is_release_stable(result)
        self.assert_rows_match_frames(legacy_rows, [
            ("subtitle_vector_0001", "first", 0, 15),
            ("subtitle_vector_0002", "second", 15, 60),
            ("subtitle_vector_0003", "third", 60, 90),
        ])
        self.assert_rows_match_frames(nle_rows, [
            ("subtitle_vector_0001", "first", 0, 15),
            ("subtitle_vector_0002", "second", 15, 60),
            ("subtitle_vector_0003", "third", 60, 90),
        ])
        self.assertRowsAlmostEqual(reopened_rows, legacy_rows)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage)
        self.assertNotIn("nle", storage)
        self.assertNotIn("nle_snapshot", storage)
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "caption_resize")

    def test_caption_resize_dual_write_diamond_updates_shared_boundary_atomically(self):
        project = _project_with_three_captions()
        result = apply_caption_resize_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0001",
            new_start=0.0,
            new_end=1.4,
            edge="diamond",
            linked_caption_id="subtitle_vector_0002",
            linked_new_start=1.4,
            linked_new_end=2.0,
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)

        self.assertEqual(result.operation.kind, "caption_resize")
        self.assertEqual(result.operation.target_ids, ("subtitle_vector_0001", "subtitle_vector_0002"))
        self.assertEqual(result.operation.metadata["linked_caption_id"], "subtitle_vector_0002")
        self.assert_final_projection_is_release_stable(result)
        self.assert_rows_match_frames(legacy_rows, [
            ("subtitle_vector_0001", "first", 0, 42),
            ("subtitle_vector_0002", "second", 42, 60),
            ("subtitle_vector_0003", "third", 60, 90),
        ])
        self.assertRowsAlmostEqual(result.operation.undo_snapshot.editor_rows, [
            {"id": "subtitle_vector_0001", "start": 0.0, "end": 1.0},
            {"id": "subtitle_vector_0002", "start": 1.0, "end": 2.0},
            {"id": "subtitle_vector_0003", "start": 2.0, "end": 3.0},
        ])

    def test_caption_resize_dual_write_absorbs_silence_gap_without_final_overlap(self):
        project = _project_with_gap()
        result = apply_caption_resize_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            new_start=1.0,
            new_end=3.0,
            edge="square_left",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)

        self.assertEqual(result.operation.kind, "caption_resize")
        self.assertEqual(result.operation.metadata["deleted_neighbor_count"], 1)
        self.assert_final_projection_is_release_stable(result)
        self.assert_rows_match_frames(legacy_rows, [
            ("subtitle_vector_0001", "first", 0, 30),
            ("subtitle_vector_0002", "second", 30, 90),
        ])
        self.assertFalse(any(row.get("is_gap") for row in legacy_rows))
        self.assertGreaterEqual(len(result.operation.undo_snapshot.silence_gaps), 1)

    def test_caption_resize_dual_write_rejects_overlapped_diamond_without_mutating_project(self):
        project = _project_with_three_captions()
        before_rows = project_segments_to_editor(project, include_analysis_candidates=False)

        with self.assertRaisesRegex(NLEOperationValidationError, "operation_projection_drift|operation_final_overlap"):
            apply_caption_resize_dual_write_pilot(
                project,
                caption_id="subtitle_vector_0001",
                new_start=0.0,
                new_end=1.6,
                edge="diamond",
                linked_caption_id="subtitle_vector_0002",
                linked_new_start=1.4,
                linked_new_end=2.0,
            )

        after_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertRowsAlmostEqual(after_rows, before_rows)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, project)

    def test_caption_delete_dual_write_replaces_final_caption_with_silence_gap(self):
        project = _project_with_gap()
        result = apply_caption_delete_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            replacement_gap_id="gap_deleted_caption_2",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        nle_rows = project_segments_from_nle_state(project)

        self.assertEqual(result.operation_family, "caption_delete")
        self.assertEqual(result.operation.kind, "caption_delete")
        self.assertEqual(result.operation.target_ids, ("subtitle_vector_0002",))
        self.assertEqual(result.operation.metadata["replacement_gap_id"], "gap_deleted_caption_2")
        self.assertEqual(result.operation.metadata["delete_mode"], "replace_with_silence_gap")
        self.assertEqual(result.after_projection.overlap_count, 0)
        self.assertEqual(result.after_projection.max_active_segments, 1)
        self.assertEqual([bool(row.get("is_gap")) for row in legacy_rows], [False, True, True])
        self.assertEqual([row.get("text", "") for row in legacy_rows], ["first", "", ""])
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in legacy_rows], [(0, 30), (30, 60), (60, 90)])
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in nle_rows], [(0, 30), (30, 60), (60, 90)])
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "caption_delete")
        self.assertGreaterEqual(len(result.operation.undo_snapshot.candidate_lanes), 2)

    def test_caption_delete_dual_write_rejects_gap_or_missing_target_without_mutating_project(self):
        project = _project_with_gap()
        before_rows = project_segments_to_editor(project, include_analysis_candidates=False)

        with self.assertRaisesRegex(ValueError, "nle_caption_delete_target_missing"):
            apply_caption_delete_dual_write_pilot(project, caption_id="gap_1")

        after_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertRowsAlmostEqual(after_rows, before_rows)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, project)

    def test_caption_merge_dual_write_merges_adjacent_final_captions(self):
        project = _project_with_three_captions()
        result = apply_caption_merge_dual_write_pilot(
            project,
            left_caption_id="subtitle_vector_0001",
            right_caption_id="subtitle_vector_0002",
            merged_text="first second",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        nle_rows = project_segments_from_nle_state(project)

        self.assertEqual(result.operation_family, "caption_merge")
        self.assertEqual(result.operation.kind, "caption_merge")
        self.assertEqual(result.operation.target_ids, ("subtitle_vector_0001", "subtitle_vector_0002"))
        self.assertEqual(result.operation.metadata["kept_caption_id"], "subtitle_vector_0001")
        self.assertEqual(result.operation.metadata["removed_caption_id"], "subtitle_vector_0002")
        self.assert_final_projection_is_release_stable(result)
        self.assert_rows_match_frames(legacy_rows, [
            ("subtitle_vector_0001", "first second", 0, 60),
            ("subtitle_vector_0003", "third", 60, 90),
        ])
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in nle_rows], [(0, 60), (60, 90)])
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "caption_merge")

    def test_caption_merge_dual_write_rejects_gap_or_missing_target_without_mutating_project(self):
        project = _project_with_gap()
        before_rows = project_segments_to_editor(project, include_analysis_candidates=False)

        with self.assertRaisesRegex(ValueError, "nle_caption_merge_right_target_missing"):
            apply_caption_merge_dual_write_pilot(
                project,
                left_caption_id="subtitle_vector_0001",
                right_caption_id="gap_1",
            )

        after_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertRowsAlmostEqual(after_rows, before_rows)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, project)

    def test_caption_split_dual_write_splits_final_caption_without_overlap(self):
        project = _project_with_three_captions()
        result = apply_caption_split_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            split_sec=1.4,
            left_text="sec",
            right_text="ond",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        nle_rows = project_segments_from_nle_state(project)

        self.assertEqual(result.operation_family, "caption_split")
        self.assertEqual(result.operation.kind, "caption_split")
        self.assertEqual(result.operation.target_ids, ("subtitle_vector_0002", "subtitle_vector_0002_split_right"))
        self.assertEqual(result.operation.metadata["caption_id"], "subtitle_vector_0002")
        self.assertEqual(result.operation.metadata["new_caption_id"], "subtitle_vector_0002_split_right")
        self.assert_final_projection_is_release_stable(result)
        self.assert_rows_match_frames(legacy_rows, [
            ("subtitle_vector_0001", "first", 0, 30),
            ("subtitle_vector_0002", "sec", 30, 42),
            ("subtitle_vector_0002_split_right", "ond", 42, 60),
            ("subtitle_vector_0003", "third", 60, 90),
        ])
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in nle_rows], [(0, 30), (30, 42), (42, 60), (60, 90)])
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "caption_split")

    def test_caption_split_dual_write_rejects_gap_or_edge_split_without_mutating_project(self):
        project = _project_with_gap()
        before_rows = project_segments_to_editor(project, include_analysis_candidates=False)

        with self.assertRaisesRegex(ValueError, "nle_caption_split_target_missing"):
            apply_caption_split_dual_write_pilot(
                project,
                caption_id="gap_1",
                split_sec=1.5,
                left_text="left",
                right_text="right",
            )
        with self.assertRaisesRegex(ValueError, "nle_caption_split_time_outside_target"):
            apply_caption_split_dual_write_pilot(
                project,
                caption_id="subtitle_vector_0001",
                split_sec=0.0,
                left_text="left",
                right_text="right",
            )

        after_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertRowsAlmostEqual(after_rows, before_rows)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, project)

    def test_candidate_confirm_dual_write_replaces_final_caption_and_preserves_candidate_lane(self):
        project = _project_with_three_captions()
        confirmed_rows = [
            {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
            {
                "id": "caption_2",
                "start": 1.0,
                "end": 2.0,
                "text": "STT2 후보",
                "speaker": "01",
                "stt_selected_source": "STT2",
                "stt_candidates": [{"source": "STT2", "start": 1.0, "end": 2.0, "text": "STT2 후보"}],
            },
            {"id": "caption_3", "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
        ]
        candidate = {"source": "STT2", "start": 1.0, "end": 2.0, "text": "STT2 후보"}

        result = apply_candidate_confirm_dual_write_pilot(
            project,
            confirmed_rows=confirmed_rows,
            candidate=candidate,
            candidate_source="STT2",
            candidate_lanes=[candidate],
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        nle_rows = project_segments_from_nle_state(project)

        self.assertEqual(result.operation_family, "candidate_confirm")
        self.assertEqual(result.operation.kind, "candidate_confirm")
        self.assertEqual(result.operation.metadata["candidate_source"], "STT2")
        self.assertEqual(result.operation.metadata["candidate_text"], "STT2 후보")
        self.assertEqual(result.operation.target_ids, ("subtitle_vector_0002",))
        self.assert_final_projection_is_release_stable(result)
        self.assertEqual([row.get("text") for row in legacy_rows], ["first", "STT2 후보", "third"])
        self.assertEqual(legacy_rows[1]["stt_selected_source"], "STT2")
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in nle_rows], [(0, 30), (30, 60), (60, 90)])
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "candidate_confirm")
        self.assertGreaterEqual(len(result.operation.undo_snapshot.candidate_lanes), 2)

    def test_candidate_confirm_dual_write_rejects_invalid_source_without_mutating_project(self):
        project = _project_with_three_captions()
        before_rows = project_segments_to_editor(project, include_analysis_candidates=False)

        with self.assertRaisesRegex(NLEOperationValidationError, "candidate_confirm_source_required"):
            apply_candidate_confirm_dual_write_pilot(
                project,
                confirmed_rows=before_rows,
                candidate={"source": "UNKNOWN", "start": 1.0, "end": 2.0, "text": "bad"},
                candidate_source="UNKNOWN",
            )

        after_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertRowsAlmostEqual(after_rows, before_rows)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, project)

    def test_gap_generate_dual_write_splits_gap_from_playhead_and_preserves_left_gap(self):
        project = _project_with_gap()
        result = apply_gap_generate_dual_write_pilot(
            project,
            gap_id="gap_1",
            sub_start=1.5,
            sub_end=2.0,
            mode="from",
            text="새자막",
        )

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        nle_rows = project_segments_from_nle_state(project)

        self.assertEqual(result.operation_family, "gap_generate")
        self.assertEqual(result.operation.kind, "gap_generate")
        self.assertEqual(result.operation.target_ids, ("gap_1",))
        self.assertEqual(result.operation.metadata["mode"], "from")
        self.assertTrue(result.operation.metadata["left_gap_preserved"])
        self.assertFalse(result.operation.metadata["right_gap_preserved"])
        self.assertEqual(result.after_projection.overlap_count, 0)
        self.assertEqual(result.after_projection.max_active_segments, 1)
        self.assertEqual(
            [(row.get("text", ""), bool(row.get("is_gap")), row["start_frame"], row["end_frame"]) for row in legacy_rows],
            [
                ("first", False, 0, 30),
                ("", True, 30, 45),
                ("새자막", False, 45, 60),
                ("second", False, 60, 90),
            ],
        )
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in nle_rows], [(0, 30), (30, 45), (45, 60), (60, 90)])
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "gap_generate")

    def test_gap_generate_dual_write_rejects_caption_outside_gap_without_mutating_project(self):
        project = _project_with_gap()
        before_rows = project_segments_to_editor(project, include_analysis_candidates=False)

        with self.assertRaisesRegex(ValueError, "nle_gap_generate_caption_outside_gap"):
            apply_gap_generate_dual_write_pilot(
                project,
                gap_id="gap_1",
                sub_start=0.5,
                sub_end=2.0,
                mode="to",
            )

        after_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertRowsAlmostEqual(after_rows, before_rows)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, project)

    def test_gap_delete_dual_write_routes_through_nle_state_and_projects_legacy_rows(self):
        project = _project_with_gap()
        result = apply_gap_delete_dual_write_pilot(project, gap_id="gap_1")

        legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
        nle_rows = project_segments_from_nle_state(project)

        self.assertEqual(result.operation_family, "gap_delete")
        self.assertEqual(result.operation.kind, "gap_delete")
        self.assertEqual(result.operation.target_ids, ("gap_1",))
        self.assertEqual(result.before_projection.gap_count, 1)
        self.assertEqual(result.after_projection.gap_count, 0)
        self.assertEqual(result.after_projection.overlap_count, 0)
        self.assertEqual(result.after_projection.max_active_segments, 1)
        self.assertEqual([row.get("text", "") for row in result.projected_rows], ["first", "second"])
        self.assertFalse(any(row.get("is_gap") for row in legacy_rows))
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in legacy_rows], [(0, 30), (60, 90)])
        self.assertEqual([(row["start_frame"], row["end_frame"]) for row in nle_rows], [(0, 30), (60, 90)])
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "gap_delete")
        self.assertEqual(len(result.operation.undo_snapshot.silence_gaps), 1)
        self.assertGreaterEqual(len(result.operation.undo_snapshot.candidate_lanes), 2)

    def test_gap_delete_dual_write_does_not_persist_runtime_nle_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "gap-delete.aissproj"
            project = _project_with_gap()
            result = apply_gap_delete_dual_write_pilot(project, gap_id="gap_1", project_path=str(project_path))

            write_project_file(str(project_path), copy.deepcopy(project))
            storage = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            reopened = read_project_file(str(project_path))
            reopened_rows = project_segments_to_editor(reopened, include_analysis_candidates=False)

        self.assertEqual(result.after_projection.diff_summary, "ok")
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage)
        self.assertNotIn("nle", storage)
        self.assertNotIn("nle_snapshot", storage)
        self.assertFalse(any(row.get("is_gap") for row in reopened_rows))
        self.assertEqual([row.get("text", "") for row in reopened_rows], ["first", "second"])

    def test_marker_edit_dual_write_records_provisional_cut_boundary_create(self):
        project = _project_with_gap()
        marker = {"timeline_sec": 1.5, "timeline_frame": 45, "fps": 30.0, "status": "provisional"}

        result = apply_marker_edit_dual_write_pilot(
            project,
            action="create",
            marker=marker,
            before_markers=[],
            after_markers=[marker],
            commit_source="provisional_cut_boundary_create",
        )

        self.assertEqual(result.operation_family, "marker_edit")
        self.assertEqual(result.operation.kind, "marker_edit")
        self.assertEqual(result.operation.metadata["action"], "create")
        self.assertEqual(result.operation.metadata["marker_kind"], "cut_boundary")
        self.assertEqual(result.operation.metadata["commit_boundary"], "release")
        self.assertEqual(result.operation.metadata["commit_source"], "provisional_cut_boundary_create")
        self.assertEqual(result.operation.metadata["before_marker_count"], 0)
        self.assertEqual(result.operation.metadata["after_marker_count"], 1)
        self.assertEqual(len(result.operation.undo_snapshot.markers), 0)
        self.assertEqual(len(project["editor_state"]["analysis"]["cut_boundary_provisional_boundaries"]), 1)
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_pilot_family"], "marker_edit")
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_marker_action"], "create")
        self.assertEqual(len(result.projected_rows), len(project_segments_to_editor(project, include_analysis_candidates=False)))

    def test_marker_edit_dual_write_records_provisional_cut_boundary_delete(self):
        marker = {"timeline_sec": 1.5, "timeline_frame": 45, "fps": 30.0, "status": "provisional"}
        project = _project_with_gap()
        project["editor_state"] = build_editor_state(
            mode="single",
            media_files=[],
            segments=project_segments_to_editor(project, include_analysis_candidates=False),
            cut_boundaries=[{"time": 2.0, "source": "visual", "status": "confirmed"}],
            provisional_cut_boundaries=[marker],
            primary_fps=30.0,
            preserve_segment_identity=True,
        )

        result = apply_marker_edit_dual_write_pilot(
            project,
            action="delete",
            marker=marker,
            before_markers=[marker],
            after_markers=[],
            commit_source="provisional_cut_boundary_delete",
        )

        self.assertEqual(result.operation.kind, "marker_edit")
        self.assertEqual(result.operation.metadata["action"], "delete")
        self.assertEqual(result.operation.metadata["before_marker_count"], 1)
        self.assertEqual(result.operation.metadata["after_marker_count"], 0)
        self.assertEqual(len(result.operation.undo_snapshot.markers), 1)
        self.assertEqual(project["editor_state"]["analysis"]["cut_boundary_provisional_boundaries"], [])
        self.assertEqual(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata["dual_write_marker_action"], "delete")

    def test_gap_delete_dual_write_rejects_missing_gap_target(self):
        project = _project_with_gap()

        with self.assertRaisesRegex(ValueError, "nle_gap_delete_target_missing:missing_gap"):
            apply_gap_delete_dual_write_pilot(project, gap_id="missing_gap")

        rows = project_segments_to_editor(project, include_analysis_candidates=False)
        self.assertTrue(any(row.get("is_gap") for row in rows))

    def assertRowsAlmostEqual(self, actual_rows, expected_rows):
        self.assertEqual(len(actual_rows), len(expected_rows))
        for actual, expected in zip(actual_rows, expected_rows):
            for key in ("id", "text", "is_gap"):
                if key in expected:
                    self.assertEqual(actual.get(key), expected.get(key))
            for key in ("start", "end"):
                self.assertTrue(
                    math.isclose(float(actual.get(key, 0.0)), float(expected.get(key, 0.0)), abs_tol=1e-6),
                    f"{key}: {actual.get(key)} != {expected.get(key)}",
                )


if __name__ == "__main__":
    unittest.main()
