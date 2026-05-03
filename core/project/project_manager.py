# Version: 03.14.00
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
import json
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
from core.project.project_context import STT_SEGMENT_METADATA_KEYS, build_editor_state, sanitize_workspace_state
from core.project.project_model_settings import (
    MODEL_SETTING_KEYS,
    MODEL_SETTINGS_SCHEMA_VERSION,
    build_model_settings_snapshot,
    extract_model_settings,
    merge_project_model_settings,
)
from core.project.project_frames import (
    _augment_project_frame_metadata as _augment_project_frame_metadata_impl,
    _clip_frame_fields as _clip_frame_fields_impl,
    _get_media_probe as _get_media_probe_impl,
)
from core.media_info import probe_media
from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.work_mode import normalize_work_mode

PROJECT_SCHEMA_VERSION = "03.00.26"


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
        raw_segs = _parse_srt_to_segments(srt_path)
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
            "segments": segments
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

    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(
        project,
        settings=user_settings or {},
        primary_fps=normalize_fps(clips[0].get("fps") if clips else 30.0),
    )
    _augment_project_frame_metadata(project)
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
    provisional_cut_boundaries: Optional[List[dict]] = None,
):
    """기존 프로젝트 JSON 업데이트"""
    if not os.path.exists(filepath):
        return

    project = _read_json(filepath)
    project["version"] = PROJECT_SCHEMA_VERSION
    project["phase"] = "PHASE2"
    project["updated_at"] = datetime.now().isoformat()

    # ── 미디어 업데이트 ──
    if media_paths is not None:
        clips = []
        cumulative = 0.0
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
    if stt_preview_segments is not None:
        from core.cut_boundary import magnetize_segments_to_cut_boundaries

        stt_preview_segments = magnetize_segments_to_cut_boundaries(
            stt_preview_segments,
            confirmed_boundaries=existing_cut_boundaries,
            provisional_boundaries=existing_provisional_cut_boundaries,
            enabled=cut_enabled,
            primary_fps=primary_fps,
        )
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
        project["subtitles"]["segments"] = new_segs

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
            segments=segments,
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
    elif media_paths is not None:
        clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
        existing_segments = [
            {
                "start": seg.get("timeline_start", seg.get("start", 0.0)),
                "end": seg.get("timeline_end", seg.get("end", 0.0)),
                "text": seg.get("text", ""),
                "speaker": seg.get("speaker", "00"),
                "quality": seg.get("quality", {}),
                "quality_history": seg.get("quality_history", []),
                "quality_candidates": seg.get("quality_candidates", []),
                **{key: seg.get(key) for key in STT_SEGMENT_METADATA_KEYS if key in seg},
            }
            for seg in (project.get("subtitles", {}) or {}).get("segments", [])
        ]
        project["editor_state"] = build_editor_state(
            mode="multiclip" if len(media_paths) > 1 else "single",
            media_files=list(media_paths or []),
            segments=existing_segments,
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
    elif stt_preview_segments is not None:
        project["editor_state"] = build_editor_state(
            mode="multiclip" if len(project.get("media", []) or []) > 1 else "single",
            media_files=[
                item.get("path", "")
                for item in sorted(project.get("media", []), key=lambda item: item.get("order", 0))
                if item.get("path")
            ],
            segments=segments if segments is not None else [
                {
                    "start": seg.get("timeline_start", seg.get("start", 0.0)),
                    "end": seg.get("timeline_end", seg.get("end", 0.0)),
                    "text": seg.get("text", ""),
                    "speaker": seg.get("speaker", "00"),
                    **{key: seg.get(key) for key in STT_SEGMENT_METADATA_KEYS if key in seg},
                }
                for seg in (project.get("subtitles", {}) or {}).get("segments", [])
            ],
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

    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(
        project,
        settings=user_settings if user_settings is not None else project.get("user_settings", {}),
        primary_fps=primary_fps,
        provisional_boundaries=existing_provisional_cut_boundaries,
    )
    _augment_project_frame_metadata(project)
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
    existing_segments = [
        {
            "start": seg.get("timeline_start", seg.get("start", 0.0)),
            "end": seg.get("timeline_end", seg.get("end", 0.0)),
            "text": seg.get("text", ""),
            "speaker": seg.get("speaker", "00"),
        }
        for seg in (project.get("subtitles", {}) or {}).get("segments", [])
    ]
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
    )
    project.setdefault("roughcut_state", {})

    project["updated_at"] = datetime.now().isoformat()
    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(project, settings=project.get("user_settings", {}))
    _augment_project_frame_metadata(project)
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

        raw_segs = _parse_srt_to_segments(srt_path)
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
    )
    project.setdefault("roughcut_state", {})
    project["updated_at"] = datetime.now().isoformat()
    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(project, settings=project.get("user_settings", {}))
    _augment_project_frame_metadata(project)
    _write_json(filepath, project)

    return len(all_segments)


# ─────────────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────────────

def _read_json(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(filepath: str, data: dict):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _parse_srt_to_segments(srt_path: str) -> list:
    """SRT → 세그먼트 리스트"""
    import re
    segments = []
    content = ""
    for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
        try:
            with open(srt_path, "r", encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue

    if not content:
        return segments

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", content.strip())
    ts_re = re.compile(
        r"(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{2,3})"
    )

    def srt_to_sec(ts):
        h, m, s = ts.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    idx = 0
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        ts_line_idx = None
        for i, line in enumerate(lines):
            if ts_re.search(line):
                ts_line_idx = i
                break
        if ts_line_idx is None:
            continue

        match = ts_re.search(lines[ts_line_idx])
        if not match:
            continue

        text_lines = lines[ts_line_idx + 1:]
        text = "\n".join(text_lines).strip()
        if not text:
            continue

        idx += 1
        try:
            segments.append({
                "index": idx,
                "start": srt_to_sec(match.group(1)),
                "end": srt_to_sec(match.group(2)),
                "text": text,
                "tags": [],
                "llm_note": "",
                "srt_synced": True
            })
        except Exception:
            continue

    return segments
