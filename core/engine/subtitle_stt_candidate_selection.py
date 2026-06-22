# Version: 03.14.29
# Phase: PHASE2
"""STT candidate selection and no-LLM raw STT restore helpers.

Behavior-preserving split from subtitle_engine.py.
"""

from __future__ import annotations

import json
import re
import sys

from core.audio.stt_lattice import select_stt_lattice_text
from core.engine.subtitle_accuracy_pipeline import llm_gate_decision
from core.engine.subtitle_final_integrity import (
    _best_stt_anchor_for_final_row,
    _source_stt_anchor_rows,
    get_local_dataset_corrections,
)
from core.engine.subtitle_llm_runtime import (
    _append_accuracy_decision_for_settings,
    _apply_llm_confidence_gate,
    _deep_rerank_chunks,
    _is_local_llm_connection_error,
    _local_ollama_ready,
    _mark_local_llm_unavailable,
    _profile_from_settings,
    _setting_bool,
    _setting_float,
    _setting_int,
    ollama_split_text,
)
from core.engine.subtitle_lora_packaging import (
    _find_matching_stt_candidate_for_decision,
    _stt_decision_speaker_fields,
)
from core.engine.subtitle_text_policy import clean_subtitle_text
from core.engine.subtitle_settings import _get_user_settings, _resolve_runtime_llm_model
from core.engine.subtitle_stt_candidate_helpers import (
    _candidate_span_from_decision,
    _selected_decision_word_span,
    _stt_candidate_compact_text,
    _stt_candidate_score100,
    _stt_candidate_similarity,
    _stt_decision_timing_span,
    _stt_selection_metadata,
)
from core.llm.gemini_provider import split_text as gemini_split_text
from core.llm.openai_provider import is_codex_model, is_openai_model, split_text as openai_split_text
from core.personalization.deep_subtitle_policy import (
    adjust_subtitle_timing as deep_adjust_subtitle_timing,
    select_stt_candidate as deep_select_stt_candidate,
)
from core.personalization.runtime_lora_context import build_runtime_lora_prompt
from core.personalization.subtitle_lora_runtime import attach_segment_lora_settings
from core.runtime.logger import get_logger


def _engine_attr(name: str, fallback):
    owner = sys.modules.get("core.engine.subtitle_engine")
    return getattr(owner, name, fallback)


_get_logger_fallback = get_logger


def get_logger(*args, **kwargs):
    return _engine_attr("get_logger", _get_logger_fallback)(*args, **kwargs)


_get_user_settings_fallback = _get_user_settings


def _get_user_settings(*args, **kwargs):
    return _engine_attr("_get_user_settings", _get_user_settings_fallback)(*args, **kwargs)


_resolve_runtime_llm_model_fallback = _resolve_runtime_llm_model


def _resolve_runtime_llm_model(*args, **kwargs):
    return _engine_attr("_resolve_runtime_llm_model", _resolve_runtime_llm_model_fallback)(*args, **kwargs)


_local_ollama_ready_fallback = _local_ollama_ready


def _local_ollama_ready(*args, **kwargs):
    return _engine_attr("_local_ollama_ready", _local_ollama_ready_fallback)(*args, **kwargs)


_mark_local_llm_unavailable_fallback = _mark_local_llm_unavailable


def _mark_local_llm_unavailable(*args, **kwargs):
    return _engine_attr("_mark_local_llm_unavailable", _mark_local_llm_unavailable_fallback)(*args, **kwargs)


_is_local_llm_connection_error_fallback = _is_local_llm_connection_error


def _is_local_llm_connection_error(*args, **kwargs):
    return _engine_attr("_is_local_llm_connection_error", _is_local_llm_connection_error_fallback)(*args, **kwargs)


_ollama_split_text_fallback = ollama_split_text


def ollama_split_text(*args, **kwargs):
    return _engine_attr("ollama_split_text", _ollama_split_text_fallback)(*args, **kwargs)


_openai_split_text_fallback = openai_split_text


def openai_split_text(*args, **kwargs):
    return _engine_attr("openai_split_text", _openai_split_text_fallback)(*args, **kwargs)


_gemini_split_text_fallback = gemini_split_text


def gemini_split_text(*args, **kwargs):
    return _engine_attr("gemini_split_text", _gemini_split_text_fallback)(*args, **kwargs)


_deep_select_stt_candidate_fallback = deep_select_stt_candidate


def deep_select_stt_candidate(*args, **kwargs):
    return _engine_attr("deep_select_stt_candidate", _deep_select_stt_candidate_fallback)(*args, **kwargs)


_deep_adjust_subtitle_timing_fallback = deep_adjust_subtitle_timing


def deep_adjust_subtitle_timing(*args, **kwargs):
    return _engine_attr("deep_adjust_subtitle_timing", _deep_adjust_subtitle_timing_fallback)(*args, **kwargs)


_attach_segment_lora_settings_fallback = attach_segment_lora_settings


def attach_segment_lora_settings(*args, **kwargs):
    return _engine_attr("attach_segment_lora_settings", _attach_segment_lora_settings_fallback)(*args, **kwargs)


_build_runtime_lora_prompt_fallback = build_runtime_lora_prompt


def build_runtime_lora_prompt(*args, **kwargs):
    return _engine_attr("build_runtime_lora_prompt", _build_runtime_lora_prompt_fallback)(*args, **kwargs)


_llm_gate_decision_fallback = llm_gate_decision


def llm_gate_decision(*args, **kwargs):
    return _engine_attr("llm_gate_decision", _llm_gate_decision_fallback)(*args, **kwargs)


_select_stt_lattice_text_fallback = select_stt_lattice_text


def select_stt_lattice_text(*args, **kwargs):
    return _engine_attr("select_stt_lattice_text", _select_stt_lattice_text_fallback)(*args, **kwargs)


def _attach_lora_and_deep_timing(row: dict, lora_meta: dict | None, settings: dict | None) -> dict:
    adjusted, timing_meta = deep_adjust_subtitle_timing(row, settings or {}, _profile_from_settings(settings))
    merged_meta = dict(lora_meta or {})
    if timing_meta:
        merged_meta["_deep_timing_policy"] = timing_meta
    attached = attach_segment_lora_settings(adjusted, merged_meta)
    for meta_key in (
        "_deep_rerank_policy",
        "_deep_candidate_selector_policy",
        "_deep_timing_policy",
        "_editor_truth_runtime_policy",
        "_stt_lattice_policy",
        "_llm_gate_policy",
        "_llm_minimize_policy",
        "_llm_candidate_policy",
        "_llm_verifier_policy",
        "_llm_rollback_policy",
        "_llm_rewrite_policy",
        "_llm_macro_chunk_policy",
        "_accuracy_decision_graph",
    ):
        if meta_key in merged_meta:
            attached[meta_key] = merged_meta[meta_key]
    return attached


def _select_stt_candidate_fast(seg: dict, settings: dict | None = None) -> dict | None:
    settings = settings or _get_user_settings()
    candidates = [
        c for c in list(seg.get("stt_candidates") or [])
        if isinstance(c, dict) and str(c.get("text", "") or "").strip()
    ]
    unique: list[dict] = []
    seen = set()
    for cand in candidates:
        key = re.sub(r"\s+", "", str(cand.get("text", "") or "")).lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(cand)
    if len(unique) < 2:
        return None

    raw_guard_decision = _select_raw_stt_candidate_when_current_is_unbacked(
        seg,
        unique,
        settings,
        selector="stt_raw_candidate_guard",
    )
    if raw_guard_decision:
        return raw_guard_decision

    lattice_decision, lattice_meta = select_stt_lattice_text(seg, settings, _profile_from_settings(settings))
    if lattice_decision:
        lattice_meta = dict(lattice_meta or {})
        raw_ok, raw_meta = _stt_decision_matches_raw_candidate(lattice_decision, unique, settings)
        lattice_meta["raw_candidate_guard"] = raw_meta
        if not raw_ok:
            get_logger().log(
                "[STT격자-딥러닝판정] STT1/STT2 원문과 의미 거리가 커서 자동 선택 보류: "
                f"similarity={raw_meta.get('similarity_to_raw_candidate', '-')}"
            )
        else:
            selected = dict(lattice_decision)
            selected["_stt_lattice_policy"] = lattice_meta
            selected.setdefault("selector", "stt_lattice")
            get_logger().log(
                f"[STT격자-딥러닝판정] 단어 {lattice_meta.get('replacements', 0)}개 교체 "
                f"confidence={lattice_meta.get('confidence', '-')}: "
                f"'{str(selected.get('text', '') or '')[:18]}...'"
            )
            return selected

    if seg.get("stt_ensemble_primary_locked"):
        return None
    deep_decision = deep_select_stt_candidate({**seg, "stt_candidates": unique}, settings, _profile_from_settings(settings))
    if deep_decision:
        raw_ok, raw_meta = _stt_decision_matches_raw_candidate(deep_decision, unique, settings)
        if not raw_ok:
            get_logger().log(
                "[STT앙상블-딥러닝판정] STT1/STT2 원문과 의미 거리가 커서 자동 선택 보류: "
                f"similarity={raw_meta.get('similarity_to_raw_candidate', '-')}"
            )
            return None
        deep_decision = {**deep_decision, "_stt_raw_candidate_guard": raw_meta}
        source = str(deep_decision.get("source", "") or "").strip().upper()
        label = str(deep_decision.get("label", "") or "").strip()
        get_logger().log(
            f"[STT앙상블-딥러닝판정] {label or '-'}({source or '-'}) 선택 "
            f"score={deep_decision.get('score', '-')} margin={deep_decision.get('margin', '-')}: "
            f"'{str(deep_decision.get('text', '') or '')[:18]}...'"
        )
        return deep_decision
    if _setting_bool(settings, "stt_selection_score_fallback_enabled", True):
        best_candidate = _best_scored_stt_candidate(unique)
        best_score = _stt_candidate_score100(best_candidate)
        current_score = _stt_current_candidate_score(seg, unique)
        min_score = _setting_float(settings, "stt_selection_score_fallback_min_score", 84.0)
        min_margin = _setting_float(settings, "stt_selection_score_fallback_min_margin", 12.0)
        if (
            best_candidate
            and best_score >= min_score
            and (best_score - current_score) >= min_margin
            and _stt_candidate_similarity(str(best_candidate.get("text", "") or ""), str(seg.get("text", "") or "")) < 0.995
        ):
            selected_text = str(best_candidate.get("text", "") or "").strip()
            selected_source = str(best_candidate.get("source", "") or "").strip().upper()
            get_logger().log(
                "[STT앙상블-점수판정] 최고 STT 점수 후보 우선 선택: "
                f"{selected_source or '-'} score={best_score:.1f} margin={best_score - current_score:.1f} "
                f"'{selected_text[:18]}...'"
            )
            return {
                "text": selected_text,
                "source": selected_source,
                "label": str(best_candidate.get("label") or best_candidate.get("stt_label") or "score").strip(),
                "start": best_candidate.get("start"),
                "end": best_candidate.get("end"),
                "words": list(best_candidate.get("words") or []),
                "score": best_candidate.get("score", best_candidate.get("stt_score")),
                "selector": "stt_candidate_score_fallback",
                **_stt_decision_speaker_fields(best_candidate, seg),
            }
    return None


def _llm_model_disabled(model: str | None) -> bool:
    return not str(model or "").strip() or "사용 안함" in str(model or "")


def _raw_stt_candidates(candidates: list[dict] | tuple[dict, ...]) -> list[dict]:
    rows = []
    for candidate in list(candidates or []):
        if not isinstance(candidate, dict):
            continue
        source = str(
            candidate.get("source")
            or candidate.get("stt_preview_source")
            or candidate.get("stt_source")
            or candidate.get("engine")
            or ""
        ).strip().upper()
        text = str(candidate.get("text", candidate.get("output", "")) or "").strip()
        if source in {"STT1", "STT2"} and text:
            item = dict(candidate)
            item["source"] = source
            item["text"] = text
            rows.append(item)
    return rows


def _candidate_decision_from_raw_stt(candidate: dict, selector: str, reason: str) -> dict:
    selected_text = str(candidate.get("text", "") or "").strip()
    selected_source = str(candidate.get("source", "") or "").strip().upper()
    return {
        "text": selected_text,
        "source": selected_source,
        "label": str(candidate.get("label") or candidate.get("stt_label") or reason or selected_source or "raw").strip(),
        "start": candidate.get("start"),
        "end": candidate.get("end"),
        "words": list(candidate.get("words") or []),
        "score": candidate.get("score", candidate.get("stt_score")),
        "selector": selector,
        "_stt_no_llm_raw_candidate_policy": {
            "task": "stt_no_llm_raw_candidate_lock",
            "reason": reason,
            "source": selected_source,
            "raw_text": selected_text,
        },
        **_stt_decision_speaker_fields(candidate, {}),
    }


def _select_stt_candidate_without_llm(seg: dict, candidates: list[dict], settings: dict | None) -> dict | None:
    raw_candidates = _raw_stt_candidates(candidates)
    if not raw_candidates:
        return None

    selected_sources = []
    for key in (
        "manual_stt_candidate_source",
        "stt_selected_source",
        "stt_ensemble_llm_selected_source",
        "stt_ensemble_fast_selected_source",
        "stt_ensemble_source",
    ):
        source = str(seg.get(key, "") or "").strip().upper()
        if source in {"STT1", "STT2"} and source not in selected_sources:
            selected_sources.append(source)
    for source in selected_sources:
        matches = [candidate for candidate in raw_candidates if str(candidate.get("source", "") or "").strip().upper() == source]
        if matches:
            chosen = max(matches, key=_stt_candidate_score100)
            return _candidate_decision_from_raw_stt(chosen, "stt_raw_candidate_no_llm", "selected_source")

    raw_guard_decision = _select_raw_stt_candidate_when_current_is_unbacked(
        seg,
        raw_candidates,
        settings,
        selector="stt_raw_candidate_guard_no_llm",
    )
    if raw_guard_decision:
        return raw_guard_decision

    current_text = str(seg.get("text", "") or "").strip()
    if current_text:
        current_key = _stt_candidate_compact_text(current_text)
        if any(_stt_candidate_compact_text(str(candidate.get("text", "") or "")) == current_key for candidate in raw_candidates):
            return None

    if _setting_bool(settings or {}, "stt_selection_score_fallback_enabled", True):
        best_candidate = _best_scored_stt_candidate(raw_candidates)
        best_score = _stt_candidate_score100(best_candidate)
        current_score = _stt_current_candidate_score(seg, raw_candidates)
        min_score = _setting_float(settings or {}, "stt_selection_score_fallback_min_score", 84.0)
        min_margin = _setting_float(settings or {}, "stt_selection_score_fallback_min_margin", 12.0)
        if (
            best_candidate
            and best_score >= min_score
            and (best_score - current_score) >= min_margin
            and _stt_candidate_similarity(str(best_candidate.get("text", "") or ""), current_text) < 0.995
        ):
            get_logger().log(
                "[STT앙상블-LLM꺼짐] raw STT 후보만 보수 선택: "
                f"{str(best_candidate.get('source', '') or '-')} score={best_score:.1f} "
                f"'{str(best_candidate.get('text', '') or '')[:18]}...'"
            )
            return _candidate_decision_from_raw_stt(best_candidate, "stt_candidate_score_fallback_no_llm", "score_fallback")
    return None


from core.engine.subtitle_stt_candidate_helpers import (
    _stt_candidate_compact_text,
    _stt_candidate_score100,
    _stt_candidate_similarity,
    _stt_decision_timing_span,
    _stt_selection_metadata,
)


def _best_scored_stt_candidate(candidates: list[dict] | tuple[dict, ...]) -> dict | None:
    rows = [c for c in list(candidates or []) if isinstance(c, dict) and str(c.get("text", "") or "").strip()]
    if not rows:
        return None
    return max(
        rows,
        key=lambda candidate: (
            _stt_candidate_score100(candidate),
            len(_stt_candidate_compact_text(str(candidate.get("text", "") or ""))),
        ),
    )


def _stt_current_candidate_score(seg: dict, candidates: list[dict] | tuple[dict, ...]) -> float:
    current_text = str((seg or {}).get("text", "") or "")
    current_score = _stt_candidate_score100(seg)
    best_match_score = 0.0
    best_match_similarity = 0.0
    for candidate in list(candidates or []):
        if not isinstance(candidate, dict):
            continue
        similarity = _stt_candidate_similarity(current_text, str(candidate.get("text", "") or ""))
        if similarity > best_match_similarity:
            best_match_similarity = similarity
            best_match_score = _stt_candidate_score100(candidate)
    if best_match_similarity >= 0.96:
        return best_match_score
    return current_score


def _select_raw_stt_candidate_when_current_is_unbacked(
    seg: dict,
    candidates: list[dict] | tuple[dict, ...],
    settings: dict | None,
    *,
    selector: str,
) -> dict | None:
    if not _setting_bool(settings or {}, "stt_selection_raw_guard_enabled", True):
        return None
    raw_candidates = _raw_stt_candidates(candidates)
    if not raw_candidates:
        return None
    current_text = str((seg or {}).get("text", "") or "").strip()
    if not current_text:
        return None
    best_similarity = max(_stt_candidate_similarity(current_text, str(candidate.get("text", "") or "")) for candidate in raw_candidates)
    compact_len = len(_stt_candidate_compact_text(current_text))
    min_similarity = _setting_float(settings or {}, "stt_selection_raw_guard_min_similarity", 0.68)
    if compact_len <= 12:
        min_similarity = max(min_similarity, 0.76)
    elif compact_len <= 24:
        min_similarity = max(min_similarity, 0.72)
    if best_similarity >= min_similarity:
        return None
    best_candidate = _best_scored_stt_candidate(raw_candidates)
    if not best_candidate:
        return None
    min_score = _setting_float(settings or {}, "stt_selection_raw_guard_min_score", 0.0)
    best_score = _stt_candidate_score100(best_candidate)
    if best_score < min_score:
        return None
    source = str(best_candidate.get("source", "") or "").strip().upper()
    selected_text = str(best_candidate.get("text", "") or "").strip()
    get_logger().log(
        "[STT원문가드] 현재 자막이 STT1/STT2 후보와 멀어 raw 후보로 복구: "
        f"{source or '-'} similarity={best_similarity:.3f}/{min_similarity:.3f} "
        f"score={best_score:.1f} '{selected_text[:18]}...'"
    )
    return _candidate_decision_from_raw_stt(best_candidate, selector, "current_not_stt_candidate")


def _stt_decision_matches_raw_candidate(decision: dict | None, candidates: list[dict], settings: dict | None) -> tuple[bool, dict]:
    decision_text = str((decision or {}).get("text", "") or "").strip()
    if not decision_text:
        return False, {"accepted": False, "reason": "empty_decision"}
    raw = [
        c for c in list(candidates or [])
        if isinstance(c, dict)
        and str(c.get("text", "") or "").strip()
        and str(c.get("source", "") or "").strip().upper() in {"STT1", "STT2"}
    ]
    if not raw:
        raw = [c for c in list(candidates or []) if isinstance(c, dict) and str(c.get("text", "") or "").strip()]
    if not raw:
        return False, {"accepted": False, "reason": "no_raw_candidates"}
    best_similarity = max(_stt_candidate_similarity(decision_text, str(c.get("text", "") or "")) for c in raw)
    compact_len = len(_stt_candidate_compact_text(decision_text))
    min_similarity = _setting_float(settings or {}, "stt_selection_min_raw_candidate_similarity", 0.72)
    if compact_len <= 12:
        min_similarity = max(min_similarity, 0.82)
    elif compact_len <= 24:
        min_similarity = max(min_similarity, 0.76)
    ok = best_similarity >= min_similarity
    return ok, {
        "accepted": ok,
        "reason": "raw_candidate_similarity" if ok else "too_far_from_stt1_stt2",
        "similarity_to_raw_candidate": round(best_similarity, 4),
        "min_similarity": round(min_similarity, 4),
    }


def _stt_candidate_risk_flags(seg: dict, candidates: list[dict]) -> set[str]:
    flags: set[str] = set()
    for row in [seg, *candidates]:
        for flag in row.get("stt_score_flags") or []:
            flags.add(str(flag))
        quality = dict(row.get("quality") or {})
        for flag in quality.get("flags") or []:
            flags.add(str(flag))
    return flags


def _should_run_stt_candidate_llm_judge(seg: dict, candidates: list[dict], settings: dict | None) -> bool:
    settings = settings or {}
    if not _setting_bool(settings, "stt_ensemble_llm_judge_require_risk", True):
        return True
    if len(candidates) < 2:
        return False

    texts = [str(c.get("text", "") or "").strip() for c in candidates]
    if len({_stt_candidate_compact_text(text) for text in texts if text}) < 2:
        return False

    if seg.get("stt_ensemble_primary_locked") or seg.get("stt_ensemble_needs_llm_review"):
        return True
    if seg.get("stt_ensemble_inserted_from_stt2") or str(seg.get("_uncertainty_bucket") or "") == "precision":
        return True

    scores = [_stt_candidate_score100(c) for c in candidates]
    current_score = _stt_candidate_score100(seg)
    low_threshold = _setting_float(settings, "stt_ensemble_llm_judge_low_score_threshold", 78.0)
    if current_score and current_score < low_threshold:
        return True
    if any(score and score < low_threshold for score in scores):
        return True

    score_span = max(scores or [0.0]) - min(scores or [0.0])
    min_delta = _setting_float(settings, "stt_ensemble_llm_judge_min_score_delta", 10.0)
    if score_span >= min_delta:
        return True

    max_similarity = _setting_float(settings, "stt_ensemble_llm_judge_max_similarity", 0.94)
    pair_similarity = min(
        _stt_candidate_similarity(texts[i], texts[j])
        for i in range(len(texts))
        for j in range(i + 1, len(texts))
    )
    if pair_similarity <= max_similarity:
        return True

    risky_flags = {
        "low_avg_logprob",
        "high_no_speech_prob",
        "high_compression_ratio",
        "low_word_confidence",
        "peer_text_disagreement",
        "repetition_hallucination_risk",
        "known_hallucination_phrase",
        "outside_vad_speech",
    }
    return bool(_stt_candidate_risk_flags(seg, candidates).intersection(risky_flags))


def _parse_stt_candidate_llm_label(raw_decision: str, labels: list[str]) -> str | None:
    text = str(raw_decision or "").strip()
    if not text:
        return None
    valid = {label.upper(): label for label in labels}

    def _from_value(value) -> str | None:
        if isinstance(value, str):
            compact = value.strip().upper()
            if compact in valid:
                return valid[compact]
            match = re.search(r"\b([A-Z])\b", compact)
            if match and match.group(1) in valid:
                return valid[match.group(1)]
        if isinstance(value, list):
            for item in value:
                found = _from_value(item)
                if found:
                    return found
        if isinstance(value, dict):
            for key in ("selected", "selection", "label", "choice", "answer", "winner"):
                found = _from_value(value.get(key))
                if found:
                    return found
            for item in value.values():
                found = _from_value(item)
                if found:
                    return found
        return None

    try:
        parsed = json.loads(text)
        found = _from_value(parsed)
        if found:
            return found
    except Exception:
        pass

    match = re.search(r"(?:선택|selected|selection|choice|answer|winner)\s*[:=]?\s*[\"']?([A-Z])", text, re.IGNORECASE)
    if match and match.group(1).upper() in valid:
        return valid[match.group(1).upper()]
    leading = re.match(r"^\s*(?:\[)?\s*[\"']?([A-Z])\b", text)
    if leading and leading.group(1).upper() in valid:
        return valid[leading.group(1).upper()]
    matches = [m.group(1).upper() for m in re.finditer(r"\b([A-Z])\b", text)]
    usable = [valid[label] for label in matches if label in valid]
    if len(usable) == 1:
        return usable[0]
    return None


def _apply_stt_candidate_decision(seg: dict, selected_decision: dict | None) -> tuple[dict, bool]:
    if not selected_decision:
        return dict(seg or {}), False
    selected_text = str(selected_decision.get("text", "") or "").strip()
    if not selected_text:
        return dict(seg or {}), False
    selected_source = str(selected_decision.get("source", "") or "").strip().upper()
    selector_name = str(selected_decision.get("selector") or "")
    is_deep_selector = bool(selector_name) and selector_name not in {
        "stt_lattice",
        "stt_candidate_llm_judge",
        "stt_candidate_score_fallback",
    }
    matched_candidate = _find_matching_stt_candidate_for_decision(seg, selected_decision)
    speaker_fields = _stt_decision_speaker_fields(selected_decision, matched_candidate or seg)
    out = {
        **dict(seg or {}),
        "text": selected_text,
        "stt_ensemble_llm_selected_source": selected_source,
        "stt_ensemble_llm_selected_label": str(selected_decision.get("label", "") or ""),
        "stt_ensemble_fast_selected_source": selected_source,
        "stt_ensemble_fast_selected_label": str(selected_decision.get("label", "") or ""),
        "stt_ensemble_deep_selected_source": selected_source if is_deep_selector else "",
        "stt_ensemble_deep_selected_label": str(selected_decision.get("label", "") or "") if is_deep_selector else "",
        "stt_ensemble_deep_selected_score": selected_decision.get("score") if is_deep_selector else None,
        "stt_ensemble_deep_selected_margin": selected_decision.get("margin") if is_deep_selector else None,
        "_stt_lattice_policy": selected_decision.get("_stt_lattice_policy") or seg.get("_stt_lattice_policy"),
        "_stt_no_llm_raw_candidate_policy": selected_decision.get("_stt_no_llm_raw_candidate_policy") or seg.get("_stt_no_llm_raw_candidate_policy"),
        "_deep_candidate_selector_policy": selected_decision.get("_deep_candidate_selector_policy") or seg.get("_deep_candidate_selector_policy"),
        "_llm_gate_policy": selected_decision.get("_llm_gate_policy") or seg.get("_llm_gate_policy"),
        **speaker_fields,
    }
    if selected_decision.get("words"):
        out["words"] = list(selected_decision.get("words") or [])
    selected_span = _stt_decision_timing_span(selected_decision)
    if selected_span is not None:
        selected_start, selected_end = selected_span
        out["start"] = selected_start
        out["end"] = selected_end
        out["_stt_original_candidate_start"] = selected_start
        out["_stt_original_candidate_end"] = selected_end
        out["original_start"] = selected_start
        out["original_end"] = selected_end
        word_span = _selected_decision_word_span(selected_decision)
        raw_span = _candidate_span_from_decision(selected_decision)
        if word_span is not None and raw_span is not None and selected_span == word_span:
            out["_stt_candidate_word_timing_anchor_policy"] = {
                "task": "stt_candidate_word_timing_anchor",
                "old_start": round(raw_span[0], 3),
                "old_end": round(raw_span[1], 3),
                "word_start": round(word_span[0], 3),
                "word_end": round(word_span[1], 3),
            }
    return out, True


def _select_stt_candidate_text(
    seg: dict,
    model: str,
    user_prompt: str,
    api_key: str,
    settings: dict | None = None,
    rules: dict | None = None,
) -> dict | None:
    settings = settings or _get_user_settings()
    if not settings.get("stt_ensemble_llm_judge_enabled", True):
        return None
    candidates = [
        c for c in list(seg.get("stt_candidates") or [])
        if str(c.get("text", "") or "").strip()
    ]
    unique: list[dict] = []
    seen = set()
    for cand in candidates:
        key = re.sub(r"\s+", "", str(cand.get("text", "") or "")).lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(cand)
    if len(unique) < 2:
        return None
    if _llm_model_disabled(model):
        return _select_stt_candidate_without_llm(seg, unique, settings)
    fast_decision = _select_stt_candidate_fast({**seg, "stt_candidates": unique}, settings)
    if fast_decision:
        return fast_decision
    if not _should_run_stt_candidate_llm_judge(seg, unique, settings):
        return None
    if not model or "사용 안함" in model:
        return None
    if _setting_bool(settings, "stt_ensemble_llm_judge_local_only", True) and (
        "Gemini" in model or is_openai_model(model) or is_codex_model(model)
    ):
        get_logger().log(f"[STT앙상블-LLM판정] 로컬 LLM 전용 정책으로 외부/CLI 모델 생략: {model}")
        return None

    unique = unique[:2]
    labels = ["A", "B"]
    lines = []
    for label, cand in zip(labels, unique):
        lines.append(
            f"{label}. [{cand.get('source', label)} / score {cand.get('score', '-')}] "
            f"{str(cand.get('text', '')).strip()}"
        )
    prompt = (
        "당신은 한국어 영상 자막 검수자입니다.\n"
        "아래 앞뒤 문맥을 참고해서 STT 후보 중 실제 발화와 가장 가까운 후보 하나만 고르세요.\n"
        "없는 말을 새로 만들거나 두 후보를 섞지 말고, 후보의 뜻을 바꾸는 추론은 하지 마세요.\n"
        "애매하면 score가 더 높은 STT 원문 후보를 고르세요.\n"
        "반드시 JSON 배열로만 답하세요. 예: [\"A\"] 또는 [\"B\"]\n\n"
        f"시간: {float(seg.get('start', 0) or 0):.2f}s ~ {float(seg.get('end', 0) or 0):.2f}s\n"
        f"이전 문맥: {str(seg.get('stt_ensemble_context_prev', '') or '').strip()[:220] or '(없음)'}\n"
        f"다음 문맥: {str(seg.get('stt_ensemble_context_next', '') or '').strip()[:220] or '(없음)'}\n"
        + "\n".join(lines)
    )
    if user_prompt.strip():
        prompt += f"\n\n사용자 지시 참고: {user_prompt.strip()[:500]}"
    lora_context = build_runtime_lora_prompt(
        " ".join(
            [
                str(seg.get("text", "") or ""),
                str(seg.get("stt_ensemble_context_prev", "") or ""),
                str(seg.get("stt_ensemble_context_next", "") or ""),
                " ".join(str(candidate.get("text", "") or "") for candidate in unique),
            ]
        ),
        rules or {},
        settings,
        include_retrieval=False,
    )
    if lora_context:
        prompt += f"\n\n[STT 후보 선택용 LoRA 근거]\n{lora_context}"

    gate_text = " ".join(str(candidate.get("text", "") or "") for candidate in unique)
    stt_llm_gate = llm_gate_decision(
        {**seg, "stt_ensemble_needs_llm_review": True},
        settings,
        _profile_from_settings(settings),
        text=gate_text,
        threshold=max(1, _setting_int(settings, "split_length_threshold", 16)),
        duration=max(0.0, float(seg.get("end", 0) or 0) - float(seg.get("start", 0) or 0)),
    )
    if not stt_llm_gate.get("call_llm", True):
        get_logger().log(
            f"[STT앙상블-LLM게이트] LoRA/딥러닝 신뢰로 후보 LLM 생략: "
            f"'{str(seg.get('text', '') or '')[:18]}...'"
        )
        return None

    try:
        if "Gemini" in model:
            chunks = gemini_split_text(api_key, model, prompt)
        elif is_openai_model(model):
            chunks = openai_split_text(api_key, model, prompt)
        else:
            if not _local_ollama_ready(model, "STT 앙상블 LLM"):
                return None
            model = _resolve_runtime_llm_model(model, logger=get_logger(), context="STT 앙상블 LLM")
            chunks = ollama_split_text(model, prompt)
    except Exception as exc:
        if _is_local_llm_connection_error(exc):
            _mark_local_llm_unavailable(model, "STT 앙상블 LLM", str(exc))
            return None
        get_logger().log(f"[STT앙상블-LLM판정 실패] {exc}")
        return None

    decision = " ".join(str(x) for x in (chunks or []))
    selected_label = _parse_stt_candidate_llm_label(decision, labels)
    if selected_label not in labels:
        fallback_candidate = _best_scored_stt_candidate(unique)
        if not fallback_candidate:
            get_logger().log(f"[STT앙상블-LLM판정] 응답 파싱 실패, 자동 선택 보류: {decision[:120]}")
            return None
        selected = str(fallback_candidate.get("text", "") or "").strip()
        if not selected:
            return None
        selected_source = str(fallback_candidate.get("source", "") or "").strip().upper()
        fallback_label = str(fallback_candidate.get("label") or fallback_candidate.get("stt_label") or "score").strip()
        get_logger().log(
            "[STT앙상블-LLM판정] 응답 파싱 실패, 최고 STT 점수 후보로 보수 선택: "
            f"{selected_source or '-'} score={_stt_candidate_score100(fallback_candidate):.1f} '{selected[:18]}...'"
        )
        return {
            "text": selected,
            "source": selected_source,
            "label": fallback_label,
            "start": fallback_candidate.get("start"),
            "end": fallback_candidate.get("end"),
            "words": list(fallback_candidate.get("words") or []),
            "score": fallback_candidate.get("score", fallback_candidate.get("stt_score")),
            "selector": "stt_candidate_score_fallback",
            "_llm_gate_policy": stt_llm_gate,
            **_stt_decision_speaker_fields(fallback_candidate, seg),
        }
    selected_index = labels.index(selected_label)
    selected_candidate = unique[selected_index]
    selected = str(selected_candidate.get("text", "") or "").strip()
    selected_source = str(selected_candidate.get("source", "") or "").strip().upper()
    if selected:
        get_logger().log(f"[STT앙상블-LLM판정] {labels[selected_index]}({selected_source or '-'}) 선택: '{selected[:18]}...'")
    if not selected:
        return None
    return {
        "text": selected,
        "source": selected_source,
        "label": labels[selected_index],
        "start": selected_candidate.get("start"),
        "end": selected_candidate.get("end"),
        "words": list(selected_candidate.get("words") or []),
        "score": selected_candidate.get("score", selected_candidate.get("stt_score")),
        "selector": "stt_candidate_llm_judge",
        "_llm_gate_policy": stt_llm_gate,
        **_stt_decision_speaker_fields(selected_candidate, seg),
    }



def _sanitize(segments: list[dict] | None) -> list[dict]:
    """Backward-compatible test hook for legacy subtitle filter overrides."""
    return [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]


def _restore_no_llm_raw_stt_text(
    segments: list[dict] | None,
    source_segments: list[dict] | None = None,
    settings: dict | None = None,
) -> list[dict]:
    trace_callback = None
    if isinstance(settings, dict):
        trace_callback = settings.get("_benchmark_no_llm_raw_restore_trace")

    def _emit_trace(step: str, row: dict, *, decision: str, reason: str, anchor_text: str = "", similarity: float | None = None) -> None:
        if not callable(trace_callback):
            return
        try:
            split_policy = dict(row.get("_common_split_guard_policy") or {})
            raw_policy = dict(row.get("_stt_no_llm_raw_candidate_policy") or {})
            words = row.get("words")
            word_text = ""
            if isinstance(words, list):
                word_text = " ".join(
                    str(word.get("word", word.get("text", "")) or "").strip()
                    for word in words
                    if isinstance(word, dict) and str(word.get("word", word.get("text", "")) or "").strip()
                ).strip()
            payload = {
                "step": str(step or "").strip(),
                "decision": str(decision or "").strip(),
                "reason": str(reason or "").strip(),
                "start": float(row.get("start", 0.0) or 0.0),
                "end": float(row.get("end", row.get("start", 0.0)) or row.get("start", 0.0) or 0.0),
                "text": str(row.get("text", "") or "").strip(),
                "split_index": split_policy.get("split_index"),
                "split_count": split_policy.get("split_count"),
                "has_common_split_policy": bool(split_policy),
                "raw_lock_reason": str(raw_policy.get("reason") or "").strip(),
                "restored_after_postprocess": bool(raw_policy.get("restored_after_postprocess")),
                "raw_text": str(row.get("_stt_no_llm_raw_text") or raw_policy.get("raw_text") or "").strip(),
                "word_text": word_text,
                "selected_source": str(row.get("stt_selected_source") or row.get("stt_ensemble_source") or "").strip(),
                "anchor_text": str(anchor_text or "").strip(),
            }
            if similarity is not None:
                payload["similarity"] = round(float(similarity), 4)
            trace_callback(payload)
        except Exception:
            pass

    corrections = get_local_dataset_corrections()
    rows = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        row = dict(seg)
        policy = dict(row.get("_stt_no_llm_raw_candidate_policy") or {})
        raw_text = str(row.get("_stt_no_llm_raw_text") or policy.get("raw_text") or "").strip()
        if raw_text and str(row.get("text", "") or "").strip() != raw_text:
            current_text = str(row.get("text", "") or "").strip()
            cleanup_policy = dict(row.get("_final_sequence_cleanup_policy") or {})
            if (
                str(cleanup_policy.get("action") or "").strip().lower() == "merge"
                and len(_stt_candidate_compact_text(current_text)) > len(_stt_candidate_compact_text(raw_text))
            ):
                _emit_trace("raw_restore", row, decision="skip", reason="merge_cleanup_preserved")
                rows.append(row)
                continue
            current_compact = _stt_candidate_compact_text(current_text)
            raw_compact = _stt_candidate_compact_text(raw_text)
            corrected_raw_text = clean_subtitle_text(raw_text, corrections if isinstance(corrections, dict) else None)
            if corrected_raw_text and _stt_candidate_compact_text(corrected_raw_text) == _stt_candidate_compact_text(current_text):
                _emit_trace("raw_restore", row, decision="skip", reason="already_matches_corrected_raw")
                rows.append(row)
                continue
            split_policy = dict(row.get("_common_split_guard_policy") or {})
            row["text"] = raw_text
            policy.update(
                {
                    "task": "stt_no_llm_raw_text_lock",
                    "restored_after_postprocess": True,
                    "raw_text": raw_text,
                }
            )
            row["_stt_no_llm_raw_candidate_policy"] = policy
            _emit_trace("raw_restore", row, decision="restore", reason="raw_text_mismatch")
        else:
            _emit_trace("raw_restore", row, decision="keep", reason="no_raw_restore_needed")
        rows.append(row)
    if not rows or not source_segments:
        return rows

    anchors = [
        anchor
        for anchor in _source_stt_anchor_rows(source_segments)
        if str(anchor.get("source", "") or "").strip().upper().split("_", 1)[0] in {"STT1", "STT2"}
    ]
    if not anchors:
        return rows
    restored_count = 0
    restored_rows: list[dict] = []
    for raw_row in rows:
        row = dict(raw_row)
        text = str(row.get("text", "") or "").strip()
        if not text or row.get("is_gap"):
            _emit_trace("anchor_restore", row, decision="skip", reason="empty_or_gap")
            restored_rows.append(row)
            continue
        anchor, meta = _best_stt_anchor_for_final_row(row, anchors, settings or {})
        if not anchor:
            _emit_trace("anchor_restore", row, decision="skip", reason="no_anchor_match")
            restored_rows.append(row)
            continue
        anchor_text = str(anchor.get("text", "") or "").strip()
        if not anchor_text:
            _emit_trace("anchor_restore", row, decision="skip", reason="empty_anchor_text")
            restored_rows.append(row)
            continue
        row_compact = _stt_candidate_compact_text(text)
        anchor_compact = _stt_candidate_compact_text(anchor_text)
        if row_compact == anchor_compact or (anchor_compact and anchor_compact in row_compact):
            _emit_trace("anchor_restore", row, decision="skip", reason="already_matches_anchor", anchor_text=anchor_text)
            restored_rows.append(row)
            continue
        split_policy = dict(row.get("_common_split_guard_policy") or {})
        if (
            _setting_bool(settings or {}, "subtitle_no_llm_raw_stt_lock_preserve_common_split_rows", False)
            and str(split_policy.get("action") or "").strip().lower() == "split"
            and int(split_policy.get("split_count") or 0) > 1
            and row_compact
            and anchor_compact
            and row_compact in anchor_compact
        ):
            _emit_trace("anchor_restore", row, decision="skip", reason="preserve_common_split_row", anchor_text=anchor_text)
            restored_rows.append(row)
            continue
        if row_compact and row_compact in anchor_compact:
            missing_chars = max(0, len(anchor_compact) - len(row_compact))
            allowed_missing = max(4, int(round(len(anchor_compact) * 0.33)))
            if missing_chars <= allowed_missing:
                _emit_trace("anchor_restore", row, decision="skip", reason="subset_within_missing_budget", anchor_text=anchor_text)
                restored_rows.append(row)
                continue
        similarity = _stt_candidate_similarity(text, anchor_text)
        min_similarity = _setting_float(settings or {}, "subtitle_no_llm_raw_stt_lock_min_similarity", 0.82)
        if similarity >= min_similarity:
            _emit_trace("anchor_restore", row, decision="skip", reason="similar_enough", anchor_text=anchor_text, similarity=similarity)
            restored_rows.append(row)
            continue
        row.update(
            {
                "text": anchor_text,
                "start": float(anchor.get("start", row.get("start", 0.0)) or 0.0),
                "end": float(anchor.get("end", row.get("end", row.get("start", 0.0))) or 0.0),
                "stt_selected_source": str(anchor.get("source") or row.get("stt_selected_source") or "STT"),
                "_stt_original_candidate_start": float(anchor.get("start", row.get("start", 0.0)) or 0.0),
                "_stt_original_candidate_end": float(anchor.get("end", row.get("end", row.get("start", 0.0))) or 0.0),
            }
        )
        policy = dict(row.get("_stt_no_llm_raw_candidate_policy") or {})
        policy.update(
            {
                "task": "stt_no_llm_raw_text_lock",
                "reason": "postprocess_candidate_drift",
                "restored_after_postprocess": True,
                "old_text": text,
                "raw_text": anchor_text,
                "source": str(anchor.get("source") or "STT"),
                "similarity_to_raw_candidate": round(similarity, 4),
                **dict(meta or {}),
            }
        )
        row["_stt_no_llm_raw_candidate_policy"] = policy
        _emit_trace("anchor_restore", row, decision="restore", reason="postprocess_candidate_drift", anchor_text=anchor_text, similarity=similarity)
        restored_rows.append(row)
        restored_count += 1
    if restored_count:
        get_logger().log(f"[STT원문잠금] 자막 LLM OFF 후처리 이탈 {restored_count}개를 STT1/2 원문으로 복구")
    return restored_rows
