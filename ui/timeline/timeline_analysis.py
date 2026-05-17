# Version: 03.09.29
# Phase: PHASE2
"""Timeline analysis and cut-safety marker helpers."""

from __future__ import annotations

import time
from typing import Any

from core.project.subtitle_status import (
    SUBTITLE_STATUS_COLORS,
    subtitle_detection_score,
)
from ui.style import COLORS
from ui.ux.apple_black_palette import APPLE_BLACK_MAJOR_COLORS


SAFETY_COLORS = {
    "ideal": COLORS["accent"],
    "acceptable": COLORS["warning"],
    "risky": COLORS["danger"],
}

ACTION_COLORS = {
    "keep": COLORS["accent"],
    "trim": "#FF9F0A",
    "remove": COLORS["danger"],
    "highlight": COLORS["info"],
    "move": COLORS["purple"],
}

QUALITY_COLORS = {
    "green": COLORS["accent"],
    "yellow": COLORS["warning"],
    "red": COLORS["danger"],
    "gray": COLORS["neutral"],
}

VOICE_ACTIVITY_STYLES = {
    "speech": ("음성", COLORS["accent"], 40, 128),
    "silence": ("무음", "#FF9F0A", 50, 112),
    "noise": ("노이즈", COLORS["danger"], 90, 158),
    "stt_pending": ("STT대기", COLORS["info"], 70, 148),
    "outside_vad": ("VAD외", COLORS["purple"], 80, 148),
    "uncertain": ("확인", COLORS["neutral"], 60, 126),
}

SUBTITLE_DETECTION_NEEDS_SELECTION_COLOR = COLORS["neutral"]
SUBTITLE_DETECTION_IDLE_COLOR = COLORS["separator"]
SUBTITLE_SCORE_DETECTION_KINDS = {
    "conflict",
    "llm_selected",
    "manual_selected",
    "pending",
    "recheck",
    "subtitle_score",
}
MAJOR_SEGMENT_COLORS = APPLE_BLACK_MAJOR_COLORS

_RECHECK_THRESHOLD_CACHE: dict[str, float] = {"value": 60.0, "until": 0.0}


def find_roughcut_result(widget: Any):
    """Find the active roughcut result from a timeline child widget."""
    owner = widget
    while owner is not None:
        roughcut = getattr(owner, "_roughcut_widget", None)
        result = getattr(roughcut, "_result", None)
        if result is not None:
            return result
        for attr in ("_roughcut_result", "roughcut_result", "_roughcut_draft_result"):
            result = getattr(owner, attr, None)
            if result is not None:
                return result
        for attr in ("_cut_boundary_topicless_middle_segments", "_middle_segments", "middle_segments"):
            rows = getattr(owner, attr, None)
            if rows:
                return {"segments": list(rows)}
        owner = owner.parent() if hasattr(owner, "parent") else None

    try:
        window = widget.window()
    except Exception:
        window = None
    if window is not None:
        roughcut = getattr(window, "_roughcut_widget", None)
        result = getattr(roughcut, "_result", None)
        if result is not None:
            return result
        result = getattr(window, "_editor_roughcut_result", None)
        if result is not None:
            return result
        for attr in ("_roughcut_result", "roughcut_result", "_roughcut_draft_result"):
            result = getattr(window, attr, None)
            if result is not None:
                return result
        for attr in ("_cut_boundary_topicless_middle_segments", "_middle_segments", "middle_segments"):
            rows = getattr(window, attr, None)
            if rows:
                return {"segments": list(rows)}
    return None


def roughcut_markers(result: Any) -> list[dict]:
    markers: list[dict] = []
    decisions = getattr(result, "edit_decisions", None) or []
    for decision in decisions:
        start = _as_float(getattr(decision, "source_start", None))
        end = _as_float(getattr(decision, "source_end", None))
        if start is None or end is None or end <= start:
            continue
        action = str(getattr(decision, "action", "") or "keep")
        safety = str(getattr(decision, "safety", "") or "acceptable")
        color = _roughcut_marker_color(action, safety)
        markers.append(
            {
                "start": start,
                "end": end,
                "kind": f"roughcut:{action}",
                "label": _roughcut_label(action, safety),
                "color": color,
                "action": action,
                "safety": safety,
                "reason": str(getattr(decision, "reason", "") or ""),
                "priority": 90 if safety == "risky" or action in {"remove", "move"} else 70,
                "alpha": 150 if safety == "risky" else 118,
            }
        )
    return markers


def roughcut_major_markers(result: Any) -> list[dict]:
    markers: list[dict] = []
    if isinstance(result, list):
        segments = list(result)
    elif isinstance(result, dict):
        segments = result.get("segments", []) or []
    else:
        segments = getattr(result, "segments", None) or []

    def _field(segment: Any, name: str, default: Any = "") -> Any:
        if isinstance(segment, dict):
            return segment.get(name, default)
        return getattr(segment, name, default)

    def _placeholder_title(segment: Any, title: str) -> bool:
        return bool(
            _field(segment, "is_topicless_placeholder", False)
            or _field(segment, "is_cut_boundary_placeholder", False)
            or str(_field(segment, "story_role", "") or "") == "topicless_placeholder"
            or title == "주제없음"
        )

    for index, segment in enumerate(segments):
        start = _as_float(_field(segment, "start", None))
        end = _as_float(_field(segment, "end", None))
        if start is None or end is None or end <= start:
            continue
        major_id = str(_field(segment, "major_id", "") or _field(segment, "segment_id", "") or chr(65 + (index % 26)))
        title = str(_field(segment, "title", "") or "")
        status = str(_field(segment, "status", "") or "provisional")
        explicit_color = str(_field(segment, "border_color", "") or _field(segment, "color", "") or "").strip()
        color = explicit_color or roughcut_major_color(major_id, index)
        explicit_display = str(
            _field(segment, "display_title", "")
            or _field(segment, "display_name", "")
            or _field(segment, "label", "")
            or ""
        ).strip()
        display_label = explicit_display or (major_id if _placeholder_title(segment, title) or not title else f"{major_id} - {title}")
        markers.append(
            {
                "start": start,
                "end": end,
                "kind": "roughcut_major",
                "label": major_id,
                "display_label": display_label,
                "title": title,
                "status": status,
                "color": color,
                "priority": 100,
                "alpha": 255,
            }
        )
    return markers


def roughcut_major_color(major_id: str, fallback_index: int = 0) -> str:
    code = str(major_id or "").strip().upper()
    if code and "A" <= code[0] <= "Z":
        return MAJOR_SEGMENT_COLORS[ord(code[0]) - ord("A")]
    return MAJOR_SEGMENT_COLORS[int(fallback_index or 0) % len(MAJOR_SEGMENT_COLORS)]


def roughcut_major_markers_for_widget(widget: Any) -> list[dict]:
    result = find_roughcut_result(widget)
    return roughcut_major_markers(result) if result is not None else []


def _rows_attr_for_widget(widget: Any, attr_names: tuple[str, ...]) -> list[dict]:
    owner = widget
    while owner is not None:
        for attr in attr_names:
            rows = getattr(owner, attr, None)
            if isinstance(rows, list) and rows:
                return [dict(row) for row in rows if isinstance(row, dict)]
        owner = owner.parent() if hasattr(owner, "parent") else None

    try:
        window = widget.window()
    except Exception:
        window = None
    if window is not None:
        for attr in attr_names:
            rows = getattr(window, attr, None)
            if isinstance(rows, list) and rows:
                return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def preliminary_major_markers_for_widget(widget: Any) -> list[dict]:
    rows = _rows_attr_for_widget(widget, ("_preliminary_middle_segments", "preliminary_middle_segments"))
    return roughcut_major_markers(rows) if rows else []


def topicless_major_markers_for_widget(widget: Any) -> list[dict]:
    rows = _rows_attr_for_widget(
        widget,
        ("_cut_boundary_topicless_middle_segments", "cut_boundary_topicless_middle_segments"),
    )
    return roughcut_major_markers(rows) if rows else []


def editor_analysis_markers(
    segments: list[dict],
    vad_segments: list[dict],
    gap_segments: list[dict],
    total_duration: float,
) -> list[dict]:
    markers: list[dict] = []
    total_duration = max(0.0, float(total_duration or 0.0))

    def _clip_range(start: float, end: float) -> tuple[float, float] | None:
        if total_duration > 0:
            start = max(0.0, min(total_duration, start))
            end = max(start, min(total_duration, end))
        if end - start < 0.05:
            return None
        return start, end

    def _merged_ranges(items: list[tuple[float, float]], min_len: float = 0.05) -> list[tuple[float, float]]:
        merged: list[tuple[float, float]] = []
        for start, end in sorted(items):
            clipped = _clip_range(start, end)
            if clipped is None:
                continue
            start, end = clipped
            if end - start < min_len:
                continue
            if merged and start <= merged[-1][1] + 0.001:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    def _subtract_ranges(
        base_ranges: list[tuple[float, float]],
        blockers: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        blockers = _merged_ranges(blockers)
        result: list[tuple[float, float]] = []
        blocker_idx = 0
        for start, end in _merged_ranges(base_ranges):
            cursor = start
            while blocker_idx < len(blockers) and blockers[blocker_idx][1] <= cursor:
                blocker_idx += 1
            scan_idx = blocker_idx
            while scan_idx < len(blockers):
                block_start, block_end = blockers[scan_idx]
                if block_start >= end:
                    break
                if block_end <= cursor:
                    scan_idx += 1
                    continue
                if block_start > cursor + 0.05:
                    result.append((cursor, min(block_start, end)))
                cursor = max(cursor, block_end)
                if cursor >= end - 0.05:
                    break
                scan_idx += 1
            if cursor < end - 0.05:
                result.append((cursor, end))
        return _merged_ranges(result)

    speech_ranges: list[tuple[float, float]] = []
    for seg in segments or []:
        if seg.get("is_gap") or _is_stt_candidate_timing_segment(seg):
            continue
        start = _as_float(seg.get("start"))
        end = _as_float(seg.get("end"))
        if start is None or end is None or end <= start:
            continue
        speech_ranges.append((start, end))

    vad_silence_ranges: list[tuple[float, float]] = []
    for vad in vad_segments or []:
        start = _as_float(vad.get("start"))
        end = _as_float(vad.get("end"))
        if start is None or end is None or end <= start:
            continue
        if _voice_kind_from_vad(vad) == "silence":
            vad_silence_ranges.append((start, end))
        else:
            speech_ranges.append((start, end))

    gap_ranges: list[tuple[float, float]] = []
    for gap in gap_segments or []:
        start = _as_float(gap.get("start"))
        end = _as_float(gap.get("end"))
        if start is None or end is None or end <= start:
            continue
        gap_ranges.append((start, end))
    gap_ranges.extend(vad_silence_ranges)

    if not gap_ranges and speech_ranges and total_duration > 0:
        cursor = 0.0
        for start, end in _merged_ranges(speech_ranges):
            if start > cursor + 0.05:
                gap_ranges.append((cursor, start))
            cursor = max(cursor, end)
        if total_duration > cursor + 0.05:
            gap_ranges.append((cursor, total_duration))

    # The bottom voice/silence lane is driven by subtitle gap blocks, but real
    # subtitle/STT blocks win when stale or wide gap ranges overlap them.
    silence_ranges = _subtract_ranges(gap_ranges, speech_ranges)

    cursor = 0.0
    for start, end in silence_ranges:
        if start > cursor + 0.05:
            markers.append(
                {
                    "start": cursor,
                    "end": start,
                    "kind": "speech",
                    "label": "음성",
                    "color": "#34C759",
                    "priority": 10,
                    "alpha": 74,
                }
            )
        markers.append(
            {
                "start": start,
                "end": end,
                "kind": "silence",
                "label": "무음",
                "color": "#FF9500",
                "priority": 20,
                "alpha": 132,
            }
        )
        cursor = max(cursor, end)

    if total_duration > cursor + 0.05:
        markers.append(
            {
                "start": cursor,
                "end": total_duration,
                "kind": "speech",
                "label": "음성",
                "color": "#34C759",
                "priority": 10,
                "alpha": 74,
            }
        )

    if not markers and total_duration > 0:
        markers.append(
            {
                "start": 0.0,
                "end": total_duration,
                "kind": "speech",
                "label": "음성",
                "color": "#34C759",
                "priority": 10,
                "alpha": 74,
            }
        )
    return markers


def voice_activity_segments_for_editor(
    segments: list[dict],
    vad_segments: list[dict],
    gap_segments: list[dict],
    total_duration: float,
) -> list[dict]:
    """Build the subtitle-detection lane while keeping the legacy save key."""
    return subtitle_detection_segments_for_editor(segments, vad_segments, gap_segments, total_duration)


def subtitle_generation_silence_segments_for_editor(
    gap_segments: list[dict],
    total_duration: float,
) -> list[dict]:
    # Gap rows remain editable in the subtitle lane, but we no longer create
    # a second "generation_silence" helper lane between speaker/subtitle rows.
    return []


def subtitle_detection_segments_for_editor(
    segments: list[dict],
    vad_segments: list[dict],
    gap_segments: list[dict],
    total_duration: float,
) -> list[dict]:
    """Build a non-overlapping subtitle detection lane from STT and quality hints."""
    candidates: list[dict] = []
    total_duration = max(0.0, float(total_duration or 0.0))
    review_threshold = _cached_recheck_threshold()

    def add(start, end, kind: str, source: str = "", label: str = "", color: str = "", priority: int = 0, alpha: int = 128, score: float | None = None, selection_state: str = ""):
        start_f = _as_float(start)
        end_f = _as_float(end)
        if start_f is None or end_f is None or end_f <= start_f:
            return
        if total_duration > 0:
            start_f = max(0.0, min(total_duration, start_f))
            end_f = max(start_f, min(total_duration, end_f))
        if end_f <= start_f:
            return
        label = label or "자막"
        color = color or SUBTITLE_DETECTION_IDLE_COLOR
        candidates.append(
            {
                "start": round(start_f, 3),
                "end": round(end_f, 3),
                "kind": kind,
                "label": label,
                "color": color,
                "priority": priority,
                "alpha": alpha,
                "source": source,
                "score": score,
                "selection_state": selection_state,
            }
        )

    for seg in segments or []:
        start = seg.get("start")
        end = seg.get("end")
        if seg.get("stt_pending") or seg.get("_live_stt_preview"):
            source = _stt_source_for_segment(seg)
            if source in {"STT1", "STT2"}:
                continue
            score = _subtitle_detection_score(seg, source)
            color = subtitle_detection_color(score) if score is not None else SUBTITLE_DETECTION_IDLE_COLOR
            add(
                start,
                end,
                "stt_candidate",
                source=source or "STT",
                label=_subtitle_detection_label(source or "STT", score),
                color=color,
                priority=45,
                alpha=116,
                score=score,
                selection_state="candidate",
            )
            continue

        llm_selected = bool(str(seg.get("stt_ensemble_llm_selected_source", "") or "").strip())
        manually_selected = bool(str(seg.get("stt_selected_source", "") or "").strip())

        source = _selected_stt_source(seg)
        score = _subtitle_detection_score(seg, source)
        quality = dict(seg.get("quality") or {})
        flags = {str(flag) for flag in (quality.get("flags") or [])}
        manually_confirmed = bool(quality.get("manual_confirmed")) or "manual_confirmed" in flags
        review_state = subtitle_review_state(seg, recheck_threshold=review_threshold)

        if manually_confirmed:
            add(
                start,
                end,
                "subtitle_confirmed",
                source="manual_confirmed",
                label="자막확정",
                color="#34C759",
                priority=98,
                alpha=162,
                score=score,
                selection_state="manual_confirmed",
            )
            continue

        if review_state == "recheck":
            add(
                start,
                end,
                "recheck",
                source=source or "quality",
                label=_subtitle_detection_label("재검사", score),
                color=SUBTITLE_STATUS_COLORS["recheck"],
                priority=97,
                alpha=162,
                score=score,
                selection_state="recheck",
            )
            continue

        if review_state == "conflict" and not (llm_selected or manually_selected):
            add(
                start,
                end,
                "conflict",
                source="review",
                label=_subtitle_detection_label("판단불가", score),
                color=SUBTITLE_STATUS_COLORS["conflict"],
                priority=96,
                alpha=154,
                score=score,
                selection_state="conflict",
            )
            continue

        if source in {"STT1", "STT2"}:
            state = "llm_selected" if llm_selected else ("manual_selected" if manually_selected else "pending")
            suffix = "미확정"
            label = _subtitle_detection_label(source, score, suffix=suffix)
            add(
                start,
                end,
                state,
                source=source,
                label=label,
                color=COLORS["warning"],
                priority=92 if llm_selected else 84,
                alpha=158,
                score=score,
                selection_state=state,
            )
            continue

        if quality:
            add(
                start,
                end,
                "subtitle_score",
                source="quality",
                label=_subtitle_detection_label("미확정", score),
                color=COLORS["warning"],
                priority=54,
                alpha=126,
                score=score,
                selection_state="quality",
            )

    if not candidates and total_duration > 0:
        add(0.0, total_duration, "idle", source="subtitle_detection", label="음성", color="#34C759", priority=0, alpha=92)

    return _resolve_non_overlapping_voice_activity(candidates)


def subtitle_score_overlay_marker(seg: dict, *, recheck_threshold: float | None = None) -> dict | None:
    """Return compact score text that can be rendered above the subtitle row."""
    if not isinstance(seg, dict) or seg.get("is_gap") or seg.get("stt_pending") or seg.get("_live_stt_preview"):
        return None
    start = _as_float(seg.get("start"))
    end = _as_float(seg.get("end"))
    if start is None or end is None or end <= start:
        return None

    llm_selected = bool(str(seg.get("stt_ensemble_llm_selected_source", "") or "").strip())
    manually_selected = bool(str(seg.get("stt_selected_source", "") or "").strip())
    source = _selected_stt_source(seg)
    score = _subtitle_detection_score(seg, source)
    quality = dict(seg.get("quality") or {})
    flags = {str(flag) for flag in (quality.get("flags") or [])}
    manually_confirmed = bool(quality.get("manual_confirmed")) or "manual_confirmed" in flags
    if manually_confirmed:
        return None

    review_state = subtitle_review_state(
        seg,
        recheck_threshold=_cached_recheck_threshold() if recheck_threshold is None else float(recheck_threshold),
    )
    if review_state == "recheck":
        label = _subtitle_detection_label("재검사", score)
        color = SUBTITLE_STATUS_COLORS["recheck"]
        kind = "recheck"
    elif review_state == "conflict" and not (llm_selected or manually_selected):
        label = _subtitle_detection_label("판단불가", score)
        color = SUBTITLE_STATUS_COLORS["conflict"]
        kind = "conflict"
    elif source in {"STT1", "STT2"}:
        label = _subtitle_detection_label(source, score, suffix="미확정")
        color = COLORS["warning"]
        kind = "llm_selected" if llm_selected else ("manual_selected" if manually_selected else "pending")
    elif quality:
        label = _subtitle_detection_label("미확정", score)
        color = COLORS["warning"]
        kind = "subtitle_score"
    else:
        return None

    return {
        "start": round(float(start), 3),
        "end": round(float(end), 3),
        "kind": kind,
        "label": label,
        "color": color,
        "score": score,
    }


def subtitle_detection_color(score: float | None) -> str:
    value = 50.0 if score is None else max(0.0, min(100.0, float(score)))
    warning = COLORS["warning"].lstrip("#")
    warning_r = int(warning[0:2], 16)
    warning_g = int(warning[2:4], 16)
    warning_b = int(warning[4:6], 16)
    if value >= 50.0:
        ratio = (value - 50.0) / 50.0
        r = round(warning_r + (52 - warning_r) * ratio)
        g = round(warning_g + (199 - warning_g) * ratio)
        b = round(warning_b + (89 - warning_b) * ratio)
    else:
        ratio = value / 50.0
        r = round(255 + (warning_r - 255) * ratio)
        g = round(69 + (warning_g - 69) * ratio)
        b = round(58 + (warning_b - 58) * ratio)
    return f"#{r:02X}{g:02X}{b:02X}"


def _subtitle_detection_label(prefix: str, score: float | None, *, suffix: str = "") -> str:
    score_text = "-" if score is None else f"{float(score):.0f}"
    label = f"{prefix} {score_text}점"
    if suffix:
        label = f"{prefix} {suffix} {score_text}점"
    return label


def _selected_stt_source(seg: dict) -> str:
    for key in ("stt_selected_source", "stt_ensemble_llm_selected_source", "stt_ensemble_source"):
        source = str(seg.get(key, "") or "").strip().upper()
        if source in {"STT1", "STT2"}:
            return source
    candidates = list(seg.get("stt_candidates") or [])
    if len(candidates) == 1:
        source = str(candidates[0].get("source", "") or "").strip().upper()
        if source in {"STT1", "STT2"}:
            return source
    return ""


def _stt_source_for_segment(seg: dict) -> str:
    for key in ("stt_preview_source", "stt_source", "stt_ensemble_source"):
        source = str(seg.get(key, "") or "").strip().upper()
        if source in {"STT1", "STT2"}:
            return source
    return ""


def _is_stt_candidate_timing_segment(seg: dict) -> bool:
    return bool(seg.get("stt_pending") or seg.get("_live_stt_preview")) and _stt_source_for_segment(seg) in {"STT1", "STT2"}


def _subtitle_needs_selection(seg: dict) -> bool:
    candidates = [
        item for item in list(seg.get("stt_candidates") or [])
        if str(item.get("source", "") or "").strip().upper() in {"STT1", "STT2"}
    ]
    selected_source = _selected_stt_source(seg)
    quality = dict(seg.get("quality") or {})
    label = str(quality.get("confidence_label") or "").strip().lower()
    flags = {str(flag) for flag in (quality.get("flags") or ())}
    return (
        bool(seg.get("stt_ensemble_needs_llm_review"))
        or (len(candidates) >= 2 and selected_source not in {"STT1", "STT2"})
        or label in {"red", "gray"}
        or bool(flags.intersection({"non_speech_hallucination_risk", "high_no_speech_prob", "outside_vad_speech"}))
        or bool(seg.get("quality_stale"))
    )


def _recheck_threshold() -> float:
    from core.project.subtitle_status import recheck_threshold

    return recheck_threshold()


def _cached_recheck_threshold() -> float:
    now = time.monotonic()
    if now < float(_RECHECK_THRESHOLD_CACHE.get("until", 0.0) or 0.0):
        return float(_RECHECK_THRESHOLD_CACHE.get("value", 60.0) or 60.0)
    value = float(_recheck_threshold())
    _RECHECK_THRESHOLD_CACHE["value"] = value
    _RECHECK_THRESHOLD_CACHE["until"] = now + 0.75
    return value


def _stt_candidate_scores(seg: dict) -> list[float]:
    scores: list[float] = []
    for candidate in list(seg.get("stt_candidates") or []):
        if str(candidate.get("source", "") or "").strip().upper() not in {"STT1", "STT2"}:
            continue
        score = _as_float(candidate.get("score"))
        if score is not None:
            scores.append(_normalize_score_100(score))
    return scores


def subtitle_review_state(seg: dict, *, recheck_threshold: float | None = None) -> str:
    from core.project.subtitle_status import subtitle_review_state as _shared_subtitle_review_state

    threshold = _cached_recheck_threshold() if recheck_threshold is None else float(recheck_threshold)
    return _shared_subtitle_review_state(seg, threshold=threshold)


def _subtitle_detection_score(seg: dict, source: str = "") -> float | None:
    return subtitle_detection_score(seg, source)


def _normalize_score_100(value: float) -> float:
    value = max(0.0, float(value))
    if value <= 1.0:
        value *= 100.0
    return max(0.0, min(100.0, value))


def _voice_kind_from_vad(vad: dict) -> str:
    raw = " ".join(
        str(vad.get(key, "") or "").lower()
        for key in ("kind", "type", "label", "category", "vad_type")
    )
    if bool(vad.get("is_noise")) or "noise" in raw or "노이즈" in raw:
        return "noise"
    if bool(vad.get("is_silence")) or "silence" in raw or "무음" in raw:
        return "silence"
    if "uncertain" in raw or "unknown" in raw or "확인" in raw:
        return "uncertain"
    return "speech"


def _resolve_non_overlapping_voice_activity(candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []
    normalized: list[tuple[float, float, dict]] = []
    for item in candidates:
        try:
            start = round(float(item["start"]), 3)
            end = round(float(item["end"]), 3)
        except Exception:
            continue
        if end <= start:
            continue
        normalized.append((start, end, item))
    if not normalized:
        return []

    resolved: list[dict] = []

    # Sweep over boundary events instead of scanning every candidate for every
    # boundary interval. Large subtitle projects can produce thousands of
    # detection spans during zoom/fit repaints, and the previous nested scan
    # made that path quadratic before any vector drawing could help.
    import heapq

    events: list[tuple[float, int, int]] = []
    for idx, (start, end, _item) in enumerate(normalized):
        events.append((start, 1, idx))
        events.append((end, -1, idx))
    events.sort(key=lambda row: row[0])

    active: set[int] = set()
    heap: list[tuple[int, float, int]] = []
    cursor = 0
    prev_time: float | None = None

    while cursor < len(events):
        event_time = events[cursor][0]
        if prev_time is not None and event_time > prev_time and active:
            while heap and heap[0][2] not in active:
                heapq.heappop(heap)
            if heap:
                chosen_idx = heap[0][2]
                start = prev_time
                end = event_time
                _item_start, _item_end, chosen = normalized[chosen_idx]
                item = dict(chosen)
                item["start"] = start
                item["end"] = end
                comparable = (item.get("kind"), item.get("label"), item.get("color"), item.get("source"))
                if resolved:
                    prev = resolved[-1]
                    prev_key = (prev.get("kind"), prev.get("label"), prev.get("color"), prev.get("source"))
                    if prev_key == comparable and abs(float(prev.get("end", 0.0) or 0.0) - start) < 0.001:
                        prev["end"] = end
                    else:
                        resolved.append(item)
                else:
                    resolved.append(item)

        while cursor < len(events) and events[cursor][0] == event_time:
            _time, kind, idx = events[cursor]
            if kind > 0:
                start, end, item = normalized[idx]
                active.add(idx)
                priority = int(item.get("priority", 0) or 0)
                duration = max(0.0, end - start)
                heapq.heappush(heap, (-priority, duration, idx))
            else:
                active.discard(idx)
            cursor += 1
        prev_time = event_time

    return resolved


def analysis_markers_for_widget(widget: Any, segments: list[dict], vad_segments: list[dict], gap_segments: list[dict], total_duration: float) -> list[dict]:
    return editor_analysis_markers(segments, vad_segments, gap_segments, total_duration)


def _roughcut_label(action: str, safety: str) -> str:
    if action == "remove":
        return "제거"
    if action == "trim":
        return "트림"
    if action == "highlight":
        return "하이라이트"
    if action == "move":
        return "이동"
    if safety == "ideal":
        return "정상"
    if safety == "risky":
        return "위험"
    return "주의"


def _roughcut_marker_color(action: str, safety: str) -> str:
    if safety == "risky":
        return SAFETY_COLORS["risky"]
    if action == "keep":
        return SAFETY_COLORS.get(safety, "#8B949E")
    return ACTION_COLORS.get(action, SAFETY_COLORS.get(safety, "#8B949E"))


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
