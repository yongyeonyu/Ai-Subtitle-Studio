#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.native_swift_subtitle_assembly import (  # noqa: E402
    ASSEMBLED_VARIANT_NAME,
    QUALITY_BASELINE_VARIANTS,
    evaluate_subtitle_assembly_quality_gate,
)
from core.optimization.quality_gate import BackendQualityGate, subtitle_quality_gate  # noqa: E402


PREFERRED_BASELINES = (
    "phase3_selective_stt2_llm",
    "phase1_serial_selective_stt2",
    "stt_original_selective_no_llm",
    "mode_high",
    "mode_auto",
    "mode_fast",
)
BEST_MODE_BASELINE_ALIASES = {
    "best-mode",
    "best_mode",
    "best-fast-auto-high",
    "best_fast_auto_high",
    "fast-auto-high",
    "fast_auto_high",
}


def _auto_baseline_name(rows: list[dict[str, Any]]) -> str:
    by_name = {str(row.get("name") or ""): row for row in rows if not row.get("error")}
    for name in PREFERRED_BASELINES:
        if name in by_name:
            return name
    for row in rows:
        if not row.get("error"):
            return str(row.get("name") or "")
    return ""


def _best_mode_baseline_name(rows: list[dict[str, Any]]) -> str:
    candidates = [
        row
        for row in rows
        if not row.get("error") and str(row.get("name") or "") in QUALITY_BASELINE_VARIANTS
    ]
    if not candidates:
        return _auto_baseline_name(rows)
    return str(max(candidates, key=_quality_score).get("name") or "")


def _quality_score(row: dict[str, Any]) -> float:
    try:
        return float(dict(row.get("quality") or {}).get("quality_score", 0.0) or 0.0)
    except Exception:
        return 0.0


def _primary_speed_score(row: dict[str, Any]) -> float:
    for key in ("primary_speed_score", "quality_speed_score", "readability_speed_score"):
        try:
            return float(row.get(key, 0.0) or 0.0)
        except Exception:
            continue
    return _quality_score(row)


def apply_gate(payload: dict[str, Any], *, baseline_variant: str = "auto") -> dict[str, Any]:
    rows = [dict(row) for row in list(payload.get("ranked_results") or payload.get("results") or []) if isinstance(row, dict)]
    requested_baseline = str(baseline_variant or "auto").strip()
    requested_key = requested_baseline.lower()
    strict_best_mode_floor = requested_key in BEST_MODE_BASELINE_ALIASES
    if requested_key == "auto":
        baseline_name = _auto_baseline_name(rows)
    elif strict_best_mode_floor:
        baseline_name = _best_mode_baseline_name(rows)
    else:
        baseline_name = requested_baseline
    if not baseline_name:
        raise RuntimeError("no usable benchmark row for quality gate baseline")
    by_name = {str(row.get("name") or ""): row for row in rows}
    baseline = by_name.get(baseline_name)
    if baseline is None:
        raise RuntimeError(f"unknown quality gate baseline variant: {baseline_name}")

    strict_gate = BackendQualityGate(max_quality_score_drop=0.0) if strict_best_mode_floor else None
    swift_assembly_gate = (
        evaluate_subtitle_assembly_quality_gate(rows)
        if ASSEMBLED_VARIANT_NAME in by_name
        else None
    )
    gated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        # Keep final selection quality-first: fast candidates must preserve the selective baseline.
        gate = subtitle_quality_gate(baseline, item, gate=strict_gate)
        if str(item.get("name") or "") == baseline_name:
            gate["baseline"] = True
        if str(item.get("name") or "") == ASSEMBLED_VARIANT_NAME and swift_assembly_gate:
            item["swift_assembly_quality_gate"] = swift_assembly_gate
            if not bool(swift_assembly_gate.get("passed")):
                gate["passed"] = False
                reasons = list(gate.get("reasons") or [])
                reasons.append(f"swift_assembly_quality_gate:{swift_assembly_gate.get('reason')}")
                gate["reasons"] = reasons
        item["quality_gate"] = gate
        item["quality_gate_passed"] = bool(gate.get("passed"))
        gated.append(item)

    ranked = sorted(
        gated,
        key=lambda row: (
            bool(row.get("quality_gate_passed")),
            _primary_speed_score(row),
            _quality_score(row),
        ),
        reverse=True,
    )
    for index, row in enumerate(ranked, start=1):
        row["quality_gate_rank"] = index

    return {
        "schema": "ai_subtitle_studio.subtitle_benchmark_quality_gate.v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_schema": payload.get("schema"),
        "source_created_at": payload.get("created_at"),
        "media": payload.get("media"),
        "reference_srt": payload.get("reference_srt"),
        "suite": payload.get("suite"),
        "baseline_variant": baseline_name,
        "baseline_variant_request": requested_baseline,
        "strict_best_mode_floor": strict_best_mode_floor,
        "swift_assembly_quality_gate": swift_assembly_gate,
        "ranked_results": ranked,
    }


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Subtitle Benchmark Quality Gate",
        "",
        f"- Media: `{payload.get('media')}`",
        f"- Reference: `{payload.get('reference_srt')}`",
        f"- Baseline variant: `{payload.get('baseline_variant')}`",
        f"- Strict Fast/Auto/High floor: `{payload.get('strict_best_mode_floor')}`",
        f"- Created: {payload.get('created_at')}",
        "",
        "| Gate Rank | Variant | Gate | Time(s) | Quality | Readability | Segs | Reasons |",
        "|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for row in list(payload.get("ranked_results") or []):
        gate = dict(row.get("quality_gate") or {})
        quality = dict(row.get("quality") or {})
        readability = dict(row.get("readability") or {})
        label = "baseline" if gate.get("baseline") else ("pass" if gate.get("passed") else "fail")
        reasons = ",".join(str(item) for item in list(gate.get("reasons") or []))
        lines.append(
            "| {rank} | `{name}` | {gate} | {elapsed:.3f} | {quality:.3f} | {readability:.3f} | {segments} | {reasons} |".format(
                rank=row.get("quality_gate_rank", ""),
                name=row.get("name", ""),
                gate=label,
                elapsed=float(row.get("elapsed_sec", 0.0) or 0.0),
                quality=float(quality.get("quality_score", 0.0) or 0.0),
                readability=float(readability.get("readability_score", 0.0) or 0.0),
                segments=row.get("final_segments", ""),
                reasons=reasons.replace("|", "/"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a subtitle quality-preservation gate to benchmark_results.json.")
    parser.add_argument("benchmark_json", help="Path to benchmark_results.json from benchmark_subtitle_pipeline_variants.py")
    parser.add_argument("--baseline-variant", default="auto")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    source = Path(args.benchmark_json).expanduser()
    payload = json.loads(source.read_text(encoding="utf-8"))
    gated = apply_gate(payload, baseline_variant=str(args.baseline_variant or "auto"))
    output_dir = Path(args.output_dir).expanduser() if str(args.output_dir or "").strip() else source.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "benchmark_quality_gate.json"
    md_path = output_dir / "benchmark_quality_gate.md"
    json_path.write_text(json.dumps(gated, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(gated, md_path)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "baseline": gated["baseline_variant"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
