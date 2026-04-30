# Version: 03.01.29
# Phase: PHASE2
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from .edit_decision_engine import classify_cut_safety
from .gap_detector import TimelineGap
from .models import ChapterMetadata, PackedPhrase
from .scene_change_detector import SceneChange


@dataclass(frozen=True, slots=True)
class BoundaryVerification:
    original_time: float
    adjusted_time: float
    status: str
    confidence: float
    reason: str


def _distance_to_gap(time_sec: float, gap: TimelineGap) -> float:
    if gap.start <= time_sec <= gap.end:
        return 0.0
    return min(abs(time_sec - gap.start), abs(time_sec - gap.end))


def _nearest_gap_boundary(time_sec: float, gaps: list[TimelineGap], window: float) -> tuple[float, float, str] | None:
    candidates: list[tuple[float, float, str]] = []
    for gap in gaps:
        if _distance_to_gap(time_sec, gap) <= window:
            midpoint = (gap.start + gap.end) / 2.0
            candidates.append((_distance_to_gap(time_sec, gap), midpoint, f"gap_mid:{gap.duration:.2f}s"))
    return min(candidates, default=None, key=lambda item: item[0])


def _nearest_scene_cut(time_sec: float, scene_changes: list[SceneChange], window: float) -> tuple[float, float, str] | None:
    candidates: list[tuple[float, float, str]] = []
    for change in scene_changes:
        cut_time = (float(change.start) + float(change.end)) / 2.0
        distance = abs(time_sec - cut_time)
        if distance <= window:
            candidates.append((distance, cut_time, f"scene_cut:{change.score:.2f}"))
    return min(candidates, default=None, key=lambda item: item[0])


def _nearest_phrase_boundary(time_sec: float, phrases: list[PackedPhrase], window: float) -> tuple[float, float, str] | None:
    candidates: list[tuple[float, float, str]] = []
    for phrase in phrases:
        for boundary, label in ((phrase.start, "phrase_start"), (phrase.end, "phrase_end")):
            distance = abs(time_sec - float(boundary))
            if distance <= window:
                candidates.append((distance, float(boundary), label))
    return min(candidates, default=None, key=lambda item: item[0])


def verify_major_boundary(
    boundary_time: float,
    phrases: Iterable[PackedPhrase] | None = None,
    gaps: Iterable[TimelineGap] | None = None,
    scene_changes: Iterable[SceneChange] | None = None,
    *,
    search_window: float = 1.5,
) -> BoundaryVerification:
    """Verify a proposed boundary against gap, scene cut, and phrase edges."""
    original = max(0.0, float(boundary_time or 0.0))
    window = max(0.0, float(search_window or 0.0))
    phrase_items = sorted(list(phrases or ()), key=lambda phrase: (phrase.start, phrase.end))
    gap_items = sorted(list(gaps or ()), key=lambda gap: (gap.start, gap.end))
    scene_items = sorted((change for change in scene_changes or () if change.is_cut), key=lambda change: (change.start, change.end))

    gap_candidate = _nearest_gap_boundary(original, gap_items, window)
    if gap_candidate is not None:
        _, adjusted, reason = gap_candidate
        return BoundaryVerification(original, round(adjusted, 3), "confirmed", 0.96, reason)

    scene_candidate = _nearest_scene_cut(original, scene_items, window)
    if scene_candidate is not None:
        _, adjusted, reason = scene_candidate
        return BoundaryVerification(original, round(adjusted, 3), "confirmed", 0.9, reason)

    phrase_candidate = _nearest_phrase_boundary(original, phrase_items, min(window, 0.25))
    if phrase_candidate is not None:
        _, adjusted, reason = phrase_candidate
        return BoundaryVerification(original, round(adjusted, 3), "confirmed", 0.78, reason)

    safety = classify_cut_safety(original, phrase_items, gap_items)
    if safety.safety == "risky":
        return BoundaryVerification(original, original, "needs_review", 0.38, safety.reason)
    return BoundaryVerification(original, original, "provisional", 0.62, safety.reason)


def refine_major_boundaries(
    chapters: Iterable[ChapterMetadata],
    phrases: Iterable[PackedPhrase] | None = None,
    gaps: Iterable[TimelineGap] | None = None,
    scene_changes: Iterable[SceneChange] | None = None,
    *,
    search_window: float = 1.5,
) -> list[ChapterMetadata]:
    """Refine adjacent chapter boundaries while keeping chapter order stable."""
    ordered = sorted(list(chapters or ()), key=lambda chapter: (chapter.start, chapter.end, chapter.chapter_id))
    if not ordered:
        return []
    refined = list(ordered)

    for index in range(len(refined) - 1):
        left = refined[index]
        right = refined[index + 1]
        proposed = max(left.start, min(left.end, right.start))
        verification = verify_major_boundary(
            proposed,
            phrases=phrases,
            gaps=gaps,
            scene_changes=scene_changes,
            search_window=search_window,
        )
        adjusted = max(left.start, min(right.end, verification.adjusted_time))
        status = str(verification.status)
        needs_review = status == "needs_review"
        reason = f"boundary:{verification.reason}"
        refined[index] = replace(
            left,
            end=max(left.start, adjusted),
            boundary_status=status,
            confidence=max(left.confidence, verification.confidence),
            needs_review=left.needs_review or needs_review,
            story_reason="; ".join(part for part in (left.story_reason, reason) if part),
        )
        refined[index + 1] = replace(
            right,
            start=max(0.0, adjusted),
            boundary_status=status,
            confidence=max(right.confidence, verification.confidence),
            needs_review=right.needs_review or needs_review,
            story_reason="; ".join(part for part in (right.story_reason, reason) if part),
        )

    return refined


__all__ = ["BoundaryVerification", "refine_major_boundaries", "verify_major_boundary"]
