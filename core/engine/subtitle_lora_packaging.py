# Version: 03.14.29
# Phase: PHASE2
"""LoRA subtitle packaging and speaker-line helpers.

Behavior-preserving split from subtitle_engine.py.
"""

from __future__ import annotations

import re

from core.engine.llm_candidate_policy import (
    _lora_line_break_patterns as _llm_lora_line_break_patterns,
    build_llm_candidate_options,
)
from core.engine.subtitle_text_policy import (
    normalize_subtitle_text_lines as _normalize_subtitle_text_lines,
    split_visible_len as _split_visible_len,
)
from core.engine.subtitle_settings import (
    _get_user_settings,
    _setting_float,
    _setting_int,
)
from core.personalization.lora_models import line_break_pattern_for_text
from core.runtime.logger import get_logger
from core.subtitle_quality.timestamp_regrouper import merge_short_segments_by_gap, regroup_by_word_timestamps
from core.utils import load_subtitle_rules

_S = _get_user_settings()
_MIN_DURATION = _setting_float(_S, "sub_min_duration", 0.3)
_MAX_DURATION = _setting_float(_S, "sub_max_duration", 6.0)
_MAX_CPS = _setting_int(_S, "sub_max_cps", 12)


def _bool_setting(settings: dict, key: str, default: bool = True) -> bool:
    value = settings.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔", "미사용"}
    return bool(value)


def _lora_style_merge_settings(settings: dict | None) -> dict:
    settings = dict(settings or {})
    try:
        from core.native_swift_subtitle_lora_merge import lora_merge_settings_via_swift

        native = lora_merge_settings_via_swift(settings)
        if native is not None:
            return native
    except Exception:
        pass

    lora_floor_chars = max(8, _setting_int(settings, "subtitle_lora_split_floor_chars", 20))
    max_chars = max(lora_floor_chars, _setting_int(settings, "split_length_threshold", 20))
    min_duration = max(
        _setting_float(settings, "sub_min_duration", 0.3),
        _setting_float(settings, "subtitle_lora_micro_merge_min_duration", 0.8),
    )
    gap_break = max(
        _setting_float(settings, "sub_gap_break_sec", 1.5),
        _setting_float(settings, "subtitle_lora_micro_merge_gap_sec", 1.8),
    )
    word_gap = max(
        _setting_float(settings, "word_timing_gap_break_sec", 0.65),
        _setting_float(settings, "subtitle_lora_micro_merge_word_gap_sec", 1.2),
    )
    continuous = max(
        _setting_float(settings, "continuous_threshold", 2.0),
        _setting_float(settings, "subtitle_lora_micro_merge_continuous_sec", 3.0),
        gap_break,
    )
    return {
        "split_length_threshold": max_chars,
        "sub_min_duration": round(min_duration, 3),
        "sub_gap_break_sec": round(gap_break, 3),
        "word_timing_gap_break_sec": round(word_gap, 3),
        "continuous_threshold": round(continuous, 3),
    }


def _lora_style_merge_mode(settings: dict | None) -> str:
    raw = str(dict(settings or {}).get("subtitle_lora_micro_merge_mode") or "full").strip().lower()
    if raw in {"readability", "readability_selective", "selective"}:
        return "readability_selective"
    return "full"


def _segment_quality_label(segment: dict) -> str:
    quality = dict(segment.get("quality") or {})
    return str(quality.get("confidence_label") or segment.get("subtitle_confidence_label") or "").strip().lower()


def _segment_quality_score(segment: dict) -> float:
    quality = dict(segment.get("quality") or {})
    score = quality.get("confidence_score", segment.get("subtitle_confidence_score"))
    try:
        value = float(score)
    except Exception:
        return 0.0
    if 0.0 <= value <= 1.0:
        value *= 100.0
    return max(0.0, min(100.0, value))


def _segment_compact_len(segment: dict) -> int:
    return len(re.sub(r"\s+", "", str(segment.get("text", "") or "")))


def _segment_duration(segment: dict) -> float:
    start = _setting_float(segment, "start", 0.0)
    end = _setting_float(segment, "end", start)
    return max(0.0, end - start)


def _lora_readability_merge_reasons(segment: dict, settings: dict | None, merge_settings: dict) -> list[str]:
    threshold = max(8, int(merge_settings.get("split_length_threshold", 20) or 20))
    chars = _segment_compact_len(segment)
    duration = max(0.1, _segment_duration(segment))
    cps = chars / duration
    max_cps = max(1, _setting_int(settings or {}, "sub_max_cps", _MAX_CPS))
    min_duration = max(0.05, float(merge_settings.get("sub_min_duration", _MIN_DURATION) or _MIN_DURATION))
    floor_chars = max(2, int(threshold * 0.45))
    quality_label = _segment_quality_label(segment)
    quality_score = _segment_quality_score(segment)
    uncertainty = dict(segment.get("_uncertainty_policy") or {})
    uncertainty_bucket = str(uncertainty.get("bucket") or "").strip().lower()
    uncertainty_reasons = {
        str(item.get("reason") or "").strip().lower()
        for item in list(uncertainty.get("reasons") or [])
        if isinstance(item, dict)
    }

    reasons: list[str] = []
    if duration < min_duration or chars <= floor_chars:
        reasons.append("micro_fragment")
    if cps > max_cps * 1.04:
        reasons.append("high_cps")
    if chars > int(threshold * 1.12):
        reasons.append("long_text")
    if quality_label in {"yellow", "red"}:
        reasons.append(f"quality_{quality_label}")
    elif 0.0 < quality_score < float((settings or {}).get("subtitle_lora_selective_quality_max_score", 82.0) or 82.0):
        reasons.append("low_quality_score")
    if uncertainty_bucket == "precision":
        reasons.append("precision_bucket")
    for key in ("high_cps", "long_text", "quality_red", "quality_yellow"):
        if key in uncertainty_reasons and key not in reasons:
            reasons.append(key)
    return reasons


def _selective_lora_merge_indexes(rows: list[dict], settings: dict | None, merge_settings: dict) -> tuple[set[int], dict[int, list[str]]]:
    try:
        from core.native_swift_subtitle_lora_merge import selective_lora_merge_indexes_via_swift

        native = selective_lora_merge_indexes_via_swift(rows, settings, merge_settings)
        if native is not None:
            return native
    except Exception:
        pass

    selected: set[int] = set()
    reasons_map: dict[int, list[str]] = {}
    for idx, row in enumerate(rows):
        reasons = _lora_readability_merge_reasons(row, settings, merge_settings)
        if not reasons:
            continue
        reasons_map[idx] = reasons
        selected.add(idx)
        if idx > 0:
            selected.add(idx - 1)
        if idx + 1 < len(rows):
            selected.add(idx + 1)
    return selected, reasons_map


def _apply_lora_style_micro_merge_selective(
    rows: list[dict],
    vad_segments: list[dict] | None,
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    merge_settings = _lora_style_merge_settings(settings)
    selected_indexes, reasons_map = _selective_lora_merge_indexes(rows, settings, merge_settings)
    if not selected_indexes:
        return rows

    for idx, row in enumerate(rows):
        policy = dict(row.get("_lora_style_merge_policy") or {})
        policy["mode"] = "readability_selective"
        if idx in reasons_map:
            policy["selective_reasons"] = list(reasons_map[idx])
        row["_lora_style_merge_policy"] = policy

    merged_rows: list[dict] = []
    merge_saved = 0
    index = 0
    while index < len(rows):
        if index not in selected_indexes:
            merged_rows.append(rows[index])
            index += 1
            continue
        tail = index + 1
        while tail < len(rows) and tail in selected_indexes:
            tail += 1
        chunk = [dict(item) for item in rows[index:tail]]
        if len(chunk) >= 2:
            out_chunk = merge_short_segments_by_gap(
                chunk,
                min_duration=float(merge_settings["sub_min_duration"]),
                max_chars=int(merge_settings["split_length_threshold"]),
                gap_break_sec=min(float(merge_settings["sub_gap_break_sec"]), 0.8),
                vad_segments=vad_segments or [],
                word_gap_break_sec=float(merge_settings["word_timing_gap_break_sec"]),
            )
            merge_saved += max(0, len(chunk) - len(out_chunk))
            merged_rows.extend(out_chunk)
        else:
            merged_rows.extend(chunk)
        index = tail

    if merge_saved > 0:
        get_logger().log(
            f"[LoRA자막묶음] {stage}: readability selective로 {merge_saved}개 미세 자막 병합"
        )
    return merged_rows


def _seed_lora_style_merge_context(segments: list[dict], settings: dict | None, *, stage: str) -> list[dict]:
    merge_settings = _lora_style_merge_settings(settings)
    rows: list[dict] = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        row = dict(seg)
        segment_settings = dict(row.get("_lora_segment_settings") or {})
        gap_settings = dict(row.get("_lora_gap_settings") or {})
        for key in ("split_length_threshold", "sub_min_duration", "sub_gap_break_sec", "word_timing_gap_break_sec"):
            segment_settings.setdefault(key, merge_settings[key])
        gap_settings.setdefault("continuous_threshold", merge_settings["continuous_threshold"])
        gap_settings.setdefault("sub_gap_break_sec", merge_settings["sub_gap_break_sec"])
        row["_lora_segment_settings"] = segment_settings
        row["_lora_gap_settings"] = gap_settings
        row["_lora_style_merge_policy"] = {
            "task": "lora_style_micro_merge",
            "stage": stage,
            "source": "runtime_lora_style_settings",
            "settings": merge_settings,
        }
        rows.append(row)
    return rows

def _apply_lora_style_micro_merge(
    segments: list[dict],
    vad_segments: list[dict] | None,
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    settings = dict(settings or {})
    if not segments or not _bool_setting(settings, "subtitle_lora_micro_merge_enabled", True):
        return segments
    rows = _seed_lora_style_merge_context(segments, settings, stage=stage)
    merge_mode = _lora_style_merge_mode(settings)
    if merge_mode == "readability_selective":
        return _apply_lora_style_micro_merge_selective(rows, vad_segments, settings, stage=stage)
    merge_settings = _lora_style_merge_settings(settings)
    before_count = len(rows)
    try:
        merged = regroup_by_word_timestamps(
            rows,
            max_chars=int(merge_settings["split_length_threshold"]),
            max_duration=_setting_float(settings, "sub_max_duration", _MAX_DURATION),
            max_cps=_setting_int(settings, "sub_max_cps", _MAX_CPS),
            min_duration=float(merge_settings["sub_min_duration"]),
            gap_break_sec=float(merge_settings["sub_gap_break_sec"]),
            word_gap_break_sec=float(merge_settings["word_timing_gap_break_sec"]),
            vad_segments=vad_segments or [],
            frame_rate=float(settings.get("video_fps", 0.0) or 0.0),
            rules=load_subtitle_rules(),
        )
    except Exception as exc:
        get_logger().log(f"[LoRA자막묶음] 실패({stage}): {exc}")
        return segments
    if len(merged) < before_count:
        get_logger().log(f"[LoRA자막묶음] {stage}: 짧은 자막 {before_count}개 → {len(merged)}개로 병합")
    return merged


def _lora_packaging_mode(settings: dict | None) -> str:
    try:
        from core.native_swift_subtitle_lora_merge import lora_packaging_mode_via_swift

        native = lora_packaging_mode_via_swift(settings)
        if native:
            return native
    except Exception:
        pass

    raw = str(dict(settings or {}).get("subtitle_lora_packaging_mode") or "full").strip().lower()
    if raw in {"readability", "readability_selective", "selective"}:
        return "readability_selective"
    return "full"


def _subtitle_text_lines(text: str) -> list[str]:
    normalized = _normalize_subtitle_text_lines(text)
    return [line.strip() for line in str(normalized or "").splitlines() if line.strip()]


def _packaging_target_patterns(settings: dict | None) -> list[str]:
    return list(_llm_lora_line_break_patterns(dict(settings or {}), limit=4) or [])


def _lora_packaging_reasons(segment: dict, settings: dict | None) -> list[str]:
    text = str(segment.get("text", "") or "")
    if not text.strip():
        return []
    threshold = max(8, _setting_int(settings or {}, "split_length_threshold", 20))
    chars = _split_visible_len(text)
    lines = _subtitle_text_lines(text)
    current_pattern = line_break_pattern_for_text(text)
    target_patterns = _packaging_target_patterns(settings)
    target_line_count = max(0, _setting_int(settings or {}, "subtitle_target_line_count", 0))
    quality_label = _segment_quality_label(segment)
    quality_score = _segment_quality_score(segment)
    quality_max_score = _setting_float(settings or {}, "subtitle_lora_packaging_quality_max_score", 84.0)
    try:
        from core.native_swift_subtitle_lora_merge import lora_packaging_reasons_via_swift

        native = lora_packaging_reasons_via_swift(
            threshold=threshold,
            chars=chars,
            line_count=len(lines),
            current_pattern=current_pattern,
            target_patterns=target_patterns,
            target_line_count=target_line_count,
            quality_label=quality_label,
            quality_score=quality_score,
            quality_max_score=quality_max_score,
        )
        if native is not None:
            return native
    except Exception:
        pass

    reasons: list[str] = []
    if len(lines) <= 1 and chars >= max(10, int(threshold * 0.88)):
        reasons.append("single_line_overflow")
    if target_patterns and current_pattern not in target_patterns:
        reasons.append("pattern_mismatch")
    if target_line_count >= 2 and len(lines) < target_line_count:
        reasons.append("line_count_target")
    if quality_label in {"yellow", "red"}:
        reasons.append(f"quality_{quality_label}")
    elif 0.0 < quality_score < quality_max_score:
        reasons.append("low_quality_score")
    return reasons


def _packaging_candidate_score(
    chunks: list[str],
    *,
    strategy: str,
    current_pattern: str,
    target_patterns: list[str],
    target_line_count: int,
    threshold: int,
) -> float:
    if not chunks:
        return float("-inf")
    pattern = line_break_pattern_for_text("\n".join(chunks))
    line_lengths = [max(1, _split_visible_len(chunk)) for chunk in chunks if str(chunk).strip()]
    if not line_lengths:
        return float("-inf")
    try:
        from core.native_swift_subtitle_lora_merge import lora_packaging_candidate_score_via_swift

        native = lora_packaging_candidate_score_via_swift(
            line_lengths=line_lengths,
            pattern=pattern,
            strategy=strategy,
            current_pattern=current_pattern,
            target_patterns=target_patterns,
            target_line_count=target_line_count,
            threshold=threshold,
        )
        if native is not None:
            return native
    except Exception:
        pass

    max_line = max(line_lengths)
    min_line = min(line_lengths)
    score = 0.0
    if target_patterns:
        if pattern == target_patterns[0]:
            score += 240.0
        elif pattern in target_patterns:
            score += 180.0
    if target_line_count > 0:
        score += max(0.0, 48.0 - abs(len(chunks) - target_line_count) * 20.0)
    if strategy == "lora_ground_truth_line_break":
        score += 30.0
    elif strategy == "lora_line_count":
        score += 18.0
    elif strategy == "balanced":
        score += 8.0
    elif strategy == "rule_greedy":
        score += 4.0
    overflow = max(0, max_line - max(1, threshold))
    score -= float(overflow) * 10.0
    if len(chunks) > 2:
        score -= float(len(chunks) - 2) * 24.0
    score -= float(max_line - min_line) * 0.6
    if len(chunks) >= 2:
        score += 6.0
    if pattern == current_pattern:
        score -= 6.0
    return score


def _apply_lora_card_packaging(
    segments: list[dict],
    settings: dict | None,
    rules: dict | None,
    *,
    stage: str,
) -> list[dict]:
    if not segments or not _bool_setting(settings or {}, "subtitle_lora_packaging_enabled", False):
        return segments
    mode = _lora_packaging_mode(settings)
    rows: list[dict] = []
    changed = 0
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        row = dict(seg)
        text = _normalize_subtitle_text_lines(str(row.get("text", "") or ""))
        if not text:
            rows.append(row)
            continue
        allow_multiline = _segment_has_multi_speaker_linebreak_permission(row)
        if not allow_multiline:
            single_line_text = " ".join(_subtitle_text_lines(text))
            if single_line_text and single_line_text != text:
                row["text"] = single_line_text
                row["_lora_packaging_policy"] = {
                    "task": "lora_card_packaging",
                    "stage": stage,
                    "mode": mode,
                    "strategy": "single_line_enforced",
                    "reason": "single_speaker_no_line_break",
                }
                changed += 1
            rows.append(row)
            continue
        row_settings = {**dict(settings or {}), **dict(row.get("_lora_segment_settings") or {})}
        if row.get("_lora_generation_profile"):
            row_settings["_lora_generation_profile"] = row.get("_lora_generation_profile")
        reasons = _lora_packaging_reasons(row, row_settings)
        if mode == "readability_selective" and not reasons:
            rows.append(row)
            continue
        threshold = max(8, _setting_int(row_settings, "split_length_threshold", 20))
        candidates = build_llm_candidate_options(text, threshold, rules or {}, row_settings)
        current_chunks = _subtitle_text_lines(text)
        current_pattern = line_break_pattern_for_text(text)
        target_patterns = _packaging_target_patterns(row_settings)
        target_line_count = max(0, _setting_int(row_settings, "subtitle_target_line_count", 0))
        best_chunks = list(current_chunks)
        best_strategy = "current"
        best_score = _packaging_candidate_score(
            best_chunks,
            strategy=best_strategy,
            current_pattern=current_pattern,
            target_patterns=target_patterns,
            target_line_count=target_line_count,
            threshold=threshold,
        )
        for candidate in list(candidates or []):
            chunks = [str(chunk).strip() for chunk in list(candidate.get("chunks") or []) if str(chunk).strip()]
            if not chunks:
                continue
            candidate_text = "\n".join(chunks)
            if re.sub(r"\s+", "", candidate_text) != re.sub(r"\s+", "", text):
                continue
            score = _packaging_candidate_score(
                chunks,
                strategy=str(candidate.get("strategy") or ""),
                current_pattern=current_pattern,
                target_patterns=target_patterns,
                target_line_count=target_line_count,
                threshold=threshold,
            )
            if score > best_score + 1e-6:
                best_chunks = list(chunks)
                best_strategy = str(candidate.get("strategy") or "")
                best_score = score
        packaged_text = "\n".join(best_chunks)
        if packaged_text != text:
            row["text"] = packaged_text
            row["_lora_packaging_policy"] = {
                "task": "lora_card_packaging",
                "stage": stage,
                "mode": mode,
                "strategy": best_strategy,
                "reasons": list(reasons),
                "target_line_count": target_line_count,
                "target_patterns": list(target_patterns[:3]),
                "before_pattern": current_pattern,
                "after_pattern": line_break_pattern_for_text(packaged_text),
            }
            changed += 1
        rows.append(row)
    if changed > 0:
        get_logger().log(f"[LoRA자막포장] {stage}: timing 유지 + 줄바꿈/카드 포장 {changed}개 조정")
    return rows


def _segment_has_multi_speaker_linebreak_permission(row: dict) -> bool:
    speakers = [
        str(item).strip()
        for item in list(row.get("speaker_list") or [])
        if str(item).strip()
    ]
    return len(set(speakers)) >= 2


def _canonical_speaker_id(value) -> str:
    speaker = str(value or "").strip()
    if speaker.startswith("SPEAKER_"):
        speaker = speaker.replace("SPEAKER_", "", 1)
    return speaker


def _speaker_values_from_row(row: dict | None) -> list[str]:
    if not isinstance(row, dict):
        return []
    values: list[str] = []
    for item in list(row.get("speaker_list") or []):
        speaker = _canonical_speaker_id(item)
        if speaker:
            values.append(speaker)
    for key in ("speaker", "speaker2", "spk", "spk_id"):
        speaker = _canonical_speaker_id(row.get(key))
        if speaker:
            values.append(speaker)
    out: list[str] = []
    seen: set[str] = set()
    for speaker in values:
        if speaker in seen:
            continue
        seen.add(speaker)
        out.append(speaker)
        if len(out) >= 2:
            break
    return out


def _stt_text_has_speaker_marker(text: str) -> bool:
    raw = str(text or "").replace("\u2028", "\n").strip()
    if not raw:
        return False
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) >= 2 and all(line.startswith("-") for line in lines[:2]):
        return True
    compact = re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()
    if not compact.startswith("-"):
        return False
    return len(re.findall(r"(?:^|\s)-\s*[^-\s]", compact)) >= 2


def _stt_decision_speaker_fields(row: dict | None, fallback: dict | None = None) -> dict:
    speakers = _speaker_values_from_row(row)
    if not speakers:
        speakers = _speaker_values_from_row(fallback)
    fields: dict = {}
    if speakers:
        fields["speaker"] = speakers[0]
        fields["speaker_list"] = speakers
        if len(speakers) >= 2:
            fields["speaker2"] = speakers[1]
    text = str((row or {}).get("text", "") or "")
    if _stt_text_has_speaker_marker(text) or len(set(speakers)) >= 2:
        fields["_stt_speaker_marker_preserved"] = True
    return fields


def _find_matching_stt_candidate_for_decision(seg: dict, decision: dict) -> dict | None:
    decision_text = re.sub(r"\s+", "", str((decision or {}).get("text", "") or "")).strip().lower()
    decision_source = str((decision or {}).get("source", "") or "").strip().upper()
    if not decision_text:
        return None
    best: dict | None = None
    best_score = -1
    for candidate in list((seg or {}).get("stt_candidates") or []):
        if not isinstance(candidate, dict):
            continue
        cand_text = re.sub(r"\s+", "", str(candidate.get("text", "") or "")).strip().lower()
        if not cand_text:
            continue
        cand_source = str(candidate.get("source", "") or "").strip().upper()
        score = 0
        if cand_text == decision_text:
            score += 4
        elif decision_text in cand_text or cand_text in decision_text:
            score += 2
        if decision_source and cand_source == decision_source:
            score += 1
        if score > best_score:
            best = candidate
            best_score = score
    return best if best_score >= 2 else None


def _is_speaker_split_multiline_segment(row: dict) -> bool:
    lines = _subtitle_text_lines(str(row.get("text", "") or ""))
    if len(lines) <= 1:
        return False
    return _segment_has_multi_speaker_linebreak_permission(row)


def _clear_split_timing_projection_fields(row: dict) -> None:
    for key in (
        "timeline_start",
        "timeline_end",
        "timeline_start_frame",
        "timeline_end_frame",
        "start_frame",
        "end_frame",
        "frame_range",
    ):
        row.pop(key, None)


def _multiline_word_groups_for_lines(row: dict, lines: list[str]) -> list[list[dict]] | None:
    words = [
        dict(word)
        for word in list(row.get("words") or [])
        if isinstance(word, dict) and str(word.get("word", "") or "").strip()
    ]
    if len(words) < len(lines):
        return None

    targets = [max(1, _split_visible_len(line)) for line in lines]
    groups: list[list[dict]] = []
    cursor = 0
    for idx, target in enumerate(targets):
        remaining_lines = len(targets) - idx
        remaining_words = len(words) - cursor
        if remaining_words < remaining_lines:
            return None
        if idx == len(targets) - 1:
            groups.append(words[cursor:])
            break

        group: list[dict] = []
        char_count = 0
        while cursor < len(words):
            remaining_words = len(words) - cursor
            if group and remaining_words <= remaining_lines - 1:
                break
            word = words[cursor]
            group.append(word)
            char_count += max(1, _split_visible_len(str(word.get("word", "") or "")))
            cursor += 1
            remaining_words = len(words) - cursor
            if char_count >= target and remaining_words >= remaining_lines - 1:
                break
        if not group:
            return None
        groups.append(group)
    if len(groups) != len(lines) or any(not group for group in groups):
        return None
    return groups


def _multiline_split_boundaries_from_groups(
    start: float,
    end: float,
    groups: list[list[dict]],
) -> list[float] | None:
    if len(groups) <= 1:
        return []
    boundaries: list[float] = []
    min_duration = 0.05
    for idx in range(len(groups) - 1):
        left = groups[idx]
        right = groups[idx + 1]
        try:
            left_end = float(left[-1].get("end", left[-1].get("start", start)) or start)
            right_start = float(right[0].get("start", left_end) or left_end)
        except Exception:
            return None
        if right_start >= left_end:
            boundary = (left_end + right_start) / 2.0
        else:
            boundary = max(left_end, right_start)
        min_boundary = start + min_duration * (idx + 1)
        max_boundary = end - min_duration * (len(groups) - idx - 1)
        boundary = max(min_boundary, min(max_boundary, boundary))
        boundaries.append(boundary)
    if any(boundaries[idx] <= boundaries[idx - 1] for idx in range(1, len(boundaries))):
        return None
    return boundaries


def _multiline_split_boundaries_from_weights(
    start: float,
    end: float,
    lines: list[str],
) -> list[float]:
    if len(lines) <= 1:
        return []
    weights = [max(1, _split_visible_len(line)) for line in lines]
    total_weight = max(1, sum(weights))
    min_duration = 0.05
    duration = max(float(end) - float(start), min_duration * len(lines))
    boundaries: list[float] = []
    consumed = 0
    for idx, weight in enumerate(weights[:-1]):
        consumed += weight
        proposed = start + duration * (consumed / total_weight)
        min_boundary = start + min_duration * (idx + 1)
        max_boundary = end - min_duration * (len(lines) - idx - 1)
        boundaries.append(max(min_boundary, min(max_boundary, proposed)))
    return boundaries


def _expand_non_speaker_multiline_segments(
    segments: list[dict],
    settings: dict | None = None,
) -> list[dict]:
    rows: list[dict] = []
    flattened_segments = 0
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        row = dict(seg)
        lines = _subtitle_text_lines(str(row.get("text", "") or ""))
        if len(lines) <= 1 or _is_speaker_split_multiline_segment(row):
            row["text"] = "\n".join(lines) if lines else str(row.get("text", "") or "").strip()
            rows.append(row)
            continue
        row["text"] = " ".join(lines)
        row.pop("words", None)
        policy = dict(row.get("_lora_packaging_policy") or {})
        policy.update(
            {
                "task": "lora_card_packaging",
                "output_mode": "single_line_flatten",
                "reason": "single_speaker_no_line_break",
            }
        )
        row["_lora_packaging_policy"] = policy
        rows.append(row)
        flattened_segments += 1

    if flattened_segments > 0:
        get_logger().log(f"[자막줄정리] 일반 줄바꿈 자막 {flattened_segments}개를 한 줄로 정리")
    return rows
