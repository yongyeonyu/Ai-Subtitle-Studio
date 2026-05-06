from __future__ import annotations

from typing import Any

from core.personalization.deep_subtitle_policy import DEEP_POLICY_MODEL_ID, DEEP_POLICY_SCHEMA
from core.personalization.lora_models import TrainingQueueItem, iso_now, stable_hash
from core.personalization.lora_storage import append_deep_policy_events, upsert_training_queue_items
from core.personalization.user_edit_metrics import (
    USER_EDIT_METRICS_SCHEMA,
    user_edit_metric_reasons,
)


DEEP_POLICY_EVENT_SCHEMA = "ai_subtitle_studio.deep_policy_event.v1"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _compact_text(text: Any, limit: int = 220) -> str:
    return " ".join(str(text or "").split())[: max(0, int(limit or 0))]


def _segment_features(segment: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or {}
    start = _safe_float(segment.get("start"), 0.0)
    end = _safe_float(segment.get("end"), start)
    duration = max(0.001, end - start)
    text = _compact_text(segment.get("text"), 500)
    char_count = len("".join(text.split()))
    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "duration_sec": round(duration, 3),
        "char_count": int(char_count),
        "cps": round(char_count / duration, 3),
        "speaker": str(segment.get("speaker") or ""),
        "max_cps_setting": settings.get("sub_max_cps"),
        "split_length_threshold": settings.get("split_length_threshold"),
    }


def _profile_summary(segment: dict[str, Any]) -> dict[str, Any]:
    profile = dict(segment.get("_lora_generation_profile") or {})
    return {
        "top_score": profile.get("top_score"),
        "used_kinds": dict(profile.get("used_kinds") or {}),
        "quality_buckets": list(profile.get("quality_buckets") or []),
        "applied_settings": dict(profile.get("applied_settings") or {}),
    }


def _row_score(event_type: str, decision: dict[str, Any], hard_case: bool) -> float:
    if hard_case:
        return 58.0
    if event_type == "decision_explanation":
        lora_score = _safe_float(decision.get("lora_score"), 0.0)
        if lora_score > 0.0:
            return max(55.0, min(96.0, lora_score))
        return 74.0
    if event_type == "stt_candidate_selection":
        return max(60.0, min(95.0, _safe_float(decision.get("score"), 0.7) * 100.0))
    if event_type == "stt_lattice":
        return max(55.0, min(96.0, _safe_float(decision.get("confidence"), 0.65) * 100.0))
    if event_type == "quality_self_review":
        score = decision.get("confidence_score")
        return max(35.0, min(96.0, _safe_float(score, 62.0)))
    if event_type == "subtitle_rerank":
        return max(55.0, min(95.0, _safe_float(decision.get("best_score"), 0.7) * 100.0))
    if event_type == "timing_adjustment":
        shift = abs(_safe_float(decision.get("start_shift"), 0.0)) + abs(_safe_float(decision.get("end_shift"), 0.0))
        return max(45.0, min(88.0, 82.0 - (shift * 35.0)))
    if event_type == "sequence_smoothing":
        return 68.0
    if event_type == "setting_policy":
        return max(55.0, min(95.0, _safe_float(decision.get("confidence"), 0.65) * 100.0))
    if event_type == "llm_gate":
        return max(55.0, min(96.0, _safe_float(decision.get("confidence"), 0.65) * 100.0))
    if event_type == "llm_candidate_policy":
        if decision.get("accepted") is False:
            return 45.0
        reason = str(decision.get("reason") or "")
        if reason == "candidate_match":
            return 90.0
        if reason == "minimal_edit":
            return 78.0
        return 72.0
    if event_type == "llm_verifier":
        return 82.0 if decision.get("accepted") else 48.0
    if event_type == "llm_rollback":
        return 45.0
    if event_type == "output_variant_selector":
        return max(35.0, min(98.0, _safe_float(decision.get("selected_score"), 62.0)))
    if event_type == "context_consistency":
        return max(35.0, min(98.0, _safe_float(decision.get("score"), 72.0)))
    if event_type == "context_repair":
        after = _safe_float(decision.get("after_score"), 72.0)
        before = _safe_float(decision.get("before_score"), after)
        return max(45.0, min(98.0, after + max(0.0, after - before) * 0.2))
    if event_type == "lora_style_consistency":
        return max(35.0, min(98.0, _safe_float(decision.get("score"), 78.0)))
    if event_type == "subtitle_bundle_policy":
        duration = _safe_float(decision.get("duration_sec"), 0.0)
        target = max(1.0, _safe_float(decision.get("target_sec"), 180.0))
        drift = abs(duration - target) / target
        return max(45.0, min(94.0, 88.0 - (drift * 20.0)))
    if event_type == "subtitle_cut_boundary_guard":
        if decision.get("action") == "allowed_high_confidence_crossing":
            return max(55.0, min(98.0, _safe_float(decision.get("confidence"), 96.0)))
        return 72.0
    if event_type == "user_edit_metrics":
        burden = _safe_float(decision.get("edit_burden_score"), 0.0)
        return max(35.0, min(98.0, 96.0 - burden * 0.58))
    if event_type == "hard_case_sample":
        return 42.0
    return 62.0


def _hard_case(event_type: str, decision: dict[str, Any], features: dict[str, Any], settings: dict[str, Any] | None = None) -> bool:
    settings = settings or {}
    margin_threshold = _safe_float(settings.get("deep_policy_hard_case_margin"), 0.08)
    if event_type == "subtitle_rerank" and abs(_safe_float(decision.get("margin"), 0.0)) <= margin_threshold:
        return True
    if event_type == "stt_candidate_selection" and _safe_float(decision.get("margin"), 1.0) <= max(0.12, margin_threshold):
        return True
    if event_type == "stt_lattice" and _safe_float(decision.get("confidence"), 1.0) <= 0.62:
        return True
    if event_type == "quality_self_review":
        label = str(decision.get("confidence_label") or "").lower()
        if label in {"red", "gray"}:
            return True
        if _safe_float(decision.get("confidence_score"), 100.0) < 65.0:
            return True
    if event_type == "setting_policy" and _safe_float(decision.get("confidence"), 1.0) <= 0.45:
        return True
    if event_type == "llm_gate" and _safe_float(decision.get("confidence"), 1.0) <= 0.5:
        return True
    if event_type == "llm_candidate_policy":
        return decision.get("accepted") is False
    if event_type == "llm_verifier" and decision.get("accepted") is False:
        return True
    if event_type == "llm_rollback":
        return True
    if event_type == "output_variant_selector":
        if int(_safe_float(decision.get("selected_index"), 0.0)) > 0:
            return True
        if _safe_float(decision.get("selected_score"), 100.0) < 65.0:
            return True
    if event_type == "context_consistency":
        if decision.get("flags"):
            return True
        if _safe_float(decision.get("score"), 100.0) < 88.0:
            return True
    if event_type == "context_repair":
        return bool(decision.get("applied"))
    if event_type == "lora_style_consistency":
        if decision.get("flags"):
            return True
        if _safe_float(decision.get("score"), 100.0) < 86.0:
            return True
    if event_type == "subtitle_bundle_policy":
        reason = str(decision.get("reason") or "")
        duration = _safe_float(decision.get("duration_sec"), 0.0)
        target = max(1.0, _safe_float(decision.get("target_sec"), 180.0))
        if reason in {"max_sec", "manual_all"}:
            return True
        if duration > target * 1.6 or duration < target * 0.35:
            return True
    if event_type == "subtitle_cut_boundary_guard":
        return decision.get("action") == "clamped_to_cut_scene"
    if event_type == "user_edit_metrics":
        if not decision.get("changed"):
            return False
        text = dict(decision.get("text") or {})
        timing = dict(decision.get("timing") or {})
        split_merge = dict(decision.get("split_merge") or {})
        style = dict(decision.get("style") or {})
        if _safe_float(decision.get("edit_burden_score"), 0.0) >= _safe_float(settings.get("user_edit_metrics_hard_case_score"), 24.0):
            return True
        if _safe_float(text.get("edit_ratio"), 0.0) >= _safe_float(settings.get("user_edit_metrics_text_ratio_hard"), 0.18):
            return True
        if _safe_float(timing.get("move_distance_sec"), 0.0) >= _safe_float(settings.get("user_edit_metrics_timing_shift_hard_sec"), 0.3):
            return True
        if split_merge.get("split_added") or split_merge.get("merge_likely"):
            return True
        if _safe_float(style.get("style_correction_count"), 0.0) >= 2.0:
            return True
        return False
    if event_type == "decision_explanation":
        actions = [str(item or "") for item in list(decision.get("actions") or [])]
        if any(action.startswith("rollback:") or action.startswith("llm_rejected:") for action in actions):
            return True
        if any(action.startswith("lora_style_flags:") for action in actions):
            return True
        if _safe_float(decision.get("lora_score"), 100.0) < 35.0:
            return True
    if event_type == "hard_case_sample":
        return True
    max_cps = _safe_float(settings.get("sub_max_cps"), 12.0)
    if max_cps > 0.0 and _safe_float(features.get("cps"), 0.0) > max_cps * 1.35:
        return True
    return False


def _hard_case_sample_decision(segment: dict[str, Any], features: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or {}
    if not settings.get("deep_hard_case_mining_enabled", True):
        return {}
    reasons: list[str] = []
    quality = dict(segment.get("quality") or {})
    label = str(quality.get("confidence_label") or segment.get("stt_score_label") or "").lower()
    if label in {"red", "yellow", "gray"}:
        reasons.append(f"quality_{label}")
    if segment.get("stt_ensemble_needs_llm_review"):
        reasons.append("stt_ensemble_needs_review")
    lattice = dict(segment.get("_stt_lattice_policy") or {})
    if lattice.get("enabled") and (lattice.get("replacements") or lattice.get("accepted") is False):
        reasons.append("stt_lattice_decision")
    if segment.get("_llm_rollback_policy"):
        reasons.append("llm_rollback")
    if dict(segment.get("_deep_sequence_policy") or {}).get("hard_cases"):
        reasons.append("deep_sequence_hard_case")
    context_policy = dict(segment.get("_context_consistency_policy") or {})
    if context_policy.get("flags"):
        reasons.append("context_consistency_risk")
    repair_policy = dict(segment.get("_context_repair_policy") or {})
    if repair_policy.get("applied"):
        reasons.append("context_repair_applied")
    lora_style_policy = dict(segment.get("_lora_style_policy") or {})
    if lora_style_policy.get("flags"):
        reasons.append("lora_style_drift")
    max_cps = _safe_float(settings.get("sub_max_cps"), 12.0)
    if max_cps > 0.0 and _safe_float(features.get("cps"), 0.0) > max_cps * 1.25:
        reasons.append("high_cps")
    if not reasons:
        return {}
    return {
        "schema": DEEP_POLICY_EVENT_SCHEMA,
        "model": "hard_case_miner_v1",
        "task": "hard_case_sample",
        "reasons": sorted(set(reasons)),
        "quality_label": label,
        "cps": features.get("cps"),
        "stt_lattice": lattice,
        "llm_rollback": dict(segment.get("_llm_rollback_policy") or {}),
    }


def _event_row(
    *,
    event_type: str,
    segment: dict[str, Any],
    decision: dict[str, Any],
    settings: dict[str, Any] | None,
    media_id: str = "",
    media_path: str = "",
) -> dict[str, Any]:
    features = _segment_features(segment, settings)
    hard_case = _hard_case(event_type, decision, features, settings)
    text = _compact_text(segment.get("text"), 500)
    row = {
        "schema": DEEP_POLICY_EVENT_SCHEMA,
        "deep_policy_schema": DEEP_POLICY_SCHEMA,
        "model": decision.get("model") or decision.get("selector") or DEEP_POLICY_MODEL_ID,
        "event_type": event_type,
        "media_id": str(media_id or segment.get("media_id") or segment.get("_media_id") or ""),
        "media_path": str(media_path or segment.get("media_path") or segment.get("_media_path") or ""),
        "segment_id": str(segment.get("segment_id") or segment.get("id") or ""),
        "text": text,
        "decision": dict(decision or {}),
        "features": features,
        "profile": _profile_summary(segment),
        "applied_settings": dict(segment.get("_lora_segment_settings") or {}),
        "hard_case": hard_case,
        "score": _row_score(event_type, decision, hard_case),
        "captured_at": iso_now(),
    }
    row["event_id"] = stable_hash(
        {
            "event_type": event_type,
            "media_id": row["media_id"],
            "media_path": row["media_path"],
            "segment_id": row["segment_id"],
            "start": features.get("start"),
            "end": features.get("end"),
            "text": text,
            "decision": decision,
        }
    )[:24]
    return row


def build_deep_policy_event_rows(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    *,
    media_id: str = "",
    media_path: str = "",
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    settings = dict(settings or {})
    limit = max(1, int(max_rows if max_rows is not None else settings.get("deep_policy_event_max_rows_per_run", 512) or 512))
    rows: list[dict[str, Any]] = []
    for segment in list(segments or []):
        if not isinstance(segment, dict):
            continue
        stt_decision = {
            "source": segment.get("stt_ensemble_deep_selected_source"),
            "label": segment.get("stt_ensemble_deep_selected_label"),
            "score": segment.get("stt_ensemble_deep_selected_score"),
            "margin": segment.get("stt_ensemble_deep_selected_margin"),
            "selector": DEEP_POLICY_MODEL_ID,
        }
        if stt_decision.get("source"):
            rows.append(_event_row(event_type="stt_candidate_selection", segment=segment, decision=stt_decision, settings=settings, media_id=media_id, media_path=media_path))
        lattice = dict(segment.get("_stt_lattice_policy") or {})
        if lattice:
            rows.append(_event_row(event_type="stt_lattice", segment=segment, decision=lattice, settings=settings, media_id=media_id, media_path=media_path))
        quality = dict(segment.get("quality") or {})
        quality_enabled = settings.get("deep_quality_event_logging_enabled", True)
        if isinstance(quality_enabled, str):
            quality_enabled = quality_enabled.strip().lower() not in {"0", "false", "off", "no", "끔"}
        if quality and quality_enabled:
            all_quality = bool(settings.get("deep_quality_event_all_segments", False))
            label = str(quality.get("confidence_label") or "").lower()
            score = _safe_float(quality.get("confidence_score"), 100.0)
            if all_quality or label in {"yellow", "red", "gray"} or score < _safe_float(settings.get("deep_quality_event_min_score"), 85.0):
                rows.append(_event_row(event_type="quality_self_review", segment=segment, decision=quality, settings=settings, media_id=media_id, media_path=media_path))
        rerank = dict(segment.get("_deep_rerank_policy") or {})
        if rerank:
            rows.append(_event_row(event_type="subtitle_rerank", segment=segment, decision=rerank, settings=settings, media_id=media_id, media_path=media_path))
        timing = dict(segment.get("_deep_timing_policy") or {})
        if timing:
            rows.append(_event_row(event_type="timing_adjustment", segment=segment, decision=timing, settings=settings, media_id=media_id, media_path=media_path))
        sequence = dict(segment.get("_deep_sequence_policy") or {})
        if sequence:
            rows.append(_event_row(event_type="sequence_smoothing", segment=segment, decision=sequence, settings=settings, media_id=media_id, media_path=media_path))
        context_policy = dict(segment.get("_context_consistency_policy") or {})
        if context_policy:
            rows.append(_event_row(event_type="context_consistency", segment=segment, decision=context_policy, settings=settings, media_id=media_id, media_path=media_path))
        lora_style_policy = dict(segment.get("_lora_style_policy") or {})
        if lora_style_policy:
            rows.append(_event_row(event_type="lora_style_consistency", segment=segment, decision=lora_style_policy, settings=settings, media_id=media_id, media_path=media_path))
        repair_policy = dict(segment.get("_context_repair_policy") or {})
        if repair_policy:
            rows.append(_event_row(event_type="context_repair", segment=segment, decision=repair_policy, settings=settings, media_id=media_id, media_path=media_path))
        output_selector = dict(segment.get("_output_selector_policy") or {})
        if output_selector:
            rows.append(_event_row(event_type="output_variant_selector", segment=segment, decision=output_selector, settings=settings, media_id=media_id, media_path=media_path))
        bundle_policy = dict(segment.get("_subtitle_bundle_policy") or {})
        if bundle_policy:
            rows.append(_event_row(event_type="subtitle_bundle_policy", segment=segment, decision=bundle_policy, settings=settings, media_id=media_id, media_path=media_path))
        cut_guard = dict(segment.get("_cut_boundary_guard_policy") or {})
        if cut_guard:
            rows.append(_event_row(event_type="subtitle_cut_boundary_guard", segment=segment, decision=cut_guard, settings=settings, media_id=media_id, media_path=media_path))
        user_edit_metrics = dict(segment.get("_user_edit_metrics") or segment.get("user_edit_metrics") or {})
        if user_edit_metrics:
            rows.append(_event_row(event_type="user_edit_metrics", segment=segment, decision=user_edit_metrics, settings=settings, media_id=media_id, media_path=media_path))
        candidate_policy = dict(segment.get("_llm_candidate_policy") or {})
        emitted_candidate_policy = False
        if candidate_policy:
            rows.append(_event_row(event_type="llm_candidate_policy", segment=segment, decision=candidate_policy, settings=settings, media_id=media_id, media_path=media_path))
            emitted_candidate_policy = True
        profile = dict(segment.get("_lora_generation_profile") or {})
        setting_policy = dict(profile.get("_deep_setting_policy") or {})
        if setting_policy:
            rows.append(_event_row(event_type="setting_policy", segment=segment, decision=setting_policy, settings=settings, media_id=media_id, media_path=media_path))
        accuracy_graph = dict(segment.get("_accuracy_decision_graph") or {})
        for decision in list(accuracy_graph.get("decisions") or []):
            if not isinstance(decision, dict):
                continue
            event_type = str(decision.get("task") or "accuracy_decision")
            if event_type == "llm_candidate_policy" and emitted_candidate_policy:
                continue
            if event_type not in {"llm_gate", "llm_candidate_policy", "llm_verifier", "llm_rollback", "output_variant_selector", "context_consistency", "context_repair", "lora_style_consistency", "subtitle_bundle_policy"}:
                event_type = "accuracy_decision"
            rows.append(_event_row(event_type=event_type, segment=segment, decision=decision, settings=settings, media_id=media_id, media_path=media_path))
            if len(rows) >= limit:
                return rows[:limit]
        explanation_enabled = settings.get("subtitle_decision_explanation_logging_enabled", True)
        if isinstance(explanation_enabled, str):
            explanation_enabled = explanation_enabled.strip().lower() not in {"0", "false", "off", "no", "끔"}
        if explanation_enabled:
            try:
                from core.engine.subtitle_accuracy_pipeline import subtitle_decision_explanations

                explanations = subtitle_decision_explanations([segment])
            except Exception:
                explanations = []
            if explanations:
                explanation = dict(explanations[0])
                explanation["model"] = "decision_explainer_v1"
                rows.append(
                    _event_row(
                        event_type="decision_explanation",
                        segment=segment,
                        decision=explanation,
                        settings=settings,
                        media_id=media_id,
                        media_path=media_path,
                    )
                )
                if len(rows) >= limit:
                    return rows[:limit]
        hard_case_decision = _hard_case_sample_decision(segment, _segment_features(segment, settings), settings)
        if hard_case_decision:
            rows.append(_event_row(event_type="hard_case_sample", segment=segment, decision=hard_case_decision, settings=settings, media_id=media_id, media_path=media_path))
        if len(rows) >= limit:
            return rows[:limit]
    return rows[:limit]


def _queue_priority(row: dict[str, Any]) -> int:
    event_type = str(row.get("event_type") or "")
    decision = dict(row.get("decision") or {})
    features = dict(row.get("features") or {})
    if event_type in {"llm_rollback", "llm_verifier", "llm_candidate_policy"}:
        return 5
    if event_type == "user_edit_metrics":
        severity = str(decision.get("severity") or "")
        if severity == "large":
            return 6
        if severity == "medium":
            return 12
        return 24
    if event_type in {"stt_candidate_selection", "stt_lattice"}:
        return 8
    if _safe_float(features.get("cps"), 0.0) > _safe_float(features.get("max_cps_setting"), 12.0) * 1.35:
        return 10
    if event_type in {"context_consistency", "context_repair", "lora_style_consistency"}:
        return 15
    if event_type == "quality_self_review":
        label = str(decision.get("confidence_label") or "").lower()
        return 12 if label in {"red", "gray"} else 20
    return 30


def _queue_reasons(row: dict[str, Any]) -> list[str]:
    decision = dict(row.get("decision") or {})
    features = dict(row.get("features") or {})
    reasons: list[str] = [str(row.get("event_type") or "hard_case")]
    for key in ("reason", "fallback"):
        if decision.get(key):
            reasons.append(str(decision.get(key)))
    for item in list(decision.get("reasons") or []):
        if str(item or "").strip():
            reasons.append(str(item))
    for item in list(decision.get("flags") or []):
        if str(item or "").strip():
            reasons.append(str(item))
    if str(row.get("event_type") or "") == "user_edit_metrics":
        reasons.extend(user_edit_metric_reasons(decision))
    max_cps = _safe_float(features.get("max_cps_setting"), 12.0)
    if max_cps > 0.0 and _safe_float(features.get("cps"), 0.0) > max_cps * 1.25:
        reasons.append("high_cps")
    return sorted(set(reasons))


def build_hard_case_training_queue_items(
    rows: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    settings = dict(settings or {})
    if not settings.get("hardcase_training_queue_enabled", True):
        return []
    limit = max(1, int(settings.get("hardcase_training_queue_max_items_per_run", 128) or 128))
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted((dict(item) for item in list(rows or []) if isinstance(item, dict) and item.get("hard_case")), key=_queue_priority):
        event_id = str(row.get("event_id") or "")
        if not event_id or event_id in seen:
            continue
        seen.add(event_id)
        features = dict(row.get("features") or {})
        payload = {
            "schema": "ai_subtitle_studio.hard_case_training_payload.v1",
            "event_id": event_id,
            "event_type": row.get("event_type"),
            "segment_id": row.get("segment_id"),
            "text": row.get("text"),
            "start": features.get("start"),
            "end": features.get("end"),
            "features": features,
            "decision": dict(row.get("decision") or {}),
            "profile": dict(row.get("profile") or {}),
            "applied_settings": dict(row.get("applied_settings") or {}),
            "hard_case_reasons": _queue_reasons(row),
        }
        items.append(
            TrainingQueueItem(
                media_id=str(row.get("media_id") or ""),
                media_path=str(row.get("media_path") or ""),
                subtitle_path="",
                job_type="hard_case_subtitle_policy",
                job_id=f"hardcase-{event_id}",
                priority=_queue_priority(row),
                score=row.get("score"),
                payload=payload,
            ).to_record()
        )
        if len(items) >= limit:
            break
    return items


def build_user_edit_metric_event_rows(
    truth_rows: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    *,
    media_id: str = "",
    media_path: str = "",
) -> list[dict[str, Any]]:
    settings = dict(settings or {})
    rows: list[dict[str, Any]] = []
    for truth in list(truth_rows or []):
        if not isinstance(truth, dict):
            continue
        metrics = dict(truth.get("user_edit_metrics") or {})
        if not metrics:
            continue
        segment = {
            "media_id": str(media_id or truth.get("media_id") or ""),
            "media_path": str(media_path or truth.get("media_path") or ""),
            "segment_id": str(truth.get("segment_id") or ""),
            "start": truth.get("start_sec"),
            "end": truth.get("end_sec"),
            "text": truth.get("speech_training_text") or truth.get("raw_ground_truth_text") or "",
            "_user_edit_metrics": metrics,
            "_lora_segment_settings": dict(truth.get("settings_snapshot") or {}),
            "_lora_generation_profile": {
                "top_score": truth.get("score"),
                "used_kinds": {"truth_table": 1},
                "applied_settings": dict(truth.get("settings_snapshot") or {}),
            },
        }
        rows.append(
            _event_row(
                event_type="user_edit_metrics",
                segment=segment,
                decision=metrics,
                settings=settings,
                media_id=media_id,
                media_path=media_path,
            )
        )
    return rows


def record_user_edit_metric_events_for_truth_rows(
    truth_rows: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    *,
    store_dir: str | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    enabled = settings.get("user_edit_metrics_deep_event_enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"0", "false", "off", "no", "끔"}
    if not enabled:
        return {"status": "disabled", "appended_rows": 0, "queued_hard_cases": 0}
    rows = build_user_edit_metric_event_rows(truth_rows, settings)
    if not rows:
        return {"status": "empty", "appended_rows": 0, "queued_hard_cases": 0}
    result = append_deep_policy_events(rows, store_dir)
    queue_items = build_hard_case_training_queue_items(rows, settings)
    queue_result = upsert_training_queue_items(queue_items, store_dir) if queue_items else {}
    return {
        "status": "recorded",
        **dict(result or {}),
        "queued_hard_cases": len(queue_items),
        "training_queue_count": len(list((queue_result or {}).get("items") or [])) if queue_result else 0,
    }


def record_deep_policy_events_for_segments(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    *,
    media_id: str = "",
    media_path: str = "",
    store_dir: str | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    enabled = settings.get("deep_policy_event_logging_enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"0", "false", "off", "no", "끔"}
    if not enabled:
        return {"status": "disabled", "appended_rows": 0}
    rows = build_deep_policy_event_rows(segments, settings, media_id=media_id, media_path=media_path)
    if not rows:
        return {"status": "empty", "appended_rows": 0}
    try:
        result = append_deep_policy_events(rows, store_dir)
        queue_items = build_hard_case_training_queue_items(rows, settings)
        queue_result = upsert_training_queue_items(queue_items, store_dir) if queue_items else {}
        return {
            "status": "recorded",
            **dict(result or {}),
            "queued_hard_cases": len(queue_items),
            "training_queue_count": len(list((queue_result or {}).get("items") or [])) if queue_result else 0,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc), "appended_rows": 0}


__all__ = [
    "DEEP_POLICY_EVENT_SCHEMA",
    "USER_EDIT_METRICS_SCHEMA",
    "build_deep_policy_event_rows",
    "build_hard_case_training_queue_items",
    "build_user_edit_metric_event_rows",
    "record_deep_policy_events_for_segments",
    "record_user_edit_metric_events_for_truth_rows",
]
