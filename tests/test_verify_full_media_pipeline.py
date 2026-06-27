import cProfile
import json

from tools.verify_full_media_pipeline import (
    _build_repeat_summary,
    _cut_boundary_profile_stage,
    _generation_profile_stage,
    _profile_stats_rows,
    _resource_pressure_stage,
    _snapshot_file,
    _snapshot_process_pid,
    _summarize_cut_boundary_profile,
    _summarize_generation_profile,
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
        "quality": {"quality_score": 88.8, "text_score": 91.0, "timing_mae_sec": 0.1234, "cer": 0.03},
        "native_segments_summary": {
            "invalid_duration_count": 0,
            "non_monotonic_count": 0,
            "overlap_count": 0,
            "max_overlap": 0.0,
            "stable_for_save_reopen": True,
        },
        "native_global_canvas_summary": {"max_active_segments": 1, "stable_for_global_canvas": True},
        "native_stt_segments_summary": {
            "stt1_selected_count": 4,
            "stt2_selected_count": 6,
            "recheck_applied_count": 6,
            "word_precision_count": 2,
            "stt2_coverage_ratio": 0.55,
            "selective_recheck_active": True,
        },
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
        "quality_score": 88.8,
        "text_score": 91.0,
        "timing_mae_sec": 0.1234,
        "cer": 0.03,
        "segment_count_delta": None,
        "self_review_overall_score": 66.6,
        "completion_avg_quality": 75.5,
        "llm_rollback_count": 0,
        "output_variant_score": 74.4,
        "readability_score": 99.1,
        "final_invalid_duration_count": 0,
        "final_non_monotonic_count": 0,
        "final_overlap_count": 0,
        "final_stable_for_save_reopen": True,
        "final_max_overlap": 0.0,
        "global_canvas_max_active_segments": 1,
        "global_canvas_stable": True,
        "stt1_selected_count": 4,
        "stt2_selected_count": 6,
        "stt_recheck_applied_count": 6,
        "word_precision_count": 2,
        "stt2_coverage_ratio": 0.55,
        "selective_recheck_active": True,
        "llm_gate_skipped_segments": None,
        "llm_verifier_rollbacks": None,
        "lora_applied_segments": None,
        "deep_policy_segments": None,
        "subtitle_memory_pressure_stage": None,
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


def test_summary_metrics_exposes_stage_wall_clock_rollup_when_variant_reports_spans():
    payload = {
        "result": {
            "stage_wall_clock_summary": {
                "span_count": 6,
                "top_stage": "stt_primary_transcribe",
                "top_elapsed_sec": 42.0,
                "stage_summaries": {
                    "stt_primary_transcribe": {"total_elapsed_sec": 42.0, "max_elapsed_sec": 42.0},
                    "stt_primary_collect_transcribe": {
                        "total_elapsed_sec": 41.5,
                        "max_elapsed_sec": 41.5,
                        "total_setup_elapsed_sec": 0.5,
                        "total_collect_elapsed_sec": 41.0,
                    },
                    "stt_collect_whisperkit_fallback": {
                        "count": 2,
                        "total_elapsed_sec": 6.5,
                        "max_elapsed_sec": 4.0,
                    },
                    "stt2_selective_recheck": {
                        "total_elapsed_sec": 9.5,
                        "max_elapsed_sec": 9.5,
                        "total_prepare_elapsed_sec": 0.25,
                        "total_collect_elapsed_sec": 8.75,
                        "total_annotate_elapsed_sec": 0.5,
                        "total_batch_elapsed_sec": 9.6,
                    },
                    "word_precision": {
                        "total_elapsed_sec": 3.25,
                        "max_elapsed_sec": 3.25,
                        "total_prepare_elapsed_sec": 0.75,
                        "total_collect_elapsed_sec": 2.0,
                        "total_annotate_elapsed_sec": 0.25,
                        "total_batch_elapsed_sec": 3.1,
                    },
                    "vad_stt_consensus": {"total_elapsed_sec": 0.2, "max_elapsed_sec": 0.2},
                    "subtitle_postprocess": {"total_elapsed_sec": 7.0, "max_elapsed_sec": 5.0},
                    "subtitle_postprocess_detail": {
                        "count": 2,
                        "total_elapsed_sec": 6.25,
                        "max_elapsed_sec": 5.5,
                        "total_detail_elapsed_sec": 6.25,
                    },
                },
                "spans": [
                    {
                        "stage": "stt_primary_transcribe",
                        "elapsed_sec": 42.0,
                        "backend": "whisperkit_persistent",
                        "resolved_model": "large-v3-v20240930_turbo_632MB",
                        "chunk_count": 2,
                        "submitted_chunk_count": 2,
                        "chunk_audio_sec": 188.0,
                        "word_timestamps": False,
                        "worker_silence_timeout_sec": 150.0,
                        "whisperkit_worker_count": 2,
                        "submission_reordered": False,
                        "received_chunks": 2,
                        "processed_chunks": 2,
                        "emitted_segment_count": 55,
                        "setup_elapsed_sec": 0.5,
                        "collect_elapsed_sec": 41.0,
                        "worker_reuse_enabled": True,
                        "worker_cache_hit": True,
                        "collect_cache_enabled": True,
                        "collect_cache_hit": False,
                        "collect_cache_write": True,
                        "collect_provider_called": True,
                    },
                    {
                        "stage": "stt_primary_collect_transcribe",
                        "elapsed_sec": 41.5,
                        "label": "STT1",
                        "backend": "whisperkit_persistent",
                        "resolved_model": "large-v3-v20240930_turbo_632MB",
                        "chunk_count": 2,
                        "submitted_chunk_count": 2,
                        "chunk_audio_sec": 188.0,
                        "word_timestamps": False,
                        "worker_silence_timeout_sec": 150.0,
                        "whisperkit_worker_count": 2,
                        "submission_reordered": False,
                        "received_chunks": 2,
                        "processed_chunks": 2,
                        "emitted_segment_count": 55,
                        "setup_elapsed_sec": 0.5,
                        "collect_elapsed_sec": 41.0,
                        "collect_cache_enabled": True,
                        "collect_cache_hit": False,
                        "collect_cache_write": True,
                        "collect_provider_called": True,
                    },
                    {
                        "stage": "stt2_selective_recheck",
                        "elapsed_sec": 9.5,
                        "raw_range_count": 3,
                        "range_count": 2,
                        "prepared_clip_count": 2,
                        "collected_segment_count": 8,
                        "applied_count": 1,
                        "applied_segment_count": 5,
                        "range_audio_sec": 24.0,
                        "max_range_duration_sec": 18.0,
                        "prepared_audio_sec": 25.2,
                        "max_prepared_clip_duration_sec": 18.6,
                        "missing_voice_range_count": 1,
                        "route_hint_range_count": 0,
                        "low_score_range_count": 1,
                        "empty_text_range_count": 1,
                        "collect_cache_enabled": True,
                        "collect_cache_hit": False,
                        "collect_cache_write": True,
                        "collect_provider_called": True,
                    },
                    {
                        "stage": "word_precision",
                        "elapsed_sec": 3.25,
                        "range_count": 4,
                        "prepared_clip_count": 4,
                        "collected_segment_count": 4,
                        "applied_count": 2,
                        "range_audio_sec": 7.5,
                        "max_range_duration_sec": 2.5,
                        "prepared_audio_sec": 10.1,
                        "max_prepared_clip_duration_sec": 3.4,
                        "selected_range_count": 1,
                        "precision_review_range_count": 2,
                        "needs_review_range_count": 1,
                        "red_range_count": 1,
                        "yellow_range_count": 2,
                        "risk_range_count": 3,
                        "missing_word_range_count": 4,
                        "collect_cache_enabled": True,
                        "collect_cache_hit": True,
                        "collect_cache_write": False,
                        "collect_provider_called": False,
                    },
                    {
                        "stage": "subtitle_postprocess",
                        "elapsed_sec": 7.0,
                        "detail_stage_count": 2,
                        "detail_top_stage": "proofread_dictionary_llm",
                        "detail_top_elapsed_sec": 5.5,
                    },
                    {
                        "stage": "subtitle_postprocess_detail",
                        "elapsed_sec": 5.5,
                        "detail_stage": "high_context_boundary",
                        "high_context_boundary_enabled": True,
                        "high_context_boundary_reason": "completed",
                        "high_context_boundary_candidate_pair_count": 4,
                        "high_context_boundary_skipped_pair_count": 12,
                        "high_context_boundary_llm_call_count": 4,
                        "high_context_boundary_failed_call_count": 0,
                        "high_context_boundary_changed_pair_count": 1,
                        "high_context_boundary_max_pairs": 24,
                        "high_context_boundary_keep_decision_count": 2,
                        "high_context_boundary_move_boundary_decision_count": 1,
                        "high_context_boundary_merge_decision_count": 1,
                        "high_context_boundary_invalid_decision_count": 0,
                        "high_context_boundary_correction_request_count": 2,
                        "high_context_boundary_applied_correction_count": 1,
                        "high_context_boundary_keep_cache_enabled": True,
                        "high_context_boundary_keep_cache_hit_count": 1,
                        "high_context_boundary_keep_cache_miss_count": 3,
                        "high_context_boundary_keep_cache_write_count": 2,
                        "high_context_boundary_elapsed_sec": 5.45,
                    }
                ],
            }
        },
    }

    metrics = summary_metrics(payload)

    assert metrics["stage_wall_clock_span_count"] == 6
    assert metrics["stage_wall_clock_top_stage"] == "stt_primary_transcribe"
    assert metrics["stage_wall_clock_top_elapsed_sec"] == 42.0
    assert metrics["stage_wall_clock_stt_primary_transcribe_total_elapsed_sec"] == 42.0
    assert metrics["stage_wall_clock_stt_primary_transcribe_backend"] == "whisperkit_persistent"
    assert metrics["stage_wall_clock_stt_primary_transcribe_chunk_count"] == 2
    assert metrics["stage_wall_clock_stt_primary_transcribe_collect_elapsed_sec"] == 41.0
    assert metrics["stage_wall_clock_stt_primary_transcribe_worker_cache_hit"] is True
    assert metrics["stage_wall_clock_stt_primary_transcribe_collect_cache_enabled"] is True
    assert metrics["stage_wall_clock_stt_primary_transcribe_collect_cache_write"] is True
    assert metrics["stage_wall_clock_stt_primary_collect_transcribe_total_elapsed_sec"] == 41.5
    assert metrics["stage_wall_clock_stt_primary_collect_transcribe_setup_elapsed_sec"] == 0.5
    assert metrics["stage_wall_clock_stt_primary_collect_transcribe_collect_elapsed_sec"] == 41.0
    assert metrics["stage_wall_clock_stt_primary_collect_transcribe_whisperkit_worker_count"] == 2
    assert metrics["stage_wall_clock_stt_primary_collect_transcribe_emitted_segment_count"] == 55
    assert metrics["stage_wall_clock_stt_primary_collect_transcribe_collect_cache_write"] is True
    assert metrics["stage_wall_clock_stt_collect_whisperkit_fallback_count"] == 2
    assert metrics["stage_wall_clock_stt_collect_whisperkit_fallback_total_elapsed_sec"] == 6.5
    assert metrics["stage_wall_clock_stt_collect_whisperkit_fallback_max_elapsed_sec"] == 4.0
    assert metrics["stage_wall_clock_stt2_selective_recheck_total_elapsed_sec"] == 9.5
    assert metrics["stage_wall_clock_stt2_selective_recheck_prepare_elapsed_sec"] == 0.25
    assert metrics["stage_wall_clock_stt2_selective_recheck_collect_elapsed_sec"] == 8.75
    assert metrics["stage_wall_clock_stt2_selective_recheck_annotate_elapsed_sec"] == 0.5
    assert metrics["stage_wall_clock_stt2_selective_recheck_batch_elapsed_sec"] == 9.6
    assert metrics["stage_wall_clock_stt2_selective_recheck_raw_range_count"] == 3
    assert metrics["stage_wall_clock_stt2_selective_recheck_range_count"] == 2
    assert metrics["stage_wall_clock_stt2_selective_recheck_range_audio_sec"] == 24.0
    assert metrics["stage_wall_clock_stt2_selective_recheck_max_range_duration_sec"] == 18.0
    assert metrics["stage_wall_clock_stt2_selective_recheck_prepared_audio_sec"] == 25.2
    assert metrics["stage_wall_clock_stt2_selective_recheck_max_prepared_clip_duration_sec"] == 18.6
    assert metrics["stage_wall_clock_stt2_selective_recheck_applied_segment_count"] == 5
    assert metrics["stage_wall_clock_stt2_selective_recheck_missing_voice_range_count"] == 1
    assert metrics["stage_wall_clock_stt2_selective_recheck_route_hint_range_count"] == 0
    assert metrics["stage_wall_clock_stt2_selective_recheck_low_score_range_count"] == 1
    assert metrics["stage_wall_clock_stt2_selective_recheck_empty_text_range_count"] == 1
    assert metrics["stage_wall_clock_stt2_selective_recheck_collect_cache_enabled"] is True
    assert metrics["stage_wall_clock_stt2_selective_recheck_collect_cache_hit"] is False
    assert metrics["stage_wall_clock_stt2_selective_recheck_collect_cache_write"] is True
    assert metrics["stage_wall_clock_stt2_selective_recheck_collect_provider_called"] is True
    assert metrics["stage_wall_clock_word_precision_total_elapsed_sec"] == 3.25
    assert metrics["stage_wall_clock_word_precision_prepare_elapsed_sec"] == 0.75
    assert metrics["stage_wall_clock_word_precision_collect_elapsed_sec"] == 2.0
    assert metrics["stage_wall_clock_word_precision_annotate_elapsed_sec"] == 0.25
    assert metrics["stage_wall_clock_word_precision_batch_elapsed_sec"] == 3.1
    assert metrics["stage_wall_clock_word_precision_range_count"] == 4
    assert metrics["stage_wall_clock_word_precision_range_audio_sec"] == 7.5
    assert metrics["stage_wall_clock_word_precision_max_range_duration_sec"] == 2.5
    assert metrics["stage_wall_clock_word_precision_prepared_audio_sec"] == 10.1
    assert metrics["stage_wall_clock_word_precision_max_prepared_clip_duration_sec"] == 3.4
    assert metrics["stage_wall_clock_word_precision_selected_range_count"] == 1
    assert metrics["stage_wall_clock_word_precision_precision_review_range_count"] == 2
    assert metrics["stage_wall_clock_word_precision_needs_review_range_count"] == 1
    assert metrics["stage_wall_clock_word_precision_red_range_count"] == 1
    assert metrics["stage_wall_clock_word_precision_yellow_range_count"] == 2
    assert metrics["stage_wall_clock_word_precision_risk_range_count"] == 3
    assert metrics["stage_wall_clock_word_precision_missing_word_range_count"] == 4
    assert metrics["stage_wall_clock_word_precision_collect_cache_enabled"] is True
    assert metrics["stage_wall_clock_word_precision_collect_cache_hit"] is True
    assert metrics["stage_wall_clock_word_precision_collect_cache_write"] is False
    assert metrics["stage_wall_clock_word_precision_collect_provider_called"] is False
    assert metrics["stage_wall_clock_vad_stt_consensus_total_elapsed_sec"] == 0.2
    assert metrics["stage_wall_clock_subtitle_postprocess_total_elapsed_sec"] == 7.0
    assert metrics["stage_wall_clock_subtitle_postprocess_detail_total_elapsed_sec"] == 6.25
    assert metrics["stage_wall_clock_subtitle_postprocess_detail_elapsed_sec"] == 6.25
    assert metrics["stage_wall_clock_subtitle_postprocess_detail_top_stage"] == "proofread_dictionary_llm"
    assert metrics["stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec"] == 5.5
    assert metrics["stage_wall_clock_subtitle_postprocess_detail_stage_count"] == 2
    assert metrics["high_context_boundary_enabled"] is True
    assert metrics["high_context_boundary_reason"] == "completed"
    assert metrics["high_context_boundary_candidate_pair_count"] == 4
    assert metrics["high_context_boundary_skipped_pair_count"] == 12
    assert metrics["high_context_boundary_llm_call_count"] == 4
    assert metrics["high_context_boundary_failed_call_count"] == 0
    assert metrics["high_context_boundary_changed_pair_count"] == 1
    assert metrics["high_context_boundary_max_pairs"] == 24
    assert metrics["high_context_boundary_keep_decision_count"] == 2
    assert metrics["high_context_boundary_move_boundary_decision_count"] == 1
    assert metrics["high_context_boundary_merge_decision_count"] == 1
    assert metrics["high_context_boundary_invalid_decision_count"] == 0
    assert metrics["high_context_boundary_correction_request_count"] == 2
    assert metrics["high_context_boundary_applied_correction_count"] == 1
    assert metrics["high_context_boundary_keep_cache_enabled"] is True
    assert metrics["high_context_boundary_keep_cache_hit_count"] == 1
    assert metrics["high_context_boundary_keep_cache_miss_count"] == 3
    assert metrics["high_context_boundary_keep_cache_write_count"] == 2
    assert metrics["high_context_boundary_elapsed_sec"] == 5.45


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


def test_verification_failure_reason_rejects_empty_nontrivial_slice_without_audio_markers():
    payload = {
        "media": {"duration_target_sec": 180.0},
        "audio_chunk_wavs": 0,
        "vad_segments": 0,
        "result": {"raw_segments": 0, "final_segments": 0, "error": ""},
    }

    assert verification_failure_reason(payload) == "empty_subtitle_output:raw_segments_zero"


def test_verification_failure_reason_rejects_final_overlap_even_when_segments_exist():
    payload = {
        "media": {"duration_target_sec": 60.0},
        "result": {
            "raw_segments": 3,
            "final_segments": 3,
            "native_segments_summary": {
                "invalid_duration_count": 0,
                "non_monotonic_count": 0,
                "overlap_count": 1,
                "stable_for_save_reopen": False,
            },
        },
    }

    assert verification_failure_reason(payload) == "final_stability:overlap_count=1"


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


def test_cut_boundary_profile_summary_groups_owner_functions_by_stage():
    rows = [
        {
            "file": "/repo/core/cut_boundary_auto_scan.py",
            "line": 120,
            "function": "scan_media_cut_boundary_provisionals",
            "primitive_calls": 1,
            "total_calls": 1,
            "total_time_sec": 0.4,
            "cumulative_time_sec": 2.2,
        },
        {
            "file": "/repo/core/cut_boundary_backend_router.py",
            "line": 40,
            "function": "resolve_pioneer_source_fps_pipe_scout",
            "primitive_calls": 1,
            "total_calls": 1,
            "total_time_sec": 0.1,
            "cumulative_time_sec": 3.3,
        },
        {
            "file": "/repo/core/cut_boundary_ffmpeg_scene.py",
            "line": 80,
            "function": "detect_ffmpeg_scene_boundaries",
            "primitive_calls": 1,
            "total_calls": 1,
            "total_time_sec": 0.2,
            "cumulative_time_sec": 1.1,
        },
        {
            "file": "/repo/core/audio/media_processor.py",
            "line": 10,
            "function": "extract_audio",
            "primitive_calls": 1,
            "total_calls": 1,
            "total_time_sec": 9.0,
            "cumulative_time_sec": 9.0,
        },
    ]

    summary = _summarize_cut_boundary_profile(rows)

    assert summary["matching_row_count"] == 3
    assert summary["top_stage"] == "source_fps_pipe_scout"
    assert summary["stage_summaries"]["pioneer_scout"]["row_count"] == 1
    assert summary["stage_summaries"]["source_fps_pipe_scout"]["max_cumulative_time_sec"] == 3.3
    assert summary["stage_summaries"]["ffmpeg_scene_prepass"]["top_rows"][0]["function"] == "detect_ffmpeg_scene_boundaries"
    assert _cut_boundary_profile_stage({"file": "/repo/core/roughcut/pipeline.py", "function": "build_ranges"}) == "roughcut_boundary"


def test_summary_metrics_exposes_cut_boundary_profile_rollup():
    payload = {
        "result": {"elapsed_sec": 1.0},
        "function_profile": {
            "cut_boundary_summary": {
                "matching_row_count": 4,
                "top_stage": "follower_verification",
                "top_cumulative_time_sec": 7.25,
            }
        },
    }

    metrics = summary_metrics(payload)

    assert metrics["cut_boundary_profile_matching_rows"] == 4
    assert metrics["cut_boundary_profile_top_stage"] == "follower_verification"
    assert metrics["cut_boundary_profile_top_cumulative_time_sec"] == 7.25


def test_generation_profile_summary_groups_stt2_word_llm_and_cleanup_stages():
    rows = [
        {
            "file": "/repo/core/audio/media_processor_transcribe.py",
            "line": 10,
            "function": "_collect_transcribe_result",
            "primitive_calls": 1,
            "total_calls": 1,
            "total_time_sec": 0.1,
            "cumulative_time_sec": 44.0,
        },
        {
            "file": "/repo/core/audio/stt_recheck_service.py",
            "line": 20,
            "function": "prepare_and_collect_recheck_segments",
            "primitive_calls": 1,
            "total_calls": 1,
            "total_time_sec": 0.1,
            "cumulative_time_sec": 28.0,
        },
        {
            "file": "/repo/core/audio/media_processor_transcribe_recheck.py",
            "line": 30,
            "function": "_recheck_word_timestamps_for_precision",
            "primitive_calls": 1,
            "total_calls": 1,
            "total_time_sec": 0.1,
            "cumulative_time_sec": 13.0,
        },
        {
            "file": "/repo/core/llm/ollama_provider.py",
            "line": 40,
            "function": "_ollama_client_generate",
            "primitive_calls": 1,
            "total_calls": 1,
            "total_time_sec": 0.1,
            "cumulative_time_sec": 17.0,
        },
        {
            "file": "/repo/core/audio/runtime_cleanup.py",
            "line": 50,
            "function": "clear_audio_model_memory_caches",
            "primitive_calls": 1,
            "total_calls": 1,
            "total_time_sec": 0.1,
            "cumulative_time_sec": 1.0,
        },
    ]

    summary = _summarize_generation_profile(rows)

    assert summary["matching_row_count"] == 5
    assert summary["top_stage"] == "stt_primary_transcribe"
    assert summary["stage_summaries"]["stt2_selective_recheck"]["max_cumulative_time_sec"] == 28.0
    assert summary["stage_summaries"]["word_precision"]["top_rows"][0]["function"] == "_recheck_word_timestamps_for_precision"
    assert summary["stage_summaries"]["llm_refinement"]["row_count"] == 1
    assert _generation_profile_stage({"file": "/repo/core/subtitle_quality/quality_pipeline.py", "function": "run"}) == "subtitle_postprocess"


def test_summary_metrics_exposes_generation_profile_rollup():
    payload = {
        "result": {"elapsed_sec": 1.0},
        "function_profile": {
            "generation_summary": {
                "matching_row_count": 8,
                "top_stage": "stt2_selective_recheck",
                "top_cumulative_time_sec": 28.0,
                "stage_summaries": {
                    "stt2_selective_recheck": {"max_cumulative_time_sec": 28.0},
                    "word_precision": {"max_cumulative_time_sec": 13.0},
                },
            }
        },
    }

    metrics = summary_metrics(payload)

    assert metrics["generation_profile_matching_rows"] == 8
    assert metrics["generation_profile_top_stage"] == "stt2_selective_recheck"
    assert metrics["generation_profile_top_cumulative_time_sec"] == 28.0
    assert metrics["generation_profile_word_precision_max_cumulative_time_sec"] == 13.0


def test_repeat_summary_rolls_up_accuracy_preserving_stt2_metrics():
    runs = [
        {
            "summary_metrics": {
                "pipeline_elapsed_sec": 10.0,
                "raw_segment_count": 5,
                "final_segment_count": 4,
                "quality_score": 81.2,
                "timing_mae_sec": 0.5,
                "final_invalid_duration_count": 0,
                "final_non_monotonic_count": 0,
                "final_overlap_count": 0,
                "final_stable_for_save_reopen": True,
                "global_canvas_max_active_segments": 1,
                "stt1_selected_count": 2,
                "stt2_selected_count": 3,
                "stt_recheck_applied_count": 3,
                "word_precision_count": 1,
                "stt2_coverage_ratio": 0.6,
                "llm_gate_skipped_segments": 0,
                "stage_trim_total_elapsed_ms": 20.0,
                "stage_trim_executed_count": 1,
                "subtitle_memory_pressure_stage": "normal",
                "stage_wall_clock_top_stage": "stt_primary_transcribe",
                "stage_wall_clock_top_elapsed_sec": 45.0,
                "stage_wall_clock_stt_primary_transcribe_total_elapsed_sec": 45.0,
                "stage_wall_clock_stt_collect_whisperkit_fallback_count": 1,
                "stage_wall_clock_stt_collect_whisperkit_fallback_total_elapsed_sec": 2.0,
                "stage_wall_clock_stt_collect_whisperkit_fallback_max_elapsed_sec": 2.0,
                "stage_wall_clock_stt2_selective_recheck_total_elapsed_sec": 12.0,
                "stage_wall_clock_stt2_selective_recheck_collect_elapsed_sec": 10.5,
                "stage_wall_clock_stt2_selective_recheck_range_audio_sec": 30.0,
                "stage_wall_clock_stt2_selective_recheck_max_range_duration_sec": 20.0,
                "stage_wall_clock_stt2_selective_recheck_prepared_audio_sec": 31.2,
                "stage_wall_clock_stt2_selective_recheck_max_prepared_clip_duration_sec": 20.6,
                "stage_wall_clock_stt2_selective_recheck_applied_segment_count": 5,
                "stage_wall_clock_stt2_selective_recheck_missing_voice_range_count": 1,
                "stage_wall_clock_stt2_selective_recheck_route_hint_range_count": 0,
                "stage_wall_clock_stt2_selective_recheck_low_score_range_count": 1,
                "stage_wall_clock_stt2_selective_recheck_empty_text_range_count": 1,
                "stage_wall_clock_word_precision_total_elapsed_sec": 4.0,
                "stage_wall_clock_word_precision_collect_elapsed_sec": 3.4,
                "stage_wall_clock_word_precision_range_audio_sec": 8.0,
                "stage_wall_clock_word_precision_max_range_duration_sec": 2.5,
                "stage_wall_clock_word_precision_prepared_audio_sec": 10.4,
                "stage_wall_clock_word_precision_max_prepared_clip_duration_sec": 3.2,
                "stage_wall_clock_word_precision_selected_range_count": 1,
                "stage_wall_clock_word_precision_precision_review_range_count": 2,
                "stage_wall_clock_word_precision_needs_review_range_count": 1,
                "stage_wall_clock_word_precision_red_range_count": 1,
                "stage_wall_clock_word_precision_yellow_range_count": 2,
                "stage_wall_clock_word_precision_risk_range_count": 3,
                "stage_wall_clock_word_precision_missing_word_range_count": 4,
                "stage_wall_clock_vad_stt_consensus_total_elapsed_sec": 0.3,
                "stage_wall_clock_subtitle_postprocess_total_elapsed_sec": 8.0,
                "stage_wall_clock_subtitle_postprocess_detail_top_stage": "proofread_dictionary_llm",
                "stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec": 6.0,
                "stage_wall_clock_subtitle_postprocess_detail_stage_count": 4,
                "stage_wall_clock_subtitle_postprocess_detail_total_elapsed_sec": 7.0,
                "high_context_boundary_enabled": True,
                "high_context_boundary_reason": "completed",
                "high_context_boundary_candidate_pair_count": 3,
                "high_context_boundary_skipped_pair_count": 10,
                "high_context_boundary_llm_call_count": 3,
                "high_context_boundary_failed_call_count": 0,
                "high_context_boundary_changed_pair_count": 0,
                "high_context_boundary_max_pairs": 24,
                "high_context_boundary_keep_decision_count": 3,
                "high_context_boundary_move_boundary_decision_count": 0,
                "high_context_boundary_merge_decision_count": 0,
                "high_context_boundary_invalid_decision_count": 0,
                "high_context_boundary_correction_request_count": 1,
                "high_context_boundary_applied_correction_count": 0,
                "high_context_boundary_keep_cache_enabled": True,
                "high_context_boundary_keep_cache_hit_count": 0,
                "high_context_boundary_keep_cache_miss_count": 3,
                "high_context_boundary_keep_cache_write_count": 3,
                "high_context_boundary_elapsed_sec": 4.5,
                "generation_profile_top_stage": "stt_primary_transcribe",
                "generation_profile_top_cumulative_time_sec": 40.0,
            },
            "result_path": "/tmp/run_01.json",
        },
        {
            "summary_metrics": {
                "pipeline_elapsed_sec": 12.0,
                "raw_segment_count": 5,
                "final_segment_count": 4,
                "quality_score": 80.8,
                "timing_mae_sec": 0.7,
                "final_invalid_duration_count": 0,
                "final_non_monotonic_count": 0,
                "final_overlap_count": 0,
                "final_stable_for_save_reopen": True,
                "global_canvas_max_active_segments": 1,
                "stt1_selected_count": 2,
                "stt2_selected_count": 3,
                "stt_recheck_applied_count": 3,
                "word_precision_count": 1,
                "stt2_coverage_ratio": 0.6,
                "llm_gate_skipped_segments": 0,
                "stage_trim_total_elapsed_ms": 30.0,
                "stage_trim_executed_count": 1,
                "subtitle_memory_pressure_stage": "warning",
                "stage_wall_clock_top_stage": "stt_primary_transcribe",
                "stage_wall_clock_top_elapsed_sec": 43.0,
                "stage_wall_clock_stt_primary_transcribe_total_elapsed_sec": 43.0,
                "stage_wall_clock_stt_collect_whisperkit_fallback_count": 2,
                "stage_wall_clock_stt_collect_whisperkit_fallback_total_elapsed_sec": 5.0,
                "stage_wall_clock_stt_collect_whisperkit_fallback_max_elapsed_sec": 3.0,
                "stage_wall_clock_stt2_selective_recheck_total_elapsed_sec": 10.0,
                "stage_wall_clock_stt2_selective_recheck_collect_elapsed_sec": 9.0,
                "stage_wall_clock_stt2_selective_recheck_range_audio_sec": 24.0,
                "stage_wall_clock_stt2_selective_recheck_max_range_duration_sec": 18.0,
                "stage_wall_clock_stt2_selective_recheck_prepared_audio_sec": 25.1,
                "stage_wall_clock_stt2_selective_recheck_max_prepared_clip_duration_sec": 18.5,
                "stage_wall_clock_stt2_selective_recheck_applied_segment_count": 4,
                "stage_wall_clock_stt2_selective_recheck_missing_voice_range_count": 2,
                "stage_wall_clock_stt2_selective_recheck_route_hint_range_count": 1,
                "stage_wall_clock_stt2_selective_recheck_low_score_range_count": 0,
                "stage_wall_clock_stt2_selective_recheck_empty_text_range_count": 2,
                "stage_wall_clock_word_precision_total_elapsed_sec": 3.5,
                "stage_wall_clock_word_precision_collect_elapsed_sec": 3.0,
                "stage_wall_clock_word_precision_range_audio_sec": 7.0,
                "stage_wall_clock_word_precision_max_range_duration_sec": 2.0,
                "stage_wall_clock_word_precision_prepared_audio_sec": 9.0,
                "stage_wall_clock_word_precision_max_prepared_clip_duration_sec": 3.0,
                "stage_wall_clock_word_precision_selected_range_count": 0,
                "stage_wall_clock_word_precision_precision_review_range_count": 1,
                "stage_wall_clock_word_precision_needs_review_range_count": 1,
                "stage_wall_clock_word_precision_red_range_count": 0,
                "stage_wall_clock_word_precision_yellow_range_count": 1,
                "stage_wall_clock_word_precision_risk_range_count": 2,
                "stage_wall_clock_word_precision_missing_word_range_count": 3,
                "stage_wall_clock_vad_stt_consensus_total_elapsed_sec": 0.2,
                "stage_wall_clock_subtitle_postprocess_total_elapsed_sec": 7.5,
                "stage_wall_clock_subtitle_postprocess_detail_top_stage": "high_context_boundary",
                "stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec": 5.0,
                "stage_wall_clock_subtitle_postprocess_detail_stage_count": 4,
                "stage_wall_clock_subtitle_postprocess_detail_total_elapsed_sec": 6.5,
                "high_context_boundary_enabled": True,
                "high_context_boundary_reason": "completed",
                "high_context_boundary_candidate_pair_count": 4,
                "high_context_boundary_skipped_pair_count": 11,
                "high_context_boundary_llm_call_count": 4,
                "high_context_boundary_failed_call_count": 0,
                "high_context_boundary_changed_pair_count": 1,
                "high_context_boundary_max_pairs": 24,
                "high_context_boundary_keep_decision_count": 2,
                "high_context_boundary_move_boundary_decision_count": 1,
                "high_context_boundary_merge_decision_count": 0,
                "high_context_boundary_invalid_decision_count": 1,
                "high_context_boundary_correction_request_count": 2,
                "high_context_boundary_applied_correction_count": 1,
                "high_context_boundary_keep_cache_enabled": True,
                "high_context_boundary_keep_cache_hit_count": 2,
                "high_context_boundary_keep_cache_miss_count": 2,
                "high_context_boundary_keep_cache_write_count": 1,
                "high_context_boundary_elapsed_sec": 5.25,
                "generation_profile_top_stage": "stt2_selective_recheck",
                "generation_profile_top_cumulative_time_sec": 28.0,
            },
            "result_path": "/tmp/run_02.json",
        },
    ]

    summary = _build_repeat_summary(runs)

    assert summary["pipeline_elapsed_sec"]["avg"] == 11.0
    assert summary["quality_score"]["list"] == [81.2, 80.8]
    assert summary["timing_mae_sec"]["avg"] == 0.6
    assert summary["final_overlap_count"]["max"] == 0
    assert summary["final_stable_for_save_reopen"]["all"] is True
    assert summary["stt2_selected_count"]["avg"] == 3.0
    assert summary["word_precision_count"]["list"] == [1, 1]
    assert summary["subtitle_memory_pressure_stage"]["latest"] == "warning"
    assert summary["stage_wall_clock_top_stage"]["latest"] == "stt_primary_transcribe"
    assert summary["stage_wall_clock_top_elapsed_sec"]["avg"] == 44.0
    assert summary["stage_wall_clock_stt_primary_transcribe_total_elapsed_sec"]["list"] == [45.0, 43.0]
    assert summary["stage_wall_clock_stt_collect_whisperkit_fallback_count"]["list"] == [1, 2]
    assert summary["stage_wall_clock_stt_collect_whisperkit_fallback_total_elapsed_sec"]["avg"] == 3.5
    assert summary["stage_wall_clock_stt_collect_whisperkit_fallback_max_elapsed_sec"]["max"] == 3.0
    assert summary["stage_wall_clock_stt2_selective_recheck_total_elapsed_sec"]["avg"] == 11.0
    assert summary["stage_wall_clock_stt2_selective_recheck_collect_elapsed_sec"]["avg"] == 9.75
    assert summary["stage_wall_clock_stt2_selective_recheck_range_audio_sec"]["avg"] == 27.0
    assert summary["stage_wall_clock_stt2_selective_recheck_max_range_duration_sec"]["max"] == 20.0
    assert summary["stage_wall_clock_stt2_selective_recheck_prepared_audio_sec"]["list"] == [31.2, 25.1]
    assert summary["stage_wall_clock_stt2_selective_recheck_max_prepared_clip_duration_sec"]["max"] == 20.6
    assert summary["stage_wall_clock_stt2_selective_recheck_applied_segment_count"]["list"] == [5, 4]
    assert summary["stage_wall_clock_stt2_selective_recheck_missing_voice_range_count"]["list"] == [1, 2]
    assert summary["stage_wall_clock_stt2_selective_recheck_route_hint_range_count"]["list"] == [0, 1]
    assert summary["stage_wall_clock_stt2_selective_recheck_low_score_range_count"]["list"] == [1, 0]
    assert summary["stage_wall_clock_stt2_selective_recheck_empty_text_range_count"]["max"] == 2
    assert summary["stage_wall_clock_word_precision_total_elapsed_sec"]["max"] == 4.0
    assert summary["stage_wall_clock_word_precision_collect_elapsed_sec"]["list"] == [3.4, 3.0]
    assert summary["stage_wall_clock_word_precision_range_audio_sec"]["avg"] == 7.5
    assert summary["stage_wall_clock_word_precision_max_range_duration_sec"]["max"] == 2.5
    assert summary["stage_wall_clock_word_precision_prepared_audio_sec"]["list"] == [10.4, 9.0]
    assert summary["stage_wall_clock_word_precision_max_prepared_clip_duration_sec"]["max"] == 3.2
    assert summary["stage_wall_clock_word_precision_selected_range_count"]["list"] == [1, 0]
    assert summary["stage_wall_clock_word_precision_precision_review_range_count"]["list"] == [2, 1]
    assert summary["stage_wall_clock_word_precision_needs_review_range_count"]["list"] == [1, 1]
    assert summary["stage_wall_clock_word_precision_red_range_count"]["list"] == [1, 0]
    assert summary["stage_wall_clock_word_precision_yellow_range_count"]["list"] == [2, 1]
    assert summary["stage_wall_clock_word_precision_risk_range_count"]["avg"] == 2.5
    assert summary["stage_wall_clock_word_precision_missing_word_range_count"]["max"] == 4
    assert summary["stage_wall_clock_vad_stt_consensus_total_elapsed_sec"]["min"] == 0.2
    assert summary["stage_wall_clock_subtitle_postprocess_total_elapsed_sec"]["avg"] == 7.75
    assert summary["stage_wall_clock_subtitle_postprocess_detail_top_stage"]["latest"] == "high_context_boundary"
    assert summary["stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec"]["avg"] == 5.5
    assert summary["stage_wall_clock_subtitle_postprocess_detail_stage_count"]["list"] == [4, 4]
    assert summary["stage_wall_clock_subtitle_postprocess_detail_total_elapsed_sec"]["avg"] == 6.75
    assert summary["high_context_boundary_enabled"]["all"] is True
    assert summary["high_context_boundary_reason"]["latest"] == "completed"
    assert summary["high_context_boundary_candidate_pair_count"]["list"] == [3, 4]
    assert summary["high_context_boundary_skipped_pair_count"]["avg"] == 10.5
    assert summary["high_context_boundary_llm_call_count"]["avg"] == 3.5
    assert summary["high_context_boundary_failed_call_count"]["max"] == 0
    assert summary["high_context_boundary_changed_pair_count"]["list"] == [0, 1]
    assert summary["high_context_boundary_max_pairs"]["list"] == [24, 24]
    assert summary["high_context_boundary_keep_decision_count"]["list"] == [3, 2]
    assert summary["high_context_boundary_move_boundary_decision_count"]["list"] == [0, 1]
    assert summary["high_context_boundary_merge_decision_count"]["max"] == 0
    assert summary["high_context_boundary_invalid_decision_count"]["list"] == [0, 1]
    assert summary["high_context_boundary_correction_request_count"]["avg"] == 1.5
    assert summary["high_context_boundary_applied_correction_count"]["list"] == [0, 1]
    assert summary["high_context_boundary_keep_cache_enabled"]["all"] is True
    assert summary["high_context_boundary_keep_cache_hit_count"]["list"] == [0, 2]
    assert summary["high_context_boundary_keep_cache_miss_count"]["avg"] == 2.5
    assert summary["high_context_boundary_keep_cache_write_count"]["list"] == [3, 1]
    assert summary["high_context_boundary_elapsed_sec"]["avg"] == 4.875
    assert summary["generation_profile_top_stage"]["latest"] == "stt2_selective_recheck"
    assert summary["generation_profile_top_cumulative_time_sec"]["max"] == 40.0
