# Version: 03.09.29
# Phase: PHASE2
"""Timeline analysis and cut-safety marker helpers."""

from __future__ import annotations

from typing import Any


SAFETY_COLORS = {
    "ideal": "#34C759",
    "acceptable": "#FFCC00",
    "risky": "#FF453A",
}

ACTION_COLORS = {
    "keep": "#34C759",
    "trim": "#FF9500",
    "remove": "#FF453A",
    "highlight": "#5AC8FA",
    "move": "#A678F4",
}

QUALITY_COLORS = {
    "green": "#34C759",
    "yellow": "#FFCC00",
    "red": "#FF453A",
    "gray": "#8E8E93",
}

VOICE_ACTIVITY_STYLES = {
    "speech": ("음성", "#34C759", 40, 128),
    "silence": ("무음", "#FF9500", 50, 112),
    "noise": ("노이즈", "#FF453A", 90, 158),
    "stt_pending": ("STT대기", "#64D2FF", 70, 148),
    "outside_vad": ("VAD외", "#BF5AF2", 80, 148),
    "uncertain": ("확인", "#8E8E93", 60, 126),
}

SUBTITLE_DETECTION_NEEDS_SELECTION_COLOR = "#8E8E93"
SUBTITLE_DETECTION_IDLE_COLOR = "#2D3942"

MAJOR_SEGMENT_COLORS = (
    "#00E676",  # A
    "#FF453A",  # B
    "#FFD60A",  # C
    "#76FF03",  # D
    "#00B8D4",  # E
    "#FF9F0A",  # F
    "#BF5AF2",  # G
    "#64D2FF",  # H
    "#FF2D55",  # I
    "#30D158",  # J
    "#0A84FF",  # K
    "#FF6B00",  # L
    "#D0FF00",  # M
    "#5E5CE6",  # N
    "#00F5D4",  # O
    "#FFB3C7",  # P
    "#9DFF00",  # Q
    "#FF375F",  # R
    "#40C8E0",  # S
    "#FFCC66",  # T
    "#32D74B",  # U
    "#DA8FFF",  # V
    "#66D4CF",  # W
    "#FF7A90",  # X
    "#A1A1FF",  # Y
    "#C6FF3D",  # Z
)


def find_roughcut_result(widget: Any):
    """Find the active roughcut result from a timeline child widget."""
    owner = widget
    while owner is not None:
        roughcut = getattr(owner, "_roughcut_widget", None)
        result = getattr(roughcut, "_result", None)
        if result is not None:
            return result
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
    segments = getattr(result, "segments", None) or []
    for index, segment in enumerate(segments):
        start = _as_float(getattr(segment, "start", None))
        end = _as_float(getattr(segment, "end", None))
        if start is None or end is None or end <= start:
            continue
        major_id = str(getattr(segment, "major_id", "") or getattr(segment, "segment_id", "") or chr(65 + (index % 26)))
        title = str(getattr(segment, "title", "") or "")
        status = str(getattr(segment, "status", "") or "provisional")
        tags = tuple(getattr(segment, "tags", ()) or ())
        is_topicless_placeholder = (
            title == "주제없음"
            or "주제없음" in tags
            or (status == "provisional" and "컷경계" in tags)
        )
        color = "#8E8E93" if is_topicless_placeholder else roughcut_major_color(major_id, index)
        markers.append(
            {
                "start": start,
                "end": end,
                "kind": "roughcut_major",
                "label": major_id,
                "title": title,
                "status": status,
                "color": color,
                "priority": 100,
                "alpha": 72 if status == "confirmed" else 42,
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


def editor_analysis_markers(
    segments: list[dict],
    vad_segments: list[dict],
    gap_segments: list[dict],
    total_duration: float,
) -> list[dict]:
    markers: list[dict] = []
    total_duration = max(0.0, float(total_duration or 0.0))

    for vad in vad_segments or []:
        start = _as_float(vad.get("start"))
        end = _as_float(vad.get("end"))
        if start is None or end is None or end <= start:
            continue
        markers.append(
            {
                "start": start,
                "end": end,
                "kind": "vad",
                "label": "음성",
                "color": "#34C759",
                "priority": 10,
                "alpha": 62,
            }
        )

    for gap in gap_segments or []:
        start = _as_float(gap.get("start"))
        end = _as_float(gap.get("end"))
        if start is None or end is None or end <= start:
            continue
        if end - start < 0.25:
            continue
        markers.append(
            {
                "start": start,
                "end": end,
                "kind": "silence",
                "label": "무음",
                "color": "#FF9500",
                "priority": 20,
                "alpha": 118,
            }
        )

    for seg in segments or []:
        start = _as_float(seg.get("start"))
        end = _as_float(seg.get("end"))
        if start is None or end is None or end <= start:
            continue
        quality = dict(seg.get("quality") or {})
        if quality:
            label_key = str(quality.get("confidence_label") or "gray")
            flags = set(quality.get("flags") or ())
            score = quality.get("confidence_score")
            score_text = "-" if score is None else f"{float(score):.0f}"
            needs_review = label_key in {"red", "gray"} or bool(flags.intersection({"non_speech_hallucination_risk", "high_no_speech_prob", "outside_vad_speech"}))
            markers.append(
                {
                    "start": start,
                    "end": end,
                    "kind": f"subtitle_quality:{label_key}",
                    "label": "확인" if needs_review else f"Q{score_text}",
                    "color": QUALITY_COLORS.get(label_key, "#8E8E93"),
                    "priority": 95 if needs_review else 35,
                    "alpha": 162 if needs_review else 104,
                }
            )
        duration = max(0.001, end - start)
        text = str(seg.get("text") or "")
        chars = len("".join(text.split()))
        cps = chars / duration
        label = ""
        color = ""
        priority = 0
        if seg.get("stt_pending"):
            label, color, priority = "STT대기", "#FF453A", 88
        elif duration < 0.35:
            label, color, priority = "짧음", "#FF453A", 82
        elif cps >= 16.0:
            label, color, priority = "CPS위험", "#FF453A", 80
        elif cps >= 12.0:
            label, color, priority = "빠름", "#FFCC00", 62
        elif duration >= 8.0:
            label, color, priority = "장문", "#FF9500", 56
        if label:
            markers.append(
                {
                    "start": start,
                    "end": end,
                    "kind": "subtitle_risk",
                    "label": label,
                    "color": color,
                    "priority": priority,
                    "alpha": 150 if priority >= 80 else 128,
                }
            )

    if not markers and total_duration > 0:
        markers.append(
            {
                "start": 0.0,
                "end": total_duration,
                "kind": "idle",
                "label": "분석대기",
                "color": "#2D3942",
                "priority": 0,
                "alpha": 96,
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


def subtitle_detection_segments_for_editor(
    segments: list[dict],
    vad_segments: list[dict],
    gap_segments: list[dict],
    total_duration: float,
) -> list[dict]:
    """Build a non-overlapping subtitle detection lane from STT and quality hints."""
    candidates: list[dict] = []
    total_duration = max(0.0, float(total_duration or 0.0))

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

        needs_selection = _subtitle_needs_selection(seg)
        llm_selected = bool(str(seg.get("stt_ensemble_llm_selected_source", "") or "").strip())
        manually_selected = bool(str(seg.get("stt_selected_source", "") or "").strip())

        source = _selected_stt_source(seg)
        score = _subtitle_detection_score(seg, source)

        if needs_selection and not (llm_selected or manually_selected):
            add(
                start,
                end,
                "needs_selection",
                source="review",
                label=_subtitle_detection_label("선택필요", score),
                color=SUBTITLE_DETECTION_NEEDS_SELECTION_COLOR,
                priority=96,
                alpha=154,
                score=score,
                selection_state="needs_selection",
            )
            continue

        if source in {"STT1", "STT2"}:
            state = "llm_selected" if llm_selected else ("manual_selected" if manually_selected else "selected")
            suffix = "LLM" if llm_selected else ("선택" if manually_selected else "")
            label = _subtitle_detection_label(source, score, suffix=suffix)
            add(
                start,
                end,
                state,
                source=source,
                label=label,
                color=subtitle_detection_color(score),
                priority=92 if llm_selected else 84,
                alpha=158,
                score=score,
                selection_state=state,
            )
            continue

        quality = dict(seg.get("quality") or {})
        if quality:
            add(
                start,
                end,
                "subtitle_score",
                source="quality",
                label=_subtitle_detection_label("자막", score),
                color=subtitle_detection_color(score),
                priority=54,
                alpha=126,
                score=score,
                selection_state="quality",
            )

    if not candidates and total_duration > 0:
        add(0.0, total_duration, "idle", source="subtitle_detection", label="감지대기", color=SUBTITLE_DETECTION_IDLE_COLOR, priority=0, alpha=92)

    return _resolve_non_overlapping_voice_activity(candidates)


def subtitle_detection_color(score: float | None) -> str:
    value = 50.0 if score is None else max(0.0, min(100.0, float(score)))
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


def _subtitle_detection_score(seg: dict, source: str = "") -> float | None:
    quality = dict(seg.get("quality") or {})
    score = _as_float(quality.get("confidence_score"))
    if score is not None:
        return max(0.0, min(100.0, score))

    target_source = str(source or _selected_stt_source(seg) or _stt_source_for_segment(seg)).strip().upper()
    for candidate in list(seg.get("stt_candidates") or []):
        cand_source = str(candidate.get("source", "") or "").strip().upper()
        if target_source and cand_source != target_source:
            continue
        score = _as_float(candidate.get("score"))
        if score is not None:
            return _normalize_score_100(score)

    for key in ("score", "confidence", "probability", "avg_confidence"):
        score = _as_float(seg.get(key))
        if score is not None:
            return _normalize_score_100(score)

    similarity = _as_float(seg.get("stt_ensemble_similarity"))
    if similarity is not None:
        return _normalize_score_100(similarity)
    return None


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
    boundaries = sorted(
        {
            round(float(item["start"]), 3)
            for item in candidates
        }
        | {
            round(float(item["end"]), 3)
            for item in candidates
        }
    )
    resolved: list[dict] = []
    for idx in range(len(boundaries) - 1):
        start = boundaries[idx]
        end = boundaries[idx + 1]
        if end <= start:
            continue
        mid = (start + end) / 2.0
        active = [
            item for item in candidates
            if float(item["start"]) <= mid < float(item["end"])
        ]
        if not active:
            continue
        chosen = max(active, key=lambda item: (int(item.get("priority", 0) or 0), -(float(item.get("end", 0.0)) - float(item.get("start", 0.0)))))
        item = dict(chosen)
        item["start"] = start
        item["end"] = end
        comparable = (item.get("kind"), item.get("label"), item.get("color"), item.get("source"))
        if resolved:
            prev = resolved[-1]
            prev_key = (prev.get("kind"), prev.get("label"), prev.get("color"), prev.get("source"))
            if prev_key == comparable and abs(float(prev.get("end", 0.0) or 0.0) - start) < 0.001:
                prev["end"] = end
                continue
        resolved.append(item)
    return resolved


def analysis_markers_for_widget(widget: Any, segments: list[dict], vad_segments: list[dict], gap_segments: list[dict], total_duration: float) -> list[dict]:
    result = find_roughcut_result(widget)
    roughcut = roughcut_markers(result) if result is not None else []
    if roughcut:
        return roughcut
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
