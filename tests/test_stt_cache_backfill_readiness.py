from __future__ import annotations

import json
from pathlib import Path

from tools.audit_stt_cache_backfill_readiness import build_readiness, load_runs, render_markdown


def _write_result(
    path: Path,
    *,
    media: str,
    reference_srt: str,
    cache_hit: bool,
    last_end: float = 180.0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "ai_subtitle_studio.benchmark_results.v1",
        "media": media,
        "reference_srt": reference_srt,
        "duration_sec": 180.0,
        "results": [
            {
                "name": "mode_high",
                "elapsed_sec": 4.0 if cache_hit else 44.0,
                "raw_segments": 54,
                "final_segments": 54,
                "quality": {
                    "reference_segments": 54,
                    "quality_score": 93.411,
                    "text_score": 91.676,
                    "timing_mae_sec": 0.1391,
                },
                "native_segments_summary": {
                    "invalid_duration_count": 0,
                    "non_monotonic_count": 0,
                    "overlap_count": 0,
                    "stable_for_save_reopen": True,
                    "last_end": last_end,
                },
                "native_global_canvas_summary": {
                    "max_active_segments": 1,
                    "stable_for_global_canvas": True,
                },
                "stage_wall_clock_summary": {
                    "stage_summaries": {
                        "stt_primary_transcribe": {"total_elapsed_sec": 0.05 if cache_hit else 18.0},
                        "stt2_selective_recheck": {"total_elapsed_sec": 0.1 if cache_hit else 14.0},
                        "word_precision": {"total_elapsed_sec": 0.5 if cache_hit else 12.0},
                        "subtitle_postprocess": {"total_elapsed_sec": 0.4},
                    },
                    "spans": [
                        {
                            "stage": "stt_primary_transcribe",
                            "collect_cache_enabled": True,
                            "collect_cache_hit": cache_hit,
                            "collect_cache_write": not cache_hit,
                            "collect_provider_called": not cache_hit,
                        },
                        {
                            "stage": "stt2_selective_recheck",
                            "collect_cache_enabled": True,
                            "collect_cache_hit": cache_hit,
                            "collect_cache_write": not cache_hit,
                            "collect_provider_called": not cache_hit,
                        },
                        {
                            "stage": "word_precision",
                            "collect_cache_enabled": True,
                            "collect_cache_hit": cache_hit,
                            "collect_cache_write": not cache_hit,
                            "collect_provider_called": not cache_hit,
                        },
                    ],
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_generated_cache_hit_keeps_collect_cache_defaults_on_hold(tmp_path: Path) -> None:
    path = tmp_path / "generated" / "benchmark_results.json"
    _write_result(
        path,
        media="output/manual_verification/latest/synthetic_fixture/generated.mp4",
        reference_srt="output/manual_verification/latest/synthetic_fixture/generated.srt",
        cache_hit=True,
    )

    readiness = build_readiness(
        load_runs([path]),
        defaults={
            "stt_primary_collect_cache_enabled": False,
            "stt_recheck_collect_cache_enabled": False,
        },
    )

    assert readiness["production_default_recommendation"] == "hold_default_off"
    assert readiness["current_real_inputs_available"] is False
    assert readiness["families"]["combined_collect_cache"]["status"] == "hold_real_media_backfill_required"
    assert readiness["families"]["combined_collect_cache"]["strict_generated_cache_hit_runs"]
    assert "missing_strict_real_media_cache_hit_replay" in readiness["families"]["combined_collect_cache"]["blockers"]


def test_failed_strict_gate_cache_hit_requires_refresh_before_backfill(tmp_path: Path) -> None:
    path = tmp_path / "generated" / "benchmark_results.json"
    _write_result(
        path,
        media="output/manual_verification/latest/synthetic_fixture/generated.mp4",
        reference_srt="output/manual_verification/latest/synthetic_fixture/generated.srt",
        cache_hit=True,
        last_end=182.0,
    )

    readiness = build_readiness(load_runs([path]))

    family = readiness["families"]["combined_collect_cache"]
    assert family["status"] == "hold_refresh_strict_generated_cache_hit_then_real_backfill"
    assert "cache_hit_runs_fail_strict_final_gate" in family["blockers"]
    assert family["failed_cache_hit_runs"][0]["last_end_within_duration_bound"] is False


def test_real_media_cache_hit_is_review_evidence_not_auto_default(tmp_path: Path) -> None:
    media = tmp_path / "real.mp4"
    reference = tmp_path / "real.srt"
    media.write_bytes(b"placeholder")
    reference.write_text("1\n00:00:00,000 --> 00:00:01,000\n테스트\n", encoding="utf-8")
    path = tmp_path / "real_run" / "benchmark_results.json"
    _write_result(path, media=str(media), reference_srt=str(reference), cache_hit=True)

    readiness = build_readiness(load_runs([path]))

    assert readiness["current_real_inputs_available"] is True
    assert readiness["production_default_recommendation"] == "hold_default_off"
    assert readiness["families"]["combined_collect_cache"]["status"] == "real_backfill_present_owner_review_required"
    assert readiness["families"]["combined_collect_cache"]["strict_real_cache_hit_runs"]


def test_render_markdown_records_default_hold_guard(tmp_path: Path) -> None:
    path = tmp_path / "generated" / "benchmark_results.json"
    _write_result(
        path,
        media="output/manual_verification/latest/synthetic_fixture/generated.mp4",
        reference_srt="output/manual_verification/latest/synthetic_fixture/generated.srt",
        cache_hit=True,
    )

    markdown = render_markdown(build_readiness(load_runs([path])))

    assert "STT Cache Backfill Readiness Audit" in markdown
    assert "Production default recommendation: `hold_default_off`" in markdown
    assert "Do not enable `stt_recheck_collect_cache_enabled`" in markdown
