from core.pipeline.subtitle_parallel_manager import (
    STAGE_DAG_SCHEMA,
    build_subtitle_parallel_iteration_plan,
    build_subtitle_stage_dag,
    hard_cut_seconds_from_rows,
    pipeline_overall_progress_percent,
)


class _NoBoolRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def __bool__(self):
        raise AssertionError("rows should not be truth-tested")

    def __iter__(self):
        return iter(self._rows)


def test_parallel_iteration_plan_normalizes_cut_rows_without_truth_testing_iterables():
    plan = build_subtitle_parallel_iteration_plan(
        target_file="/tmp/a.mp4",
        queue_index="2",
        total_files="5",
        cut_boundary_snapshot={
            "cut_boundaries": _NoBoolRows([{"timeline_sec": 2.0004}, {"time": 1.5}, 4.25, "ignore"]),
            "provisional_cut_boundaries": _NoBoolRows([{"start": 3.0}]),
        },
    )

    assert plan.queue_index == 2
    assert plan.total_files == 5
    assert [round(sec, 3) for sec in plan.hard_cut_boundaries] == [1.5, 2.0, 4.25]
    assert len(plan.cut_boundaries) == 2
    assert len(plan.provisional_cut_boundaries) == 1
    assert plan.stage_schema == STAGE_DAG_SCHEMA
    assert plan.stage_dag[0].stage == "audio_extract"


def test_hard_cut_seconds_from_rows_sorts_unique_positive_seconds():
    rows = _NoBoolRows([{"start": 4.4}, {"timeline_sec": 4.4001}, 5.0, 0.0, "ignore"])

    assert hard_cut_seconds_from_rows(rows) == [4.4, 5.0]


def test_pipeline_overall_progress_percent_sanitizes_numeric_inputs():
    assert pipeline_overall_progress_percent(
        queue_index="1",
        total_files="4",
        chunk_index="3",
        chunk_total="6",
    ) == 37


def test_stage_dag_can_filter_to_requested_stage_contracts():
    stages = build_subtitle_stage_dag(["audio_extract", "stt", "editor_feed"])

    assert [node.stage for node in stages] == ["audio_extract", "stt", "editor_feed"]
    assert stages[1].depends_on == ("audio_extract", "cut_boundary")
    assert stages[-1].lane == "ui"
