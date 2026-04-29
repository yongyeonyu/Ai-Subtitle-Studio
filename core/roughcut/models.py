# Version: 03.00.26
# Phase: PHASE2
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Literal


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class SubtitleSegment:
    start: float
    end: float
    text: str
    speaker: str | None = None
    words: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    subtitle_id: int | None = None

    def __post_init__(self) -> None:
        start = max(0.0, _coerce_float(self.start))
        end = max(start, _coerce_float(self.end, start))
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "text", str(self.text or "").strip())
        object.__setattr__(self, "words", tuple(self.words or ()))

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class VisualSceneNote:
    start: float
    end: float
    text: str
    source: str = "local"
    confidence: float = 0.0
    needs_review: bool = True
    thumbnail_path: str | None = None

    def __post_init__(self) -> None:
        start = max(0.0, _coerce_float(self.start))
        end = max(start, _coerce_float(self.end, start))
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "text", str(self.text or "").strip())
        object.__setattr__(self, "confidence", max(0.0, min(1.0, _coerce_float(self.confidence))))


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    event_id: str
    start: float
    end: float
    event_type: Literal["subtitle", "visual_scene_note", "gap"]
    text: str = ""
    subtitle_ids: tuple[int, ...] = field(default_factory=tuple)
    note: VisualSceneNote | None = None

    def __post_init__(self) -> None:
        start = max(0.0, _coerce_float(self.start))
        end = max(start, _coerce_float(self.end, start))
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class PackedPhrase:
    phrase_id: str
    start: float
    end: float
    text: str
    speaker: str | None = None
    source_indices: tuple[int, ...] = field(default_factory=tuple)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class SemanticChunk:
    chunk_id: str
    start: float
    end: float
    phrase_ids: tuple[str, ...] = field(default_factory=tuple)
    source_indices: tuple[int, ...] = field(default_factory=tuple)
    text: str = ""
    keywords: tuple[str, ...] = field(default_factory=tuple)
    topic_shift_score: float = 0.0
    title: str = ""
    summary: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class ChapterBoundaryCandidate:
    start: float
    end: float
    score: float
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RoughCutSegment:
    segment_id: str
    start: float
    end: float
    subtitle_ids: tuple[int, ...] = field(default_factory=tuple)
    timeline_event_ids: tuple[str, ...] = field(default_factory=tuple)
    thumbnail_path: str | None = None
    preview_path: str | None = None
    title: str = ""
    summary: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    story_role: str = ""
    narrative_function: str = ""
    importance_score: float = 0.0
    can_move: bool = True
    can_trim: bool = True
    can_remove: bool = True
    move_risk: Literal["low", "medium", "high"] = "low"
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    needs_review: bool = False
    boundary_confidence: float = 0.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class ChapterMetadata:
    chapter_id: str
    title: str
    start: float
    end: float
    summary: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    segment_ids: tuple[str, ...] = field(default_factory=tuple)
    importance_score: float = 0.0
    narrative_function: str = ""
    story_role: str = ""
    story_reason: str = ""
    move_recommendation: str = ""
    role_confidence: float = 0.0
    needs_review: bool = False


@dataclass(frozen=True, slots=True)
class StoryboardCandidate:
    candidate_id: str
    title: str
    mode: str
    segment_order: tuple[str, ...]
    estimated_duration: float
    target_duration: float | None = None
    removed_segments: tuple[str, ...] = field(default_factory=tuple)
    trimmed_segments: tuple[str, ...] = field(default_factory=tuple)
    story_summary: str = ""
    strengths: tuple[str, ...] = field(default_factory=tuple)
    risks: tuple[str, ...] = field(default_factory=tuple)
    recommended_for: str = ""


@dataclass(frozen=True, slots=True)
class StoryboardPlan:
    plan_id: str
    candidates: tuple[StoryboardCandidate, ...] = field(default_factory=tuple)
    selected_candidate_id: str | None = None


@dataclass(frozen=True, slots=True)
class EditDecision:
    segment_id: str
    action: Literal["keep", "trim", "remove", "highlight", "move"]
    reason: str = ""
    source_start: float | None = None
    source_end: float | None = None
    output_order: int | None = None
    safety: Literal["ideal", "acceptable", "risky"] = "acceptable"


@dataclass(frozen=True, slots=True)
class EDLSegment:
    source_path: str
    segment_id: str
    source_start: float
    source_end: float
    output_start: float
    output_end: float
    action: str = "keep"
    chapter_id: str | None = None
    story_role: str = ""
    reason: str = ""
    timeline_start: float | None = None
    timeline_end: float | None = None
    clip_index: int | None = None


@dataclass(frozen=True, slots=True)
class RoughCutResult:
    segments: tuple[RoughCutSegment, ...] = field(default_factory=tuple)
    chapters: tuple[ChapterMetadata, ...] = field(default_factory=tuple)
    storyboard_plan: StoryboardPlan | None = None
    edit_decisions: tuple[EditDecision, ...] = field(default_factory=tuple)
    edl_segments: tuple[EDLSegment, ...] = field(default_factory=tuple)
    guide_markdown: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)


def subtitle_from_dict(data: dict[str, Any], fallback_id: int | None = None) -> SubtitleSegment:
    """Adapt existing subtitle dicts into the Phase2 roughcut model."""
    return SubtitleSegment(
        start=_coerce_float(data.get("start")),
        end=_coerce_float(data.get("end")),
        text=str(data.get("text") or ""),
        speaker=data.get("speaker") or data.get("speaker_name"),
        words=tuple(data.get("words") or ()),
        subtitle_id=data.get("subtitle_id") if data.get("subtitle_id") is not None else fallback_id,
    )


def subtitles_from_dicts(items: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> tuple[SubtitleSegment, ...]:
    return tuple(
        subtitle_from_dict(item, fallback_id=index)
        for index, item in enumerate(items)
        if item and not item.get("is_gap")
    )


def _dataclass_kwargs(cls, data: dict[str, Any]) -> dict[str, Any]:
    return {item.name: data[item.name] for item in fields(cls) if item.name in data}


def _tuple_fields(data: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    out = dict(data)
    for name in names:
        if name in out:
            out[name] = tuple(out.get(name) or ())
    return out


def roughcut_result_from_dict(data: dict[str, Any] | None) -> RoughCutResult:
    """Restore a RoughCutResult saved inside project roughcut_state."""
    data = data or {}
    chapters = tuple(
        ChapterMetadata(**_dataclass_kwargs(ChapterMetadata, _tuple_fields(item, ("tags", "segment_ids"))))
        for item in data.get("chapters", []) or []
        if isinstance(item, dict)
    )
    decisions = tuple(
        EditDecision(**_dataclass_kwargs(EditDecision, item))
        for item in data.get("edit_decisions", []) or []
        if isinstance(item, dict)
    )
    edl_segments = tuple(
        EDLSegment(**_dataclass_kwargs(EDLSegment, item))
        for item in data.get("edl_segments", []) or []
        if isinstance(item, dict)
    )
    segments = tuple(
        RoughCutSegment(
            **_dataclass_kwargs(
                RoughCutSegment,
                _tuple_fields(item, ("subtitle_ids", "timeline_event_ids", "tags", "dependencies")),
            )
        )
        for item in data.get("segments", []) or []
        if isinstance(item, dict)
    )
    return RoughCutResult(
        segments=segments,
        chapters=chapters,
        edit_decisions=decisions,
        edl_segments=edl_segments,
        guide_markdown=str(data.get("guide_markdown", "") or ""),
        warnings=tuple(data.get("warnings", []) or ()),
    )
