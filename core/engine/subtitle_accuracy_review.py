from __future__ import annotations

from typing import Any

from core.engine import subtitle_accuracy_pipeline as _base

SUBTITLE_ACCURACY_SCHEMA = _base.SUBTITLE_ACCURACY_SCHEMA
_decision = _base._decision
_decision_items = _base._decision_items
_has_decision = _base._has_decision
_candidate_text_conflict = _base._candidate_text_conflict
_clean_text = _base._clean_text
compact_len = _base.compact_len
_deep_hard_case_reasons = _base._deep_hard_case_reasons
_line_count = _base._line_count
_review_reason = _base._review_reason
_safe_bool = _base._safe_bool
_safe_float = _base._safe_float
_segment_duration = _base._segment_duration
_severity_rank = _base._severity_rank
_stage_payload = _base._stage_payload
_score_percent = _base._score_percent
_profile_score = _base._profile_score
subtitle_accuracy_metrics = _base.subtitle_accuracy_metrics


def subtitle_auto_review_items(segments: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return only subtitle rows that deserve human review."""
    settings = dict(settings or {})
    if not _safe_bool(settings.get("subtitle_auto_review_enabled"), True):
        return []
    max_cps = max(0.0, _safe_float(settings.get("sub_max_cps"), 12.0))
    max_duration = max(0.0, _safe_float(settings.get("sub_max_duration"), 6.0))
    lora_min = max(0.0, min(100.0, _safe_float(settings.get("subtitle_auto_review_lora_min_score"), 58.0)))
    candidate_min_similarity = max(0.0, min(1.0, _safe_float(settings.get("subtitle_auto_review_stt_conflict_similarity"), 0.9)))
    items: list[dict[str, Any]] = []

    for index, segment in enumerate(list(segments or [])):
        if not isinstance(segment, dict):
            continue
        reasons: list[dict[str, Any]] = []
        start = _safe_float(segment.get("start"), 0.0)
        end = _safe_float(segment.get("end"), start)
        duration = max(0.001, end - start)
        text = _clean_text(segment.get("text"))
        cps = compact_len(text) / duration

        quality = dict(segment.get("quality") or {})
        label = str(quality.get("confidence_label") or "").strip().lower()
        quality_score = quality.get("confidence_score")
        if label == "red":
            reasons.append(_review_reason("quality_red", "red", "Subtitle quality checker marked this row red.", confidence_score=quality_score))
        elif label in {"yellow", "gray"}:
            reasons.append(_review_reason("quality_uncertain", "yellow", "Subtitle quality checker marked this row uncertain.", confidence_label=label, confidence_score=quality_score))

        if max_cps and cps > max_cps:
            severity = "red" if cps > max_cps * 1.35 else "yellow"
            reasons.append(_review_reason("high_cps", severity, "Subtitle is faster than the configured CPS limit.", cps=round(cps, 3), max_cps=round(max_cps, 3)))

        if max_duration and duration > max_duration:
            severity = "red" if duration > max_duration * 1.35 else "yellow"
            reasons.append(_review_reason("over_max_duration", severity, "Subtitle duration is longer than the target maximum.", duration=round(duration, 3), max_duration=round(max_duration, 3)))

        lora_profile = dict(segment.get("_lora_generation_profile") or {})
        lora_score = _profile_score(lora_profile)
        has_lora = bool(lora_profile or segment.get("_lora_segment_settings") or segment.get("_lora_segment_score") is not None)
        if has_lora and lora_score > 0.0 and lora_score < lora_min:
            reasons.append(_review_reason("low_lora_score", "yellow", "LoRA ground-truth support is weak for this row.", lora_score=round(lora_score, 4), min_score=round(lora_min, 4)))

        stt_conflict = _candidate_text_conflict(segment, min_similarity=candidate_min_similarity)
        if segment.get("stt_ensemble_needs_llm_review") or stt_conflict:
            reasons.append(_review_reason("stt_candidate_conflict", "red", "STT candidates disagree and need focused review.", **(stt_conflict or {})))

        lattice = dict(segment.get("_stt_lattice_policy") or {})
        if lattice.get("enabled"):
            confidence = _safe_float(lattice.get("confidence"), 1.0)
            min_conf = _safe_float(lattice.get("min_confidence"), _safe_float(settings.get("stt_lattice_min_confidence"), 0.62))
            if lattice.get("accepted") is False or confidence < min_conf:
                reasons.append(_review_reason("stt_lattice_uncertain", "yellow", "STT lattice selector could not make a confident replacement.", confidence=round(confidence, 4), min_confidence=round(min_conf, 4), reason=lattice.get("reason")))

        if segment.get("_llm_rollback_policy") or _has_decision(segment, "llm_rollback"):
            rollback = dict(segment.get("_llm_rollback_policy") or {})
            reasons.append(_review_reason("llm_rollback", "red", "LLM output was rejected and rolled back.", reason=rollback.get("reason"), fallback=rollback.get("fallback")))
        if _has_decision(segment, "llm_verifier", accepted=False):
            reasons.append(_review_reason("llm_verifier_rejected", "red", "LLM verifier rejected the generated subtitle.", task="llm_verifier"))
        rewrite_policy = dict(segment.get("_llm_rewrite_policy") or {})
        if rewrite_policy.get("needs_review"):
            rewrite_confidence = str(rewrite_policy.get("confidence") or "low").lower()
            rewrite_severity = "yellow" if rewrite_confidence == "medium" else "red"
            reasons.append(
                _review_reason(
                    "llm_uncertain_rewrite",
                    rewrite_severity,
                    "LLM corrected an STT phrase but the rewrite confidence is limited.",
                    confidence=rewrite_confidence,
                    similarity=rewrite_policy.get("similarity"),
                    reason=rewrite_policy.get("reason"),
                )
            )

        cut_guard = dict(segment.get("_cut_boundary_guard_policy") or {})
        cut_action = str(cut_guard.get("action") or "")
        if cut_action:
            severity = "yellow" if cut_action == "allowed_high_confidence_crossing" else "red"
            reasons.append(_review_reason("cut_boundary_crossing", severity, "Subtitle touched or crossed a cut boundary.", action=cut_action, confidence=cut_guard.get("confidence")))

        context_policy = dict(segment.get("_context_consistency_policy") or {})
        if context_policy.get("flags"):
            reasons.append(_review_reason("context_consistency_risk", "yellow", "Sequence checker found repeated, overlapping, or unstable context.", flags=list(context_policy.get("flags") or [])))

        lora_style = dict(segment.get("_lora_style_policy") or {})
        if lora_style.get("flags"):
            reasons.append(_review_reason("lora_style_drift", "yellow", "Subtitle drifts away from similar ground-truth style.", flags=list(lora_style.get("flags") or []), score=lora_style.get("score")))

        deep_reasons = _deep_hard_case_reasons(segment)
        if deep_reasons:
            reasons.append(_review_reason("deep_hard_case", "yellow", "Deep-learning policy marked this row as a hard case.", reasons=deep_reasons))

        if segment.get("stt_pending") or segment.get("_live_stt_preview"):
            reasons.append(_review_reason("unfinished_stt_preview", "yellow", "This row still looks like an unfinished STT preview.", stt_pending=segment.get("stt_pending"), live_preview=segment.get("_live_stt_preview")))

        if not reasons:
            continue

        severity = max((str(reason.get("severity") or "info") for reason in reasons), key=_severity_rank)
        issue_types = sorted({str(reason.get("type") or "") for reason in reasons if reason.get("type")})
        risk_score = min(100.0, sum({1: 8.0, 2: 24.0, 3: 42.0}.get(_severity_rank(reason.get("severity")), 4.0) for reason in reasons))
        actions = ["review_subtitle_row"]
        if any(reason.get("type") in {"stt_candidate_conflict", "stt_lattice_uncertain"} for reason in reasons):
            actions.append("compare_stt_candidates")
        if any(reason.get("type") in {"llm_rollback", "llm_verifier_rejected"} for reason in reasons):
            actions.append("check_llm_rollback")
        if any(reason.get("type") == "llm_uncertain_rewrite" for reason in reasons):
            actions.append("check_llm_rewrite")
        if any(reason.get("type") == "cut_boundary_crossing" for reason in reasons):
            actions.append("check_cut_boundary")
        if any(reason.get("type") in {"high_cps", "over_max_duration"} for reason in reasons):
            actions.append("adjust_timing_or_split")

        items.append(
            {
                "schema": SUBTITLE_ACCURACY_SCHEMA,
                "task": "subtitle_auto_review_item",
                "index": index,
                "segment_id": str(segment.get("segment_id") or segment.get("id") or index),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(duration, 3),
                "text_preview": text[:100],
                "severity": severity,
                "risk_score": round(risk_score, 3),
                "issue_types": issue_types,
                "reasons": reasons,
                "actions": actions,
                "cps": round(cps, 3),
                "lora_score": round(lora_score, 4),
                "quality_label": label,
                "quality_score": quality_score,
            }
        )

    return sorted(items, key=lambda item: (-_severity_rank(item.get("severity")), float(item.get("start", 0.0)), int(item.get("index", 0))))


def subtitle_auto_review_summary(segments: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = dict(settings or {})
    items = subtitle_auto_review_items(segments, settings)
    severity_counts = {"red": 0, "yellow": 0, "info": 0}
    issue_type_counts: dict[str, int] = {}
    for item in items:
        severity = str(item.get("severity") or "info")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        for issue_type in list(item.get("issue_types") or []):
            issue_type_counts[str(issue_type)] = issue_type_counts.get(str(issue_type), 0) + 1
    seconds_per_item = max(3.0, _safe_float(settings.get("subtitle_auto_review_seconds_per_item"), 14.0))
    estimated_review_sec = int(round((len(items) * seconds_per_item) + (severity_counts.get("red", 0) * 6.0)))
    return {
        "schema": SUBTITLE_ACCURACY_SCHEMA,
        "task": "subtitle_auto_review_summary",
        "enabled": _safe_bool(settings.get("subtitle_auto_review_enabled"), True),
        "total_segments": len([seg for seg in list(segments or []) if isinstance(seg, dict)]),
        "issue_count": len(items),
        "severity_counts": severity_counts,
        "issue_type_counts": dict(sorted(issue_type_counts.items())),
        "estimated_review_sec": estimated_review_sec,
        "estimated_review_min": round(estimated_review_sec / 60.0, 2),
        "items": items,
    }


def annotate_subtitle_auto_review(segments: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Attach issue-only review metadata to final subtitle rows."""
    rows = [dict(segment) for segment in list(segments or []) if isinstance(segment, dict)]
    if not rows:
        return []
    summary = subtitle_auto_review_summary(rows, settings)
    by_index = {int(item.get("index", -1)): item for item in list(summary.get("items") or []) if isinstance(item, dict)}
    stale_keys = (
        "subtitle_auto_review",
        "subtitle_auto_review_reasons",
        "subtitle_auto_review_severity",
        "subtitle_auto_review_score",
        "subtitle_auto_review_actions",
        "subtitle_auto_review_summary",
    )
    for index, row in enumerate(rows):
        for key in stale_keys:
            row.pop(key, None)
        item = by_index.get(index)
        if not item:
            continue
        row["subtitle_auto_review"] = item
        row["subtitle_auto_review_reasons"] = list(item.get("issue_types") or [])
        row["subtitle_auto_review_severity"] = str(item.get("severity") or "info")
        row["subtitle_auto_review_score"] = item.get("risk_score")
        row["subtitle_auto_review_actions"] = list(item.get("actions") or [])
    compact_summary = dict(summary)
    compact_summary["items"] = [
        {
            "index": item.get("index"),
            "segment_id": item.get("segment_id"),
            "start": item.get("start"),
            "end": item.get("end"),
            "severity": item.get("severity"),
            "risk_score": item.get("risk_score"),
            "issue_types": list(item.get("issue_types") or []),
            "text_preview": item.get("text_preview"),
        }
        for item in list(summary.get("items") or [])
        if isinstance(item, dict)
    ]
    rows[0]["subtitle_auto_review_summary"] = compact_summary
    return rows


def subtitle_stage_confidence(segment: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build cut/STT/LLM/LoRA/final confidence chips for one subtitle."""
    settings = dict(settings or {})
    segment = dict(segment or {})
    stages: dict[str, dict[str, Any]] = {}

    cut_guard = dict(segment.get("_cut_boundary_guard_policy") or {})
    cut_action = str(cut_guard.get("action") or "")
    if cut_action == "clamped_to_cut_scene":
        stages["cut"] = _stage_payload("cut", _score_percent(cut_guard.get("confidence"), 45.0), "red", "cut_boundary_clamped", action=cut_action)
    elif cut_action == "allowed_high_confidence_crossing":
        stages["cut"] = _stage_payload("cut", _score_percent(cut_guard.get("confidence"), 92.0), "green", "high_confidence_crossing_allowed", action=cut_action)
    elif cut_action:
        stages["cut"] = _stage_payload("cut", _score_percent(cut_guard.get("confidence"), 65.0), None, cut_action, action=cut_action)
    elif segment.get("cut_scene_index") is not None or segment.get("cut_scene_start") is not None or segment.get("cut_scene_end") is not None:
        stages["cut"] = _stage_payload("cut", 96.0, "green", "inside_cut_scene")
    else:
        stages["cut"] = _stage_payload("cut", None, "gray", "no_cut_signal")

    stt_scores = [
        _score_percent(segment.get(key))
        for key in ("stt_score", "score", "confidence", "probability", "avg_confidence", "stt_ensemble_similarity")
        if segment.get(key) is not None
    ]
    for candidate in list(segment.get("stt_candidates") or []):
        if isinstance(candidate, dict):
            stt_scores.append(_score_percent(candidate.get("stt_score", candidate.get("score"))))
    lattice = dict(segment.get("_stt_lattice_policy") or {})
    if lattice.get("confidence") is not None:
        stt_scores.append(_score_percent(lattice.get("confidence")))
    stt_score = max((score for score in stt_scores if score is not None), default=None)
    if segment.get("stt_ensemble_needs_llm_review"):
        stt_score = min(stt_score if stt_score is not None else 52.0, 52.0)
    stages["stt"] = _stage_payload(
        "stt",
        stt_score,
        "red" if segment.get("stt_ensemble_needs_llm_review") and (stt_score or 0.0) < 58.0 else None,
        "stt_conflict" if segment.get("stt_ensemble_needs_llm_review") else ("stt_scored" if stt_score is not None else "no_stt_score"),
        candidate_count=len(segment.get("stt_candidates") or []),
        lattice_confidence=lattice.get("confidence"),
    )

    decisions = _decision_items(segment)
    gate = next((item for item in reversed(decisions) if item.get("task") == "llm_gate"), {})
    verifier = dict(segment.get("_llm_verifier_policy") or {})
    if not verifier:
        verifier = next((item for item in reversed(decisions) if item.get("task") == "llm_verifier"), {})
    rollback = dict(segment.get("_llm_rollback_policy") or {})
    if not rollback:
        rollback = next((item for item in reversed(decisions) if item.get("task") == "llm_rollback"), {})
    if rollback:
        stages["llm"] = _stage_payload("llm", 35.0, "red", "llm_rollback", rollback_reason=rollback.get("reason"), fallback=rollback.get("fallback"))
    elif verifier:
        accepted = bool(verifier.get("accepted"))
        score = _score_percent(verifier.get("similarity"), 88.0 if accepted else 42.0)
        stages["llm"] = _stage_payload("llm", score, "green" if accepted else "red", "llm_verified" if accepted else "llm_rejected", verifier_reason=verifier.get("reason"))
    elif gate and gate.get("call_llm") is False:
        stages["llm"] = _stage_payload("llm", _score_percent(gate.get("confidence"), 88.0), "green", "llm_skipped_high_confidence")
    elif gate:
        stages["llm"] = _stage_payload("llm", _score_percent(gate.get("confidence"), 62.0), None, "llm_called", gate_reason=gate.get("reason"))
    else:
        stages["llm"] = _stage_payload("llm", None, "gray", "no_llm_signal")

    lora_profile = dict(segment.get("_lora_generation_profile") or {})
    lora_score = _profile_score(lora_profile)
    has_lora = bool(lora_profile or segment.get("_lora_segment_settings") or segment.get("_lora_segment_score") is not None)
    stages["lora"] = _stage_payload("lora", lora_score if has_lora and lora_score > 0.0 else None, None if has_lora else "gray", "lora_profile" if has_lora else "no_lora_signal", doc_count=segment.get("_lora_segment_doc_count"))

    quality = dict(segment.get("quality") or {})
    final_score = _score_percent(quality.get("confidence_score"))
    final_label = str(quality.get("confidence_label") or "").strip().lower() or None
    auto_review_severity = str(segment.get("subtitle_auto_review_severity") or "").strip().lower()
    if auto_review_severity == "red":
        final_score = min(final_score if final_score is not None else 48.0, 48.0)
        final_label = "red"
    elif auto_review_severity == "yellow" and final_label not in {"red"}:
        final_score = min(final_score if final_score is not None else 72.0, 72.0)
        final_label = "yellow"
    stages["final"] = _stage_payload(
        "final",
        final_score,
        final_label,
        str(quality.get("confidence_reason") or auto_review_severity or "final_quality"),
        auto_review_severity=auto_review_severity,
    )

    known_scores = [float(item.get("score")) for item in stages.values() if isinstance(item.get("score"), (int, float))]
    overall_score = min(known_scores) if known_scores else None
    stage_labels = [str(item.get("label") or "gray") for item in stages.values()]
    if "red" in stage_labels:
        overall_label = "red"
    elif "yellow" in stage_labels:
        overall_label = "yellow"
    elif "green" in stage_labels:
        overall_label = "green"
    else:
        overall_label = "gray"
    return {
        "schema": SUBTITLE_ACCURACY_SCHEMA,
        "task": "subtitle_stage_confidence",
        "overall_score": None if overall_score is None else round(overall_score, 3),
        "overall_label": overall_label,
        "stage_order": ["cut", "stt", "llm", "lora", "final"],
        "stages": stages,
    }


def annotate_subtitle_stage_confidence(segments: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = [dict(segment) for segment in list(segments or []) if isinstance(segment, dict)]
    if not rows:
        return []
    counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
    for row in rows:
        confidence = subtitle_stage_confidence(row, settings)
        label = str(confidence.get("overall_label") or "gray")
        counts[label] = counts.get(label, 0) + 1
        row["subtitle_stage_confidence"] = confidence
        row["subtitle_confidence_label"] = label
        row["subtitle_confidence_score"] = confidence.get("overall_score")
    rows[0]["subtitle_confidence_summary"] = {
        "schema": SUBTITLE_ACCURACY_SCHEMA,
        "task": "subtitle_stage_confidence_summary",
        "total_segments": len(rows),
        "label_counts": counts,
    }
    return rows


def subtitle_completion_report(segments: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the final user-facing subtitle generation report."""
    settings = dict(settings or {})
    rows = [dict(segment) for segment in list(segments or []) if isinstance(segment, dict)]
    metrics = subtitle_accuracy_metrics(rows, settings)
    auto_review = dict(rows[0].get("subtitle_auto_review_summary") or {}) if rows else {}
    if not auto_review:
        auto_review = subtitle_auto_review_summary(rows, settings)
    confidence_summary = dict(rows[0].get("subtitle_confidence_summary") or {}) if rows else {}
    confidence_counts = dict(confidence_summary.get("label_counts") or {})
    total = int(metrics.get("total_segments", len(rows)) or len(rows))
    issue_count = int(auto_review.get("issue_count", 0) or 0)
    severity_counts = dict(auto_review.get("severity_counts") or {})
    red_rows = int(severity_counts.get("red", 0) or 0)
    yellow_rows = int(severity_counts.get("yellow", 0) or 0)
    lora_applied = int(metrics.get("lora_applied_segments", 0) or 0)
    lora_rate = round(lora_applied / max(1, total), 4)
    policy_rollbacks = sum(1 for row in rows if row.get("_llm_rollback_policy") or _has_decision(row, "llm_rollback"))
    rollback_count = max(int(metrics.get("llm_verifier_rollbacks", 0) or 0), int(policy_rollbacks))
    estimated_review_sec = int(auto_review.get("estimated_review_sec", 0) or 0)
    recommended_actions: list[str] = []
    if red_rows:
        recommended_actions.append("Review red auto-review rows first.")
    if rollback_count:
        recommended_actions.append("Check LLM rollback rows against original STT candidates.")
    if int(metrics.get("high_cps_segments", 0) or 0):
        recommended_actions.append("Inspect high-CPS rows for split or timing adjustment.")
    if lora_rate < 0.45 and total >= 5:
        recommended_actions.append("LoRA coverage is low; consider confirming corrected subtitles as ground truth.")
    if not recommended_actions:
        recommended_actions.append("No urgent issues found; spot-check yellow rows if time allows.")
    return {
        "schema": SUBTITLE_ACCURACY_SCHEMA,
        "task": "subtitle_completion_report",
        "total_subtitles": total,
        "auto_review_issue_count": issue_count,
        "red_risk_rows": red_rows,
        "yellow_risk_rows": yellow_rows,
        "llm_rollback_count": rollback_count,
        "lora_applied": lora_applied,
        "lora_application_rate": lora_rate,
        "estimated_review_sec": estimated_review_sec,
        "estimated_review_min": round(estimated_review_sec / 60.0, 2),
        "avg_cps": metrics.get("avg_cps"),
        "avg_quality_score": metrics.get("avg_quality_score"),
        "confidence_label_counts": confidence_counts,
        "metrics": metrics,
        "auto_review": {
            "issue_type_counts": dict(auto_review.get("issue_type_counts") or {}),
            "severity_counts": severity_counts,
        },
        "recommended_actions": recommended_actions,
    }


def annotate_subtitle_completion_report(segments: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = [dict(segment) for segment in list(segments or []) if isinstance(segment, dict)]
    if not rows:
        return []
    rows[0]["subtitle_completion_report"] = subtitle_completion_report(rows, settings)
    return rows


def subtitle_output_variant_score(segments: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = dict(settings or {})
    metrics = subtitle_accuracy_metrics(segments, settings)
    total = max(1, int(metrics.get("total_segments", 0) or 0))
    avg_quality = metrics.get("avg_quality_score")
    quality_score = float(avg_quality) if isinstance(avg_quality, (int, float)) else 62.0
    high_cps_penalty = (float(metrics.get("high_cps_segments", 0) or 0) / total) * 18.0
    long_duration_penalty = (float(metrics.get("over_max_duration_segments", 0) or 0) / total) * 10.0
    rollback_penalty = (float(metrics.get("llm_verifier_rollbacks", 0) or 0) / total) * 16.0
    context_score = metrics.get("context_consistency_score")
    if not isinstance(context_score, (int, float)):
        context_score = 100.0
    context_penalty = max(0.0, 100.0 - float(context_score)) * max(
        0.0,
        _safe_float(settings.get("subtitle_context_score_penalty_weight"), 0.32),
    )
    lora_style_score = metrics.get("lora_style_score")
    if not isinstance(lora_style_score, (int, float)):
        lora_style_score = 100.0
    lora_style_penalty = max(0.0, 100.0 - float(lora_style_score)) * max(
        0.0,
        _safe_float(settings.get("subtitle_lora_style_score_penalty_weight"), 0.22),
    )
    deep_bonus = min(4.0, (float(metrics.get("deep_policy_segments", 0) or 0) / total) * 4.0)
    lora_bonus = min(4.0, (float(metrics.get("lora_applied_segments", 0) or 0) / total) * 4.0)
    score = max(
        0.0,
        min(
            100.0,
            quality_score
            - high_cps_penalty
            - long_duration_penalty
            - rollback_penalty
            - context_penalty
            - lora_style_penalty
            + deep_bonus
            + lora_bonus,
        ),
    )
    return {
        "schema": SUBTITLE_ACCURACY_SCHEMA,
        "task": "output_variant_score",
        "score": round(score, 4),
        "metrics": metrics,
        "penalties": {
            "high_cps": round(high_cps_penalty, 4),
            "over_max_duration": round(long_duration_penalty, 4),
            "llm_rollback": round(rollback_penalty, 4),
            "context_consistency": round(context_penalty, 4),
            "lora_style": round(lora_style_penalty, 4),
        },
        "bonuses": {
            "deep_policy": round(deep_bonus, 4),
            "lora": round(lora_bonus, 4),
        },
    }


def select_best_subtitle_output(
    variants: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Choose the safest subtitle output variant using runtime quality and policy signals."""
    settings = dict(settings or {})
    if not variants:
        return [], _decision("output_variant_selector", selected_index=-1, reason="empty_variants", variants=[])
    if not _safe_bool(settings.get("subtitle_output_selector_enabled"), True):
        first_segments = list(dict(variants[0]).get("segments") or [])
        return first_segments, _decision("output_variant_selector", selected_index=0, reason="disabled", variants=[])

    scored: list[dict[str, Any]] = []
    for index, variant in enumerate(list(variants or [])):
        payload = dict(variant or {})
        segments = list(payload.get("segments") or [])
        score_meta = subtitle_output_variant_score(segments, settings)
        scored.append(
            {
                "index": index,
                "name": str(payload.get("name") or f"variant_{index}"),
                "score": score_meta["score"],
                "score_meta": score_meta,
            }
        )
    scored.sort(key=lambda item: (float(item.get("score", 0.0)), -int(item.get("index", 0))), reverse=True)
    selected = scored[0]
    selected_index = int(selected.get("index", 0))
    return list(dict(variants[selected_index]).get("segments") or []), _decision(
        "output_variant_selector",
        selected_index=selected_index,
        selected_name=selected.get("name"),
        selected_score=selected.get("score"),
        variants=scored,
    )
