from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import os
from typing import Any

from core.cut_boundary import normalize_cut_boundaries, project_cut_boundaries
from core.frame_time import normalize_fps
from core.project.project_context import (
    project_clip_boundaries,
    project_media_files,
    project_segments_to_editor,
)
from core.project.project_format import project_primary_fps, project_total_duration
from core.project.project_roughcut_store import selected_roughcut_candidate
from core.roughcut.models import EDLSegment
from core.roughcut.renderer_skeleton import RenderCommandPlan, build_concat_render_plan

NLE_SNAPSHOT_SCHEMA = "ai_subtitle_studio.nle_snapshot.v1"


@dataclass(frozen=True, slots=True)
class ProjectAsset:
    asset_id: str
    path: str
    kind: str = "media"
    duration: float = 0.0
    fps: float = 30.0
    width: int = 0
    height: int = 0
    missing: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Clip:
    clip_id: str
    asset_id: str
    source_start: float
    source_end: float
    sequence_start: float
    sequence_end: float
    clip_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CaptionSegment:
    caption_id: str
    sequence_start: float
    sequence_end: float
    text: str
    speaker: str = ""
    line: int = 0
    clip_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TimelineMarker:
    marker_id: str
    kind: str
    time: float
    time_domain: str = "sequence"
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Track:
    track_id: str
    kind: str
    item_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Sequence:
    sequence_id: str
    name: str
    duration: float
    fps: float
    tracks: tuple[Track, ...] = ()
    clips: tuple[Clip, ...] = ()
    captions: tuple[CaptionSegment, ...] = ()
    markers: tuple[TimelineMarker, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RenderPlan:
    plan_id: str
    output_path: str = ""
    render_mode: str = ""
    output_duration: float = 0.0
    segments: tuple[dict[str, Any], ...] = ()
    segment_manifest: tuple[dict[str, Any], ...] = ()
    stitched_cut_boundaries: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NLESnapshot:
    schema: str
    source_project_path: str
    assets: tuple[ProjectAsset, ...]
    sequences: tuple[Sequence, ...]
    render_plans: tuple[RenderPlan, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return _as_float(value, 0.0)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return _as_int(value, 0)


def _copy_metadata(row: dict[str, Any], *, drop: set[str]) -> dict[str, Any]:
    return deepcopy({str(key): value for key, value in row.items() if str(key) not in drop})


def _timeline_clips(project: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = project.get("timeline") if isinstance(project.get("timeline"), dict) else {}
    tracks = timeline.get("tracks") if isinstance(timeline.get("tracks"), list) else []
    if not tracks:
        return []
    first_track = tracks[0] if isinstance(tracks[0], dict) else {}
    clips = first_track.get("clips") if isinstance(first_track.get("clips"), list) else []
    return [dict(clip) for clip in clips if isinstance(clip, dict)]


def _asset_id_for_clip(clip: dict[str, Any], index: int) -> str:
    raw = str(clip.get("asset_id") or clip.get("id") or clip.get("source_path") or "").strip()
    return raw or f"asset_{index + 1:04d}"


def _build_assets_and_clips(project: dict[str, Any], *, fps: float, duration: float) -> tuple[tuple[ProjectAsset, ...], tuple[Clip, ...]]:
    raw_clips = _timeline_clips(project)
    if not raw_clips:
        media_files = project_media_files(project)
        if media_files:
            clip_duration = duration
            raw_clips = [
                {
                    "id": f"clip_{index + 1:04d}",
                    "source_path": path,
                    "source_duration": clip_duration if len(media_files) == 1 else 0.0,
                    "timeline_start": 0.0,
                    "timeline_end": clip_duration if len(media_files) == 1 else 0.0,
                    "fps": fps,
                    "type": "video",
                    "order": index,
                }
                for index, path in enumerate(media_files)
            ]

    assets_by_id: dict[str, ProjectAsset] = {}
    clips: list[Clip] = []
    for index, clip in enumerate(raw_clips):
        asset_id = _asset_id_for_clip(clip, index)
        path = str(clip.get("source_path") or clip.get("path") or "")
        clip_fps = normalize_fps(clip.get("fps") or clip.get("source_frame_rate") or fps)
        source_duration = _as_float(
            clip.get("source_duration", clip.get("duration", clip.get("duration_sec", 0.0))),
            0.0,
        )
        sequence_start = _as_float(clip.get("timeline_start", clip.get("timeline_start_sec", 0.0)), 0.0)
        sequence_end = _as_float(
            clip.get("timeline_end", clip.get("timeline_end_sec", sequence_start + source_duration)),
            sequence_start + source_duration,
        )
        source_start = _as_float(clip.get("source_start", 0.0), 0.0)
        source_end = _as_float(clip.get("source_end", source_duration), source_duration)
        if source_end <= source_start:
            source_end = source_start + max(0.0, sequence_end - sequence_start)

        assets_by_id.setdefault(
            asset_id,
            ProjectAsset(
                asset_id=asset_id,
                path=path,
                kind=str(clip.get("type") or "media"),
                duration=max(0.0, source_duration),
                fps=clip_fps,
                width=_as_int(clip.get("width"), 0),
                height=_as_int(clip.get("height"), 0),
                missing=bool(path and not os.path.exists(path)),
                metadata=_copy_metadata(
                    clip,
                    drop={
                        "id",
                        "asset_id",
                        "source_path",
                        "path",
                        "type",
                        "source_duration",
                        "duration",
                        "duration_sec",
                        "fps",
                        "source_frame_rate",
                        "width",
                        "height",
                    },
                ),
            ),
        )
        clips.append(
            Clip(
                clip_id=str(clip.get("id") or f"clip_{index + 1:04d}"),
                asset_id=asset_id,
                source_start=max(0.0, source_start),
                source_end=max(source_start, source_end),
                sequence_start=max(0.0, sequence_start),
                sequence_end=max(sequence_start, sequence_end),
                clip_index=_as_int(clip.get("order"), index),
                metadata={
                    "boundary_span": {
                        "start": max(0.0, sequence_start),
                        "end": max(sequence_start, sequence_end),
                        "file": path,
                    },
                    **_copy_metadata(
                        clip,
                        drop={
                            "id",
                            "asset_id",
                            "source_path",
                            "path",
                            "source_start",
                            "source_end",
                            "timeline_start",
                            "timeline_end",
                            "timeline_start_sec",
                            "timeline_end_sec",
                            "order",
                        },
                    ),
                },
            )
        )
    return tuple(assets_by_id.values()), tuple(clips)


def _clip_lookup(clips: tuple[Clip, ...], project: dict[str, Any]) -> tuple[dict[int, str], dict[str, str]]:
    by_index = {clip.clip_index: clip.clip_id for clip in clips}
    by_path = {
        str(clip.metadata.get("boundary_span", {}).get("file") or ""): clip.clip_id
        for clip in clips
        if isinstance(clip.metadata.get("boundary_span"), dict)
    }
    for index, boundary in enumerate(project_clip_boundaries(project)):
        if not isinstance(boundary, dict):
            continue
        path = str(boundary.get("file") or "")
        if path and path not in by_path and index in by_index:
            by_path[path] = by_index[index]
    return by_index, by_path


def _build_captions(project: dict[str, Any], clips: tuple[Clip, ...]) -> tuple[CaptionSegment, ...]:
    by_index, by_path = _clip_lookup(clips, project)
    captions: list[CaptionSegment] = []
    for index, row in enumerate(project_segments_to_editor(project, include_analysis_candidates=False)):
        if not isinstance(row, dict) or row.get("is_gap"):
            continue
        start = _as_float(row.get("start", row.get("timeline_start", 0.0)), 0.0)
        end = _as_float(row.get("end", row.get("timeline_end", start)), start)
        clip_id = ""
        clip_idx = row.get("_clip_idx")
        if clip_idx is not None:
            clip_id = by_index.get(_as_int(clip_idx), "")
        if not clip_id:
            clip_id = by_path.get(str(row.get("_clip_file") or ""), "")
        captions.append(
            CaptionSegment(
                caption_id=str(row.get("id") or row.get("index") or f"caption_{index + 1:04d}"),
                sequence_start=max(0.0, start),
                sequence_end=max(start, end),
                text=str(row.get("text") or ""),
                speaker=str(row.get("speaker") or row.get("spk") or ""),
                line=_as_int(row.get("line"), index),
                clip_id=clip_id,
                metadata=_copy_metadata(
                    row,
                    drop={"id", "index", "line", "start", "end", "timeline_start", "timeline_end", "text", "speaker", "spk"},
                ),
            )
        )
    return tuple(captions)


def _marker_from_cut_boundary(row: dict[str, Any], *, index: int, kind: str, time_domain: str) -> TimelineMarker:
    time_value = _as_float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))), 0.0)
    return TimelineMarker(
        marker_id=str(row.get("id") or f"{kind}_{index + 1:04d}"),
        kind=kind,
        time=max(0.0, time_value),
        time_domain=time_domain,
        source=str(row.get("source") or ""),
        metadata=_copy_metadata(row, drop={"id", "time", "timeline_sec", "source"}),
    )


def _stitched_rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("stitched_cut_boundaries")
    if not rows and isinstance(payload.get("outputs"), dict):
        rows = _stitched_rows_from_payload(payload["outputs"])
    if not rows and isinstance(payload.get("edl"), dict):
        rows = payload["edl"].get("stitched_cut_boundaries")
    if not rows and isinstance(payload.get("render_plan"), dict):
        rows = payload["render_plan"].get("stitched_cut_boundaries")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def markers_from_stitched_cut_boundaries(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    primary_fps: float = 30.0,
) -> tuple[TimelineMarker, ...]:
    markers = []
    for index, row in enumerate(normalize_cut_boundaries(list(rows or []), primary_fps=primary_fps)):
        marker = _marker_from_cut_boundary(row, index=index, kind="roughcut_exact_join", time_domain="output")
        metadata = dict(marker.metadata)
        metadata["exact_join"] = {
            key: row.get(key)
            for key in (
                "output_join_index",
                "segment_before_id",
                "segment_after_id",
                "chapter_before_id",
                "chapter_after_id",
                "source_before_path",
                "source_after_path",
                "output_before_end",
                "output_after_start",
                "timeline_before_end",
                "timeline_after_start",
                "join_gap_sec",
            )
            if row.get(key) not in (None, "")
        }
        markers.append(
            TimelineMarker(
                marker_id=marker.marker_id,
                kind=marker.kind,
                time=marker.time,
                time_domain=marker.time_domain,
                source=marker.source,
                metadata=metadata,
            )
        )
    return tuple(markers)


def markers_from_roughcut_sidecar_payload(payload: dict[str, Any], *, primary_fps: float = 30.0) -> tuple[TimelineMarker, ...]:
    return markers_from_stitched_cut_boundaries(_stitched_rows_from_payload(payload), primary_fps=primary_fps)


def _build_markers(project: dict[str, Any], selected_candidate: dict[str, Any]) -> tuple[TimelineMarker, ...]:
    markers: list[TimelineMarker] = []
    primary_fps = project_primary_fps(project)
    for index, row in enumerate(project_cut_boundaries(project, primary_fps=primary_fps)):
        markers.append(_marker_from_cut_boundary(row, index=index, kind="cut_boundary", time_domain="sequence"))

    editor_state = project.get("editor_state") if isinstance(project.get("editor_state"), dict) else {}
    multiclip = editor_state.get("multiclip") if isinstance(editor_state.get("multiclip"), dict) else {}
    provisional = multiclip.get("cut_boundary_provisional_boundaries")
    if isinstance(provisional, list):
        base_index = len(markers)
        for offset, row in enumerate(normalize_cut_boundaries(provisional, primary_fps=project_primary_fps(project))):
            markers.append(_marker_from_cut_boundary(row, index=base_index + offset, kind="provisional_cut_boundary", time_domain="sequence"))

    exact_rows = _stitched_rows_from_payload(selected_candidate)
    seen_exact: set[tuple[float, str, str]] = set()
    for marker in markers_from_stitched_cut_boundaries(exact_rows, primary_fps=primary_fps):
        exact = marker.metadata.get("exact_join") if isinstance(marker.metadata, dict) else {}
        key = (
            round(float(marker.time), 3),
            str(exact.get("segment_before_id", "")) if isinstance(exact, dict) else "",
            str(exact.get("segment_after_id", "")) if isinstance(exact, dict) else "",
        )
        if key in seen_exact:
            continue
        seen_exact.add(key)
        markers.append(marker)
    return tuple(markers)


def _edl_duration(edl_payload: dict[str, Any]) -> float:
    duration = _as_float(edl_payload.get("duration"), 0.0)
    if duration > 0.0:
        return duration
    segments = edl_payload.get("segments")
    if isinstance(segments, list):
        return max((_as_float(row.get("output_end"), 0.0) for row in segments if isinstance(row, dict)), default=0.0)
    return 0.0


def _build_render_plans(selected_candidate: dict[str, Any]) -> tuple[RenderPlan, ...]:
    if not selected_candidate:
        return ()
    outputs = selected_candidate.get("outputs") if isinstance(selected_candidate.get("outputs"), dict) else {}
    render_payload = outputs.get("render_plan") if isinstance(outputs.get("render_plan"), dict) else {}
    edl_payload = outputs.get("edl") if isinstance(outputs.get("edl"), dict) else {}
    if not render_payload and not edl_payload:
        return ()
    segments = tuple(dict(row) for row in list(edl_payload.get("segments") or []) if isinstance(row, dict))
    manifest = tuple(dict(row) for row in list(render_payload.get("segment_manifest") or []) if isinstance(row, dict))
    stitched = _stitched_rows_from_payload(render_payload) or _stitched_rows_from_payload(edl_payload)
    output_duration = _edl_duration(edl_payload)
    if output_duration <= 0.0:
        output_duration = max((_as_float(row.get("output_end"), 0.0) for row in manifest), default=0.0)
    return (
        RenderPlan(
            plan_id=str(selected_candidate.get("candidate_id") or "roughcut_render_plan"),
            output_path=str(render_payload.get("output_path") or ""),
            render_mode=str(render_payload.get("render_mode") or ""),
            output_duration=max(0.0, output_duration),
            segments=segments,
            segment_manifest=manifest,
            stitched_cut_boundaries=tuple(stitched),
            metadata={
                "candidate_id": str(selected_candidate.get("candidate_id") or ""),
                "candidate_name": str(selected_candidate.get("name") or ""),
                "edl_duration": _as_float(edl_payload.get("duration"), 0.0) if edl_payload else 0.0,
            },
        ),
    )


def _select_render_plan(snapshot: NLESnapshot, plan_id: str = "") -> RenderPlan:
    for plan in snapshot.render_plans:
        if not plan_id or plan.plan_id == plan_id:
            return plan
    raise ValueError("nle_render_plan_missing")


def _edl_segment_from_snapshot_row(row: dict[str, Any], *, index: int) -> EDLSegment:
    segment_id = str(row.get("segment_id") or row.get("chapter_id") or f"segment_{index + 1:04d}")
    return EDLSegment(
        source_path=str(row.get("source_path") or row.get("path") or ""),
        segment_id=segment_id,
        source_start=_as_float(row.get("source_start"), 0.0),
        source_end=_as_float(row.get("source_end"), 0.0),
        output_start=_as_float(row.get("output_start"), 0.0),
        output_end=_as_float(row.get("output_end"), 0.0),
        action=str(row.get("action") or "keep"),
        chapter_id=str(row.get("chapter_id")) if row.get("chapter_id") not in (None, "") else None,
        story_role=str(row.get("story_role") or ""),
        reason=str(row.get("reason") or ""),
        timeline_start=_optional_float(row.get("timeline_start")),
        timeline_end=_optional_float(row.get("timeline_end")),
        clip_index=_optional_int(row.get("clip_index")),
    )


def edl_segments_from_render_plan_snapshot(snapshot: NLESnapshot, *, plan_id: str = "") -> tuple[EDLSegment, ...]:
    plan = _select_render_plan(snapshot, plan_id=plan_id)
    return tuple(
        _edl_segment_from_snapshot_row(row, index=index)
        for index, row in enumerate(plan.segments)
        if isinstance(row, dict)
    )


def build_concat_render_plan_from_snapshot(
    snapshot: NLESnapshot,
    output_path: str,
    temp_dir: str,
    *,
    plan_id: str = "",
    ffmpeg_binary: str = "ffmpeg",
    render_mode: str | None = None,
) -> RenderCommandPlan:
    plan = _select_render_plan(snapshot, plan_id=plan_id)
    mode = render_mode if render_mode is not None else plan.render_mode
    return build_concat_render_plan(
        edl_segments_from_render_plan_snapshot(snapshot, plan_id=plan.plan_id),
        output_path,
        temp_dir,
        ffmpeg_binary=ffmpeg_binary,
        render_mode=mode,
    )


def build_project_nle_snapshot(project: dict[str, Any], *, project_path: str = "") -> NLESnapshot:
    source = deepcopy(project if isinstance(project, dict) else {})
    fps = project_primary_fps(source)
    duration = project_total_duration(source)
    assets, clips = _build_assets_and_clips(source, fps=fps, duration=duration)
    captions = _build_captions(source, clips)
    selected_candidate = selected_roughcut_candidate(source.get("roughcut_state"))
    markers = _build_markers(source, selected_candidate)
    render_plans = _build_render_plans(selected_candidate)
    sequence_duration = max(
        duration,
        max((clip.sequence_end for clip in clips), default=0.0),
        max((caption.sequence_end for caption in captions), default=0.0),
    )
    tracks = (
        Track("track_media_0001", "media", tuple(clip.clip_id for clip in clips)),
        Track("track_caption_0001", "captions", tuple(caption.caption_id for caption in captions)),
        Track("track_markers_0001", "markers", tuple(marker.marker_id for marker in markers)),
    )
    sequence = Sequence(
        sequence_id="sequence_default",
        name=str(source.get("project_name") or "Default Sequence"),
        duration=round(sequence_duration, 6),
        fps=normalize_fps(fps),
        tracks=tracks,
        clips=clips,
        captions=captions,
        markers=markers,
        metadata={
            "source": "project_snapshot_adapter",
            "project_mode": str(source.get("mode") or ""),
            "time_model": {
                "source_time": "asset-local seconds",
                "sequence_time": "project timeline seconds",
                "output_time": "rendered roughcut/export seconds",
            },
        },
    )
    return NLESnapshot(
        schema=NLE_SNAPSHOT_SCHEMA,
        source_project_path=str(project_path or source.get("_project_file_path") or source.get("project_path") or ""),
        assets=assets,
        sequences=(sequence,),
        render_plans=render_plans,
        metadata={
            "read_only": True,
            "asset_count": len(assets),
            "caption_count": len(captions),
            "marker_count": len(markers),
            "render_plan_count": len(render_plans),
        },
    )


__all__ = [
    "CaptionSegment",
    "Clip",
    "NLE_SNAPSHOT_SCHEMA",
    "NLESnapshot",
    "ProjectAsset",
    "RenderPlan",
    "Sequence",
    "TimelineMarker",
    "Track",
    "build_project_nle_snapshot",
    "build_concat_render_plan_from_snapshot",
    "edl_segments_from_render_plan_snapshot",
    "markers_from_roughcut_sidecar_payload",
    "markers_from_stitched_cut_boundaries",
]
