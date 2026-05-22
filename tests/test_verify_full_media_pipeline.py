import cProfile
import json

from tools.verify_full_media_pipeline import (
    _profile_stats_rows,
    _resource_pressure_stage,
    _snapshot_file,
    _snapshot_process_pid,
    summary_metrics,
    verification_failure_reason,
)


def test_summary_metrics_exposes_top_level_quality_and_performance_fields():
    payload = {
        "result": {
            "elapsed_sec": 12.3,
            "raw_segments": 10,
            "final_segments": 11,
            "avg_stt_score": 77.7,
            "readability": {"readability_score": 99.1},
        },
        "self_review_summary": {"overall_score": 66.6},
        "completion_report": {"avg_quality_score": 75.5, "llm_rollback_count": 0},
        "variant_score": {"score": 74.4},
    }

    metrics = summary_metrics(payload)

    assert metrics == {
        "pipeline_elapsed_sec": 12.3,
        "raw_segment_count": 10,
        "final_segment_count": 11,
        "avg_stt_score": 77.7,
        "self_review_overall_score": 66.6,
        "completion_avg_quality": 75.5,
        "llm_rollback_count": 0,
        "output_variant_score": 74.4,
        "readability_score": 99.1,
        "peak_rss_bytes": None,
        "free_memory_ratio": None,
        "free_memory_gb": 0.0,
    }


def test_summary_metrics_exposes_stage_trim_rollup_when_monitor_snapshot_exists():
    payload = {
        "result": {},
        "subtitle_generation_monitor_after": {
            "stage_trim_summary": {
                "requested_count": 4,
                "executed_count": 2,
                "skipped_count": 2,
                "total_elapsed_ms": 18.5,
                "total_failure_count": 1,
                "slowest_stage_key": "subtitle_optimize_done",
                "slowest_stage_elapsed_ms": 11.0,
            }
        },
    }

    metrics = summary_metrics(payload)

    assert metrics["stage_trim_total_elapsed_ms"] == 18.5
    assert metrics["stage_trim_executed_count"] == 2
    assert metrics["stage_trim_slowest_stage"] == "subtitle_optimize_done"


def test_snapshot_file_ignores_stale_monitor_from_other_process(tmp_path):
    src = tmp_path / "latest.json"
    src.write_text(
        json.dumps({
            "pressure_stage": "critical",
            "subtitle_generation_stage": "stt_transcribe_start",
            "resource": {"native_memory": {"pid": 111}},
        }),
        encoding="utf-8",
    )
    ignored = []

    snapshot = _snapshot_file(
        src,
        tmp_path,
        "runtime_monitor_before.json",
        expected_pid=222,
        ignored_snapshots=ignored,
    )

    assert snapshot is None
    assert ignored[0]["reason"] == "pid_mismatch:111!=222"
    assert ignored[0]["source_stage"] == "critical"
    ignored_path = tmp_path / "runtime_monitor_before_ignored.json"
    assert ignored_path.exists()
    ignored_payload = json.loads(ignored_path.read_text(encoding="utf-8"))
    assert ignored_payload["ignored"] is True
    assert ignored_payload["snapshot"]["subtitle_generation_stage"] == "stt_transcribe_start"


def test_snapshot_process_pid_and_resource_pressure_helpers():
    payload = {
        "memory_pressure_stage": "warning",
        "native_memory": {"pid": 333, "pressure_stage": "critical"},
    }

    assert _snapshot_process_pid(payload) == 333
    assert _resource_pressure_stage(payload) == "warning"


def test_verification_failure_reason_rejects_empty_spoken_slice():
    payload = {
        "media": {"duration_target_sec": 60.0},
        "audio_chunk_wavs": 1,
        "vad_segments": 11,
        "result": {"raw_segments": 0, "final_segments": 0, "error": ""},
    }

    assert verification_failure_reason(payload) == "empty_subtitle_output:raw_segments_zero"


def test_verification_failure_reason_allows_empty_trivial_slice_without_vad():
    payload = {
        "media": {"duration_target_sec": 1.0},
        "audio_chunk_wavs": 0,
        "vad_segments": 0,
        "result": {"raw_segments": 0, "final_segments": 0, "error": ""},
    }

    assert verification_failure_reason(payload) == ""


def test_profile_stats_rows_reports_cumulative_hot_functions():
    def _busy_function():
        return sum(range(50))

    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(5):
        _busy_function()
    profiler.disable()

    rows = _profile_stats_rows(profiler, limit=20)

    assert any(row["function"] == "_busy_function" for row in rows)
    assert all("cumulative_time_sec" in row for row in rows)
