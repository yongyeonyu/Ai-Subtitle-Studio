import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.audio.audio_runtime_services import (
    memory_pressure_stage_from_snapshot,
    plan_audio_route_workers,
    stage_owned_resource_policy,
)
from core.pipeline.cut_boundary_strategy import CutBoundaryCandidateStrategy, CutBoundaryPrescanStrategy
from core.pipeline.single_pipeline_plan import (
    PipelineProgressCoordinator,
    SinglePipelineActionSession,
    build_single_pipeline_iteration_plan,
    hard_cut_seconds_from_rows,
    pipeline_overall_progress_percent,
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
        self.assertTrue(settings["scan_cut_parallel_quarter_enabled"])
        self.assertEqual(settings["scan_cut_parallel_quarter_count"], 4)

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

    def test_pipeline_progress_coordinator_emits_chunk_status_and_header(self):
        emissions = []
        coordinator = PipelineProgressCoordinator(lambda *args: emissions.append(args) or True)

        pct = coordinator.emit_chunk_progress(
            queue_index=1,
            total_files=4,
            chunk_index=3,
            chunk_total=6,
        )

        self.assertEqual(pct, 37)
        self.assertEqual(emissions[0], ("_sig_update_status", 3, 6))
        self.assertEqual(emissions[1], ("_sig_update_queue_header", 2, 4, 37, ""))
        self.assertEqual(
            pipeline_overall_progress_percent(
                queue_index=1,
                total_files=4,
                chunk_index=3,
                chunk_total=6,
            ),
            37,
        )

    def test_single_pipeline_action_session_preserves_legacy_state_refs_and_events(self):
        started = []
        stopped = []
        session = SinglePipelineActionSession()
        on_save, on_start, on_prev, on_exit = session.callbacks(
            start_hook=lambda: started.append("start"),
            stop_hook=lambda: stopped.append("stop"),
        )

        on_start()
        self.assertEqual(started, ["start"])
        self.assertEqual(session.state_ref[0], "start")
        self.assertTrue(session.start_event.is_set())

        session.edit_event.clear()
        on_save([{"text": "완료"}])
        self.assertEqual(session.state_ref[0], "next")
        self.assertEqual(session.final_segments, [{"text": "완료"}])
        self.assertTrue(session.edit_event.is_set())

        session.edit_event.clear()
        session.start_event.clear()
        on_prev()
        self.assertEqual(session.state_ref[0], "prev")
        self.assertTrue(session.edit_event.is_set())
        self.assertTrue(session.start_event.is_set())

        session.edit_event.clear()
        session.start_event.clear()
        on_exit([{"text": "종료"}])
        self.assertEqual(stopped, ["stop"])
        self.assertEqual(session.state_ref[0], "exit")
        self.assertEqual(session.final_segments, [{"text": "종료"}])
        self.assertTrue(session.edit_event.is_set())
        self.assertTrue(session.start_event.is_set())

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

    def test_stage_owned_resource_policy_releases_stt_and_llm_only_under_critical(self):
        normal = stage_owned_resource_policy({}, pressure_stage="normal")
        warning = stage_owned_resource_policy({}, pressure_stage="warning")
        critical = stage_owned_resource_policy({}, pressure_stage="critical")

        self.assertTrue(normal.allow_stt_collect_worker_reuse)
        self.assertTrue(normal.keep_llm_resident)
        self.assertEqual(warning.warm_pool_label, "reduced")
        self.assertTrue(warning.keep_stt_worker_warm)
        self.assertFalse(critical.allow_stt_collect_worker_reuse)
        self.assertFalse(critical.keep_stt_worker_warm)
        self.assertFalse(critical.keep_llm_resident)
        self.assertTrue(critical.include_gpu_on_release)

    def test_memory_pressure_stage_from_snapshot_uses_configurable_thresholds(self):
        settings = {
            "runtime_memory_warning_ratio": 0.25,
            "runtime_memory_critical_ratio": 0.10,
            "macos_memory_warning_reserve_gb": 4.0,
            "macos_memory_critical_reserve_gb": 1.0,
        }

        self.assertEqual(
            memory_pressure_stage_from_snapshot({"available_memory_ratio": 0.20}, settings),
            "warning",
        )
        self.assertEqual(
            memory_pressure_stage_from_snapshot({"available_memory_ratio": 0.08}, settings),
            "critical",
        )
        self.assertEqual(
            memory_pressure_stage_from_snapshot({"native_memory": {"pressure_stage": "critical"}}, settings),
            "critical",
        )

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
