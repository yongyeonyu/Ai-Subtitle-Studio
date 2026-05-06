from __future__ import annotations

import re
from typing import Any

UNCERTAINTY_SCHEDULER_SCHEMA = "ai_subtitle_studio.subtitle_uncertainty_scheduler.v1"


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "n", "끔", "아니오"}
    return bool(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _compact_len(text: Any) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def _duration(segment: dict[str, Any]) -> float:
    start = _safe_float(segment.get("start", segment.get("timeline_start")), 0.0)
    end = _safe_float(segment.get("end", segment.get("timeline_end")), start)
    return max(0.0, end - start)


def _score_percent(value: Any, default: float = 0.0) -> float:
    score = _safe_float(value, default)
    if 0.0 <= score <= 1.0:
        score *= 100.0
    return max(0.0, min(100.0, score))


def _lora_score(segment: dict[str, Any]) -> float:
    profile = dict(segment.get("_lora_generation_profile") or {})
    scores = [
        _safe_float(segment.get("_lora_segment_score"), 0.0),
        _safe_float(profile.get("top_score"), 0.0),
        _safe_float(profile.get("truth_score"), 0.0),
    ]
    for item in list(profile.get("examples") or []):
        if isinstance(item, dict):
            scores.append(_safe_float(item.get("score"), 0.0))
    return max(scores, default=0.0)


def _stt_score(segment: dict[str, Any]) -> float:
    scores = [
        _score_percent(segment.get("score")),
        _score_percent(segment.get("stt_score")),
        _score_percent(segment.get("stt_ensemble_similarity")),
    ]
    lattice = dict(segment.get("_stt_lattice_policy") or {})
    if lattice:
        scores.append(_score_percent(lattice.get("confidence")))
    deep = dict(segment.get("_deep_candidate_selector_policy") or {})
    if deep:
        scores.append(_score_percent(deep.get("confidence")))
        scores.append(_score_percent(deep.get("score")))
    return max(scores, default=0.0)


def _quality_label(segment: dict[str, Any]) -> str:
    quality = dict(segment.get("quality") or {})
    return str(quality.get("confidence_label") or segment.get("subtitle_confidence_label") or "").strip().lower()


def _quality_score(segment: dict[str, Any]) -> float:
    quality = dict(segment.get("quality") or {})
    return _score_percent(quality.get("confidence_score", segment.get("subtitle_confidence_score")), 0.0)


def _has_deep_hard_case(segment: dict[str, Any]) -> bool:
    for key, value in segment.items():
        if not (str(key).startswith("_deep_") and str(key).endswith("_policy")):
            continue
        policy = dict(value or {})
        if policy.get("hard_case") or policy.get("hard_cases"):
            return True
        for item in list(policy.get("changes") or []):
            if isinstance(item, dict) and "hard_case" in str(item.get("type") or ""):
                return True
    return False


def subtitle_uncertainty_policy(segment: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = dict(settings or {})
    if not _safe_bool(settings.get("uncertainty_first_enabled"), True):
        return {
            "schema": UNCERTAINTY_SCHEDULER_SCHEMA,
            "enabled": False,
            "bucket": "normal",
            "risk_score": 0.0,
            "reasons": ["disabled"],
            "precision_pass_required": False,
            "fast_lane": False,
        }

    threshold = max(1.0, _safe_float(settings.get("split_length_threshold"), 10.0))
    max_duration = max(0.3, _safe_float(settings.get("sub_max_duration"), 6.0))
    max_cps = max(1.0, _safe_float(settings.get("sub_max_cps"), 12.0))
    easy_score = max(0.0, _safe_float(settings.get("uncertainty_first_easy_score"), 18.0))
    precision_score = max(easy_score + 1.0, _safe_float(settings.get("uncertainty_first_precision_score"), 52.0))

    text = str(segment.get("text") or "")
    chars = _compact_len(text)
    duration = _duration(segment)
    cps = chars / max(0.1, duration)
    lora_score = _lora_score(segment)
    stt_score = _stt_score(segment)
    quality_label = _quality_label(segment)
    quality_score = _quality_score(segment)
    reasons: list[dict[str, Any]] = []
    risk = 0.0

    def add(reason: str, points: float, **evidence: Any) -> None:
        nonlocal risk
        risk += float(points or 0.0)
        clean_evidence = {key: value for key, value in evidence.items() if value not in (None, "", [], {})}
        reasons.append({"reason": reason, "points": round(float(points or 0.0), 3), "evidence": clean_evidence})

    if not text.strip():
        add("empty_text", 65.0)
    if chars > threshold * _safe_float(settings.get("uncertainty_first_long_text_ratio"), 1.45):
        add("long_text", 16.0, compact_len=chars, threshold=threshold)
    if duration > max_duration * 1.08:
        add("long_duration", 14.0, duration=round(duration, 3), max_duration=max_duration)
    if cps > max_cps * 1.12:
        add("high_cps", 18.0, cps=round(cps, 3), max_cps=max_cps)
    if segment.get("stt_ensemble_needs_llm_review"):
        add("stt_candidate_conflict", 38.0)
    if 0.0 < stt_score < _safe_float(settings.get("uncertainty_first_low_stt_score"), 58.0):
        add("low_stt_score", 20.0, stt_score=round(stt_score, 3))
    if 0.0 < lora_score < _safe_float(settings.get("uncertainty_first_low_lora_score"), 58.0):
        add("low_lora_score", 14.0, lora_score=round(lora_score, 3))
    if lora_score <= 0.0 and stt_score <= 0.0:
        add("missing_confidence_signals", 22.0)
    if quality_label == "red":
        add("quality_red", 42.0, quality_score=round(quality_score, 3))
    elif quality_label == "yellow":
        add("quality_yellow", 18.0, quality_score=round(quality_score, 3))

    lattice = dict(segment.get("_stt_lattice_policy") or {})
    if lattice and (lattice.get("accepted") is False or _score_percent(lattice.get("confidence"), 100.0) < 62.0):
        add("stt_lattice_uncertain", 18.0, confidence=lattice.get("confidence"), detail=lattice.get("reason"))

    rollback = dict(segment.get("_llm_rollback_policy") or {})
    verifier = dict(segment.get("_llm_verifier_policy") or {})
    if rollback:
        add("llm_rollback", 46.0, detail=rollback.get("reason"))
    if verifier and verifier.get("accepted") is False:
        add("llm_verifier_rejected", 34.0, detail=verifier.get("reason"))

    cut_guard = dict(segment.get("_cut_boundary_guard_policy") or {})
    cut_action = str(cut_guard.get("action") or "")
    if cut_action in {"clamped_to_cut_boundary", "cut_boundary_crossing"}:
        add("cut_boundary_crossing", 30.0, action=cut_action, confidence=cut_guard.get("confidence"))
    elif cut_action == "allowed_high_confidence_crossing":
        add("cut_boundary_touch", 8.0, action=cut_action, confidence=cut_guard.get("confidence"))

    if _has_deep_hard_case(segment):
        add("deep_hard_case", 28.0)

    positive_signal = max(lora_score, stt_score, quality_score)
    if not reasons and positive_signal >= _safe_float(settings.get("uncertainty_first_easy_signal_score"), 82.0):
        bucket = "easy"
    elif risk <= easy_score and positive_signal >= _safe_float(settings.get("uncertainty_first_easy_signal_score"), 82.0):
        bucket = "easy"
    elif risk >= precision_score:
        bucket = "precision"
    else:
        bucket = "normal"

    actions = []
    if bucket == "precision":
        actions.append("run_precision_pass")
    if any(item.get("reason") in {"stt_candidate_conflict", "stt_lattice_uncertain", "low_stt_score"} for item in reasons):
        actions.append("prefer_stt_recheck")
    if any(item.get("reason") in {"llm_rollback", "llm_verifier_rejected", "long_text"} for item in reasons):
        actions.append("allow_llm_minimal_fix")
    if any(item.get("reason") in {"cut_boundary_crossing", "cut_boundary_touch"} for item in reasons):
        actions.append("recheck_cut_boundary")

    return {
        "schema": UNCERTAINTY_SCHEDULER_SCHEMA,
        "enabled": True,
        "bucket": bucket,
        "risk_score": round(risk, 4),
        "confidence_signal_score": round(positive_signal, 4),
        "precision_pass_required": bucket == "precision",
        "fast_lane": bucket == "easy",
        "reasons": reasons,
        "recommended_actions": list(dict.fromkeys(actions)),
        "features": {
            "compact_len": chars,
            "duration_sec": round(duration, 4),
            "cps": round(cps, 4),
            "lora_score": round(lora_score, 4),
            "stt_score": round(stt_score, 4),
            "quality_label": quality_label,
            "quality_score": round(quality_score, 4),
        },
    }


def annotate_uncertainty_first_segments(
    segments: list[dict[str, Any]] | None,
    settings: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [dict(row) for row in list(segments or []) if isinstance(row, dict)]
    policies = [subtitle_uncertainty_policy(row, settings) for row in rows]
    for row, policy in zip(rows, policies):
        row["_uncertainty_policy"] = policy
        row["_uncertainty_bucket"] = policy.get("bucket")
        row["_uncertainty_risk_score"] = policy.get("risk_score")

    order_mode = str((settings or {}).get("uncertainty_first_process_order") or "easy_first").strip().lower()
    bucket_order = {"easy": 0, "normal": 1, "precision": 2}
    if order_mode in {"precision_first", "uncertain_first"}:
        bucket_order = {"precision": 0, "normal": 1, "easy": 2}
    elif order_mode in {"original", "timeline"}:
        process_order = list(range(len(rows)))
    else:
        process_order = sorted(
            range(len(rows)),
            key=lambda idx: (
                bucket_order.get(str(policies[idx].get("bucket") or "normal"), 1),
                _safe_float(rows[idx].get("start", rows[idx].get("timeline_start")), 0.0),
                idx,
            ),
        )
    if order_mode not in {"original", "timeline"}:
        pass

    counts: dict[str, int] = {"easy": 0, "normal": 0, "precision": 0}
    for policy in policies:
        bucket = str(policy.get("bucket") or "normal")
        counts[bucket] = counts.get(bucket, 0) + 1
    plan = {
        "schema": UNCERTAINTY_SCHEDULER_SCHEMA,
        "enabled": bool(policies and policies[0].get("enabled", True)),
        "order_mode": order_mode,
        "process_order": process_order,
        "bucket_counts": counts,
        "precision_count": counts.get("precision", 0),
        "easy_count": counts.get("easy", 0),
        "normal_count": counts.get("normal", 0),
    }
    if rows:
        rows[0]["_uncertainty_schedule_summary"] = dict(plan)
    return rows, plan


__all__ = [
    "UNCERTAINTY_SCHEDULER_SCHEMA",
    "annotate_uncertainty_first_segments",
    "subtitle_uncertainty_policy",
]
