from __future__ import annotations

import hashlib
import math
import re
from statistics import median
from typing import Any

from core.native_text_similarity import similarity_ratio


DEEP_POLICY_SCHEMA = "ai_subtitle_studio.deep_subtitle_policy.v1"
DEEP_POLICY_MODEL_ID = "feature_mlp_fallback_v1"

_SETTING_KEYS = (
    "continuous_threshold",
    "gap_push_rate",
    "gap_pull_rate",
    "single_subtitle_end",
    "split_length_threshold",
    "subtitle_target_line_count",
    "llm_confidence_gate_min_lora_score",
    "sub_min_duration",
    "sub_max_duration",
    "sub_max_cps",
    "sub_dedup_window",
    "sub_gap_break_sec",
    "word_timing_gap_break_sec",
    "deep_timing_max_shift_sec",
    "chunk_time_limit",
    "subtitle_bundle_target_sec",
    "subtitle_bundle_min_sec",
    "subtitle_bundle_max_sec",
)


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _compact(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


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


def _clamp(value: Any, low: float, high: float, default: float | None = None) -> float:
    fallback = low if default is None else default
    return max(float(low), min(float(high), _safe_float(value, fallback)))


def _clamp_int(value: Any, low: int, high: int, default: int | None = None) -> int:
    fallback = low if default is None else default
    return max(int(low), min(int(high), _safe_int(value, fallback)))


def _hash_unit(payload: Any) -> float:
    text = repr(payload).encode("utf-8", errors="ignore")
    digest = hashlib.sha256(text).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _setting_bool(settings: dict[str, Any] | None, key: str, default: bool = True) -> bool:
    settings = settings or {}
    value = settings.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "사용 안함", "끔"}
    return bool(value)


def deep_policy_enabled(settings: dict[str, Any] | None) -> bool:
    return _setting_bool(settings, "deep_subtitle_policy_enabled", True)


def _token_overlap(a: str, b: str) -> float:
    left = set(re.findall(r"[\w가-힣]+", str(a or "").lower()))
    right = set(re.findall(r"[\w가-힣]+", str(b or "").lower()))
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def text_similarity(a: Any, b: Any) -> float:
    left = _compact(a)
    right = _compact(b)
    if not left or not right:
        return 0.0
    char_ratio = similarity_ratio(left, right)
    token_ratio = _token_overlap(str(a or ""), str(b or ""))
    return max(0.0, min(1.0, (char_ratio * 0.72) + (token_ratio * 0.28)))


def _profile_examples(profile: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    for item in list((profile or {}).get("examples") or []):
        if not isinstance(item, dict):
            continue
        for key in ("output", "text", "input"):
            text = _norm(item.get(key))
            if text:
                out.append(text)
                break
    return out


def _profile_example_candidates(profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, item in enumerate(list((profile or {}).get("examples") or [])):
        if not isinstance(item, dict):
            continue
        text = ""
        for key in ("output", "text", "input"):
            text = _norm(item.get(key))
            if text:
                break
        if not text:
            continue
        score = _safe_float(item.get("score"), _safe_float((profile or {}).get("top_score"), 0.0))
        if score > 1.0:
            score = score / 100.0
        out.append(
            {
                "source": f"LORA_{str(item.get('kind') or 'EXAMPLE').upper()}",
                "text": text,
                "score": _clamp(score, 0.0, 1.0, 0.0),
                "candidate_role": "lora_similar_subtitle",
                "example_index": index,
            }
        )
    return out[:6]


def _profile_setting_values(profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    profile = profile or {}
    out: list[dict[str, Any]] = []
    for key in ("applied_settings", "retrieved_settings"):
        values = dict(profile.get(key) or {})
        if values:
            out.append(values)
    for item in list(profile.get("setting_sources") or []):
        if isinstance(item, dict) and isinstance(item.get("settings"), dict):
            out.append(dict(item.get("settings") or {}))
    return out


def _profile_exclusions(profile: dict[str, Any] | None) -> list[str]:
    exclusions = []
    for item in list((profile or {}).get("exclusions") or []):
        if isinstance(item, dict) and _norm(item.get("text")):
            exclusions.append(_norm(item.get("text")))
    return exclusions


def _profile_top_score(profile: dict[str, Any] | None) -> float:
    return _clamp((profile or {}).get("top_score", 0.0), 0.0, 100.0, 0.0) / 100.0


def _pattern_settings(profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = profile or {}
    settings = profile.get("pattern_settings")
    if isinstance(settings, dict) and settings:
        return dict(settings)
    pattern = profile.get("pattern_match")
    if isinstance(pattern, dict) and isinstance(pattern.get("settings"), dict):
        return dict(pattern.get("settings") or {})
    return {}


def _excluded_penalty(text: str, profile: dict[str, Any] | None) -> float:
    compact_text = _compact(text)
    if not compact_text:
        return 0.0
    penalty = 0.0
    for excluded in _profile_exclusions(profile):
        ex = _compact(excluded)
        if ex and ex in compact_text:
            penalty = max(penalty, 0.42)
    return penalty


def _profile_style_score(text: str, settings: dict[str, Any], profile: dict[str, Any] | None) -> float:
    pattern = _pattern_settings(profile)
    if pattern:
        compact_len = len(_compact(text))
        target_len = _clamp_int(pattern.get("split_length_threshold", settings.get("split_length_threshold", 16)), 6, 40, 16)
        if compact_len <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - min(1.0, abs(compact_len - target_len) / max(6.0, target_len))))
    examples = _profile_examples(profile)
    if examples:
        example_score = max(text_similarity(text, example) for example in examples)
    else:
        example_score = 0.35

    compact_len = len(_compact(text))
    target_len = _clamp_int(settings.get("split_length_threshold", 16), 6, 40, 16)
    if compact_len <= 0:
        length_score = 0.0
    else:
        length_score = 1.0 - min(1.0, abs(compact_len - target_len) / max(6.0, target_len))

    return max(0.0, min(1.0, (example_score * 0.65) + (length_score * 0.35) - _excluded_penalty(text, profile)))


def _candidate_text_score(
    original_text: str,
    chunks: list[str],
    settings: dict[str, Any],
    profile: dict[str, Any] | None,
) -> float:
    text = _norm(" ".join(_norm(chunk) for chunk in chunks if _norm(chunk)))
    if not text:
        return 0.0

    integrity = text_similarity(original_text, text)
    style = _profile_style_score(text, settings, profile)
    max_chars = _clamp_int(settings.get("split_length_threshold", 16), 6, 40, 16)
    chunk_lengths = [len(_compact(chunk)) for chunk in chunks if _compact(chunk)]
    if not chunk_lengths:
        split_score = 0.0
    else:
        overflow = max(0, max(chunk_lengths) - int(max_chars * 1.45))
        underflow = sum(1 for count in chunk_lengths if count <= 1)
        split_score = max(0.0, 1.0 - (overflow / max(1.0, max_chars)) - (underflow * 0.2))
    target_lines = _safe_int(settings.get("subtitle_target_line_count"), 0)
    if target_lines > 0:
        line_score = max(0.0, 1.0 - (abs(len(chunks) - target_lines) / max(1.0, float(target_lines))))
    else:
        line_score = 0.65

    # The fallback behaves like a tiny learned scorer: original integrity is a guardrail,
    # then LoRA style similarity decides between safe candidates.
    return max(0.0, min(1.0, (integrity * 0.43) + (style * 0.34) + (split_score * 0.13) + (line_score * 0.10)))


def rerank_subtitle_candidates(
    original_text: Any,
    candidate_lists: list[list[str]],
    settings: dict[str, Any] | None,
    profile: dict[str, Any] | None,
) -> tuple[list[str], dict[str, Any]]:
    settings = dict(settings or {})
    if not deep_policy_enabled(settings) or not _setting_bool(settings, "deep_subtitle_reranker_enabled", True):
        return list(candidate_lists[0] if candidate_lists else []), {}

    original = _norm(original_text)
    pattern_only = _setting_bool(settings, "deep_policy_pattern_only_enabled", False)
    scored: list[tuple[float, int, list[str]]] = []
    seen: set[str] = set()
    for index, chunks in enumerate(list(candidate_lists or [])):
        clean_chunks = [_norm(chunk) for chunk in list(chunks or []) if _norm(chunk)]
        key = "\n".join(_compact(chunk) for chunk in clean_chunks)
        if not clean_chunks or key in seen:
            continue
        seen.add(key)
        if pattern_only and _pattern_settings(profile):
            text = _norm(" ".join(clean_chunks))
            target_len = _clamp_int(_pattern_settings(profile).get("split_length_threshold", settings.get("split_length_threshold", 16)), 6, 40, 16)
            line_target = _safe_int(_pattern_settings(profile).get("subtitle_target_line_count"), _safe_int(settings.get("subtitle_target_line_count"), 0))
            length_score = 1.0 - min(1.0, abs(len(_compact(text)) - target_len) / max(6.0, target_len))
            line_score = 0.65 if line_target <= 0 else max(0.0, 1.0 - abs(len(clean_chunks) - line_target) / max(1.0, float(line_target)))
            score = max(0.0, min(1.0, (length_score * 0.74) + (line_score * 0.26)))
        else:
            score = _candidate_text_score(original, clean_chunks, settings, profile)
        scored.append((score, index, clean_chunks))

    if not scored:
        return [], {}
    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    best_score, best_index, best_chunks = scored[0]
    base_score = next((score for score, index, _chunks in scored if index == 0), best_score)
    margin = float(best_score - base_score)
    min_margin = _clamp(settings.get("deep_subtitle_reranker_min_margin", 0.03), 0.0, 0.4, 0.03)
    chosen = best_chunks if best_index == 0 or margin >= min_margin else list(candidate_lists[0])
    metadata = {
        "schema": DEEP_POLICY_SCHEMA,
        "model": DEEP_POLICY_MODEL_ID,
        "task": "subtitle_rerank",
        "chosen_index": int(best_index if chosen == best_chunks else 0),
        "best_score": round(best_score, 4),
        "base_score": round(base_score, 4),
        "margin": round(margin, 4),
        "profile_score": round(_profile_top_score(profile), 4),
        "candidate_count": len(scored),
    }
    return chosen, metadata


def _weighted_setting_from_profile(profile: dict[str, Any] | None, key: str) -> Any:
    values = []
    for index, source in enumerate(_profile_setting_values(profile)):
        if key not in source or source.get(key) in (None, ""):
            continue
        weight = 1.0 / (index + 1)
        values.append((source.get(key), weight))
    if not values:
        return None
    numeric = []
    for value, weight in values:
        try:
            numeric.append((float(value), float(weight)))
        except Exception:
            return values[0][0]
    total_weight = sum(weight for _value, weight in numeric) or 1.0
    return sum(value * weight for value, weight in numeric) / total_weight


def predict_segment_settings(
    segment: dict[str, Any],
    base_settings: dict[str, Any] | None,
    profile: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    settings = dict(base_settings or {})
    if not deep_policy_enabled(settings) or not _setting_bool(settings, "deep_segment_setting_policy_enabled", True):
        return {}, {}

    predicted: dict[str, Any] = {}
    pattern = _pattern_settings(profile)
    if pattern and _setting_bool(settings, "deep_policy_pattern_only_enabled", False):
        for key, value in pattern.items():
            if key not in _SETTING_KEYS or value in (None, ""):
                continue
            if key in {"split_length_threshold", "sub_max_cps"}:
                predicted[key] = _clamp_int(value, 6, 40 if key == "split_length_threshold" else 24, _safe_int(settings.get(key), 16))
            elif key == "subtitle_target_line_count":
                predicted[key] = _clamp_int(value, 1, 3, _safe_int(settings.get(key), 0) or 1)
            elif key in {"gap_push_rate", "gap_pull_rate"}:
                predicted[key] = round(_clamp(value, 0.0, 1.0, _safe_float(settings.get(key), 0.5)), 3)
            elif key == "single_subtitle_end":
                predicted[key] = round(_clamp(value, 0.0, 2.0, _safe_float(settings.get(key), 0.2)), 3)
            else:
                predicted[key] = round(_clamp(value, 0.05, 12.0, _safe_float(settings.get(key), 1.0)), 3)
        if predicted:
            return predicted, {
                "schema": DEEP_POLICY_SCHEMA,
                "model": f"{DEEP_POLICY_MODEL_ID}:pattern_fast_path",
                "task": "segment_setting_policy",
                "confidence": round(max(_profile_top_score(profile), 0.72), 4),
                "applied_keys": sorted(predicted),
                "segment_chars": len(_compact(segment.get("text"))),
                "pattern_only": True,
            }
    for key in _SETTING_KEYS:
        value = _weighted_setting_from_profile(profile, key)
        if value in (None, ""):
            continue
        if key in {"split_length_threshold", "sub_max_cps"}:
            predicted[key] = _clamp_int(value, 6, 40 if key == "split_length_threshold" else 24, _safe_int(settings.get(key), 16))
        elif key == "subtitle_target_line_count":
            predicted[key] = _clamp_int(value, 1, 3, _safe_int(settings.get(key), 0) or 1)
        elif key == "llm_confidence_gate_min_lora_score":
            predicted[key] = round(_clamp(value, 40.0, 98.0, _safe_float(settings.get(key), 82.0)), 3)
        elif key in {"chunk_time_limit", "subtitle_bundle_target_sec", "subtitle_bundle_min_sec", "subtitle_bundle_max_sec"}:
            predicted[key] = _clamp_int(value, 30, 900, _safe_int(settings.get(key), 180))
        elif key in {"gap_push_rate", "gap_pull_rate"}:
            predicted[key] = round(_clamp(value, 0.0, 1.0, _safe_float(settings.get(key), 0.5)), 3)
        elif key == "single_subtitle_end":
            predicted[key] = round(_clamp(value, 0.0, 2.0, _safe_float(settings.get(key), 0.2)), 3)
        elif key in {"sub_min_duration", "sub_max_duration", "continuous_threshold", "sub_gap_break_sec", "word_timing_gap_break_sec", "sub_dedup_window"}:
            predicted[key] = round(_clamp(value, 0.05, 12.0, _safe_float(settings.get(key), 1.0)), 3)

    example_lengths = [len(_compact(text)) for text in _profile_examples(profile) if _compact(text)]
    if example_lengths and "split_length_threshold" not in predicted:
        predicted["split_length_threshold"] = _clamp_int(median(example_lengths), 6, 40, _safe_int(settings.get("split_length_threshold"), 16))

    examples = list((profile or {}).get("examples") or [])
    cps_values = [
        _safe_float(item.get("cps"), 0.0)
        for item in examples
        if isinstance(item, dict) and _safe_float(item.get("cps"), 0.0) > 0.0
    ]
    if cps_values and "sub_max_cps" not in predicted:
        predicted["sub_max_cps"] = _clamp_int(max(cps_values), 8, 24, _safe_int(settings.get("sub_max_cps"), 12))

    confidence = max(_profile_top_score(profile), 0.35 if _profile_examples(profile) else 0.0)
    line_count_values: list[int] = []
    for item in examples:
        if not isinstance(item, dict):
            continue
        style_profile = item.get("style_profile") if isinstance(item.get("style_profile"), dict) else {}
        line_count = _safe_int((style_profile.get("line_break") or {}).get("line_count"), 0)
        if line_count <= 0:
            text = _norm(item.get("text") or item.get("output") or item.get("input"))
            if text:
                line_count = max(1, len([line for line in str(text).splitlines() if _norm(line)]))
        if line_count > 0:
            line_count_values.append(_clamp_int(line_count, 1, 3, 1))
    if (
        _setting_bool(settings, "subtitle_target_line_count_auto_enabled", True)
        and line_count_values
        and "subtitle_target_line_count" not in predicted
    ):
        predicted["subtitle_target_line_count"] = _clamp_int(median(line_count_values), 1, 3, 1)
    if "llm_confidence_gate_min_lora_score" not in predicted:
        if confidence >= 0.90:
            predicted["llm_confidence_gate_min_lora_score"] = 78.0
        elif confidence <= 0.45:
            predicted["llm_confidence_gate_min_lora_score"] = 92.0
    exploration: dict[str, Any] = {}
    rate = _clamp(settings.get("deep_segment_setting_exploration_rate", 0.04), 0.0, 1.0, 0.04)
    if rate > 0.0 and confidence < 0.92:
        seed = {
            "text": _compact(segment.get("text")),
            "start": round(_safe_float(segment.get("start"), 0.0), 2),
            "profile_score": round(confidence, 3),
        }
        unit = _hash_unit(seed)
        if unit <= rate:
            before_keys = set(predicted)
            branch = int(_hash_unit({**seed, "branch": "setting"}) * 4) % 4
            if branch == 0 and "split_length_threshold" not in predicted:
                base = _safe_int(settings.get("split_length_threshold"), 16)
                predicted["split_length_threshold"] = _clamp_int(base + (2 if _hash_unit({**seed, "direction": 1}) >= 0.5 else -2), 6, 40, base)
            elif branch == 1 and "sub_gap_break_sec" not in predicted:
                base = _safe_float(settings.get("sub_gap_break_sec"), 1.5)
                predicted["sub_gap_break_sec"] = round(_clamp(base + (0.15 if _hash_unit({**seed, "direction": 2}) >= 0.5 else -0.15), 0.5, 3.0, base), 3)
            elif branch == 2 and "sub_max_cps" not in predicted:
                base = _safe_int(settings.get("sub_max_cps"), 12)
                predicted["sub_max_cps"] = _clamp_int(base + (1 if _hash_unit({**seed, "direction": 3}) >= 0.5 else -1), 8, 24, base)
            elif branch == 3 and "continuous_threshold" not in predicted:
                base = _safe_float(settings.get("continuous_threshold"), 2.0)
                predicted["continuous_threshold"] = round(_clamp(base + (0.2 if _hash_unit({**seed, "direction": 4}) >= 0.5 else -0.2), 0.5, 5.0, base), 3)
            if set(predicted) != before_keys:
                exploration = {
                    "enabled": True,
                    "rate": round(rate, 4),
                    "unit": round(unit, 6),
                    "branch": branch,
                    "reason": "low_confidence_contextual_bandit",
                }

    if not predicted:
        return {}, {}

    metadata = {
        "schema": DEEP_POLICY_SCHEMA,
        "model": DEEP_POLICY_MODEL_ID,
        "task": "segment_setting_policy",
        "confidence": round(confidence, 4),
        "applied_keys": sorted(predicted),
        "segment_chars": len(_compact(segment.get("text"))),
    }
    if exploration:
        metadata["exploration"] = exploration
    return predicted, metadata


def _candidate_base_score(candidate: dict[str, Any]) -> float:
    raw = candidate.get("score", candidate.get("stt_score", 0.0))
    value = _safe_float(raw, 0.0)
    if value > 1.0:
        value = value / 100.0
    return _clamp(value, 0.0, 1.0, 0.0)


def select_stt_candidate(
    segment: dict[str, Any],
    settings: dict[str, Any] | None,
    profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    settings = dict(settings or {})
    if not deep_policy_enabled(settings) or not _setting_bool(settings, "deep_stt_candidate_selector_enabled", True):
        return None

    candidate_keys = (
        "stt_candidates",
        "vad_candidates",
        "stt_retry_candidates",
        "stt_recheck_candidates",
        "stt_rescue_candidates",
        "stt_lattice_candidates",
    )
    candidates: list[dict[str, Any]] = []
    for key in candidate_keys:
        for candidate in list(segment.get(key) or []):
            if not isinstance(candidate, dict) or not _norm(candidate.get("text")):
                continue
            row = dict(candidate)
            row.setdefault("candidate_role", key)
            candidates.append(row)
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_text_by_key: dict[str, str] = {}
    for candidate in candidates:
        key = _compact(candidate.get("text"))
        if key and key not in seen:
            seen.add(key)
            seen_text_by_key[key] = _norm(candidate.get("text"))
            unique.append(candidate)

    current_text = _norm(segment.get("text"))
    lora_min_similarity = _clamp(settings.get("deep_stt_candidate_lora_min_similarity", 0.86), 0.0, 1.0, 0.86)
    if not (_setting_bool(settings, "deep_policy_pattern_only_enabled", False) and _pattern_settings(profile)):
        for candidate in _profile_example_candidates(profile):
            text = _norm(candidate.get("text"))
            key = _compact(text)
            if not key:
                continue
            if key in seen and seen_text_by_key.get(key) == text:
                continue
            nearest = max(
                [text_similarity(text, current_text)]
                + [text_similarity(text, row.get("text")) for row in unique[:6]]
            )
            if nearest < lora_min_similarity:
                continue
            seen.add(key)
            seen_text_by_key[key] = text
            unique.append(candidate)

    if len(unique) < 2:
        return None

    scored: list[tuple[float, int, dict[str, Any]]] = []
    source_counts: dict[str, int] = {}
    max_candidates = _clamp_int(settings.get("deep_stt_candidate_pool_limit", 6), 2, 12, 6)
    for index, candidate in enumerate(unique[:max_candidates]):
        text = _norm(candidate.get("text"))
        base = _candidate_base_score(candidate)
        role = str(candidate.get("candidate_role") or "stt_candidates")
        source = str(candidate.get("source") or role or "").strip().upper()
        source_counts[source or role] = int(source_counts.get(source or role, 0) or 0) + 1
        profile_score = _profile_style_score(text, settings, profile)
        continuity = max(
            text_similarity(text, current_text),
            text_similarity(text, segment.get("stt_ensemble_context_prev")),
            text_similarity(text, segment.get("stt_ensemble_context_next")),
        )
        source_prior = 0.06 if source.startswith(("STT", "VAD", "RECHECK", "RETRY", "RESCUE")) else 0.0
        if source.startswith("LORA"):
            source_prior = min(0.05, _profile_top_score(profile) * 0.06)
            base = max(base, _profile_top_score(profile) * 0.82)
        score = (base * 0.30) + (profile_score * 0.45) + (continuity * 0.18) + source_prior
        scored.append((max(0.0, min(1.0, score)), index, candidate))

    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    best_score, best_index, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_score - second_score
    if best_score < _clamp(settings.get("deep_stt_candidate_min_score", 0.56), 0.0, 1.0, 0.56):
        return None
    if margin < _clamp(settings.get("deep_stt_candidate_min_margin", 0.18), 0.0, 1.0, 0.18):
        return None

    labels = ["A", "B", "C"]
    policy = {
        "schema": DEEP_POLICY_SCHEMA,
        "model": DEEP_POLICY_MODEL_ID,
        "task": "stt_candidate_competition",
        "candidate_count": len(scored),
        "source_counts": source_counts,
        "best_score": round(best_score, 4),
        "second_score": round(second_score, 4),
        "margin": round(margin, 4),
        "profile_score": round(_profile_top_score(profile), 4),
    }
    return {
        "text": _norm(best.get("text")),
        "source": str(best.get("source", "") or "").strip().upper(),
        "label": labels[min(best_index, len(labels) - 1)],
        "score": round(best_score, 4),
        "margin": round(margin, 4),
        "selector": DEEP_POLICY_MODEL_ID,
        "_deep_candidate_selector_policy": policy,
    }


def adjust_subtitle_timing(
    segment: dict[str, Any],
    settings: dict[str, Any] | None,
    profile: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    settings = dict(settings or {})
    row = dict(segment or {})
    if not deep_policy_enabled(settings) or not _setting_bool(settings, "deep_timing_adjustment_enabled", True):
        return row, {}

    start = _safe_float(row.get("start"), 0.0)
    end = _safe_float(row.get("end"), start)
    if end <= start:
        return row, {}

    max_shift = _clamp(settings.get("deep_timing_max_shift_sec", 0.12), 0.0, 0.5, 0.12)
    min_duration = _clamp(settings.get("sub_min_duration", 0.2), 0.05, 2.0, 0.2)
    max_duration = _clamp(settings.get("sub_max_duration", 6.0), max(min_duration, 0.5), 12.0, 6.0)
    old_start, old_end = start, end

    words = [word for word in list(row.get("words") or []) if isinstance(word, dict)]
    if words:
        first = _safe_float(words[0].get("start"), start)
        last = _safe_float(words[-1].get("end"), end)
        if first > 0.0:
            start = start + max(-max_shift, min(max_shift, first - start))
        if last > start:
            end = end + max(-max_shift, min(max_shift, last - end))

    if (end - start) < min_duration:
        end = start + min_duration
    if (end - start) > max_duration:
        end = start + max_duration

    if abs(start - old_start) < 0.001 and abs(end - old_end) < 0.001:
        return row, {}

    row["start"] = round(start, 3)
    row["end"] = round(end, 3)
    metadata = {
        "schema": DEEP_POLICY_SCHEMA,
        "model": DEEP_POLICY_MODEL_ID,
        "task": "subtitle_timing_adjustment",
        "start_shift": round(start - old_start, 4),
        "end_shift": round(end - old_end, 4),
        "profile_score": round(_profile_top_score(profile), 4),
    }
    row["_deep_timing_policy"] = metadata
    return row, metadata


def _row_score(row: dict[str, Any], keys: tuple[str, ...]) -> float:
    return max(_safe_float(row.get(key), 0.0) for key in keys)


def score_cut_boundary(row: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = dict(settings or {})
    if not _setting_bool(settings, "deep_cut_boundary_model_enabled", True):
        return {
            "schema": DEEP_POLICY_SCHEMA,
            "model": DEEP_POLICY_MODEL_ID,
            "task": "cut_boundary_score",
            "score": 0.0,
            "decision": "disabled",
        }

    visual = _row_score(row, ("score", "color_score", "delta", "window_score"))
    visual_norm = 1.0 - math.exp(-(max(0.0, visual) / 120.0))
    audio_delta = abs(
        _safe_float(
            row.get("audio_gain_db_delta", row.get("delta_db", row.get("gain_delta_db"))),
            0.0,
        )
    )
    audio_threshold = max(1.0, _safe_float(settings.get("scan_cut_audio_gain_threshold_db"), 10.0))
    audio_norm = min(1.0, audio_delta / (audio_threshold * 1.4))
    source = str(row.get("source") or row.get("provisional_source") or "").lower()
    source_boost = 0.12 if "audio" in source else 0.0
    if "visual" in source or "rollback" in source:
        source_boost = max(source_boost, 0.08)
    has_regions = bool(row.get("regions") or row.get("candidate_regions"))
    region_boost = 0.06 if has_regions else 0.0

    combined = max(0.0, min(1.0, (visual_norm * 0.52) + (audio_norm * 0.34) + source_boost + region_boost))
    keep_threshold = _clamp(settings.get("deep_cut_boundary_keep_threshold", 0.72), 0.0, 1.0, 0.72)
    verify_threshold = _clamp(settings.get("deep_cut_boundary_verify_threshold", 0.46), 0.0, 1.0, 0.46)
    if combined >= keep_threshold and visual_norm >= 0.35:
        decision = "keep"
    elif combined >= verify_threshold or (audio_norm >= 0.75 and combined >= verify_threshold * 0.75):
        decision = "verify"
    else:
        decision = "drop_hint"

    return {
        "schema": DEEP_POLICY_SCHEMA,
        "model": DEEP_POLICY_MODEL_ID,
        "task": "cut_boundary_score",
        "score": round(combined, 4),
        "decision": decision,
        "visual_score": round(visual_norm, 4),
        "audio_score": round(audio_norm, 4),
        "audio_delta_db": round(audio_delta, 3),
    }


def annotate_cut_boundary_rows(rows: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        scored = score_cut_boundary(row, settings)
        out = dict(row)
        out["deep_boundary_score"] = scored.get("score", 0.0)
        out["deep_boundary_decision"] = scored.get("decision", "")
        out["deep_boundary_model"] = scored.get("model", DEEP_POLICY_MODEL_ID)
        annotated.append(out)
    return annotated


def _row_chars(row: dict[str, Any]) -> int:
    return len(_compact(row.get("text")))


def _duration(row: dict[str, Any]) -> float:
    return max(0.001, _safe_float(row.get("end"), 0.0) - _safe_float(row.get("start"), 0.0))


def smooth_subtitle_sequence(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    settings = dict(settings or {})
    if not deep_policy_enabled(settings) or not _setting_bool(settings, "deep_sequence_smoothing_enabled", True):
        return [dict(row) for row in list(segments or []) if isinstance(row, dict)], {}
    rows = [dict(row) for row in list(segments or []) if isinstance(row, dict)]
    if len(rows) < 2:
        return rows, {}

    max_shift = _clamp(settings.get("deep_sequence_max_shift_sec", 0.18), 0.0, 0.8, 0.18)
    bridge_gap = _clamp(settings.get("deep_sequence_bridge_gap_sec", 0.3), 0.0, 2.0, 0.3)
    max_cps = _clamp(settings.get("sub_max_cps", 12), 6.0, 30.0, 12.0)
    min_duration = _clamp(settings.get("sub_min_duration", 0.2), 0.05, 2.0, 0.2)
    changed = 0
    hard_cases = 0

    for index, row in enumerate(rows):
        row.setdefault("_deep_sequence_policy", {"schema": DEEP_POLICY_SCHEMA, "model": DEEP_POLICY_MODEL_ID, "task": "sequence_smoothing", "changes": []})
        changes = list(dict(row.get("_deep_sequence_policy") or {}).get("changes") or [])
        start = _safe_float(row.get("start"), 0.0)
        end = _safe_float(row.get("end"), start)
        if end <= start:
            continue

        if index > 0:
            prev = rows[index - 1]
            prev_end = _safe_float(prev.get("end"), start)
            if start < prev_end:
                boundary = round((start + prev_end) * 0.5, 3)
                prev["end"] = boundary
                row["start"] = boundary
                changes.append({"type": "overlap_midpoint", "from_start": round(start, 3), "to_start": boundary})
                changed += 1
                start = boundary

        next_start = _safe_float(rows[index + 1].get("start"), end) if index + 1 < len(rows) else None
        gap_to_next = (next_start - end) if next_start is not None else 0.0
        cps = _row_chars(row) / _duration(row)
        if cps > max_cps and gap_to_next > 0.02:
            needed = (_row_chars(row) / max_cps) - _duration(row)
            shift = min(max_shift, max(0.0, gap_to_next * 0.55), max(0.0, needed))
            if shift >= 0.01:
                old_end = end
                end = round(end + shift, 3)
                row["end"] = end
                changes.append({"type": "high_cps_extend", "from_end": round(old_end, 3), "to_end": end, "cps": round(cps, 3)})
                changed += 1

        duration = _duration(row)
        if duration < min_duration and gap_to_next > 0.02:
            shift = min(max_shift, max(0.0, gap_to_next * 0.5), max(0.0, min_duration - duration))
            if shift >= 0.01:
                old_end = _safe_float(row.get("end"), end)
                row["end"] = round(old_end + shift, 3)
                changes.append({"type": "min_duration_extend", "from_end": round(old_end, 3), "to_end": row["end"]})
                changed += 1

        if gap_to_next is not None and 0.0 <= gap_to_next <= bridge_gap and cps > (max_cps * 1.15):
            hard_cases += 1
            changes.append({"type": "hard_case_dense_sequence", "gap_to_next": round(gap_to_next, 3), "cps": round(cps, 3)})

        if changes:
            row["_deep_sequence_policy"] = {
                "schema": DEEP_POLICY_SCHEMA,
                "model": DEEP_POLICY_MODEL_ID,
                "task": "sequence_smoothing",
                "changes": changes[-6:],
            }
        elif "_deep_sequence_policy" in row:
            row.pop("_deep_sequence_policy", None)

    summary = {
        "schema": DEEP_POLICY_SCHEMA,
        "model": DEEP_POLICY_MODEL_ID,
        "task": "sequence_smoothing",
        "changed_segments": int(changed),
        "hard_cases": int(hard_cases),
        "segment_count": len(rows),
    }
    return rows, summary if changed or hard_cases else {}


__all__ = [
    "DEEP_POLICY_MODEL_ID",
    "DEEP_POLICY_SCHEMA",
    "adjust_subtitle_timing",
    "annotate_cut_boundary_rows",
    "deep_policy_enabled",
    "predict_segment_settings",
    "rerank_subtitle_candidates",
    "score_cut_boundary",
    "select_stt_candidate",
    "smooth_subtitle_sequence",
    "text_similarity",
]
