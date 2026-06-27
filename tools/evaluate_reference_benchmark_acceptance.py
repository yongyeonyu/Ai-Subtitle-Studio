#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _best_row(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in list(payload.get("ranked_results") or payload.get("results") or []) if isinstance(row, dict)]
    if not rows:
        return {}
    return dict(rows[0])


def _probe_media_duration_sec(path_text: str) -> float:
    path = Path(str(path_text or "")).expanduser()
    if not path.exists():
        return 0.0
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return max(0.0, float(str(out).strip() or 0.0))
    except Exception:
        return 0.0


def _duration_bound_from_payload(
    payload: dict[str, Any],
    *,
    media_duration_sec: float = 0.0,
    eof_slack_sec: float = 1.0,
) -> float:
    start_sec = _to_float(payload.get("start_sec"), 0.0)
    requested_duration = _to_float(payload.get("duration_sec"), 0.0)
    if requested_duration <= 0.0:
        end_sec = _to_float(payload.get("end_sec"), 0.0)
        if end_sec > start_sec:
            requested_duration = end_sec - start_sec
    media_remaining = max(0.0, float(media_duration_sec or 0.0) - start_sec)
    if requested_duration > 0.0 and media_remaining > 0.0 and media_remaining <= requested_duration + float(eof_slack_sec):
        return media_remaining
    if requested_duration > 0.0:
        return requested_duration
    return media_remaining


def evaluate_reference_benchmark_acceptance(
    payload: dict[str, Any],
    *,
    min_quality_score: float = 70.0,
    min_text_score: float = 70.0,
    max_timing_mae_sec: float = 2.5,
    max_global_active_segments: int = 1,
    duration_bound_sec: float = 0.0,
    max_final_end_slack_sec: float = 0.25,
    min_segment_duration_sec: float = 0.3,
    max_segment_duration_sec: float = 12.0,
) -> dict[str, Any]:
    row = _best_row(payload)
    quality = dict(row.get("quality") or {})
    final_summary = dict(row.get("native_segments_summary") or {})
    global_summary = dict(row.get("native_global_canvas_summary") or {})

    quality_score = _to_float(quality.get("quality_score"))
    text_score = _to_float(quality.get("text_score"))
    timing_mae = _to_float(quality.get("timing_mae_sec"), default=999.0)
    final_invalid = _to_int(final_summary.get("invalid_duration_count"))
    final_non_monotonic = _to_int(final_summary.get("non_monotonic_count"))
    final_overlap = _to_int(final_summary.get("overlap_count"))
    final_segment_count = _to_int(final_summary.get("segment_count"), _to_int(row.get("final_segments")))
    final_last_end = _to_float(final_summary.get("last_end"))
    final_min_duration = _to_float(final_summary.get("min_segment_duration_sec"))
    final_max_duration = _to_float(final_summary.get("max_segment_duration_sec"))
    final_short_count = _to_int(final_summary.get("short_segment_count"))
    final_long_count = _to_int(final_summary.get("long_segment_count"))
    global_max_active = _to_int(global_summary.get("max_active_segments"))
    duration_bound = float(duration_bound_sec or _duration_bound_from_payload(payload))

    reasons: list[str] = []
    if not row:
        reasons.append("missing_benchmark_row")
    if str(row.get("error") or "").strip():
        reasons.append("benchmark_row_error")
    if quality_score < float(min_quality_score):
        reasons.append("quality_score_below_floor")
    if text_score < float(min_text_score):
        reasons.append("text_score_below_floor")
    if timing_mae > float(max_timing_mae_sec):
        reasons.append("timing_mae_above_ceiling")
    if final_invalid != 0:
        reasons.append("final_invalid_duration_nonzero")
    if final_non_monotonic != 0:
        reasons.append("final_non_monotonic_nonzero")
    if final_overlap != 0:
        reasons.append("final_overlap_nonzero")
    if final_summary.get("stable_for_save_reopen") is not True:
        reasons.append("final_not_stable_for_save_reopen")
    if duration_bound > 0.0 and final_last_end > duration_bound + float(max_final_end_slack_sec):
        reasons.append("final_last_end_beyond_duration_bound")
    if final_segment_count > 0 and final_min_duration > 0.0 and final_min_duration < float(min_segment_duration_sec):
        reasons.append("final_min_segment_duration_below_floor")
    if final_short_count > 0:
        reasons.append("final_short_segment_count_nonzero")
    if final_segment_count > 0 and final_max_duration > float(max_segment_duration_sec):
        reasons.append("final_max_segment_duration_above_ceiling")
    if final_long_count > 0:
        reasons.append("final_long_segment_count_nonzero")
    if global_max_active > int(max_global_active_segments):
        reasons.append("global_canvas_max_active_above_ceiling")
    if global_summary.get("stable_for_global_canvas") is not True:
        reasons.append("global_canvas_not_stable")

    accepted = not reasons
    return {
        "schema": "ai_subtitle_studio.reference_benchmark_acceptance.v1",
        "accepted": accepted,
        "reasons": reasons,
        "thresholds": {
            "min_quality_score": float(min_quality_score),
            "min_text_score": float(min_text_score),
            "max_timing_mae_sec": float(max_timing_mae_sec),
            "max_global_active_segments": int(max_global_active_segments),
            "duration_bound_sec": round(float(duration_bound), 6),
            "max_final_end_slack_sec": float(max_final_end_slack_sec),
            "min_segment_duration_sec": float(min_segment_duration_sec),
            "max_segment_duration_sec": float(max_segment_duration_sec),
        },
        "benchmark": {
            "name": row.get("name"),
            "elapsed_sec": row.get("elapsed_sec"),
            "raw_segments": row.get("raw_segments"),
            "final_segments": row.get("final_segments"),
            "reference_segments": quality.get("reference_segments"),
            "quality_score": quality_score,
            "text_score": text_score,
            "timing_mae_sec": timing_mae,
            "final_invalid_duration_count": final_invalid,
            "final_non_monotonic_count": final_non_monotonic,
            "final_overlap_count": final_overlap,
            "final_stable_for_save_reopen": final_summary.get("stable_for_save_reopen"),
            "final_last_end_sec": final_last_end,
            "final_min_segment_duration_sec": final_min_duration,
            "final_max_segment_duration_sec": final_max_duration,
            "final_short_segment_count": final_short_count,
            "final_long_segment_count": final_long_count,
            "global_canvas_max_active_segments": global_max_active,
            "global_canvas_stable": global_summary.get("stable_for_global_canvas"),
        },
    }


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    benchmark = dict(payload.get("benchmark") or {})
    thresholds = dict(payload.get("thresholds") or {})
    lines = [
        "# Reference Benchmark Acceptance",
        "",
        f"- Accepted: `{bool(payload.get('accepted'))}`",
        f"- Reasons: `{', '.join(str(item) for item in list(payload.get('reasons') or [])) or 'none'}`",
        f"- Variant: `{benchmark.get('name')}`",
        f"- Elapsed: `{benchmark.get('elapsed_sec')}`",
        f"- Raw/final/reference: `{benchmark.get('raw_segments')}/{benchmark.get('final_segments')}/{benchmark.get('reference_segments')}`",
        f"- Quality score: `{benchmark.get('quality_score')}`",
        f"- Text score: `{benchmark.get('text_score')}`",
        f"- Timing MAE: `{benchmark.get('timing_mae_sec')}`",
        f"- Final invalid/non-monotonic/overlap: `{benchmark.get('final_invalid_duration_count')}/{benchmark.get('final_non_monotonic_count')}/{benchmark.get('final_overlap_count')}`",
        f"- Final stable: `{benchmark.get('final_stable_for_save_reopen')}`",
        f"- Final last end / duration bound: `{benchmark.get('final_last_end_sec')}/{thresholds.get('duration_bound_sec')}`",
        f"- Final min/max segment duration: `{benchmark.get('final_min_segment_duration_sec')}/{benchmark.get('final_max_segment_duration_sec')}`",
        f"- Final short/long segment counts: `{benchmark.get('final_short_segment_count')}/{benchmark.get('final_long_segment_count')}`",
        f"- Global max active: `{benchmark.get('global_canvas_max_active_segments')}`",
        f"- Global stable: `{benchmark.get('global_canvas_stable')}`",
        "",
        "## Thresholds",
        "",
        f"- Min quality score: `{thresholds.get('min_quality_score')}`",
        f"- Min text score: `{thresholds.get('min_text_score')}`",
        f"- Max timing MAE: `{thresholds.get('max_timing_mae_sec')}`",
        f"- Max global active segments: `{thresholds.get('max_global_active_segments')}`",
        f"- Duration bound: `{thresholds.get('duration_bound_sec')}`",
        f"- Max final end slack: `{thresholds.get('max_final_end_slack_sec')}`",
        f"- Min segment duration: `{thresholds.get('min_segment_duration_sec')}`",
        f"- Max segment duration: `{thresholds.get('max_segment_duration_sec')}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a reference-scored subtitle benchmark as accepted or rejected.")
    parser.add_argument("benchmark_json")
    parser.add_argument("--min-quality-score", type=float, default=70.0)
    parser.add_argument("--min-text-score", type=float, default=70.0)
    parser.add_argument("--max-timing-mae-sec", type=float, default=2.5)
    parser.add_argument("--max-global-active-segments", type=int, default=1)
    parser.add_argument("--media-duration-sec", type=float, default=0.0)
    parser.add_argument("--max-final-end-slack-sec", type=float, default=0.25)
    parser.add_argument("--min-segment-duration-sec", type=float, default=0.3)
    parser.add_argument("--max-segment-duration-sec", type=float, default=12.0)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    source = Path(args.benchmark_json).expanduser()
    payload = json.loads(source.read_text(encoding="utf-8"))
    media_duration_sec = float(args.media_duration_sec or 0.0)
    if media_duration_sec <= 0.0:
        media_duration_sec = _probe_media_duration_sec(str(payload.get("media") or ""))
    duration_bound_sec = _duration_bound_from_payload(payload, media_duration_sec=media_duration_sec)
    report = evaluate_reference_benchmark_acceptance(
        payload,
        min_quality_score=float(args.min_quality_score),
        min_text_score=float(args.min_text_score),
        max_timing_mae_sec=float(args.max_timing_mae_sec),
        max_global_active_segments=int(args.max_global_active_segments),
        duration_bound_sec=duration_bound_sec,
        max_final_end_slack_sec=float(args.max_final_end_slack_sec),
        min_segment_duration_sec=float(args.min_segment_duration_sec),
        max_segment_duration_sec=float(args.max_segment_duration_sec),
    )
    output_dir = Path(args.output_dir).expanduser() if str(args.output_dir or "").strip() else source.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "reference_benchmark_acceptance.json"
    md_path = output_dir / "reference_benchmark_acceptance.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(report, md_path)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "accepted": report["accepted"]}, ensure_ascii=False))
    return 0 if bool(report.get("accepted")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
