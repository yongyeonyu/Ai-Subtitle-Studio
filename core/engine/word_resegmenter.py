# Version: 03.01.21
# Phase: PHASE2
from __future__ import annotations

import re
from typing import Any

from core.subtitle_quality.models import attach_asr_metadata
from core.subtitle_quality.vad_alignment_checker import normalize_vad_segments

try:
    from core.native_cut_boundary import word_split_groups as _native_word_split_groups
except Exception:  # pragma: no cover - native extension is optional.
    _native_word_split_groups = None


_PUNCT_ENDINGS = tuple(",?!;:~…")
_PRESERVED_SEGMENT_KEYS = (
    "_lora_segment_settings",
    "_lora_gap_settings",
    "_lora_generation_profile",
    "_lora_segment_score",
    "_lora_segment_doc_count",
    "_lora_segment_query",
    "_lora_style_merge_policy",
    "_deep_rerank_policy",
    "_deep_timing_policy",
    "_editor_truth_runtime_policy",
    "_stt_lattice_policy",
    "_llm_gate_policy",
    "_llm_minimize_policy",
    "_llm_candidate_policy",
    "_llm_verifier_policy",
    "_llm_rollback_policy",
    "_llm_macro_chunk_policy",
    "_accuracy_decision_graph",
    "_cut_boundary_guard_policy",
    "_uncertainty_policy",
    "_uncertainty_bucket",
    "_uncertainty_risk_score",
    "_codex_native_fast_path_policy",
    "_stt_original_candidate_start",
    "_stt_original_candidate_end",
    "_stt_original_candidate_start_frame",
    "_stt_original_candidate_end_frame",
    "_stt_candidate_word_timing_anchor_policy",
    "_stt_word_match_timing_policy",
    "_llm_stt_text_guard_policy",
    "_stt_no_llm_raw_candidate_policy",
    "_stt_no_llm_raw_text",
    "original_start",
    "original_end",
    "speaker_list",
    "speaker2",
    "_stt_speaker_marker_preserved",
    "stt_candidates",
    "stt_ensemble_source",
    "stt_selected_source",
    "score",
    "stt_score",
    "score_color",
    "stt_score_color",
    "stt_score_label",
    "stt_score_flags",
    "stt_score_components",
)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _char_count(text: str) -> int:
    return len(str(text or "").replace(" ", "").replace("\n", ""))


def _segment_setting(segment: dict[str, Any], key: str, default: Any) -> Any:
    for payload_key in ("_lora_gap_settings", "_lora_segment_settings"):
        payload = segment.get(payload_key)
        if isinstance(payload, dict) and payload.get(key) not in (None, ""):
            return payload.get(key)
    return default


def _segment_int(segment: dict[str, Any], key: str, default: int, *, low: int = 1) -> int:
    try:
        value = int(round(float(_segment_setting(segment, key, default))))
    except Exception:
        value = int(default)
    return max(low, value)


def _segment_float(segment: dict[str, Any], key: str, default: float, *, low: float = 0.0) -> float:
    try:
        value = float(_segment_setting(segment, key, default))
    except Exception:
        value = float(default)
    return max(low, value)


def _lora_score(segment: dict[str, Any]) -> float:
    scores: list[float] = []
    for key in ("_lora_segment_score", "lora_score"):
        value = segment.get(key)
        if value not in (None, ""):
            scores.append(_as_float(value))
    profile = segment.get("_lora_generation_profile")
    if isinstance(profile, dict):
        scores.append(_as_float(profile.get("top_score")))
        pattern = profile.get("pattern_match")
        if isinstance(pattern, dict):
            scores.append(_as_float(pattern.get("score")))
    return max(scores or [0.0])


def _lora_continuity_enabled(segment: dict[str, Any]) -> bool:
    for payload_key in ("_lora_gap_settings", "_lora_segment_settings"):
        payload = segment.get(payload_key)
        if not isinstance(payload, dict):
            continue
        if payload.get("subtitle_lora_split_policy_enabled") is False:
            return False
        if any(
            payload.get(key) not in (None, "")
            for key in (
                "split_length_threshold",
                "sub_gap_break_sec",
                "word_timing_gap_break_sec",
                "continuous_threshold",
                "sub_min_duration",
            )
        ):
            return True
    return _lora_score(segment) >= 70.0


def _clean_word(value: str) -> str:
    return re.sub(r"[^\w가-힣]", "", str(value or ""))


def _word_text(word: dict[str, Any]) -> str:
    return str(word.get("word", "") or "").strip()


def _segment_words(segment: dict[str, Any]) -> list[dict[str, Any]]:
    words = [dict(word) for word in (segment.get("words") or []) if _word_text(word)]
    if words:
        return sorted(words, key=lambda item: _as_float(item.get("start")))

    text = str(segment.get("text", "") or "").strip()
    tokens = [token for token in text.split() if token]
    if not tokens:
        return []
    start = _as_float(segment.get("start"))
    end = max(start + 0.1, _as_float(segment.get("end"), start + 0.1))
    step = max(0.05, (end - start) / max(1, len(tokens)))
    speaker = segment.get("speaker")
    return [
        {
            "word": token,
            "start": round(start + index * step, 3),
            "end": round(start + (index + 1) * step, 3),
            "speaker": speaker,
        }
        for index, token in enumerate(tokens)
    ]


def _is_rule_break(word: str, next_word: str, rules: dict[str, Any] | None) -> bool:
    rules = rules or {}
    current = _clean_word(word)
    nxt = _clean_word(next_word)
    end_words = [str(item) for item in rules.get("end_words", []) if item]
    start_words = [str(item) for item in rules.get("start_words", []) if item]
    if end_words and any(current.endswith(item) for item in end_words):
        return True
    if start_words and any(nxt.startswith(item) for item in start_words):
        return True
    return False


def _is_punctuation_break(word: str) -> bool:
    value = str(word or "").strip()
    return bool(value) and value.endswith(_PUNCT_ENDINGS)


def _build_segment(
    words: list[dict[str, Any]],
    fallback_speaker: str | None,
    source_metadata: dict[str, Any] | None = None,
    source_segment: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not words:
        return None
    text = " ".join(_word_text(word) for word in words).strip()
    if not text:
        return None
    start = _as_float(words[0].get("start"))
    end = max(start + 0.05, _as_float(words[-1].get("end"), start + 0.05))
    preserved = {
        key: source_segment[key]
        for key in _PRESERVED_SEGMENT_KEYS
        if isinstance(source_segment, dict) and key in source_segment
    }
    built = {
        **preserved,
        "start": round(start, 3),
        "end": round(end, 3),
        "text": text,
        "speaker": words[0].get("speaker") or fallback_speaker,
        "words": words,
    }
    if source_metadata:
        built["asr_metadata"] = dict(source_metadata)
    return attach_asr_metadata(built, backend=(built.get("asr_metadata") or {}).get("backend"))


def _should_flush(
    buf: list[dict[str, Any]],
    next_word: dict[str, Any] | None,
    *,
    max_chars: int,
    max_duration: float,
    max_cps: float,
    min_duration: float,
    gap_break_sec: float,
    word_gap_break_sec: float,
    vad_segments: list[dict[str, Any]] | None,
    rules: dict[str, Any] | None,
    lora_continuity: bool = False,
) -> bool:
    if not buf:
        return False
    if next_word is None:
        return True

    start = _as_float(buf[0].get("start"))
    end = _as_float(buf[-1].get("end"), start)
    duration = max(0.05, end - start)

    text = " ".join(_word_text(word) for word in buf)
    chars = _char_count(text)
    current_word = _word_text(buf[-1])
    following_word = _word_text(next_word)
    gap = _as_float(next_word.get("start"), end) - end
    cps = chars / duration if duration > 0 else chars
    natural = _is_punctuation_break(current_word) or _is_rule_break(current_word, following_word, rules)

    vad_break = _is_vad_boundary_between_words(buf[-1], next_word, vad_segments)
    word_gap_break = gap >= word_gap_break_sec

    if duration < min_duration:
        return False

    if lora_continuity:
        if gap >= gap_break_sec:
            return True
    elif (vad_break or word_gap_break) and duration >= 0.08:
        return True

    if gap >= gap_break_sec:
        return True
    if chars >= max_chars and natural:
        return True
    if duration >= max_duration and (natural or gap >= min(gap_break_sec * 0.5, 1.0) or chars >= int(max_chars * 0.5)):
        return True
    if cps > max_cps and chars >= max_chars and natural:
        return True
    if chars >= int(max_chars * 1.5):
        return True
    return False


def _word_center(word: dict[str, Any]) -> float:
    start = _as_float(word.get("start"))
    end = _as_float(word.get("end"), start)
    return (start + max(start, end)) / 2.0


def _vad_index_for_word(word: dict[str, Any], vad_segments: list[dict[str, Any]] | None) -> int | None:
    if not vad_segments:
        return None
    center = _word_center(word)
    start = _as_float(word.get("start"), center)
    end = _as_float(word.get("end"), center)
    best_idx = None
    best_overlap = 0.0
    for idx, vad in enumerate(vad_segments):
        vad_start = _as_float(vad.get("start"))
        vad_end = _as_float(vad.get("end"), vad_start)
        overlap = max(0.0, min(end, vad_end) - max(start, vad_start))
        if vad_start <= center <= vad_end:
            return idx
        if overlap > best_overlap:
            best_overlap = overlap
            best_idx = idx
    return best_idx if best_overlap > 0.0 else None


def _is_vad_boundary_between_words(
    current_word: dict[str, Any],
    next_word: dict[str, Any],
    vad_segments: list[dict[str, Any]] | None,
) -> bool:
    if not vad_segments:
        return False
    left_idx = _vad_index_for_word(current_word, vad_segments)
    right_idx = _vad_index_for_word(next_word, vad_segments)
    if left_idx is None or right_idx is None:
        return False
    return left_idx != right_idx


def _native_word_groups(
    words: list[dict[str, Any]],
    *,
    max_chars: int,
    max_duration: float,
    max_cps: float,
    min_duration: float,
    gap_break_sec: float,
    word_gap_break_sec: float,
    vad_segments: list[dict[str, Any]] | None,
    rules: dict[str, Any] | None,
) -> list[tuple[int, int]] | None:
    if not callable(_native_word_split_groups) or len(words) < 2:
        return None
    starts: list[float] = []
    ends: list[float] = []
    char_counts: list[int] = []
    natural_breaks: list[int] = []
    vad_indexes: list[int] = []
    for index, word in enumerate(words):
        start = _as_float(word.get("start"))
        end = max(start + 0.001, _as_float(word.get("end"), start + 0.001))
        starts.append(start)
        ends.append(end)
        char_counts.append(_char_count(_word_text(word)))
        if index + 1 < len(words):
            current_word = _word_text(word)
            next_word = _word_text(words[index + 1])
            natural_breaks.append(
                1
                if (_is_punctuation_break(current_word) or _is_rule_break(current_word, next_word, rules))
                else 0
            )
        else:
            natural_breaks.append(0)
        vad_idx = _vad_index_for_word(word, vad_segments)
        vad_indexes.append(int(vad_idx) if vad_idx is not None else -1)
    groups = _native_word_split_groups(
        starts,
        ends,
        char_counts,
        natural_breaks,
        vad_indexes,
        max_chars=max_chars,
        max_duration=max_duration,
        max_cps=max_cps,
        min_duration=min_duration,
        gap_break_sec=gap_break_sec,
        word_gap_break_sec=word_gap_break_sec,
    )
    if not groups:
        return None
    cleaned: list[tuple[int, int]] = []
    cursor = 0
    word_count = len(words)
    for begin, end in groups:
        begin = int(begin)
        end = int(end)
        if begin != cursor or end <= begin or end > word_count:
            return None
        cleaned.append((begin, end))
        cursor = end
    return cleaned if cursor == word_count else None


def resegment_by_word_timestamps(
    segments: list[dict[str, Any]],
    *,
    max_chars: int,
    max_duration: float,
    max_cps: float,
    min_duration: float,
    gap_break_sec: float,
    word_gap_break_sec: float | None = None,
    vad_segments: list[dict[str, Any]] | None = None,
    rules: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Re-split subtitles using word timestamps after STT/LLM cleanup."""
    if not segments:
        return []

    max_chars = max(2, int(max_chars or 10))
    max_duration = max(0.5, float(max_duration or 6.0))
    max_cps = max(3.0, float(max_cps or 12.0))
    min_duration = max(0.0, float(min_duration or 0.0))
    gap_break_sec = max(0.05, float(gap_break_sec or 1.5))
    word_gap_break_sec = max(0.08, float(word_gap_break_sec if word_gap_break_sec is not None else 0.65))
    vad_segments = normalize_vad_segments(vad_segments or [])

    result: list[dict[str, Any]] = []
    for segment in sorted((dict(item) for item in segments), key=lambda item: _as_float(item.get("start"))):
        words = _segment_words(segment)
        if not words:
            continue
        segment_max_chars = _segment_int(segment, "split_length_threshold", max_chars, low=2)
        segment_max_duration = _segment_float(segment, "sub_max_duration", max_duration, low=0.5)
        segment_max_cps = _segment_float(segment, "sub_max_cps", max_cps, low=3.0)
        segment_min_duration = _segment_float(segment, "sub_min_duration", min_duration, low=0.0)
        segment_gap_break_sec = _segment_float(segment, "sub_gap_break_sec", gap_break_sec, low=0.05)
        segment_word_gap_break_sec = _segment_float(segment, "word_timing_gap_break_sec", word_gap_break_sec, low=0.08)
        lora_continuity = _lora_continuity_enabled(segment)
        fallback_speaker = segment.get("speaker")
        source_metadata = dict(segment.get("asr_metadata") or {})
        native_groups = None if lora_continuity else _native_word_groups(
            words,
            max_chars=segment_max_chars,
            max_duration=segment_max_duration,
            max_cps=segment_max_cps,
            min_duration=segment_min_duration,
            gap_break_sec=segment_gap_break_sec,
            word_gap_break_sec=segment_word_gap_break_sec,
            vad_segments=vad_segments,
            rules=rules,
        )
        if native_groups is not None:
            for begin, end in native_groups:
                built = _build_segment(words[begin:end], fallback_speaker, source_metadata, segment)
                if built is not None:
                    result.append(built)
            continue
        buf: list[dict[str, Any]] = []
        for index, word in enumerate(words):
            buf.append(word)
            next_word = words[index + 1] if index + 1 < len(words) else None
            if not _should_flush(
                buf,
                next_word,
                max_chars=segment_max_chars,
                max_duration=segment_max_duration,
                max_cps=segment_max_cps,
                min_duration=segment_min_duration,
                gap_break_sec=segment_gap_break_sec,
                word_gap_break_sec=segment_word_gap_break_sec,
                vad_segments=vad_segments,
                rules=rules,
                lora_continuity=lora_continuity,
            ):
                continue
            built = _build_segment(buf, fallback_speaker, source_metadata, segment)
            if built is not None:
                result.append(built)
            buf = []

        if buf:
            built = _build_segment(buf, fallback_speaker, source_metadata, segment)
            if built is not None:
                result.append(built)

    return result
