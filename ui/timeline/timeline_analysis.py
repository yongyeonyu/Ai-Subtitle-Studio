# Version: 03.01.25
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
        color = ACTION_COLORS.get(action, SAFETY_COLORS.get(safety, "#8B949E"))
        markers.append(
            {
                "start": start,
                "end": end,
                "kind": f"roughcut:{action}",
                "label": _roughcut_label(action, safety),
                "color": color,
                "priority": 90 if safety == "risky" or action in {"remove", "move"} else 70,
                "alpha": 150 if safety == "risky" else 118,
            }
        )
    return markers


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
                "color": "#2E8BFF",
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
                "color": "#4D5B66",
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
        return "안전"
    if safety == "risky":
        return "위험"
    return "주의"


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
