from __future__ import annotations

from typing import Any

from core.personalization.lora_store_common import read_jsonl, store_paths


DEEP_RUNTIME_ADAPTATION_SCHEMA = "ai_subtitle_studio.deep_runtime_adaptation.v1"


def _safe_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔"}
    return bool(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(round(float(value)))
    except Exception:
        return int(default)


def _clamp_float(value: float, low: float, high: float) -> float:
    return max(float(low), min(float(high), float(value)))


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(int(low), min(int(high), int(value)))


def _recent_deep_events(settings: dict[str, Any], store_dir: str | None = None) -> list[dict[str, Any]]:
    lookback = _clamp_int(_safe_int(settings.get("deep_runtime_adaptation_lookback_events"), 256), 16, 5000)
    try:
        rows = read_jsonl(store_paths(store_dir)["deep_policy_events"])
    except Exception:
        return []
    return [dict(row) for row in rows[-lookback:] if isinstance(row, dict)]


def summarize_deep_runtime_events(rows: list[dict[str, Any]]) -> dict[str, Any]:
    quality_scores: list[float] = []
    quality_bad = 0
    high_cps = 0
    llm_rollbacks = 0
    llm_verifier_rejects = 0
    llm_gate_skips = 0
    stt_lattice_hard = 0
    hard_cases = 0
    context_events = 0
    context_repeat = 0
    context_overlap = 0
    context_timing_order = 0
    context_cps_jump = 0
    context_hallucination = 0
    lora_style_events = 0
    lora_style_drift = 0
    lora_style_excluded = 0
    lora_style_length = 0
    lora_style_cps = 0
    bundle_events = 0
    bundle_max = 0
    bundle_cut = 0
    bundle_short = 0
    bundle_long = 0

    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        event_type = str(row.get("event_type") or "")
        decision = dict(row.get("decision") or {})
        features = dict(row.get("features") or {})
        row_high_cps = False
        if row.get("hard_case"):
            hard_cases += 1
        if event_type == "quality_self_review":
            score = decision.get("confidence_score")
            if isinstance(score, (int, float)):
                quality_scores.append(float(score))
            label = str(decision.get("confidence_label") or "").lower()
            flags = {str(flag) for flag in list(decision.get("flags") or [])}
            if label in {"red", "gray"}:
                quality_bad += 1
            if "high_cps" in flags:
                row_high_cps = True
        elif event_type == "llm_rollback":
            llm_rollbacks += 1
        elif event_type == "llm_verifier" and decision.get("accepted") is False:
            llm_verifier_rejects += 1
        elif event_type == "llm_gate" and decision.get("call_llm") is False:
            llm_gate_skips += 1
        elif event_type == "stt_lattice" and row.get("hard_case"):
            stt_lattice_hard += 1
        elif event_type == "context_consistency":
            context_events += 1
            flags = {str(flag) for flag in list(decision.get("flags") or [])}
            if flags & {"repeat_previous", "near_duplicate_previous"}:
                context_repeat += 1
            if "overlap_previous" in flags:
                context_overlap += 1
            if "timing_order_violation" in flags:
                context_timing_order += 1
            if "cps_jump" in flags:
                context_cps_jump += 1
                row_high_cps = True
            if "hallucination_phrase" in flags:
                context_hallucination += 1
        elif event_type == "hard_case_sample":
            reasons = {str(reason) for reason in list(decision.get("reasons") or [])}
            if "context_consistency_risk" in reasons:
                context_events += 1
            if "context_repair_applied" in reasons:
                context_events += 1
        elif event_type == "context_repair" and decision.get("applied"):
            context_events += 1
            if _safe_int(decision.get("dropped_repeats"), 0) > 0:
                context_repeat += 1
            if _safe_int(decision.get("shifted_starts"), 0) > 0:
                context_overlap += 1
            if _safe_int(decision.get("extended_cps_segments"), 0) > 0:
                context_cps_jump += 1
            if _safe_int(decision.get("dropped_hallucinations"), 0) > 0:
                context_hallucination += 1
        elif event_type == "lora_style_consistency":
            lora_style_events += 1
            flags = {str(flag) for flag in list(decision.get("flags") or [])}
            if flags or _safe_float(decision.get("score"), 100.0) < 86.0:
                lora_style_drift += 1
            if "excluded_phrase" in flags:
                lora_style_excluded += 1
            if "style_length_drift" in flags or "style_line_drift" in flags:
                lora_style_length += 1
            if "style_cps_drift" in flags:
                lora_style_cps += 1
        elif event_type == "subtitle_bundle_policy":
            bundle_events += 1
            reason = str(decision.get("reason") or "")
            duration = _safe_float(decision.get("duration_sec"), 0.0)
            target = max(1.0, _safe_float(decision.get("target_sec"), 180.0))
            if reason == "max_sec" or duration > target * 1.6:
                bundle_max += 1
                bundle_long += 1
            if reason in {"confirmed_cut", "provisional_cut"}:
                bundle_cut += 1
            if 0.0 < duration < target * 0.35:
                bundle_short += 1
        if _safe_float(features.get("cps"), 0.0) > _safe_float(features.get("max_cps_setting"), 12.0) * 1.25:
            row_high_cps = True
        if row_high_cps:
            high_cps += 1

    total = max(1, len(rows or []))
    quality_total = max(1, sum(1 for row in rows if str(row.get("event_type") or "") == "quality_self_review"))
    avg_quality = round(sum(quality_scores) / max(1, len(quality_scores)), 4) if quality_scores else None
    return {
        "schema": DEEP_RUNTIME_ADAPTATION_SCHEMA,
        "event_count": len(rows or []),
        "quality_event_count": quality_total if quality_scores or quality_bad else 0,
        "avg_quality_score": avg_quality,
        "bad_quality_ratio": round(quality_bad / quality_total, 4) if quality_total else 0.0,
        "high_cps_ratio": round(high_cps / total, 4),
        "llm_rollback_ratio": round((llm_rollbacks + llm_verifier_rejects) / total, 4),
        "llm_gate_skip_ratio": round(llm_gate_skips / total, 4),
        "stt_lattice_hard_ratio": round(stt_lattice_hard / total, 4),
        "hard_case_ratio": round(hard_cases / total, 4),
        "context_risk_ratio": round(context_events / total, 4),
        "context_repeat_ratio": round(context_repeat / total, 4),
        "context_overlap_ratio": round(context_overlap / total, 4),
        "context_timing_order_ratio": round(context_timing_order / total, 4),
        "context_cps_jump_ratio": round(context_cps_jump / total, 4),
        "context_hallucination_ratio": round(context_hallucination / total, 4),
        "lora_style_risk_ratio": round(lora_style_drift / total, 4),
        "lora_style_excluded_ratio": round(lora_style_excluded / total, 4),
        "lora_style_length_ratio": round(lora_style_length / total, 4),
        "lora_style_cps_ratio": round(lora_style_cps / total, 4),
        "subtitle_bundle_max_ratio": round(bundle_max / total, 4),
        "subtitle_bundle_cut_ratio": round(bundle_cut / total, 4),
        "subtitle_bundle_short_ratio": round(bundle_short / total, 4),
        "subtitle_bundle_long_ratio": round(bundle_long / total, 4),
        "counts": {
            "quality_bad": quality_bad,
            "high_cps": high_cps,
            "llm_rollbacks": llm_rollbacks,
            "llm_verifier_rejects": llm_verifier_rejects,
            "llm_gate_skips": llm_gate_skips,
            "stt_lattice_hard": stt_lattice_hard,
            "hard_cases": hard_cases,
            "context_events": context_events,
            "context_repeat": context_repeat,
            "context_overlap": context_overlap,
            "context_timing_order": context_timing_order,
            "context_cps_jump": context_cps_jump,
            "context_hallucination": context_hallucination,
            "lora_style_events": lora_style_events,
            "lora_style_drift": lora_style_drift,
            "lora_style_excluded": lora_style_excluded,
            "lora_style_length": lora_style_length,
            "lora_style_cps": lora_style_cps,
            "subtitle_bundle_events": bundle_events,
            "subtitle_bundle_max": bundle_max,
            "subtitle_bundle_cut": bundle_cut,
            "subtitle_bundle_short": bundle_short,
            "subtitle_bundle_long": bundle_long,
        },
    }


def adapt_runtime_settings_from_deep_events(
    settings: dict[str, Any] | None,
    *,
    store_dir: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base = dict(settings or {})
    if not _safe_bool(base.get("deep_runtime_adaptation_enabled"), True):
        return base, {"schema": DEEP_RUNTIME_ADAPTATION_SCHEMA, "applied": False, "reason": "disabled"}

    rows = _recent_deep_events(base, store_dir)
    min_events = _clamp_int(_safe_int(base.get("deep_runtime_adaptation_min_events"), 8), 1, 1000)
    if len(rows) < min_events:
        return base, {
            "schema": DEEP_RUNTIME_ADAPTATION_SCHEMA,
            "applied": False,
            "reason": "not_enough_events",
            "event_count": len(rows),
            "min_events": min_events,
        }

    summary = summarize_deep_runtime_events(rows)
    out = dict(base)
    changes: dict[str, dict[str, Any]] = {}

    def set_value(key: str, value: Any, reason: str) -> None:
        old = out.get(key)
        if old == value:
            return
        out[key] = value
        changes[key] = {"old": old, "new": value, "reason": reason}

    avg_quality = summary.get("avg_quality_score")
    bad_quality = _safe_float(summary.get("bad_quality_ratio"), 0.0)
    high_cps = _safe_float(summary.get("high_cps_ratio"), 0.0)
    rollback = _safe_float(summary.get("llm_rollback_ratio"), 0.0)
    gate_skip = _safe_float(summary.get("llm_gate_skip_ratio"), 0.0)
    hard_case = _safe_float(summary.get("hard_case_ratio"), 0.0)
    context_risk = _safe_float(summary.get("context_risk_ratio"), 0.0)
    context_repeat = _safe_float(summary.get("context_repeat_ratio"), 0.0)
    context_overlap = _safe_float(summary.get("context_overlap_ratio"), 0.0)
    context_timing_order = _safe_float(summary.get("context_timing_order_ratio"), 0.0)
    context_cps_jump = _safe_float(summary.get("context_cps_jump_ratio"), 0.0)
    context_hallucination = _safe_float(summary.get("context_hallucination_ratio"), 0.0)
    lora_style_risk = _safe_float(summary.get("lora_style_risk_ratio"), 0.0)
    lora_style_excluded = _safe_float(summary.get("lora_style_excluded_ratio"), 0.0)
    lora_style_cps = _safe_float(summary.get("lora_style_cps_ratio"), 0.0)
    bundle_max = _safe_float(summary.get("subtitle_bundle_max_ratio"), 0.0)
    bundle_cut = _safe_float(summary.get("subtitle_bundle_cut_ratio"), 0.0)
    bundle_short = _safe_float(summary.get("subtitle_bundle_short_ratio"), 0.0)
    learning_rate = _clamp_float(_safe_float(base.get("deep_runtime_adaptation_rate"), 1.0), 0.1, 2.0)

    if (isinstance(avg_quality, (int, float)) and float(avg_quality) < 72.0) or bad_quality >= 0.18 or hard_case >= 0.28:
        current = _safe_float(out.get("llm_confidence_gate_min_lora_score"), 82.0)
        set_value("llm_confidence_gate_min_lora_score", round(_clamp_float(current + (5.0 * learning_rate), 70.0, 96.0), 3), "recent_quality_low")
        current_ratio = _safe_float(out.get("llm_confidence_gate_max_compact_ratio"), 1.45)
        set_value("llm_confidence_gate_max_compact_ratio", round(_clamp_float(current_ratio - (0.08 * learning_rate), 1.08, 1.8), 3), "recent_quality_low")

    if high_cps >= 0.08:
        split = _safe_int(out.get("split_length_threshold"), 16)
        set_value("split_length_threshold", _clamp_int(split - max(1, int(round(2 * learning_rate))), 8, 32), "recent_high_cps")
        max_cps = _safe_int(out.get("sub_max_cps"), 12)
        set_value("sub_max_cps", _clamp_int(max_cps - 1, 9, 24), "recent_high_cps")

    if context_risk >= 0.06:
        weight = _safe_float(out.get("subtitle_context_score_penalty_weight"), 0.32)
        set_value(
            "subtitle_context_score_penalty_weight",
            round(_clamp_float(weight + (0.06 * learning_rate), 0.12, 0.8), 3),
            "recent_context_risk",
        )

    if context_repeat >= 0.04:
        dedup = _safe_float(out.get("sub_dedup_window"), 0.5)
        set_value("sub_dedup_window", round(_clamp_float(dedup + (0.08 * learning_rate), 0.2, 1.4), 3), "recent_context_repeats")
        repeat_window = _safe_float(out.get("subtitle_context_repeat_window_sec"), 4.0)
        set_value(
            "subtitle_context_repeat_window_sec",
            round(_clamp_float(repeat_window + (0.4 * learning_rate), 2.0, 8.0), 3),
            "recent_context_repeats",
        )
        near_ratio = _safe_float(out.get("subtitle_context_near_duplicate_ratio"), 0.94)
        set_value(
            "subtitle_context_near_duplicate_ratio",
            round(_clamp_float(near_ratio - (0.015 * learning_rate), 0.86, 0.98), 3),
            "recent_context_repeats",
        )

    if context_overlap >= 0.03 or context_timing_order >= 0.02:
        set_value("deep_sequence_smoothing_enabled", True, "recent_context_timing_risk")
        max_shift = _safe_float(out.get("deep_sequence_max_shift_sec"), 0.18)
        set_value(
            "deep_sequence_max_shift_sec",
            round(_clamp_float(max_shift + (0.04 * learning_rate), 0.08, 0.45), 3),
            "recent_context_timing_risk",
        )
        bridge_gap = _safe_float(out.get("deep_sequence_bridge_gap_sec"), 0.3)
        set_value(
            "deep_sequence_bridge_gap_sec",
            round(_clamp_float(bridge_gap + (0.04 * learning_rate), 0.1, 0.8), 3),
            "recent_context_timing_risk",
        )

    if context_cps_jump >= 0.03:
        jump_ratio = _safe_float(out.get("subtitle_context_cps_jump_ratio"), 2.6)
        set_value(
            "subtitle_context_cps_jump_ratio",
            round(_clamp_float(jump_ratio - (0.12 * learning_rate), 1.5, 3.2), 3),
            "recent_context_cps_jumps",
        )
        split = _safe_int(out.get("split_length_threshold"), 16)
        set_value("split_length_threshold", _clamp_int(split - 1, 8, 32), "recent_context_cps_jumps")

    if context_hallucination >= 0.01:
        current = _safe_float(out.get("llm_confidence_gate_min_lora_score"), 82.0)
        set_value("llm_confidence_gate_min_lora_score", round(_clamp_float(current + (3.0 * learning_rate), 70.0, 96.0), 3), "recent_context_hallucination")

    if lora_style_risk >= 0.03:
        weight = _safe_float(out.get("subtitle_lora_style_score_penalty_weight"), 0.22)
        set_value(
            "subtitle_lora_style_score_penalty_weight",
            round(_clamp_float(weight + (0.05 * learning_rate), 0.08, 0.7), 3),
            "recent_lora_style_drift",
        )
        current = _safe_float(out.get("llm_confidence_gate_min_lora_score"), 82.0)
        set_value(
            "llm_confidence_gate_min_lora_score",
            round(_clamp_float(current + (2.0 * learning_rate), 70.0, 96.0), 3),
            "recent_lora_style_drift",
        )

    if lora_style_excluded >= 0.01:
        min_score = _safe_float(out.get("subtitle_lora_style_min_profile_score"), 28.0)
        set_value(
            "subtitle_lora_style_min_profile_score",
            round(_clamp_float(min_score + (2.0 * learning_rate), 20.0, 70.0), 3),
            "recent_lora_excluded_phrase",
        )

    if lora_style_cps >= 0.02:
        max_ratio = _safe_float(out.get("subtitle_lora_style_max_cps_ratio"), 2.0)
        set_value(
            "subtitle_lora_style_max_cps_ratio",
            round(_clamp_float(max_ratio - (0.08 * learning_rate), 1.25, 2.8), 3),
            "recent_lora_style_cps_drift",
        )

    if bundle_max >= 0.04:
        target = _safe_float(out.get("subtitle_bundle_target_sec", out.get("chunk_time_limit", 180.0)), 180.0)
        new_target = round(_clamp_float(target - (18.0 * learning_rate), 90.0, 360.0), 3)
        set_value("subtitle_bundle_target_sec", new_target, "recent_subtitle_bundle_too_long")
        set_value("chunk_time_limit", int(round(new_target)), "recent_subtitle_bundle_too_long")
        max_sec = _safe_float(out.get("subtitle_bundle_max_sec"), 300.0)
        set_value(
            "subtitle_bundle_max_sec",
            round(_clamp_float(max_sec - (24.0 * learning_rate), 150.0, 600.0), 3),
            "recent_subtitle_bundle_too_long",
        )

    if bundle_cut >= 0.03:
        set_value("subtitle_bundle_use_confirmed_cuts", True, "recent_cut_aligned_subtitle_bundles")
        set_value("subtitle_bundle_use_provisional_cuts", True, "recent_cut_aligned_subtitle_bundles")

    if bundle_short >= 0.06:
        min_sec = _safe_float(out.get("subtitle_bundle_min_sec"), 90.0)
        set_value(
            "subtitle_bundle_min_sec",
            round(_clamp_float(min_sec + (12.0 * learning_rate), 45.0, 180.0), 3),
            "recent_subtitle_bundle_too_short",
        )

    if rollback >= 0.04:
        min_similarity = _safe_float(out.get("llm_verifier_min_similarity"), 0.86)
        set_value("llm_verifier_min_similarity", round(_clamp_float(min_similarity + (0.025 * learning_rate), 0.82, 0.96), 3), "recent_llm_rollbacks")
        max_delta = _safe_float(out.get("llm_verifier_max_length_delta_ratio"), 0.16)
        set_value("llm_verifier_max_length_delta_ratio", round(_clamp_float(max_delta - (0.02 * learning_rate), 0.06, 0.22), 3), "recent_llm_rollbacks")

    if isinstance(avg_quality, (int, float)) and float(avg_quality) >= 88.0 and bad_quality <= 0.05 and rollback <= 0.01 and gate_skip >= 0.12:
        current = _safe_float(out.get("llm_confidence_gate_min_lora_score"), 82.0)
        set_value("llm_confidence_gate_min_lora_score", round(_clamp_float(current - (2.0 * learning_rate), 70.0, 96.0), 3), "recent_quality_high_gate_safe")
        current_ratio = _safe_float(out.get("llm_confidence_gate_max_compact_ratio"), 1.45)
        set_value("llm_confidence_gate_max_compact_ratio", round(_clamp_float(current_ratio + (0.04 * learning_rate), 1.08, 1.8), 3), "recent_quality_high_gate_safe")

    if _safe_bool(out.get("subtitle_lora_split_floor_enabled"), False):
        floor = _clamp_int(_safe_int(out.get("subtitle_lora_split_floor_chars"), 20), 12, 36)
        split = _safe_int(out.get("split_length_threshold"), 20)
        if split < floor:
            set_value("split_length_threshold", floor, "lora_split_floor")
        target = _safe_int(out.get("subtitle_common_split_target_chars"), floor)
        if target < floor:
            set_value("subtitle_common_split_target_chars", floor, "lora_split_floor")
        hard = _safe_int(out.get("subtitle_common_split_hard_max_chars"), max(floor + 8, int(floor * 1.6)))
        hard_floor = max(floor + 8, int(floor * 1.6))
        if hard < hard_floor:
            set_value("subtitle_common_split_hard_max_chars", hard_floor, "lora_split_floor")

    meta = {
        "schema": DEEP_RUNTIME_ADAPTATION_SCHEMA,
        "applied": bool(changes),
        "event_count": len(rows),
        "summary": summary,
        "changes": changes,
    }
    if changes:
        out["_deep_runtime_adaptation"] = meta
    return out, meta


__all__ = [
    "DEEP_RUNTIME_ADAPTATION_SCHEMA",
    "adapt_runtime_settings_from_deep_events",
    "summarize_deep_runtime_events",
]
