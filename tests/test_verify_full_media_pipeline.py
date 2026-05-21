from tools.verify_full_media_pipeline import summary_metrics, verification_failure_reason


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
