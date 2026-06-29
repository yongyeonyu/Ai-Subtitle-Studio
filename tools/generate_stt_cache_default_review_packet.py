#!/usr/bin/env python3
"""Build an owner-review packet for STT collect-cache default promotion."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime.config import DEFAULT_ADV_SETTINGS


DEFAULT_EVIDENCE_DIR = (
    "output/manual_verification/latest/stt_cache_backfill_real_nas_20260628_2202"
)

DECISION_ROWS = (
    {
        "id": "stt_primary_collect_cache",
        "label": "STT1 primary collect cache",
        "default_key": "stt_primary_collect_cache_enabled",
        "readiness_family": "stt_primary_collect_cache",
    },
    {
        "id": "stt2_selective_recheck_collect_cache",
        "label": "STT2 selective recheck collect cache",
        "default_key": "stt_recheck_collect_cache_enabled",
        "readiness_family": "stt_recheck_word_collect_cache",
    },
    {
        "id": "word_precision_collect_cache",
        "label": "Word precision collect cache",
        "default_key": "stt_recheck_collect_cache_enabled",
        "readiness_family": "stt_recheck_word_collect_cache",
    },
)


def _resolve(root: Path, path: str | Path) -> Path:
    value = Path(path).expanduser()
    if value.is_absolute():
        return value
    return root / value


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _acceptance_summary(payload: dict[str, Any]) -> dict[str, Any]:
    benchmark = dict(payload.get("benchmark") or {})
    return {
        "accepted": bool(payload.get("accepted")),
        "elapsed_sec": benchmark.get("elapsed_sec"),
        "raw_segments": benchmark.get("raw_segments"),
        "final_segments": benchmark.get("final_segments"),
        "reference_segments": benchmark.get("reference_segments"),
        "quality_score": benchmark.get("quality_score"),
        "text_score": benchmark.get("text_score"),
        "timing_mae_sec": benchmark.get("timing_mae_sec"),
        "final_invalid_duration_count": benchmark.get("final_invalid_duration_count"),
        "final_non_monotonic_count": benchmark.get("final_non_monotonic_count"),
        "final_overlap_count": benchmark.get("final_overlap_count"),
        "final_last_end_sec": benchmark.get("final_last_end_sec"),
        "duration_bound_sec": (payload.get("thresholds") or {}).get("duration_bound_sec"),
        "final_stable_for_save_reopen": benchmark.get("final_stable_for_save_reopen"),
        "global_canvas_max_active_segments": benchmark.get("global_canvas_max_active_segments"),
        "global_canvas_stable": benchmark.get("global_canvas_stable"),
        "reasons": list(payload.get("reasons") or []),
    }


def _decision_matrix(
    *,
    defaults: dict[str, Any],
    readiness: dict[str, Any],
    evidence_ready: bool,
) -> list[dict[str, Any]]:
    families = dict(readiness.get("families") or {})
    rows: list[dict[str, Any]] = []
    for item in DECISION_ROWS:
        family = dict(families.get(item["readiness_family"]) or {})
        current_default = bool(defaults.get(item["default_key"], False))
        rows.append(
            {
                "id": item["id"],
                "label": item["label"],
                "default_key": item["default_key"],
                "current_default": current_default,
                "readiness_family": item["readiness_family"],
                "readiness_status": family.get("status"),
                "strict_real_cache_write_count": len(family.get("strict_real_cache_write_runs") or []),
                "strict_real_cache_hit_count": len(family.get("strict_real_cache_hit_runs") or []),
                "evidence_ready": bool(evidence_ready and family.get("status") == "real_backfill_present_owner_review_required"),
                "owner_approval_required": True,
                "default_change_allowed": False,
                "rollback_boundary_required": True,
                "promotion_mode": "one_cache_at_a_time_only_after_owner_approval",
                "focused_proof_required_after_any_change": [
                    "same_real_media_write_and_hit_acceptance",
                    "final_invalid_non_monotonic_overlap_0_0_0",
                    "save_reopen_stable_true",
                    "global_canvas_max_active_segments_1",
                    "defaults_assertion_for_only_the_selected_cache",
                ],
            }
        )
    return rows


def _first_run(readiness: dict[str, Any], family: str, key: str) -> dict[str, Any]:
    family_data = dict((readiness.get("families") or {}).get(family) or {})
    rows = family_data.get(key) or []
    return dict(rows[0]) if rows and isinstance(rows[0], dict) else {}


def build_review_packet(
    *,
    root: Path = ROOT,
    evidence_dir: str | Path = DEFAULT_EVIDENCE_DIR,
    output_dir: str | Path | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    evidence_path = _resolve(root, evidence_dir)
    output_path = _resolve(
        root,
        output_dir or "output/manual_verification/latest/stt_cache_default_review_packet",
    )
    defaults = dict(DEFAULT_ADV_SETTINGS if defaults is None else defaults)
    current_defaults = {
        "stt_primary_collect_cache_enabled": bool(defaults.get("stt_primary_collect_cache_enabled", False)),
        "stt_recheck_collect_cache_enabled": bool(defaults.get("stt_recheck_collect_cache_enabled", False)),
    }

    write_acceptance = _load_json(evidence_path / "acceptance_write" / "reference_benchmark_acceptance.json")
    hit_acceptance = _load_json(evidence_path / "acceptance_hit" / "reference_benchmark_acceptance.json")
    readiness = _load_json(evidence_path / "readiness_refresh" / "stt_cache_backfill_readiness.json")
    timeout_audit = _load_json(evidence_path / "timeout_audit" / "stt_worker_timeout_audit.json")

    write_summary = _acceptance_summary(write_acceptance)
    hit_summary = _acceptance_summary(hit_acceptance)
    evidence_ready = (
        write_summary["accepted"] is True
        and hit_summary["accepted"] is True
        and timeout_audit.get("timeout_detected") is False
    )
    combined_write = _first_run(readiness, "combined_collect_cache", "strict_real_cache_write_runs")
    combined_hit = _first_run(readiness, "combined_collect_cache", "strict_real_cache_hit_runs")
    production_defaults_unchanged = not any(current_defaults.values())
    matrix = _decision_matrix(defaults=current_defaults, readiness=readiness, evidence_ready=evidence_ready)
    status = "owner_review_required" if evidence_ready and production_defaults_unchanged else "hold_default_off"
    elapsed_delta = None
    elapsed_ratio = None
    if isinstance(write_summary.get("elapsed_sec"), (int, float)) and isinstance(hit_summary.get("elapsed_sec"), (int, float)):
        elapsed_delta = round(float(write_summary["elapsed_sec"]) - float(hit_summary["elapsed_sec"]), 6)
        if float(hit_summary["elapsed_sec"]) > 0:
            elapsed_ratio = round(float(write_summary["elapsed_sec"]) / float(hit_summary["elapsed_sec"]), 6)

    return {
        "schema": "ai_subtitle_studio.stt_cache_default_review_packet.v1",
        "root": str(root),
        "output_dir": str(output_path),
        "evidence_dir": str(evidence_path),
        "status": status,
        "not_runtime_change": True,
        "production_defaults_unchanged": production_defaults_unchanged,
        "default_promotion_allowed": False,
        "owner_review_required": True,
        "current_defaults": current_defaults,
        "evidence_summary": {
            "write_acceptance": write_summary,
            "hit_acceptance": hit_summary,
            "representative_fixture": {
                "media": combined_write.get("media") or combined_hit.get("media"),
                "reference_srt": combined_write.get("reference_srt") or combined_hit.get("reference_srt"),
                "start_sec": 0,
                "duration_sec": write_summary.get("duration_bound_sec") or hit_summary.get("duration_bound_sec"),
                "write_run_id": combined_write.get("run_id"),
                "hit_run_id": combined_hit.get("run_id"),
                "same_media_and_reference": bool(
                    combined_write
                    and combined_hit
                    and combined_write.get("media") == combined_hit.get("media")
                    and combined_write.get("reference_srt") == combined_hit.get("reference_srt")
                ),
                "same_fixture_cache_hit_replay_only": True,
            },
            "provider_calls": {
                "write_path": True,
                "cache_hit_replay": False,
                "source": "readiness strict_real_cache_write_runs / strict_real_cache_hit_runs",
            },
            "cache_hit_replay_delta_sec": elapsed_delta,
            "write_to_hit_elapsed_ratio": elapsed_ratio,
            "readiness_statuses": {
                key: (value or {}).get("status")
                for key, value in dict(readiness.get("families") or {}).items()
            },
            "timeout_detected": bool(timeout_audit.get("timeout_detected")),
            "timeout_run_count": timeout_audit.get("timeout_run_count"),
        },
        "decision_matrix": matrix,
        "remaining_blockers": [
            "owner_approval_for_cache_default_promotion",
            "one_cache_at_a_time_promotion_only",
            "rollback_commit_boundary_before_any_default_change",
            "focused_same_fixture_proof_after_any_default_change",
            "no_app_store_ui_or_nle_claim_from_this_packet",
        ],
        "not_included": [
            "runtime_default_change",
            "model_downgrade",
            "stt2_skip",
            "word_precision_disable",
            "quality_gate_relaxation",
            "fast_mode_default_promotion",
            "ui_ux_change",
            "app_store_packaging_signing_upload_or_submission",
            "nle_persistence_or_disk_format_change",
        ],
        "interpretation": (
            "This packet collects representative NAS cache write/hit evidence for owner review. "
            "The 1.183s value is same-fixture cache-hit replay evidence, not first-run user speed. "
            "It does not enable collect caches by default and does not approve production speed claims."
        ),
    }


def render_markdown(packet: dict[str, Any]) -> str:
    evidence = dict(packet.get("evidence_summary") or {})
    write = dict(evidence.get("write_acceptance") or {})
    hit = dict(evidence.get("hit_acceptance") or {})
    fixture = dict(evidence.get("representative_fixture") or {})
    lines = [
        "# STT Cache Default Review Packet",
        "",
        "This is an owner-review packet. It is not a runtime default change.",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Not runtime change: `{packet.get('not_runtime_change')}`",
        f"- Production defaults unchanged: `{packet.get('production_defaults_unchanged')}`",
        f"- Default promotion allowed by this packet: `{packet.get('default_promotion_allowed')}`",
        f"- Current defaults: `{packet.get('current_defaults')}`",
        f"- Evidence dir: `{packet.get('evidence_dir')}`",
        "",
        "## Evidence Summary",
        "",
        f"- Fixture: `{fixture.get('media')}`",
        f"- Reference SRT: `{fixture.get('reference_srt')}`",
        f"- Same fixture cache-hit replay only: `{fixture.get('same_fixture_cache_hit_replay_only')}`",
        f"- Write accepted: `{write.get('accepted')}`, elapsed: `{write.get('elapsed_sec')}`",
        f"- Hit accepted: `{hit.get('accepted')}`, elapsed: `{hit.get('elapsed_sec')}`",
        f"- Cache-hit replay delta seconds: `{evidence.get('cache_hit_replay_delta_sec')}`",
        f"- Write/hit elapsed ratio: `{evidence.get('write_to_hit_elapsed_ratio')}`",
        f"- Raw/final/reference: `{write.get('raw_segments')}` / `{write.get('final_segments')}` / `{write.get('reference_segments')}`",
        f"- Quality/text/timing: `{write.get('quality_score')}` / `{write.get('text_score')}` / `{write.get('timing_mae_sec')}`",
        f"- Final invalid/non-monotonic/overlap: `{write.get('final_invalid_duration_count')}` / `{write.get('final_non_monotonic_count')}` / `{write.get('final_overlap_count')}`",
        f"- Final last end/duration bound: `{write.get('final_last_end_sec')}` / `{write.get('duration_bound_sec')}`",
        f"- Global canvas max active: `{write.get('global_canvas_max_active_segments')}`",
        f"- Timeout detected: `{evidence.get('timeout_detected')}`",
        "",
        "## Decision Matrix",
        "",
        "| Cache | Current Default | Evidence Ready | Owner Approval Required | Default Change Allowed |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in packet.get("decision_matrix") or []:
        lines.append(
            "| {label} | `{current_default}` | `{evidence_ready}` | `{owner_approval_required}` | `{default_change_allowed}` |".format(
                label=row.get("label"),
                current_default=row.get("current_default"),
                evidence_ready=row.get("evidence_ready"),
                owner_approval_required=row.get("owner_approval_required"),
                default_change_allowed=row.get("default_change_allowed"),
            )
        )
    lines.extend(["", "## Remaining Blockers", ""])
    lines.extend(f"- `{item}`" for item in packet.get("remaining_blockers") or [])
    lines.extend(["", "## Not Included", ""])
    lines.extend(f"- `{item}`" for item in packet.get("not_included") or [])
    lines.extend(["", packet.get("interpretation") or "", ""])
    return "\n".join(lines)


def write_review_packet(packet: dict[str, Any], output_dir: str | Path | None = None) -> list[Path]:
    output_path = _resolve(Path(packet["root"]), output_dir or packet["output_dir"])
    written = [
        output_path / "stt_cache_default_review_packet.json",
        output_path / "stt_cache_default_review_packet.md",
        output_path / "decision_matrix.json",
    ]
    packet = dict(packet)
    packet["output_dir"] = str(output_path)
    _write_json(written[0], packet)
    _write_text(written[1], render_markdown(packet))
    _write_json(written[2], packet["decision_matrix"])
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    packet = build_review_packet(evidence_dir=args.evidence_dir, output_dir=args.output_dir)
    written = write_review_packet(packet, args.output_dir)
    print(
        json.dumps(
            {
                "output_dir": str(_resolve(ROOT, args.output_dir)),
                "status": packet["status"],
                "production_defaults_unchanged": packet["production_defaults_unchanged"],
                "default_promotion_allowed": packet["default_promotion_allowed"],
                "written": [str(path) for path in written],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
