# Version: 03.01.32
# Phase: PHASE2
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable

from .models import ChapterMetadata, EDLSegment, EditDecision, RoughCutSegment


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _item_id(item: ChapterMetadata | RoughCutSegment) -> str:
    return getattr(item, "segment_id", "") or getattr(item, "chapter_id", "")


def _item_lookup(items: Iterable[ChapterMetadata | RoughCutSegment] | None) -> dict[str, ChapterMetadata | RoughCutSegment]:
    lookup: dict[str, ChapterMetadata | RoughCutSegment] = {}
    for item in items or ():
        item_id = _item_id(item)
        if item_id:
            lookup[item_id] = item
    return lookup


def _chapter_id(item: ChapterMetadata | RoughCutSegment | None, fallback_id: str) -> str | None:
    if item is None:
        return fallback_id if fallback_id.startswith("chapter_") else None
    return getattr(item, "chapter_id", None) or (fallback_id if fallback_id.startswith("chapter_") else None)


def _story_role(item: ChapterMetadata | RoughCutSegment | None) -> str:
    return str(getattr(item, "story_role", "") or "") if item is not None else ""


def _source_range(decision: EditDecision, item: ChapterMetadata | RoughCutSegment | None) -> tuple[float, float]:
    fallback_start = _as_float(getattr(item, "start", 0.0), 0.0) if item is not None else 0.0
    fallback_end = _as_float(getattr(item, "end", fallback_start), fallback_start) if item is not None else fallback_start
    start = _as_float(decision.source_start, fallback_start) if decision.source_start is not None else fallback_start
    end = _as_float(decision.source_end, fallback_end) if decision.source_end is not None else fallback_end
    return max(0.0, start), max(max(0.0, start), end)


def build_edl_segments(
    source_path: str,
    decisions: Iterable[EditDecision],
    items: Iterable[ChapterMetadata | RoughCutSegment] | None = None,
    min_duration: float = 0.05,
) -> list[EDLSegment]:
    """Convert edit decisions into executable EDL segments, excluding remove decisions."""
    lookup = _item_lookup(items)
    ordered = sorted(
        list(decisions),
        key=lambda decision: (
            decision.output_order if decision.output_order is not None else 10_000_000,
            decision.source_start if decision.source_start is not None else 0.0,
            decision.segment_id,
        ),
    )
    minimum = max(0.0, float(min_duration))
    output_cursor = 0.0
    edl: list[EDLSegment] = []

    for decision in ordered:
        if decision.action == "remove":
            continue
        item = lookup.get(decision.segment_id)
        source_start, source_end = _source_range(decision, item)
        duration = max(0.0, source_end - source_start)
        if duration < minimum:
            continue
        output_start = output_cursor
        output_end = output_start + duration
        edl.append(
            EDLSegment(
                source_path=str(source_path),
                segment_id=decision.segment_id,
                source_start=round(source_start, 3),
                source_end=round(source_end, 3),
                output_start=round(output_start, 3),
                output_end=round(output_end, 3),
                action=decision.action,
                chapter_id=_chapter_id(item, decision.segment_id),
                story_role=_story_role(item),
                reason=decision.reason,
                timeline_start=round(source_start, 3),
                timeline_end=round(source_end, 3),
            )
        )
        output_cursor = output_end

    return edl


def generate_edl(
    source_path: str,
    decisions: Iterable[EditDecision],
    items: Iterable[ChapterMetadata | RoughCutSegment] | None = None,
    min_duration: float = 0.05,
) -> list[EDLSegment]:
    """Compatibility wrapper for the public roughcut EDL contract."""
    return build_edl_segments(source_path, decisions, items=items, min_duration=min_duration)


def _boundary_items(clip_boundaries: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    items = []
    for idx, item in enumerate(clip_boundaries or ()):
        start = _as_float(item.get("start", item.get("timeline_start", 0.0)))
        end = _as_float(item.get("end", item.get("timeline_end", start)), start)
        path = str(item.get("file", item.get("source_path", "")) or "")
        if end <= start or not path:
            continue
        items.append({"index": idx, "start": start, "end": end, "file": path})
    return sorted(items, key=lambda value: (value["start"], value["end"]))


def map_edl_segments_to_clip_sources(
    edl_segments: Iterable[EDLSegment],
    clip_boundaries: Iterable[dict[str, Any]] | None,
) -> list[EDLSegment]:
    """Map global timeline EDL ranges to per-clip source paths and local times."""
    boundaries = _boundary_items(clip_boundaries)
    if not boundaries:
        return list(edl_segments or ())

    mapped: list[EDLSegment] = []
    output_cursor = 0.0
    for segment in edl_segments or ():
        global_start = _as_float(segment.timeline_start, segment.source_start)
        global_end = _as_float(segment.timeline_end, segment.source_end)
        parts: list[tuple[dict[str, Any], float, float]] = []
        for boundary in boundaries:
            start = max(global_start, boundary["start"])
            end = min(global_end, boundary["end"])
            if end > start:
                parts.append((boundary, start, end))
        if not parts:
            duration = max(0.0, global_end - global_start)
            mapped.append(
                EDLSegment(
                    source_path=segment.source_path,
                    segment_id=segment.segment_id,
                    source_start=round(segment.source_start, 3),
                    source_end=round(segment.source_end, 3),
                    output_start=round(output_cursor, 3),
                    output_end=round(output_cursor + duration, 3),
                    action=segment.action,
                    chapter_id=segment.chapter_id,
                    story_role=segment.story_role,
                    reason=segment.reason,
                    timeline_start=round(global_start, 3),
                    timeline_end=round(global_end, 3),
                    clip_index=segment.clip_index,
                )
            )
            output_cursor += duration
            continue

        for part_idx, (boundary, part_start, part_end) in enumerate(parts, start=1):
            local_start = part_start - boundary["start"]
            local_end = part_end - boundary["start"]
            duration = max(0.0, local_end - local_start)
            if duration <= 0.0:
                continue
            mapped.append(
                EDLSegment(
                    source_path=boundary["file"],
                    segment_id=segment.segment_id if len(parts) == 1 else f"{segment.segment_id}_part{part_idx}",
                    source_start=round(local_start, 3),
                    source_end=round(local_end, 3),
                    output_start=round(output_cursor, 3),
                    output_end=round(output_cursor + duration, 3),
                    action=segment.action,
                    chapter_id=segment.chapter_id,
                    story_role=segment.story_role,
                    reason=segment.reason,
                    timeline_start=round(part_start, 3),
                    timeline_end=round(part_end, 3),
                    clip_index=int(boundary["index"]),
                )
            )
            output_cursor += duration
    return mapped


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def edl_to_dict(
    edl_segments: Iterable[EDLSegment],
    metadata: dict[str, Any] | None = None,
    chapters: Iterable[ChapterMetadata] | None = None,
    major_segments: Iterable[RoughCutSegment] | None = None,
) -> dict[str, Any]:
    segments = list(edl_segments)
    duration = segments[-1].output_end if segments else 0.0
    chapter_meta = _chapter_metadata_lookup(chapters)
    major_meta = _major_metadata_lookup(major_segments)
    return {
        "schema": "ai_subtitle_studio.roughcut.edl.v1",
        "version": "03.01.32",
        "metadata": _jsonable(_edl_metadata(metadata or {}, chapters, major_segments)),
        "duration": round(duration, 3),
        "segments": [
            _jsonable(_edl_segment_payload(segment, chapter_meta=chapter_meta, major_meta=major_meta))
            for segment in segments
        ],
    }


def _edl_metadata(
    metadata: dict[str, Any],
    chapters: Iterable[ChapterMetadata] | None,
    major_segments: Iterable[RoughCutSegment] | None,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    chapter_items = list(chapters or ())
    major_items = list(major_segments or ())
    if chapter_items or major_items:
        payload["roughcut_v2"] = {
            "chapter_count": len(chapter_items),
            "major_segment_count": len(major_items),
            "has_major_minor": any(getattr(chapter, "major_id", "") or getattr(chapter, "minor_code", "") for chapter in chapter_items),
        }
    return payload


def _chapter_metadata_lookup(chapters: Iterable[ChapterMetadata] | None) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for chapter in chapters or ():
        lookup[chapter.chapter_id] = {
            "major_id": chapter.major_id,
            "minor_code": chapter.minor_code,
            "boundary_status": chapter.boundary_status,
            "confidence": chapter.confidence,
            "tags": chapter.tags,
        }
    return lookup


def _major_metadata_lookup(segments: Iterable[RoughCutSegment] | None) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for segment in segments or ():
        major_id = getattr(segment, "major_id", "") or getattr(segment, "segment_id", "")
        if not major_id:
            continue
        lookup[major_id] = {
            "major_id": major_id,
            "title": segment.title,
            "summary": segment.summary or segment.llm_summary,
            "status": segment.status,
            "safety": segment.safety,
            "importance": segment.importance or segment.importance_score,
            "tags": segment.tags,
        }
    return lookup


def _edl_segment_payload(
    segment: EDLSegment,
    *,
    chapter_meta: dict[str, dict[str, Any]],
    major_meta: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    payload = asdict(segment)
    meta = dict(chapter_meta.get(str(segment.chapter_id or segment.segment_id), {}))
    major_id = str(meta.get("major_id") or "")
    if major_id and major_id in major_meta:
        meta["major"] = major_meta[major_id]
    if meta:
        payload["metadata"] = meta
    return payload


def save_edl_json(
    path: str | Path,
    edl_segments: Iterable[EDLSegment],
    metadata: dict[str, Any] | None = None,
    chapters: Iterable[ChapterMetadata] | None = None,
    major_segments: Iterable[RoughCutSegment] | None = None,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = edl_to_dict(edl_segments, metadata=metadata, chapters=chapters, major_segments=major_segments)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
