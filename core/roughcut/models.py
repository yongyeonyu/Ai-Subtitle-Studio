# Version: 03.01.30
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
    major_id: str = ""
    minor_groups: tuple["RoughCutMinorGroup", ...] = field(default_factory=tuple)
    status: Literal["provisional", "reading", "confirmed", "needs_review"] = "confirmed"
    safety: Literal["ideal", "acceptable", "risky"] = "acceptable"
    importance: float = 0.0
    llm_summary: str = ""

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
    major_id: str = ""
    minor_code: str = ""
    confidence: float = 0.0
    boundary_status: Literal["provisional", "reading", "confirmed", "needs_review"] = "confirmed"


@dataclass(frozen=True, slots=True)
class RoughCutMinorGroup:
    minor_id: str
    major_id: str
    code: str
    title: str
    start: float
    end: float
    subtitle_ids: tuple[int, ...] = field(default_factory=tuple)
    chapter_ids: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    status: Literal["provisional", "reading", "confirmed", "needs_review"] = "provisional"
    safety: Literal["ideal", "acceptable", "risky"] = "acceptable"
    confidence: float = 0.0
    needs_review: bool = False

    def __post_init__(self) -> None:
        start = max(0.0, _coerce_float(self.start))
        end = max(start, _coerce_float(self.end, start))
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "subtitle_ids", tuple(self.subtitle_ids or ()))
        object.__setattr__(self, "chapter_ids", tuple(self.chapter_ids or ()))
        object.__setattr__(self, "tags", tuple(self.tags or ()))
        object.__setattr__(self, "confidence", max(0.0, min(1.0, _coerce_float(self.confidence))))


@dataclass(frozen=True, slots=True)
class RoughCutTitleSuggestion:
    title_id: str
    title: str
    score: float = 0.0
    reason: str = ""
    source: Literal["local", "llm", "user"] = "local"
    tags: tuple[str, ...] = field(default_factory=tuple)
    expected_reach: str = ""
    copied: bool = False
    applied: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", str(self.title or "").strip())
        object.__setattr__(self, "score", max(0.0, min(1.0, _coerce_float(self.score))))
        object.__setattr__(self, "reason", str(self.reason or "").strip())
        object.__setattr__(self, "tags", tuple(self.tags or ()))
        object.__setattr__(self, "expected_reach", str(self.expected_reach or "").strip())
        object.__setattr__(self, "copied", bool(self.copied))
        object.__setattr__(self, "applied", bool(self.applied))


@dataclass(frozen=True, slots=True)
class RoughCutDraftState:
    draft_id: str = ""
    status: Literal["idle", "analyzing", "review", "confirmed", "rendered"] = "idle"
    selected_major_id: str = ""
    selected_minor_code: str = ""
    autosave_enabled: bool = True
    last_saved_at: str = ""
    notes: str = ""


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
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class CutPoint:
    segment_id: str
    cut_time: float
    boundary: Literal["start", "end"]
    action: str = "keep"
    safety: Literal["ideal", "acceptable", "risky"] = "acceptable"
    reason: str = ""
    adjusted_time: float | None = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        cut_time = max(0.0, _coerce_float(self.cut_time))
        adjusted = None if self.adjusted_time is None else max(0.0, _coerce_float(self.adjusted_time))
        confidence = max(0.0, min(1.0, _coerce_float(self.confidence)))
        object.__setattr__(self, "cut_time", cut_time)
        object.__setattr__(self, "adjusted_time", adjusted)
        object.__setattr__(self, "confidence", confidence)


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
    video_summary: str = ""
    packed_phrases: tuple[PackedPhrase, ...] = field(default_factory=tuple)
    chunks: tuple[SemanticChunk, ...] = field(default_factory=tuple)
    cut_points: tuple[CutPoint, ...] = field(default_factory=tuple)
    title_suggestions: tuple[RoughCutTitleSuggestion, ...] = field(default_factory=tuple)
    draft_state: RoughCutDraftState | None = None
    schema_version: str = "roughcut_result.v1"

    @property
    def edl(self) -> tuple[EDLSegment, ...]:
        return self.edl_segments

    @property
    def markdown_guide(self) -> str:
        return self.guide_markdown


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


def _minor_group_from_dict(data: dict[str, Any]) -> RoughCutMinorGroup:
    return RoughCutMinorGroup(
        **_dataclass_kwargs(
            RoughCutMinorGroup,
            _tuple_fields(data, ("subtitle_ids", "chapter_ids", "tags")),
        )
    )


def _segment_from_dict(data: dict[str, Any]) -> RoughCutSegment:
    item = _tuple_fields(data, ("subtitle_ids", "timeline_event_ids", "tags", "dependencies"))
    raw_groups = item.get("minor_groups", ()) or ()
    item["minor_groups"] = tuple(
        _minor_group_from_dict(group)
        for group in raw_groups
        if isinstance(group, dict)
    )
    return RoughCutSegment(**_dataclass_kwargs(RoughCutSegment, item))


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
        for item in (data.get("edl_segments") or data.get("edl") or [])
        if isinstance(item, dict)
    )
    packed_phrases = tuple(
        PackedPhrase(**_dataclass_kwargs(PackedPhrase, _tuple_fields(item, ("source_indices",))))
        for item in data.get("packed_phrases", []) or []
        if isinstance(item, dict)
    )
    chunks = tuple(
        SemanticChunk(**_dataclass_kwargs(SemanticChunk, _tuple_fields(item, ("phrase_ids", "source_indices", "keywords"))))
        for item in data.get("chunks", []) or []
        if isinstance(item, dict)
    )
    cut_points = tuple(
        CutPoint(**_dataclass_kwargs(CutPoint, item))
        for item in data.get("cut_points", []) or []
        if isinstance(item, dict)
    )
    segments = tuple(
        _segment_from_dict(item)
        for item in data.get("segments", []) or []
        if isinstance(item, dict)
    )
    title_suggestions = tuple(
        RoughCutTitleSuggestion(**_dataclass_kwargs(RoughCutTitleSuggestion, _tuple_fields(item, ("tags",))))
        for item in data.get("title_suggestions", []) or []
        if isinstance(item, dict)
    )
    draft_data = data.get("draft_state")
    draft_state = (
        RoughCutDraftState(**_dataclass_kwargs(RoughCutDraftState, draft_data))
        if isinstance(draft_data, dict)
        else None
    )
    return RoughCutResult(
        segments=segments,
        chapters=chapters,
        storyboard_plan=None,
        edit_decisions=decisions,
        edl_segments=edl_segments,
        guide_markdown=str(data.get("guide_markdown") or data.get("markdown_guide") or ""),
        warnings=tuple(data.get("warnings", []) or ()),
        video_summary=str(data.get("video_summary", "") or ""),
        packed_phrases=packed_phrases,
        chunks=chunks,
        cut_points=cut_points,
        title_suggestions=title_suggestions,
        draft_state=draft_state,
        schema_version=str(data.get("result_schema_version") or data.get("schema_version") or data.get("schema") or "roughcut_result.v1"),
    )
