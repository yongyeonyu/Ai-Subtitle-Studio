from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.runtime import config
from tools.generate_stt_cache_default_review_packet import (
    build_review_packet,
    render_markdown,
    write_review_packet,
)


ROOT = Path(__file__).resolve().parents[1]


def _acceptance(elapsed: float, *, accepted: bool = True, overlap: int = 0) -> dict:
    return {
        "schema": "ai_subtitle_studio.reference_benchmark_acceptance.v1",
        "accepted": accepted,
        "reasons": [] if accepted else ["test_rejection"],
        "benchmark": {
            "name": "mode_high",
            "elapsed_sec": elapsed,
            "raw_segments": 58,
            "final_segments": 56,
            "reference_segments": 89,
            "quality_score": 93.766,
            "text_score": 94.267,
            "timing_mae_sec": 0.5808,
            "final_invalid_duration_count": 0,
            "final_non_monotonic_count": 0,
            "final_overlap_count": overlap,
            "final_last_end_sec": 180.0,
            "final_stable_for_save_reopen": True,
            "global_canvas_max_active_segments": 1,
            "global_canvas_stable": True,
        },
        "thresholds": {"duration_bound_sec": 180.0},
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _evidence_dir(tmp_path: Path, *, hit_accepted: bool = True) -> Path:
    evidence_dir = tmp_path / "evidence"
    media = tmp_path / "real.mp4"
    reference = tmp_path / "real.srt"
    media.write_bytes(b"media")
    reference.write_text("1\n00:00:00,000 --> 00:00:01,000\n테스트\n", encoding="utf-8")
    _write_json(evidence_dir / "acceptance_write" / "reference_benchmark_acceptance.json", _acceptance(177.888))
    _write_json(
        evidence_dir / "acceptance_hit" / "reference_benchmark_acceptance.json",
        _acceptance(1.183, accepted=hit_accepted, overlap=0 if hit_accepted else 1),
    )
    _write_json(
        evidence_dir / "readiness_refresh" / "stt_cache_backfill_readiness.json",
        {
            "schema": "ai_subtitle_studio.stt_cache_backfill_readiness.v1",
            "default_settings": {
                "stt_primary_collect_cache_enabled": False,
                "stt_recheck_collect_cache_enabled": False,
            },
            "families": {
                "stt_primary_collect_cache": _family(media, reference),
                "stt_recheck_word_collect_cache": _family(media, reference),
                "combined_collect_cache": _family(media, reference),
            },
        },
    )
    _write_json(
        evidence_dir / "timeout_audit" / "stt_worker_timeout_audit.json",
        {
            "schema": "ai_subtitle_studio.stt_worker_timeout_audit.v1",
            "timeout_detected": False,
            "timeout_run_count": 0,
            "production_change_allowed": False,
            "default_cache_promotion_allowed": False,
        },
    )
    return evidence_dir


def _family(media: Path, reference: Path) -> dict:
    write = {
        "run_id": "20260628_220327",
        "path": ".codex_work/benchmarks/subtitle_pipeline_variants/20260628_220327/benchmark_results.json",
        "media": str(media),
        "reference_srt": str(reference),
        "elapsed_sec": 177.888,
        "quality_score": 93.766,
        "raw_segments": 58,
        "final_segments": 56,
        "reference_segments": 89,
        "strict_final_pass": True,
        "last_end_within_duration_bound": True,
    }
    hit = dict(write)
    hit.update(
        {
            "run_id": "20260628_220718",
            "path": ".codex_work/benchmarks/subtitle_pipeline_variants/20260628_220718/benchmark_results.json",
            "elapsed_sec": 1.183,
        }
    )
    return {
        "status": "real_backfill_present_owner_review_required",
        "default_keys": {
            "stt_primary_collect_cache_enabled": False,
            "stt_recheck_collect_cache_enabled": False,
        },
        "blockers": [],
        "strict_real_cache_write_runs": [write],
        "strict_real_cache_hit_runs": [hit],
        "strict_generated_cache_hit_runs": [],
        "failed_cache_hit_runs": [],
    }


def test_review_packet_is_owner_review_only_and_keeps_defaults_off(tmp_path: Path) -> None:
    packet = build_review_packet(evidence_dir=_evidence_dir(tmp_path), output_dir=tmp_path / "out")

    assert packet["schema"] == "ai_subtitle_studio.stt_cache_default_review_packet.v1"
    assert packet["status"] == "owner_review_required"
    assert packet["not_runtime_change"] is True
    assert packet["production_defaults_unchanged"] is True
    assert packet["default_promotion_allowed"] is False
    assert packet["current_defaults"] == {
        "stt_primary_collect_cache_enabled": False,
        "stt_recheck_collect_cache_enabled": False,
    }
    assert config.DEFAULT_ADV_SETTINGS["stt_primary_collect_cache_enabled"] is False
    assert config.DEFAULT_ADV_SETTINGS["stt_recheck_collect_cache_enabled"] is False


def test_review_packet_preserves_real_nas_acceptance_numbers(tmp_path: Path) -> None:
    packet = build_review_packet(evidence_dir=_evidence_dir(tmp_path), output_dir=tmp_path / "out")
    evidence = packet["evidence_summary"]
    write = evidence["write_acceptance"]
    hit = evidence["hit_acceptance"]

    assert write["accepted"] is True
    assert hit["accepted"] is True
    assert write["elapsed_sec"] == 177.888
    assert hit["elapsed_sec"] == 1.183
    assert write["raw_segments"] == 58
    assert write["final_segments"] == 56
    assert write["reference_segments"] == 89
    assert write["quality_score"] == 93.766
    assert write["text_score"] == 94.267
    assert write["timing_mae_sec"] == 0.5808
    assert write["final_invalid_duration_count"] == 0
    assert write["final_non_monotonic_count"] == 0
    assert write["final_overlap_count"] == 0
    assert write["final_last_end_sec"] == 180.0
    assert write["duration_bound_sec"] == 180.0
    assert write["global_canvas_max_active_segments"] == 1
    assert evidence["representative_fixture"]["same_media_and_reference"] is True
    assert evidence["representative_fixture"]["same_fixture_cache_hit_replay_only"] is True
    assert evidence["provider_calls"] == {
        "write_path": True,
        "cache_hit_replay": False,
        "source": "readiness strict_real_cache_write_runs / strict_real_cache_hit_runs",
    }
    assert evidence["timeout_detected"] is False


def test_decision_matrix_requires_owner_approval_for_each_cache(tmp_path: Path) -> None:
    packet = build_review_packet(evidence_dir=_evidence_dir(tmp_path), output_dir=tmp_path / "out")

    assert {row["id"] for row in packet["decision_matrix"]} == {
        "stt_primary_collect_cache",
        "stt2_selective_recheck_collect_cache",
        "word_precision_collect_cache",
    }
    for row in packet["decision_matrix"]:
        assert row["current_default"] is False
        assert row["evidence_ready"] is True
        assert row["owner_approval_required"] is True
        assert row["default_change_allowed"] is False
        assert row["rollback_boundary_required"] is True
        assert row["promotion_mode"] == "one_cache_at_a_time_only_after_owner_approval"


def test_packet_stays_hold_when_acceptance_is_not_strict(tmp_path: Path) -> None:
    packet = build_review_packet(evidence_dir=_evidence_dir(tmp_path, hit_accepted=False), output_dir=tmp_path / "out")

    assert packet["status"] == "hold_default_off"
    assert packet["default_promotion_allowed"] is False
    assert packet["evidence_summary"]["hit_acceptance"]["accepted"] is False


def test_markdown_and_written_artifacts_avoid_misleading_claims(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    packet = build_review_packet(evidence_dir=_evidence_dir(tmp_path), output_dir=output_dir)
    written = write_review_packet(packet, output_dir)
    names = {path.name for path in written}
    markdown = render_markdown(packet)

    assert "stt_cache_default_review_packet.json" in names
    assert "stt_cache_default_review_packet.md" in names
    assert "decision_matrix.json" in names
    assert "owner-review packet" in markdown
    assert "Production defaults unchanged: `True`" in markdown
    assert "Default promotion allowed by this packet: `False`" in markdown
    assert "same-fixture cache-hit replay evidence, not first-run user speed" in markdown
    for forbidden in (
        "enabled by default",
        "production speedup complete",
        "default promoted",
        "shipped performance improvement",
        "generation is now faster",
    ):
        assert forbidden not in markdown


def test_review_packet_cli_writes_summary(tmp_path: Path) -> None:
    output_dir = tmp_path / "cli_out"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/generate_stt_cache_default_review_packet.py"),
            "--evidence-dir",
            str(_evidence_dir(tmp_path)),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["output_dir"] == str(output_dir)
    assert payload["status"] == "owner_review_required"
    assert payload["production_defaults_unchanged"] is True
    assert payload["default_promotion_allowed"] is False
    assert (output_dir / "stt_cache_default_review_packet.md").is_file()
    assert (output_dir / "decision_matrix.json").is_file()
