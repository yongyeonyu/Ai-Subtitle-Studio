from __future__ import annotations

import re
from statistics import median
from typing import Any

from core.audio.stt_lattice import STT_LATTICE_CANDIDATE_KEYS, collect_stt_lattice_candidates
from core.engine.subtitle_settings import _setting_int
from core.personalization.deep_subtitle_policy import predict_segment_settings
from core.personalization.lora_retrieval_config import INDEX_JSON_SOURCE_KEYS, INDEX_JSONL_SOURCE_KEYS, RUNTIME_SETTING_KEYS
from core.personalization.lora_retrieval_scoring import runtime_settings_from_retrieved_items
from core.personalization.lora_vector_retriever import retrieve_lora_context
from core.personalization.runtime_lora_context import runtime_lora_enabled
from core.personalization.subtitle_pattern_index import match_subtitle_pattern, segment_pattern_features


SEGMENT_LORA_GAP_SETTING_KEYS = frozenset(
    {
        "continuous_threshold",
        "gap_push_rate",
        "gap_pull_rate",
        "single_subtitle_end",
        "split_length_threshold",
        "subtitle_target_line_count",
        "subtitle_target_line_count_auto_enabled",
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
    }
)

SEGMENT_LORA_SETTING_KEYS = frozenset(
    {
        *SEGMENT_LORA_GAP_SETTING_KEYS,
        "subtitle_quality_auto_check_after_generate",
        "subtitle_quality_auto_correct_enabled",
        "editor_lora_runtime_enabled",
        "correction_memory_enabled",
        "wrong_answer_memory_enabled",
        "review_auto_correct_apply_threshold",
        "review_auto_correct_min_improvement",
        "review_recheck_buffer_sec",
        "deep_subtitle_policy_enabled",
        "deep_segment_setting_policy_enabled",
        "deep_subtitle_reranker_enabled",
        "deep_subtitle_reranker_min_margin",
        "deep_stt_candidate_selector_enabled",
        "deep_stt_candidate_min_score",
        "deep_stt_candidate_min_margin",
        "deep_timing_adjustment_enabled",
        "deep_timing_max_shift_sec",
        "deep_sequence_smoothing_enabled",
        "deep_sequence_max_shift_sec",
        "deep_sequence_bridge_gap_sec",
        "deep_segment_setting_exploration_rate",
        "deep_policy_event_logging_enabled",
        "deep_policy_event_max_rows_per_run",
        "deep_policy_hard_case_margin",
        "deep_hard_case_mining_enabled",
        "stt_lattice_selector_enabled",
        "stt_lattice_min_confidence",
        "stt_lattice_replace_margin",
        "stt_lattice_min_match_score",
        "stt_lattice_require_word_timestamps",
        "llm_threads_auto_enabled",
        "llm_workers_auto_enabled",
        "llm_threads_resource_max",
        "subtitle_llm_macro_chunk_enabled",
        "subtitle_llm_macro_chunk_min_rows",
        "subtitle_llm_macro_chunk_max_rows",
        "subtitle_llm_macro_chunk_use_cut_boundaries",
        "roughcut_llm_threads_auto_enabled",
        "roughcut_llm_threads_resource_max",
        "roughcut_llm_rows_auto_enabled",
        "roughcut_llm_rows_lora_enabled",
        "roughcut_llm_rows_lora_blend",
        "roughcut_llm_rows_exploration_rate",
        "roughcut_llm_max_context_rows",
        "roughcut_llm_chunk_rows",
        "roughcut_llm_lookahead_rows",
        "roughcut_llm_context_min_rows",
        "roughcut_llm_context_max_rows",
        "roughcut_llm_chunk_min_rows",
        "roughcut_llm_chunk_max_rows",
        "roughcut_llm_lookahead_min_rows",
        "roughcut_llm_lookahead_max_rows",
        "subtitle_bundle_autopilot_enabled",
        "subtitle_bundle_lora_enabled",
        "subtitle_bundle_lora_blend",
        "subtitle_bundle_use_confirmed_cuts",
        "subtitle_bundle_use_provisional_cuts",
        "subtitle_bundle_confirmed_cut_min_sec",
        "subtitle_bundle_provisional_cut_min_sec",
        "subtitle_bundle_boundary_snap_window_sec",
        "llm_confidence_gate_enabled",
        "llm_confidence_gate_min_lora_score",
        "llm_confidence_gate_max_compact_ratio",
        "llm_minimize_enabled",
        "llm_minimize_min_gate_confidence",
        "llm_minimize_required_signal_score",
        "uncertainty_first_enabled",
        "uncertainty_first_process_order",
        "uncertainty_first_easy_score",
        "uncertainty_first_precision_score",
        "uncertainty_first_easy_signal_score",
        "uncertainty_first_low_stt_score",
        "uncertainty_first_low_lora_score",
        "uncertainty_first_long_text_ratio",
        "subtitle_target_line_count",
        "subtitle_target_line_count_auto_enabled",
        "llm_verifier_enabled",
        "llm_verifier_min_similarity",
        "llm_verifier_max_length_delta_ratio",
        "llm_verifier_max_chunks",
        "accuracy_decision_graph_enabled",
        "subtitle_accuracy_metrics_enabled",
        "subtitle_output_selector_enabled",
        "subtitle_context_consistency_enabled",
        "subtitle_context_repeat_window_sec",
        "subtitle_context_near_duplicate_ratio",
        "subtitle_context_cps_jump_ratio",
        "subtitle_context_score_penalty_weight",
        "subtitle_context_repair_enabled",
        "subtitle_context_repair_drop_repeats",
        "subtitle_context_repair_drop_empty_enabled",
        "subtitle_context_repair_drop_hallucinations_enabled",
        "subtitle_context_repair_overlap_pad_sec",
        "subtitle_context_repair_min_duration_sec",
        "subtitle_context_repair_cps_jumps_enabled",
        "subtitle_context_repair_cps_max_extend_sec",
        "subtitle_lora_style_consistency_enabled",
        "subtitle_lora_style_min_profile_score",
        "subtitle_lora_style_max_length_drift_ratio",
        "subtitle_lora_style_max_line_drift",
        "subtitle_lora_style_max_cps_ratio",
        "subtitle_lora_style_score_penalty_weight",
        "runtime_quality_self_review_enabled",
        "deep_quality_event_logging_enabled",
        "deep_quality_event_all_segments",
        "deep_quality_event_min_score",
        "deep_runtime_adaptation_enabled",
        "deep_runtime_adaptation_min_events",
        "deep_runtime_adaptation_lookback_events",
        "deep_runtime_adaptation_rate",
        "deep_cut_boundary_model_enabled",
        "deep_cut_boundary_keep_threshold",
        "deep_cut_boundary_verify_threshold",
    }
)

SEGMENT_LORA_KINDS = tuple(
    dict.fromkeys(
        (
            *INDEX_JSONL_SOURCE_KEYS,
            "best_settings",
            "learned_split_rules",
            "learned_line_break_rules",
            *INDEX_JSON_SOURCE_KEYS,
        )
    )
)


def _compact_len(text: Any) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def _clean_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = low
    return max(low, min(high, number))


def _clamp_int(value: Any, low: int, high: int) -> int:
    try:
        number = int(round(float(value)))
    except Exception:
        number = low
    return max(low, min(high, number))


def _setting_bool(settings: dict[str, Any] | None, key: str, default: bool = True) -> bool:
    value = dict(settings or {}).get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "사용 안함", "끔"}
    return bool(value)


def _flatten_summary(value: Any, *, limit: int = 8, max_chars: int = 80) -> list[str]:
    out: list[str] = []

    def add(label: str, item: Any) -> None:
        if len(out) >= limit:
            return
        text = _clean_text(item)
        if not text:
            return
        prefix = f"{label}=" if label else ""
        out.append(f"{prefix}{text}"[:max_chars])

    if isinstance(value, dict):
        for key, item in list(value.items())[:limit]:
            if isinstance(item, (dict, list, tuple, set)):
                nested = ", ".join(_flatten_summary(item, limit=3, max_chars=32))
                add(str(key), nested)
            else:
                add(str(key), item)
    elif isinstance(value, (list, tuple, set)):
        for item in list(value)[:limit]:
            add("", item)
    else:
        add("", value)
    return out[:limit]


def _segment_stt_candidate_texts(segment: dict[str, Any], *, limit: int = 8) -> list[str]:
    candidates = collect_stt_lattice_candidates(segment, include_current=False, limit=max(1, limit * 2))
    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = _clean_text(candidate.get("text"))
        if not text:
            continue
        key = re.sub(r"\s+", "", text).casefold()
        if key in seen:
            continue
        seen.add(key)
        label = str(candidate.get("source") or candidate.get("candidate_role") or "STT").strip()
        role = str(candidate.get("candidate_role") or "").strip()
        prefix = f"{label}/{role}" if role and role.casefold() not in label.casefold() else label
        out.append(f"{prefix}: {text}"[:120])
        if len(out) >= limit:
            break
    return out


def _segment_audio_summary(segment: dict[str, Any]) -> list[str]:
    summary: list[str] = []
    for key in (
        "audio_environment_summary",
        "audio_summary",
        "audio_profile",
        "_audio_profile",
        "audio_features",
        "_audio_features",
        "voice_activity_summary",
        "_voice_activity_summary",
    ):
        if key in segment and segment.get(key) not in (None, "", [], {}):
            summary.extend(_flatten_summary(segment.get(key), limit=5, max_chars=70))
    return summary[:8]


def _segment_cut_summary(segment: dict[str, Any]) -> list[str]:
    guard = dict(segment.get("_cut_boundary_guard_policy") or {})
    summary: list[str] = []
    if guard:
        for key in ("action", "confidence", "scene_start", "scene_end", "old_start", "old_end", "new_start", "new_end"):
            if guard.get(key) not in (None, ""):
                summary.append(f"{key}={guard.get(key)}")
    for key in (
        "cut_boundary_proximity_sec",
        "nearest_cut_boundary_sec",
        "nearest_confirmed_cut_sec",
        "nearest_provisional_cut_sec",
        "cut_boundary_role",
        "cut_boundary_source",
    ):
        if key in segment and segment.get(key) not in (None, ""):
            summary.append(f"{key}={segment.get(key)}")
    return summary[:10]


def _segment_topic_summary(segment: dict[str, Any]) -> list[str]:
    summary: list[str] = []
    for key in (
        "roughcut_topic",
        "roughcut_chapter",
        "roughcut_major_label",
        "roughcut_minor_label",
        "topic",
        "video_topic",
        "video_diagnostic_tags",
        "diagnostic_tags",
        "startup_diagnostics",
    ):
        if key in segment and segment.get(key) not in (None, "", [], {}):
            summary.extend(_flatten_summary(segment.get(key), limit=5, max_chars=70))
    return summary[:8]


def _segment_query_text(segment: dict[str, Any], settings: dict[str, Any] | None = None) -> str:
    if _setting_bool(settings, "lora_pattern_query_compact_enabled", True):
        features = segment_pattern_features(segment)
        return " ".join(
            [
                "subtitle_pattern",
                f"chars={features.get('char_count', 0)}",
                f"duration={features.get('duration_sec', 0.0)}",
                f"cps={features.get('cps', 0.0)}",
                f"lines={features.get('line_count', 1)}",
            ]
        ).strip()
    text = _clean_text(segment.get("text"))
    candidate_texts = _segment_stt_candidate_texts(segment)
    context_bits = []
    prev_context = _clean_text(segment.get("stt_ensemble_context_prev"))
    next_context = _clean_text(segment.get("stt_ensemble_context_next"))
    if prev_context:
        context_bits.append(f"prev {prev_context}")
    if next_context:
        context_bits.append(f"next {next_context}")
    if candidate_texts:
        context_bits.append("stt_candidates " + " / ".join(candidate_texts[:8]))
    audio_bits = _segment_audio_summary(segment)
    if audio_bits:
        context_bits.append("audio " + " / ".join(audio_bits))
    cut_bits = _segment_cut_summary(segment)
    if cut_bits:
        context_bits.append("cut_boundary " + " / ".join(cut_bits))
    topic_bits = _segment_topic_summary(segment)
    if topic_bits:
        context_bits.append("video_topic " + " / ".join(topic_bits))
    speaker = _clean_text(segment.get("speaker"))
    if speaker:
        context_bits.append(f"speaker {speaker}")
    return " ".join([text, *context_bits]).strip()


def _segment_context(segment: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    start = _clamp_float(segment.get("start", 0.0), 0.0, 999999.0)
    end = _clamp_float(segment.get("end", start), start, 999999.0)
    duration = max(0.0, end - start)
    text = _clean_text(segment.get("text"))
    chars = _compact_len(text)
    compact_query = _setting_bool(settings, "lora_pattern_query_compact_enabled", True)
    return {
        "subtitle_segment": {
            "duration_sec": round(duration, 3),
            "char_count": chars,
            "cps": round(chars / max(0.05, duration), 3) if chars and duration else 0.0,
            "speaker": "" if compact_query else str(segment.get("speaker") or ""),
        },
        "subtitle_neighbors": {
            "previous": "" if compact_query else _short(segment.get("stt_ensemble_context_prev"), 240),
            "next": "" if compact_query else _short(segment.get("stt_ensemble_context_next"), 240),
        },
        "stt_candidate_lattice": {
            "candidate_keys": list(STT_LATTICE_CANDIDATE_KEYS),
            "candidates": [] if compact_query else _segment_stt_candidate_texts(segment, limit=12),
            "candidate_count": len(list(collect_stt_lattice_candidates(segment, include_current=False, limit=24) or [])),
        },
        "audio_environment": _segment_audio_summary(segment),
        "cut_boundary": _segment_cut_summary(segment),
        "video_diagnostics": _segment_topic_summary(segment),
    }


def _generation_profile_from_pattern(
    *,
    query: str,
    pattern: dict[str, Any],
    applied_settings: dict[str, Any],
) -> dict[str, Any]:
    score = _clamp_float(pattern.get("score", 0.0), 0.0, 100.0)
    return {
        "schema": "ai_subtitle_studio.subtitle_lora_generation_profile.v1",
        "query": query[:240],
        "top_score": round(score, 4),
        "min_score": 0.0,
        "index_doc_count": 0,
        "quality_buckets": ["pattern"],
        "used_kinds": {"subtitle_pattern_index": int(pattern.get("count", 0) or 0)},
        "retrieved_settings": {},
        "applied_settings": dict(applied_settings or {}),
        "examples": [],
        "setting_sources": [
            {
                "kind": "subtitle_pattern_index",
                "settings": dict(pattern.get("settings") or {}),
                "score": round(score, 2),
                "matched_key": pattern.get("matched_key"),
            }
        ],
        "context_hits": [],
        "exclusions": [],
        "learned_rules": [],
        "prompt_hints": [],
        "style_hints": [],
        "other_hints": [],
        "pattern_match": {
            key: value
            for key, value in dict(pattern or {}).items()
            if key not in {"settings"}
        },
        "pattern_settings": dict(pattern.get("settings") or {}),
    }


def _media_path_for_segment(segment: dict[str, Any]) -> str:
    for key in ("media_path", "_media_path", "source_path", "_source_path", "clip_file", "_clip_file"):
        value = str(segment.get(key) or "").strip()
        if value:
            return value
    return ""


def _derive_gap_settings_from_truth(items: list[dict[str, Any]], *, min_score: float) -> dict[str, Any]:
    char_counts: list[int] = []
    durations: list[float] = []
    cps_values: list[float] = []
    line_counts: list[int] = []
    weighted_scores: list[float] = []

    for item in list(items or []):
        score = _clamp_float(item.get("retrieval_score", 0.0), 0.0, 100.0)
        if score < min_score:
            continue
        payload = dict(item.get("payload") or {})
        kind = str(item.get("kind") or "")
        text = ""
        if kind == "truth_table":
            text = _clean_text(payload.get("speech_training_text"))
            duration = _clamp_float(payload.get("duration_sec", 0.0), 0.0, 60.0)
            cps = _clamp_float(payload.get("cps", 0.0), 0.0, 60.0)
            if duration > 0.0:
                durations.append(duration)
            if cps > 0.0:
                cps_values.append(cps)
        elif kind in {"text_lora_dataset", "text_lora_corpus"}:
            text = _clean_text(payload.get("output") or payload.get("input"))
        else:
            continue

        if text:
            lines = [line for line in re.split(r"[\n\r]+", str(text)) if _clean_text(line)]
            if len(lines) > 1:
                line_counts.append(len(lines))
                char_counts.extend(_compact_len(line) for line in lines if _compact_len(line))
            else:
                char_counts.append(_compact_len(text))
            weighted_scores.append(score)

    derived: dict[str, Any] = {}
    if char_counts:
        target = _clamp_int(median(char_counts), 8, 32)
        derived["split_length_threshold"] = target
    if cps_values:
        derived["sub_max_cps"] = _clamp_int(max(cps_values), 10, 18)
    if durations:
        med_duration = _clamp_float(median(durations), 0.1, 8.0)
        derived["sub_min_duration"] = _clamp_float(min(durations), 0.1, 1.2)
        derived["sub_max_duration"] = _clamp_float(max(med_duration * 1.8, max(durations)), 2.0, 8.0)
    if line_counts and median(line_counts) >= 2 and "sub_gap_break_sec" not in derived:
        derived["sub_gap_break_sec"] = 1.0
    if line_counts:
        derived["subtitle_target_line_count"] = _clamp_int(median(line_counts), 1, 3)
    if weighted_scores:
        derived["_truth_score_index"] = round(max(weighted_scores), 4)
    return derived


def _filter_segment_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in dict(settings or {}).items()
        if key in SEGMENT_LORA_SETTING_KEYS and value not in (None, "")
    }


def _short(text: Any, limit: int = 72) -> str:
    return _clean_text(text)[: max(0, int(limit or 0))]


def _append_unique(out: list[dict[str, Any]], item: dict[str, Any], seen: set[tuple[Any, ...]], key: tuple[Any, ...], limit: int) -> None:
    if len(out) >= limit or key in seen:
        return
    seen.add(key)
    out.append(item)


def _generation_profile_from_items(
    *,
    query: str,
    result: dict[str, Any],
    items: list[dict[str, Any]],
    retrieved_settings: dict[str, Any],
    applied_settings: dict[str, Any],
    min_score: float,
) -> dict[str, Any]:
    examples: list[dict[str, Any]] = []
    setting_sources: list[dict[str, Any]] = []
    context_hits: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    learned_rules: list[dict[str, Any]] = []
    prompt_hints: list[dict[str, Any]] = []
    style_hints: list[dict[str, Any]] = []
    other_hints: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    top_score = 0.0
    used_kinds: dict[str, int] = {}

    for item in list(items or []):
        kind = str(item.get("kind") or "")
        score = _clamp_float(item.get("retrieval_score", 0.0), 0.0, 100.0)
        if score < min_score:
            continue
        top_score = max(top_score, score)
        used_kinds[kind] = used_kinds.get(kind, 0) + 1
        payload = dict(item.get("payload") or {})
        if kind == "truth_table":
            text = _short(payload.get("speech_training_text"), 96)
            style_profile = payload.get("style_profile")
            style_profile = style_profile if isinstance(style_profile, dict) else {}
            if text:
                _append_unique(
                    examples,
                    {
                        "kind": kind,
                        "text": text,
                        "line_break_pattern": _short(payload.get("line_break_pattern"), 24),
                        "punctuation_pattern": _short(payload.get("punctuation_pattern"), 12),
                        "duration_sec": payload.get("duration_sec"),
                        "cps": payload.get("cps"),
                        "style_profile": style_profile,
                        "score": round(score, 2),
                    },
                    seen,
                    ("truth", text),
                    6,
                )
            if style_profile:
                _append_unique(
                    style_hints,
                    {"kind": kind, "style_profile": style_profile, "score": round(score, 2)},
                    seen,
                    ("style", kind, text, repr(sorted(style_profile.keys()))),
                    6,
                )
        elif kind in {"text_lora_dataset", "text_lora_corpus"}:
            source = _short(payload.get("input"), 96)
            target = _short(payload.get("output"), 96)
            meta = payload.get("meta")
            meta = meta if isinstance(meta, dict) else {}
            style_profile = payload.get("style_profile") if isinstance(payload.get("style_profile"), dict) else meta.get("style_profile")
            style_profile = style_profile if isinstance(style_profile, dict) else {}
            if source or target:
                _append_unique(
                    examples,
                    {"kind": kind, "input": source, "output": target, "style_profile": style_profile, "score": round(score, 2)},
                    seen,
                    ("text", source, target),
                    6,
                )
            if style_profile:
                _append_unique(
                    style_hints,
                    {"kind": kind, "style_profile": style_profile, "score": round(score, 2)},
                    seen,
                    ("style", kind, source, target, repr(sorted(style_profile.keys()))),
                    6,
                )
        elif kind in {"setting_trials", "best_settings", "audio_preset_lora"}:
            config = dict(payload.get("config") or payload.get("audio_tune_settings") or payload.get("settings") or {})
            safe_config = {
                key: value
                for key, value in config.items()
                if key in RUNTIME_SETTING_KEYS and value not in (None, "")
            }
            if safe_config:
                _append_unique(
                    setting_sources,
                    {
                        "kind": kind,
                        "settings": safe_config,
                        "score": round(score, 2),
                        "score_index": item.get("score_index"),
                    },
                    seen,
                    ("settings", kind, tuple(sorted((str(k), str(v)) for k, v in safe_config.items()))),
                    5,
                )
        elif kind == "deep_policy_events":
            config = dict(payload.get("applied_settings") or {})
            safe_config = {
                key: value
                for key, value in config.items()
                if key in RUNTIME_SETTING_KEYS and value not in (None, "")
            }
            event_type = _short(payload.get("event_type"), 48)
            event_text = _short(payload.get("text"), 120)
            if safe_config:
                _append_unique(
                    setting_sources,
                    {
                        "kind": kind,
                        "settings": safe_config,
                        "score": round(score, 2),
                        "score_index": item.get("score_index"),
                    },
                    seen,
                    ("deep_settings", event_type, tuple(sorted((str(k), str(v)) for k, v in safe_config.items()))),
                    5,
                )
            if event_type or event_text:
                _append_unique(
                    other_hints,
                    {"kind": kind, "text": f"{event_type}: {event_text}".strip(": "), "score": round(score, 2)},
                    seen,
                    ("deep_event", event_type, event_text),
                    6,
                )
        elif kind == "prompt_trials":
            prompt_text = _short(payload.get("prompt_text"), 160)
            prompt_id = _short(payload.get("prompt_template_id"), 64)
            if prompt_text or prompt_id:
                _append_unique(
                    prompt_hints,
                    {"prompt_template_id": prompt_id, "prompt_text": prompt_text, "score": round(score, 2)},
                    seen,
                    ("prompt", prompt_id, prompt_text),
                    4,
                )
        elif kind == "multimodal_lora_context":
            summary = dict(payload.get("classification_summary") or {})
            style_profile = payload.get("subtitle_style_profile")
            style_profile = style_profile if isinstance(style_profile, dict) else {}
            if not summary:
                classification = dict(payload.get("context_classification") or {})
                microphone = dict(classification.get("microphone_environment") or {})
                summary = {
                    "scene": dict(classification.get("scene_environment") or {}).get("label"),
                    "topic": dict(classification.get("topic") or {}).get("primary"),
                    "mic_type": microphone.get("mic_type"),
                    "noise_level": microphone.get("noise_level"),
                    "noise_sources": list(microphone.get("noise_sources") or []),
                    "training_focus": list(classification.get("training_focus") or []),
                }
            if summary:
                _append_unique(
                    context_hits,
                    {"summary": summary, "score": round(score, 2)},
                    seen,
                    ("context", tuple(sorted((str(k), str(v)) for k, v in summary.items()))),
                    4,
                )
            if style_profile:
                _append_unique(
                    style_hints,
                    {"kind": kind, "style_profile": style_profile, "score": round(score, 2)},
                    seen,
                    ("style", kind, repr(sorted(style_profile.keys()))),
                    6,
                )
        elif kind == "excluded_parentheticals":
            text = _short(payload.get("excluded_text") or payload.get("text"), 64)
            if text:
                _append_unique(
                    exclusions,
                    {"text": text, "score": round(score, 2)},
                    seen,
                    ("exclude", text),
                    6,
                )
        elif kind in {"learned_split_rules", "learned_line_break_rules"}:
            rule = _short(payload.get("rule_text"), 48)
            if rule:
                _append_unique(
                    learned_rules,
                    {
                        "kind": kind,
                        "rule_text": rule,
                        "confidence": payload.get("confidence"),
                        "score": round(score, 2),
                    },
                    seen,
                    ("rule", kind, rule),
                    8,
                )
        else:
            preview = _short(item.get("text_preview") or payload, 160)
            if preview:
                _append_unique(
                    other_hints,
                    {"kind": kind, "text": preview, "score": round(score, 2)},
                    seen,
                    ("other", kind, preview),
                    6,
                )

    return {
        "schema": "ai_subtitle_studio.subtitle_lora_generation_profile.v1",
        "query": query[:240],
        "top_score": round(top_score, 4),
        "min_score": round(float(min_score or 0.0), 4),
        "index_doc_count": int(result.get("index_doc_count", 0) or 0),
        "quality_buckets": list(result.get("quality_buckets") or []),
        "used_kinds": used_kinds,
        "retrieved_settings": {
            key: value
            for key, value in dict(retrieved_settings or {}).items()
            if key in RUNTIME_SETTING_KEYS and value not in (None, "")
        },
        "applied_settings": {
            key: value
            for key, value in dict(applied_settings or {}).items()
            if key in SEGMENT_LORA_SETTING_KEYS and value not in (None, "")
        },
        "examples": examples,
        "setting_sources": setting_sources,
        "context_hits": context_hits,
        "exclusions": exclusions,
        "learned_rules": learned_rules,
        "prompt_hints": prompt_hints,
        "style_hints": style_hints,
        "other_hints": other_hints,
    }


def lora_settings_for_subtitle_segment(
    segment: dict[str, Any],
    base_settings: dict[str, Any] | None,
    *,
    rules: dict[str, Any] | None = None,
    store_dir: str | None = None,
) -> dict[str, Any]:
    settings = dict(base_settings or {})
    if not runtime_lora_enabled(settings):
        return {}

    min_score = _clamp_float(settings.get("segment_lora_min_score", 28.0), 0.0, 100.0)
    query = _segment_query_text(segment, settings)
    pattern = match_subtitle_pattern(segment, settings, store_dir=store_dir)
    pattern_settings = _filter_segment_settings(dict(pattern.get("settings") or {}))
    pattern_score = _clamp_float(pattern.get("score", 0.0), 0.0, 100.0)
    skip_retrieval = bool(
        pattern_settings
        and _setting_bool(settings, "lora_pattern_first_enabled", True)
        and pattern_score >= _clamp_float(settings.get("lora_pattern_skip_text_retrieval_score", 78.0), 0.0, 100.0)
    )

    result: dict[str, Any] = {"index_doc_count": 0, "quality_buckets": [], "items": []}
    items: list[dict[str, Any]] = []
    if query and not skip_retrieval:
        try:
            result = retrieve_lora_context(
                query,
                media_path=_media_path_for_segment(segment),
                media_id=str(segment.get("media_id") or segment.get("_media_id") or ""),
                settings=settings,
                context=_segment_context(segment, settings),
                store_dir=store_dir,
                limit=_setting_int(settings, "segment_lora_retrieval_limit", 24),
                per_kind=_setting_int(settings, "segment_lora_retrieval_per_kind", 4),
                kinds=SEGMENT_LORA_KINDS,
                rebuild_if_stale=False,
            )
        except Exception:
            result = {"index_doc_count": 0, "quality_buckets": [], "items": []}
        items = list(result.get("items") or [])

    overrides = dict(pattern_settings)
    overrides.update(runtime_settings_from_retrieved_items(items, min_score=min_score))
    derived = _derive_gap_settings_from_truth(items, min_score=min_score)
    truth_score = float(derived.pop("_truth_score_index", 0.0) or 0.0)
    for key, value in derived.items():
        overrides.setdefault(key, value)

    filtered = _filter_segment_settings(overrides)
    top_score = max([pattern_score, truth_score, *[float(item.get("retrieval_score", 0.0) or 0.0) for item in items]], default=0.0)
    if items:
        profile = _generation_profile_from_items(
            query=query,
            result=result,
            items=items,
            retrieved_settings=overrides,
            applied_settings=filtered,
            min_score=min_score,
        )
        if pattern:
            profile["pattern_match"] = {
                key: value
                for key, value in dict(pattern or {}).items()
                if key != "settings"
            }
            profile["pattern_settings"] = dict(pattern_settings)
            profile.setdefault("used_kinds", {})["subtitle_pattern_index"] = int(pattern.get("count", 0) or 0)
    else:
        profile = _generation_profile_from_pattern(
            query=query,
            pattern=pattern,
            applied_settings=filtered,
        ) if pattern_settings else {
            "schema": "ai_subtitle_studio.subtitle_lora_generation_profile.v1",
            "query": query[:240],
            "top_score": 0.0,
            "used_kinds": {},
            "applied_settings": {},
        }
    policy_settings, policy_meta = predict_segment_settings(segment, settings, profile)
    for key, value in policy_settings.items():
        if key in SEGMENT_LORA_SETTING_KEYS and value not in (None, ""):
            filtered.setdefault(key, value)
            profile.setdefault("deep_policy_settings", {})[key] = value
    if policy_meta:
        profile["_deep_setting_policy"] = policy_meta
        profile["applied_settings"] = {
            key: value
            for key, value in {**dict(profile.get("applied_settings") or {}), **filtered}.items()
            if key in SEGMENT_LORA_SETTING_KEYS and value not in (None, "")
        }
    if not filtered and not profile.get("used_kinds"):
        return {}

    filtered["_lora_segment_score"] = round(top_score, 4)
    filtered["_lora_segment_doc_count"] = int(result.get("index_doc_count", 0) or 0)
    filtered["_lora_segment_query"] = query[:240]
    filtered["_lora_generation_profile"] = profile
    return filtered


def merge_segment_lora_settings(
    segment: dict[str, Any],
    base_settings: dict[str, Any] | None,
    *,
    rules: dict[str, Any] | None = None,
    store_dir: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base = dict(base_settings or {})
    override = lora_settings_for_subtitle_segment(segment, base, rules=rules, store_dir=store_dir)
    if not override:
        return base, {}
    runtime = dict(base)
    runtime.update({key: value for key, value in override.items() if not key.startswith("_lora_")})
    if "_lora_generation_profile" in override:
        runtime["_lora_generation_profile"] = override["_lora_generation_profile"]
    return runtime, override


def attach_segment_lora_settings(segment: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    row = dict(segment)
    filtered = _filter_segment_settings(override or {})
    profile = dict((override or {}).get("_lora_generation_profile") or {})
    if not filtered and not profile:
        return row
    if filtered:
        row["_lora_segment_settings"] = filtered
        row["_lora_gap_settings"] = {key: value for key, value in filtered.items() if key in SEGMENT_LORA_GAP_SETTING_KEYS}
    if profile:
        row["_lora_generation_profile"] = profile
    for meta_key in ("_lora_segment_score", "_lora_segment_doc_count", "_lora_segment_query"):
        if meta_key in (override or {}):
            row[meta_key] = (override or {})[meta_key]
    return row


__all__ = [
    "SEGMENT_LORA_GAP_SETTING_KEYS",
    "SEGMENT_LORA_SETTING_KEYS",
    "attach_segment_lora_settings",
    "lora_settings_for_subtitle_segment",
    "merge_segment_lora_settings",
]
