import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.audio.audio_runtime_services import plan_audio_route_workers
from core.pipeline.cut_boundary_strategy import CutBoundaryCandidateStrategy, CutBoundaryPrescanStrategy
from core.pipeline.single_pipeline_plan import (
    PipelineProgressCoordinator,
    build_single_pipeline_iteration_plan,
    hard_cut_seconds_from_rows,
)
from core.project.project_session_service import editor_session_rows


class _NoBoolRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def __bool__(self):
        raise AssertionError("rows should not be truth-tested")

    def __iter__(self):
        return iter(self._rows)


class ActionItemRuntimeServiceTests(unittest.TestCase):
    def test_cut_boundary_candidate_strategy_marks_and_removes_followed_rows(self):
        strategy = CutBoundaryCandidateStrategy()
        provisional = [
            {"timeline_sec": 1.2345, "clip_idx": 0, "status": "provisional"},
            {"timeline_sec": 2.0, "clip_idx": 0, "status": "provisional"},
            {"timeline_sec": 3.0, "clip_idx": 0, "rollback_relocated": True},
        ]

        changed = strategy.mark_following(provisional, _NoBoolRows([{"timeline_sec": 1.2344}]))

        self.assertTrue(changed)
        self.assertEqual(provisional[0]["status"], "verifying")
        self.assertEqual(provisional[0]["candidate_key"], "0:1.234")
        self.assertTrue(strategy.remove_checked(provisional, _NoBoolRows([{"timeline_sec": 1.2344}])))
        self.assertEqual([round(row["timeline_sec"], 3) for row in provisional], [2.0, 3.0])

    def test_cut_boundary_prescan_strategy_keeps_fast_path_decisions_testable(self):
        strategy = CutBoundaryPrescanStrategy()
        settings = strategy.fast_settings({"scan_cut_follower_stream_start_percent": 80})

        self.assertEqual(settings["cut_boundary_backend_policy"], "fast")
        self.assertEqual(settings["scan_cut_follower_stream_start_percent"], 25)
        self.assertTrue(settings["scan_cut_realtime_preview_enabled"])

    def test_single_pipeline_iteration_plan_normalizes_cut_rows_and_hard_cuts(self):
        plan = build_single_pipeline_iteration_plan(
            target_file="/tmp/a.mp4",
            queue_index=2,
            total_files=5,
            cut_boundary_snapshot={
                "cut_boundaries": _NoBoolRows(
                    [
                        {"timeline_sec": 2.0004},
                        {"time": 1.5},
                        4.25,
                        "ignore",
                    ]
                ),
                "provisional_cut_boundaries": [{"timeline_sec": 3.0}],
            },
        )

        self.assertEqual(plan.queue_index, 2)
        self.assertEqual([round(sec, 3) for sec in plan.hard_cut_boundaries], [1.5, 2.0, 4.25])
        self.assertEqual(len(plan.cut_boundaries), 2)
        self.assertEqual(len(plan.provisional_cut_boundaries), 1)
        self.assertEqual(hard_cut_seconds_from_rows(_NoBoolRows([{"start": 4.4}, 5.0])), [4.4, 5.0])

    def test_pipeline_progress_coordinator_emits_structured_stage_to_both_targets(self):
        emissions = []
        coordinator = PipelineProgressCoordinator(lambda *args: emissions.append(args) or True)

        self.assertTrue(coordinator.emit_stage(1, "처리 중"))
        self.assertEqual(emissions[0], ("_sig_update_queue", 1, "처리 중", "", "", ""))
        self.assertEqual(emissions[1], ("_sig_editor_processing_stage", "처리 중"))

    def test_audio_route_worker_plan_applies_route_cap_once(self):
        with patch(
            "core.audio.audio_runtime_services.runtime_parallel_worker_plan",
            return_value=(6, {"reductions": ["memory_pressure"]}),
        ):
            plan = plan_audio_route_workers(
                settings={"audio_chunk_route_max_workers": 2},
                requested=8,
                workload=10,
            )

        self.assertEqual(plan.max_workers, 2)
        self.assertEqual(plan.scheduler["audio_chunk_route_max_workers"], 2)
        self.assertEqual(plan.reductions_label, "memory_pressure,audio_route_cap")

    def test_project_session_rows_uses_targeted_view_without_full_project_hydration(self):
        class _Session:
            def stt_preview_rows(self):
                return [{"text": "preview"}]

            def project_save_view(self):
                raise AssertionError("targeted row access should not hydrate the full save view")

        editor = SimpleNamespace(editor_session_model=_Session())

        self.assertEqual(editor_session_rows(editor, "stt_preview_segments"), [{"text": "preview"}])


if __name__ == "__main__":
    unittest.main()
