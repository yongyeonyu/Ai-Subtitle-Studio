from __future__ import annotations

import json
from pathlib import Path

from tools.audit_stt_worker_timeout import build_audit, render_markdown


def _write_benchmark(path: Path, *, include_timeouts: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    spans = [
        {
            "stage": "stt_primary_transcribe",
            "elapsed_sec": 16.0 if not include_timeouts else 166.0,
            "status": "ok",
            "label": "STT1",
            "backend": "mlx",
            "received_chunks": 2,
            "processed_chunks": 2,
            "collect_elapsed_sec": 16.0,
        },
        {
            "stage": "stt2_selective_recheck",
            "elapsed_sec": 8.0 if not include_timeouts else 159.0,
            "status": "applied",
            "range_count": 1,
            "applied_segment_count": 36,
            "collect_elapsed_sec": 8.0 if not include_timeouts else 159.0,
        },
    ]
    if include_timeouts:
        spans.extend(
            [
                {
                    "stage": "stt_collect_whisperkit_fallback",
                    "elapsed_sec": 150.0,
                    "label": "STT1",
                    "reason": "worker_timeout",
                    "source_model": "whisperkit-persistent:large-v3",
                    "fallback_model": "mlx-community/whisper-large-v3-turbo",
                    "total_chunks": 2,
                    "received_chunks": 0,
                    "processed_chunks": 0,
                    "word_timestamps": False,
                },
                {
                    "stage": "stt_collect_whisperkit_fallback",
                    "elapsed_sec": 150.0,
                    "label": "Fast-STT2",
                    "reason": "worker_timeout",
                    "source_model": "whisperkit-persistent:large-v3",
                    "fallback_model": "mlx-community/whisper-large-v3-turbo",
                    "total_chunks": 1,
                    "received_chunks": 0,
                    "processed_chunks": 0,
                    "word_timestamps": False,
                },
                {
                    "stage": "word_precision_collect_transcribe",
                    "elapsed_sec": 30.1,
                    "label": "STT-단어정밀",
                    "status": "failed",
                    "backend": "whisperkit_persistent",
                    "resolved_model": "whisperkit-persistent:large-v3",
                    "chunk_count": 3,
                    "received_chunks": 0,
                    "worker_silence_timeout_sec": 30.0,
                    "word_timestamps": True,
                },
            ]
        )
    payload = {
        "schema": "ai_subtitle_studio.benchmark_results.v1",
        "media": "/Volumes/photo/heydealer.mp4",
        "reference_srt": "/Volumes/photo/heydealer.srt",
        "duration_sec": 180.0,
        "ranked_results": [
            {
                "name": "mode_high",
                "elapsed_sec": 374.0 if include_timeouts else 45.0,
                "raw_segments": 55,
                "final_segments": 57,
                "quality": {
                    "reference_segments": 89,
                    "quality_score": 93.955,
                    "text_score": 94.867,
                    "timing_mae_sec": 0.5536,
                },
                "native_segments_summary": {
                    "invalid_duration_count": 0,
                    "non_monotonic_count": 0,
                    "overlap_count": 0,
                    "stable_for_save_reopen": True,
                    "last_end": 180.0,
                    "short_segment_count": 0,
                    "long_segment_count": 0,
                },
                "native_global_canvas_summary": {
                    "max_active_segments": 1,
                    "stable_for_global_canvas": True,
                },
                "stage_wall_clock_summary": {
                    "spans": spans,
                    "top_stage": "stt_primary_transcribe",
                    "top_elapsed_sec": 166.0 if include_timeouts else 16.0,
                },
            }
        ],
        "results": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_audit_detects_stt_worker_timeouts(tmp_path: Path) -> None:
    path = tmp_path / "20260628_123336" / "benchmark_results.json"
    _write_benchmark(path, include_timeouts=True)

    audit = build_audit([path])
    run = audit["runs"][0]

    assert audit["timeout_detected"] is True
    assert audit["timeout_run_count"] == 1
    assert run["timeout_fallback_count"] == 2
    assert run["word_precision_timeout_like_count"] == 1
    assert run["timeout_total_elapsed_sec"] == 330.1
    assert run["timeout_labels"] == {"STT1": 1, "Fast-STT2": 1}
    assert run["recommendation"] == "diagnose_worker_timeout_before_runtime_trim"
    assert audit["production_change_allowed"] is False
    assert audit["default_cache_promotion_allowed"] is False


def test_build_audit_keeps_no_timeout_artifact_clear(tmp_path: Path) -> None:
    path = tmp_path / "20260628_112647" / "benchmark_results.json"
    _write_benchmark(path, include_timeouts=False)

    audit = build_audit([path])

    assert audit["timeout_detected"] is False
    assert audit["timeout_run_count"] == 0
    assert audit["runs"][0]["recommendation"] == "no_worker_timeout_evidence_in_selected_artifacts"


def test_render_markdown_keeps_runtime_guardrails(tmp_path: Path) -> None:
    path = tmp_path / "20260628_123336" / "benchmark_results.json"
    _write_benchmark(path, include_timeouts=True)

    markdown = render_markdown(build_audit([path]))

    assert "STT Worker Timeout Audit" in markdown
    assert "Timeout detected: `True`" in markdown
    assert "Do not apply `skip_stt2`" in markdown
    assert "Do not apply `quality_gate_relaxation`" in markdown
    assert "repeat_same_fixture_after_worker_reset_or_resource_probe" in markdown
