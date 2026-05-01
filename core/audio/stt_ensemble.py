# Version: 03.04.01
# Phase: PHASE2
"""STT ensemble helpers for merging two Whisper transcripts."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


_KO_RE = re.compile(r"[가-힣]")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def compact_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or ""), flags=re.UNICODE).lower()


def text_similarity(left: str, right: str) -> float:
    ltxt = compact_text(left)
    rtxt = compact_text(right)
    if not ltxt and not rtxt:
        return 1.0
    if not ltxt or not rtxt:
        return 0.0
    return SequenceMatcher(None, ltxt, rtxt).ratio()


def overlap_ratio(left: dict, right: dict) -> float:
    start = max(_as_float(left.get("start")), _as_float(right.get("start")))
    end = min(_as_float(left.get("end")), _as_float(right.get("end")))
    overlap = max(0.0, end - start)
    span = max(
        _as_float(left.get("end")) - _as_float(left.get("start")),
        _as_float(right.get("end")) - _as_float(right.get("start")),
        0.001,
    )
    return overlap / span


def candidate_score(segment: dict) -> float:
    text = normalize_text(segment.get("text", ""))
    compact = compact_text(text)
    if not compact:
        return -999.0
    duration = max(0.05, _as_float(segment.get("end")) - _as_float(segment.get("start")))
    ko_ratio = len(_KO_RE.findall(text)) / max(1, len(compact))
    length_score = min(len(compact), 42) / 42.0
    cps = len(compact) / duration
    cps_penalty = max(0.0, cps - 18.0) * 0.04

    avg_logprob = segment.get("avg_logprob")
    logprob_score = 0.0
    if avg_logprob is not None:
        logprob_score = max(-2.5, min(0.0, _as_float(avg_logprob))) / 2.5 + 1.0

    no_speech = max(0.0, min(1.0, _as_float(segment.get("no_speech_prob"), 0.0)))
    compression = _as_float(segment.get("compression_ratio"), 1.0)
    compression_penalty = max(0.0, compression - 2.2) * 0.15

    word_conf = segment.get("word_confidence")
    word_score = 0.0
    if word_conf is not None:
        word_score = max(0.0, min(1.0, _as_float(word_conf)))
    elif segment.get("words"):
        word_score = 0.25

    return (
        length_score * 1.2
        + ko_ratio * 0.9
        + logprob_score * 0.8
        + word_score * 0.6
        - no_speech * 0.9
        - cps_penalty
        - compression_penalty
    )


def _candidate_payload(source: str, segment: dict) -> dict:
    return {
        "source": source,
        "text": normalize_text(segment.get("text", "")),
        "start": round(_as_float(segment.get("start")), 3),
        "end": round(_as_float(segment.get("end")), 3),
        "score": round(candidate_score(segment), 4),
        "avg_logprob": segment.get("avg_logprob"),
        "no_speech_prob": segment.get("no_speech_prob"),
        "compression_ratio": segment.get("compression_ratio"),
    }


def _pick_best(candidates: list[tuple[str, dict]]) -> tuple[str, dict]:
    return max(candidates, key=lambda item: candidate_score(item[1]))


def _merge_group(candidates: list[tuple[str, dict]]) -> dict:
    source, selected = _pick_best(candidates)
    group_segments = [seg for _, seg in candidates]
    merged = dict(selected)
    merged["start"] = min(_as_float(seg.get("start")) for seg in group_segments)
    merged["end"] = max(_as_float(seg.get("end")) for seg in group_segments)
    merged["text"] = normalize_text(selected.get("text", ""))
    merged["stt_ensemble_source"] = source
    merged["stt_candidates"] = [_candidate_payload(src, seg) for src, seg in candidates]
    merged["stt_ensemble_similarity"] = (
        text_similarity(candidates[0][1].get("text", ""), candidates[1][1].get("text", ""))
        if len(candidates) == 2 else 1.0
    )
    return merged


def _merge_primary_group(primary_item: tuple[str, dict], candidates: list[tuple[str, dict]]) -> dict:
    _source, primary = primary_item
    merged = dict(primary)
    merged["start"] = round(_as_float(primary.get("start")), 3)
    merged["end"] = round(_as_float(primary.get("end")), 3)
    merged["text"] = normalize_text(primary.get("text", ""))
    merged["stt_ensemble_source"] = "STT1"
    merged["stt_ensemble_primary_locked"] = True
    merged["stt_candidates"] = [_candidate_payload(src, seg) for src, seg in candidates]
    merged["stt_ensemble_similarity"] = (
        text_similarity(candidates[0][1].get("text", ""), candidates[1][1].get("text", ""))
        if len(candidates) == 2 else 1.0
    )
    return merged


def _secondary_has_primary_coverage(secondary: dict, primary_items: list[tuple[str, dict]]) -> bool:
    s_start = _as_float(secondary.get("start"))
    s_end = _as_float(secondary.get("end"))
    s_dur = max(0.05, s_end - s_start)
    for _src, primary in primary_items:
        p_start = _as_float(primary.get("start"))
        p_end = _as_float(primary.get("end"))
        overlap = max(0.0, min(p_end, s_end) - max(p_start, s_start))
        if overlap >= min(0.25, s_dur * 0.45):
            return True
        if overlap_ratio(primary, secondary) >= 0.15:
            return True
        if abs(p_start - s_start) <= 0.8 and text_similarity(primary.get("text", ""), secondary.get("text", "")) >= 0.2:
            return True
    return False


def _primary_overlap_seconds(segment: dict, primary_items: list[tuple[str, dict]]) -> float:
    s_start = _as_float(segment.get("start"))
    s_end = _as_float(segment.get("end"))
    total = 0.0
    for _src, primary in primary_items:
        p_start = _as_float(primary.get("start"))
        p_end = _as_float(primary.get("end"))
        total += max(0.0, min(p_end, s_end) - max(p_start, s_start))
    return total


def _is_safe_secondary_insert(secondary: dict, primary_items: list[tuple[str, dict]]) -> bool:
    text = normalize_text(secondary.get("text", ""))
    if not text:
        return False
    s_start = _as_float(secondary.get("start"))
    s_end = _as_float(secondary.get("end"))
    s_dur = max(0.0, s_end - s_start)
    if s_dur < 0.28:
        return False
    overlap = _primary_overlap_seconds(secondary, primary_items)
    if overlap > min(0.18, s_dur * 0.12):
        return False
    if candidate_score(secondary) < 0.15:
        return False
    return not _secondary_has_primary_coverage(secondary, primary_items)


def _clip_secondary_to_primary_gaps(segment: dict, primary_items: list[tuple[str, dict]]) -> dict | None:
    cur = dict(segment)
    start = _as_float(cur.get("start"))
    end = _as_float(cur.get("end"))
    for _src, primary in sorted(primary_items, key=lambda item: _as_float(item[1].get("start"))):
        p_start = _as_float(primary.get("start"))
        p_end = _as_float(primary.get("end"))
        if p_end <= start or p_start >= end:
            continue
        left_span = max(0.0, p_start - start)
        right_span = max(0.0, end - p_end)
        if left_span >= right_span and left_span >= 0.28:
            end = p_start
        elif right_span >= 0.28:
            start = p_end
        else:
            return None
    if end - start < 0.28:
        return None
    cur["start"] = round(start, 3)
    cur["end"] = round(end, 3)
    return cur


def _resolve_overlaps_preserving_primary(segments: list[dict], primary_items: list[tuple[str, dict]]) -> list[dict]:
    resolved: list[dict] = []
    primary_refs = primary_items
    for segment in sorted(segments, key=lambda seg: (_as_float(seg.get("start")), _as_float(seg.get("end")))):
        is_primary = bool(segment.get("stt_ensemble_primary_locked")) or segment.get("stt_ensemble_source") == "STT1"
        item = dict(segment)
        if not is_primary:
            clipped = _clip_secondary_to_primary_gaps(item, primary_refs)
            if clipped is None:
                continue
            item = clipped
        if resolved and _as_float(resolved[-1].get("end")) > _as_float(item.get("start")):
            prev = resolved[-1]
            prev_is_primary = bool(prev.get("stt_ensemble_primary_locked")) or prev.get("stt_ensemble_source") == "STT1"
            if prev_is_primary and is_primary:
                item["start"] = max(_as_float(item.get("start")), _as_float(prev.get("end")) + 0.01)
            elif prev_is_primary:
                item["start"] = max(_as_float(item.get("start")), _as_float(prev.get("end")) + 0.01)
            elif is_primary:
                prev["end"] = min(_as_float(prev.get("end")), _as_float(item.get("start")) - 0.01)
            else:
                midpoint = (_as_float(prev.get("end")) + _as_float(item.get("start"))) / 2.0
                prev["end"] = max(_as_float(prev.get("start")) + 0.05, min(_as_float(prev.get("end")), midpoint))
                item["start"] = max(_as_float(item.get("start")), _as_float(prev.get("end")) + 0.01)
        if _as_float(item.get("end")) <= _as_float(item.get("start")):
            if is_primary:
                item["end"] = _as_float(item.get("start")) + 0.2
            else:
                continue
        if resolved and _as_float(resolved[-1].get("end")) <= _as_float(resolved[-1].get("start")):
            resolved.pop()
        resolved.append(item)
    return resolved


def merge_stt_outputs(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """Merge STT outputs with STT1 as the authoritative transcript.

    STT2 is kept as a candidate for overlapping STT1 segments, but it does not
    replace STT1 text/timing. Only STT2-only regions that STT1 appears to have
    missed are inserted as additional subtitles.
    """
    primary_items = [("STT1", dict(seg)) for seg in primary if normalize_text(seg.get("text", ""))]
    secondary_items = [("STT2", dict(seg)) for seg in secondary if normalize_text(seg.get("text", ""))]
    if not primary_items:
        return [_merge_group([item]) for item in secondary_items]
    if not secondary_items:
        return [_merge_group([item]) for item in primary_items]

    used_secondary: set[int] = set()
    groups: list[dict] = []
    for p_src, p_seg in primary_items:
        best_idx = None
        best_score = 0.0
        for idx, (s_src, s_seg) in enumerate(secondary_items):
            if idx in used_secondary:
                continue
            temporal = overlap_ratio(p_seg, s_seg)
            start_gap = abs(_as_float(p_seg.get("start")) - _as_float(s_seg.get("start")))
            textual = text_similarity(p_seg.get("text", ""), s_seg.get("text", ""))
            score = temporal * 0.7 + textual * 0.3
            if start_gap <= 1.2 and score > best_score:
                best_idx = idx
                best_score = score
        if best_idx is not None and best_score >= 0.25:
            used_secondary.add(best_idx)
            groups.append(_merge_primary_group((p_src, p_seg), [(p_src, p_seg), secondary_items[best_idx]]))
        else:
            groups.append(_merge_primary_group((p_src, p_seg), [(p_src, p_seg)]))

    for idx, item in enumerate(secondary_items):
        if idx in used_secondary:
            continue
        if not _is_safe_secondary_insert(item[1], primary_items):
            continue
        inserted = _merge_group([item])
        inserted["stt_ensemble_inserted_from_stt2"] = True
        inserted["stt_ensemble_needs_llm_review"] = True
        groups.append(inserted)

    return _resolve_overlaps_preserving_primary(groups, primary_items)
