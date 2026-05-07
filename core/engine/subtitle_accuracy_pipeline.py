from __future__ import annotations

import difflib
import re
from collections import Counter
from statistics import median
from time import time
from typing import Any, Iterable

from core.engine.llm_correction_guard import contains_timecode, normalized_text, validate_llm_chunks


SUBTITLE_ACCURACY_SCHEMA = "ai_subtitle_studio.subtitle_accuracy_pipeline.v1"
CONTEXT_CONSISTENCY_MODEL_ID = "context_sequence_heuristic_v1"
LORA_STYLE_MODEL_ID = "lora_style_drift_heuristic_v1"

_HALLUCINATION_PHRASES = (
    "한국어 대화",
    "자막 생성",
    "번역 중",
    "처리 중",
    "대화 내용",
    "Korean conversation",
    "subtitle",
    "transcription",
    "Thank you for watching",
)
_NUMBER_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*(?:[%％]|[A-Za-z가-힣]+)?")
_LATIN_PROPER_TOKEN_RE = re.compile(
    r"\b(?:[A-Z]{2,}[A-Za-z0-9-]*|[A-Za-z]+[0-9][A-Za-z0-9-]*|[A-Z][a-z]+(?:[A-Z][a-z]+)+)\b"
)
_CONTENT_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_INTERJECTION_TOKENS = {
    "아",
    "어",
    "음",
    "오",
    "와",
    "우와",
    "헉",
    "어머",
    "아니",
    "아이",
    "흠",
}


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(round(float(value)))
    except Exception:
        return int(default)


def compact_len(text: Any) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def _compact_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def _clean_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _line_count(text: Any) -> int:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return max(1, len(lines))


def _profile_examples(profile: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    for item in list((profile or {}).get("examples") or []):
        if isinstance(item, str):
            text = _clean_text(item)
            if text:
                out.append(text)
            continue
        if not isinstance(item, dict):
            continue
        for key in ("output", "corrected", "subtitle", "text", "input"):
            text = _clean_text(item.get(key))
            if text:
                out.append(text)
                break
    return out


def _walk_profile_values(value: Any, keys: set[str]) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in keys:
                if isinstance(child, str):
                    out.append(child)
                elif isinstance(child, (list, tuple, set)):
                    out.extend(str(item) for item in child if str(item or "").strip())
            out.extend(_walk_profile_values(child, keys))
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            out.extend(_walk_profile_values(child, keys))
    return out


def _number_tokens(text: Any) -> list[str]:
    return [normalized_text(token) for token in _NUMBER_TOKEN_RE.findall(str(text or "")) if normalized_text(token)]


def _profile_brand_tokens(profile: dict[str, Any] | None) -> set[str]:
    keys = {"brand_tokens", "brand_name_tokens", "brand_names", "proper_nouns"}
    return {normalized_text(token) for token in _walk_profile_values(profile or {}, keys) if normalized_text(token)}


def _proper_noun_tokens(text: Any, profile: dict[str, Any] | None = None) -> set[str]:
    tokens = {normalized_text(token) for token in _LATIN_PROPER_TOKEN_RE.findall(str(text or "")) if normalized_text(token)}
    profile_tokens = _profile_brand_tokens(profile)
    compact = normalized_text(str(text or ""))
    tokens.update(token for token in profile_tokens if token and token in compact)
    return tokens


def _interjection_tokens(text: Any) -> set[str]:
    raw_tokens = [normalized_text(token) for token in _CONTENT_TOKEN_RE.findall(str(text or ""))]
    return {token for token in raw_tokens if token in _INTERJECTION_TOKENS}


def _content_tokens(text: Any) -> set[str]:
    return {normalized_text(token) for token in _CONTENT_TOKEN_RE.findall(str(text or "")) if len(normalized_text(token)) >= 2}


def _token_is_supported_by_source(token: str, source_norm: str, source_tokens: set[str]) -> bool:
    if not token:
        return True
    if token in source_norm:
        return True
    for source_token in source_tokens:
        if len(source_token) >= 2 and (source_token in token or token in source_token):
            return True
    return False


def llm_source_preservation_violations(
    source_text: str,
    candidate_text: str,
    settings: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return concrete reasons an LLM output changed source facts or style anchors."""
    settings = dict(settings or {})
    source = str(source_text or "")
    candidate = str(candidate_text or "")
    source_norm = normalized_text(source)
    candidate_norm = normalized_text(candidate)
    violations: list[dict[str, Any]] = []

    if _safe_bool(settings.get("llm_verifier_preserve_numbers"), True):
        source_numbers = Counter(_number_tokens(source))
        candidate_numbers = Counter(_number_tokens(candidate))
        if source_numbers != candidate_numbers:
            violations.append(
                {
                    "type": "number_changed",
                    "source_numbers": sorted(source_numbers.elements()),
                    "candidate_numbers": sorted(candidate_numbers.elements()),
                }
            )

    if _safe_bool(settings.get("llm_verifier_preserve_proper_nouns"), True):
        source_proper = _proper_noun_tokens(source, profile)
        candidate_proper = _proper_noun_tokens(candidate, profile)
        missing = sorted(token for token in source_proper if token not in candidate_norm)
        added = sorted(token for token in candidate_proper if token not in source_norm)
        if missing or added:
            violations.append({"type": "proper_noun_changed", "missing": missing, "added": added})

    if _safe_bool(settings.get("llm_verifier_preserve_interjections"), True):
        source_interjections = _interjection_tokens(source)
        missing_interjections = sorted(token for token in source_interjections if token not in candidate_norm)
        if missing_interjections:
            violations.append({"type": "interjection_deleted", "missing": missing_interjections})

    if _safe_bool(settings.get("llm_verifier_block_added_content_tokens"), True):
        source_tokens = _content_tokens(source)
        candidate_tokens = _content_tokens(candidate)
        added_content = sorted(
            token
            for token in candidate_tokens
            if token not in _INTERJECTION_TOKENS
            and token not in _profile_brand_tokens(profile)
            and not _token_is_supported_by_source(token, source_norm, source_tokens)
        )
        if added_content:
            violations.append({"type": "added_content_token", "added": added_content[:8]})

    return violations


def _profile_exclusions(profile: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    for key in ("exclusions", "excluded_parentheticals"):
        for item in list((profile or {}).get(key) or []):
            if isinstance(item, str):
                text = _clean_text(item)
            elif isinstance(item, dict):
                text = _clean_text(item.get("text") or item.get("phrase") or item.get("value"))
            else:
                text = ""
            if text:
                out.append(text)
    return out


def _profile_example_cps_values(profile: dict[str, Any] | None) -> list[float]:
    values: list[float] = []
    for item in list((profile or {}).get("examples") or []):
        if not isinstance(item, dict):
            continue
        cps = _safe_float(item.get("cps"), 0.0)
        if cps > 0.0:
            values.append(cps)
            continue
        text = ""
        for key in ("output", "corrected", "subtitle", "text", "input"):
            text = _clean_text(item.get(key))
            if text:
                break
        start = _safe_float(item.get("start"), 0.0)
        end = _safe_float(item.get("end"), start)
        duration = max(0.0, end - start)
        if text and duration > 0.05:
            values.append(compact_len(text) / duration)
    return values


def _placeholder_hallucination_phrase(text: Any) -> str:
    normalized = normalized_text(str(text or ""))
    if not normalized:
        return ""
    for phrase in _HALLUCINATION_PHRASES:
        phrase_norm = normalized_text(str(phrase or ""))
        if not phrase_norm:
            continue
        if normalized == phrase_norm:
            return str(phrase)
        if phrase_norm in normalized and len(normalized) <= len(phrase_norm) + 4:
            return str(phrase)
    return ""


def _segment_duration(segment: dict[str, Any]) -> float:
    start = _safe_float(segment.get("start"), 0.0)
    end = _safe_float(segment.get("end"), start)
    return max(0.0, end - start)


def _segment_scope_key(segment: dict[str, Any]) -> tuple[str, str] | None:
    clip_idx = segment.get("_clip_idx")
    if clip_idx is not None:
        return ("clip_idx", str(clip_idx))
    clip_file = segment.get("_clip_file") or segment.get("clip_file")
    if clip_file:
        return ("clip_file", str(clip_file))
    return None


def _same_scope(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if not left or not right:
        return False
    left_key = _segment_scope_key(left)
    right_key = _segment_scope_key(right)
    if left_key is None and right_key is None:
        return True
    return left_key == right_key


def _profile_score(profile: dict[str, Any] | None) -> float:
    profile = dict(profile or {})
    scores = [
        _safe_float(profile.get("top_score"), 0.0),
        _safe_float(profile.get("truth_score"), 0.0),
    ]
    for source in list(profile.get("setting_sources") or []):
        if isinstance(source, dict):
            scores.append(_safe_float(source.get("score"), 0.0))
    for example in list(profile.get("examples") or []):
        if isinstance(example, dict):
            scores.append(_safe_float(example.get("score"), 0.0))
    return max(scores, default=0.0)


def _confidence_to_100(value: Any) -> float:
    score = _safe_float(value, 0.0)
    if score <= 1.0:
        score *= 100.0
    return max(0.0, min(100.0, score))


def _segment_signal_scores(segment: dict[str, Any]) -> dict[str, float]:
    deep_policy = dict(segment.get("_deep_candidate_selector_policy") or {})
    lattice_policy = dict(segment.get("_stt_lattice_policy") or {})
    scores = {
        "deep_score": max(
            _confidence_to_100(deep_policy.get("confidence")),
            _confidence_to_100(deep_policy.get("score")),
            _confidence_to_100(segment.get("stt_ensemble_deep_selected_score")),
        ),
        "stt_lattice_score": _confidence_to_100(lattice_policy.get("confidence")),
        "stt_score": _confidence_to_100(segment.get("score", segment.get("stt_score"))),
    }
    scores["combined_signal_score"] = max(scores.values(), default=0.0)
    return scores


def _decision(task: str, **payload: Any) -> dict[str, Any]:
    return {
        "schema": SUBTITLE_ACCURACY_SCHEMA,
        "task": task,
        "created_epoch": round(time(), 3),
        **payload,
    }


def _severity_rank(severity: Any) -> int:
    order = {"info": 1, "yellow": 2, "red": 3}
    return order.get(str(severity or "").strip().lower(), 0)


def _review_reason(issue_type: str, severity: str, message: str, **evidence: Any) -> dict[str, Any]:
    clean_evidence = {key: value for key, value in evidence.items() if value not in (None, "", [], {})}
    return {
        "type": str(issue_type),
        "severity": str(severity),
        "message": str(message),
        "evidence": clean_evidence,
    }


def _candidate_text_conflict(segment: dict[str, Any], *, min_similarity: float = 0.9) -> dict[str, Any] | None:
    texts = []
    for candidate in list(segment.get("stt_candidates") or []):
        if not isinstance(candidate, dict):
            continue
        text = _clean_text(candidate.get("text"))
        if text:
            texts.append(text)
    texts = list(dict.fromkeys(texts))
    if len(texts) < 2:
        return None
    compact = [_compact_text(text) for text in texts if _compact_text(text)]
    if len(set(compact)) < 2:
        return None
    best_similarity = 0.0
    for left_index, left in enumerate(compact):
        for right in compact[left_index + 1:]:
            best_similarity = max(best_similarity, difflib.SequenceMatcher(None, left, right).ratio())
    if best_similarity >= min_similarity:
        return None
    return {
        "candidate_count": len(texts),
        "best_similarity": round(best_similarity, 4),
        "examples": texts[:3],
    }


def _decision_items(segment: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in list(dict(segment.get("_accuracy_decision_graph") or {}).get("decisions") or [])
        if isinstance(item, dict)
    ]


def _has_decision(segment: dict[str, Any], task: str, *, accepted: bool | None = None) -> bool:
    for decision in _decision_items(segment):
        if decision.get("task") != task:
            continue
        if accepted is None or bool(decision.get("accepted")) == accepted:
            return True
    return False


def _deep_hard_case_reasons(segment: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    sequence = dict(segment.get("_deep_sequence_policy") or {})
    if sequence.get("hard_cases"):
        reasons.append("deep_sequence_hard_case")
    for key, value in segment.items():
        if not (str(key).startswith("_deep_") and str(key).endswith("_policy")):
            continue
        policy = dict(value or {})
        for item in list(policy.get("changes") or []):
            if isinstance(item, dict) and "hard_case" in str(item.get("type") or ""):
                reasons.append(str(item.get("type")))
        if policy.get("hard_case"):
            reasons.append(str(policy.get("task") or key))
    return sorted(set(reasons))


def _stage_score_to_label(score: float | None) -> str:
    if score is None:
        return "gray"
    value = max(0.0, min(100.0, float(score)))
    if value >= 82.0:
        return "green"
    if value >= 58.0:
        return "yellow"
    return "red"


def _score_percent(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        score = float(value)
    except Exception:
        return default
    if 0.0 <= score <= 1.0:
        score *= 100.0
    return max(0.0, min(100.0, score))


def _stage_payload(stage: str, score: float | None, label: str | None = None, reason: str = "", **evidence: Any) -> dict[str, Any]:
    clean_evidence = {key: value for key, value in evidence.items() if value not in (None, "", [], {})}
    final_label = str(label or _stage_score_to_label(score))
    return {
        "stage": str(stage),
        "score": None if score is None else round(float(score), 3),
        "label": final_label,
        "reason": str(reason or final_label),
        "evidence": clean_evidence,
    }


def llm_gate_decision(
    segment: dict[str, Any],
    settings: dict[str, Any] | None,
    profile: dict[str, Any] | None,
    *,
    text: str,
    threshold: int,
    duration: float | None = None,
) -> dict[str, Any]:
    """Decide whether a subtitle segment really needs an LLM split/correction call."""
    settings = dict(settings or {})
    profile = dict(profile or {})
    if not _safe_bool(settings.get("llm_confidence_gate_enabled"), True):
        return _decision("llm_gate", call_llm=True, reason="disabled", reasons=["disabled"], confidence=0.0)

    threshold = max(1, _safe_int(threshold or settings.get("split_length_threshold"), 10))
    duration_sec = _safe_float(duration, _segment_duration(segment))
    chars = compact_len(text)
    ratio = chars / max(1, threshold)
    lora_score = _profile_score(profile)
    signal_scores = _segment_signal_scores(segment)
    combined_signal_score = max(lora_score, signal_scores.get("combined_signal_score", 0.0))
    min_lora_score = _safe_float(settings.get("llm_confidence_gate_min_lora_score"), 82.0)
    max_compact_ratio = max(1.0, _safe_float(settings.get("llm_confidence_gate_max_compact_ratio"), 1.45))
    max_duration = max(0.3, _safe_float(settings.get("sub_max_duration"), 6.0))

    reasons: list[str] = []
    if not str(text or "").strip():
        reasons.append("empty_text")
    if chars > int(threshold * max_compact_ratio):
        reasons.append("long_text_needs_llm")
    if duration_sec > max_duration * 1.08:
        reasons.append("long_duration_needs_llm")
    if segment.get("stt_ensemble_needs_llm_review"):
        reasons.append("stt_candidate_uncertain")
    if contains_timecode(text):
        reasons.append("timecode_noise")
    if any(phrase in str(text or "") for phrase in _HALLUCINATION_PHRASES):
        reasons.append("hallucination_phrase_in_source")
    if combined_signal_score < min_lora_score:
        reasons.append("low_lora_score")

    call_llm = bool(reasons)
    if "empty_text" in reasons:
        call_llm = False

    confidence = 0.35
    if not call_llm:
        score_part = min(0.35, max(0.0, (combined_signal_score - min_lora_score) / 100.0))
        length_part = max(0.0, min(0.25, (max_compact_ratio - min(ratio, max_compact_ratio)) / max_compact_ratio))
        duration_part = max(0.0, min(0.18, (max_duration - min(duration_sec, max_duration)) / max_duration))
        confidence = min(0.98, 0.42 + score_part + length_part + duration_part)

    reason = "call_llm:" + ",".join(reasons) if call_llm else "skip_llm:high_lora_deep_stt_confidence"
    return _decision(
        "llm_gate",
        call_llm=call_llm,
        reason=reason,
        reasons=reasons,
        confidence=round(confidence, 4),
        compact_len=chars,
        threshold=threshold,
        compact_ratio=round(ratio, 4),
        duration_sec=round(duration_sec, 4),
        lora_score=round(lora_score, 4),
        deep_score=round(signal_scores.get("deep_score", 0.0), 4),
        stt_lattice_score=round(signal_scores.get("stt_lattice_score", 0.0), 4),
        stt_score=round(signal_scores.get("stt_score", 0.0), 4),
        combined_signal_score=round(combined_signal_score, 4),
        min_lora_score=round(min_lora_score, 4),
        max_compact_ratio=round(max_compact_ratio, 4),
    )


def llm_minimize_decision(
    segment: dict[str, Any],
    settings: dict[str, Any] | None,
    gate_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    """Record the explicit LLM cost/accuracy decision after the confidence gate."""
    settings = dict(settings or {})
    gate = dict(gate_decision or {})
    if not _safe_bool(settings.get("llm_minimize_enabled"), True):
        return _decision("llm_minimize", enabled=False, skip_llm=False, reason="disabled")

    call_llm = bool(gate.get("call_llm", True))
    confidence = _safe_float(gate.get("confidence"), 0.0)
    combined_signal = _safe_float(gate.get("combined_signal_score"), 0.0)
    min_confidence = _safe_float(settings.get("llm_minimize_min_gate_confidence"), 0.74)
    required_signal = _safe_float(settings.get("llm_minimize_required_signal_score"), _safe_float(settings.get("llm_confidence_gate_min_lora_score"), 82.0))
    uncertainty = dict(segment.get("_uncertainty_policy") or {})
    uncertainty_bucket = str(uncertainty.get("bucket") or "")

    if call_llm:
        return _decision(
            "llm_minimize",
            enabled=True,
            skip_llm=False,
            avoided_call=False,
            reason="gate_requested_llm",
            gate_reason=gate.get("reason"),
            confidence=round(confidence, 4),
            combined_signal_score=round(combined_signal, 4),
            uncertainty_bucket=uncertainty_bucket,
        )

    strong_skip = confidence >= min_confidence and combined_signal >= required_signal
    empty_skip = "empty_text" in list(gate.get("reasons") or [])
    reason = "skip_llm:strong_lora_deep_signal" if strong_skip else "skip_llm:gate_safe"
    if empty_skip:
        reason = "skip_llm:empty_text"

    return _decision(
        "llm_minimize",
        enabled=True,
        skip_llm=True,
        avoided_call=True,
        reason=reason,
        confidence=round(confidence, 4),
        min_confidence=round(min_confidence, 4),
        combined_signal_score=round(combined_signal, 4),
        required_signal_score=round(required_signal, 4),
        strong_skip=bool(strong_skip),
        uncertainty_bucket=uncertainty_bucket,
        gate_reason=gate.get("reason"),
    )


def _clean_chunks(chunks: Iterable[str] | None) -> list[str]:
    return [str(chunk or "").strip() for chunk in list(chunks or []) if str(chunk or "").strip()]


def verify_llm_chunks_for_subtitle(
    source_text: str,
    chunks: Iterable[str] | None,
    settings: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> tuple[list[str] | None, dict[str, Any]]:
    """Validate LLM output and return None when the engine should roll back to safe splitting."""
    settings = dict(settings or {})
    cleaned = _clean_chunks(chunks)
    source_norm = normalized_text(source_text)
    candidate_norm = normalized_text("".join(cleaned))
    similarity = difflib.SequenceMatcher(None, source_norm, candidate_norm).ratio() if source_norm and candidate_norm else 0.0
    length_delta = abs(len(candidate_norm) - len(source_norm)) / max(1, len(source_norm)) if source_norm else 1.0
    base_meta = {
        "chunk_count": len(cleaned),
        "source_compact_len": len(source_norm),
        "candidate_compact_len": len(candidate_norm),
        "similarity": round(similarity, 4),
        "length_delta_ratio": round(length_delta, 4),
        "lora_score": round(_profile_score(profile), 4),
    }
    if not _safe_bool(settings.get("llm_verifier_enabled"), True):
        return cleaned or None, _decision("llm_verifier", accepted=bool(cleaned), reason="disabled", **base_meta)

    max_chunks = max(1, _safe_int(settings.get("llm_verifier_max_chunks"), 8))
    if not cleaned:
        return None, _decision("llm_verifier", accepted=False, reason="empty_chunks", **base_meta)
    if len(cleaned) > max_chunks:
        return None, _decision("llm_verifier", accepted=False, reason="too_many_chunks", max_chunks=max_chunks, **base_meta)
    if any(contains_timecode(chunk) for chunk in cleaned):
        return None, _decision("llm_verifier", accepted=False, reason="timecode_in_output", **base_meta)

    source_text_str = str(source_text or "")
    for phrase in _HALLUCINATION_PHRASES:
        if any(phrase in chunk for chunk in cleaned) and phrase not in source_text_str:
            return None, _decision("llm_verifier", accepted=False, reason=f"hallucination_phrase:{phrase}", **base_meta)

    preservation_violations = llm_source_preservation_violations(
        source_text_str,
        " ".join(cleaned),
        settings,
        profile,
    )
    if preservation_violations:
        first_type = str(preservation_violations[0].get("type") or "source_preservation_failed")
        return None, _decision(
            "llm_verifier",
            accepted=False,
            reason=f"source_preservation:{first_type}",
            preservation_violations=preservation_violations[:6],
            **base_meta,
        )

    min_similarity = _safe_float(settings.get("llm_verifier_min_similarity"), 0.86)
    max_delta = _safe_float(settings.get("llm_verifier_max_length_delta_ratio"), 0.16)
    ok, reason = validate_llm_chunks(
        source_text,
        cleaned,
        min_similarity=min_similarity,
        max_length_delta_ratio=max_delta,
    )
    if not ok:
        return None, _decision(
            "llm_verifier",
            accepted=False,
            reason=reason,
            min_similarity=round(min_similarity, 4),
            max_length_delta_ratio=round(max_delta, 4),
            **base_meta,
        )
    return cleaned, _decision(
        "llm_verifier",
        accepted=True,
        reason="ok",
        min_similarity=round(min_similarity, 4),
        max_length_delta_ratio=round(max_delta, 4),
        **base_meta,
    )


def append_accuracy_decision(payload: dict[str, Any] | None, decision: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(payload or {})
    if not isinstance(decision, dict) or not decision:
        return out
    graph = dict(out.get("_accuracy_decision_graph") or {})
    if graph.get("schema") != SUBTITLE_ACCURACY_SCHEMA:
        graph = {"schema": SUBTITLE_ACCURACY_SCHEMA, "decisions": []}
    decisions = list(graph.get("decisions") or [])
    decisions.append(dict(decision))
    graph["decisions"] = decisions[-24:]
    graph["updated_epoch"] = round(time(), 3)
    out["_accuracy_decision_graph"] = graph
    return out


def rollback_decision(reason: str, *, fallback: str, source: str = "llm_verifier") -> dict[str, Any]:
    return _decision("llm_rollback", reason=str(reason or "unknown"), fallback=str(fallback or "safe_split"), source=source)


def subtitle_context_consistency_metrics(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score sequence-level subtitle risks that single-segment checks miss."""
    settings = dict(settings or {})
    if not _safe_bool(settings.get("subtitle_context_consistency_enabled"), True):
        return {
            "schema": SUBTITLE_ACCURACY_SCHEMA,
            "task": "context_consistency",
            "enabled": False,
            "score": 100.0,
        }

    repeat_window = max(0.0, _safe_float(settings.get("subtitle_context_repeat_window_sec"), 4.0))
    near_duplicate_ratio = max(0.5, min(1.0, _safe_float(settings.get("subtitle_context_near_duplicate_ratio"), 0.94)))
    cps_jump_ratio = max(1.1, _safe_float(settings.get("subtitle_context_cps_jump_ratio"), 2.6))
    max_cps = max(0.0, _safe_float(settings.get("sub_max_cps"), 12.0))

    total = 0
    empty_segments = 0
    repeated_segments = 0
    near_duplicate_segments = 0
    overlap_segments = 0
    timing_order_violations = 0
    hallucination_phrase_segments = 0
    cps_jump_segments = 0

    prev_start: float | None = None
    prev_end: float | None = None
    prev_text = ""
    prev_cps: float | None = None
    for segment in list(segments or []):
        if not isinstance(segment, dict) or segment.get("is_gap"):
            continue
        total += 1
        start = _safe_float(segment.get("start"), 0.0)
        end = _safe_float(segment.get("end"), start)
        text = str(segment.get("text", "") or "").strip()
        compact = _compact_text(text)
        duration = max(0.001, end - start)
        cps = compact_len(text) / duration

        if not compact:
            empty_segments += 1
        if any(phrase.lower() in text.lower() for phrase in _HALLUCINATION_PHRASES):
            hallucination_phrase_segments += 1

        if prev_start is not None and start + 0.02 < prev_start:
            timing_order_violations += 1
        if prev_end is not None:
            if start < prev_end - 0.02:
                overlap_segments += 1
            gap = max(0.0, start - prev_end)
            if compact and prev_text and gap <= repeat_window:
                if compact == prev_text and len(compact) >= 2:
                    repeated_segments += 1
                elif min(len(compact), len(prev_text)) >= 4:
                    similarity = difflib.SequenceMatcher(None, compact, prev_text).ratio()
                    if similarity >= near_duplicate_ratio:
                        near_duplicate_segments += 1
            if (
                prev_cps is not None
                and compact_len(text) >= 5
                and cps > max(max_cps * 1.15, prev_cps * cps_jump_ratio)
            ):
                cps_jump_segments += 1

        prev_start = start
        prev_end = end
        prev_text = compact
        prev_cps = cps

    if total <= 0:
        score = 100.0
    else:
        penalty = (
            repeated_segments * 14.0
            + near_duplicate_segments * 8.0
            + overlap_segments * 10.0
            + timing_order_violations * 14.0
            + hallucination_phrase_segments * 18.0
            + empty_segments * 12.0
            + cps_jump_segments * 5.0
        ) / total
        score = max(0.0, min(100.0, 100.0 - penalty))

    return {
        "schema": SUBTITLE_ACCURACY_SCHEMA,
        "task": "context_consistency",
        "enabled": True,
        "score": round(score, 4),
        "total_segments": total,
        "repeated_segments": repeated_segments,
        "near_duplicate_segments": near_duplicate_segments,
        "overlap_segments": overlap_segments,
        "timing_order_violations": timing_order_violations,
        "hallucination_phrase_segments": hallucination_phrase_segments,
        "empty_segments": empty_segments,
        "cps_jump_segments": cps_jump_segments,
        "repeat_window_sec": round(repeat_window, 4),
        "near_duplicate_ratio": round(near_duplicate_ratio, 4),
    }


def annotate_subtitle_context_consistency(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Attach per-segment context risk metadata for learning and UI inspection."""
    settings = dict(settings or {})
    rows = [dict(segment) for segment in list(segments or []) if isinstance(segment, dict)]
    if not _safe_bool(settings.get("subtitle_context_consistency_enabled"), True):
        return rows

    repeat_window = max(0.0, _safe_float(settings.get("subtitle_context_repeat_window_sec"), 4.0))
    near_duplicate_ratio = max(0.5, min(1.0, _safe_float(settings.get("subtitle_context_near_duplicate_ratio"), 0.94)))
    cps_jump_ratio = max(1.1, _safe_float(settings.get("subtitle_context_cps_jump_ratio"), 2.6))
    max_cps = max(0.0, _safe_float(settings.get("sub_max_cps"), 12.0))

    prev_index: int | None = None
    prev_start: float | None = None
    prev_end: float | None = None
    prev_text = ""
    prev_cps: float | None = None
    for index, row in enumerate(rows):
        row.pop("_context_consistency_policy", None)
        if row.get("is_gap"):
            continue

        start = _safe_float(row.get("start"), 0.0)
        end = _safe_float(row.get("end"), start)
        text = str(row.get("text", "") or "").strip()
        compact = _compact_text(text)
        duration = max(0.001, end - start)
        cps = compact_len(text) / duration
        flags: list[str] = []
        details: dict[str, Any] = {
            "segment_index": index,
            "start": round(start, 3),
            "end": round(end, 3),
            "cps": round(cps, 3),
        }

        if not compact:
            flags.append("empty_text")
        if any(phrase.lower() in text.lower() for phrase in _HALLUCINATION_PHRASES):
            flags.append("hallucination_phrase")
        if prev_start is not None and start + 0.02 < prev_start:
            flags.append("timing_order_violation")
        if prev_end is not None:
            if start < prev_end - 0.02:
                flags.append("overlap_previous")
                details["overlap_sec"] = round(prev_end - start, 4)
            gap = max(0.0, start - prev_end)
            details["gap_to_previous_sec"] = round(gap, 4)
            if compact and prev_text and gap <= repeat_window:
                if compact == prev_text and len(compact) >= 2:
                    flags.append("repeat_previous")
                    details["repeat_similarity"] = 1.0
                elif min(len(compact), len(prev_text)) >= 4:
                    similarity = difflib.SequenceMatcher(None, compact, prev_text).ratio()
                    if similarity >= near_duplicate_ratio:
                        flags.append("near_duplicate_previous")
                        details["repeat_similarity"] = round(similarity, 4)
            if (
                prev_cps is not None
                and compact_len(text) >= 5
                and cps > max(max_cps * 1.15, prev_cps * cps_jump_ratio)
            ):
                flags.append("cps_jump")
                details["previous_cps"] = round(prev_cps, 3)

        if flags:
            penalty = 0.0
            penalty += 18.0 if "hallucination_phrase" in flags else 0.0
            penalty += 14.0 if "repeat_previous" in flags else 0.0
            penalty += 8.0 if "near_duplicate_previous" in flags else 0.0
            penalty += 10.0 if "overlap_previous" in flags else 0.0
            penalty += 14.0 if "timing_order_violation" in flags else 0.0
            penalty += 12.0 if "empty_text" in flags else 0.0
            penalty += 5.0 if "cps_jump" in flags else 0.0
            details["previous_segment_index"] = prev_index
            row["_context_consistency_policy"] = _decision(
                "context_consistency",
                model=CONTEXT_CONSISTENCY_MODEL_ID,
                flags=sorted(set(flags)),
                score=round(max(0.0, 100.0 - penalty), 4),
                details=details,
            )

        prev_index = index
        prev_start = start
        prev_end = end
        prev_text = compact
        prev_cps = cps
    return rows


def _lora_style_policy_for_segment(
    segment: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    settings = dict(settings or {})
    profile = dict(segment.get("_lora_generation_profile") or {})
    if not profile:
        return None
    if not _safe_bool(settings.get("subtitle_lora_style_consistency_enabled"), True):
        return None

    profile_score = _profile_score(profile)
    min_profile_score = _safe_float(settings.get("subtitle_lora_style_min_profile_score"), 28.0)
    if profile_score < min_profile_score:
        return None

    text = str(segment.get("text") or "")
    compact = _compact_text(text)
    if not compact:
        return None

    examples = _profile_examples(profile)
    exclusions = _profile_exclusions(profile)
    if not examples and not exclusions:
        return None

    flags: list[str] = []
    details: dict[str, Any] = {
        "profile_score": round(profile_score, 4),
        "min_profile_score": round(min_profile_score, 4),
        "segment_chars": compact_len(text),
        "segment_lines": _line_count(text),
    }

    compact_current = _compact_text(text)
    for excluded in exclusions:
        compact_excluded = _compact_text(excluded)
        if len(compact_excluded) >= 2 and compact_excluded in compact_current:
            flags.append("excluded_phrase")
            details.setdefault("excluded_phrases", []).append(excluded[:80])

    if examples:
        example_lengths = [compact_len(example) for example in examples if compact_len(example) > 0]
        example_lines = [_line_count(example) for example in examples if _clean_text(example)]
        if example_lengths:
            reference_chars = float(median(example_lengths))
            drift_ratio = abs(compact_len(text) - reference_chars) / max(4.0, reference_chars)
            details["reference_chars"] = round(reference_chars, 3)
            details["length_drift_ratio"] = round(drift_ratio, 4)
            max_drift = _safe_float(settings.get("subtitle_lora_style_max_length_drift_ratio"), 1.25)
            if drift_ratio > max_drift:
                flags.append("style_length_drift")
        if example_lines:
            reference_lines = int(round(float(median(example_lines))))
            line_drift = abs(_line_count(text) - reference_lines)
            details["reference_lines"] = reference_lines
            details["line_drift"] = int(line_drift)
            max_line_drift = max(0, _safe_int(settings.get("subtitle_lora_style_max_line_drift"), 1))
            if line_drift > max_line_drift:
                flags.append("style_line_drift")

    cps_values = _profile_example_cps_values(profile)
    if cps_values:
        start = _safe_float(segment.get("start"), 0.0)
        end = _safe_float(segment.get("end"), start)
        duration = max(0.001, end - start)
        cps = compact_len(text) / duration
        reference_cps = float(median(cps_values))
        max_cps_ratio = max(1.1, _safe_float(settings.get("subtitle_lora_style_max_cps_ratio"), 2.0))
        max_cps = max(0.0, _safe_float(settings.get("sub_max_cps"), 12.0))
        details["cps"] = round(cps, 3)
        details["reference_cps"] = round(reference_cps, 3)
        if reference_cps > 0.0 and cps > reference_cps * max_cps_ratio and (not max_cps or cps > max_cps * 1.1):
            flags.append("style_cps_drift")

    if not flags:
        return None

    penalty = 0.0
    penalty += 22.0 if "excluded_phrase" in flags else 0.0
    penalty += 8.0 if "style_length_drift" in flags else 0.0
    penalty += 6.0 if "style_line_drift" in flags else 0.0
    penalty += 8.0 if "style_cps_drift" in flags else 0.0
    return _decision(
        "lora_style_consistency",
        model=LORA_STYLE_MODEL_ID,
        flags=sorted(set(flags)),
        score=round(max(0.0, 100.0 - penalty), 4),
        details=details,
    )


def annotate_subtitle_lora_style_consistency(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Attach LoRA style drift metadata without modifying subtitle text."""
    rows = [dict(segment) for segment in list(segments or []) if isinstance(segment, dict)]
    if not _safe_bool(dict(settings or {}).get("subtitle_lora_style_consistency_enabled"), True):
        for row in rows:
            row.pop("_lora_style_policy", None)
        return rows
    for row in rows:
        row.pop("_lora_style_policy", None)
        if row.get("is_gap"):
            continue
        policy = _lora_style_policy_for_segment(row, settings)
        if policy:
            row["_lora_style_policy"] = policy
    return rows


def subtitle_lora_style_consistency_metrics(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score whether generated subtitles still follow retrieved LoRA style evidence."""
    settings = dict(settings or {})
    if not _safe_bool(settings.get("subtitle_lora_style_consistency_enabled"), True):
        return {
            "schema": SUBTITLE_ACCURACY_SCHEMA,
            "task": "lora_style_consistency",
            "enabled": False,
            "score": 100.0,
        }

    total_profiled = 0
    drift_segments = 0
    excluded_segments = 0
    length_drift_segments = 0
    line_drift_segments = 0
    cps_drift_segments = 0
    scores: list[float] = []

    for segment in list(segments or []):
        if not isinstance(segment, dict) or segment.get("is_gap"):
            continue
        profile = dict(segment.get("_lora_generation_profile") or {})
        if not profile:
            continue
        if _profile_score(profile) < _safe_float(settings.get("subtitle_lora_style_min_profile_score"), 28.0):
            continue
        if not (_profile_examples(profile) or _profile_exclusions(profile)):
            continue
        total_profiled += 1
        policy = dict(segment.get("_lora_style_policy") or {})
        if not policy:
            policy = _lora_style_policy_for_segment(segment, settings) or {}
        if policy:
            drift_segments += 1
            flags = {str(flag) for flag in list(policy.get("flags") or [])}
            if "excluded_phrase" in flags:
                excluded_segments += 1
            if "style_length_drift" in flags:
                length_drift_segments += 1
            if "style_line_drift" in flags:
                line_drift_segments += 1
            if "style_cps_drift" in flags:
                cps_drift_segments += 1
            score = policy.get("score")
            if isinstance(score, (int, float)):
                scores.append(float(score))
        else:
            scores.append(100.0)

    if total_profiled <= 0:
        score = 100.0
    else:
        base = sum(scores) / max(1, len(scores)) if scores else 100.0
        density_penalty = (drift_segments / max(1, total_profiled)) * 10.0
        score = max(0.0, min(100.0, base - density_penalty))

    return {
        "schema": SUBTITLE_ACCURACY_SCHEMA,
        "task": "lora_style_consistency",
        "enabled": True,
        "score": round(score, 4),
        "profiled_segments": total_profiled,
        "style_drift_segments": drift_segments,
        "excluded_phrase_segments": excluded_segments,
        "length_drift_segments": length_drift_segments,
        "line_drift_segments": line_drift_segments,
        "cps_drift_segments": cps_drift_segments,
    }


def repair_subtitle_context_consistency(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a conservative same-text/timing repair candidate for output selection."""
    settings = dict(settings or {})
    rows = [dict(segment) for segment in list(segments or []) if isinstance(segment, dict)]
    if not _safe_bool(settings.get("subtitle_context_repair_enabled"), True):
        return rows, _decision("context_repair", model=CONTEXT_CONSISTENCY_MODEL_ID, applied=False, reason="disabled")
    if not rows:
        return rows, _decision("context_repair", model=CONTEXT_CONSISTENCY_MODEL_ID, applied=False, reason="empty")

    before_metrics = subtitle_context_consistency_metrics(rows, settings)
    annotated = annotate_subtitle_context_consistency(rows, settings)
    min_duration = max(0.05, _safe_float(settings.get("sub_min_duration"), _safe_float(settings.get("subtitle_context_repair_min_duration_sec"), 0.2)))
    pad = max(0.0, min(0.2, _safe_float(settings.get("subtitle_context_repair_overlap_pad_sec"), 0.02)))
    drop_repeats = _safe_bool(settings.get("subtitle_context_repair_drop_repeats"), True)
    drop_empty = _safe_bool(settings.get("subtitle_context_repair_drop_empty_enabled"), True)
    drop_hallucinations = _safe_bool(settings.get("subtitle_context_repair_drop_hallucinations_enabled"), True)
    repair_cps_jumps = _safe_bool(settings.get("subtitle_context_repair_cps_jumps_enabled"), True)
    cps_max_extend = max(0.0, min(1.5, _safe_float(settings.get("subtitle_context_repair_cps_max_extend_sec"), 0.4)))
    max_cps = max(1.0, _safe_float(settings.get("sub_max_cps"), 12.0))
    repaired: list[dict[str, Any]] = []
    dropped_repeats = 0
    dropped_empty = 0
    dropped_hallucinations = 0
    shifted_starts = 0
    extended_ends = 0
    extended_cps_segments = 0

    def next_non_gap(index: int) -> dict[str, Any] | None:
        for candidate in annotated[index + 1 :]:
            if isinstance(candidate, dict) and not candidate.get("is_gap"):
                return candidate
        return None

    for index, row in enumerate(annotated):
        if not isinstance(row, dict):
            continue
        current = dict(row)
        policy = dict(current.get("_context_consistency_policy") or {})
        flags = set(str(flag) for flag in list(policy.get("flags") or []))
        previous = next((item for item in reversed(repaired) if isinstance(item, dict) and not item.get("is_gap")), None)
        same_scope = _same_scope(previous, current)
        current_text = _compact_text(current.get("text"))
        previous_text = _compact_text((previous or {}).get("text"))

        if drop_empty and not current_text:
            dropped_empty += 1
            continue

        hallucination_phrase = _placeholder_hallucination_phrase(current.get("text"))
        if drop_hallucinations and hallucination_phrase:
            dropped_hallucinations += 1
            continue

        if (
            drop_repeats
            and same_scope
            and "repeat_previous" in flags
            and current_text
            and current_text == previous_text
        ):
            dropped_repeats += 1
            continue

        if same_scope and (flags & {"overlap_previous", "timing_order_violation"}):
            prev_end = _safe_float((previous or {}).get("end"), 0.0)
            start = _safe_float(current.get("start"), 0.0)
            end = _safe_float(current.get("end"), start)
            safe_start = max(start, prev_end + pad)
            if safe_start > start + 0.001:
                current["start"] = round(safe_start, 3)
                current["timeline_start"] = current["start"]
                shifted_starts += 1
                if end < safe_start + min_duration:
                    end = safe_start + min_duration
                    current["end"] = round(end, 3)
                    current["timeline_end"] = current["end"]
                    extended_ends += 1
        if repair_cps_jumps and "cps_jump" in flags and current_text:
            start = _safe_float(current.get("start"), 0.0)
            end = _safe_float(current.get("end"), start)
            duration = max(0.001, end - start)
            needed_duration = compact_len(current.get("text")) / max_cps
            needed_extension = max(0.0, needed_duration - duration)
            next_row = next_non_gap(index)
            available_extension = cps_max_extend
            if next_row is not None and _same_scope(current, next_row):
                next_start = _safe_float(next_row.get("start"), end)
                available_extension = max(0.0, min(cps_max_extend, next_start - pad - end))
            extension = min(needed_extension, available_extension)
            if extension >= 0.01:
                current["end"] = round(end + extension, 3)
                current["timeline_end"] = current["end"]
                extended_ends += 1
                extended_cps_segments += 1
        repaired.append(current)

    repaired = annotate_subtitle_context_consistency(repaired, settings)
    after_metrics = subtitle_context_consistency_metrics(repaired, settings)
    applied = bool(dropped_repeats or dropped_empty or dropped_hallucinations or shifted_starts or extended_ends)
    decision = _decision(
        "context_repair",
        model=CONTEXT_CONSISTENCY_MODEL_ID,
        applied=applied,
        reason="repaired" if applied else "no_safe_repair",
        dropped_repeats=dropped_repeats,
        dropped_empty=dropped_empty,
        dropped_hallucinations=dropped_hallucinations,
        shifted_starts=shifted_starts,
        extended_ends=extended_ends,
        extended_cps_segments=extended_cps_segments,
        before_score=before_metrics.get("score"),
        after_score=after_metrics.get("score"),
        before_counts={
            "repeated_segments": before_metrics.get("repeated_segments"),
            "near_duplicate_segments": before_metrics.get("near_duplicate_segments"),
            "overlap_segments": before_metrics.get("overlap_segments"),
            "timing_order_violations": before_metrics.get("timing_order_violations"),
            "cps_jump_segments": before_metrics.get("cps_jump_segments"),
        },
        after_counts={
            "repeated_segments": after_metrics.get("repeated_segments"),
            "near_duplicate_segments": after_metrics.get("near_duplicate_segments"),
            "overlap_segments": after_metrics.get("overlap_segments"),
            "timing_order_violations": after_metrics.get("timing_order_violations"),
            "cps_jump_segments": after_metrics.get("cps_jump_segments"),
        },
    )
    return repaired, decision


def subtitle_accuracy_metrics(segments: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = dict(settings or {})
    if not _safe_bool(settings.get("subtitle_accuracy_metrics_enabled"), True):
        return {"schema": SUBTITLE_ACCURACY_SCHEMA, "enabled": False}
    context = subtitle_context_consistency_metrics(segments, settings)
    lora_style = subtitle_lora_style_consistency_metrics(segments, settings)
    total = 0
    cps_sum = 0.0
    high_cps = 0
    over_duration = 0
    lora_segments = 0
    deep_segments = 0
    gate_skips = 0
    verifier_rollbacks = 0
    quality_scores: list[float] = []
    quality_counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
    max_cps = max(0.0, _safe_float(settings.get("sub_max_cps"), 12.0))
    max_duration = max(0.0, _safe_float(settings.get("sub_max_duration"), 6.0))

    for segment in list(segments or []):
        if not isinstance(segment, dict):
            continue
        total += 1
        duration = max(0.001, _segment_duration(segment))
        chars = compact_len(segment.get("text"))
        cps = chars / duration
        cps_sum += cps
        if max_cps and cps > max_cps:
            high_cps += 1
        if max_duration and duration > max_duration:
            over_duration += 1
        if segment.get("_lora_generation_profile") or segment.get("_lora_segment_settings"):
            lora_segments += 1
        if any(key.startswith("_deep_") for key in segment):
            deep_segments += 1
        quality = dict(segment.get("quality") or {})
        label = str(quality.get("confidence_label") or "").lower()
        if label in quality_counts:
            quality_counts[label] += 1
        score = quality.get("confidence_score")
        if isinstance(score, (int, float)):
            quality_scores.append(float(score))
        for decision in list(dict(segment.get("_accuracy_decision_graph") or {}).get("decisions") or []):
            if not isinstance(decision, dict):
                continue
            if decision.get("task") == "llm_gate" and not decision.get("call_llm", True):
                gate_skips += 1
            if decision.get("task") == "llm_rollback":
                verifier_rollbacks += 1

    return {
        "schema": SUBTITLE_ACCURACY_SCHEMA,
        "enabled": True,
        "total_segments": total,
        "avg_cps": round(cps_sum / max(1, total), 3),
        "high_cps_segments": high_cps,
        "over_max_duration_segments": over_duration,
        "lora_applied_segments": lora_segments,
        "deep_policy_segments": deep_segments,
        "llm_gate_skipped_segments": gate_skips,
        "llm_verifier_rollbacks": verifier_rollbacks,
        "avg_quality_score": round(sum(quality_scores) / max(1, len(quality_scores)), 3) if quality_scores else None,
        "quality_label_counts": quality_counts,
        "context_consistency_score": context.get("score") if context.get("enabled") else None,
        "context_repeat_segments": int(context.get("repeated_segments", 0) or 0) + int(context.get("near_duplicate_segments", 0) or 0),
        "context_overlap_segments": int(context.get("overlap_segments", 0) or 0),
        "context_timing_order_violations": int(context.get("timing_order_violations", 0) or 0),
        "context_cps_jump_segments": int(context.get("cps_jump_segments", 0) or 0),
        "lora_style_score": lora_style.get("score") if lora_style.get("enabled") else None,
        "lora_style_profiled_segments": int(lora_style.get("profiled_segments", 0) or 0),
        "lora_style_drift_segments": int(lora_style.get("style_drift_segments", 0) or 0),
        "lora_style_excluded_segments": int(lora_style.get("excluded_phrase_segments", 0) or 0),
    }


def subtitle_decision_explanations(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize why each final subtitle row was accepted, skipped, or rolled back."""
    explanations: list[dict[str, Any]] = []
    for index, segment in enumerate(list(segments or [])):
        if not isinstance(segment, dict):
            continue
        decisions = [
            dict(item)
            for item in list(dict(segment.get("_accuracy_decision_graph") or {}).get("decisions") or [])
            if isinstance(item, dict)
        ]
        lora_profile = dict(segment.get("_lora_generation_profile") or {})
        stt_lattice = dict(segment.get("_stt_lattice_policy") or {})
        lora_style = dict(segment.get("_lora_style_policy") or {})
        cut_guard = dict(segment.get("_cut_boundary_guard_policy") or {})
        deep_tasks = sorted(
            key[6:-7]
            for key in segment.keys()
            if key.startswith("_deep_") and key.endswith("_policy")
        )
        llm_gate = next((item for item in reversed(decisions) if item.get("task") == "llm_gate"), {})
        candidate_policy = dict(segment.get("_llm_candidate_policy") or {})
        if not candidate_policy:
            candidate_policy = next((item for item in reversed(decisions) if item.get("task") == "llm_candidate_policy"), {})
        verifier = next((item for item in reversed(decisions) if item.get("task") == "llm_verifier"), {})
        rollback = next((item for item in reversed(decisions) if item.get("task") == "llm_rollback"), {})
        actions: list[str] = []
        if stt_lattice:
            replacements = _safe_int(stt_lattice.get("replacements"), 0)
            reason = str(stt_lattice.get("reason") or ("word_replacements" if replacements else "checked"))
            actions.append(f"stt_lattice:{reason}:{replacements}")
        if llm_gate:
            actions.append("llm_skipped" if llm_gate.get("call_llm") is False else "llm_called")
        if candidate_policy:
            reason = str(candidate_policy.get("reason") or "checked")
            if candidate_policy.get("accepted"):
                actions.append(f"llm_candidate:{reason}")
            else:
                actions.append(f"llm_candidate_rejected:{reason}")
        if verifier:
            actions.append("llm_verified" if verifier.get("accepted") else f"llm_rejected:{verifier.get('reason')}")
        if rollback:
            actions.append(f"rollback:{rollback.get('fallback') or rollback.get('reason')}")
        if lora_style.get("flags"):
            actions.append("lora_style_flags:" + ",".join(str(flag) for flag in list(lora_style.get("flags") or [])))
        if cut_guard:
            actions.append(f"cut_boundary:{cut_guard.get('action') or 'checked'}")
        if deep_tasks:
            actions.append("deep_policy:" + ",".join(deep_tasks))

        explanations.append(
            {
                "schema": SUBTITLE_ACCURACY_SCHEMA,
                "task": "subtitle_decision_explanation",
                "index": index,
                "segment_id": str(segment.get("segment_id") or segment.get("id") or index),
                "start": round(_safe_float(segment.get("start"), 0.0), 3),
                "end": round(_safe_float(segment.get("end"), 0.0), 3),
                "text_preview": _clean_text(segment.get("text"))[:80],
                "actions": actions or ["accepted_without_extra_policy"],
                "lora_score": round(_profile_score(lora_profile), 4),
                "llm_gate": {
                    "call_llm": llm_gate.get("call_llm"),
                    "reason": llm_gate.get("reason"),
                    "confidence": llm_gate.get("confidence"),
                } if llm_gate else {},
                "llm_verifier": {
                    "accepted": verifier.get("accepted"),
                    "reason": verifier.get("reason"),
                    "similarity": verifier.get("similarity"),
                } if verifier else {},
                "llm_candidate_policy": candidate_policy,
                "rollback": rollback,
                "stt_lattice": stt_lattice,
                "lora_style": lora_style,
                "cut_boundary_guard": cut_guard,
                "decision_count": len(decisions),
            }
        )
    return explanations


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


__all__ = [
    "CONTEXT_CONSISTENCY_MODEL_ID",
    "LORA_STYLE_MODEL_ID",
    "SUBTITLE_ACCURACY_SCHEMA",
    "append_accuracy_decision",
    "annotate_subtitle_completion_report",
    "annotate_subtitle_auto_review",
    "annotate_subtitle_context_consistency",
    "annotate_subtitle_lora_style_consistency",
    "annotate_subtitle_stage_confidence",
    "compact_len",
    "llm_gate_decision",
    "llm_minimize_decision",
    "llm_source_preservation_violations",
    "rollback_decision",
    "repair_subtitle_context_consistency",
    "select_best_subtitle_output",
    "subtitle_auto_review_items",
    "subtitle_auto_review_summary",
    "subtitle_completion_report",
    "subtitle_context_consistency_metrics",
    "subtitle_decision_explanations",
    "subtitle_lora_style_consistency_metrics",
    "subtitle_output_variant_score",
    "subtitle_stage_confidence",
    "subtitle_accuracy_metrics",
    "verify_llm_chunks_for_subtitle",
]
