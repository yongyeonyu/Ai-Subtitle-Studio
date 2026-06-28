#!/usr/bin/env python3
"""Freeze fixed-fixture cut-boundary QA target corrections from visual evidence."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.native_json import dumps_json_bytes
from tools.audit_cut_boundary_frame_semantics import DEFAULT_BLOCKED_RUNTIME_CHANGES


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_pair(text: str) -> tuple[int, int]:
    raw = str(text or "").strip()
    if "->" not in raw:
        return (0, 0)
    left, right = raw.split("->", 1)
    return (_as_int(left), _as_int(right))


def _pair_text(pair: tuple[int, int]) -> str:
    return f"{int(pair[0])}:{int(pair[1])}"


def _target_correction_row(window: dict[str, Any]) -> dict[str, Any]:
    original_target = _as_int(window.get("target_frame"))
    expected_pair = _parse_pair(str(window.get("expected_pair") or ""))
    strongest_pair = _parse_pair(str(window.get("strongest_pair") or ""))
    classification = str(window.get("classification") or "")
    convention_review = bool(window.get("label_or_boundary_convention_review_required"))
    strongest_detected = bool(window.get("strongest_detected"))
    detector_evidence_required = bool(window.get("detector_evidence_required"))
    if convention_review and strongest_detected and strongest_pair[1] > 0:
        corrected_target = strongest_pair[1]
        corrected_pair = strongest_pair
        status = "corrected_to_strongest_detected_boundary"
        reason = "contact_sheet_strongest_detected_neighbor"
    else:
        corrected_target = original_target
        corrected_pair = expected_pair
        status = "unchanged_detector_evidence_required" if detector_evidence_required else "unchanged"
        reason = "target_requires_detector_evidence" if detector_evidence_required else "target_already_matches_fixture_convention"
    return {
        "original_target_frame": original_target,
        "corrected_target_frame": corrected_target,
        "original_pair": f"{expected_pair[0]}->{expected_pair[1]}",
        "corrected_pair": f"{corrected_pair[0]}->{corrected_pair[1]}",
        "source_strongest_pair": f"{strongest_pair[0]}->{strongest_pair[1]}",
        "classification": classification,
        "correction_status": status,
        "correction_reason": reason,
        "target_changed": corrected_target != original_target,
        "detector_evidence_required": detector_evidence_required,
        "expected_mean_delta": _as_float((window.get("expected_pair_metrics") or {}).get("mean_abs_delta")),
        "strongest_mean_delta": _as_float((window.get("strongest_pair_metrics") or {}).get("mean_abs_delta")),
        "strongest_to_expected_mean_delta_ratio": _as_float(window.get("strongest_to_expected_mean_delta_ratio")),
    }


def build_fixture_target_correction_audit(
    fixture_convention_audit: dict[str, Any],
    *,
    source_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    rows = [
        _target_correction_row(window)
        for window in list(fixture_convention_audit.get("windows") or [])
        if isinstance(window, dict)
    ]
    corrected_targets = [int(row["corrected_target_frame"]) for row in rows]
    corrected_pairs = [_pair_text(_parse_pair(str(row.get("corrected_pair") or ""))) for row in rows]
    changed = [row for row in rows if row.get("target_changed")]
    blocked = list(fixture_convention_audit.get("blocked_runtime_changes") or [])
    for item in DEFAULT_BLOCKED_RUNTIME_CHANGES:
        if item not in blocked:
            blocked.append(item)
    manifest = {
        "schema": "ai_subtitle_studio.cut_boundary_fixture_target_correction.v1",
        "note": "Read-only audit. It converts fixture convention evidence into corrected QA target frames.",
        "source_fixture_convention_audit_path": str(source_path) if source_path else "",
        "source_schema": str(fixture_convention_audit.get("schema") or ""),
        "media_path": str(fixture_convention_audit.get("media_path") or ""),
        "target_correction_required": bool(changed),
        "target_correction_count": len(changed),
        "detector_evidence_required_count": sum(1 for row in rows if row.get("detector_evidence_required")),
        "corrected_target_frames": corrected_targets,
        "corrected_target_frames_csv": ",".join(str(frame) for frame in corrected_targets),
        "corrected_source_fps_pairs": corrected_pairs,
        "corrected_source_fps_pairs_csv": ",".join(corrected_pairs),
        "runtime_change_allowed": False,
        "qa_fixture_target_change_allowed": True,
        "blocked_runtime_changes": blocked,
        "windows": rows,
        "elapsed_sec": round(time.time() - started, 3),
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "cut_boundary_fixture_target_correction.json"
        md_path = output_dir / "cut_boundary_fixture_target_correction.md"
        json_path.write_bytes(dumps_json_bytes(manifest, indent=2, sort_keys=True, append_newline=True))
        manifest["artifact_path"] = str(json_path)
        _write_markdown(md_path, manifest)
    return manifest


def _write_markdown(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Cut Boundary Fixture Target Correction",
        "",
        f"- Target correction required: `{bool(manifest.get('target_correction_required'))}`",
        f"- Target correction count: `{manifest.get('target_correction_count')}`",
        f"- Detector evidence required count: `{manifest.get('detector_evidence_required_count')}`",
        f"- Corrected target frames: `{manifest.get('corrected_target_frames_csv')}`",
        f"- Corrected source-fps pairs: `{manifest.get('corrected_source_fps_pairs_csv')}`",
        f"- Runtime change allowed: `{bool(manifest.get('runtime_change_allowed'))}`",
        f"- QA fixture target change allowed: `{bool(manifest.get('qa_fixture_target_change_allowed'))}`",
        f"- Source convention audit: `{manifest.get('source_fixture_convention_audit_path')}`",
        "",
        "## Targets",
        "",
        "| Original | Corrected | Original pair | Corrected pair | Status | Ratio | Reason |",
        "| ---: | ---: | --- | --- | --- | ---: | --- |",
    ]
    for row in list(manifest.get("windows") or []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| {orig} | {corr} | {orig_pair} | {corr_pair} | {status} | {ratio} | {reason} |".format(
                orig=row.get("original_target_frame"),
                corr=row.get("corrected_target_frame"),
                orig_pair=row.get("original_pair"),
                corr_pair=row.get("corrected_pair"),
                status=row.get("correction_status"),
                ratio=row.get("strongest_to_expected_mean_delta_ratio"),
                reason=row.get("correction_reason"),
            )
        )
    lines.extend(["", "## Guardrails", ""])
    for item in list(manifest.get("blocked_runtime_changes") or []):
        lines.append(f"- Do not apply `{item}` from this audit alone.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build corrected fixed-fixture target frames from convention evidence.")
    parser.add_argument("fixture_convention_audit_json", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_path = args.fixture_convention_audit_json
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    manifest = build_fixture_target_correction_audit(payload, source_path=source_path, output_dir=args.output_dir)
    print(dumps_json_bytes(manifest, indent=2, sort_keys=True).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
