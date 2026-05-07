from __future__ import annotations

"""AutoPilot policy helpers.

This module keeps the normal UI simple while preserving internal lanes for
speed/accuracy decisions. The functions are intentionally lightweight and
deterministic so they can run before expensive STT/LoRA/LLM work starts.
"""

from math import isfinite
from typing import Any


AUTOPILOT_POLICY_SCHEMA = "ai_subtitle_studio.autopilot_policy.v1"
AUTOPILOT_PROGRESS_SCHEMA = "ai_subtitle_studio.autopilot_progress_event.v1"
AUTOPILOT_STAGE_PREWARM_SCHEMA = "ai_subtitle_studio.autopilot_stage_prewarm.v1"
AUTOPILOT_SPEAKER_PREFLIGHT_SCHEMA = "ai_subtitle_studio.autopilot_speaker_preflight.v1"
HYBRID_CUT_BOUNDARY_SCHEMA = "ai_subtitle_studio.hybrid_cut_boundary_policy.v1"

CONFIDENCE_SIGNAL_WEIGHTS = {
    "stt_confidence": 0.19,
    "lora_score": 0.18,
    "deep_selector_confidence": 0.17,
    "vad_alignment_score": 0.12,
    "cut_boundary_confidence": 0.12,
    "timing_quality": 0.10,
    "user_history_score": 0.07,
    "style_match_score": 0.05,
}

STAGE_SEQUENCE = (
    "diagnostic",
    "audio_extract",
    "vad",
    "cut_boundary",
    "stt",
    "lora",
    "llm_review",
    "roughcut",
    "export",
)

STAGE_PREWARM_RESOURCE = {
    "audio_extract": "audio_cache",
    "vad": "vad_model",
    "cut_boundary": "cut_boundary_index",
    "stt": "stt_model",
    "lora": "lora_index",
    "llm_review": "llm_runner",
    "roughcut": "roughcut_context",
    "export": "renderer",
}


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"0", "false", "off", "no", "n", "끔", "아니오"}:
            return False
        if text in {"1", "true", "on", "yes", "y", "켬", "예"}:
            return True
    return bool(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return float(default)
    return number if isfinite(number) else float(default)


def _score_100(value: Any, default: float = 0.0) -> float:
    score = _safe_float(value, default)
    if 0.0 <= score <= 1.0:
        score *= 100.0
    return max(0.0, min(100.0, score))


def _label(score: float) -> str:
    if score >= 86.0:
        return "green"
    if score >= 64.0:
        return "yellow"
    return "red"


def autopilot_runtime_defaults() -> dict[str, Any]:
    return {
        "autopilot_enabled": True,
        "autopilot_single_user_mode": True,
        "operation_mode_choices_visible": False,
        "autopilot_internal_lanes_enabled": True,
        "autopilot_fast_lane_enabled": True,
        "autopilot_review_lane_enabled": True,
        "autopilot_llm_lane_enabled": True,
        "autopilot_rollback_lane_enabled": True,
        "autopilot_fast_lane_min_confidence": 88.0,
        "autopilot_review_lane_min_confidence": 68.0,
        "autopilot_llm_lane_max_confidence": 67.999,
        "autopilot_speaker_preflight_enabled": True,
        "autopilot_speaker_preflight_targeted_diarization": True,
        "autopilot_stage_prewarm_enabled": True,
        "autopilot_stage_prewarm_start_progress": 0.72,
        "autopilot_stage_prewarm_llm_min_risky_segments": 2,
        "autopilot_progress_events_enabled": True,
        "autopilot_progress_min_interval_sec": 0.35,
        "cut_boundary_policy_mode": "hybrid",
        "cut_boundary_user_level_visible": False,
        "cut_boundary_hybrid_enabled": True,
        "cut_boundary_hybrid_fast_level": "low",
        "cut_boundary_hybrid_escalate_level": "medium",
        "cut_boundary_audio_provisional_color": "#39FF14",
        "autopilot_cache_enabled": True,
        "autopilot_stage_cache_enabled": True,
        "autopilot_negative_cache_enabled": True,
        "autopilot_compressed_diagnostics_enabled": True,
        "cut_boundary_cache_enabled": True,
        "scan_cut_compare_max_width": 1920,
        "scan_cut_compare_max_height": 1080,
        "vad_detection_cache_enabled": True,
        "autopilot_compact_fast_lane_graph": True,
    }


def apply_autopilot_runtime_policy(settings: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(settings or {})
    if not _safe_bool(out.get("autopilot_enabled"), True):
        return out
    defaults = autopilot_runtime_defaults()
    for key, value in defaults.items():
        out.setdefault(key, value)
    from core.mode_policy import selected_mode_from_settings

    mode = selected_mode_from_settings(out)
    out["simple_operation_mode"] = mode
    out["subtitle_mode"] = mode
    out["operation_mode_choices_visible"] = False
    if mode == "auto" and _safe_bool(out.get("cut_boundary_hybrid_enabled"), True):
        out["cut_boundary_policy_mode"] = "hybrid"
        out["cut_boundary_user_level_visible"] = False
        if _safe_bool(out.get("cut_boundary_enabled", out.get("cut_boundary_detection_enabled", True)), True):
            out["scan_cut_level"] = str(out.get("cut_boundary_hybrid_fast_level") or "low")
            out["cut_boundary_level"] = str(out.get("cut_boundary_hybrid_fast_level") or "low")
            out["scan_cut_boundary_level"] = str(out.get("cut_boundary_hybrid_fast_level") or "low")
    out["autopilot_policy"] = {
        "schema": AUTOPILOT_POLICY_SCHEMA,
        "single_user_mode": True,
        "internal_lanes": ["fast", "review", "llm", "rollback"],
        "cut_boundary_policy": str(out.get("cut_boundary_policy_mode") or "hybrid"),
    }
    return out


def unified_confidence_score(signals: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(signals or {})
    weighted = 0.0
    weight_sum = 0.0
    missing: list[str] = []
    for key, weight in CONFIDENCE_SIGNAL_WEIGHTS.items():
        if key not in data or data.get(key) in (None, ""):
            missing.append(key)
            continue
        weighted += _score_100(data.get(key)) * weight
        weight_sum += weight
    if weight_sum <= 0.0:
        score = 50.0
    else:
        score = weighted / weight_sum
        if missing:
            score -= min(10.0, len(missing) * 1.25)
    score = max(0.0, min(100.0, score))
    return {
        "schema": AUTOPILOT_POLICY_SCHEMA,
        "task": "unified_confidence",
        "score": round(score, 3),
        "label": _label(score),
        "missing_signals": missing,
        "signals": {key: _score_100(value) for key, value in data.items() if key in CONFIDENCE_SIGNAL_WEIGHTS},
    }


def classify_confidence_lane(
    signals: dict[str, Any] | None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    data = dict(signals or {})
    confidence = unified_confidence_score(data)
    score = float(confidence["score"])
    reasons: list[str] = []
    rollback_reasons = [
        "llm_meaning_changed",
        "llm_added_unsupported_content",
        "number_changed",
        "proper_noun_changed",
        "timing_style_violation",
    ]
    if any(_safe_bool(data.get(key), False) for key in rollback_reasons):
        return {
            "schema": AUTOPILOT_POLICY_SCHEMA,
            "task": "confidence_lane",
            "lane": "rollback",
            "score": round(score, 3),
            "label": "red",
            "call_llm": False,
            "finalize_without_llm": False,
            "reasons": [key for key in rollback_reasons if _safe_bool(data.get(key), False)],
            "confidence": confidence,
        }

    risk_keys = {
        "stt_candidate_conflict": "stt_candidate_conflict",
        "numeric_risk": "numeric_or_proper_noun_risk",
        "proper_noun_risk": "numeric_or_proper_noun_risk",
        "hallucination_risk": "hallucination_risk",
        "cut_boundary_crossing": "cut_boundary_crossing",
        "poor_vad_alignment": "poor_vad_alignment",
        "long_text_risk": "long_text_risk",
    }
    for key, reason in risk_keys.items():
        if _safe_bool(data.get(key), False) and reason not in reasons:
            reasons.append(reason)

    fast_min = _safe_float(settings.get("autopilot_fast_lane_min_confidence"), 88.0)
    review_min = _safe_float(settings.get("autopilot_review_lane_min_confidence"), 68.0)
    if score >= fast_min and not reasons:
        lane = "fast"
        call_llm = False
        finalize_without_llm = True
        reasons.append("high_confidence_all_signals")
    elif score >= review_min and len(reasons) <= 1:
        lane = "review"
        call_llm = False
        finalize_without_llm = False
        if not reasons:
            reasons.append("medium_confidence_use_cheap_checks")
    else:
        lane = "llm"
        call_llm = True
        finalize_without_llm = False
        if not reasons:
            reasons.append("low_unified_confidence")

    return {
        "schema": AUTOPILOT_POLICY_SCHEMA,
        "task": "confidence_lane",
        "lane": lane,
        "score": round(score, 3),
        "label": _label(score),
        "call_llm": call_llm,
        "finalize_without_llm": finalize_without_llm,
        "reasons": reasons,
        "confidence": confidence,
    }


def speaker_preflight_decision(
    vad_segments: list[dict[str, Any]] | None = None,
    *,
    media_duration_sec: float | None = None,
    speaker_count_hint: int | None = None,
    audio_evidence: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    segments = [dict(item) for item in list(vad_segments or []) if isinstance(item, dict)]
    duration = max(0.0, _safe_float(media_duration_sec, 0.0))
    if duration <= 0.0 and segments:
        duration = max(_safe_float(item.get("end"), 0.0) for item in segments)
    minutes = max(duration / 60.0, 0.1)
    hint = max(0, int(speaker_count_hint or 0))
    segment_rate = len(segments) / minutes
    avg_segment_sec = 0.0
    if segments:
        avg_segment_sec = sum(max(0.0, _safe_float(row.get("end"), 0.0) - _safe_float(row.get("start"), 0.0)) for row in segments) / len(segments)
    audio = dict(audio_evidence or {})
    gain_shifts = int(audio.get("gain_shift_count", audio.get("audio_gain_boundary_count", 0)) or 0)

    reasons: list[str] = []
    multi_risk = 0.0
    if hint >= 2:
        multi_risk += 0.62
        reasons.append("explicit_speaker_hint")
    if segment_rate >= 18.0 and avg_segment_sec <= 3.2:
        multi_risk += 0.18
        reasons.append("rapid_vad_turns")
    if gain_shifts >= max(2, int(minutes // 4)):
        multi_risk += 0.12
        reasons.append("frequent_audio_gain_shifts")
    if len(segments) <= 2 and hint <= 1:
        multi_risk -= 0.18
        reasons.append("few_vad_segments")
    multi_risk = max(0.0, min(1.0, multi_risk))
    estimated_count = 2 if multi_risk >= 0.52 else 1
    confidence = 0.92 - min(0.24, abs(0.5 - multi_risk) * 0.48)
    if hint:
        confidence = max(confidence, 0.88)
    if estimated_count <= 1 and multi_risk <= 0.22:
        lane = "skip_diarization"
        action = "single_speaker_output"
    elif multi_risk < 0.52:
        lane = "sample_check"
        action = "cheap_speaker_check"
    else:
        lane = "targeted_diarization" if _safe_bool(settings.get("autopilot_speaker_preflight_targeted_diarization"), True) else "sample_check"
        action = "targeted_speaker_regions"
    return {
        "schema": AUTOPILOT_SPEAKER_PREFLIGHT_SCHEMA,
        "enabled": _safe_bool(settings.get("autopilot_speaker_preflight_enabled"), True),
        "estimated_speaker_count": estimated_count,
        "speaker_change_risk": round(multi_risk, 4),
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "lane": lane,
        "action": action,
        "reasons": reasons or ["single_speaker_default"],
        "segment_rate_per_min": round(segment_rate, 3),
        "avg_vad_segment_sec": round(avg_segment_sec, 3),
    }


def hybrid_cut_boundary_decision(
    evidence: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    row = dict(evidence or {})
    source = str(row.get("source") or row.get("detector") or "").lower()
    visual_score = _score_100(row.get("visual_score", row.get("score")), 0.0)
    audio_delta = abs(_safe_float(row.get("audio_gain_db_delta", row.get("delta_db")), 0.0))
    deep_score = _score_100(row.get("deep_boundary_score", row.get("deep_score")), 0.0)
    stt_shift = _score_100(row.get("stt_context_shift_score", row.get("topic_shift_score")), 0.0)
    is_audio = "audio" in source or "gain" in source
    is_visual = "visual" in source or _safe_bool(row.get("has_visual"), False)
    combined = max(visual_score, deep_score, stt_shift, min(100.0, audio_delta * 7.5))
    if is_audio and not is_visual:
        lane = "audio_provisional"
        action = "verify_with_visual_follower"
        hard_cut = False
        color = str(settings.get("cut_boundary_audio_provisional_color") or "#39FF14")
        reason = "audio_gain_needs_visual_confirmation"
    elif combined >= 86.0 and is_visual:
        lane = "fast_confirm"
        action = "accept_hard_cut"
        hard_cut = True
        color = ""
        reason = "high_visual_or_deep_score"
    elif combined >= 48.0:
        lane = "escalate"
        action = "run_medium_or_rollback_verification"
        hard_cut = False
        color = ""
        reason = "ambiguous_boundary_evidence"
    else:
        lane = "drop_hint"
        action = "discard_or_keep_roughcut_only"
        hard_cut = False
        color = ""
        reason = "weak_boundary_evidence"
    return {
        "schema": HYBRID_CUT_BOUNDARY_SCHEMA,
        "lane": lane,
        "action": action,
        "hard_cut_allowed": hard_cut,
        "line_color": color,
        "confidence": round(combined, 3),
        "reason": reason,
        "fast_level": str(settings.get("cut_boundary_hybrid_fast_level") or "low"),
        "escalate_level": str(settings.get("cut_boundary_hybrid_escalate_level") or "medium"),
    }


def stage_prewarm_decision(
    active_stage: str,
    progress: float,
    settings: dict[str, Any] | None = None,
    resource: dict[str, Any] | None = None,
    *,
    predicted_risky_segments: int = 0,
) -> dict[str, Any]:
    settings = dict(settings or {})
    resource = dict(resource or {})
    stage = str(active_stage or "").strip().lower()
    threshold = max(0.0, min(1.0, _safe_float(settings.get("autopilot_stage_prewarm_start_progress"), 0.72)))
    progress_value = max(0.0, min(1.0, _safe_float(progress, 0.0)))
    enabled = _safe_bool(settings.get("autopilot_stage_prewarm_enabled"), True)
    if stage not in STAGE_SEQUENCE:
        next_stage = ""
    else:
        idx = STAGE_SEQUENCE.index(stage)
        next_stage = STAGE_SEQUENCE[idx + 1] if idx + 1 < len(STAGE_SEQUENCE) else ""
    if not enabled:
        action, reason = "skip", "disabled"
    elif not next_stage:
        action, reason = "skip", "no_next_stage"
    elif progress_value < threshold:
        action, reason = "wait", "active_stage_not_near_complete"
    elif next_stage == "llm_review" and int(predicted_risky_segments or 0) < int(settings.get("autopilot_stage_prewarm_llm_min_risky_segments", 2) or 2):
        action, reason = "skip", "llm_risk_too_low"
    elif _safe_bool(resource.get("user_active"), False):
        action, reason = "delay", "user_active"
    elif _safe_float(resource.get("memory_pressure"), 0.0) >= 0.82:
        action, reason = "delay", "memory_pressure"
    elif _safe_float(resource.get("cpu_pressure"), 0.0) >= 0.88:
        action, reason = "delay", "cpu_pressure"
    elif _safe_bool(resource.get("battery_saver"), False):
        action, reason = "delay", "battery_saver"
    else:
        action, reason = "prewarm", "stage_near_complete"
    return {
        "schema": AUTOPILOT_STAGE_PREWARM_SCHEMA,
        "active_stage": stage,
        "progress": round(progress_value, 4),
        "next_stage": next_stage,
        "resource": STAGE_PREWARM_RESOURCE.get(next_stage, ""),
        "action": action,
        "reason": reason,
        "predicted_risky_segments": int(predicted_risky_segments or 0),
    }


def compact_progress_event(
    *,
    stage: str,
    lane: str = "",
    reason: str = "",
    next_stage: str = "",
    resource_state: str = "",
    skipped: str = "",
    triggered: str = "",
) -> dict[str, Any]:
    parts = [str(stage or "AutoPilot").strip()]
    if lane:
        parts.append(f"{lane} lane")
    if reason:
        parts.append(str(reason))
    if skipped:
        parts.append(f"skipped {skipped}")
    if triggered:
        parts.append(f"triggered {triggered}")
    if next_stage:
        parts.append(f"next {next_stage}")
    if resource_state:
        parts.append(str(resource_state))
    label = " · ".join(part for part in parts if part)
    return {
        "schema": AUTOPILOT_PROGRESS_SCHEMA,
        "stage": str(stage or ""),
        "lane": str(lane or ""),
        "reason": str(reason or ""),
        "next_stage": str(next_stage or ""),
        "resource_state": str(resource_state or ""),
        "skipped": str(skipped or ""),
        "triggered": str(triggered or ""),
        "label": label,
    }


__all__ = [
    "AUTOPILOT_POLICY_SCHEMA",
    "AUTOPILOT_PROGRESS_SCHEMA",
    "AUTOPILOT_SPEAKER_PREFLIGHT_SCHEMA",
    "AUTOPILOT_STAGE_PREWARM_SCHEMA",
    "HYBRID_CUT_BOUNDARY_SCHEMA",
    "apply_autopilot_runtime_policy",
    "autopilot_runtime_defaults",
    "classify_confidence_lane",
    "compact_progress_event",
    "hybrid_cut_boundary_decision",
    "speaker_preflight_decision",
    "stage_prewarm_decision",
    "unified_confidence_score",
]
