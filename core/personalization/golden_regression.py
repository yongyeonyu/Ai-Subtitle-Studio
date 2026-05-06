from __future__ import annotations

import json
import re
import argparse
from pathlib import Path
from typing import Any

from core.engine.llm_correction_guard import contains_timecode
from core.engine.subtitle_accuracy_pipeline import (
    subtitle_accuracy_metrics,
    subtitle_decision_explanations,
)
from core.personalization.lora_trial_scoring import (
    candidate_segments_to_rows,
    score_candidate_rows,
)
from core.srt_parser import parse_srt


GOLDEN_REGRESSION_SCHEMA = "ai_subtitle_studio.golden_subtitle_regression.v1"
GOLDEN_SUITE_MANIFEST_SCHEMA = "ai_subtitle_studio.golden_subtitle_suite_manifest.v1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN_SUITE_PATH = PROJECT_ROOT / "dataset" / "golden_subtitle_suite.json"
DEFAULT_GOLDEN_REPORT_PATH = PROJECT_ROOT / "output" / "golden_subtitle_regression_report.json"

DEFAULT_GOLDEN_THRESHOLDS = {
    "final_score_min": 88.0,
    "character_error_rate_max": 0.08,
    "eojeol_error_rate_max": 0.16,
    "timing_overlap_score_min": 0.82,
    "line_break_match_score_min": 0.70,
    "segment_split_merge_f1_min": 0.80,
    "cps_violation_rate_max": 0.10,
    "hallucination_proxy_rate_max": 0.02,
}

_HALLUCINATION_PHRASES = (
    "Thank you for watching",
    "Korean conversation",
    "subtitle",
    "transcription",
    "자막 생성",
    "번역 중",
    "처리 중",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def _segments_from_path(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    return [dict(row) for row in parse_srt(str(path)) if isinstance(row, dict)]


def _rows_from_segments(
    segments: list[dict[str, Any]],
    *,
    media_id: str = "",
    media_path: str = "",
    subtitle_path: str = "",
) -> list[dict[str, Any]]:
    return candidate_segments_to_rows(
        [dict(row) for row in list(segments or []) if isinstance(row, dict) and not row.get("is_gap")],
        media_id=media_id,
        media_path=media_path,
        subtitle_path=subtitle_path,
    )


def _merge_thresholds(thresholds: dict[str, Any] | None = None) -> dict[str, float]:
    merged = dict(DEFAULT_GOLDEN_THRESHOLDS)
    for key, value in dict(thresholds or {}).items():
        if key in merged:
            merged[key] = _safe_float(value, float(merged[key]))
    return {key: float(value) for key, value in merged.items()}


def _threshold_failures(metrics: dict[str, Any], thresholds: dict[str, float]) -> list[dict[str, Any]]:
    checks = (
        ("final_score", ">=", "final_score_min"),
        ("character_error_rate", "<=", "character_error_rate_max"),
        ("eojeol_error_rate", "<=", "eojeol_error_rate_max"),
        ("timing_overlap_score", ">=", "timing_overlap_score_min"),
        ("line_break_match_score", ">=", "line_break_match_score_min"),
        ("segment_split_merge_f1", ">=", "segment_split_merge_f1_min"),
        ("cps_violation_rate", "<=", "cps_violation_rate_max"),
        ("hallucination_proxy_rate", "<=", "hallucination_proxy_rate_max"),
    )
    failures: list[dict[str, Any]] = []
    for metric_key, op, threshold_key in checks:
        value = _safe_float(metrics.get(metric_key), 0.0)
        threshold = float(thresholds[threshold_key])
        ok = value >= threshold if op == ">=" else value <= threshold
        if not ok:
            failures.append(
                {
                    "metric": metric_key,
                    "actual": round(value, 4),
                    "expected": f"{op} {threshold}",
                }
            )
    return failures


def _hallucination_proxy_rate(
    truth_segments: list[dict[str, Any]],
    candidate_segments: list[dict[str, Any]],
) -> float:
    truth_all = "\n".join(str(row.get("text") or "") for row in truth_segments)
    truth_compact = _compact_text(truth_all)
    risky = 0
    total = 0
    for row in list(candidate_segments or []):
        text = str(row.get("text") or "")
        if not text.strip():
            continue
        total += 1
        compact = _compact_text(text)
        phrase_added = any(phrase in text and phrase not in truth_all for phrase in _HALLUCINATION_PHRASES)
        timecode_added = contains_timecode(text)
        unsupported_long = bool(compact and truth_compact and compact not in truth_compact and len(compact) > max(18, int(len(truth_compact) * 0.35)))
        if phrase_added or timecode_added or unsupported_long:
            risky += 1
    return risky / max(1, total)


def evaluate_golden_case(
    *,
    truth_srt_path: str | Path | None = None,
    candidate_srt_path: str | Path | None = None,
    truth_segments: list[dict[str, Any]] | None = None,
    candidate_segments: list[dict[str, Any]] | None = None,
    case_id: str = "",
    media_path: str = "",
    settings: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one generated subtitle output against a ground-truth SRT."""
    truth = list(truth_segments or _segments_from_path(truth_srt_path))
    candidate = list(candidate_segments or _segments_from_path(candidate_srt_path))
    media_id = str(case_id or Path(str(media_path or truth_srt_path or candidate_srt_path or "golden")).stem)
    truth_rows = _rows_from_segments(
        truth,
        media_id=media_id,
        media_path=media_path,
        subtitle_path=str(truth_srt_path or ""),
    )
    candidate_rows = _rows_from_segments(
        candidate,
        media_id=media_id,
        media_path=media_path,
        subtitle_path=str(candidate_srt_path or ""),
    )
    score_metrics = score_candidate_rows(truth_rows, candidate_rows)
    runtime_metrics = subtitle_accuracy_metrics(candidate, settings or {})
    total = max(1, int(runtime_metrics.get("total_segments", len(candidate)) or len(candidate) or 1))
    cps_violation_rate = float(runtime_metrics.get("high_cps_segments", 0) or 0) / total
    hallucination_rate = _hallucination_proxy_rate(truth, candidate)
    metrics = {
        **score_metrics,
        "cer": score_metrics.get("character_error_rate"),
        "wer": score_metrics.get("eojeol_error_rate"),
        "timing_iou": score_metrics.get("timing_overlap_score"),
        "line_break_f1": score_metrics.get("line_break_match_score"),
        "cps_violation_rate": round(cps_violation_rate, 4),
        "hallucination_proxy_rate": round(hallucination_rate, 4),
        "user_edit_proxy_cer": score_metrics.get("character_error_rate"),
    }
    merged_thresholds = _merge_thresholds(thresholds)
    failures = _threshold_failures(metrics, merged_thresholds)
    return {
        "schema": GOLDEN_REGRESSION_SCHEMA,
        "case_id": media_id,
        "media_path": str(media_path or ""),
        "truth_srt_path": str(truth_srt_path or ""),
        "candidate_srt_path": str(candidate_srt_path or ""),
        "truth_segments": len(truth),
        "candidate_segments": len(candidate),
        "passed": not failures,
        "failures": failures,
        "thresholds": merged_thresholds,
        "metrics": metrics,
        "runtime_metrics": runtime_metrics,
        "decision_explanations": subtitle_decision_explanations(candidate),
    }


def evaluate_golden_suite(
    cases: list[dict[str, Any]],
    *,
    settings: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate multiple golden subtitle cases and return an aggregate report."""
    results = [
        evaluate_golden_case(
            truth_srt_path=case.get("truth_srt_path"),
            candidate_srt_path=case.get("candidate_srt_path"),
            truth_segments=case.get("truth_segments"),
            candidate_segments=case.get("candidate_segments"),
            case_id=str(case.get("case_id") or ""),
            media_path=str(case.get("media_path") or ""),
            settings=dict(case.get("settings") or settings or {}),
            thresholds=dict(case.get("thresholds") or thresholds or {}),
        )
        for case in list(cases or [])
        if isinstance(case, dict)
    ]
    total = len(results)
    passed = sum(1 for item in results if item.get("passed"))
    average_score = sum(_safe_float(item.get("metrics", {}).get("final_score"), 0.0) for item in results) / max(1, total)
    return {
        "schema": GOLDEN_REGRESSION_SCHEMA,
        "task": "golden_suite",
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "passed": total > 0 and passed == total,
        "average_final_score": round(average_score, 4),
        "cases": results,
    }


def default_golden_suite_manifest() -> dict[str, Any]:
    return {
        "schema": GOLDEN_SUITE_MANIFEST_SCHEMA,
        "description": "Golden subtitle regression suite. Add case entries with truth_srt_path and candidate_srt_path.",
        "thresholds": dict(DEFAULT_GOLDEN_THRESHOLDS),
        "pre_release_gate": {
            "enabled": False,
            "fail_on_regression": True,
        },
        "cases": [],
    }


def load_golden_suite_manifest(path: str | Path | None = None) -> dict[str, Any]:
    manifest_path = Path(path or DEFAULT_GOLDEN_SUITE_PATH)
    if not manifest_path.exists():
        return default_golden_suite_manifest()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return default_golden_suite_manifest()
    if not isinstance(payload, dict):
        return default_golden_suite_manifest()
    merged = default_golden_suite_manifest()
    merged.update(payload)
    thresholds = dict(DEFAULT_GOLDEN_THRESHOLDS)
    thresholds.update(dict(payload.get("thresholds") or {}))
    merged["thresholds"] = thresholds
    merged["cases"] = [dict(item) for item in list(payload.get("cases") or []) if isinstance(item, dict)]
    return merged


def evaluate_golden_suite_manifest(
    manifest_path: str | Path | None = None,
    *,
    output_path: str | Path | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = load_golden_suite_manifest(manifest_path)
    report = evaluate_golden_suite(
        list(manifest.get("cases") or []),
        settings=settings or {},
        thresholds=dict(manifest.get("thresholds") or {}),
    )
    report["manifest_schema"] = manifest.get("schema")
    report["manifest_path"] = str(Path(manifest_path or DEFAULT_GOLDEN_SUITE_PATH))
    report["pre_release_gate"] = dict(manifest.get("pre_release_gate") or {})
    target = Path(output_path or DEFAULT_GOLDEN_REPORT_PATH)
    report["report_path"] = write_golden_report(report, target)
    return report


def write_golden_report(report: dict[str, Any], output_path: str | Path) -> str:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def golden_regression_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate AI Subtitle Studio golden subtitle regression cases.")
    parser.add_argument("--manifest", default=str(DEFAULT_GOLDEN_SUITE_PATH), help="Path to golden suite manifest JSON.")
    parser.add_argument("--output", default=str(DEFAULT_GOLDEN_REPORT_PATH), help="Path to write regression report JSON.")
    parser.add_argument("--fail-on-regression", action="store_true", help="Return a non-zero exit code when thresholds fail.")
    args = parser.parse_args(argv)
    report = evaluate_golden_suite_manifest(args.manifest, output_path=args.output)
    print(
        f"Golden subtitle regression: {report.get('passed_cases', 0)}/{report.get('total_cases', 0)} passed, "
        f"average_score={report.get('average_final_score', 0.0)}"
    )
    print(f"Report: {report.get('report_path')}")
    if args.fail_on_regression and not report.get("passed"):
        return 1
    return 0


__all__ = [
    "DEFAULT_GOLDEN_THRESHOLDS",
    "DEFAULT_GOLDEN_REPORT_PATH",
    "DEFAULT_GOLDEN_SUITE_PATH",
    "GOLDEN_REGRESSION_SCHEMA",
    "GOLDEN_SUITE_MANIFEST_SCHEMA",
    "default_golden_suite_manifest",
    "evaluate_golden_case",
    "evaluate_golden_suite",
    "evaluate_golden_suite_manifest",
    "golden_regression_cli",
    "load_golden_suite_manifest",
    "write_golden_report",
]


if __name__ == "__main__":
    raise SystemExit(golden_regression_cli())
