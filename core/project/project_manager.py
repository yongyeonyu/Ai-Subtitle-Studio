# Version: 03.14.28
# Phase: PHASE2
"""
core/project_manager.py
프로젝트 JSON 파일 생성 / 저장 / 로드

[v02.01.00]
- 저장 시 workspace(작업 환경) 저장/복원 지원
- 자동 프로젝트 저장 흐름 대응
- 구조 정리 및 중복 코드 리팩토링
- v02.00.00 완전 하위 호환 유지
"""

import os
import uuid
from datetime import datetime
from typing import List, Optional

from core.cut_boundary import (
    cut_boundary_enabled,
    normalize_cut_boundaries,
    project_cut_boundaries,
    project_cut_provisional_boundaries,
    sync_project_cut_boundaries,
)
from core.project.project_context import (
    STT_SEGMENT_METADATA_KEYS,
    build_editor_state,
    project_media_files,
    project_segments_to_editor,
    project_stt_preview_segments,
    sanitize_workspace_state,
)
from core.project.project_assets import (
    PROJECT_EXTERNAL_STORAGE,
    externalize_project_text_assets,
    hydrate_project_text_asset_cache,
    project_uses_external_text_assets,
)
from core.project.subtitle_status import subtitle_status_payload
from core.project.project_io import read_project_file, write_project_file
from core.project.project_srt import parse_srt_to_segments
from core.project.project_model_settings import (
    build_model_settings_snapshot,
    extract_model_settings,
    merge_project_model_settings,
)
from core.project.recovery_state import (
    attach_recovery_state_to_project,
    build_recovery_checkpoint,
    merge_recovery_checkpoint,
    refresh_project_recovery_state,
)
from core.stt_mode.project_state import attach_stt_mode_state
from core.project.project_frames import (
    _augment_project_frame_metadata as _augment_project_frame_metadata_impl,
    _clip_frame_fields as _clip_frame_fields_impl,
    _get_media_probe as _get_media_probe_impl,
)
from core.media_info import probe_media
from core.frame_time import frame_to_sec, normalize_fps
from core.work_mode import normalize_work_mode

PROJECT_SCHEMA_VERSION = "03.00.26"
PROJECT_STORAGE_SCHEMA = "ai_subtitle_studio.project.vector.v1"

__all__ = [
    "PROJECTS_DIR",
    "add_media_to_project",
    "create_project",
    "ensure_projects_dir",
    "extract_model_settings",
    "get_boundary_times",
    "load_project",
    "merge_project_model_settings",
    "save_project",
]


# ─────────────────────────────────────────────
# 기본 경로
# ─────────────────────────────────────────────

PROJECTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "projects"
)


def ensure_projects_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def _archive_existing_base_project(filepath: str) -> str | None:
    """Move an existing base project aside so the base name always stays latest."""
    if not os.path.exists(filepath):
        return None
    folder = os.path.dirname(filepath)
    base, ext = os.path.splitext(os.path.basename(filepath))
    ext = ext or ".json"
    counter = 1
    while True:
        archived = os.path.join(folder, f"{base}_{counter}{ext}")
        if not os.path.exists(archived):
            os.replace(filepath, archived)
            return archived
        counter += 1


# ─────────────────────────────────────────────
# ID / Duration 유틸
# ─────────────────────────────────────────────

def _make_clip_id() -> str:
    return f"clip_{uuid.uuid4().hex[:8]}"


def _make_seg_id() -> str:
    return f"seg_{uuid.uuid4().hex[:8]}"


def _get_media_duration(filepath: str) -> float:
    """Return media duration using the shared cached probe path."""
    try:
        return float(probe_media(filepath).get("duration", 0.0) or 0.0)
    except Exception:
        return 0.0


def _get_media_probe(filepath: str) -> dict:
    return _get_media_probe_impl(filepath, probe_func=probe_media)


def _sanitize_project_workspace_fields(project: dict) -> dict:
    project["workspace"] = sanitize_workspace_state(project.get("workspace", {}) or {})
    if project.get("editor_state"):
        editor_workspace = project["editor_state"].get("workspace", {}) or project["workspace"]
        project["editor_state"]["workspace"] = sanitize_workspace_state(editor_workspace)
    return project


def _clip_frame_fields(timeline_start: float, timeline_end: float, fps: float, timeline_fps: float) -> dict:
    return _clip_frame_fields_impl(timeline_start, timeline_end, fps, timeline_fps)


def _augment_project_frame_metadata(project: dict):
    return _augment_project_frame_metadata_impl(project, probe_func=_get_media_probe)


def _segment_lookup_key(seg: dict) -> tuple[float, float]:
    start = seg.get("timeline_start", seg.get("start", 0.0))
    end = seg.get("timeline_end", seg.get("end", start))
    try:
        start = round(float(start or 0.0), 3)
        end = round(float(end or start), 3)
    except Exception:
        start = 0.0
        end = start
    return start, end


def _existing_segment_matchers(existing_segments: list[dict]) -> tuple[dict[str, dict], dict[tuple[float, float], dict]]:
    by_id: dict[str, dict] = {}
    by_time: dict[tuple[float, float], dict] = {}
    for row in existing_segments or []:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id", "") or "")
        if row_id:
            by_id[row_id] = row
        by_time[_segment_lookup_key(row)] = row
    return by_id, by_time


def _copy_missing_stt_metadata(target: dict, source: dict | None) -> None:
    if not isinstance(source, dict):
        return
    for key in STT_SEGMENT_METADATA_KEYS:
        if key in source and key not in target:
            target[key] = source.get(key)


def _vector_segment_count(project: dict) -> int:
    rows = (
        ((project.get("editor_state", {}) or {}).get("rendering", {}) or {})
        .get("subtitle_canvas", {})
        or {}
    ).get("segments")
    return len(rows) if isinstance(rows, list) else 0


def _external_text_storage_enabled(project: dict, user_settings: dict | None = None) -> bool:
    settings = user_settings if isinstance(user_settings, dict) else project.get("user_settings", {})
    if isinstance(settings, dict) and "project_external_srt_storage_enabled" in settings:
        return bool(settings.get("project_external_srt_storage_enabled"))
    return True


def _project_stt_candidate_tracks(project: dict) -> dict[str, list[dict]]:
    stt_state = ((project.get("editor_state", {}) or {}).get("stt", {}) or {})
    tracks = stt_state.get("candidate_tracks")
    return tracks if isinstance(tracks, dict) else {}


def _externalize_project_payload(
    filepath: str,
    project: dict,
    *,
    segments: list[dict] | None,
    user_settings: dict | None = None,
) -> dict:
    if not _external_text_storage_enabled(project, user_settings):
        return project
    rows = list(segments or [])
    stt_tracks = _project_stt_candidate_tracks(project)
    has_subtitles = any(str(row.get("text", "") or "").strip() for row in rows if isinstance(row, dict))
    has_stt = any(
        isinstance(track_rows, list) and any(str(row.get("text", "") or "").strip() for row in track_rows if isinstance(row, dict))
        for track_rows in stt_tracks.values()
    )
    if not has_subtitles and not has_stt:
        project.pop("asset_storage", None)
        subtitles = project.setdefault("subtitles", {})
        subtitles.pop("external_track", None)
        subtitles.pop("external_tracks", None)
        subtitles["storage"] = "editor_state.rendering.subtitle_canvas"
        subtitles["segment_count"] = 0
        editor_state = project.get("editor_state")
        if isinstance(editor_state, dict):
            editor_state.setdefault("subtitles", {})["storage"] = "vector_canvas"
            editor_state.setdefault("subtitles", {})["segments"] = []
            editor_state.setdefault("subtitles", {})["segment_count"] = 0
            stt_state = editor_state.setdefault("stt", {})
            stt_state["preview_segments"] = []
            stt_state["candidate_tracks"] = {}
            stt_state.pop("external_tracks", None)
        analysis = project.get("analysis")
        if isinstance(analysis, dict):
            analysis.pop("external_stt_tracks", None)
        return project
    return externalize_project_text_assets(
        filepath,
        project,
        final_segments=rows,
        stt_tracks=stt_tracks,
    )


def _prune_project_payload_for_vector_storage(project: dict) -> dict:
    """Remove legacy duplicate subtitle arrays; vector canvas is the source of truth."""
    project["storage_schema"] = PROJECT_STORAGE_SCHEMA
    project.pop("segments", None)
    subtitles = project.setdefault("subtitles", {})
    subtitles.pop("segments", None)
    external = project_uses_external_text_assets(project)
    subtitles["storage"] = PROJECT_EXTERNAL_STORAGE if external else "editor_state.rendering.subtitle_canvas"
    if external:
        track = subtitles.get("external_track") if isinstance(subtitles.get("external_track"), dict) else {}
        subtitles["segment_count"] = int(track.get("segment_count", subtitles.get("segment_count", 0)) or 0)
    else:
        subtitles["segment_count"] = _vector_segment_count(project)
    editor_state = project.get("editor_state")
    if isinstance(editor_state, dict):
        editor_subtitles = editor_state.setdefault("subtitles", {})
        editor_subtitles["storage"] = PROJECT_EXTERNAL_STORAGE if external else "vector_canvas"
        editor_subtitles["segments"] = []
        editor_subtitles["segment_count"] = subtitles["segment_count"]
    return project


# ─────────────────────────────────────────────
# 프로젝트 생성
# ─────────────────────────────────────────────

def create_project(
    name: str,
    media_paths: Optional[List[str]] = None,
    srt_path: Optional[str] = None,
    user_settings: Optional[dict] = None
) -> str:
    """새 프로젝트 JSON 생성 → 파일 경로 반환"""
    ensure_projects_dir()
    now = datetime.now().isoformat()

    clips = []
    cumulative = 0.0

    if media_paths:
        for i, path in enumerate(media_paths):
            ext = os.path.splitext(path)[1].lower()
            m_type = "audio" if ext in {".wav", ".m4a", ".mp3", ".aac", ".m2a"} else "video"
            info = _get_media_probe(path)
            dur = float(info.get("duration", 0.0) or 0.0)
            fps = normalize_fps(info.get("fps", 0.0) or 30.0)

            clips.append({
                "id": _make_clip_id(),
                "source_path": path,
                "type": m_type,
                "source_duration": dur,
                "in_point": 0.0,
                "out_point": dur,
                "timeline_start": cumulative,
                "timeline_end": cumulative + dur,
                "fps": fps,
                "order": i
            })
            cumulative += dur

    segments = []
    if srt_path and os.path.exists(srt_path):
        raw_segs = parse_srt_to_segments(srt_path)
        for seg in raw_segs:
            clip_id = ""
            cl_start = seg["start"]
            cl_end = seg["end"]

            for c in clips:
                if c["timeline_start"] <= seg["start"] < c["timeline_end"]:
                    clip_id = c["id"]
                    cl_start = seg["start"] - c["timeline_start"]
                    cl_end = seg["end"] - c["timeline_start"]
                    break

            segments.append({
                "id": _make_seg_id(),
                "index": seg.get("index", 0),
                "timeline_start": seg["start"],
                "timeline_end": seg["end"],
                "clip_id": clip_id,
                "clip_local_start": cl_start,
                "clip_local_end": cl_end,
                "text": seg.get("text", "").replace("\u2028", "\n"),
                "speaker": seg.get("speaker", "00"),
                "tags": seg.get("tags", []),
                "llm_note": seg.get("llm_note", ""),
                "srt_synced": True,
                "is_deleted": False
            })

    project = {
        "app": "AI Subtitle Studio",
        "version": PROJECT_SCHEMA_VERSION,
        "phase": "PHASE2",
        "project_name": name,
        "storage_schema": PROJECT_STORAGE_SCHEMA,
        "created_at": now,
        "updated_at": now,

        "timeline": {
            "total_duration": cumulative,
            "tracks": [
                {
                    "id": "video_track_0",
                    "type": "video",
                    "clips": clips
                }
            ]
        },

        "subtitles": {
            "srt_path": srt_path or "",
            "storage": "editor_state.rendering.subtitle_canvas",
            "segment_count": len(segments),
        },

        "editor_state": build_editor_state(
            mode="multiclip" if len(media_paths or []) > 1 else "single",
            media_files=list(media_paths or []),
            segments=[
                {
                    "start": seg.get("timeline_start", 0.0),
                    "end": seg.get("timeline_end", 0.0),
                    "text": seg.get("text", ""),
                    "speaker": seg.get("speaker", "00"),
                }
                for seg in segments
            ],
            workspace={},
            clip_boundaries=[
                {
                    "start": c["timeline_start"],
                    "end": c["timeline_end"],
                    "file": c["source_path"],
                    "name": os.path.basename(c["source_path"]),
                }
                for c in clips
            ],
            cut_boundaries=[],
            provisional_cut_boundaries=[],
            primary_fps=normalize_fps(clips[0].get("fps") if clips else 30.0),
        ),

        "roughcut_state": {},

        "analysis": {
            "cut_boundary_schema": "cut_boundaries.v1",
            "cut_boundaries": [],
            "cut_boundary_settings": {
                "enabled": bool((user_settings or {}).get("cut_boundary_detection_enabled", (user_settings or {}).get("scan_cut_enabled", True))),
                "detector": "opencv-gray-pyramid60"
            }
        },

        # ✅ [v02.01.00] 작업 환경 저장용
        "workspace": {
            "last_playhead": 0.0,
            "last_cursor_block": 0,
            "splitter_sizes": [],
            "terminal_visible": False,
            "dashboard_mode": "dashboard",
            "project_panel_visible": True
        },

        "user_settings": user_settings or {},
        "model_settings": build_model_settings_snapshot(user_settings),

        # 하위 호환용
        "media": [
            {
                "order": c["order"],
                "path": c["source_path"],
                "type": c["type"],
                "duration": c["source_duration"],
                "offset": c["timeline_start"]
            }
            for c in clips
        ]
    }

    filename = f"{name}.json"
    filepath = os.path.join(PROJECTS_DIR, filename)
    archived_path = _archive_existing_base_project(filepath)
    if archived_path:
        project.setdefault("history", {})
        project["history"]["previous_base_project"] = archived_path

    if media_paths:
        try:
            attach_recovery_state_to_project(
                project,
                build_recovery_checkpoint(
                    media_path=list(media_paths or [""])[0],
                    project_path=filepath,
                    stage="queued",
                    status="saved",
                    detail="project_created",
                    segments=segments,
                    settings=user_settings or {},
                ),
            )
        except Exception:
            pass

    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(
        project,
        settings=user_settings or {},
        primary_fps=normalize_fps(clips[0].get("fps") if clips else 30.0),
    )
    _augment_project_frame_metadata(project)
    _externalize_project_payload(
        filepath,
        project,
        segments=project_segments_to_editor(project),
        user_settings=user_settings or {},
    )
    _prune_project_payload_for_vector_storage(project)
    _write_json(filepath, project)
    return filepath


# ─────────────────────────────────────────────
# 프로젝트 저장
# ─────────────────────────────────────────────

def save_project(
    filepath: str,
    media_paths: Optional[List[str]] = None,
    srt_path: Optional[str] = None,
    segments: Optional[List[dict]] = None,
    user_settings: Optional[dict] = None,
    workspace: Optional[dict] = None,
    roughcut_state: Optional[dict] = None,
    active_work_mode: Optional[str] = None,
    voice_activity_segments: Optional[List[dict]] = None,
    stt_preview_segments: Optional[List[dict]] = None,
    stt_mode_state: Optional[dict] = None,
    stt_mode_learning: Optional[dict] = None,
    provisional_cut_boundaries: Optional[List[dict]] = None,
    recovery_state: Optional[dict] = None,
    persist_analysis_artifacts: bool = True,
):
    """기존 프로젝트 JSON 업데이트"""
    if not os.path.exists(filepath):
        return

    project = _read_json(filepath)
    project["version"] = PROJECT_SCHEMA_VERSION
    project["phase"] = "PHASE2"
    project["updated_at"] = datetime.now().isoformat()

    # ── 미디어 업데이트 ──
    current_media_paths = [str(path) for path in list(media_paths or []) if path] if media_paths is not None else None
    if current_media_paths is not None:
        existing_media_paths = project_media_files(project)
        media_changed = (
            len(existing_media_paths) != len(current_media_paths)
            or any(
                os.path.normpath(str(left or "")) != os.path.normpath(str(right or ""))
                for left, right in zip(existing_media_paths, current_media_paths)
            )
        )
    else:
        media_changed = False

    if current_media_paths is not None and media_changed:
        clips = []
        cumulative = 0.0
        for i, path in enumerate(current_media_paths):
            ext = os.path.splitext(path)[1].lower()
            m_type = "audio" if ext in {".wav", ".m4a", ".mp3", ".aac", ".m2a"} else "video"
            info = _get_media_probe(path)
            dur = float(info.get("duration", 0.0) or 0.0)
            fps = normalize_fps(info.get("fps", 0.0) or 30.0)
            clips.append({
                "id": _make_clip_id(),
                "source_path": path,
                "type": m_type,
                "source_duration": dur,
                "in_point": 0.0,
                "out_point": dur,
                "timeline_start": cumulative,
                "timeline_end": cumulative + dur,
                "fps": fps,
                "order": i
            })
            cumulative += dur

        project.setdefault("timeline", {"tracks": []})
        project["timeline"]["total_duration"] = cumulative
        project["timeline"]["tracks"] = [{
            "id": "video_track_0",
            "type": "video",
            "clips": clips
        }]

        project["media"] = [
            {
                "order": c["order"],
                "path": c["source_path"],
                "type": c["type"],
                "duration": c["source_duration"],
                "offset": c["timeline_start"]
            }
            for c in clips
        ]

    # ── SRT 경로 ──
    if srt_path is not None:
        project.setdefault("subtitles", {})
        project["subtitles"]["srt_path"] = srt_path

    # ── 세그먼트 ──
    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
    timebase = (project.get("timeline", {}) or {}).get("timebase", {}) or {}
    primary_fps = normalize_fps(timebase.get("primary_fps") or (clips[0].get("fps") if clips else 30.0))
    existing_cut_boundaries = project_cut_boundaries(project, primary_fps=primary_fps)
    existing_provisional_cut_boundaries = (
        normalize_cut_boundaries(provisional_cut_boundaries, primary_fps=primary_fps)
        if provisional_cut_boundaries is not None
        else project_cut_provisional_boundaries(project, primary_fps=primary_fps)
    )
    cut_enabled = cut_boundary_enabled(user_settings if user_settings is not None else project.get("user_settings", {}))
    explicit_stt_preview_update = stt_preview_segments is not None
    if explicit_stt_preview_update:
        from core.cut_boundary import magnetize_segments_to_cut_boundaries

        stt_preview_segments = magnetize_segments_to_cut_boundaries(
            stt_preview_segments,
            confirmed_boundaries=existing_cut_boundaries,
            provisional_boundaries=existing_provisional_cut_boundaries,
            enabled=cut_enabled,
            primary_fps=primary_fps,
        )
    effective_stt_preview_segments = (
        stt_preview_segments
        if explicit_stt_preview_update
        else project_stt_preview_segments(project)
    )
    new_segs = None
    if segments is not None:
        from core.cut_boundary import magnetize_segments_to_cut_boundaries

        segments = magnetize_segments_to_cut_boundaries(
            segments,
            confirmed_boundaries=existing_cut_boundaries,
            provisional_boundaries=existing_provisional_cut_boundaries,
            enabled=cut_enabled,
            primary_fps=primary_fps,
        )
        new_segs = []
        existing_subtitle_segments = project_segments_to_editor(project)
        existing_by_id, existing_by_time = _existing_segment_matchers(existing_subtitle_segments)

        for i, seg in enumerate(segments):
            if seg.get("start_frame", seg.get("timeline_start_frame")) is not None:
                t_start = frame_to_sec(seg.get("start_frame", seg.get("timeline_start_frame")), primary_fps)
            else:
                t_start = seg.get("timeline_start", seg.get("start", 0.0))
            if seg.get("end_frame", seg.get("timeline_end_frame")) is not None:
                t_end = frame_to_sec(seg.get("end_frame", seg.get("timeline_end_frame")), primary_fps)
            else:
                t_end = seg.get("timeline_end", seg.get("end", 0.0))

            clip_id = ""
            cl_start = t_start
            cl_end = t_end

            for c in clips:
                if c["timeline_start"] <= t_start < c["timeline_end"]:
                    clip_id = c["id"]
                    cl_start = t_start - c["timeline_start"]
                    cl_end = t_end - c["timeline_start"]
                    break

            new_seg = {
                "id": seg.get("id", _make_seg_id()),
                "index": i + 1,
                "timeline_start": t_start,
                "timeline_end": t_end,
                "clip_id": clip_id,
                "clip_local_start": cl_start,
                "clip_local_end": cl_end,
                "text": seg.get("text", ""),
                "speaker": seg.get("speaker", "00"),
                "tags": seg.get("tags", []),
                "llm_note": seg.get("llm_note", ""),
                "srt_synced": True,
                "is_deleted": seg.get("is_deleted", False),
                "stt_mode": bool(seg.get("stt_mode", False)),
                "stt_pending": bool(seg.get("stt_pending", False)),
                "original_text": seg.get("original_text", ""),
                "dictated_text": seg.get("dictated_text", ""),
            }
            for key in ("quality", "quality_history", "quality_candidates", "quality_stale"):
                if key in seg:
                    new_seg[key] = seg.get(key)
            for key in STT_SEGMENT_METADATA_KEYS:
                if key in seg:
                    new_seg[key] = seg.get(key)
            existing_seg = existing_by_id.get(str(seg.get("id", "") or ""))
            if existing_seg is None:
                existing_seg = existing_by_time.get(_segment_lookup_key(new_seg))
            _copy_missing_stt_metadata(new_seg, existing_seg)
            new_seg.update({key: value for key, value in subtitle_status_payload(new_seg).items() if value not in (None, "")})
            for key in (
                "start_frame",
                "end_frame",
                "timeline_start_frame",
                "timeline_end_frame",
                "clip_local_start_frame",
                "clip_local_end_frame",
                "frame_rate",
                "timeline_frame_rate",
                "source_frame_rate",
                "frame_range",
            ):
                if key in seg:
                    new_seg[key] = seg.get(key)
            new_segs.append(new_seg)

        project.setdefault("subtitles", {})
        project["subtitles"]["storage"] = "editor_state.rendering.subtitle_canvas"
        project["subtitles"]["segment_count"] = len(new_segs)

    project_segment_rows = new_segs if new_segs is not None else project_segments_to_editor(project)

    if voice_activity_segments is not None:
        project.setdefault("analysis", {})
        project["analysis"]["voice_activity_schema"] = "subtitle_detection.v1"
        project["analysis"]["voice_activity_segments"] = [
            _normalize_voice_activity_segment(item, idx)
            for idx, item in enumerate(voice_activity_segments or [])
            if isinstance(item, dict)
        ]

        project["editor_state"] = build_editor_state(
            mode="multiclip" if len(media_paths or project.get("media", []) or []) > 1 else "single",
            media_files=[
                item.get("path", "")
                for item in sorted(project.get("media", []), key=lambda item: item.get("order", 0))
                if item.get("path")
            ],
            segments=project_segment_rows,
            workspace=workspace or project.get("workspace", {}) or {},
            clip_boundaries=[
                {
                    "start": c.get("timeline_start", 0.0),
                    "end": c.get("timeline_end", 0.0),
                    "file": c.get("source_path", ""),
                    "name": os.path.basename(c.get("source_path", "")),
                }
                for c in clips
            ],
            stt_preview_segments=effective_stt_preview_segments,
            cut_boundaries=existing_cut_boundaries,
            provisional_cut_boundaries=existing_provisional_cut_boundaries,
            primary_fps=normalize_fps(clips[0].get("fps") if clips else 30.0),
        )
    elif media_paths is not None:
        clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
        project["editor_state"] = build_editor_state(
            mode="multiclip" if len(media_paths) > 1 else "single",
            media_files=list(media_paths or []),
            segments=project_segment_rows,
            workspace=workspace or project.get("workspace", {}) or {},
            clip_boundaries=[
                {
                    "start": c.get("timeline_start", 0.0),
                    "end": c.get("timeline_end", 0.0),
                    "file": c.get("source_path", ""),
                    "name": os.path.basename(c.get("source_path", "")),
                }
                for c in clips
            ],
            stt_preview_segments=effective_stt_preview_segments,
            cut_boundaries=existing_cut_boundaries,
            provisional_cut_boundaries=existing_provisional_cut_boundaries,
            primary_fps=normalize_fps(clips[0].get("fps") if clips else 30.0),
        )
    elif stt_preview_segments is not None:
        project["editor_state"] = build_editor_state(
            mode="multiclip" if len(project.get("media", []) or []) > 1 else "single",
            media_files=[
                item.get("path", "")
                for item in sorted(project.get("media", []), key=lambda item: item.get("order", 0))
                if item.get("path")
            ],
            segments=project_segment_rows,
            workspace=workspace or project.get("workspace", {}) or {},
            clip_boundaries=[
                {
                    "start": c.get("timeline_start", 0.0),
                    "end": c.get("timeline_end", 0.0),
                    "file": c.get("source_path", ""),
                    "name": os.path.basename(c.get("source_path", "")),
                }
                for c in clips
            ],
            stt_preview_segments=stt_preview_segments,
            cut_boundaries=existing_cut_boundaries,
            provisional_cut_boundaries=existing_provisional_cut_boundaries,
            primary_fps=normalize_fps(clips[0].get("fps") if clips else 30.0),
        )
    elif segments is not None:
        project["editor_state"] = build_editor_state(
            mode="multiclip" if len(project.get("media", []) or []) > 1 else "single",
            media_files=[
                item.get("path", "")
                for item in sorted(project.get("media", []), key=lambda item: item.get("order", 0))
                if item.get("path")
            ],
            segments=project_segment_rows,
            workspace=workspace or project.get("workspace", {}) or {},
            clip_boundaries=[
                {
                    "start": c.get("timeline_start", 0.0),
                    "end": c.get("timeline_end", 0.0),
                    "file": c.get("source_path", ""),
                    "name": os.path.basename(c.get("source_path", "")),
                }
                for c in clips
            ],
            stt_preview_segments=effective_stt_preview_segments,
            cut_boundaries=existing_cut_boundaries,
            provisional_cut_boundaries=existing_provisional_cut_boundaries,
            primary_fps=normalize_fps(clips[0].get("fps") if clips else 30.0),
        )

    # ── 사용자 설정 ──
    if user_settings is not None:
        project["user_settings"] = user_settings
        project["model_settings"] = build_model_settings_snapshot(user_settings)
    elif "model_settings" not in project and isinstance(project.get("user_settings"), dict):
        project["model_settings"] = build_model_settings_snapshot(project.get("user_settings"))

    # ── 작업 환경 ──
    if workspace is not None:
        workspace = sanitize_workspace_state(workspace)
        project["workspace"] = workspace
        if project.get("editor_state"):
            project["editor_state"]["workspace"] = workspace

    if active_work_mode:
        active_work_mode = normalize_work_mode(active_work_mode)
        project.setdefault("workspace", {})
        project["workspace"]["active_work_mode"] = active_work_mode
        if project.get("editor_state"):
            project["editor_state"].setdefault("workspace", {})
            project["editor_state"]["workspace"]["active_work_mode"] = active_work_mode

    if roughcut_state is not None:
        project["roughcut_state"] = dict(roughcut_state or {})
    else:
        project.setdefault("roughcut_state", project.get("roughcut_state", {}) or {})

    editor_stt = (project.get("editor_state", {}) or {}).get("stt", {}) or {}
    candidate_tracks = editor_stt.get("candidate_tracks")
    if isinstance(candidate_tracks, dict) and candidate_tracks:
        project.setdefault("analysis", {})
        project["analysis"]["stt_candidate_schema"] = "stt_candidate_tracks.v1"
        project["analysis"]["stt_candidate_tracks"] = candidate_tracks
        project["analysis"]["stt_candidate_counts"] = {
            str(source): len(rows)
            for source, rows in candidate_tracks.items()
            if isinstance(rows, list)
        }

    if persist_analysis_artifacts and segments is not None:
        try:
            from core.engine.subtitle_accuracy_graph import persist_subtitle_accuracy_graph

            media_items = list(project.get("media") or [])
            primary_media_path = ""
            if media_items and isinstance(media_items[0], dict):
                primary_media_path = str(media_items[0].get("path") or "")
            graph_result = persist_subtitle_accuracy_graph(
                list(segments or []),
                user_settings if user_settings is not None else project.get("user_settings", {}),
                media_path=primary_media_path,
                project_path=filepath,
            )
            project.setdefault("analysis", {})
            project["analysis"]["subtitle_accuracy_graph_schema"] = graph_result.get("schema")
            project["analysis"]["subtitle_accuracy_graph_path"] = graph_result.get("path", "")
            project["analysis"]["subtitle_accuracy_graph_summary"] = graph_result.get("summary", {})
            project["analysis"]["subtitle_accuracy_graph_segment_count"] = graph_result.get("segment_count", 0)
            if project.get("editor_state"):
                project["editor_state"].setdefault("analysis", {})
                project["editor_state"]["analysis"]["subtitle_accuracy_graph_path"] = graph_result.get("path", "")
                project["editor_state"]["analysis"]["subtitle_accuracy_graph_summary"] = graph_result.get("summary", {})
        except Exception:
            pass
        try:
            from core.audio.stt_lattice import persist_stt_lattice_artifact

            media_items = list(project.get("media") or [])
            primary_media_path = ""
            if media_items and isinstance(media_items[0], dict):
                primary_media_path = str(media_items[0].get("path") or "")
            lattice_result = persist_stt_lattice_artifact(
                list(segments or []),
                user_settings if user_settings is not None else project.get("user_settings", {}),
                media_path=primary_media_path,
                project_path=filepath,
            )
            project.setdefault("analysis", {})
            project["analysis"]["stt_lattice_schema"] = lattice_result.get("schema")
            project["analysis"]["stt_lattice_artifact_path"] = lattice_result.get("path", "")
            project["analysis"]["stt_lattice_summary"] = lattice_result.get("summary", {})
            project["analysis"]["stt_lattice_segment_count"] = lattice_result.get("segment_count", 0)
            if project.get("editor_state"):
                project["editor_state"].setdefault("analysis", {})
                project["editor_state"]["analysis"]["stt_lattice_artifact_path"] = lattice_result.get("path", "")
                project["editor_state"]["analysis"]["stt_lattice_summary"] = lattice_result.get("summary", {})
        except Exception:
            pass

    project["mode"] = "multiclip" if len(project_media_files(project)) > 1 else "single"

    try:
        media_items = list(project.get("media") or [])
        primary_media_path = ""
        if media_items and isinstance(media_items[0], dict):
            primary_media_path = str(media_items[0].get("path") or "")
        existing_recovery = (
            (project.get("analysis", {}) or {}).get("recovery_state")
            or ((project.get("editor_state", {}) or {}).get("analysis", {}) or {}).get("recovery_state")
            or {}
        )
        settings_for_recovery = user_settings if user_settings is not None else project.get("user_settings", {})
        artifacts = {}
        if srt_path is not None:
            artifacts["srt_path"] = srt_path
        if isinstance(recovery_state, dict) and recovery_state:
            checkpoint = dict(recovery_state)
            if checkpoint.get("schema") != "ai_subtitle_studio.recovery_state.v1":
                checkpoint = build_recovery_checkpoint(
                    media_path=primary_media_path,
                    project_path=filepath,
                    stage=str(checkpoint.get("stage", "save") or "save"),
                    status=str(checkpoint.get("status", "saved") or "saved"),
                    detail=str(checkpoint.get("detail", "") or ""),
                    segments=project_segment_rows,
                    artifacts=dict(checkpoint.get("artifacts", {}) or artifacts),
                    settings=settings_for_recovery,
                    previous_state=existing_recovery if isinstance(existing_recovery, dict) else None,
                )
            checkpoint = merge_recovery_checkpoint(existing_recovery, checkpoint)
        else:
            checkpoint = build_recovery_checkpoint(
                media_path=primary_media_path,
                project_path=filepath,
                stage="save",
                status="saved",
                detail="project_saved",
                segments=project_segment_rows,
                artifacts=artifacts,
                settings=settings_for_recovery,
                previous_state=existing_recovery if isinstance(existing_recovery, dict) else None,
            )
        attach_recovery_state_to_project(project, checkpoint)
    except Exception:
        pass

    if stt_mode_state is not None or stt_mode_learning is not None:
        attach_stt_mode_state(
            project,
            state=stt_mode_state,
            learning=stt_mode_learning,
        )

    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(
        project,
        settings=user_settings if user_settings is not None else project.get("user_settings", {}),
        primary_fps=primary_fps,
        provisional_boundaries=existing_provisional_cut_boundaries,
    )
    _augment_project_frame_metadata(project)
    _externalize_project_payload(
        filepath,
        project,
        segments=project_segments_to_editor(project),
        user_settings=user_settings if user_settings is not None else project.get("user_settings", {}),
    )
    _prune_project_payload_for_vector_storage(project)
    _write_json(filepath, project)


def _normalize_voice_activity_segment(item: dict, idx: int) -> dict:
    start = float(item.get("start", 0.0) or 0.0)
    end = float(item.get("end", start) or start)
    normalized = {
        "id": str(item.get("id") or f"subtitle_detection_{idx + 1:04d}"),
        "index": idx + 1,
        "start": start,
        "end": max(start, end),
        "kind": str(item.get("kind", "uncertain") or "uncertain"),
        "label": str(item.get("label", "") or ""),
        "source": str(item.get("source", "") or ""),
        "color": str(item.get("color", "") or ""),
        "priority": int(item.get("priority", 0) or 0),
    }
    for key in ("score", "alpha", "selection_state", "selected_source"):
        if key in item:
            normalized[key] = item.get(key)
    return normalized


# ─────────────────────────────────────────────
# 로드 / 목록
# ─────────────────────────────────────────────

def load_project(filepath: str) -> dict | None:
    """프로젝트 JSON 로드 → dict 반환"""
    if not os.path.exists(filepath):
        return None
    project = _read_json(filepath)
    project["version"] = PROJECT_SCHEMA_VERSION
    project["phase"] = "PHASE2"
    project.setdefault("roughcut_state", {})
    try:
        refresh_project_recovery_state(project)
    except Exception:
        pass
    hydrate_project_text_asset_cache(project)
    return project


def list_projects() -> list:
    """projects/ 폴더 내 모든 프로젝트 목록 반환 (최근 수정순)"""
    ensure_projects_dir()
    result = []
    for fname in os.listdir(PROJECTS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(PROJECTS_DIR, fname)
        try:
            data = _read_json(path)
            clips = data.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
            result.append({
                "name": data.get("project_name", fname),
                "path": path,
                "updated_at": data.get("updated_at", ""),
                "media_count": len(clips)
            })
        except Exception:
            continue
    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return result


# ─────────────────────────────────────────────
# 경계선
# ─────────────────────────────────────────────

def get_boundary_times(project: dict) -> list:
    """프로젝트에서 클립 경계 시간 리스트 반환 (마지막 제외)"""
    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
    boundaries = []
    for c in clips:
        end = c.get("timeline_end", 0.0)
        if end > 0:
            boundaries.append(end)
    if boundaries:
        boundaries.pop()
    return boundaries


# ─────────────────────────────────────────────
# 미디어 추가 / SRT 병합
# ─────────────────────────────────────────────

def add_media_to_project(filepath: str, new_paths: list):
    """기존 프로젝트에 미디어 파일 추가"""
    if not os.path.exists(filepath):
        return

    project = _read_json(filepath)
    project["version"] = PROJECT_SCHEMA_VERSION
    project["phase"] = "PHASE2"

    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
    existing_paths = {c["source_path"] for c in clips}
    max_order = max((c.get("order", 0) for c in clips), default=-1)
    cumulative = max((c.get("timeline_end", 0.0) for c in clips), default=0.0)

    for path in new_paths:
        if path in existing_paths:
            continue
        max_order += 1
        ext = os.path.splitext(path)[1].lower()
        m_type = "audio" if ext in {".wav", ".m4a", ".mp3", ".aac", ".m2a"} else "video"
        info = _get_media_probe(path)
        dur = float(info.get("duration", 0.0) or 0.0)
        fps = normalize_fps(info.get("fps", 0.0) or 30.0)
        clips.append({
            "id": _make_clip_id(),
            "source_path": path,
            "type": m_type,
            "source_duration": dur,
            "in_point": 0.0,
            "out_point": dur,
            "timeline_start": cumulative,
            "timeline_end": cumulative + dur,
            "fps": fps,
            "order": max_order
        })
        cumulative += dur

    project.setdefault("timeline", {"tracks": []})
    project["timeline"]["total_duration"] = cumulative
    project["timeline"]["tracks"] = [{
        "id": "video_track_0",
        "type": "video",
        "clips": clips
    }]

    project["media"] = [
        {
            "order": c["order"],
            "path": c["source_path"],
            "type": c["type"],
            "duration": c["source_duration"],
            "offset": c["timeline_start"]
        }
        for c in clips
    ]
    existing_segments = project_segments_to_editor(project)
    project["editor_state"] = build_editor_state(
        mode="multiclip" if len(project["media"]) > 1 else "single",
        media_files=[item["path"] for item in sorted(project["media"], key=lambda item: item.get("order", 0))],
        segments=existing_segments,
        workspace=project.get("workspace", {}) or {},
        clip_boundaries=[
            {
                "start": c.get("timeline_start", 0.0),
                "end": c.get("timeline_end", 0.0),
                "file": c.get("source_path", ""),
                "name": os.path.basename(c.get("source_path", "")),
            }
            for c in clips
        ],
        cut_boundaries=project_cut_boundaries(project),
        provisional_cut_boundaries=project_cut_provisional_boundaries(project),
        primary_fps=normalize_fps(clips[0].get("fps") if clips else 30.0),
    )
    project.setdefault("roughcut_state", {})

    project["updated_at"] = datetime.now().isoformat()
    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(project, settings=project.get("user_settings", {}))
    _augment_project_frame_metadata(project)
    _externalize_project_payload(
        filepath,
        project,
        segments=project_segments_to_editor(project),
        user_settings=project.get("user_settings", {}),
    )
    _prune_project_payload_for_vector_storage(project)
    _write_json(filepath, project)


def merge_srt_to_project(filepath: str) -> int | None:
    """프로젝트 내 각 클립의 개별 SRT를 찾아서 segments에 병합"""
    if not os.path.exists(filepath):
        return None

    project = _read_json(filepath)
    project["version"] = PROJECT_SCHEMA_VERSION
    project["phase"] = "PHASE2"
    clips = sorted(
        project.get("timeline", {}).get("tracks", [{}])[0].get("clips", []),
        key=lambda x: x.get("order", 0)
    )

    all_segments = []
    for clip in clips:
        base = os.path.splitext(clip["source_path"])[0]
        srt_path = base + ".srt"
        if not os.path.exists(srt_path):
            continue

        raw_segs = parse_srt_to_segments(srt_path)
        offset = clip["timeline_start"]

        for seg in raw_segs:
            all_segments.append({
                "id": _make_seg_id(),
                "index": len(all_segments) + 1,
                "timeline_start": seg["start"] + offset,
                "timeline_end": seg["end"] + offset,
                "clip_id": clip["id"],
                "clip_local_start": seg["start"],
                "clip_local_end": seg["end"],
                "text": seg.get("text", ""),
                "speaker": seg.get("speaker", "00"),
                "tags": [],
                "llm_note": "",
                "srt_synced": True,
                "is_deleted": False
            })

    project.setdefault("subtitles", {})
    project["subtitles"]["segments"] = all_segments
    project["editor_state"] = build_editor_state(
        mode="multiclip" if len(clips) > 1 else "single",
        media_files=[clip.get("source_path", "") for clip in clips if clip.get("source_path")],
        segments=[
            {
                "start": seg.get("timeline_start", 0.0),
                "end": seg.get("timeline_end", 0.0),
                "text": seg.get("text", ""),
                "speaker": seg.get("speaker", "00"),
            }
            for seg in all_segments
        ],
        workspace=project.get("workspace", {}) or {},
        clip_boundaries=[
            {
                "start": clip.get("timeline_start", 0.0),
                "end": clip.get("timeline_end", 0.0),
                "file": clip.get("source_path", ""),
                "name": os.path.basename(clip.get("source_path", "")),
            }
            for clip in clips
        ],
        cut_boundaries=project_cut_boundaries(project),
        provisional_cut_boundaries=project_cut_provisional_boundaries(project),
        primary_fps=normalize_fps(clips[0].get("fps") if clips else 30.0),
    )
    project.setdefault("roughcut_state", {})
    project["updated_at"] = datetime.now().isoformat()
    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(project, settings=project.get("user_settings", {}))
    _augment_project_frame_metadata(project)
    _externalize_project_payload(
        filepath,
        project,
        segments=project_segments_to_editor(project),
        user_settings=project.get("user_settings", {}),
    )
    _prune_project_payload_for_vector_storage(project)
    _write_json(filepath, project)

    return len(all_segments)


# ─────────────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────────────

def _read_json(filepath: str) -> dict:
    return read_project_file(filepath)


def _write_json(filepath: str, data: dict):
    if isinstance(data, dict):
        data["project_path"] = os.path.abspath(filepath)
    write_project_file(filepath, data)
