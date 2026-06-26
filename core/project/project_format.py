from __future__ import annotations

from typing import Any

from core.coerce import safe_float as _safe_float, safe_round_int as _safe_int
from core.frame_time import frame_count, frame_duration, normalize_fps
from core.project.project_roughcut_store import (
    compact_project_roughcut_payload,
    hydrate_project_roughcut_payload,
)

PROJECT_SCHEMA_VERSION = "04.00.18"
PROJECT_STORAGE_SCHEMA = "ai_subtitle_studio.project.v5"
PROJECT_VIDEO_SCHEMA = "ai_subtitle_studio.project.video_header.v1"

def _timeline_clips(project: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []
    timeline = project.get("timeline", {}) if isinstance(project.get("timeline"), dict) else {}
    tracks = timeline.get("tracks", []) if isinstance(timeline.get("tracks"), list) else []
    if not tracks:
        return []
    track = tracks[0] if isinstance(tracks[0], dict) else {}
    clips = track.get("clips", []) if isinstance(track.get("clips"), list) else []
    return [clip for clip in clips if isinstance(clip, dict)]


def _timeline_total_duration(project: dict[str, Any] | None) -> float:
    if not isinstance(project, dict):
        return 0.0
    timeline = project.get("timeline", {}) if isinstance(project.get("timeline"), dict) else {}
    total_duration = _safe_float(timeline.get("total_duration"), 0.0)
    if total_duration > 0.0:
        return total_duration
    return max(
        (
            _safe_float(clip.get("timeline_end"), _safe_float(clip.get("timeline_start"), 0.0))
            for clip in _timeline_clips(project)
        ),
        default=0.0,
    )


def project_video_header(project: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(project, dict):
        return {}
    video = project.get("video")
    return dict(video) if isinstance(video, dict) else {}


def project_primary_fps(project: dict[str, Any] | None, default: float = 30.0) -> float:
    if isinstance(project, dict):
        for clip in _timeline_clips(project):
            clip_fps = _safe_float(clip.get("fps", clip.get("source_frame_rate")), 0.0)
            if clip_fps > 0.0:
                return normalize_fps(clip_fps)
        timeline = project.get("timeline", {}) if isinstance(project.get("timeline"), dict) else {}
        timebase = timeline.get("timebase", {}) if isinstance(timeline.get("timebase"), dict) else {}
        fps = _safe_float(timebase.get("primary_fps"), 0.0)
        if fps > 0.0:
            return normalize_fps(fps)
    video = project_video_header(project)
    fps = _safe_float(video.get("primary_fps"), 0.0)
    if fps > 0.0:
        return normalize_fps(fps)
    timebase = video.get("timebase", {}) if isinstance(video.get("timebase"), dict) else {}
    fps = _safe_float(timebase.get("primary_fps"), 0.0)
    if fps > 0.0:
        return normalize_fps(fps)
    return normalize_fps(default)


def project_total_duration(project: dict[str, Any] | None, default: float = 0.0) -> float:
    if isinstance(project, dict):
        duration = _timeline_total_duration(project)
        if duration > 0.0:
            return duration
    video = project_video_header(project)
    duration = _safe_float(video.get("duration_sec"), 0.0)
    if duration > 0.0:
        return duration
    return max(0.0, float(default))


def refresh_project_video_header(project: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(project, dict):
        return {}
    clips = _timeline_clips(project)
    primary_fps = project_primary_fps(project)
    total_duration = _timeline_total_duration(project)
    total_frames = frame_count(total_duration, primary_fps)
    primary_frame_duration = frame_duration(primary_fps)
    first_clip = clips[0] if clips else {}
    width = _safe_int(first_clip.get("width"), 0)
    height = _safe_int(first_clip.get("height"), 0)
    media_kind = str(first_clip.get("type") or ("video" if width and height else "audio") or "video")
    clip_items: list[dict[str, Any]] = []
    for idx, clip in enumerate(clips):
        clip_fps = normalize_fps(clip.get("fps") or clip.get("source_frame_rate") or primary_fps)
        start = _safe_float(clip.get("timeline_start"), 0.0)
        end = _safe_float(clip.get("timeline_end"), start)
        duration = max(0.0, _safe_float(clip.get("source_duration"), end - start))
        start_frame = _safe_int(clip.get("timeline_start_frame"), 0)
        end_frame = _safe_int(
            clip.get("timeline_end_frame"),
            frame_count(max(0.0, end), primary_fps),
        )
        frame_total = _safe_int(
            clip.get("source_frame_count"),
            frame_count(duration, clip_fps),
        )
        item = {
            "id": str(clip.get("id") or f"clip_{idx + 1:04d}"),
            "order": int(clip.get("order", idx) or idx),
            "path": str(clip.get("source_path") or ""),
            "type": str(clip.get("type") or media_kind or "video"),
            "duration_sec": duration,
            "fps": clip_fps,
            "frame_count": frame_total,
            "width": _safe_int(clip.get("width"), 0),
            "height": _safe_int(clip.get("height"), 0),
            "timeline_start_sec": start,
            "timeline_end_sec": max(start, end),
            "timeline_start_frame": start_frame,
            "timeline_end_frame": end_frame,
        }
        clip_items.append(item)
    header = {
        "schema": PROJECT_VIDEO_SCHEMA,
        "primary_path": str(first_clip.get("source_path") or ""),
        "media_kind": media_kind,
        "duration_sec": total_duration,
        "primary_fps": primary_fps,
        "frame_duration": primary_frame_duration,
        "total_frames": total_frames,
        "width": width,
        "height": height,
        "resolution": f"{width}x{height}" if width and height else "",
        "clip_count": len(clip_items),
        "clips": clip_items,
        "timebase": {
            "unit": "frame",
            "canonical_unit": "frame",
            "mode": "project_video_header",
            "primary_fps": primary_fps,
            "frame_duration": primary_frame_duration,
            "timeline_start_frame": 0,
            "timeline_end_frame": total_frames,
            "total_frames": total_frames,
            "seconds_are_derived": True,
            "time_fields_are_compatibility": False,
        },
    }
    project["video"] = header
    timeline = project.setdefault("timeline", {})
    if isinstance(timeline, dict):
        timeline["total_duration"] = total_duration
        timeline["timebase"] = dict(header["timebase"])
    project["storage_schema"] = PROJECT_STORAGE_SCHEMA
    project["version"] = PROJECT_SCHEMA_VERSION
    return header


def hydrate_project_runtime_views(project: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(project, dict):
        return project
    header = project_video_header(project)
    if not header:
        header = refresh_project_video_header(project)
    timebase = dict(header.get("timebase", {}) or {})
    primary_fps = project_primary_fps(project)
    total_duration = project_total_duration(project)
    timeline = project.setdefault("timeline", {})
    if isinstance(timeline, dict):
        timeline["total_duration"] = total_duration
        timeline["timebase"] = dict(timebase)
        tracks = timeline.get("tracks", []) if isinstance(timeline.get("tracks"), list) else []
        if tracks:
            clips = tracks[0].get("clips", []) if isinstance(tracks[0], dict) and isinstance(tracks[0].get("clips"), list) else []
            clip_index = {
                str(item.get("id") or item.get("path") or ""): item
                for item in list(header.get("clips") or [])
                if isinstance(item, dict)
            }
            for idx, clip in enumerate(clips):
                if not isinstance(clip, dict):
                    continue
                key = str(clip.get("id") or clip.get("source_path") or "")
                clip_info = clip_index.get(key)
                if clip_info is None and idx < len(header.get("clips") or []):
                    candidate = header["clips"][idx]
                    clip_info = candidate if isinstance(candidate, dict) else None
                if not isinstance(clip_info, dict):
                    continue
                clip["fps"] = normalize_fps(clip_info.get("fps") or clip.get("fps") or primary_fps)
                clip["source_frame_rate"] = clip["fps"]
                clip["source_duration"] = _safe_float(clip_info.get("duration_sec"), clip.get("source_duration", 0.0))
                clip["width"] = _safe_int(clip_info.get("width"), clip.get("width", 0))
                clip["height"] = _safe_int(clip_info.get("height"), clip.get("height", 0))
                clip["source_frame_count"] = _safe_int(clip_info.get("frame_count"), clip.get("source_frame_count", 0))
                clip["timeline_start_frame"] = _safe_int(clip_info.get("timeline_start_frame"), clip.get("timeline_start_frame", 0))
                clip["timeline_end_frame"] = _safe_int(clip_info.get("timeline_end_frame"), clip.get("timeline_end_frame", 0))
    project["frame_timebase"] = dict(timebase)
    media_rows: list[dict[str, Any]] = []
    for clip in _timeline_clips(project):
        media_rows.append(
            {
                "order": int(clip.get("order", len(media_rows)) or len(media_rows)),
                "path": str(clip.get("source_path") or ""),
                "type": str(clip.get("type") or header.get("media_kind") or "video"),
                "duration": _safe_float(clip.get("source_duration"), 0.0),
                "offset": _safe_float(clip.get("timeline_start"), 0.0),
                "fps": normalize_fps(clip.get("fps") or primary_fps),
                "width": _safe_int(clip.get("width"), 0),
                "height": _safe_int(clip.get("height"), 0),
                "frame_count": _safe_int(clip.get("source_frame_count"), 0),
                "offset_frame": _safe_int(clip.get("timeline_start_frame"), 0),
                "timeline_start_frame": _safe_int(clip.get("timeline_start_frame"), 0),
                "timeline_end_frame": _safe_int(clip.get("timeline_end_frame"), 0),
            }
        )
    project["media"] = media_rows
    editor_state = project.get("editor_state")
    if isinstance(editor_state, dict):
        editor_state["frame_timebase"] = dict(timebase)
        editor_state["media_files"] = [str(item.get("path") or "") for item in media_rows if item.get("path")]
    hydrate_project_roughcut_payload(project, primary_fps=primary_fps)
    project["mode"] = "multiclip" if len(media_rows) > 1 else "single"
    project["storage_schema"] = PROJECT_STORAGE_SCHEMA
    project["version"] = PROJECT_SCHEMA_VERSION
    return project


def build_storage_project_payload(project: dict[str, Any]) -> dict[str, Any]:
    payload = dict(project or {})
    header = refresh_project_video_header(payload)
    payload["video"] = header
    compact_project_roughcut_payload(payload, primary_fps=project_primary_fps(payload))
    payload["storage_schema"] = PROJECT_STORAGE_SCHEMA
    payload["version"] = PROJECT_SCHEMA_VERSION
    payload.pop("frame_timebase", None)
    payload.pop("media", None)
    payload.pop("project_path", None)
    payload.pop("_nle_project_state", None)
    payload.pop("nle", None)
    payload.pop("nle_snapshot", None)
    editor_state = payload.get("editor_state")
    if isinstance(editor_state, dict):
        editor_state = dict(editor_state)
        editor_state.pop("frame_timebase", None)
        payload["editor_state"] = editor_state
    ordered: dict[str, Any] = {}
    priority = [
        "video",
        "app",
        "version",
        "phase",
        "project_name",
        "storage_schema",
        "created_at",
        "updated_at",
        "mode",
        "timeline",
        "subtitles",
        "asset_storage",
        "editor_state",
        "analysis",
        "middle_segments",
        "preliminary_middle_segments",
        "roughcut_state",
        "roughcut",
        "roughcut_draft",
        "roughcut_result",
        "roughcut_segments",
        "workspace",
        "user_settings",
        "model_settings",
        "history",
    ]
    for key in priority:
        if key in payload:
            ordered[key] = payload[key]
    for key, value in payload.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


__all__ = [
    "PROJECT_SCHEMA_VERSION",
    "PROJECT_STORAGE_SCHEMA",
    "PROJECT_VIDEO_SCHEMA",
    "build_storage_project_payload",
    "hydrate_project_runtime_views",
    "project_primary_fps",
    "project_total_duration",
    "project_video_header",
    "refresh_project_video_header",
]
