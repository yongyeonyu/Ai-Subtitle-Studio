import copy
import unittest

from core.project.nle_operations import (
    NLE_OPERATION_KINDS,
    NLE_OPERATION_SCHEMA,
    NLE_UNDO_SNAPSHOT_SCHEMA,
    NLEOperationValidationError,
    build_nle_editor_operation,
    build_nle_undo_snapshot,
)
from core.project.nle_projection_parity import build_project_nle_projection_parity_report
from core.project.project_context import build_editor_state, project_segments_to_editor
from core.project.nle_project_state import build_project_nle_state, record_nle_operation_journal_entry


def _project_with_segments(segments):
    return {
        "project_name": "nle_operation_case",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=segments,
            stt_preview_segments=[
                {"start": 4.0, "end": 5.0, "text": "preview", "stt_preview_source": "STT1"}
            ],
            cut_boundaries=[{"time": 2.0, "source": "visual", "status": "confirmed"}],
            primary_fps=30.0,
        ),
        "roughcut_state": {
            "selected_candidate_id": "roughcut_a",
            "candidates": [
                {
                    "candidate_id": "roughcut_a",
                    "outputs": {
                        "edl": {
                            "duration": 5.0,
                            "segments": [
                                {"segment_id": "chapter_0001", "output_start": 0.0, "output_end": 2.0},
                                {"segment_id": "chapter_0002", "output_start": 2.0, "output_end": 5.0},
                            ],
                            "stitched_cut_boundaries": [
                                {
                                    "time": 2.0,
                                    "timeline_sec": 2.0,
                                    "source": "roughcut_concat_join",
                                    "segment_before_id": "chapter_0001",
                                    "segment_after_id": "chapter_0002",
                                }
                            ],
                        },
                        "render_plan": {
                            "segment_manifest": [{"segment_id": "chapter_0001", "output_end": 2.0}],
                            "stitched_cut_boundaries": [
                                {
                                    "time": 2.0,
                                    "timeline_sec": 2.0,
                                    "source": "roughcut_concat_join",
                                    "segment_before_id": "chapter_0001",
                                    "segment_after_id": "chapter_0002",
                                }
                            ],
                        },
                    },
                }
            ],
        },
    }


def _stable_project():
    return _project_with_segments(
        [
            {
                "id": "caption_1",
                "start": 0.0,
                "end": 1.0,
                "text": "first",
                "speaker": "00",
                "stt_candidates": [
                    {"source": "STT1", "start": 0.0, "end": 1.0, "text": "first raw", "score": 0.81}
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
                    {"source": "STT2", "start": 2.0, "end": 3.0, "text": "second raw", "score": 0.75}
                ],
            },
        ]
    )


class NLEOperationModelTests(unittest.TestCase):
    def test_operation_builder_covers_allowed_kinds_with_required_undo_snapshot(self):
        project = _stable_project()
        before = copy.deepcopy(project)
        report = build_project_nle_projection_parity_report(project)
        rows = project_segments_to_editor(project, include_analysis_candidates=False)
        undo = build_nle_undo_snapshot(
            operation_id="op_caption_move",
            editor_rows=rows,
            candidate_lanes=[{"source": "STT1", "caption_id": "caption_1"}],
            silence_gaps=[row for row in rows if row.get("is_gap")],
            markers=[{"kind": "cut_boundary", "time": 2.0, "time_domain": "sequence"}],
            ui_state_ref={"active_segment_id": "caption_1"},
        )

        by_kind = {}
        for kind in sorted(NLE_OPERATION_KINDS):
            operation_id = f"op_{kind}"
            local_undo = undo
            if operation_id != undo.operation_id:
                local_undo = build_nle_undo_snapshot(operation_id=operation_id, editor_rows=rows)
            metadata = {"candidate_source": "STT1"} if kind == "candidate_confirm" else {}
            domain = "output" if kind == "roughcut_range_edit" else "sequence"
            op = build_nle_editor_operation(
                operation_id=operation_id,
                kind=kind,
                target_ids=["caption_1" if kind != "roughcut_range_edit" else "chapter_0001"],
                before_projection=report,
                after_projection=report,
                time_domain=domain,
                undo_snapshot=local_undo,
                metadata=metadata,
            )
            by_kind[kind] = op

        self.assertEqual(project, before)
        self.assertEqual(set(by_kind), set(NLE_OPERATION_KINDS))
        self.assertEqual(by_kind["caption_move"].schema, NLE_OPERATION_SCHEMA)
        self.assertEqual(by_kind["caption_move"].undo_snapshot.schema, NLE_UNDO_SNAPSHOT_SCHEMA)
        self.assertEqual(by_kind["roughcut_range_edit"].time_domain, "output")
        self.assertEqual(by_kind["candidate_confirm"].metadata["candidate_source"], "STT1")
        payload = by_kind["caption_move"].to_dict()
        self.assertEqual(payload["target_ids"], ["caption_1"])
        self.assertEqual(payload["undo_snapshot"]["ui_state_ref"]["active_segment_id"], "caption_1")

    def test_final_caption_operation_rejects_after_projection_overlap(self):
        before_project = _stable_project()
        after_project = _project_with_segments(
            [
                {"id": "caption_1", "start": 0.0, "end": 2.0, "text": "first"},
                {"id": "caption_2", "start": 1.0, "end": 3.0, "text": "second"},
            ]
        )
        before_report = build_project_nle_projection_parity_report(before_project)
        after_report = build_project_nle_projection_parity_report(after_project)
        undo = build_nle_undo_snapshot(
            operation_id="op_overlap",
            editor_rows=project_segments_to_editor(before_project, include_analysis_candidates=False),
        )

        with self.assertRaisesRegex(NLEOperationValidationError, "operation_projection_drift|operation_final_overlap"):
            build_nle_editor_operation(
                operation_id="op_overlap",
                kind="caption_move",
                target_ids=["caption_2"],
                before_projection=before_report,
                after_projection=after_report,
                time_domain="sequence",
                undo_snapshot=undo,
            )

    def test_candidate_confirm_requires_candidate_source_metadata(self):
        report = build_project_nle_projection_parity_report(_stable_project())
        undo = build_nle_undo_snapshot(operation_id="op_candidate", editor_rows=[])

        with self.assertRaisesRegex(NLEOperationValidationError, "candidate_confirm_source_required"):
            build_nle_editor_operation(
                operation_id="op_candidate",
                kind="candidate_confirm",
                target_ids=["caption_1"],
                before_projection=report,
                after_projection=report,
                time_domain="sequence",
                undo_snapshot=undo,
            )

    def test_roughcut_operation_requires_output_time_domain(self):
        report = build_project_nle_projection_parity_report(_stable_project())
        undo = build_nle_undo_snapshot(operation_id="op_roughcut", editor_rows=[])

        with self.assertRaisesRegex(NLEOperationValidationError, "operation_time_domain_invalid"):
            build_nle_editor_operation(
                operation_id="op_roughcut",
                kind="roughcut_range_edit",
                target_ids=["chapter_0001"],
                before_projection=report,
                after_projection=report,
                time_domain="sequence",
                undo_snapshot=undo,
            )

        op = build_nle_editor_operation(
            operation_id="op_roughcut",
            kind="roughcut_range_edit",
            target_ids=["chapter_0001"],
            before_projection=report,
            after_projection=report,
            time_domain="output",
            undo_snapshot=undo,
        )
        self.assertEqual(op.time_domain, "output")

    def test_operation_requires_matching_undo_snapshot(self):
        report = build_project_nle_projection_parity_report(_stable_project())
        undo = build_nle_undo_snapshot(operation_id="op_other", editor_rows=[])

        with self.assertRaisesRegex(NLEOperationValidationError, "operation_undo_snapshot_required"):
            build_nle_editor_operation(
                operation_id="op_missing",
                kind="caption_delete",
                target_ids=["caption_1"],
                before_projection=report,
                after_projection=report,
                time_domain="sequence",
                undo_snapshot=None,
            )
        with self.assertRaisesRegex(NLEOperationValidationError, "operation_undo_snapshot_mismatch"):
            build_nle_editor_operation(
                operation_id="op_missing",
                kind="caption_delete",
                target_ids=["caption_1"],
                before_projection=report,
                after_projection=report,
                time_domain="sequence",
                undo_snapshot=undo,
            )

    def test_operation_journal_records_bounded_runtime_tail(self):
        project = _stable_project()
        state = build_project_nle_state(project)
        report = build_project_nle_projection_parity_report(project)
        rows = project_segments_to_editor(project, include_analysis_candidates=False)

        for index in range(5):
            operation_id = f"op_caption_move_{index}"
            undo = build_nle_undo_snapshot(
                operation_id=operation_id,
                editor_rows=rows,
                ui_state_ref={"commit_boundary": "release", "commit_source": "center"},
            )
            operation = build_nle_editor_operation(
                operation_id=operation_id,
                kind="caption_move",
                target_ids=["caption_1"],
                before_projection=report,
                after_projection=report,
                time_domain="sequence",
                undo_snapshot=undo,
                metadata={
                    "operation_family": "caption_move",
                    "commit_boundary": "release",
                    "commit_source": "center",
                },
            )
            record_nle_operation_journal_entry(state, operation, projected_count=len(rows), max_entries=3)

        self.assertEqual([entry.sequence for entry in state.operation_journal], [3, 4, 5])
        self.assertEqual([entry.operation_id for entry in state.operation_journal], [
            "op_caption_move_2",
            "op_caption_move_3",
            "op_caption_move_4",
        ])
        self.assertEqual(state.operation_journal[-1].operation_kind, "caption_move")
        self.assertEqual(state.operation_journal[-1].operation_family, "caption_move")
        self.assertEqual(state.operation_journal[-1].commit_boundary, "release")
        self.assertEqual(state.operation_journal[-1].commit_source, "center")
        self.assertEqual(state.operation_journal[-1].projected_count, len(rows))
        self.assertEqual(state.operation_journal[-1].after_overlap_count, 0)
        self.assertEqual(state.metadata["operation_journal_runtime_only"], True)
        self.assertEqual(state.metadata["operation_journal_count"], 3)
        self.assertEqual(state.metadata["operation_journal_max_entries"], 3)


if __name__ == "__main__":
    unittest.main()
