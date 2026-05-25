# Version: 03.14.29
# Phase: PHASE2
"""Final subtitle sequence cleanup and STT anchor integrity guards.

Behavior-preserving split from subtitle_engine.py.
"""

from __future__ import annotations

import difflib
import re
import sys

from core.engine.subtitle_accuracy_pipeline import describe_llm_verifier_decision, verify_llm_chunks_for_subtitle
from core.engine.subtitle_lora_packaging import (
    _apply_lora_style_micro_merge,
    _bool_setting,
    _clear_split_timing_projection_fields,
    _expand_non_speaker_multiline_segments,
    _is_speaker_split_multiline_segment,
    _subtitle_text_lines,
)
from core.engine.subtitle_settings import (
    _get_user_settings,
    _setting_float,
    _setting_int,
    get_local_dataset_corrections,
)
from core.engine.subtitle_stt_candidate_helpers import (
    _stt_candidate_compact_text,
    _stt_candidate_score100,
    _stt_candidate_similarity,
    _stt_decision_timing_span,
    _stt_selection_metadata,
)
from core.engine.subtitle_text_policy import enforce_final_subtitle_text_policy as _enforce_final_subtitle_text_policy
from core.engine.subtitle_timing import adjust_timing, align_stt_candidates_to_subtitle_segments, apply_final_gap_settings
from core.runtime.logger import get_logger

_S = _get_user_settings()
_MAX_CPS = _setting_int(_S, "sub_max_cps", 12)


def _profile_from_settings(settings: dict | None) -> dict:
    return dict(settings or {})


def _engine_attr(name: str, fallback):
    owner = sys.modules.get("core.engine.subtitle_engine")
    return getattr(owner, name, fallback)


_get_local_dataset_corrections_fallback = get_local_dataset_corrections


def get_local_dataset_corrections(*args, **kwargs):
    return _engine_attr("get_local_dataset_corrections", _get_local_dataset_corrections_fallback)(*args, **kwargs)


_get_logger_fallback = get_logger


def get_logger(*args, **kwargs):
    return _engine_attr("get_logger", _get_logger_fallback)(*args, **kwargs)


_FINAL_FILLER_FRAGMENTS = {
    "네", "네네", "네네네",
    "예", "예예", "예예예",
    "응", "응응",
    "음", "음음", "으음",
    "어", "어어",
    "아", "아아",
    "오",
    "와",
    "흠",
    "자",
    "뭐",
    "그",
    "저",
}

_FINAL_CLOSING_PHRASES = {
    "감사합니다",
    "고맙습니다",
    "이상입니다",
    "여기까지입니다",
    "마치겠습니다",
}

_FINAL_DUPLICATE_BRIDGE_TOKENS = {
    "그래서",
    "그래서요",
    "그리고",
    "그리고요",
    "근데",
    "그런데",
    "그러니까",
    "그러면",
    "그럼",
    "여기까지",
    "여기까지고",
    "지금까지",
    "이제",
    "자",
    "또",
    "다음으로",
    "그다음",
    "그다음에",
    "그 다음에",
}

_FINAL_CONTINUATION_TAIL_RE = re.compile(
    r"(고|서|데|는데|은데|인데|니까|으니까|지만|면서|으면서|려고|으려고|라서|이라서|해서|이며|이고|하고|며|다가|거나|든지|더니|더라도|도록|듯이)$"
)
_FINAL_TINY_FRAGMENT_MAX_SEC = 0.18
_FINAL_TINY_FRAGMENT_MAX_CHARS = 2
_FINAL_TINY_FRAGMENT_MAX_GAP_SEC = 0.08

def _sequence_text_for_integrity(segments: list[dict] | None) -> str:
    return " ".join(
        " ".join(_subtitle_text_lines(str(seg.get("text", "") or "")))
        for seg in list(segments or [])
        if isinstance(seg, dict) and str(seg.get("text", "") or "").strip() and not seg.get("is_gap")
    ).strip()


def _segment_scope_key_local(segment: dict | None) -> tuple[str, str] | None:
    if not isinstance(segment, dict):
        return None
    clip_idx = segment.get("_clip_idx")
    if clip_idx is not None:
        return ("clip_idx", str(clip_idx))
    clip_file = segment.get("_clip_file") or segment.get("clip_file")
    if clip_file:
        return ("clip_file", str(clip_file))
    return None


def _same_segment_scope_local(left: dict | None, right: dict | None) -> bool:
    if not left or not right:
        return False
    left_key = _segment_scope_key_local(left)
    right_key = _segment_scope_key_local(right)
    if left_key is None and right_key is None:
        return True
    return left_key == right_key


def _speaker_signature(row: dict | None) -> tuple[str, ...]:
    if not isinstance(row, dict):
        return ()
    speakers = [
        str(item).strip()
        for item in list(row.get("speaker_list") or [])
        if str(item).strip()
    ]
    if not speakers:
        speaker = str(row.get("speaker") or row.get("spk") or "").strip()
        if speaker:
            speakers = [speaker]
    return tuple(sorted(set(speakers)))


def _compatible_speaker_signature(left: dict | None, right: dict | None) -> bool:
    left_sig = _speaker_signature(left)
    right_sig = _speaker_signature(right)
    if left_sig and right_sig:
        return left_sig == right_sig
    return True


def _compact_subtitle_text(text: str) -> str:
    return re.sub(r"\s+", "", " ".join(_subtitle_text_lines(text)))


def _subtitle_tokens(text: str) -> list[str]:
    return [token for token in " ".join(_subtitle_text_lines(text)).split() if token]


def _token_compact_len(tokens: list[str]) -> int:
    return len(re.sub(r"\s+", "", "".join(tokens)))


def _overlap_token_count(left_tokens: list[str], right_tokens: list[str], *, mode: str) -> int:
    max_size = min(len(left_tokens), len(right_tokens), 8)
    for size in range(max_size, 0, -1):
        if mode == "prefix":
            matched = left_tokens[-size:] == right_tokens[:size]
        else:
            matched = right_tokens[-size:] == left_tokens[:size]
        if matched:
            return size
    return 0


def _normalize_short_closing_phrase(text: str) -> str:
    tokens = _subtitle_tokens(text)
    if len(tokens) != 2:
        return " ".join(tokens).strip()
    if tokens[0] in _FINAL_CLOSING_PHRASES and tokens[1] in _FINAL_FILLER_FRAGMENTS:
        return tokens[0]
    if tokens[1] in _FINAL_CLOSING_PHRASES and tokens[0] in _FINAL_FILLER_FRAGMENTS:
        return tokens[1]
    return " ".join(tokens).strip()


def _is_low_value_duplicate_bridge_tokens(tokens: list[str]) -> bool:
    if not tokens:
        return False
    for token in tokens:
        if token in _FINAL_FILLER_FRAGMENTS:
            continue
        if token in _FINAL_DUPLICATE_BRIDGE_TOKENS:
            continue
        if _FINAL_CONTINUATION_TAIL_RE.search(token):
            continue
        return False
    return True


def _merge_adjacent_rows(left: dict, right: dict, *, stage: str, reason: str) -> dict:
    left_text = " ".join(_subtitle_text_lines(str(left.get("text", "") or "")))
    right_text = " ".join(_subtitle_text_lines(str(right.get("text", "") or "")))
    merged = dict(left)
    merged["end"] = max(_setting_float(right, "end", 0.0), _setting_float(left, "end", 0.0))
    merged["text"] = f"{left_text} {right_text}".strip()
    if "timeline_end" in merged or "timeline_start" in merged:
        merged["timeline_start"] = _setting_float(merged, "start", 0.0)
        merged["timeline_end"] = merged["end"]
    if isinstance(left.get("words"), list) and isinstance(right.get("words"), list):
        merged["words"] = [dict(word) for word in left.get("words", [])] + [dict(word) for word in right.get("words", [])]
    policy = {
        "task": "final_sequence_cleanup",
        "stage": stage,
        "action": "merge",
        "reason": reason,
    }
    merged["_final_sequence_cleanup_policy"] = policy
    _clear_split_timing_projection_fields(merged)
    return merged


def _final_cleanup_source_texts(*rows: dict | None) -> list[str]:
    texts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("source_text", "original_text", "dictated_text", "raw_text", "_stt_no_llm_raw_text"):
            value = str(row.get(key, "") or "").strip()
            if value:
                texts.append(value)
        for candidate in list(row.get("stt_candidates") or []):
            if not isinstance(candidate, dict):
                continue
            value = str(candidate.get("text", "") or "").strip()
            if value:
                texts.append(value)
        words = row.get("words")
        if isinstance(words, list):
            word_text = " ".join(
                str(word.get("word", word.get("text", "")) or "").strip()
                for word in words
                if isinstance(word, dict)
            ).strip()
            if word_text:
                texts.append(word_text)
    return [text for text in texts if len(_compact_subtitle_text(text)) >= 3]


def _tiny_tail_drop_keeps_source_similarity(previous: dict, row: dict) -> bool:
    source_texts = _final_cleanup_source_texts(previous, row)
    if not source_texts:
        return False
    previous_text = " ".join(_subtitle_text_lines(str(previous.get("text", "") or "")))
    row_text = " ".join(_subtitle_text_lines(str(row.get("text", "") or "")))
    merged_text = f"{previous_text} {row_text}".strip()
    best_previous = max((_stt_candidate_similarity(previous_text, source) for source in source_texts), default=0.0)
    best_merged = max((_stt_candidate_similarity(merged_text, source) for source in source_texts), default=0.0)
    return best_previous + 0.005 >= best_merged


def _drop_tiny_tail_fragments(rows: list[dict], settings: dict | None, *, stage: str) -> tuple[list[dict], int]:
    if not rows:
        return rows, 0
    max_sec = max(0.04, _setting_float(settings or {}, "subtitle_final_tiny_fragment_max_sec", _FINAL_TINY_FRAGMENT_MAX_SEC))
    max_chars = max(1, _setting_int(settings or {}, "subtitle_final_tiny_fragment_max_chars", _FINAL_TINY_FRAGMENT_MAX_CHARS))
    max_gap = max(0.0, _setting_float(settings or {}, "subtitle_final_tiny_fragment_max_gap_sec", _FINAL_TINY_FRAGMENT_MAX_GAP_SEC))
    result: list[dict] = []
    dropped = 0
    for raw_row in rows:
        row = dict(raw_row)
        if not result:
            result.append(row)
            continue
        previous = result[-1]
        text = " ".join(_subtitle_text_lines(str(row.get("text", "") or "")))
        compact = _compact_subtitle_text(text)
        duration = max(0.0, _setting_float(row, "end", 0.0) - _setting_float(row, "start", 0.0))
        gap = _setting_float(row, "start", 0.0) - _setting_float(previous, "end", 0.0)
        if (
            compact
            and compact in _FINAL_FILLER_FRAGMENTS
            and len(compact) <= max_chars
            and duration <= max_sec
            and 0.0 <= gap <= max_gap
            and _same_segment_scope_local(previous, row)
            and _compatible_speaker_signature(previous, row)
            and not _is_speaker_split_multiline_segment(previous)
            and not _is_speaker_split_multiline_segment(row)
            and _tiny_tail_drop_keeps_source_similarity(previous, row)
        ):
            updated_previous = dict(previous)
            updated_previous["_final_sequence_cleanup_policy"] = {
                "task": "final_sequence_cleanup",
                "stage": stage,
                "action": "drop_tiny_tail_fragment",
                "dropped_text": text,
            }
            result[-1] = updated_previous
            dropped += 1
            continue
        result.append(row)
    return result, dropped


def _drop_shadowed_short_rows(rows: list[dict], settings: dict | None, *, stage: str) -> tuple[list[dict], int]:
    del stage
    if not rows:
        return rows, 0
    max_chars = max(4, _setting_int(settings or {}, "subtitle_final_shadow_drop_max_chars", 8))
    max_gap = max(0.0, _setting_float(settings or {}, "subtitle_final_shadow_drop_gap_sec", 0.08))
    min_growth = max(2, _setting_int(settings or {}, "subtitle_final_shadow_drop_growth_chars", 4))
    result: list[dict] = []
    dropped = 0
    count = len(rows)
    for index, raw_row in enumerate(rows):
        row = dict(raw_row)
        if index + 1 >= count:
            result.append(row)
            continue
        nxt = rows[index + 1]
        text = " ".join(_subtitle_text_lines(str(row.get("text", "") or "")))
        next_text = " ".join(_subtitle_text_lines(str(nxt.get("text", "") or "")))
        compact = _compact_subtitle_text(text)
        next_compact = _compact_subtitle_text(next_text)
        gap = _setting_float(nxt, "start", 0.0) - _setting_float(row, "end", 0.0)
        if (
            compact
            and next_compact
            and len(compact) <= max_chars
            and len(next_compact) >= len(compact) + min_growth
            and next_compact.startswith(compact)
            and gap <= max_gap
            and _same_segment_scope_local(row, nxt)
            and _compatible_speaker_signature(row, nxt)
            and not _is_speaker_split_multiline_segment(row)
            and not _is_speaker_split_multiline_segment(nxt)
        ):
            dropped += 1
            continue
        result.append(row)
    return result, dropped


def _merge_likely_oversplit_rows(rows: list[dict], settings: dict | None, *, stage: str) -> tuple[list[dict], int]:
    if not rows:
        return rows, 0
    max_gap = max(0.0, _setting_float(settings or {}, "subtitle_final_micro_merge_gap_sec", 0.08))
    split_threshold = max(12, _setting_int(settings or {}, "split_length_threshold", 20))
    max_chars = max(18, int(split_threshold * 1.45))
    max_cps = max(1.0, _setting_float(settings or {}, "sub_max_cps", _MAX_CPS))
    continuation_max_chars = max(6, _setting_int(settings or {}, "subtitle_final_micro_merge_continuation_max_chars", 14))
    result: list[dict] = []
    merged_count = 0
    for raw_row in rows:
        row = dict(raw_row)
        if not result:
            result.append(row)
            continue
        previous = result[-1]
        if previous.get("_final_sequence_cleanup_policy", {}).get("action") == "merge":
            result.append(row)
            continue
        prev_text = " ".join(_subtitle_text_lines(str(previous.get("text", "") or "")))
        text = " ".join(_subtitle_text_lines(str(row.get("text", "") or "")))
        prev_compact = _compact_subtitle_text(prev_text)
        compact = _compact_subtitle_text(text)
        gap = _setting_float(row, "start", 0.0) - _setting_float(previous, "end", 0.0)
        if (
            not prev_compact
            or not compact
            or gap > max_gap
            or _is_speaker_split_multiline_segment(previous)
            or _is_speaker_split_multiline_segment(row)
            or not _same_segment_scope_local(previous, row)
            or not _compatible_speaker_signature(previous, row)
        ):
            result.append(row)
            continue
        merged_text = f"{prev_text} {text}".strip()
        merged_compact_len = len(_compact_subtitle_text(merged_text))
        duration = max(0.05, _setting_float(row, "end", 0.0) - _setting_float(previous, "start", 0.0))
        merged_cps = merged_compact_len / duration
        reason = None
        if prev_compact in _FINAL_FILLER_FRAGMENTS or compact in _FINAL_FILLER_FRAGMENTS:
            reason = "filler_fragment"
        elif (
            len(prev_compact) <= continuation_max_chars
            and _FINAL_CONTINUATION_TAIL_RE.search(prev_compact)
            and not re.search(r"[?!…~]$", prev_text)
        ):
            reason = "continuation_tail"
        if reason and merged_compact_len <= max_chars and merged_cps <= max_cps * 1.12:
            result[-1] = _merge_adjacent_rows(previous, row, stage=stage, reason=reason)
            merged_count += 1
            continue
        result.append(row)
    return result, merged_count


def _trim_recent_overlap_rows(rows: list[dict], settings: dict | None, *, stage: str) -> tuple[list[dict], int]:
    del settings
    if not rows:
        return rows, 0
    result: list[dict] = []
    changed = 0
    for raw_row in rows:
        row = dict(raw_row)
        text = " ".join(_subtitle_text_lines(str(row.get("text", "") or "")))
        tokens = _subtitle_tokens(text)
        if (
            not tokens
            or not result
            or _is_speaker_split_multiline_segment(row)
        ):
            result.append(row)
            continue
        recent_rows = [item for item in result[-2:] if isinstance(item, dict)]
        recent_tokens = [
            token
            for item in recent_rows
            for token in _subtitle_tokens(str(item.get("text", "") or ""))
        ]
        updated_tokens = list(tokens)
        if recent_tokens:
            prefix_overlap = _overlap_token_count(recent_tokens, updated_tokens, mode="prefix")
            if prefix_overlap and (prefix_overlap >= 3 or _token_compact_len(updated_tokens[:prefix_overlap]) >= 8):
                updated_tokens = updated_tokens[prefix_overlap:]
            suffix_overlap = _overlap_token_count(recent_tokens, updated_tokens, mode="suffix")
            if suffix_overlap and (suffix_overlap >= 3 or _token_compact_len(updated_tokens[-suffix_overlap:]) >= 8):
                updated_tokens = updated_tokens[:-suffix_overlap]
        trimmed_text = _normalize_short_closing_phrase(" ".join(updated_tokens).strip())
        if trimmed_text != text:
            changed += 1
        if not trimmed_text:
            continue
        previous = result[-1]
        gap = _setting_float(row, "start", 0.0) - _setting_float(previous, "end", 0.0)
        previous_tokens = _subtitle_tokens(str(previous.get("text", "") or ""))
        if (
            previous_tokens
            and len(updated_tokens) > len(previous_tokens)
            and updated_tokens[-len(previous_tokens):] == previous_tokens
            and _is_low_value_duplicate_bridge_tokens(updated_tokens[:-len(previous_tokens)])
            and any(token in _FINAL_CLOSING_PHRASES for token in previous_tokens)
            and gap <= 0.35
            and _same_segment_scope_local(previous, row)
            and _compatible_speaker_signature(previous, row)
        ):
            changed += 1
            continue
        if (
            updated_tokens
            and _is_low_value_duplicate_bridge_tokens(updated_tokens)
            and any(token in _FINAL_CLOSING_PHRASES for token in previous_tokens)
            and gap <= 0.35
            and _same_segment_scope_local(previous, row)
            and _compatible_speaker_signature(previous, row)
        ):
            changed += 1
            continue
        if (
            _compact_subtitle_text(trimmed_text) == _compact_subtitle_text(str(previous.get("text", "") or ""))
            and gap <= 0.08
            and _same_segment_scope_local(previous, row)
            and _compatible_speaker_signature(previous, row)
        ):
            changed += 1
            continue
        row["text"] = trimmed_text
        if trimmed_text != text:
            row["_final_sequence_cleanup_policy"] = {
                "task": "final_sequence_cleanup",
                "stage": stage,
                "action": "trim_recent_overlap",
            }
        result.append(row)
    return result, changed


def _apply_final_sequence_cleanup(
    segments: list[dict],
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    if not segments or not _bool_setting(settings or {}, "subtitle_final_sequence_cleanup_enabled", True):
        return segments
    rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    if not rows:
        return segments
    rows, dropped_tiny = _drop_tiny_tail_fragments(rows, settings, stage=stage)
    rows, dropped_shadow = _drop_shadowed_short_rows(rows, settings, stage=stage)
    rows, merged = _merge_likely_oversplit_rows(rows, settings, stage=stage)
    rows, trimmed = _trim_recent_overlap_rows(rows, settings, stage=stage)
    if dropped_tiny or dropped_shadow or merged or trimmed:
        get_logger().log(
            "[자막후단보정] "
            f"{stage}: 초미세 tail 삭제 {dropped_tiny}개, 그림자 삭제 {dropped_shadow}개, "
            f"과분할 병합 {merged}개, 최근중복 정리 {trimmed}개"
        )
    return rows


def _safe_source_integrity_variant(source_segments: list[dict], settings: dict | None) -> list[dict]:
    rows = [
        dict(seg)
        for seg in list(source_segments or [])
        if isinstance(seg, dict) and str(seg.get("text", "") or "").strip() and not seg.get("is_gap")
    ]
    if not rows:
        return []
    rows = adjust_timing(rows)
    rows = apply_final_gap_settings(rows, settings or {}, force=True)
    rows = align_stt_candidates_to_subtitle_segments(rows)
    raw_corr = get_local_dataset_corrections()
    corrections: dict = raw_corr if isinstance(raw_corr, dict) else {}
    rows = _enforce_final_subtitle_text_policy(rows, corrections)
    rows = _apply_final_sequence_cleanup(rows, settings or {}, stage="source_integrity")
    return _expand_non_speaker_multiline_segments(rows, settings or {})


def _source_stt_anchor_rows(source_segments: list[dict]) -> list[dict]:
    anchors: list[dict] = []
    for source_index, raw_seg in enumerate(list(source_segments or [])):
        if not isinstance(raw_seg, dict):
            continue
        seg = dict(raw_seg)
        selected_source_name = str(seg.get("stt_selected_source") or seg.get("stt_ensemble_source") or "").strip().upper()
        selected_source_base = selected_source_name.split("_", 1)[0]
        raw_stt_candidates = []
        for candidate in list(seg.get("stt_candidates") or []):
            if not isinstance(candidate, dict):
                continue
            source_name = str(
                candidate.get("source")
                or candidate.get("stt_selected_source")
                or candidate.get("stt_preview_source")
                or candidate.get("stt_source")
                or ""
            ).strip().upper()
            if source_name.split("_", 1)[0] not in {"STT1", "STT2"}:
                continue
            if not str(candidate.get("text", "") or "").strip():
                continue
            raw_stt_candidates.append(dict(candidate))
        raw_stt_source_bases = {
            str(candidate.get("source", "") or "").strip().upper().split("_", 1)[0]
            for candidate in raw_stt_candidates
        }
        include_segment_anchor = (
            not raw_stt_candidates
            or (
                selected_source_base in {"STT1", "STT2"}
                and selected_source_base not in raw_stt_source_bases
            )
        )

        if raw_stt_candidates:
            def _anchor_candidate_order(candidate: dict) -> tuple[int, float]:
                source_base = str(candidate.get("source", "") or "").strip().upper().split("_", 1)[0]
                selected_penalty = 0 if selected_source_base and source_base == selected_source_base else 1
                return selected_penalty, -_stt_candidate_score100(candidate)

            # 변경 금지: 선택된 STT1/2 원문 후보가 있으면 이미 후처리된 seg["text"]를
            # 같은 소스의 STT 앵커로 승격하지 않는다. 이 줄을 풀면 "STT1은 맞는데
            # 최종 자막은 엉뚱함" 케이스에서 오염된 현재 텍스트가 복구 기준이 된다.
            candidates = ([] if not include_segment_anchor else [seg])
            candidates.extend(sorted(raw_stt_candidates, key=_anchor_candidate_order))
        else:
            candidates = [seg]
        for cand_index, candidate in enumerate(candidates):
            text = str(candidate.get("text", "") or "").strip()
            if not text or _stt_candidate_compact_text(text) in {"", "-"}:
                continue
            span = _stt_decision_timing_span(candidate) or _stt_decision_timing_span(seg)
            if span is None:
                continue
            start, end = span
            if end <= start:
                continue
            source_name = str(
                candidate.get("source")
                or candidate.get("stt_selected_source")
                or seg.get("stt_selected_source")
                or seg.get("stt_ensemble_source")
                or "STT"
            ).strip().upper()
            source_base = source_name.split("_", 1)[0]
            anchor_priority = 0.0
            if cand_index == 0:
                anchor_priority += 4.0
            if selected_source_base and source_base == selected_source_base:
                anchor_priority += 2.0
            anchor_priority += min(1.0, _stt_candidate_score100(candidate) / 100.0)
            anchors.append(
                {
                    **{key: seg[key] for key in _stt_selection_metadata(seg).keys() if key in seg},
                    **dict(candidate),
                    "text": text,
                    "start": float(start),
                    "end": float(end),
                    "source": source_name,
                    "_anchor_priority": round(anchor_priority, 4),
                    "_source_segment_index": source_index,
                    "_source_candidate_index": cand_index,
                }
            )
    anchors.sort(key=lambda item: (float(item.get("start", 0.0) or 0.0), float(item.get("end", 0.0) or 0.0)))
    return anchors


_FINAL_STT_ANCHOR_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:[%％]|[A-Za-z가-힣]+)?")


def _subtitle_number_tokens(text: str) -> set[str]:
    return {
        _stt_candidate_compact_text(token)
        for token in _FINAL_STT_ANCHOR_NUMBER_RE.findall(str(text or ""))
        if _stt_candidate_compact_text(token)
    }


def _final_text_overextends_stt_anchor(text: str, anchor_text: str, settings: dict | None) -> bool:
    text_compact = _stt_candidate_compact_text(text)
    anchor_compact = _stt_candidate_compact_text(anchor_text)
    if not text_compact or not anchor_compact or text_compact == anchor_compact:
        return False
    min_anchor_chars = max(3, _setting_int(settings or {}, "subtitle_final_stt_anchor_guard_overextend_min_chars", 5))
    if len(anchor_compact) < min_anchor_chars or anchor_compact not in text_compact:
        return False
    extra_chars = max(0, len(text_compact) - len(anchor_compact))
    max_extra_chars = max(2, _setting_int(settings or {}, "subtitle_final_stt_anchor_guard_overextend_max_extra_chars", 5))
    max_extra_ratio = max(
        0.05,
        _setting_float(settings or {}, "subtitle_final_stt_anchor_guard_overextend_max_extra_ratio", 0.45),
    )
    allowed_extra = max(max_extra_chars, int(round(len(anchor_compact) * max_extra_ratio)))
    return extra_chars > allowed_extra


def _final_overextension_backed_by_adjacent_primary_anchor(text: str, anchor: dict, anchors: list[dict], settings: dict | None) -> bool:
    text_compact = _stt_candidate_compact_text(text)
    if not text_compact:
        return False
    current_key = _stt_anchor_guard_key(anchor)
    current_source_index = anchor.get("_source_segment_index")
    min_anchor_chars = max(3, _setting_int(settings or {}, "subtitle_final_stt_anchor_guard_overextend_min_chars", 5))
    for other in list(anchors or []):
        if _stt_anchor_guard_key(other) == current_key:
            continue
        if other.get("_source_segment_index") == current_source_index:
            continue
        if int(other.get("_source_candidate_index", 0) or 0) != 0:
            continue
        other_text = str(other.get("text", "") or "")
        other_compact = _stt_candidate_compact_text(other_text)
        if len(other_compact) >= min_anchor_chars and other_compact in text_compact:
            return True
    return False


def _stt_anchor_guard_key(anchor: dict) -> tuple:
    return (
        anchor.get("_source_segment_index"),
        anchor.get("_source_candidate_index"),
        round(float(anchor.get("start", 0.0) or 0.0), 3),
        round(float(anchor.get("end", 0.0) or 0.0), 3),
        _stt_candidate_compact_text(str(anchor.get("text", "") or "")),
    )


def _subtitle_row_span(row: dict) -> tuple[float, float] | None:
    try:
        start = float(row.get("start"))
        end = float(row.get("end"))
    except (TypeError, ValueError):
        return None
    if end <= start:
        return None
    return start, end


def _best_stt_anchor_for_final_row(row: dict, anchors: list[dict], settings: dict | None) -> tuple[dict | None, dict]:
    row_span = _subtitle_row_span(row)
    if row_span is None:
        return None, {}
    row_start, row_end = row_span
    row_mid = (row_start + row_end) / 2.0
    row_duration = max(0.05, row_end - row_start)
    max_mid_delta = max(0.8, _setting_float(settings or {}, "subtitle_final_stt_anchor_guard_max_mid_delta_sec", 1.9))
    best: tuple[float, dict, dict] | None = None
    for anchor in anchors:
        anchor_span = _subtitle_row_span(anchor)
        if anchor_span is None:
            continue
        anchor_start, anchor_end = anchor_span
        anchor_duration = max(0.05, anchor_end - anchor_start)
        overlap = max(0.0, min(row_end, anchor_end) - max(row_start, anchor_start))
        overlap_ratio = overlap / max(0.05, min(row_duration, anchor_duration))
        anchor_mid = (anchor_start + anchor_end) / 2.0
        mid_delta = abs(anchor_mid - row_mid)
        if overlap_ratio <= 0.0 and mid_delta > max(max_mid_delta, row_duration + 0.65, anchor_duration + 0.65):
            continue
        temporal_score = (overlap_ratio * 4.0) + max(0.0, 1.0 - (mid_delta / max(0.05, max_mid_delta)))
        text_similarity = _stt_candidate_similarity(str(row.get("text", "") or ""), str(anchor.get("text", "") or ""))
        anchor_priority = float(anchor.get("_anchor_priority", 0.0) or 0.0)
        score = temporal_score + (text_similarity * 0.35) + (anchor_priority * 0.12)
        meta = {
            "overlap_ratio": round(overlap_ratio, 4),
            "mid_delta_sec": round(mid_delta, 4),
            "text_similarity": round(text_similarity, 4),
            "temporal_score": round(temporal_score, 4),
            "anchor_priority": round(anchor_priority, 4),
        }
        if best is None or score > best[0]:
            best = (score, anchor, meta)
    if best is None:
        return None, {}
    return best[1], best[2]


def _stt_anchor_is_represented(anchor: dict, rows: list[dict], settings: dict | None) -> bool:
    anchor_span = _subtitle_row_span(anchor)
    if anchor_span is None:
        return False
    anchor_start, anchor_end = anchor_span
    anchor_mid = (anchor_start + anchor_end) / 2.0
    anchor_duration = max(0.05, anchor_end - anchor_start)
    anchor_text = str(anchor.get("text", "") or "").strip()
    anchor_compact = _stt_candidate_compact_text(anchor_text)
    if not anchor_compact:
        return False
    min_similarity = max(
        0.05,
        min(0.95, _setting_float(settings or {}, "subtitle_final_stt_anchor_guard_present_similarity", 0.64)),
    )
    max_mid_delta = max(
        0.25,
        _setting_float(settings or {}, "subtitle_final_stt_anchor_guard_present_mid_delta_sec", 1.1),
    )
    for row in list(rows or []):
        row_span = _subtitle_row_span(row)
        if row_span is None:
            continue
        row_start, row_end = row_span
        row_mid = (row_start + row_end) / 2.0
        row_duration = max(0.05, row_end - row_start)
        overlap = max(0.0, min(row_end, anchor_end) - max(row_start, anchor_start))
        overlap_ratio = overlap / max(0.05, min(row_duration, anchor_duration))
        mid_delta = abs(row_mid - anchor_mid)
        if overlap_ratio <= 0.0 and mid_delta > max_mid_delta:
            continue
        row_text = str(row.get("text", "") or "").strip()
        row_compact = _stt_candidate_compact_text(row_text)
        if len(anchor_compact) >= 4 and anchor_compact in row_compact:
            return True
        if _stt_candidate_similarity(anchor_text, row_text) >= min_similarity:
            return True
    return False


def _trim_rows_for_inserted_stt_anchor(rows: list[dict], anchor: dict, settings: dict | None) -> list[dict]:
    anchor_span = _subtitle_row_span(anchor)
    if anchor_span is None:
        return rows
    anchor_start, anchor_end = anchor_span
    min_duration = max(0.15, min(0.5, _setting_float(settings or {}, "sub_min_duration", 0.3)))
    trimmed: list[dict] = []
    for raw_row in list(rows or []):
        row = dict(raw_row)
        row_span = _subtitle_row_span(row)
        if row_span is None:
            trimmed.append(row)
            continue
        row_start, row_end = row_span
        overlap = max(0.0, min(row_end, anchor_end) - max(row_start, anchor_start))
        if overlap <= 0.0:
            trimmed.append(row)
            continue
        old_start, old_end = row_start, row_end
        if row_start < anchor_start < row_end:
            row_end = min(row_end, anchor_start)
            if row_end - row_start >= min_duration:
                row["end"] = row_end
                row["_final_stt_anchor_trim_policy"] = {
                    "task": "final_stt_anchor_guard",
                    "action": "trim_end_for_inserted_stt_anchor",
                    "old_start": round(old_start, 3),
                    "old_end": round(old_end, 3),
                    "new_start": round(row_start, 3),
                    "new_end": round(row_end, 3),
                    "inserted_text": str(anchor.get("text", "") or "")[:80],
                }
        elif row_start < anchor_end < row_end:
            row_start = max(row_start, anchor_end)
            if row_end - row_start >= min_duration:
                row["start"] = row_start
                row["_final_stt_anchor_trim_policy"] = {
                    "task": "final_stt_anchor_guard",
                    "action": "trim_start_for_inserted_stt_anchor",
                    "old_start": round(old_start, 3),
                    "old_end": round(old_end, 3),
                    "new_start": round(row_start, 3),
                    "new_end": round(row_end, 3),
                    "inserted_text": str(anchor.get("text", "") or "")[:80],
                }
        trimmed.append(row)
    return trimmed


def _restore_final_stt_anchor_drift(
    optimized: list[dict],
    source_segments: list[dict],
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    settings = dict(settings or {})
    if not optimized or not source_segments:
        return optimized
    if not _bool_setting(settings, "subtitle_final_stt_anchor_guard_enabled", True):
        return optimized
    anchors = _source_stt_anchor_rows(source_segments)
    if not anchors:
        return optimized
    min_similarity = max(
        0.05,
        min(0.95, _setting_float(settings, "subtitle_final_stt_anchor_guard_min_similarity", 0.38)),
    )
    min_source_chars = max(2, _setting_int(settings, "subtitle_final_stt_anchor_guard_min_source_chars", 3))
    min_overlap_ratio = max(
        0.0,
        min(0.95, _setting_float(settings, "subtitle_final_stt_anchor_guard_min_overlap_ratio", 0.35)),
    )
    strict_mid_delta = max(
        0.1,
        _setting_float(settings, "subtitle_final_stt_anchor_guard_strict_mid_delta_sec", 0.45),
    )
    restored_count = 0
    rows: list[dict] = []
    used_anchor_keys: set[tuple] = set()
    for raw_row in list(optimized or []):
        row = dict(raw_row) if isinstance(raw_row, dict) else {}
        text = str(row.get("text", "") or "").strip()
        if not text or row.get("is_gap"):
            rows.append(row)
            continue
        anchor, meta = _best_stt_anchor_for_final_row(row, anchors, settings)
        if not anchor:
            rows.append(row)
            continue
        anchor_key = _stt_anchor_guard_key(anchor)
        if anchor_key in used_anchor_keys:
            rows.append(row)
            continue
        anchor_text = str(anchor.get("text", "") or "").strip()
        if len(_stt_candidate_compact_text(anchor_text)) < min_source_chars:
            rows.append(row)
            continue
        text_numbers = _subtitle_number_tokens(text)
        anchor_numbers = _subtitle_number_tokens(anchor_text)
        if text_numbers and not text_numbers.issubset(anchor_numbers):
            rows.append(row)
            continue
        similarity = float(meta.get("text_similarity", 0.0) or 0.0)
        overextended = _final_text_overextends_stt_anchor(text, anchor_text, settings)
        overextension_backed = (
            overextended
            and _final_overextension_backed_by_adjacent_primary_anchor(text, anchor, anchors, settings)
        )
        if similarity >= min_similarity and not (overextended and not overextension_backed):
            rows.append(row)
            continue
        overlap_ratio = float(meta.get("overlap_ratio", 0.0) or 0.0)
        mid_delta = float(meta.get("mid_delta_sec", 999.0) or 999.0)
        if overlap_ratio < min_overlap_ratio and mid_delta > strict_mid_delta:
            rows.append(row)
            continue
        restored = {
            **row,
            "text": anchor_text,
            "start": float(anchor.get("start", row.get("start", 0.0)) or 0.0),
            "end": float(anchor.get("end", row.get("end", row.get("start", 0.0))) or 0.0),
            "stt_selected_source": str(anchor.get("source") or row.get("stt_selected_source") or "STT"),
            "_stt_original_candidate_start": float(anchor.get("start", row.get("start", 0.0)) or 0.0),
            "_stt_original_candidate_end": float(anchor.get("end", row.get("end", row.get("start", 0.0))) or 0.0),
            "_final_stt_anchor_guard_policy": {
                "task": "final_stt_anchor_guard",
                "stage": stage,
                "action": "restore_stt_anchor",
                "old_text": text,
                "new_text": anchor_text,
                "source": str(anchor.get("source") or "STT"),
                "source_segment_index": anchor.get("_source_segment_index"),
                "source_candidate_index": anchor.get("_source_candidate_index"),
                "overextended_anchor": bool(overextended),
                **meta,
            },
        }
        restored_count += 1
        used_anchor_keys.add(anchor_key)
        rows.append(restored)
    if restored_count:
        get_logger().log(f"[자막무결성-STT앵커] {stage}: STT 후보와 어긋난 최종 자막 {restored_count}개 복구")
    return rows


def _restore_missing_final_stt_anchor_rows(
    optimized: list[dict],
    source_segments: list[dict],
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    settings = dict(settings or {})
    if not optimized or not source_segments:
        return optimized
    if not _bool_setting(settings, "subtitle_final_stt_anchor_guard_enabled", True):
        return optimized
    if not _bool_setting(settings, "subtitle_final_stt_anchor_guard_insert_missing_enabled", True):
        return optimized
    anchors = _source_stt_anchor_rows(source_segments)
    if not anchors:
        return optimized
    min_source_chars = max(2, _setting_int(settings, "subtitle_final_stt_anchor_guard_min_source_chars", 3))
    rows = [dict(row) for row in list(optimized or []) if isinstance(row, dict)]
    inserted_count = 0
    for anchor in anchors:
        if int(anchor.get("_source_candidate_index", 0) or 0) != 0:
            continue
        anchor_text = str(anchor.get("text", "") or "").strip()
        if len(_stt_candidate_compact_text(anchor_text)) < min_source_chars:
            continue
        if _stt_anchor_is_represented(anchor, rows, settings):
            continue
        anchor_span = _subtitle_row_span(anchor)
        if anchor_span is None:
            continue
        anchor_start, anchor_end = anchor_span
        rows = _trim_rows_for_inserted_stt_anchor(rows, anchor, settings)
        rows.append(
            {
                **_stt_selection_metadata(anchor),
                "start": float(anchor_start),
                "end": float(anchor_end),
                "text": anchor_text,
                "stt_selected_source": str(anchor.get("source") or anchor.get("stt_selected_source") or "STT"),
                "_stt_original_candidate_start": float(anchor_start),
                "_stt_original_candidate_end": float(anchor_end),
                "_final_stt_anchor_guard_policy": {
                    "task": "final_stt_anchor_guard",
                    "stage": stage,
                    "action": "insert_missing_stt_anchor",
                    "new_text": anchor_text,
                    "source": str(anchor.get("source") or "STT"),
                    "source_segment_index": anchor.get("_source_segment_index"),
                    "source_candidate_index": anchor.get("_source_candidate_index"),
                },
            }
        )
        inserted_count += 1
    if inserted_count:
        rows.sort(key=lambda item: (float(item.get("start", 0.0) or 0.0), float(item.get("end", 0.0) or 0.0)))
        get_logger().log(f"[자막무결성-STT앵커] {stage}: 최종 자막에서 누락된 STT 앵커 {inserted_count}개 복구")
    return rows


def _attach_final_integrity_policy(rows: list[dict], policy: dict) -> list[dict]:
    if not rows:
        return rows
    out = [dict(row) for row in rows]
    out[0]["_final_transcript_integrity_policy"] = dict(policy)
    return out


def _nonempty_subtitle_segment_count(rows: list[dict] | None) -> int:
    return sum(
        1
        for seg in rows or []
        if isinstance(seg, dict) and str(seg.get("text", "") or "").strip()
    )


def _final_transcript_integrity_guard(
    optimized: list[dict],
    source_segments: list[dict],
    vad_segments: list[dict] | None,
    settings: dict | None,
) -> list[dict]:
    del vad_segments
    settings = dict(settings or {})
    if not _bool_setting(settings, "subtitle_final_integrity_guard_enabled", True):
        return optimized
    if not optimized or not source_segments:
        return optimized
    source_text = _sequence_text_for_integrity(source_segments)
    final_text = _sequence_text_for_integrity(optimized)
    if not source_text or not final_text:
        return optimized

    guard_settings = {
        **settings,
        "llm_verifier_enabled": True,
        "llm_verifier_block_added_content_tokens": True,
        "llm_verifier_preserve_numbers": True,
        "llm_verifier_preserve_interjections": True,
        "llm_verifier_min_similarity": max(
            0.9,
            _setting_float(settings, "subtitle_final_integrity_min_similarity", 0.9),
            _setting_float(settings, "llm_verifier_min_similarity", 0.86),
        ),
        "llm_verifier_max_length_delta_ratio": min(
            0.12,
            _setting_float(settings, "subtitle_final_integrity_max_length_delta_ratio", 0.12),
            _setting_float(settings, "llm_verifier_max_length_delta_ratio", 0.16),
        ),
        "llm_verifier_max_chunks": max(1, _setting_int(settings, "llm_verifier_max_chunks", 8)),
    }
    verified, decision = verify_llm_chunks_for_subtitle(
        source_text,
        [final_text],
        guard_settings,
        _profile_from_settings(settings),
    )
    policy = {
        "task": "final_transcript_integrity_guard",
        "accepted": bool(verified),
        "reason": str(decision.get("reason") or "ok"),
        "source_segments": _nonempty_subtitle_segment_count(source_segments),
        "final_segments": _nonempty_subtitle_segment_count(optimized),
        "source_compact_len": decision.get("source_compact_len"),
        "candidate_compact_len": decision.get("candidate_compact_len"),
        "similarity": decision.get("similarity"),
        "length_delta_ratio": decision.get("length_delta_ratio"),
    }
    if verified is not None:
        return _attach_final_integrity_policy(optimized, policy)

    fallback = _safe_source_integrity_variant(source_segments, settings)
    if not fallback:
        get_logger().log(
            "[자막무결성-경고] 최종 자막이 STT 원문과 불일치하지만 복구할 STT 원문 세그먼트가 없습니다 "
            f"({describe_llm_verifier_decision(decision)})"
        )
        return _attach_final_integrity_policy(optimized, {**policy, "fallback": "unavailable"})
    get_logger().log(
        "[자막무결성-롤백] 최종 자막이 STT1/2 원문 흐름과 불일치하여 STT 원문 기반 결과로 복구 "
        f"({describe_llm_verifier_decision(decision)})"
    )
    return _attach_final_integrity_policy(
        fallback,
        {
            **policy,
            "fallback": "source_stt_segments",
            "accepted": False,
        },
    )
