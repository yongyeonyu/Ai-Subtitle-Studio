#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime.config import APP_VERSION

SCHEMA = "ai_subtitle_studio.g3_active_final_surface_audit.v1"
DEFAULT_SOURCE_DIR = (
    ROOT / "output/manual_verification/latest/g3_live_nle_real_media_observability_timeout20_20260629"
)
TRACK_ORDER = ("VAD", "STT1", "STT2", "subtitle_preview", "final")
RUNTIME_REFERENCE_TRACKS = tuple(track for track in TRACK_ORDER if track != "final")
_LIVE_SNAPSHOT_RE = re.compile(r"live_nle_\d+_(?P<ms>\d+)ms\.png$")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _track_counts(sample: dict[str, Any]) -> dict[str, int]:
    raw = sample.get("nle_runtime_track_counts") if isinstance(sample.get("nle_runtime_track_counts"), dict) else {}
    return {track: max(0, _as_int(raw.get(track), 0)) for track in TRACK_ORDER}


def _compact_contract_ok(sample: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    contract = (
        sample.get("compact_runtime_track_contract")
        if isinstance(sample.get("compact_runtime_track_contract"), dict)
        else {}
    )
    if not bool(contract.get("compact_payload", False)):
        issues.append("compact_payload_missing")
    if bool(contract.get("raw_payload_leak", False)):
        issues.append("raw_runtime_payload_leak")
    if not bool(contract.get("final_authority_ok", False)):
        issues.append("final_authority_contract_failed")
    authority = contract.get("authority") if isinstance(contract.get("authority"), dict) else {}
    if authority.get("final") is not True:
        issues.append("final_not_authoritative")
    for track in RUNTIME_REFERENCE_TRACKS:
        if authority.get(track) is not False:
            issues.append(f"{track.lower()}_authority_drift")
    return not issues, issues


def _budget_contract_ok(sample: dict[str, Any]) -> bool:
    budget = (
        sample.get("live_nle_projection_budget_contract")
        if isinstance(sample.get("live_nle_projection_budget_contract"), dict)
        else {}
    )
    return bool(budget.get("present", False)) and bool(budget.get("ok", False))


def _is_valid_active_final_sample(sample: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    counts = _track_counts(sample)
    if not bool(sample.get("ok", False)):
        issues.append("status_poll_failed")
    if not bool(sample.get("pre_final_active", False)):
        issues.append("not_pre_final_active")
    if bool(sample.get("generation_completed", False)):
        issues.append("completed_sample")
    if bool(sample.get("status_handler_timeout", False)):
        issues.append("status_handler_timeout")
    if bool(sample.get("status_response_cached", False)):
        issues.append("status_response_cached")
    if bool(sample.get("status_snapshot_fallback", False)):
        issues.append("status_snapshot_fallback")
    if counts["final"] <= 0:
        issues.append("final_track_missing")
    if not any(counts[track] > 0 for track in RUNTIME_REFERENCE_TRACKS):
        issues.append("runtime_reference_track_missing")
    compact_ok, compact_issues = _compact_contract_ok(sample)
    if not compact_ok:
        issues.extend(compact_issues)
    if not _budget_contract_ok(sample):
        issues.append("projection_budget_contract_failed")
    return not issues, issues


def _snapshot_elapsed_sec(path: str) -> float | None:
    match = _LIVE_SNAPSHOT_RE.search(Path(path).name)
    if not match:
        return None
    return _as_float(match.group("ms"), 0.0) / 1000.0


def _snapshot_pairs(
    *,
    source_dir: Path,
    snapshot_files: list[str],
    observations: list[dict[str, Any]],
    max_delta_sec: float,
) -> list[dict[str, Any]]:
    snapshots: list[tuple[float, str, Path]] = []
    for rel in snapshot_files:
        elapsed = _snapshot_elapsed_sec(str(rel))
        if elapsed is None:
            continue
        path = source_dir / rel
        if path.is_file() and path.stat().st_size > 0:
            snapshots.append((elapsed, str(rel), path))
    pairs: list[dict[str, Any]] = []
    for sample in observations:
        sample_elapsed = _as_float(sample.get("elapsed_sec"), 0.0)
        if not snapshots:
            continue
        nearest = min(snapshots, key=lambda item: abs(item[0] - sample_elapsed))
        delta = abs(nearest[0] - sample_elapsed)
        if delta <= max_delta_sec:
            pairs.append(
                {
                    "poll_index": sample.get("poll_index"),
                    "sample_elapsed_sec": round(sample_elapsed, 3),
                    "snapshot_elapsed_sec": round(nearest[0], 3),
                    "delta_sec": round(delta, 3),
                    "snapshot": nearest[1],
                    "snapshot_bytes": nearest[2].stat().st_size,
                }
            )
    return pairs


def build_report(
    *,
    source_dir: Path = DEFAULT_SOURCE_DIR,
    output_dir: Path | None = None,
    min_observations: int = 2,
    max_snapshot_delta_sec: float = 0.001,
) -> dict[str, Any]:
    source_dir = Path(source_dir)
    output_dir = Path(output_dir) if output_dir is not None else source_dir
    proof_path = source_dir / "live_nle_runtime_proof.json"
    samples_path = source_dir / "status_samples.json"
    issues: list[str] = []
    proof: dict[str, Any] = {}
    samples: list[dict[str, Any]] = []
    if not proof_path.is_file():
        issues.append("live_nle_runtime_proof_json_missing")
    else:
        loaded = _load_json(proof_path)
        proof = dict(loaded or {}) if isinstance(loaded, dict) else {}
    if not samples_path.is_file():
        issues.append("status_samples_json_missing")
    else:
        loaded = _load_json(samples_path)
        samples = [dict(row) for row in loaded] if isinstance(loaded, list) else []
    if proof:
        if _as_int(proof.get("sample_count"), -1) != len(samples):
            issues.append("source_sample_count_mismatch")
        if proof.get("status") != "passed":
            issues.append("source_live_nle_proof_not_passed")
        if proof.get("issues"):
            issues.append("source_live_nle_proof_has_issues")
        if _as_int(proof.get("failed_sample_count"), 0) != 0:
            issues.append("source_live_nle_proof_has_failed_samples")
        if not bool(proof.get("generation_completed", False)):
            issues.append("source_generation_not_completed")
        for key, issue in (
            ("raw_payload_leak_elapsed_sec", "source_raw_payload_leak"),
            ("compact_payload_failure_elapsed_sec", "source_compact_payload_failure"),
            ("final_authority_failure_elapsed_sec", "source_final_authority_failure"),
            ("budget_failure_elapsed_sec", "source_budget_failure"),
            ("status_handler_timeout_elapsed_sec", "source_status_handler_timeout"),
            ("status_response_cached_elapsed_sec", "source_status_response_cached"),
            ("status_snapshot_fallback_elapsed_sec", "source_status_snapshot_fallback"),
        ):
            if proof.get(key):
                issues.append(issue)

    candidate_samples: list[dict[str, Any]] = []
    valid_samples: list[dict[str, Any]] = []
    invalid_candidate_reasons: list[dict[str, Any]] = []
    for sample in samples:
        counts = _track_counts(sample)
        if counts["final"] <= 0:
            continue
        if not bool(sample.get("pre_final_active", False)):
            continue
        candidate_samples.append(sample)
        ok, sample_issues = _is_valid_active_final_sample(sample)
        if ok:
            valid_samples.append(sample)
        else:
            invalid_candidate_reasons.append(
                {
                    "poll_index": sample.get("poll_index"),
                    "elapsed_sec": sample.get("elapsed_sec"),
                    "issues": sample_issues,
                }
            )
    required = max(1, _as_int(min_observations, 2))
    if len(valid_samples) < required:
        issues.append("insufficient_active_final_observations")
    snapshot_files = list(proof.get("snapshot_files") or []) if isinstance(proof.get("snapshot_files"), list) else []
    snapshot_pairs = _snapshot_pairs(
        source_dir=source_dir,
        snapshot_files=[str(row) for row in snapshot_files],
        observations=valid_samples,
        max_delta_sec=max(0.0, _as_float(max_snapshot_delta_sec, 10.0)),
    )
    if not snapshot_pairs:
        issues.append("active_final_snapshot_pair_missing")

    observations: list[dict[str, Any]] = []
    for sample in valid_samples:
        counts = _track_counts(sample)
        observations.append(
            {
                "poll_index": sample.get("poll_index"),
                "elapsed_sec": round(_as_float(sample.get("elapsed_sec"), 0.0), 3),
                "counts": counts,
                "runtime_reference_tracks": [track for track in RUNTIME_REFERENCE_TRACKS if counts[track] > 0],
                "generation_stage": str(sample.get("generation_stage") or ""),
                "status_response_truncated": bool(sample.get("status_response_truncated", False)),
            }
        )

    max_counts = {track: max([_track_counts(sample)[track] for sample in valid_samples] or [0]) for track in TRACK_ORDER}
    return {
        "schema": SCHEMA,
        "status": "passed" if not issues else "blocked",
        "audit_app_version": APP_VERSION,
        "source_proof_app_version": str(proof.get("app_version") or "unknown_not_reexecuted_by_this_audit"),
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "source_live_proof": str(proof_path),
        "source_status_samples": str(samples_path),
        "source_live_proof_status": proof.get("status", ""),
        "source_sample_count": len(samples),
        "source_generation_completed": bool(proof.get("generation_completed", False)),
        "source_failed_sample_count": _as_int(proof.get("failed_sample_count"), 0),
        "required_active_final_observations": required,
        "active_final_candidate_count": len(candidate_samples),
        "valid_active_final_observation_count": len(valid_samples),
        "max_snapshot_delta_sec": round(max(0.0, _as_float(max_snapshot_delta_sec, 10.0)), 3),
        "snapshot_pair_count": len(snapshot_pairs),
        "snapshot_pairs": snapshot_pairs,
        "active_final_observations": observations,
        "max_counts": max_counts,
        "invalid_candidate_reasons": invalid_candidate_reasons,
        "raw_payload_guard_source": "derived_compact_contract_flags_and_source_summary_failure_lists",
        "issues": issues,
        "notes": [
            "This audit reads an existing representative live proof artifact; it is not a new live run.",
            "The source proof app version is not rebound by this offline audit; current APP_VERSION identifies the audit code only.",
            "Raw-payload leakage is checked from derived compact-contract flags and source summary failure lists because raw status payloads are intentionally not stored.",
            "status_response_truncated is diagnostic only when compact payload, raw-leak, authority, and budget contracts pass.",
            "This audit does not approve UI changes, STT/cache defaults, worker fan-out changes, disk-format cutover, or App Store readiness.",
        ],
    }


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "g3_active_final_surface_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# G3 Active-Final Surface Audit",
        "",
        f"- status: `{report.get('status')}`",
        f"- audit_app_version: `{report.get('audit_app_version')}`",
        f"- source_proof_app_version: `{report.get('source_proof_app_version')}`",
        f"- source_dir: `{report.get('source_dir')}`",
        f"- source_live_proof_status: `{report.get('source_live_proof_status')}`",
        f"- source_sample_count: `{report.get('source_sample_count')}`",
        f"- source_generation_completed: `{report.get('source_generation_completed')}`",
        f"- source_failed_sample_count: `{report.get('source_failed_sample_count')}`",
        f"- required_active_final_observations: `{report.get('required_active_final_observations')}`",
        f"- valid_active_final_observation_count: `{report.get('valid_active_final_observation_count')}`",
        f"- snapshot_pair_count: `{report.get('snapshot_pair_count')}`",
        f"- raw_payload_guard_source: `{report.get('raw_payload_guard_source')}`",
        f"- issues: `{', '.join(report.get('issues') or []) or 'none'}`",
        "",
        "## Active-Final Observations",
        "",
        "| Poll | Elapsed | Final | Runtime reference tracks | Stage |",
        "| ---: | ---: | ---: | --- | --- |",
    ]
    for row in list(report.get("active_final_observations") or []):
        counts = row.get("counts") if isinstance(row.get("counts"), dict) else {}
        lines.append(
            "| {poll} | {elapsed} | {final} | {tracks} | {stage} |".format(
                poll=row.get("poll_index", ""),
                elapsed=row.get("elapsed_sec", ""),
                final=counts.get("final", ""),
                tracks=", ".join(row.get("runtime_reference_tracks") or []),
                stage=str(row.get("generation_stage") or "").replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Snapshot Pairing",
            "",
            "| Poll | Sample elapsed | Snapshot | Snapshot elapsed | Delta | Bytes |",
            "| ---: | ---: | --- | ---: | ---: | ---: |",
        ]
    )
    for row in list(report.get("snapshot_pairs") or []):
        lines.append(
            "| {poll} | {sample_elapsed} | `{snapshot}` | {snapshot_elapsed} | {delta} | {size} |".format(
                poll=row.get("poll_index", ""),
                sample_elapsed=row.get("sample_elapsed_sec", ""),
                snapshot=row.get("snapshot", ""),
                snapshot_elapsed=row.get("snapshot_elapsed_sec", ""),
                delta=row.get("delta_sec", ""),
                size=row.get("snapshot_bytes", ""),
            )
        )
    lines.extend(["", "## Notes", ""])
    for note in list(report.get("notes") or []):
        lines.append(f"- {note}")
    (output_dir / "g3_active_final_surface_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit existing G3 live proof for active final-surface observations.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-observations", type=int, default=2)
    parser.add_argument("--max-snapshot-delta-sec", type=float, default=0.001)
    args = parser.parse_args(argv)
    report = build_report(
        source_dir=Path(args.source_dir),
        output_dir=Path(args.output_dir),
        min_observations=args.min_observations,
        max_snapshot_delta_sec=args.max_snapshot_delta_sec,
    )
    write_report(report, Path(args.output_dir))
    print(
        "status={status} valid_active_final_observations={count} snapshot_pairs={pairs}".format(
            status=report.get("status"),
            count=report.get("valid_active_final_observation_count"),
            pairs=report.get("snapshot_pair_count"),
        )
    )
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
