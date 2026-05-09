# Version: 03.13.02
# Phase: PHASE2
"""Score STT1/STT2 subtitle candidates on a stable 0-100 scale."""
from __future__ import annotations

from bisect import bisect_left
import re
from typing import Any

from core.native_text_similarity import character_error_rate, similarity_ratio

try:
    from core.native_cut_boundary import interval_overlaps as _native_interval_overlaps
except Exception:  # pragma: no cover - optional native extension.
    _native_interval_overlaps = None

_KO_RE = re.compile(r"[가-힣]")
_LANG_RE = re.compile(r"[가-힣A-Za-z]")
_HARD_HALLUCINATION_RE = re.compile(
    r"(시청해주셔서|구독|좋아요|알림설정|자막제공|광고|subscribe|thanks for watching)",
    re.IGNORECASE,
)
DEFAULT_MIN_STT_KEEP_SCORE = 24.0


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _normalize_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _compact_text(text: Any) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or ""), flags=re.UNICODE).lower()


def _duration(segment: dict[str, Any]) -> float:
    start = _as_float(segment.get("start"), 0.0) or 0.0
    end = _as_float(segment.get("end"), start) or start
    return max(0.0, end - start)


def _metadata(segment: dict[str, Any]) -> dict[str, Any]:
    meta = dict(segment.get("asr_metadata") or {})
    for key in (
        "avg_logprob",
        "compression_ratio",
        "no_speech_prob",
        "temperature",
        "word_confidence",
        "language_probability",
    ):
        if segment.get(key) is not None and meta.get(key) is None:
            meta[key] = segment.get(key)
    if segment.get("words") and not meta.get("words"):
        meta["words"] = segment.get("words")
    return meta


def _add_flag(flags: list[str], value: str) -> None:
    if value and value not in flags:
        flags.append(value)


def _word_confidence(segment: dict[str, Any], meta: dict[str, Any], flags: list[str]) -> float:
    direct = _as_float(meta.get("word_confidence"))
    if direct is not None:
        if direct < 0.42:
            _add_flag(flags, "low_word_confidence")
        return _clip(direct * 100.0)

    words = [dict(w) for w in (segment.get("words") or meta.get("words") or []) if isinstance(w, dict)]
    values: list[float] = []
    for word in words:
        value = _as_float(word.get("confidence", word.get("probability", word.get("score"))))
        if value is not None:
            values.append(_clip(value, 0.0, 1.0))
    if values:
        avg = sum(values) / max(1, len(values))
        if avg < 0.42:
            _add_flag(flags, "low_word_confidence")
        return _clip(avg * 100.0)

    _add_flag(flags, "word_confidence_missing")
    return 40.0 if words else 22.0


def _asr_score(segment: dict[str, Any], flags: list[str]) -> float:
    meta = _metadata(segment)
    score = 66.0

    no_speech = _as_float(meta.get("no_speech_prob"))
    avg_logprob = _as_float(meta.get("avg_logprob"))
    compression = _as_float(meta.get("compression_ratio"))
    language_probability = _as_float(meta.get("language_probability"))

    if no_speech is None:
        _add_flag(flags, "no_speech_prob_missing")
    else:
        score -= max(0.0, no_speech - 0.10) * 84.0
        if no_speech >= 0.58:
            _add_flag(flags, "high_no_speech_prob")

    if avg_logprob is None:
        _add_flag(flags, "avg_logprob_missing")
    else:
        score += _clip((avg_logprob + 1.10) * 18.0, -30.0, 12.0)
        if avg_logprob <= -0.92:
            _add_flag(flags, "low_avg_logprob")

    if compression is not None and compression >= 2.15:
        score -= min(36.0, (compression - 2.15) * 26.0)
        _add_flag(flags, "high_compression_ratio")

    if language_probability is not None and language_probability < 0.62:
        score -= 22.0
        _add_flag(flags, "low_language_probability")

    word_score = _word_confidence(segment, meta, flags)
    score = score * 0.68 + word_score * 0.32
    return _clip(score)


def _timing_score(segment: dict[str, Any], settings: dict[str, Any] | None, flags: list[str]) -> float:
    settings = settings or {}
    duration = _duration(segment)
    text_len = len(_compact_text(segment.get("text")))
    if duration <= 0.0 or text_len <= 0:
        _add_flag(flags, "invalid_timing_or_empty_text")
        return 0.0

    min_duration = float(settings.get("sub_min_duration", 0.2) or 0.2)
    max_duration = float(settings.get("sub_max_duration", 6.0) or 6.0)
    max_cps = float(settings.get("sub_max_cps", 12.0) or 12.0)
    cps = text_len / max(duration, 0.01)
    score = 100.0

    if duration < min_duration:
        score -= min(58.0, (min_duration - duration) * 130.0)
        _add_flag(flags, "too_short_duration")
    if duration > max_duration:
        score -= min(45.0, (duration - max_duration) * 7.0)
        _add_flag(flags, "too_long_duration")
    if cps > max_cps:
        score -= min(55.0, (cps - max_cps) * 5.0)
        _add_flag(flags, "high_cps")
    if cps < 0.45 and text_len >= 3:
        score -= 12.0
        _add_flag(flags, "very_slow_text")

    return _clip(score)


def _repetition_risk(text: str) -> bool:
    compact = _compact_text(text)
    if len(compact) < 6:
        return False
    if re.search(r"(.{2,6})\1{2,}", compact):
        return True
    tokens = [tok for tok in re.split(r"\s+", _normalize_text(text)) if tok]
    if len(tokens) >= 5 and len(set(tokens)) / max(1, len(tokens)) <= 0.45:
        return True
    return False


def _text_score(segment: dict[str, Any], flags: list[str]) -> float:
    text = _normalize_text(segment.get("text"))
    compact = _compact_text(text)
    if not compact:
        _add_flag(flags, "empty_text")
        return 0.0
    if _HARD_HALLUCINATION_RE.search(text):
        _add_flag(flags, "known_hallucination_phrase")
        return 0.0

    score = 80.0
    lang_count = len(_LANG_RE.findall(text))
    ko_count = len(_KO_RE.findall(text))
    lang_ratio = lang_count / max(1, len(compact))
    ko_ratio = ko_count / max(1, len(compact))
    if lang_ratio < 0.55:
        score -= 48.0
        _add_flag(flags, "low_language_char_ratio")
    if ko_ratio < 0.35 and lang_count > 0:
        score -= 18.0
        _add_flag(flags, "low_korean_ratio")
    if len(compact) <= 1:
        score -= 42.0
        _add_flag(flags, "too_short_text")
    if _repetition_risk(text):
        score -= 65.0
        _add_flag(flags, "repetition_hallucination_risk")
    if len(compact) >= 18:
        diversity = len(set(compact)) / max(1, len(compact))
        if diversity <= 0.34:
            score -= 22.0
            _add_flag(flags, "low_character_diversity")
    return _clip(score)


def _overlap_ratio(left: dict[str, Any], right: dict[str, Any]) -> float:
    l_start = _as_float(left.get("start"), 0.0) or 0.0
    l_end = _as_float(left.get("end"), l_start) or l_start
    r_start = _as_float(right.get("start"), 0.0) or 0.0
    r_end = _as_float(right.get("end"), r_start) or r_start
    overlap = max(0.0, min(l_end, r_end) - max(l_start, r_start))
    span = max(0.001, max(l_end - l_start, r_end - r_start))
    return overlap / span


def _segment_bounds(segment: dict[str, Any]) -> tuple[float, float]:
    start = _as_float(segment.get("start"), 0.0) or 0.0
    end = _as_float(segment.get("end"), start) or start
    return float(start), float(end)


def _peer_overlap_windows(
    rows: list[dict[str, Any]],
    peer_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[list[dict[str, Any]]] | None:
    if peer_segments is None:
        return None
    peers: list[tuple[float, float, dict[str, Any]]] = []
    for peer in peer_segments or ():
        if not isinstance(peer, dict):
            continue
        start, end = _segment_bounds(peer)
        if end > start:
            peers.append((start, end, dict(peer)))
    if not peers:
        return [[] for _ in rows]

    peers.sort(key=lambda item: (item[0], item[1]))
    peer_starts = [item[0] for item in peers]
    row_items: list[tuple[float, float, int]] = []
    for index, row in enumerate(rows):
        start, end = _segment_bounds(row)
        if end > start:
            row_items.append((start, end, index))
    row_items.sort(key=lambda item: (item[0], item[1]))

    windows: list[list[dict[str, Any]]] = [[] for _ in rows]
    active: list[tuple[float, float, dict[str, Any]]] = []
    cursor = 0
    for start, end, index in row_items:
        stop = bisect_left(peer_starts, end, lo=cursor)
        if stop > cursor:
            active.extend(peers[cursor:stop])
            cursor = stop
        if active:
            active = [item for item in active if item[1] > start]
        windows[index] = [peer for peer_start, peer_end, peer in active if peer_start < end and peer_end > start]
    return windows


def _text_similarity(left: Any, right: Any) -> float:
    ltxt = _compact_text(left)
    rtxt = _compact_text(right)
    if not ltxt and not rtxt:
        return 1.0
    if not ltxt or not rtxt:
        return 0.0
    sequence_similarity = similarity_ratio(ltxt, rtxt)
    cer_similarity = 1.0 - _character_error_rate(ltxt, rtxt)
    return max(0.0, min(1.0, sequence_similarity * 0.55 + cer_similarity * 0.45))


def _character_error_rate(reference: str, hypothesis: str) -> float:
    return character_error_rate(reference, hypothesis)


def _agreement_score(
    segment: dict[str, Any],
    peer_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    flags: list[str],
) -> float | None:
    best: tuple[float, float, dict[str, Any] | None] = (0.0, 0.0, None)
    for peer in peer_segments or ():
        if not isinstance(peer, dict):
            continue
        temporal = _overlap_ratio(segment, peer)
        if temporal <= 0.0:
            continue
        textual = _text_similarity(segment.get("text"), peer.get("text"))
        score = temporal * 0.38 + textual * 0.62
        if score > best[0]:
            best = (score, textual, peer)
    if best[2] is None:
        _add_flag(flags, "peer_missing")
        return None
    if best[1] < 0.28:
        _add_flag(flags, "peer_text_disagreement")
    return _clip(best[0] * 100.0)


def _vad_score(
    segment: dict[str, Any],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    flags: list[str],
) -> float | None:
    quality = dict(segment.get("quality") or {})
    direct = _as_float(quality.get("vad_alignment_score"))
    if direct is not None:
        if direct < 20.0:
            _add_flag(flags, "outside_vad_speech")
        return _clip(direct)

    meta = _metadata(segment)
    vad_alignment = dict(meta.get("vad_alignment") or {})
    ratio = _as_float(vad_alignment.get("vad_overlap_ratio"))
    if ratio is not None:
        score = _clip(ratio * 100.0)
        if score < 20.0:
            _add_flag(flags, "outside_vad_speech")
        return score

    if not vad_segments:
        return None

    start = _as_float(segment.get("start"), 0.0) or 0.0
    end = _as_float(segment.get("end"), start) or start
    dur = max(0.001, end - start)
    overlap = 0.0
    for vad in vad_segments:
        try:
            v_start = float(vad.get("start", 0.0) or 0.0)
            v_end = float(vad.get("end", v_start) or v_start)
        except Exception:
            continue
        overlap += max(0.0, min(end, v_end) - max(start, v_start))
    score = _clip((overlap / dur) * 100.0)
    if score < 20.0:
        _add_flag(flags, "outside_vad_speech")
    return score


def _native_vad_alignment_infos(
    segments: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]] | None:
    if not callable(_native_interval_overlaps) or not segments or not vad_segments:
        return None

    starts: list[float] = []
    ends: list[float] = []
    durations: list[float] = []
    for segment in segments:
        start = max(0.0, _as_float(segment.get("start"), 0.0) or 0.0)
        end = max(start, _as_float(segment.get("end"), start) or start)
        starts.append(start)
        ends.append(end)
        durations.append(max(0.0, end - start))

    vad_starts: list[float] = []
    vad_ends: list[float] = []
    for vad in vad_segments or ():
        if not isinstance(vad, dict):
            continue
        start = max(0.0, _as_float(vad.get("start"), 0.0) or 0.0)
        end = max(start, _as_float(vad.get("end"), start) or start)
        if end > start:
            vad_starts.append(start)
            vad_ends.append(end)
    if not vad_starts:
        return None

    overlaps = _native_interval_overlaps(starts, ends, vad_starts, vad_ends)
    if overlaps is None or len(overlaps) != len(segments):
        return None

    infos: list[dict[str, Any]] = []
    for duration, overlap in zip(durations, overlaps):
        overlap_value = max(0.0, float(overlap or 0.0))
        if duration <= 0.0:
            infos.append(
                {
                    "vad_overlap_ratio": None,
                    "vad_overlap_sec": 0.0,
                    "vad_duration_sec": 0.0,
                    "vad_aligned": None,
                    "native_backend": "cpp",
                }
            )
            continue
        ratio = round(_clip(overlap_value / duration, 0.0, 1.0), 6)
        infos.append(
            {
                "vad_overlap_ratio": ratio,
                "vad_overlap_sec": round(overlap_value, 6),
                "vad_duration_sec": round(duration, 6),
                "vad_aligned": ratio >= 0.35,
                "native_backend": "cpp",
            }
        )
    return infos


def _attach_native_vad_alignment(row: dict[str, Any], info: dict[str, Any]) -> None:
    ratio = _as_float(info.get("vad_overlap_ratio"))
    asr_metadata = dict(row.get("asr_metadata") or {})
    vad_alignment = dict(asr_metadata.get("vad_alignment") or {})
    if vad_alignment.get("vad_overlap_ratio") is None:
        vad_alignment.update(info)
        asr_metadata["vad_alignment"] = vad_alignment
        row["asr_metadata"] = asr_metadata

    quality = dict(row.get("quality") or {})
    if ratio is None or quality.get("vad_alignment_score") is not None:
        if quality:
            row["quality"] = quality
        return
    quality["vad_alignment_score"] = round(float(ratio) * 100.0, 3)
    flags = list(quality.get("flags") or ())
    if ratio < 0.2 and "outside_vad_speech" not in flags:
        flags.append("outside_vad_speech")
    if flags:
        quality["flags"] = tuple(flags)
    row["quality"] = quality


def stt_score_to_color(score: float | None) -> str:
    value = 50.0 if score is None else _clip(score)
    if value >= 50.0:
        ratio = (value - 50.0) / 50.0
        r = round(255 + (52 - 255) * ratio)
        g = round(204 + (199 - 204) * ratio)
        b = round(0 + (89 - 0) * ratio)
    else:
        ratio = value / 50.0
        r = round(255 + (255 - 255) * ratio)
        g = round(69 + (204 - 69) * ratio)
        b = round(58 + (0 - 58) * ratio)
    return f"#{r:02X}{g:02X}{b:02X}"


def stt_score_label(score: float | None) -> str:
    if score is None:
        return "gray"
    if score <= 0:
        return "unusable"
    if score >= 82:
        return "green"
    if score >= 55:
        return "yellow"
    return "red"


def score_stt_candidate(
    segment: dict[str, Any],
    *,
    source: str = "",
    peer_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    previous_texts: list[str] | tuple[str, ...] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return score metadata for one STT candidate.

    0 means unusable; 100 means very reliable. The function is intentionally
    dependency-light so the pipeline never blocks on optional AI scorers.
    """
    flags: list[str] = []
    text = _normalize_text(segment.get("text"))
    compact = _compact_text(text)
    if not compact:
        return {
            "score": 0.0,
            "label": "unusable",
            "color": stt_score_to_color(0.0),
            "flags": ["empty_text"],
            "components": {},
            "source": str(source or "").strip().upper(),
        }

    asr = _asr_score(segment, flags)
    timing = _timing_score(segment, settings, flags)
    text_component = _text_score(segment, flags)
    vad = _vad_score(segment, vad_segments, flags)
    agreement = _agreement_score(segment, peer_segments, flags) if peer_segments is not None else None

    repetition = 100.0
    for prev in reversed(list(previous_texts or ())[-36:]):
        if _text_similarity(prev, text) >= 0.94 and len(compact) >= 5:
            repetition = 30.0
            _add_flag(flags, "repeated_context_text")
            break

    components: dict[str, float] = {
        "asr": asr,
        "timing": timing,
        "text": text_component,
        "repetition": repetition,
    }
    if vad is not None:
        components["vad"] = vad
    if agreement is not None:
        components["agreement"] = agreement

    weights = {
        "asr": 0.32,
        "timing": 0.18,
        "text": 0.18,
        "repetition": 0.08,
        "vad": 0.12,
        "agreement": 0.22,
    }
    weight_sum = sum(weights[key] for key in components)
    score = sum(components[key] * weights[key] for key in components) / max(weight_sum, 0.001)

    meta = _metadata(segment)
    hallucination = dict(meta.get("hallucination_risk") or {})
    risk = _as_float(hallucination.get("risk"), 0.0) or 0.0
    if risk > 0.0:
        score -= _clip(risk, 0.0, 1.0) * 34.0
        for flag in hallucination.get("flags") or ():
            _add_flag(flags, str(flag))
    if risk >= 0.82 and (vad is None or vad < 35.0 or asr < 55.0):
        score = 0.0
        _add_flag(flags, "severe_hallucination_risk")

    if "repetition_hallucination_risk" in flags and asr < 58.0:
        score = min(score, 24.0)
    if "word_confidence_missing" in flags and agreement is None and asr < 52.0:
        score = min(score, 22.0)

    no_speech = _as_float(meta.get("no_speech_prob"))
    if (
        text_component <= 0.0
        or "known_hallucination_phrase" in flags
        or (no_speech is not None and no_speech >= 0.92 and (vad is None or vad < 8.0))
    ):
        score = 0.0

    if "manual_confirmed" in (dict(segment.get("quality") or {}).get("flags") or ()):
        score = max(score, 98.0)
        _add_flag(flags, "manual_confirmed")

    score = round(_clip(score), 2)
    return {
        "score": score,
        "label": stt_score_label(score),
        "color": stt_score_to_color(score),
        "flags": flags or ["ok"],
        "components": {key: round(float(value), 2) for key, value in components.items()},
        "source": str(source or "").strip().upper(),
    }


def filter_scored_stt_candidates(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    min_score: float = DEFAULT_MIN_STT_KEEP_SCORE,
) -> list[dict[str, Any]]:
    keep: list[dict[str, Any]] = []
    limit = _clip(min_score)
    severe_flags = {
        "known_hallucination_phrase",
        "repetition_hallucination_risk",
        "severe_hallucination_risk",
        "high_no_speech_prob",
        "high_compression_ratio",
    }
    for segment in segments or ():
        if not isinstance(segment, dict):
            continue
        row = dict(segment)
        text = _normalize_text(row.get("text"))
        score = _as_float(row.get("stt_score", row.get("score")), 0.0) or 0.0
        flags = set(str(flag) for flag in (row.get("stt_score_flags") or []))
        quality_flags = set(str(flag) for flag in (dict(row.get("quality") or {}).get("flags") or []))
        if not text or score <= 0.0:
            continue
        if "manual_confirmed" in flags or "manual_confirmed" in quality_flags:
            keep.append(row)
            continue
        if score < limit:
            continue
        if flags.intersection(severe_flags) and score < 68.0:
            continue
        if "outside_vad_speech" in flags and score < 35.0:
            continue
        if "peer_text_disagreement" in flags and "low_word_confidence" in flags and score < 55.0:
            continue
        keep.append(row)
    return keep


def annotate_stt_candidates(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    source: str,
    peer_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    previous: list[str] = []
    source_key = str(source or "").strip().upper() or "STT"
    rows = [dict(segment) for segment in segments or () if isinstance(segment, dict)]
    vad_infos = _native_vad_alignment_infos(rows, vad_segments)
    if vad_infos is not None:
        for row, info in zip(rows, vad_infos):
            _attach_native_vad_alignment(row, info)
    peer_windows = _peer_overlap_windows(rows, peer_segments)

    for index, row in enumerate(rows):
        row_peers = peer_windows[index] if peer_windows is not None else peer_segments
        score = score_stt_candidate(
            row,
            source=source_key,
            peer_segments=row_peers,
            vad_segments=vad_segments,
            previous_texts=previous,
            settings=settings,
        )
        row["score"] = score["score"]
        row["stt_score"] = score["score"]
        row["score_color"] = score["color"]
        row["stt_score_color"] = score["color"]
        row["stt_score_label"] = score["label"]
        row["stt_score_flags"] = list(score["flags"])
        row["stt_score_components"] = dict(score["components"])
        row.setdefault("stt_preview_source", source_key)
        row.setdefault("stt_source", source_key)
        out.append(row)
        text = _normalize_text(row.get("text"))
        if text:
            previous.append(text)
    return out


def annotate_stt_candidate_tracks(
    tracks: dict[str, list[dict[str, Any]]],
    *,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    stt1 = [dict(seg) for seg in tracks.get("STT1", []) if isinstance(seg, dict)]
    stt2 = [dict(seg) for seg in tracks.get("STT2", []) if isinstance(seg, dict)]
    return {
        "STT1": annotate_stt_candidates(
            stt1,
            source="STT1",
            peer_segments=stt2,
            vad_segments=vad_segments,
            settings=settings,
        ),
        "STT2": annotate_stt_candidates(
            stt2,
            source="STT2",
            peer_segments=stt1,
            vad_segments=vad_segments,
            settings=settings,
        ),
    }


def average_stt_score(segments: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> float:
    values: list[float] = []
    for segment in segments or ():
        value = _as_float(dict(segment).get("stt_score", dict(segment).get("score")))
        if value is not None:
            values.append(_clip(value))
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


__all__ = [
    "annotate_stt_candidate_tracks",
    "annotate_stt_candidates",
    "average_stt_score",
    "filter_scored_stt_candidates",
    "score_stt_candidate",
    "stt_score_label",
    "stt_score_to_color",
]
