# Version: 03.01.26
# Phase: PHASE2
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from .gap_detector import TimelineGap
from .models import ChapterMetadata, CutPoint, EditDecision, PackedPhrase, RoughCutSegment

CutSafety = Literal["ideal", "acceptable", "risky"]


@dataclass(frozen=True, slots=True)
class CutSafetyResult:
    cut_time: float
    safety: CutSafety
    reason: str
    nearest_gap_distance: float | None = None
    nearest_phrase_boundary_distance: float | None = None
    adjusted_time: float | None = None


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ordered_phrases(phrases: Iterable[PackedPhrase] | None) -> list[PackedPhrase]:
    return sorted(list(phrases or ()), key=lambda phrase: (phrase.start, phrase.end))


def _ordered_gaps(gaps: Iterable[TimelineGap] | None) -> list[TimelineGap]:
    return sorted(list(gaps or ()), key=lambda gap: (gap.start, gap.end))


def _gap_distance(cut_time: float, gap: TimelineGap) -> float:
    if gap.start <= cut_time <= gap.end:
        return 0.0
    return min(abs(cut_time - gap.start), abs(cut_time - gap.end))


def _nearest_phrase_boundary(cut_time: float, phrases: list[PackedPhrase]) -> tuple[float | None, float | None]:
    nearest_time: float | None = None
    nearest_distance: float | None = None
    for phrase in phrases:
        for boundary in (phrase.start, phrase.end):
            distance = abs(cut_time - boundary)
            if nearest_distance is None or distance < nearest_distance:
                nearest_time = boundary
                nearest_distance = distance
    return nearest_time, nearest_distance


def _is_inside_phrase_body(cut_time: float, phrases: list[PackedPhrase], boundary_tolerance: float) -> bool:
    for phrase in phrases:
        if phrase.start + boundary_tolerance < cut_time < phrase.end - boundary_tolerance:
            return True
    return False


def classify_cut_safety(
    cut_time: float,
    phrases: Iterable[PackedPhrase] | None = None,
    gaps: Iterable[TimelineGap] | None = None,
    ideal_gap_duration: float = 0.45,
    acceptable_gap_duration: float = 0.18,
    boundary_tolerance: float = 0.08,
) -> CutSafetyResult:
    """Classify whether a cut point is safe, preferring silence gaps and phrase edges."""
    cut = max(0.0, _as_float(cut_time))
    phrase_items = _ordered_phrases(phrases)
    gap_items = _ordered_gaps(gaps)
    boundary_tol = max(0.0, float(boundary_tolerance))
    ideal_gap = max(0.0, float(ideal_gap_duration))
    acceptable_gap = max(0.0, float(acceptable_gap_duration))

    containing_gap = next((gap for gap in gap_items if gap.start <= cut <= gap.end), None)
    if containing_gap is not None:
        duration = containing_gap.duration
        if duration >= ideal_gap:
            return CutSafetyResult(cut, "ideal", f"inside_gap:{duration:.2f}s", 0.0, None, cut)
        if duration >= acceptable_gap:
            return CutSafetyResult(cut, "acceptable", f"inside_short_gap:{duration:.2f}s", 0.0, None, cut)

    nearest_boundary, boundary_distance = _nearest_phrase_boundary(cut, phrase_items)
    if boundary_distance is not None and boundary_distance <= boundary_tol:
        return CutSafetyResult(
            cut,
            "acceptable",
            "near_phrase_boundary",
            None,
            round(boundary_distance, 4),
            nearest_boundary,
        )

    nearest_gap_distance = None
    if gap_items:
        nearest_gap_distance = min(_gap_distance(cut, gap) for gap in gap_items)

    if _is_inside_phrase_body(cut, phrase_items, boundary_tol):
        return CutSafetyResult(
            cut,
            "risky",
            "inside_phrase_body",
            round(nearest_gap_distance, 4) if nearest_gap_distance is not None else None,
            round(boundary_distance, 4) if boundary_distance is not None else None,
            None,
        )

    if nearest_gap_distance is not None and nearest_gap_distance <= acceptable_gap:
        return CutSafetyResult(
            cut,
            "acceptable",
            "near_gap_edge",
            round(nearest_gap_distance, 4),
            round(boundary_distance, 4) if boundary_distance is not None else None,
            cut,
        )

    return CutSafetyResult(
        cut,
        "risky",
        "no_gap_or_phrase_boundary",
        round(nearest_gap_distance, 4) if nearest_gap_distance is not None else None,
        round(boundary_distance, 4) if boundary_distance is not None else None,
        None,
    )


def _worst_safety(*values: CutSafety) -> CutSafety:
    rank = {"ideal": 0, "acceptable": 1, "risky": 2}
    return max(values, key=lambda value: rank[value])


def _confidence_for_safety(safety: CutSafety) -> float:
    return {"ideal": 0.96, "acceptable": 0.78, "risky": 0.38}.get(safety, 0.5)


def _item_id(item: ChapterMetadata | RoughCutSegment) -> str:
    return getattr(item, "segment_id", "") or getattr(item, "chapter_id", "")


def _item_text(item: ChapterMetadata | RoughCutSegment) -> str:
    parts = [
        getattr(item, "title", ""),
        getattr(item, "summary", ""),
        " ".join(getattr(item, "tags", ()) or ()),
        getattr(item, "story_role", ""),
        getattr(item, "narrative_function", ""),
    ]
    return " ".join(part for part in parts if part).lower()


def _contains_highlight_hint(text: str) -> bool:
    hints = ("핵심", "전환", "결론", "추천", "문제", "결과", "하이라이트", "중요")
    return any(hint in text for hint in hints)


def _choose_action(
    item: ChapterMetadata | RoughCutSegment,
    safety: CutSafety,
    highlight_threshold: float,
    remove_threshold: float,
    trim_duration_threshold: float,
) -> tuple[Literal["keep", "trim", "remove", "highlight", "move"], str]:
    duration = max(0.0, _as_float(getattr(item, "end", 0.0)) - _as_float(getattr(item, "start", 0.0)))
    importance = max(0.0, min(1.0, _as_float(getattr(item, "importance_score", 0.5), 0.5)))
    needs_review = bool(getattr(item, "needs_review", False))
    move_recommendation = str(getattr(item, "move_recommendation", "") or "")
    story_role = str(getattr(item, "story_role", "") or "")
    text = _item_text(item)

    if duration <= 0.01:
        return "remove", "zero_duration"
    if importance <= remove_threshold and needs_review and safety != "risky":
        return "remove", f"low_importance:{importance:.2f}; needs_review"
    if move_recommendation.startswith("review_move"):
        return "move", move_recommendation
    if importance >= highlight_threshold or story_role == "전" or _contains_highlight_hint(text):
        return "highlight", f"highlight_score:{importance:.2f}; role:{story_role or '-'}"
    if duration >= trim_duration_threshold:
        if safety == "risky":
            return "keep", "trim_skipped:risky_cut"
        return "trim", f"long_segment:{duration:.2f}s"
    return "keep", f"balanced_keep:{importance:.2f}"


def _padded_range(start: float, end: float, safety: CutSafety, padding: float) -> tuple[float, float]:
    if safety == "risky":
        return start, end
    pad = max(0.0, float(padding))
    return max(0.0, start - pad), max(start, end + pad)


def build_edit_decisions(
    items: Iterable[ChapterMetadata | RoughCutSegment],
    phrases: Iterable[PackedPhrase] | None = None,
    gaps: Iterable[TimelineGap] | None = None,
    highlight_threshold: float = 0.68,
    remove_threshold: float = 0.22,
    trim_duration_threshold: float = 90.0,
    safe_padding: float = 0.12,
) -> list[EditDecision]:
    """Create conservative edit decisions for the next EDL stage."""
    phrase_items = _ordered_phrases(phrases)
    gap_items = _ordered_gaps(gaps)
    decisions: list[EditDecision] = []

    for output_order, item in enumerate(items):
        start = max(0.0, _as_float(getattr(item, "start", 0.0)))
        end = max(start, _as_float(getattr(item, "end", start), start))
        start_safety = classify_cut_safety(start, phrase_items, gap_items)
        end_safety = classify_cut_safety(end, phrase_items, gap_items)
        safety = _worst_safety(start_safety.safety, end_safety.safety)
        action, reason = _choose_action(
            item,
            safety=safety,
            highlight_threshold=max(0.0, min(1.0, float(highlight_threshold))),
            remove_threshold=max(0.0, min(1.0, float(remove_threshold))),
            trim_duration_threshold=max(0.0, float(trim_duration_threshold)),
        )
        padded_start, padded_end = _padded_range(start, end, safety, safe_padding)
        safety_reason = f"cut_safety:{safety}; start:{start_safety.reason}; end:{end_safety.reason}"

        decisions.append(
            EditDecision(
                segment_id=_item_id(item),
                action=action,
                reason=f"{reason}; {safety_reason}",
                source_start=padded_start,
                source_end=padded_end,
                output_order=output_order,
                safety=safety,
                confidence=_confidence_for_safety(safety),
            )
        )

    return decisions


def generate_cut_points(
    decisions: Iterable[EditDecision],
    phrases: Iterable[PackedPhrase] | None = None,
    gaps: Iterable[TimelineGap] | None = None,
) -> list[CutPoint]:
    """Expose start/end cut points as a standalone contract object."""
    phrase_items = _ordered_phrases(phrases)
    gap_items = _ordered_gaps(gaps)
    cut_points: list[CutPoint] = []
    for decision in decisions or ():
        for boundary, value in (("start", decision.source_start), ("end", decision.source_end)):
            if value is None:
                continue
            safety = classify_cut_safety(value, phrase_items, gap_items)
            cut_points.append(
                CutPoint(
                    segment_id=decision.segment_id,
                    cut_time=value,
                    boundary=boundary,
                    action=decision.action,
                    safety=safety.safety,
                    reason=safety.reason,
                    adjusted_time=safety.adjusted_time,
                    confidence=_confidence_for_safety(safety.safety),
                )
            )
    return cut_points
