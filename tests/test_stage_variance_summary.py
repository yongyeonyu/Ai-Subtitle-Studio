from __future__ import annotations

import json
from pathlib import Path

from tools.summarize_stage_variance import build_summary, load_runs, render_markdown


def _write_result(path: Path, *, elapsed: float, stt1_collect: float, pressure: str, cache_hit: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "ai_subtitle_studio.benchmark_results.v1",
        "media": "fixture.mp4",
        "duration_sec": 180.0,
        "results": [
            {
                "name": "mode_high",
                "elapsed_sec": elapsed,
                "raw_segments": 54,
                "final_segments": 54,
                "quality": {
                    "reference_segments": 54,
                    "quality_score": 80.153,
                    "text_score": 91.676,
                    "timing_mae_sec": 1.437,
                },
                "native_segments_summary": {
                    "invalid_duration_count": 0,
                    "non_monotonic_count": 0,
                    "overlap_count": 0,
                    "stable_for_save_reopen": True,
                    "last_end": 180.0,
                },
                "native_global_canvas_summary": {
                    "max_active_segments": 1,
                    "stable_for_global_canvas": True,
                },
                "stage_wall_clock_summary": {
                    "stage_summaries": {
                        "stt_primary_transcribe": {
                            "total_elapsed_sec": stt1_collect + 0.05,
                            "max_elapsed_sec": stt1_collect + 0.05,
                            "total_collect_elapsed_sec": stt1_collect,
                            "total_setup_elapsed_sec": 0.05,
                        },
                        "stt2_selective_recheck": {
                            "total_elapsed_sec": 0.1,
                            "max_elapsed_sec": 0.1,
                            "total_collect_elapsed_sec": 0.0,
                            "total_prepare_elapsed_sec": 0.08,
                        },
                        "word_precision": {
                            "total_elapsed_sec": 0.5,
                            "max_elapsed_sec": 0.5,
                            "total_collect_elapsed_sec": 0.0,
                            "total_prepare_elapsed_sec": 0.49,
                        },
                        "subtitle_postprocess": {
                            "total_elapsed_sec": 0.4,
                            "max_elapsed_sec": 0.4,
                            "total_detail_top_elapsed_sec": 0.3,
                        },
                    },
                    "spans": [
                        {
                            "stage": "stt_primary_transcribe",
                            "collect_elapsed_sec": stt1_collect,
                            "setup_elapsed_sec": 0.05,
                            "collect_cache_enabled": True,
                            "collect_cache_hit": cache_hit,
                            "collect_cache_write": not cache_hit,
                            "collect_provider_called": not cache_hit,
                            "resource_pressure_stage": pressure,
                        },
                        {
                            "stage": "stt2_selective_recheck",
                            "collect_cache_enabled": True,
                            "collect_cache_hit": cache_hit,
                            "collect_cache_write": not cache_hit,
                            "collect_provider_called": not cache_hit,
                            "collect_elapsed_sec": 0.0,
                            "prepare_elapsed_sec": 0.08,
                        },
                        {
                            "stage": "word_precision",
                            "collect_cache_enabled": True,
                            "collect_cache_hit": cache_hit,
                            "collect_cache_write": not cache_hit,
                            "collect_provider_called": not cache_hit,
                            "collect_elapsed_sec": 0.0,
                            "prepare_elapsed_sec": 0.49,
                        },
                        {
                            "stage": "subtitle_postprocess_detail",
                            "detail_stage": "proofread_dictionary_llm",
                            "detail_elapsed_sec": 0.3,
                            "llm_macro_response_cache_hit_group_count": 1 if cache_hit else 0,
                            "llm_macro_response_cache_write_group_count": 0 if cache_hit else 1,
                            "llm_macro_provider_called_group_count": 0 if cache_hit else 1,
                        },
                    ],
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_summary_rolls_up_stage_and_memory_variance(tmp_path: Path) -> None:
    first = tmp_path / "20260628_000001" / "benchmark_results.json"
    second = tmp_path / "20260628_000002" / "benchmark_results.json"
    _write_result(first, elapsed=40.0, stt1_collect=17.0, pressure="normal", cache_hit=False)
    _write_result(second, elapsed=4.0, stt1_collect=0.0, pressure="warning", cache_hit=True)

    summary = build_summary(load_runs([first, second]))

    assert summary["run_count"] == 2
    assert summary["elapsed_sec"]["range"] == 36.0
    assert summary["stage_variance"]["stt_primary_transcribe"]["range"] == 17.0
    assert summary["pressure_worst_counts"] == {"normal": 1, "warning": 1}
    assert summary["final_gate_all"]["overlap_count_zero"] is True
    assert summary["final_gate_all"]["last_end_within_duration_bound"] is True
    assert summary["runs"][1]["cache"]["stt_primary"]["hit"] is True
    assert summary["runs"][1]["cache"]["macro_proofread"]["provider_called_groups"] == 0


def test_build_summary_flags_duration_bound_failures(tmp_path: Path) -> None:
    path = tmp_path / "20260628_000001" / "benchmark_results.json"
    _write_result(path, elapsed=4.0, stt1_collect=0.0, pressure="normal", cache_hit=True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["results"][0]["native_segments_summary"]["last_end"] = 182.0
    path.write_text(json.dumps(payload), encoding="utf-8")

    summary = build_summary(load_runs([path]))

    assert summary["runs"][0]["final_gates"]["last_end_beyond_duration_sec"] == 2.0
    assert summary["final_gate_all"]["last_end_within_duration_bound"] is False


def test_render_markdown_keeps_interpretation_guard(tmp_path: Path) -> None:
    path = tmp_path / "20260628_000001" / "benchmark_results.json"
    _write_result(path, elapsed=4.0, stt1_collect=0.0, pressure="normal", cache_hit=True)

    markdown = render_markdown(build_summary(load_runs([path])))

    assert "Stage Variance Summary" in markdown
    assert "Do not enable `stt_recheck_collect_cache_enabled`" in markdown
