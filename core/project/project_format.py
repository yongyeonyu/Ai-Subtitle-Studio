from __future__ import annotations

from typing import Any

from core.coerce import safe_float as _safe_float, safe_round_int as _safe_int
from core.frame_time import frame_count, frame_duration, normalize_fps
from core.project.project_roughcut_store import (
    compact_project_roughcut_payload,
    hydrate_project_roughcut_payload,
)
from core.project.nle_persistence_guard import (
    NLE_PERSISTENCE_QUARANTINE_KEY,
    NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
    NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER,
    approved_final_cutover_requested,
    approved_legacy_disk_shape_replacement_requested,
    approved_nle_snapshot_canonical_load_requested,
    approved_runtime_nle_project_state_payload,
    approved_runtime_nle_project_state_persistence_requested,
    approved_top_level_nle_canonical_load_requested,
    approved_nle_snapshot_persistence_requested,
    approved_top_level_nle_persistence_requested,
    nle_final_cutover_approval_payload,
    nle_legacy_disk_shape_replacement_approval_payload,
    nle_runtime_state_persistence_approval_payload,
    nle_snapshot_canonical_load_approval_payload,
    nle_top_level_canonical_load_approval_payload,
    nle_snapshot_persistence_approval_payload,
    nle_top_level_persistence_approval_payload,
    strip_unapproved_nle_persistence_fields,
)

PROJECT_SCHEMA_VERSION = "04.01.34"
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
    strip_unapproved_nle_persistence_fields(project, source="project_format.hydrate")
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
    strip_unapproved_nle_persistence_fields(payload, source="project_format.storage")
    persist_nle_snapshot = approved_nle_snapshot_persistence_requested(payload)
    persist_top_level_nle = approved_top_level_nle_persistence_requested(payload)
    canonical_nle_snapshot = approved_nle_snapshot_canonical_load_requested(payload)
    canonical_top_level_nle = approved_top_level_nle_canonical_load_requested(payload)
    final_cutover = approved_final_cutover_requested(payload)
    replace_legacy_disk_shape = approved_legacy_disk_shape_replacement_requested(payload) or final_cutover
    legacy_replacement_rows: list[dict[str, Any]] | None = None
    persist_runtime_nle_state = (
        approved_runtime_nle_project_state_persistence_requested(payload)
        or replace_legacy_disk_shape
    )
    runtime_state_payload: dict[str, Any] | None = None
    if persist_runtime_nle_state:
        from core.project.nle_project_state import (
            NLEProjectState,
            build_project_nle_state,
            nle_project_state_to_persisted_payload,
        )

        runtime_state = payload.get("_nle_project_state")
        if isinstance(runtime_state, NLEProjectState):
            runtime_state_payload = nle_project_state_to_persisted_payload(
                runtime_state,
                source="project_format.storage",
            )
        elif approved_runtime_nle_project_state_payload(runtime_state):
            runtime_state_payload = dict(runtime_state)
        else:
            runtime_state_payload = nle_project_state_to_persisted_payload(
                build_project_nle_state(payload, project_path=""),
                source="project_format.storage",
            )
    header = refresh_project_video_header(payload)
    payload["video"] = header
    compact_project_roughcut_payload(payload, primary_fps=project_primary_fps(payload))
    payload["storage_schema"] = PROJECT_STORAGE_SCHEMA
    payload["version"] = PROJECT_SCHEMA_VERSION
    payload.pop("frame_timebase", None)
    payload.pop("media", None)
    payload.pop("project_path", None)
    payload.pop("_nle_project_state", None)
    payload.pop("_nle_snapshot_readback_parity", None)
    existing_nle_snapshot = payload.get("nle_snapshot") if isinstance(payload.get("nle_snapshot"), dict) else {}
    existing_top_level_nle = payload.get("nle") if isinstance(payload.get("nle"), dict) else {}
    payload.pop("nle", None)
    payload.pop("nle_snapshot", None)
    payload.pop(NLE_PERSISTENCE_QUARANTINE_KEY, None)
    if persist_nle_snapshot or persist_top_level_nle:
        from core.project.nle_snapshot import build_project_nle_snapshot, build_top_level_nle_shadow_payload
        from core.project.nle_snapshot import editor_rows_from_top_level_nle_payload, project_copy_with_editor_rows

        snapshot_source = payload
        if canonical_nle_snapshot:
            canonical_rows = editor_rows_from_top_level_nle_payload(existing_nle_snapshot)
            if canonical_rows:
                snapshot_source = project_copy_with_editor_rows(payload, canonical_rows)
        elif canonical_top_level_nle:
            canonical_rows = editor_rows_from_top_level_nle_payload(existing_top_level_nle)
            if canonical_rows:
                snapshot_source = project_copy_with_editor_rows(payload, canonical_rows)
        snapshot_payload = build_project_nle_snapshot(snapshot_source, project_path="").to_dict()
        if persist_nle_snapshot:
            if canonical_nle_snapshot:
                metadata = snapshot_payload.setdefault("metadata", {})
                metadata["read_only"] = False
                metadata["legacy_editor_state_remains_canonical"] = False
                metadata["legacy_editor_state_preserved_for_rollback"] = True
                metadata["owner_approved_canonical_load_opt_in"] = True
                snapshot_payload["persistence"] = nle_snapshot_canonical_load_approval_payload(
                    source="project_format.storage"
                )
            else:
                snapshot_payload["persistence"] = nle_snapshot_persistence_approval_payload(
                    source="project_format.storage"
                )
            payload["nle_snapshot"] = snapshot_payload
        if persist_top_level_nle:
            nle_payload = build_top_level_nle_shadow_payload(
                payload,
                project_path="",
                snapshot_payload=snapshot_payload,
            )
            if canonical_top_level_nle:
                nle_payload["role"] = "canonical_load_owner"
                nle_payload["canonical_load_owner"] = NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER
                nle_payload["metadata"]["read_only"] = False
                nle_payload["metadata"]["legacy_editor_state_remains_canonical"] = False
                nle_payload["metadata"]["legacy_editor_state_preserved_for_rollback"] = True
                nle_payload["metadata"]["owner_approved_canonical_load_opt_in"] = True
                nle_payload["persistence"] = nle_top_level_canonical_load_approval_payload(
                    source="project_format.storage"
                )
            else:
                nle_payload["persistence"] = nle_top_level_persistence_approval_payload(
                    source="project_format.storage"
                )
            payload["nle"] = nle_payload
        if replace_legacy_disk_shape:
            from core.project.nle_snapshot import editor_rows_from_top_level_nle_payload

            replacement_rows = editor_rows_from_top_level_nle_payload(
                payload.get("nle_snapshot") if isinstance(payload.get("nle_snapshot"), dict) else {},
                canonical_source=NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
            )
            if replacement_rows:
                legacy_replacement_rows = replacement_rows
            else:
                replace_legacy_disk_shape = False
        policy_payload = nle_snapshot_persistence_approval_payload(
            source="project_format.storage"
        )
        if persist_top_level_nle:
            policy_payload["persist_top_level_nle"] = True
            policy_payload["top_level_nle_schema"] = "ai_subtitle_studio.nle_shadow_project.v1"
        if canonical_top_level_nle:
            policy_payload["canonical_load_owner"] = NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER
            policy_payload["canonical_load_owner_change_allowed"] = True
            policy_payload["legacy_editor_state_remains_canonical"] = False
            policy_payload["legacy_editor_state_preserved_for_rollback"] = True
        elif canonical_nle_snapshot:
            policy_payload["canonical_load_owner"] = NLE_SNAPSHOT_CANONICAL_LOAD_OWNER
            policy_payload["canonical_load_owner_change_allowed"] = True
            policy_payload["legacy_editor_state_remains_canonical"] = False
            policy_payload["legacy_editor_state_preserved_for_rollback"] = True
            policy_payload["nle_snapshot_canonical_load_source_allowed"] = True
        if persist_runtime_nle_state and runtime_state_payload is not None:
            runtime_policy = nle_runtime_state_persistence_approval_payload(source="project_format.storage")
            policy_payload["persist_runtime_project_state"] = True
            policy_payload["runtime_project_state_persistence_allowed"] = True
            policy_payload["runtime_project_state_schema"] = runtime_policy["runtime_project_state_schema"]
            policy_payload["default_project_authority_unchanged"] = not bool(final_cutover)
            policy_payload["legacy_disk_shape_replacement_allowed"] = bool(replace_legacy_disk_shape)
            policy_payload["final_cutover_ready"] = bool(final_cutover)
        if replace_legacy_disk_shape:
            replacement_policy = nle_legacy_disk_shape_replacement_approval_payload(source="project_format.storage")
            policy_payload["legacy_editor_state_preserved_for_rollback"] = True
            policy_payload["legacy_editor_state_rows_replaced"] = True
            policy_payload["legacy_editor_state_projection_source"] = replacement_policy[
                "legacy_editor_state_projection_source"
            ]
            policy_payload["legacy_disk_shape_replacement_schema"] = replacement_policy["schema"]
            policy_payload["default_project_authority"] = "legacy_compatible_editor_state_projection"
        if final_cutover:
            final_policy = nle_final_cutover_approval_payload(source="project_format.storage")
            policy_payload["final_cutover_schema"] = final_policy["schema"]
            policy_payload["final_cutover_ready"] = True
            policy_payload["default_project_authority"] = final_policy["default_project_authority"]
            policy_payload["default_project_authority_changed"] = True
            policy_payload["default_project_authority_unchanged"] = False
            policy_payload["legacy_editor_state_compatibility_key_preserved"] = True
        payload["nle_persistence"] = policy_payload
    if persist_runtime_nle_state and runtime_state_payload is not None:
        payload["_nle_project_state"] = runtime_state_payload
    editor_state = payload.get("editor_state")
    if isinstance(editor_state, dict):
        editor_state = dict(editor_state)
        editor_state.pop("frame_timebase", None)
        if replace_legacy_disk_shape and legacy_replacement_rows is not None:
            editor_state = _replace_legacy_editor_state_subtitle_rows(
                payload,
                editor_state,
                legacy_replacement_rows,
                final_cutover_ready=final_cutover,
            )
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
        "nle_persistence",
        "nle_snapshot",
        "nle",
        "_nle_project_state",
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


def _replace_legacy_editor_state_subtitle_rows(
    project: dict[str, Any],
    editor_state: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    final_cutover_ready: bool = False,
) -> dict[str, Any]:
    from core.project.project_context import build_editor_state

    original = editor_state if isinstance(editor_state, dict) else {}
    multiclip = original.get("multiclip") if isinstance(original.get("multiclip"), dict) else {}
    analysis = original.get("analysis") if isinstance(original.get("analysis"), dict) else {}
    stt_state = original.get("stt") if isinstance(original.get("stt"), dict) else {}
    rebuilt = build_editor_state(
        mode=str(original.get("mode") or project.get("mode") or "single"),
        media_files=[str(path) for path in list(original.get("media_files") or []) if path],
        segments=[dict(row) for row in list(rows or []) if isinstance(row, dict)],
        workspace=original.get("workspace") if isinstance(original.get("workspace"), dict) else {},
        clip_boundaries=multiclip.get("boundaries") if isinstance(multiclip.get("boundaries"), list) else [],
        stt_preview_segments=stt_state.get("preview_segments") if isinstance(stt_state.get("preview_segments"), list) else [],
        cut_boundaries=analysis.get("cut_boundaries") if isinstance(analysis.get("cut_boundaries"), list) else [],
        provisional_cut_boundaries=(
            analysis.get("cut_boundary_provisional_boundaries")
            if isinstance(analysis.get("cut_boundary_provisional_boundaries"), list)
            else []
        ),
        primary_fps=project_primary_fps(project),
        preserve_segment_identity=True,
    )
    rebuilt["legacy_disk_shape_replacement"] = {
        "schema": "ai_subtitle_studio.legacy_editor_state_projection.v1",
        "source": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "row_count": len([row for row in list(rows or []) if isinstance(row, dict)]),
        "final_cutover_ready": bool(final_cutover_ready),
    }
    rebuilt.setdefault("subtitles", {})["legacy_disk_shape_replaced"] = True
    rebuilt.setdefault("subtitles", {})["projection_source"] = NLE_SNAPSHOT_CANONICAL_LOAD_OWNER
    rebuilt.setdefault("subtitles", {})["legacy_editor_state_compatibility_key_preserved"] = bool(final_cutover_ready)
    canvas = rebuilt.setdefault("rendering", {}).setdefault("subtitle_canvas", {})
    canvas["legacy_disk_shape_replaced"] = True
    canvas["projection_source"] = NLE_SNAPSHOT_CANONICAL_LOAD_OWNER
    canvas["legacy_editor_state_compatibility_key_preserved"] = bool(final_cutover_ready)
    return rebuilt


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
