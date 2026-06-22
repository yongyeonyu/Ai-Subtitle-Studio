from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from statistics import median
from time import time
from typing import Any, Iterable

from core.engine.subtitle_accuracy_utils import (
    clean_text as _clean_text,
    compact_len,
    compact_text as _compact_text,
    line_count as _line_count,
    safe_bool as _safe_bool,
    safe_float as _safe_float,
    safe_int as _safe_int,
)
from core.engine.llm_correction_guard import contains_timecode, normalized_edit_distance, normalized_text, validate_llm_chunks
from core.native_text_similarity import similarity_ratio


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
_NUMBER_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*(?:(?:[%％]|[A-Za-z가-힣]+)(?:/[A-Za-z가-힣]+)*)?")
_NUMBER_TOKEN_PARTS_RE = re.compile(r"^(?P<core>\d+(?:[.,]\d+)*)(?P<suffix>(?:(?:[%％]|[A-Za-z가-힣]+)(?:/[A-Za-z가-힣]+)*)?)$")
_NUMBER_SUFFIX_TRAILING_PARTICLE_RE = re.compile(
    r"(으로|에서|부터|까지|이나|인데|이고|이라도|로|은|는|이|가|을|를|와|과|도|에|만|씩|쯤|정도|나)$"
)
_LATIN_PROPER_TOKEN_RE = re.compile(
    r"\b(?:[A-Z]{2,}[A-Za-z0-9-]*|[A-Za-z]+[0-9][A-Za-z0-9-]*|[A-Z][a-z]+(?:[A-Z][a-z]+)+)\b"
)
_CONTENT_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣/]+")
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
    out: list[str] = []
    for token in _NUMBER_TOKEN_RE.findall(str(text or "")):
        normalized = normalized_text(token)
        if normalized:
            out.append(normalized)
    return out


def _number_token_parts(text: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for token in _NUMBER_TOKEN_RE.findall(str(text or "")):
        match = _NUMBER_TOKEN_PARTS_RE.match(token.strip())
        if not match:
            continue
        core = normalized_text(str(match.group("core") or ""))
        suffix = normalized_text(str(match.group("suffix") or ""))
        if core:
            out.append((core, suffix))
    return out


def _normalize_number_suffix(suffix: str) -> str:
    value = normalized_text(str(suffix or ""))
    if not value:
        return ""
    stripped = _NUMBER_SUFFIX_TRAILING_PARTICLE_RE.sub("", value)
    return stripped or ""


def _numbers_match_with_safe_suffix_additions(source_text: Any, candidate_text: Any) -> bool:
    source_parts = _number_token_parts(source_text)
    candidate_parts = _number_token_parts(candidate_text)
    if len(source_parts) != len(candidate_parts):
        return False
    for (source_core, source_suffix), (candidate_core, candidate_suffix) in zip(source_parts, candidate_parts):
        if source_core != candidate_core:
            return False
        source_unit = _normalize_number_suffix(source_suffix)
        candidate_unit = _normalize_number_suffix(candidate_suffix)
        if source_unit:
            if candidate_unit != source_unit:
                return False
    return True


def _numeric_core_tokens(text: Any) -> set[str]:
    return {core for core, _suffix in _number_token_parts(text) if core}


def _profile_brand_tokens(profile: dict[str, Any] | None) -> set[str]:
    keys = {"brand_tokens", "brand_name_tokens", "brand_names", "proper_nouns"}
    return {normalized_text(token) for token in _walk_profile_values(profile or {}, keys) if normalized_text(token)}


def _proper_noun_tokens(text: Any, profile: dict[str, Any] | None = None) -> set[str]:
    tokens = _normalized_findall_set(_LATIN_PROPER_TOKEN_RE, text)
    profile_tokens = _profile_brand_tokens(profile)
    compact = normalized_text(str(text or ""))
    tokens.update(token for token in profile_tokens if token and token in compact)
    return tokens


def _interjection_tokens(text: Any) -> set[str]:
    raw_tokens = _normalized_findall_list(_CONTENT_TOKEN_RE, text)
    return {token for token in raw_tokens if token in _INTERJECTION_TOKENS}


def _content_tokens(text: Any) -> set[str]:
    return {token for token in _normalized_findall_list(_CONTENT_TOKEN_RE, text) if len(token) >= 2}


def _has_exact_tandem_repeat_text(text: Any) -> bool:
    tokens = _normalized_findall_list(_CONTENT_TOKEN_RE, text)
    if len(tokens) < 2 or len(tokens) % 2:
        return False
    half = len(tokens) // 2
    left = tokens[:half]
    if left != tokens[half:]:
        return False
    if len(left) < 2 and compact_len(" ".join(left)) < 4:
        return False
    return True


def _normalized_findall_list(pattern: re.Pattern[str], text: Any) -> list[str]:
    out: list[str] = []
    for token in pattern.findall(str(text or "")):
        normalized = normalized_text(token)
        if normalized:
            out.append(normalized)
    return out


def _normalized_findall_set(pattern: re.Pattern[str], text: Any) -> set[str]:
    return set(_normalized_findall_list(pattern, text))


def _token_is_supported_by_source(token: str, source_text: str, source_norm: str, source_tokens: set[str]) -> bool:
    if not token:
        return True
    if token in source_norm:
        return True
    token_number_cores = _numeric_core_tokens(token)
    if token_number_cores and token_number_cores.issubset(_numeric_core_tokens(source_text)):
        return True
    for source_token in source_tokens:
        if len(source_token) >= 2 and (source_token in token or token in source_token):
            return True
        if len(source_token) >= 2 and normalized_edit_distance(source_token, token, limit=2) <= 2:
            return True
    return False


def _token_diff_preview(
    source_text: str,
    candidate_text: str,
    profile: dict[str, Any] | None = None,
    *,
    limit: int = 6,
) -> tuple[list[str], list[str]]:
    source_norm = normalized_text(source_text)
    source_tokens = _content_tokens(source_text)
    candidate_tokens = _content_tokens(candidate_text)
    profile_brand_tokens = _profile_brand_tokens(profile)
    missing = sorted(token for token in source_tokens if token not in candidate_tokens)[:limit]
    added = sorted(
        token
        for token in candidate_tokens
        if token not in _INTERJECTION_TOKENS
        and token not in profile_brand_tokens
        and not _token_is_supported_by_source(token, source_text, source_norm, source_tokens)
    )[:limit]
    return missing, added


def _llm_verifier_length_delta_policy(
    source_text: str,
    settings: dict[str, Any] | None = None,
    *,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    base = _safe_float(settings.get("llm_verifier_max_length_delta_ratio"), 0.16)
    source_compact_len = len(normalized_text(source_text))
    short_len = max(4, _safe_int(settings.get("llm_verifier_short_text_compact_len"), 10))
    long_len = max(short_len + 4, _safe_int(settings.get("llm_verifier_long_text_compact_len"), 28))
    short_ratio = min(
        base,
        _safe_float(settings.get("llm_verifier_short_text_max_length_delta_ratio"), max(0.08, base - 0.04)),
    )
    long_ratio = max(
        base,
        _safe_float(settings.get("llm_verifier_long_text_max_length_delta_ratio"), min(0.28, base + 0.06)),
    )
    if source_compact_len <= short_len:
        interpolated = short_ratio
        bucket = "short"
    elif source_compact_len >= long_len:
        interpolated = long_ratio
        bucket = "long"
    else:
        progress = (source_compact_len - short_len) / max(1, long_len - short_len)
        interpolated = short_ratio + ((long_ratio - short_ratio) * progress)
        bucket = "medium"

    duration_adjust = 0.0
    if duration_sec is not None:
        short_duration_sec = _safe_float(settings.get("llm_verifier_short_duration_sec"), 1.2)
        long_duration_sec = max(
            short_duration_sec + 0.2,
            _safe_float(settings.get("llm_verifier_long_duration_sec"), 3.6),
        )
        short_duration_adjust = _safe_float(settings.get("llm_verifier_short_duration_delta_adjust"), -0.01)
        long_duration_adjust = _safe_float(settings.get("llm_verifier_long_duration_delta_adjust"), 0.02)
        if duration_sec <= short_duration_sec:
            duration_adjust = short_duration_adjust
            bucket = "short"
        elif duration_sec >= long_duration_sec:
            duration_adjust = long_duration_adjust
            bucket = "long" if bucket != "short" else bucket

    effective = min(0.28, max(0.08, interpolated + duration_adjust))
    return {
        "base": round(base, 4),
        "effective": round(effective, 4),
        "bucket": bucket,
        "short_text_compact_len": short_len,
        "long_text_compact_len": long_len,
        "source_compact_len": source_compact_len,
        "short_ratio": round(short_ratio, 4),
        "long_ratio": round(long_ratio, 4),
        "duration_adjust": round(duration_adjust, 4),
        "duration_sec": None if duration_sec is None else round(max(0.0, float(duration_sec)), 4),
    }


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
        if source_numbers != candidate_numbers and not _numbers_match_with_safe_suffix_additions(source, candidate):
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
        profile_brand_tokens = _profile_brand_tokens(profile)
        added_content = sorted(
            token
            for token in candidate_tokens
            if token not in _INTERJECTION_TOKENS
            and token not in profile_brand_tokens
            and not _token_is_supported_by_source(token, source, source_norm, source_tokens)
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


def _manual_timing_locked(segment: dict[str, Any] | None) -> bool:
    if not isinstance(segment, dict):
        return False
    return bool(
        segment.get("manual_stt_candidate_locked")
        or segment.get("manual_timing_locked")
        or segment.get("_manual_timing_locked")
    )


def _matching_coverage(left: str, right: str) -> float:
    left = str(left or "")
    right = str(right or "")
    base = min(len(left), len(right))
    if base <= 0:
        return 0.0
    if left in right or right in left:
        return 1.0
    matcher = SequenceMatcher(None, left, right, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return max(0.0, min(1.0, matched / base))


def _shadow_duplicate_following_info(
    rows: list[dict[str, Any]],
    index: int,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Detect a parent subtitle that is immediately repeated by following split children."""
    settings = dict(settings or {})
    if not _safe_bool(settings.get("subtitle_context_repair_drop_shadow_duplicates"), True):
        return None
    if index < 0 or index >= len(rows):
        return None
    current = rows[index]
    if not isinstance(current, dict) or current.get("is_gap") or _manual_timing_locked(current):
        return None
    current_text = _compact_text(current.get("text"))
    if len(current_text) < max(8, _safe_int(settings.get("subtitle_context_shadow_duplicate_min_chars"), 8)):
        return None
    current_start = _safe_float(current.get("start"), 0.0)
    current_end = _safe_float(current.get("end"), current_start)
    window = max(0.0, _safe_float(settings.get("subtitle_context_shadow_duplicate_window_sec"), 4.0))
    max_followers = max(1, min(6, _safe_int(settings.get("subtitle_context_shadow_duplicate_max_followers"), 4)))
    min_coverage = max(0.5, min(1.0, _safe_float(settings.get("subtitle_context_shadow_duplicate_min_coverage"), 0.72)))
    min_similarity = max(0.3, min(1.0, _safe_float(settings.get("subtitle_context_shadow_duplicate_min_similarity"), 0.56)))

    followers: list[dict[str, Any]] = []
    for follower in rows[index + 1:]:
        if not isinstance(follower, dict):
            continue
        if follower.get("is_gap"):
            break
        if not _same_scope(current, follower):
            break
        follower_start = _safe_float(follower.get("start"), current_end)
        if follower_start < current_start - 0.05:
            continue
        if follower_start > current_end + window:
            break
        follower_text = _compact_text(follower.get("text"))
        if not follower_text:
            break
        followers.append(follower)
        if len(followers) >= max_followers:
            break

    if not followers:
        return None
    follower_text = "".join(_compact_text(row.get("text")) for row in followers)
    if not follower_text or follower_text == current_text:
        return None
    # One exact shorter child after a full subtitle is usually a legitimate candidate display.
    # A true shadow duplicate either spans multiple following children or the following text
    # is at least as complete as the parent.
    if len(followers) < 2 and len(follower_text) <= len(current_text) * 1.05:
        return None
    coverage = _matching_coverage(current_text, follower_text)
    similarity = similarity_ratio(current_text, follower_text)
    if coverage < min_coverage or similarity < min_similarity:
        return None
    return {
        "follower_count": len(followers),
        "coverage": round(coverage, 4),
        "similarity": round(similarity, 4),
        "current_chars": len(current_text),
        "following_chars": len(follower_text),
        "window_sec": round(window, 4),
    }


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
    lora_profile = dict(segment.get("_lora_generation_profile") or {})
    lora_scores = [
        _safe_float(segment.get("_lora_segment_score"), 0.0),
        _safe_float(lora_profile.get("top_score"), 0.0),
        _safe_float(lora_profile.get("truth_score"), 0.0),
    ]
    for source in list(lora_profile.get("setting_sources") or []):
        if isinstance(source, dict):
            lora_scores.append(_safe_float(source.get("score"), 0.0))
    for example in list(lora_profile.get("examples") or []):
        if isinstance(example, dict):
            lora_scores.append(_safe_float(example.get("score"), 0.0))
    deep_policy = dict(segment.get("_deep_candidate_selector_policy") or {})
    lattice_policy = dict(segment.get("_stt_lattice_policy") or {})
    scores = {
        "lora_score": max(lora_scores, default=0.0),
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
            best_similarity = max(best_similarity, similarity_ratio(left, right))
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
    signal_scores = _segment_signal_scores(segment)
    lora_score = max(_profile_score(profile), signal_scores.get("lora_score", 0.0))
    combined_signal_score = max(lora_score, signal_scores.get("combined_signal_score", 0.0))
    min_lora_score = _safe_float(settings.get("llm_confidence_gate_min_lora_score"), 82.0)
    max_compact_ratio = max(1.0, _safe_float(settings.get("llm_confidence_gate_max_compact_ratio"), 1.45))
    max_duration = max(0.3, _safe_float(settings.get("sub_max_duration"), 6.0))
    strong_signal_score = max(min_lora_score, _safe_float(settings.get("llm_confidence_gate_strong_signal_score"), 88.0))
    strong_max_ratio = max(
        max_compact_ratio,
        _safe_float(settings.get("llm_confidence_gate_strong_max_compact_ratio"), 1.85),
    )
    strong_max_duration_ratio = max(
        1.0,
        _safe_float(settings.get("llm_confidence_gate_strong_max_duration_ratio"), 1.65),
    )

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

    hard_reasons = {
        "empty_text",
        "stt_candidate_uncertain",
        "timecode_noise",
        "hallucination_phrase_in_source",
    }
    strong_fast_lane = (
        combined_signal_score >= strong_signal_score
        and ratio <= strong_max_ratio
        and duration_sec <= max_duration * strong_max_duration_ratio
        and not any(reason in hard_reasons for reason in reasons)
    )
    if strong_fast_lane:
        reasons = [
            reason
            for reason in reasons
            if reason not in {"long_text_needs_llm", "long_duration_needs_llm", "low_lora_score"}
        ]

    call_llm = bool(reasons)
    if "empty_text" in reasons:
        call_llm = False

    confidence = 0.35
    if not call_llm:
        score_part = min(0.35, max(0.0, (combined_signal_score - min_lora_score) / 100.0))
        length_part = max(0.0, min(0.25, (max_compact_ratio - min(ratio, max_compact_ratio)) / max_compact_ratio))
        duration_part = max(0.0, min(0.18, (max_duration - min(duration_sec, max_duration)) / max_duration))
        confidence = min(0.98, 0.42 + score_part + length_part + duration_part)

    if call_llm:
        reason = "call_llm:" + ",".join(reasons)
    elif strong_fast_lane:
        reason = "skip_llm:strong_lora_deep_stt_fast_lane"
    else:
        reason = "skip_llm:high_lora_deep_stt_confidence"
    return _decision(
        "llm_gate",
        call_llm=call_llm,
        reason=reason,
        reasons=reasons,
        strong_fast_lane=bool(strong_fast_lane),
        confidence=round(confidence, 4),
        compact_len=chars,
        threshold=threshold,
        compact_ratio=round(ratio, 4),
        duration_sec=round(duration_sec, 4),
        lora_score=round(lora_score, 4),
        segment_lora_score=round(signal_scores.get("lora_score", 0.0), 4),
        deep_score=round(signal_scores.get("deep_score", 0.0), 4),
        stt_lattice_score=round(signal_scores.get("stt_lattice_score", 0.0), 4),
        stt_score=round(signal_scores.get("stt_score", 0.0), 4),
        combined_signal_score=round(combined_signal_score, 4),
        min_lora_score=round(min_lora_score, 4),
        max_compact_ratio=round(max_compact_ratio, 4),
        strong_signal_score=round(strong_signal_score, 4),
        strong_max_compact_ratio=round(strong_max_ratio, 4),
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
    *,
    duration_sec: float | None = None,
) -> tuple[list[str] | None, dict[str, Any]]:
    """Validate LLM output and return None when the engine should roll back to safe splitting."""
    settings = dict(settings or {})
    cleaned = _clean_chunks(chunks)
    source_text_str = str(source_text or "")
    source_norm = normalized_text(source_text_str)
    candidate_text = " ".join(cleaned).strip()
    candidate_norm = normalized_text("".join(cleaned))
    similarity = similarity_ratio(source_norm, candidate_norm) if source_norm and candidate_norm else 0.0
    length_delta = abs(len(candidate_norm) - len(source_norm)) / max(1, len(source_norm)) if source_norm else 1.0
    length_policy = _llm_verifier_length_delta_policy(source_text_str, settings, duration_sec=duration_sec)
    missing_tokens_preview, added_tokens_preview = _token_diff_preview(source_text_str, candidate_text, profile)
    base_meta = {
        "chunk_count": len(cleaned),
        "source_compact_len": len(source_norm),
        "candidate_compact_len": len(candidate_norm),
        "similarity": round(similarity, 4),
        "length_delta_ratio": round(length_delta, 4),
        "lora_score": round(_profile_score(profile), 4),
        "missing_tokens_preview": missing_tokens_preview,
        "added_tokens_preview": added_tokens_preview,
        "length_delta_bucket": length_policy.get("bucket"),
        "max_length_delta_ratio_base": length_policy.get("base"),
        "max_length_delta_ratio_effective": length_policy.get("effective"),
        "length_delta_duration_adjust": length_policy.get("duration_adjust"),
        "source_duration_sec": length_policy.get("duration_sec"),
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
    max_delta = float(length_policy.get("effective") or _safe_float(settings.get("llm_verifier_max_length_delta_ratio"), 0.16))
    max_edit_distance = max(1, _safe_int(settings.get("llm_verifier_max_edit_distance"), 2))
    ok, reason = validate_llm_chunks(
        source_text,
        cleaned,
        min_similarity=min_similarity,
        max_length_delta_ratio=max_delta,
        max_edit_distance=max_edit_distance,
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


def describe_llm_verifier_decision(decision: dict[str, Any] | None) -> str:
    if not isinstance(decision, dict) or not decision:
        return "unknown"
    parts: list[str] = [str(decision.get("reason") or "unknown")]
    reason = str(decision.get("reason") or "")
    if reason.startswith("length_delta:"):
        if decision.get("length_delta_ratio") is not None:
            parts.append(f"delta={float(decision.get('length_delta_ratio') or 0.0):.2f}")
        effective = decision.get("max_length_delta_ratio_effective", decision.get("max_length_delta_ratio"))
        if effective is not None:
            parts.append(f"허용={float(effective or 0.0):.2f}")
        bucket = str(decision.get("length_delta_bucket") or "").strip()
        if bucket:
            parts.append(f"구간={bucket}")
    elif reason.startswith("similarity:") and decision.get("similarity") is not None:
        parts.append(f"similarity={float(decision.get('similarity') or 0.0):.2f}")

    violations = list(decision.get("preservation_violations") or [])
    if violations:
        first = dict(violations[0] or {})
        violation_type = str(first.get("type") or "")
        if violation_type == "number_changed":
            source_numbers = ",".join(str(item) for item in list(first.get("source_numbers") or [])[:4])
            candidate_numbers = ",".join(str(item) for item in list(first.get("candidate_numbers") or [])[:4])
            if source_numbers or candidate_numbers:
                parts.append(f"숫자={source_numbers}->{candidate_numbers}")
        missing = [str(item) for item in list(first.get("missing") or [])[:4] if str(item or "").strip()]
        added = [str(item) for item in list(first.get("added") or [])[:4] if str(item or "").strip()]
        if missing:
            parts.append("누락=" + ",".join(missing))
        if added:
            parts.append("추가=" + ",".join(added))
    else:
        missing_preview = [str(item) for item in list(decision.get("missing_tokens_preview") or [])[:4] if str(item or "").strip()]
        added_preview = [str(item) for item in list(decision.get("added_tokens_preview") or [])[:4] if str(item or "").strip()]
        if missing_preview:
            parts.append("누락=" + ",".join(missing_preview))
        if added_preview:
            parts.append("추가=" + ",".join(added_preview))
    return ", ".join(parts)


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
    shadow_duplicate_segments = 0
    self_repeat_segments = 0

    prev_start: float | None = None
    prev_end: float | None = None
    prev_text = ""
    prev_cps: float | None = None
    rows = [segment for segment in list(segments or []) if isinstance(segment, dict)]
    for index, segment in enumerate(rows):
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
        if _has_exact_tandem_repeat_text(text):
            self_repeat_segments += 1
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
                    similarity = similarity_ratio(compact, prev_text)
                    if similarity >= near_duplicate_ratio:
                        near_duplicate_segments += 1
            if (
                prev_cps is not None
                and compact_len(text) >= 5
                and cps > max(max_cps * 1.15, prev_cps * cps_jump_ratio)
            ):
                cps_jump_segments += 1
        if _shadow_duplicate_following_info(rows, index, settings):
            shadow_duplicate_segments += 1

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
            + shadow_duplicate_segments * 12.0
            + self_repeat_segments * 14.0
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
        "shadow_duplicate_segments": shadow_duplicate_segments,
        "self_repeat_segments": self_repeat_segments,
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
        shadow_info = _shadow_duplicate_following_info(rows, index, settings)

        if not compact:
            flags.append("empty_text")
        if _has_exact_tandem_repeat_text(text):
            flags.append("self_repeat_text")
        if any(phrase.lower() in text.lower() for phrase in _HALLUCINATION_PHRASES):
            flags.append("hallucination_phrase")
        if shadow_info:
            flags.append("shadow_duplicate_following")
            details["shadow_duplicate"] = shadow_info
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
                    similarity = similarity_ratio(compact, prev_text)
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
            penalty += 12.0 if "shadow_duplicate_following" in flags else 0.0
            penalty += 14.0 if "self_repeat_text" in flags else 0.0
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
    dropped_shadow_duplicates = 0
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
            and not _manual_timing_locked(current)
            and "shadow_duplicate_following" in flags
        ):
            dropped_shadow_duplicates += 1
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
    applied = bool(
        dropped_repeats
        or dropped_empty
        or dropped_hallucinations
        or dropped_shadow_duplicates
        or shifted_starts
        or extended_ends
    )
    decision = _decision(
        "context_repair",
        model=CONTEXT_CONSISTENCY_MODEL_ID,
        applied=applied,
        reason="repaired" if applied else "no_safe_repair",
        dropped_repeats=dropped_repeats,
        dropped_empty=dropped_empty,
        dropped_hallucinations=dropped_hallucinations,
        dropped_shadow_duplicates=dropped_shadow_duplicates,
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
            "shadow_duplicate_segments": before_metrics.get("shadow_duplicate_segments"),
        },
        after_counts={
            "repeated_segments": after_metrics.get("repeated_segments"),
            "near_duplicate_segments": after_metrics.get("near_duplicate_segments"),
            "overlap_segments": after_metrics.get("overlap_segments"),
            "timing_order_violations": after_metrics.get("timing_order_violations"),
            "cps_jump_segments": after_metrics.get("cps_jump_segments"),
            "shadow_duplicate_segments": after_metrics.get("shadow_duplicate_segments"),
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
        "context_shadow_duplicate_segments": int(context.get("shadow_duplicate_segments", 0) or 0),
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


from core.engine.subtitle_accuracy_review import (
    annotate_subtitle_auto_review,
    annotate_subtitle_completion_report,
    annotate_subtitle_stage_confidence,
    select_best_subtitle_output,
    subtitle_auto_review_items,
    subtitle_auto_review_summary,
    subtitle_completion_report,
    subtitle_output_variant_score,
    subtitle_stage_confidence,
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
    "describe_llm_verifier_decision",
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
