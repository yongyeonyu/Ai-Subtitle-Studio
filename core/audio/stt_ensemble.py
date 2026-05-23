# Version: 03.05.04
# Phase: PHASE2
"""STT ensemble helpers for merging two Whisper transcripts."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
import re
from typing import Any

from core.audio.stt_candidate_scorer import score_stt_candidate, stt_score_label, stt_score_to_color
from core.native_text_similarity import similarity_ratio


_KO_RE = re.compile(r"[가-힣]")
_KNOWN_HALLUCINATION_RE = re.compile(
    r"(시청해주셔서|구독|좋아요|알림설정|자막제공|감사합니다|안녕히계세요)",
    re.IGNORECASE,
)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_candidate_text(segment: dict) -> str:
    raw = str((segment or {}).get("text", "") or "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.replace("\u2028", "\n").splitlines()]
    lines = [line for line in lines if line]
    if len(lines) >= 2 and sum(1 for line in lines[:2] if line.startswith("-")) >= 2:
        return "\n".join(lines)
    return normalize_text(raw)


def _speaker_list_from_segment(segment: dict) -> list[str]:
    values: list[str] = []
    for item in list((segment or {}).get("speaker_list") or []):
        text = str(item or "").strip()
        if text:
            values.append(text)
    for key in ("speaker", "speaker2", "spk", "spk_id"):
        text = str((segment or {}).get(key) or "").strip()
        if text:
            values.append(text)
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= 2:
            break
    return out


def compact_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or ""), flags=re.UNICODE).lower()


def _repeat_risk(text: str) -> bool:
    compact = compact_text(text)
    if len(compact) < 6:
        return False
    if _KNOWN_HALLUCINATION_RE.search(str(text or "")):
        return True
    if re.search(r"(.{2,6})\1{2,}", compact):
        return True
    tokens = [tok for tok in re.split(r"\s+", normalize_text(text)) if tok]
    if len(tokens) >= 5:
        unique_ratio = len(set(tokens)) / max(1, len(tokens))
        if unique_ratio <= 0.45:
            return True
    return False


def text_similarity(left: str, right: str) -> float:
    ltxt = compact_text(left)
    rtxt = compact_text(right)
    if not ltxt and not rtxt:
        return 1.0
    if not ltxt or not rtxt:
        return 0.0
    return similarity_ratio(ltxt, rtxt)


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


def _build_start_index(items: list[tuple[str, dict]]) -> tuple[list[float], list[tuple[float, int, tuple[str, dict]]]]:
    indexed = sorted(
        ((_as_float(item[1].get("start")), index, item) for index, item in enumerate(items)),
        key=lambda entry: (entry[0], entry[1]),
    )
    return [entry[0] for entry in indexed], indexed


def _matching_secondary_candidates(
    primary: dict,
    secondary_items: list[tuple[str, dict]],
    secondary_starts: list[float],
    secondary_index: list[tuple[float, int, tuple[str, dict]]],
    *,
    start_gap_sec: float = 1.2,
) -> list[tuple[int, tuple[str, dict]]]:
    if not secondary_items:
        return []
    p_start = _as_float(primary.get("start"))
    lo = bisect_left(secondary_starts, p_start - start_gap_sec)
    hi = bisect_right(secondary_starts, p_start + start_gap_sec)
    if lo >= hi:
        return []
    return sorted(((index, item) for _start, index, item in secondary_index[lo:hi]), key=lambda entry: entry[0])


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


def _normalize_score_100(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score <= 1.0:
        score *= 100.0
    return max(0.0, min(100.0, score))


def _candidate_score_100(segment: dict) -> float:
    for key in ("stt_score", "score", "confidence", "probability", "avg_confidence"):
        score = _normalize_score_100(segment.get(key))
        if score is not None:
            return score
    return float(score_stt_candidate(segment).get("score", 0.0) or 0.0)


def _candidate_usable(segment: dict) -> bool:
    score = _candidate_score_100(segment)
    explicit_score = any(segment.get(key) is not None for key in ("stt_score", "score", "confidence", "probability", "avg_confidence"))
    if explicit_score and score < 24.0:
        return False
    flags = set(str(flag) for flag in (segment.get("stt_score_flags") or []))
    if flags.intersection({"known_hallucination_phrase", "repetition_hallucination_risk", "severe_hallucination_risk"}) and score < 68.0:
        return False
    return bool(normalize_text(segment.get("text", "")))


def _word_text(word: dict) -> str:
    return normalize_text(word.get("word") or word.get("text") or "")


def _word_confidence(word: dict, fallback: float = 0.0) -> float:
    for key in ("confidence", "probability", "score"):
        if word.get(key) is not None:
            return max(0.0, min(1.0, _as_float(word.get(key))))
    return fallback


def _segment_quality_flags(segment: dict) -> set[str]:
    flags: set[str] = set()
    avg_logprob = segment.get("avg_logprob")
    if avg_logprob is not None and _as_float(avg_logprob) <= -0.85:
        flags.add("low_avg_logprob")
    no_speech = segment.get("no_speech_prob")
    if no_speech is not None and _as_float(no_speech) >= 0.35:
        flags.add("high_no_speech_prob")
    compression = segment.get("compression_ratio")
    if compression is not None and _as_float(compression) >= 2.35:
        flags.add("high_compression_ratio")
    text = compact_text(segment.get("text", ""))
    duration = max(0.05, _as_float(segment.get("end")) - _as_float(segment.get("start")))
    if text and len(text) / duration > 20.0:
        flags.add("too_fast_text")
    if _repeat_risk(segment.get("text", "")):
        flags.add("repeated_or_known_hallucination")
    if candidate_score(segment) < 0.45:
        flags.add("low_candidate_score")
    return flags


def _segment_is_low_confidence(segment: dict) -> bool:
    flags = _segment_quality_flags(segment)
    return bool(flags.intersection({"low_avg_logprob", "high_no_speech_prob", "high_compression_ratio", "too_fast_text", "repeated_or_known_hallucination"})) or len(flags) >= 2


def _secondary_is_safe_for_promotion(segment: dict) -> bool:
    flags = _segment_quality_flags(segment)
    if "repeated_or_known_hallucination" in flags:
        return False
    if "high_no_speech_prob" in flags or "high_compression_ratio" in flags:
        return False
    explicit_score = any(segment.get(key) is not None for key in ("stt_score", "score", "confidence", "probability", "avg_confidence"))
    threshold = 62.0 if explicit_score else 8.0
    return _candidate_score_100(segment) >= threshold


def _protected_word(text: str) -> bool:
    compact = compact_text(text)
    if not compact:
        return True
    if any(ch.isdigit() for ch in compact):
        return True
    if len(compact) <= 1:
        return True
    if re.search(r"[A-Z]{2,}", str(text or "")):
        return True
    return False


def _words_from_segment(segment: dict) -> list[dict]:
    words: list[dict] = []
    raw_words = segment.get("words") or []
    for raw in raw_words:
        if not isinstance(raw, dict):
            continue
        text = _word_text(raw)
        if not text:
            continue
        start = _as_float(raw.get("start"), _as_float(segment.get("start")))
        end = _as_float(raw.get("end"), start)
        if end < start:
            end = start
        item = dict(raw)
        item["word"] = text
        item["start"] = round(start, 3)
        item["end"] = round(end, 3)
        words.append(item)
    if words:
        return words

    text_words = [w for w in re.split(r"\s+", normalize_text(segment.get("text", ""))) if w]
    if not text_words:
        return []
    start = _as_float(segment.get("start"))
    end = max(start + 0.05, _as_float(segment.get("end"), start + 0.05))
    step = (end - start) / max(1, len(text_words))
    for idx, text in enumerate(text_words):
        words.append({
            "word": text,
            "start": round(start + step * idx, 3),
            "end": round(start + step * (idx + 1), 3),
            "synthetic": True,
        })
    return words


def _word_time_score(left: dict, right: dict) -> float:
    start = max(_as_float(left.get("start")), _as_float(right.get("start")))
    end = min(_as_float(left.get("end")), _as_float(right.get("end")))
    overlap = max(0.0, end - start)
    span = max(
        _as_float(left.get("end")) - _as_float(left.get("start")),
        _as_float(right.get("end")) - _as_float(right.get("start")),
        0.05,
    )
    overlap_score = overlap / span
    l_mid = (_as_float(left.get("start")) + _as_float(left.get("end"))) / 2.0
    r_mid = (_as_float(right.get("start")) + _as_float(right.get("end"))) / 2.0
    midpoint_score = max(0.0, 1.0 - abs(l_mid - r_mid) / 0.75)
    return max(overlap_score, midpoint_score * 0.75)


def _word_score(word: dict, parent: dict, *, source: str, parent_low_confidence: bool) -> float:
    score = _word_confidence(word, 0.45 if word.get("synthetic") else 0.55)
    parent_score = max(-1.0, min(2.5, candidate_score(parent))) / 3.5 + 0.3
    score += parent_score * 0.25
    if not parent_low_confidence:
        score += 0.04
    if word.get("synthetic"):
        score -= 0.12
    return score


def _find_matching_word(primary_word: dict, secondary_words: list[dict], used: set[int]) -> tuple[int | None, float]:
    best_idx = None
    best_score = 0.0
    for idx, secondary_word in enumerate(secondary_words):
        if idx in used:
            continue
        temporal = _word_time_score(primary_word, secondary_word)
        textual = text_similarity(_word_text(primary_word), _word_text(secondary_word))
        score = temporal * 0.58 + textual * 0.42
        if score > best_score:
            best_idx = idx
            best_score = score
    if best_score < 0.36:
        return None, best_score
    return best_idx, best_score


def _join_words(words: list[dict]) -> str:
    return normalize_text(" ".join(_word_text(w) for w in words if _word_text(w)))


def _has_protected_primary_mismatch(primary: dict, secondary: dict) -> bool:
    primary_words = _words_from_segment(primary)
    secondary_words = _words_from_segment(secondary)
    if not primary_words or not secondary_words:
        return False
    used: set[int] = set()
    for primary_word in primary_words:
        p_text = _word_text(primary_word)
        if not _protected_word(p_text):
            continue
        match_idx, match_score = _find_matching_word(primary_word, secondary_words, used)
        if match_idx is None:
            continue
        used.add(match_idx)
        s_text = _word_text(secondary_words[match_idx])
        if match_score >= 0.36 and text_similarity(p_text, s_text) < 0.72:
            return True
    return False


def _word_level_rover(primary: dict, secondary: dict) -> tuple[str, list[dict], dict]:
    primary_words = _words_from_segment(primary)
    secondary_words = _words_from_segment(secondary)
    if not primary_words or not secondary_words:
        return normalize_text(primary.get("text", "")), primary_words, {
            "enabled": False,
            "reason": "word_timestamps_missing",
            "replaced": 0,
            "aligned": 0,
        }

    primary_low = _segment_is_low_confidence(primary)
    secondary_low = _segment_is_low_confidence(secondary)
    used_secondary: set[int] = set()
    selected: list[dict] = []
    replacements = 0
    aligned = 0
    for primary_word in primary_words:
        match_idx, match_score = _find_matching_word(primary_word, secondary_words, used_secondary)
        chosen = dict(primary_word)
        chosen["stt_word_source"] = "STT1"
        if match_idx is not None:
            aligned += 1
            secondary_word = secondary_words[match_idx]
            used_secondary.add(match_idx)
            p_text = _word_text(primary_word)
            s_text = _word_text(secondary_word)
            p_score = _word_score(primary_word, primary, source="STT1", parent_low_confidence=primary_low)
            s_score = _word_score(secondary_word, secondary, source="STT2", parent_low_confidence=primary_low)
            protected = _protected_word(p_text)
            similar = text_similarity(p_text, s_text)
            replace_allowed = (
                not secondary_low
                and s_text
                and similar < 0.98
                and match_score >= 0.42
                and (s_score >= p_score + (0.06 if primary_low else 0.18))
                and (not protected or similar >= 0.72)
            )
            if replace_allowed:
                chosen = dict(secondary_word)
                chosen["stt_word_source"] = "STT2"
                chosen["stt_word_replaced_from"] = p_text
                replacements += 1
        selected.append(chosen)

    text = _join_words(selected) or normalize_text(primary.get("text", ""))
    return text, selected, {
        "enabled": True,
        "replaced": replacements,
        "aligned": aligned,
        "primary_words": len(primary_words),
        "secondary_words": len(secondary_words),
    }


def _candidate_payload(source: str, segment: dict) -> dict:
    score = round(_candidate_score_100(segment), 2)
    score_flags = list(segment.get("stt_score_flags") or [])
    if not score_flags:
        score_flags = sorted(_segment_quality_flags(segment))
    speakers = _speaker_list_from_segment(segment)
    payload = {
        "source": source,
        "text": _normalize_candidate_text(segment),
        "start": round(_as_float(segment.get("start")), 3),
        "end": round(_as_float(segment.get("end")), 3),
        "score": score,
        "stt_score": score,
        "score_color": str(segment.get("score_color") or segment.get("stt_score_color") or stt_score_to_color(score)),
        "stt_score_label": str(segment.get("stt_score_label") or stt_score_label(score)),
        "stt_score_flags": score_flags,
        "stt_score_components": dict(segment.get("stt_score_components") or {}),
        "stt_recheck_applied": bool(segment.get("stt_recheck_applied", False)),
        "stt_recheck_original_scores": dict(segment.get("stt_recheck_original_scores") or {}),
        "avg_logprob": segment.get("avg_logprob"),
        "no_speech_prob": segment.get("no_speech_prob"),
        "compression_ratio": segment.get("compression_ratio"),
        "words": _words_from_segment(segment),
    }
    if speakers:
        payload["speaker"] = speakers[0]
        payload["speaker_list"] = speakers
        if len(speakers) >= 2:
            payload["speaker2"] = speakers[1]
    return payload


def _pick_best(candidates: list[tuple[str, dict]]) -> tuple[str, dict]:
    return max(candidates, key=lambda item: _candidate_score_100(item[1]))


def _duration(segment: dict) -> float:
    return max(0.0, _as_float(segment.get("end")) - _as_float(segment.get("start")))


def _is_near_duplicate_segment(left: dict, right: dict) -> bool:
    left_dur = _duration(left)
    right_dur = _duration(right)
    shorter = min(left_dur, right_dur)
    longer = max(left_dur, right_dur)
    if shorter < 0.28:
        return False
    overlap = max(0.0, min(_as_float(left.get("end")), _as_float(right.get("end"))) - max(_as_float(left.get("start")), _as_float(right.get("start"))))
    if overlap / max(0.05, shorter) < 0.78:
        return False
    if longer / max(0.05, shorter) > 1.45:
        return False
    return text_similarity(left.get("text", ""), right.get("text", "")) >= 0.52


def _prefer_duplicate_candidate(candidate: dict, existing: dict) -> bool:
    cand_score = _candidate_score_100(candidate)
    existing_score = _candidate_score_100(existing)
    cand_quality_depth = _candidate_quality_depth(candidate)
    existing_quality_depth = _candidate_quality_depth(existing)
    if cand_quality_depth > existing_quality_depth and cand_score >= existing_score - 3.0:
        return True
    if existing_quality_depth > cand_quality_depth and existing_score >= cand_score - 3.0:
        return False
    if cand_score > existing_score + 0.5:
        return True
    if existing_score > cand_score + 0.5:
        return False
    cand_dur = _duration(candidate)
    existing_dur = _duration(existing)
    if cand_dur > existing_dur + 0.08:
        return True
    if existing_dur > cand_dur + 0.08:
        return False
    return _as_float(candidate.get("start")) < _as_float(existing.get("start"))


def _candidate_quality_depth(segment: dict) -> int:
    quality = segment.get("quality")
    depth = 0
    if isinstance(quality, dict):
        depth += len([key for key, value in quality.items() if value not in (None, "", [], {})])
        for key in ("asr_metadata_score", "correction_memory_score", "word_timestamp_score", "confidence_score"):
            if quality.get(key) not in (None, ""):
                depth += 2
    if segment.get("avg_logprob") is not None:
        depth += 1
    if segment.get("no_speech_prob") is not None:
        depth += 1
    if segment.get("words"):
        depth += 2
    return depth


def _dedupe_near_duplicate_source_items(items: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    """Collapse same-source near-duplicate rows before cross-STT matching.

    Some persisted STT tracks include both raw and refined rows for the same
    utterance. If both are treated as primary, overlap resolution can trim one
    into a tiny tail and later stages may attach the wrong text to a full slot.
    """
    kept: list[tuple[str, dict]] = []
    for source, segment in sorted(items, key=lambda item: (_as_float(item[1].get("start")), _as_float(item[1].get("end")))):
        duplicate_idx = None
        for idx, (_kept_source, kept_segment) in enumerate(kept):
            if _is_near_duplicate_segment(segment, kept_segment):
                duplicate_idx = idx
                break
        if duplicate_idx is None:
            kept.append((source, segment))
            continue
        if _prefer_duplicate_candidate(segment, kept[duplicate_idx][1]):
            kept[duplicate_idx] = (source, segment)
    return sorted(kept, key=lambda item: (_as_float(item[1].get("start")), _as_float(item[1].get("end"))))


def _covered_primary_duplicate(prev: dict, item: dict) -> bool:
    prev_start = _as_float(prev.get("start"))
    prev_end = _as_float(prev.get("end"))
    item_start = _as_float(item.get("start"))
    item_end = _as_float(item.get("end"))
    item_dur = max(0.05, item_end - item_start)
    overlap = max(0.0, min(prev_end, item_end) - max(prev_start, item_start))
    if overlap / item_dur < 0.65:
        return False
    prev_text = compact_text(prev.get("text", ""))
    item_text = compact_text(item.get("text", ""))
    if not prev_text or not item_text:
        return False
    return item_text in prev_text or prev_text in item_text or text_similarity(prev_text, item_text) >= 0.62


def _merge_group(candidates: list[tuple[str, dict]]) -> dict:
    source, selected = _pick_best(candidates)
    group_segments = [seg for _, seg in candidates]
    merged = dict(selected)
    merged["start"] = min(_as_float(seg.get("start")) for seg in group_segments)
    merged["end"] = max(_as_float(seg.get("end")) for seg in group_segments)
    merged["text"] = _normalize_candidate_text(selected)
    merged["stt_ensemble_source"] = source
    selected_score = _candidate_score_100(selected)
    merged["score"] = round(selected_score, 2)
    merged["stt_score"] = round(selected_score, 2)
    merged["score_color"] = str(selected.get("score_color") or selected.get("stt_score_color") or stt_score_to_color(selected_score))
    merged["stt_candidates"] = [_candidate_payload(src, seg) for src, seg in candidates]
    merged["stt_ensemble_similarity"] = (
        text_similarity(candidates[0][1].get("text", ""), candidates[1][1].get("text", ""))
        if len(candidates) == 2 else 1.0
    )
    return merged


def _merge_primary_group(primary_item: tuple[str, dict], candidates: list[tuple[str, dict]]) -> dict:
    _source, primary = primary_item
    selected_source = "STT1"
    selected_segment = primary
    rover_meta: dict[str, Any] = {"enabled": False, "replaced": 0, "aligned": 0}
    if len(candidates) >= 2:
        secondary = candidates[1][1]
        primary_score = _candidate_score_100(primary)
        secondary_score = _candidate_score_100(secondary)
        similarity = text_similarity(primary.get("text", ""), secondary.get("text", ""))
        primary_low = _segment_is_low_confidence(primary)
        primary_words = _words_from_segment(primary)
        secondary_words = _words_from_segment(secondary)
        has_real_word_timestamps = bool(primary.get("words")) and bool(secondary.get("words"))
        protected_mismatch = _has_protected_primary_mismatch(primary, secondary)
        secondary_safe = _secondary_is_safe_for_promotion(secondary)
        promotion_margin = 4.0 if primary_low else (5.0 if primary_score < 70.0 else 8.0)
        if secondary_safe and has_real_word_timestamps and primary_words and secondary_words and similarity >= 0.20:
            rover_text, rover_words, rover_meta = _word_level_rover(primary, secondary)
            if rover_meta.get("enabled") and rover_meta.get("replaced", 0) > 0:
                selected_source = "ROVER"
                selected_segment = dict(primary)
                selected_segment["text"] = rover_text
                selected_segment["words"] = rover_words
        if (
            selected_source == "STT1"
            and secondary_safe
            and not protected_mismatch
            and secondary_score >= primary_score + promotion_margin
            and similarity >= 0.12
            and (primary_low or not primary_words or not secondary_words or similarity >= 0.42)
        ):
            selected_source = "STT2"
            selected_segment = secondary

    merged = dict(selected_segment)
    if selected_source == "STT1" and selected_segment.get("stt_recheck_applied"):
        selected_source = "RECHECK"
    merged["start"] = round(_as_float(selected_segment.get("start")), 3)
    merged["end"] = round(_as_float(selected_segment.get("end")), 3)
    merged["text"] = _normalize_candidate_text(selected_segment)
    merged["stt_ensemble_source"] = selected_source
    selected_score = _candidate_score_100(selected_segment)
    merged["score"] = round(selected_score, 2)
    merged["stt_score"] = round(selected_score, 2)
    merged["score_color"] = str(selected_segment.get("score_color") or selected_segment.get("stt_score_color") or stt_score_to_color(selected_score))
    merged["stt_ensemble_primary_region"] = True
    merged["stt_ensemble_primary_locked"] = selected_source == "STT1"
    if selected_source != "STT1":
        merged["stt_ensemble_needs_llm_review"] = True
    merged["stt_candidates"] = [_candidate_payload(src, seg) for src, seg in candidates]
    merged["stt_ensemble_quality_flags"] = {
        src: sorted(_segment_quality_flags(seg)) for src, seg in candidates
    }
    if rover_meta.get("enabled"):
        merged["stt_ensemble_word_rover"] = rover_meta
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
    if not _secondary_is_safe_for_promotion(secondary):
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
        is_primary = (
            bool(segment.get("stt_ensemble_primary_region"))
            or bool(segment.get("stt_ensemble_primary_locked"))
            or segment.get("stt_ensemble_source") == "STT1"
        )
        item = dict(segment)
        if not is_primary:
            clipped = _clip_secondary_to_primary_gaps(item, primary_refs)
            if clipped is None:
                continue
            item = clipped
        if resolved and _as_float(resolved[-1].get("end")) > _as_float(item.get("start")):
            prev = resolved[-1]
            prev_is_primary = (
                bool(prev.get("stt_ensemble_primary_region"))
                or bool(prev.get("stt_ensemble_primary_locked"))
                or prev.get("stt_ensemble_source") == "STT1"
            )
            if prev_is_primary and is_primary:
                new_start = max(_as_float(item.get("start")), _as_float(prev.get("end")) + 0.01)
                if _as_float(item.get("end")) - new_start < 0.28 and _covered_primary_duplicate(prev, item):
                    continue
                item["start"] = new_start
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
    """Merge STT outputs with STT1 as the default, not absolute, transcript.

    Overlapping STT1/STT2 segments are scored by quality metadata. When both
    sides provide word timestamps, a conservative ROVER-like pass can replace
    low-confidence STT1 words with stronger STT2 words. STT2-only regions that
    STT1 appears to have missed are still inserted as additional subtitles.
    """
    primary_items = _dedupe_near_duplicate_source_items([("STT1", dict(seg)) for seg in primary if _candidate_usable(seg)])
    secondary_items = _dedupe_near_duplicate_source_items([("STT2", dict(seg)) for seg in secondary if _candidate_usable(seg)])
    if not primary_items:
        return [_merge_group([item]) for item in secondary_items]
    if not secondary_items:
        return [_merge_group([item]) for item in primary_items]

    used_secondary: set[int] = set()
    groups: list[dict] = []
    secondary_starts, secondary_index = _build_start_index(secondary_items)
    for p_src, p_seg in primary_items:
        best_idx = None
        best_score = 0.0
        for idx, (s_src, s_seg) in _matching_secondary_candidates(
            p_seg,
            secondary_items,
            secondary_starts,
            secondary_index,
        ):
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
