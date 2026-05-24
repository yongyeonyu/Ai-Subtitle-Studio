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
import re
import uuid
from datetime import datetime
from typing import List, Optional

from core.runtime import config
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
    clear_project_text_asset_files,
    copy_project_rows,
    externalize_project_text_assets,
    hydrate_project_text_asset_cache,
    load_external_stt_tracks,
    load_external_subtitle_segments,
    project_uses_external_text_assets,
)
from core.project.project_analysis_store import (
    ensure_project_analysis_store as _project_analysis_store,
    normalize_project_voice_activity_segments as _normalize_project_voice_activity_segments,
    store_project_stt_candidate_tracks as _store_project_stt_candidate_tracks,
    store_project_voice_activity_segments as _store_project_voice_activity_segments,
)
from core.project.project_roughcut_store import (
    normalize_middle_segment_rows,
    selected_roughcut_candidate,
    mark_preliminary_middle_segment_rows,
    store_project_middle_segments,
    store_project_preliminary_middle_segments,
    store_project_roughcut_result,
)
from core.roughcut.cut_boundary_placeholder import (
    build_topicless_middle_segments,
    rows_are_placeholder_only,
    store_topicless_placeholders_in_project_data,
)
from core.roughcut import (
    build_editor_roughcut_candidate_payload,
    build_editor_roughcut_draft_result,
    merge_editor_roughcut_draft_state,
    run_editor_roughcut_llm_draft,
)
from core.project.subtitle_status import recheck_threshold, subtitle_status_payload
from core.project.project_io import read_project_file, write_project_file
from core.project.project_srt import parse_srt_to_segments
from core.project.project_model_settings import (
    extract_model_settings,
    merge_project_model_settings,
    restore_project_model_settings,
    store_project_model_settings_snapshot,
)
from core.settings_profiles import sanitize_persisted_settings
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
from core.media_info import (
    copy_media_probe_result,
    media_probe_result_has_fields,
    probe_media,
    probe_media_many_lookup,
)
from core.project.project_format import (
    PROJECT_SCHEMA_VERSION,
    PROJECT_STORAGE_SCHEMA,
    build_storage_project_payload,
    hydrate_project_runtime_views,
    project_primary_fps,
)
from core.frame_time import frame_to_sec, normalize_fps
from core.work_mode import normalize_work_mode

__all__ = [
    "PROJECT_FILE_EXTENSION",
    "PROJECT_FILE_FILTER",
    "PROJECTS_DIR",
    "add_media_to_project",
    "create_project",
    "ensure_projects_dir",
    "extract_model_settings",
    "get_boundary_times",
    "load_project",
    "merge_project_model_settings",
    "project_file_path_for_name",
    "restore_project_model_settings",
    "save_project",
    "save_project_roughcut_state",
    "is_project_file_path",
]


# ─────────────────────────────────────────────
# 기본 경로
# ─────────────────────────────────────────────

PROJECTS_DIR = getattr(
    config,
    "PROJECTS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "projects"),
)
PROJECT_FILE_EXTENSION = ".aissproj"
PROJECT_FILE_FILTER = f"AI Subtitle Studio Project Files (*{PROJECT_FILE_EXTENSION})"


def ensure_projects_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def _safe_name(name: str) -> str:
    banned = r'<>:"/\|?*'
    out = ''.join('_' if c in banned else c for c in (name or '').strip())
    out = out.strip().strip('.')
    return out or 'untitled_project'


def is_project_file_path(path: str | None) -> bool:
    name = str(path or "").strip().lower()
    return bool(name) and name.endswith(PROJECT_FILE_EXTENSION)


def project_file_path_for_name(name: str, *, folder: str | None = None) -> str:
    safe_name = _safe_name(name)
    return os.path.join(folder or PROJECTS_DIR, f"{safe_name}{PROJECT_FILE_EXTENSION}")


def _move_legacy_numbered_project_backups(folder: str, base: str, ext: str, backup_dir: str) -> None:
    """Move old ``project_1.json`` style backups out of the active project folder."""
    try:
        names = os.listdir(folder)
    except Exception:
        return
    pattern = re.compile(rf"^{re.escape(base)}_(\d+){re.escape(ext)}$")
    numbered: list[tuple[int, str]] = []
    for name in names:
        match = pattern.match(name)
        if not match:
            continue
        numbered.append((int(match.group(1)), name))
    for _idx, name in sorted(numbered):
        src = os.path.join(folder, name)
        if not os.path.isfile(src):
            continue
        target = os.path.join(backup_dir, name)
        if os.path.exists(target):
            stem, suffix = os.path.splitext(name)
            counter = 1
            while True:
                candidate = os.path.join(backup_dir, f"{stem}_legacy{counter}{suffix or ext}")
                if not os.path.exists(candidate):
                    target = candidate
                    break
                counter += 1
        try:
            os.replace(src, target)
        except Exception:
            pass


def _archive_existing_base_project(filepath: str) -> str | None:
    """Move an existing base project aside so the base name always stays latest."""
    if not os.path.exists(filepath):
        return None
    folder = os.path.dirname(filepath)
    backup_dir = os.path.join(folder, "프로젝트백업")
    os.makedirs(backup_dir, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(filepath))
    ext = ext or ".json"
    _move_legacy_numbered_project_backups(folder, base, ext, backup_dir)
    if ext != ".json":
        _move_legacy_numbered_project_backups(folder, base, ".json", backup_dir)
    counter = 1
    while True:
        archived = os.path.join(backup_dir, f"{base}_{counter}{ext}")
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


def _probe_cache_key(filepath: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(filepath or ""))))


def _copy_probe_result(info: dict | None) -> dict:
    return copy_media_probe_result(info)


def _probe_cache_get(probe_cache: dict[str, dict] | None, cache_key: str) -> dict | None:
    if probe_cache is None:
        return None
    cached = probe_cache.get(cache_key)
    return _copy_probe_result(cached) if isinstance(cached, dict) and cached else None


def _probe_cache_put(
    probe_cache: dict[str, dict] | None,
    cache_key: str,
    info: dict | None,
    *,
    assume_owned: bool = False,
) -> None:
    if probe_cache is None:
        return
    probe_cache[cache_key] = info if assume_owned and isinstance(info, dict) else _copy_probe_result(info)


def _probe_result_has_media_fields(info: dict | None) -> bool:
    return media_probe_result_has_fields(info)


def _get_media_probe(filepath: str, *, probe_cache: dict[str, dict] | None = None) -> dict:
    path = str(filepath or "")
    cache_key = _probe_cache_key(path)
    cached = _probe_cache_get(probe_cache, cache_key)
    if cached is not None:
        return cached
    normalized = _copy_probe_result(_get_media_probe_impl(path, probe_func=probe_media))
    _probe_cache_put(probe_cache, cache_key, normalized, assume_owned=True)
    return normalized


def _probe_media_rows(filepaths: list[str] | None, *, probe_cache: dict[str, dict] | None = None) -> list[dict]:
    paths = [str(path) for path in (filepaths or []) if path]
    if not paths:
        return []
    cache_keys = [_probe_cache_key(path) for path in paths]
    cached_rows: list[dict | None] = []
    missing_paths: list[str] = []
    missing_seen: set[str] = set()
    for idx, path in enumerate(paths):
        cache_key = cache_keys[idx]
        cached = _probe_cache_get(probe_cache, cache_key)
        if cached is not None:
            cached_rows.append(cached)
            continue
        cached_rows.append(None)
        if path not in missing_seen:
            missing_seen.add(path)
            missing_paths.append(path)
    batch_lookup = probe_media_many_lookup(missing_paths) if missing_paths else {}
    out: list[dict] = []
    for idx, path in enumerate(paths):
        info = _copy_probe_result(cached_rows[idx] or batch_lookup.get(path))
        if not _probe_result_has_media_fields(info):
            info = _get_media_probe(path, probe_cache=probe_cache)
        normalized = _copy_probe_result(info)
        _probe_cache_put(probe_cache, cache_keys[idx], normalized, assume_owned=True)
        out.append(normalized)
    return out


def _build_clip_rows(
    media_paths: list[str] | None,
    *,
    start_timeline_sec: float = 0.0,
    start_order: int = 0,
    probe_cache: dict[str, dict] | None = None,
) -> tuple[list[dict], float]:
    paths = [str(path) for path in list(media_paths or []) if path]
    if not paths:
        return [], float(start_timeline_sec or 0.0)
    cumulative = float(start_timeline_sec or 0.0)
    probe_rows = _probe_media_rows(paths, probe_cache=probe_cache)
    clips: list[dict] = []
    for idx, path in enumerate(paths):
        ext = os.path.splitext(path)[1].lower()
        m_type = "audio" if ext in {".wav", ".m4a", ".mp3", ".aac", ".m2a"} else "video"
        info = probe_rows[idx] if idx < len(probe_rows) else _get_media_probe(path, probe_cache=probe_cache)
        dur = float(info.get("duration", 0.0) or 0.0)
        fps = normalize_fps(info.get("fps", 0.0) or 30.0)
        width = int(info.get("width", 0) or 0)
        height = int(info.get("height", 0) or 0)
        clips.append({
            "id": _make_clip_id(),
            "source_path": path,
            "type": m_type,
            "source_duration": dur,
            "width": width,
            "height": height,
            "in_point": 0.0,
            "out_point": dur,
            "timeline_start": cumulative,
            "timeline_end": cumulative + dur,
            "fps": fps,
            "order": start_order + idx,
        })
        cumulative += dur
    return clips, cumulative


def _sanitize_project_workspace_fields(project: dict) -> dict:
    project["workspace"] = sanitize_workspace_state(project.get("workspace", {}) or {})
    if project.get("editor_state"):
        editor_workspace = project["editor_state"].get("workspace", {}) or project["workspace"]
        project["editor_state"]["workspace"] = sanitize_workspace_state(editor_workspace)
    return project


def _clip_frame_fields(timeline_start: float, timeline_end: float, fps: float, timeline_fps: float) -> dict:
    return _clip_frame_fields_impl(timeline_start, timeline_end, fps, timeline_fps)


def _augment_project_frame_metadata(project: dict, *, probe_cache: dict[str, dict] | None = None):
    return _augment_project_frame_metadata_impl(
        project,
        probe_func=lambda filepath: _get_media_probe(filepath, probe_cache=probe_cache),
    )


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


def _project_total_duration(clips: list[dict] | None) -> float:
    return max((float(item.get("timeline_end", 0.0) or 0.0) for item in list(clips or [])), default=0.0)


def _dict_rows(rows) -> list[dict]:
    return [row for row in list(rows or []) if isinstance(row, dict)]


def _ordered_media_paths(rows) -> list[str]:
    return [
        str(item.get("path", "") or "")
        for item in sorted(_dict_rows(rows), key=lambda item: item.get("order", 0))
        if item.get("path")
    ]


def _clip_source_paths(clips) -> list[str]:
    return [
        str(item.get("source_path", "") or "")
        for item in list(clips or [])
        if item.get("source_path")
    ]


def _project_media_rows_from_clips(clips, *, allow_missing_fps: bool = False) -> list[dict]:
    return [
        {
            "order": item["order"],
            "path": item["source_path"],
            "type": item["type"],
            "duration": item["source_duration"],
            "offset": item["timeline_start"],
            "fps": item.get("fps", 0.0) if allow_missing_fps else item["fps"],
            "width": item.get("width", 0),
            "height": item.get("height", 0),
        }
        for item in list(clips or [])
    ]


def _project_primary_media_path(project: dict) -> str:
    media_items = _dict_rows(project.get("media"))
    if not media_items:
        return ""
    return str(media_items[0].get("path", "") or "")


def _project_workspace_store(project: dict) -> tuple[dict, dict | None]:
    workspace = project.get("workspace")
    if not isinstance(workspace, dict):
        workspace = {}
        project["workspace"] = workspace
    editor_state = project.get("editor_state")
    if not isinstance(editor_state, dict):
        return workspace, None
    editor_workspace = editor_state.get("workspace")
    if not isinstance(editor_workspace, dict):
        editor_workspace = {}
        editor_state["workspace"] = editor_workspace
    return workspace, editor_workspace


def _store_project_workspace(project: dict, workspace: dict | None) -> dict:
    normalized = sanitize_workspace_state(workspace)
    project_workspace, editor_workspace = _project_workspace_store(project)
    project_workspace.clear()
    project_workspace.update(normalized)
    if editor_workspace is not None:
        editor_workspace.clear()
        editor_workspace.update(normalized)
    return normalized


def _store_project_active_work_mode(project: dict, active_work_mode: object) -> str:
    normalized = normalize_work_mode(active_work_mode)
    project_workspace, editor_workspace = _project_workspace_store(project)
    project_workspace["active_work_mode"] = normalized
    if editor_workspace is not None:
        editor_workspace["active_work_mode"] = normalized
    return normalized


def _store_project_analysis_artifact(
    project: dict,
    *,
    schema_key: str,
    path_key: str,
    summary_key: str,
    count_key: str,
    result: dict | None,
) -> None:
    analysis, editor_analysis = _project_analysis_store(project)
    payload = result if isinstance(result, dict) else {}
    path = str(payload.get("path", "") or "")
    summary = payload.get("summary", {})
    analysis[schema_key] = payload.get("schema")
    analysis[path_key] = path
    analysis[summary_key] = summary
    analysis[count_key] = payload.get("segment_count", 0)
    if editor_analysis is not None:
        editor_analysis[path_key] = path
        editor_analysis[summary_key] = summary


def _store_project_model_settings_snapshot(
    project: dict,
    *,
    effective_user_settings: dict,
    user_settings_provided: bool,
) -> None:
    store_project_model_settings_snapshot(
        project,
        effective_user_settings,
        user_settings_provided=user_settings_provided,
    )


def _editor_clip_boundaries(clips) -> list[dict]:
    return [
        {
            "start": item.get("timeline_start", 0.0),
            "end": item.get("timeline_end", 0.0),
            "file": item.get("source_path", ""),
            "name": os.path.basename(item.get("source_path", "")),
        }
        for item in _dict_rows(clips)
    ]


def _editor_seed_segments(rows) -> list[dict]:
    return [
        {
            "start": item.get("timeline_start", 0.0),
            "end": item.get("timeline_end", 0.0),
            "text": item.get("text", ""),
            "speaker": item.get("speaker", "00"),
        }
        for item in list(rows or [])
    ]


def _editor_canvas_segments(project: dict) -> list[dict] | None:
    editor_state = project.get("editor_state", {}) if isinstance(project, dict) else {}
    rendering = editor_state.get("rendering", {}) if isinstance(editor_state, dict) else {}
    canvas = rendering.get("subtitle_canvas", {}) if isinstance(rendering, dict) else {}
    segments = canvas.get("segments") if isinstance(canvas, dict) else None
    return segments if isinstance(segments, list) else None


def _editor_workspace_state(project: dict, workspace: dict | None = None) -> dict:
    return workspace if workspace is not None else (project.get("workspace", {}) or {})


def _store_project_editor_state(
    project: dict,
    *,
    media_files: list[str] | tuple[str, ...] | None,
    segments: list[dict] | None,
    workspace: dict | None,
    clip_boundaries: list[dict] | None,
    stt_preview_segments: list[dict] | None = None,
    cut_boundaries: list[dict] | None = None,
    provisional_cut_boundaries: list[dict] | None = None,
    primary_fps: float | None = None,
) -> dict:
    normalized_media_files = [str(path) for path in list(media_files or []) if path]
    project["editor_state"] = build_editor_state(
        mode="multiclip" if len(normalized_media_files) > 1 else "single",
        media_files=normalized_media_files,
        segments=segments or [],
        workspace=workspace,
        clip_boundaries=clip_boundaries,
        stt_preview_segments=stt_preview_segments,
        cut_boundaries=cut_boundaries,
        provisional_cut_boundaries=provisional_cut_boundaries,
        primary_fps=primary_fps,
    )
    return project["editor_state"]


def _save_editor_state_write_inputs(
    *,
    voice_activity_segments: list[dict] | None,
    media_paths: list[str] | None,
    stt_preview_segments: list[dict] | None,
    segments: list[dict] | None,
    editor_media_files: list[str],
    effective_stt_preview_segments: list[dict] | None,
) -> tuple[list[str], list[dict] | None] | None:
    if voice_activity_segments is not None:
        return editor_media_files, effective_stt_preview_segments
    if media_paths is not None:
        return list(media_paths or []), effective_stt_preview_segments
    if stt_preview_segments is not None:
        return editor_media_files, stt_preview_segments
    if segments is not None:
        return editor_media_files, effective_stt_preview_segments
    return None


def _store_editor_state_after_save(
    project: dict,
    *,
    voice_activity_segments: list[dict] | None,
    media_paths: list[str] | None,
    stt_preview_segments: list[dict] | None,
    effective_stt_preview_segments: list[dict] | None,
    segments: list[dict] | None,
    project_segment_rows: list[dict] | None,
    editor_media_files: list[str],
    editor_workspace: dict | None,
    editor_clip_boundaries: list[dict] | None,
    primary_fps: float | None,
    cut_boundaries: list[dict] | None,
    provisional_cut_boundaries: list[dict] | None,
) -> None:
    write_inputs = _save_editor_state_write_inputs(
        voice_activity_segments=voice_activity_segments,
        media_paths=media_paths,
        stt_preview_segments=stt_preview_segments,
        segments=segments,
        editor_media_files=editor_media_files,
        effective_stt_preview_segments=effective_stt_preview_segments,
    )
    if write_inputs is None:
        return
    media_files, preview_rows = write_inputs
    _store_project_editor_state(
        project,
        media_files=media_files,
        segments=project_segment_rows,
        workspace=editor_workspace,
        clip_boundaries=editor_clip_boundaries,
        stt_preview_segments=preview_rows,
        cut_boundaries=cut_boundaries,
        provisional_cut_boundaries=provisional_cut_boundaries,
        primary_fps=primary_fps,
    )


def _store_project_recovery_checkpoint(
    project: dict,
    *,
    filepath: str,
    segments: list[dict] | None,
    settings: dict,
    srt_path: str | None,
    recovery_state: dict | None,
) -> None:
    primary_media_path = _project_primary_media_path(project)
    existing_recovery = (
        (project.get("analysis", {}) or {}).get("recovery_state")
        or ((project.get("editor_state", {}) or {}).get("analysis", {}) or {}).get("recovery_state")
        or {}
    )
    artifacts: dict[str, str] = {}
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
                segments=segments,
                artifacts=dict(checkpoint.get("artifacts", {}) or artifacts),
                settings=settings,
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
            segments=segments,
            artifacts=artifacts,
            settings=settings,
            previous_state=existing_recovery if isinstance(existing_recovery, dict) else None,
        )
    attach_recovery_state_to_project(project, checkpoint)


def _store_project_roughcut_payload(
    project: dict,
    *,
    roughcut_state: dict | None,
    middle_segments,
    preliminary_middle_segments,
    roughcut_result,
) -> None:
    if roughcut_state is not None:
        project["roughcut_state"] = dict(roughcut_state or {})
    else:
        project.setdefault("roughcut_state", project.get("roughcut_state", {}) or {})

    if middle_segments is not None:
        _store_project_middle_segments(project, middle_segments)
    else:
        selected_middle_segments = _selected_roughcut_candidate_segments(project.get("roughcut_state", {}) or {})
        if selected_middle_segments:
            _store_project_middle_segments(project, selected_middle_segments)

    if preliminary_middle_segments is not None:
        _store_project_preliminary_middle_segments(project, preliminary_middle_segments)
    if roughcut_result is not None:
        store_project_roughcut_result(project, roughcut_result, primary_fps=project_primary_fps(project))
    else:
        candidate_payload = selected_roughcut_candidate(project.get("roughcut_state", {}) or {})
        if candidate_payload:
            store_project_roughcut_result(project, candidate_payload, primary_fps=project_primary_fps(project))


def _project_middle_segment_rows(rows) -> list[dict]:
    probe_row = next((dict(row) for row in list(rows or []) if isinstance(row, dict)), {})
    fps = (
        probe_row.get("timeline_frame_rate")
        or probe_row.get("frame_rate")
        or ((probe_row.get("frame_range") or {}).get("timeline_frame_rate") if isinstance(probe_row.get("frame_range"), dict) else None)
        or 30.0
    )
    return normalize_middle_segment_rows(rows, primary_fps=fps)


def _selected_roughcut_candidate_segments(roughcut_state: dict | None) -> list[dict]:
    rows = selected_roughcut_candidate(roughcut_state).get("segments")
    return copy_project_rows(rows)


def _store_project_middle_segments(project: dict, rows) -> list[dict]:
    saved_rows = store_project_middle_segments(project, rows, primary_fps=project_primary_fps(project))
    if rows_are_placeholder_only(project.get("roughcut_segments", [])):
        project["roughcut_segments"] = list(saved_rows)
    return saved_rows


def _preliminary_middle_segment_rows(rows: list[dict] | None) -> list[dict]:
    return mark_preliminary_middle_segment_rows(_project_middle_segment_rows(rows))


def _store_project_preliminary_middle_segments(project: dict, rows) -> list[dict]:
    return store_project_preliminary_middle_segments(project, rows, primary_fps=project_primary_fps(project))


def _project_roughcut_source_segments(segments: list[dict] | None) -> list[dict]:
    out: list[dict] = []
    for idx, row in enumerate(list(segments or [])):
        if not isinstance(row, dict):
            continue
        text = str(row.get("text", "") or "").strip()
        if not text:
            continue
        try:
            start = float(row.get("timeline_start", row.get("start", 0.0)) or 0.0)
        except Exception:
            start = 0.0
        try:
            end = float(row.get("timeline_end", row.get("end", start)) or start)
        except Exception:
            end = start
        out.append(
            {
                "id": str(row.get("id") or f"subtitle_{idx + 1:04d}"),
                "subtitle_id": idx,
                "start": start,
                "end": max(start, end),
                "text": text,
                "speaker": str(row.get("speaker", "00") or "00"),
            }
        )
    return out


def _scan_confirmed_cut_boundaries_for_project(
    clips: list[dict] | None,
    *,
    settings: dict | None = None,
    primary_fps: float = 30.0,
) -> list[dict]:
    clips = _dict_rows(clips)
    settings = dict(settings or {})
    if not clips or not cut_boundary_enabled(settings):
        return []

    try:
        from core.cut_boundary import (
            cut_boundary_scan_profile,
            scan_media_cut_boundary_provisionals,
            verify_media_cut_boundary_rows,
        )
    except Exception:
        return []

    try:
        scan_profile = cut_boundary_scan_profile(settings)
    except Exception:
        scan_profile = {
            "level": str(settings.get("scan_cut_boundary_level", settings.get("cut_boundary_level", "medium")) or "medium"),
            "positions": (0, 2, 4, 6, 8),
            "mask": "x5",
        }

    try:
        sample_step_sec = float(
            settings.get(
                "scan_cut_provisional_sample_step_sec",
                settings.get("scan_cut_auto_sample_step_sec", 2.0),
            )
            or 2.0
        )
    except Exception:
        sample_step_sec = 2.0

    try:
        threshold = float(settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)) or 24.0)
    except Exception:
        threshold = 24.0

    confirmed_rows: list[dict] = []
    for idx, clip in enumerate(clips):
        path = str(clip.get("source_path", "") or "")
        if not path or not os.path.exists(path):
            continue
        offset = float(clip.get("timeline_start", 0.0) or 0.0)
        try:
            provisional_rows = scan_media_cut_boundary_provisionals(
                path,
                clip_offset=offset,
                clip_idx=idx,
                sample_step_sec=sample_step_sec,
                threshold=threshold,
                scan_profile=scan_profile,
                sample_positions=scan_profile.get("positions", ()),
                sample_mask=scan_profile.get("mask", ""),
                settings=settings,
                settings_preloaded=True,
            )
            verified_rows = verify_media_cut_boundary_rows(
                path,
                provisional_rows,
                clip_offset=offset,
                clip_idx=idx,
                scan_profile=scan_profile,
                sample_positions=scan_profile.get("positions", ()),
                settings=settings,
                settings_preloaded=True,
            )
        except Exception:
            continue
        for row in list(verified_rows or []):
            if not isinstance(row, dict):
                continue
            if row.get("verified") or row.get("visual_verify_skipped"):
                confirmed_rows.append(dict(row))

    return normalize_cut_boundaries(confirmed_rows, primary_fps=primary_fps)


def _prefill_project_cut_boundary_artifacts(
    project: dict,
    *,
    clips: list[dict] | None,
    settings: dict | None = None,
    primary_fps: float = 30.0,
) -> list[dict]:
    clips = _dict_rows(clips)
    settings = dict(settings or {})
    if not clips or not cut_boundary_enabled(settings):
        return []
    confirmed_rows = _scan_confirmed_cut_boundaries_for_project(
        clips,
        settings=settings,
        primary_fps=primary_fps,
    )
    topicless_rows = build_topicless_middle_segments(
        confirmed_rows,
        media_duration=_project_total_duration(clips),
    )
    store_topicless_placeholders_in_project_data(
        project,
        topicless_rows,
        cut_boundaries=confirmed_rows,
        finalized=True,
    )
    return confirmed_rows


def _finalize_project_middle_segment_artifacts(
    project: dict,
    *,
    subtitle_segments: list[dict] | None,
    clips: list[dict] | None,
    settings: dict | None = None,
) -> list[dict]:
    source_segments = _project_roughcut_source_segments(subtitle_segments)
    if not source_segments:
        return []

    analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
    reference_rows = copy_project_rows(
        analysis.get("cut_boundary_topicless_middle_segments")
        or analysis.get("topicless_middle_segments")
        or analysis.get("middle_segments")
        or []
    )
    reviewed_rows = copy_project_rows(
        analysis.get("cut_boundary_reviewed_rows")
        or analysis.get("cut_boundaries")
        or []
    )
    confirmed_rows = copy_project_rows(analysis.get("cut_boundaries", []) or [])
    media_files = _clip_source_paths(clips)
    source_path = media_files[0] if media_files else ""
    clip_boundaries = _editor_clip_boundaries(clips)
    llm_payload = run_editor_roughcut_llm_draft(
        source_segments,
        settings=settings or {},
        cut_boundaries=confirmed_rows,
        reference_major_segments=reference_rows,
        reviewed_cut_boundaries=reviewed_rows,
    )
    result = build_editor_roughcut_draft_result(
        source_segments,
        media_duration=_project_total_duration(clips),
        source_path=source_path,
        settings=settings or {},
        llm_payload=llm_payload,
        reference_major_segments=reference_rows,
    )
    candidate = build_editor_roughcut_candidate_payload(
        result,
        source_segments=source_segments,
        settings=settings or {},
        source_path=source_path,
        source_media=os.path.basename(source_path) if source_path else "현재 프로젝트",
        media_files=media_files,
        clip_boundaries=clip_boundaries,
        editor_mode="multiclip" if len(media_files) > 1 else "single",
    )
    project["roughcut_state"] = merge_editor_roughcut_draft_state(project.get("roughcut_state", {}) or {}, candidate)
    candidate_rows = candidate.get("segments") or []
    _store_project_preliminary_middle_segments(project, candidate_rows)
    store_project_roughcut_result(project, candidate, primary_fps=project_primary_fps(project))
    return _store_project_middle_segments(project, candidate_rows)


def _external_text_storage_enabled(project: dict, user_settings: dict | None = None) -> bool:
    settings = user_settings if isinstance(user_settings, dict) else project.get("user_settings", {})
    if isinstance(settings, dict) and "project_external_srt_storage_enabled" in settings:
        return bool(settings.get("project_external_srt_storage_enabled"))
    return True


def _project_stt_candidate_tracks(project: dict) -> dict[str, list[dict]]:
    stt_state = ((project.get("editor_state", {}) or {}).get("stt", {}) or {})
    tracks = stt_state.get("candidate_tracks")
    return tracks if isinstance(tracks, dict) else {}


def _segments_have_text(rows) -> bool:
    for row in (() if rows is None else rows):
        if isinstance(row, dict) and str(row.get("text", "") or "").strip():
            return True
    return False


def _track_map_has_text(tracks: dict[str, list[dict]] | None) -> bool:
    if not isinstance(tracks, dict):
        return False
    return any(_segments_have_text(track_rows) for track_rows in tracks.values())


def _externalize_project_payload(
    filepath: str,
    project: dict,
    *,
    segments: list[dict] | None,
    user_settings: dict | None = None,
    rewrite_stt_reference_tracks: bool = True,
    recover_external_assets_on_empty: bool = True,
) -> dict:
    if not _external_text_storage_enabled(project, user_settings):
        return project
    rows = segments if isinstance(segments, list) else list(segments or [])
    stt_tracks = _project_stt_candidate_tracks(project)
    has_subtitles = _segments_have_text(rows)
    has_stt = _track_map_has_text(stt_tracks)
    recovered_subtitles = (
        load_external_subtitle_segments(project)
        if recover_external_assets_on_empty and not has_subtitles
        else []
    )
    recovered_stt_tracks = (
        load_external_stt_tracks(project)
        if recover_external_assets_on_empty and not has_stt and rewrite_stt_reference_tracks
        else {}
    )
    recovered_has_subtitles = _segments_have_text(recovered_subtitles)
    recovered_has_stt = _track_map_has_text(recovered_stt_tracks)
    final_segments = recovered_subtitles if recovered_has_subtitles else rows
    final_stt_tracks = recovered_stt_tracks if recovered_has_stt else stt_tracks
    if not _segments_have_text(final_segments) and not _track_map_has_text(final_stt_tracks):
        if not recover_external_assets_on_empty:
            clear_project_text_asset_files(filepath, project)
        project.pop("_external_subtitle_segments_cache", None)
        project.pop("_external_stt_tracks_cache", None)
        project.pop("_hot_open_subtitle_segments_cache", None)
        project.pop("_hot_open_stt_preview_segments_cache", None)
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
        final_segments=final_segments,
        stt_tracks=final_stt_tracks,
        rewrite_stt_reference_tracks=bool(rewrite_stt_reference_tracks),
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
    user_settings: Optional[dict] = None,
    *,
    prefill_analysis_artifacts: bool = True,
) -> str:
    """새 프로젝트 JSON 생성 → 파일 경로 반환"""
    ensure_projects_dir()
    now = datetime.now().isoformat()
    persisted_user_settings = sanitize_persisted_settings(user_settings)
    probe_cache: dict[str, dict] = {}

    clips, cumulative = _build_clip_rows(media_paths, probe_cache=probe_cache)

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
    editor_segments = _editor_seed_segments(segments)

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

        "editor_state": {},

        "roughcut_state": {},

        "analysis": {
            "cut_boundary_schema": "cut_boundaries.v1",
            "cut_boundaries": [],
            "cut_boundary_settings": {
                "enabled": bool(
                    persisted_user_settings.get(
                        "cut_boundary_detection_enabled",
                        persisted_user_settings.get("scan_cut_enabled", True),
                    )
                ),
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

        "user_settings": persisted_user_settings,

        # 하위 호환용
        "media": _project_media_rows_from_clips(clips)
    }
    _store_project_editor_state(
        project,
        media_files=list(media_paths or []),
        segments=editor_segments,
        workspace={},
        clip_boundaries=_editor_clip_boundaries(clips),
        cut_boundaries=[],
        provisional_cut_boundaries=[],
        primary_fps=normalize_fps(clips[0].get("fps") if clips else 30.0),
    )
    store_project_model_settings_snapshot(project, persisted_user_settings, user_settings_provided=True)

    filepath = project_file_path_for_name(name)
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
                    settings=persisted_user_settings,
                ),
            )
        except Exception:
            pass

    primary_fps = project_primary_fps(project)
    if prefill_analysis_artifacts:
        _prefill_project_cut_boundary_artifacts(
            project,
            clips=clips,
            settings=persisted_user_settings,
            primary_fps=primary_fps,
        )
        _finalize_project_middle_segment_artifacts(
            project,
            subtitle_segments=segments,
            clips=clips,
            settings=persisted_user_settings,
        )
    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(
        project,
        settings=persisted_user_settings,
        primary_fps=primary_fps,
    )
    _augment_project_frame_metadata(project, probe_cache=probe_cache)
    _externalize_project_payload(
        filepath,
        project,
        segments=editor_segments,
        user_settings=persisted_user_settings,
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
    middle_segments: Optional[List[dict]] = None,
    roughcut_result: Optional[dict] = None,
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
    rewrite_stt_reference_tracks: bool = True,
    preliminary_middle_segments: Optional[List[dict]] = None,
    recover_external_assets_on_empty: bool = True,
):
    """기존 프로젝트 JSON 업데이트"""
    if not os.path.exists(filepath):
        return

    project = _read_json(filepath)
    stored_user_settings = sanitize_persisted_settings(project.get("user_settings", {}))
    if "user_settings" in project:
        project["user_settings"] = stored_user_settings
    effective_user_settings = (
        sanitize_persisted_settings(user_settings)
        if user_settings is not None
        else stored_user_settings
    )
    project["version"] = PROJECT_SCHEMA_VERSION
    project["phase"] = "PHASE2"
    project["updated_at"] = datetime.now().isoformat()
    probe_cache: dict[str, dict] = {}

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
        clips, cumulative = _build_clip_rows(current_media_paths, probe_cache=probe_cache)

        project.setdefault("timeline", {"tracks": []})
        project["timeline"]["total_duration"] = cumulative
        project["timeline"]["tracks"] = [{
            "id": "video_track_0",
            "type": "video",
            "clips": clips
        }]

        project["media"] = _project_media_rows_from_clips(clips)

    # ── SRT 경로 ──
    if srt_path is not None:
        project.setdefault("subtitles", {})
        project["subtitles"]["srt_path"] = srt_path

    # ── 세그먼트 ──
    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
    primary_fps = project_primary_fps(project)
    existing_cut_boundaries = project_cut_boundaries(project, primary_fps=primary_fps)
    existing_provisional_cut_boundaries = (
        normalize_cut_boundaries(provisional_cut_boundaries, primary_fps=primary_fps)
        if provisional_cut_boundaries is not None
        else project_cut_provisional_boundaries(project, primary_fps=primary_fps)
    )
    cut_enabled = cut_boundary_enabled(effective_user_settings)
    explicit_stt_preview_update = stt_preview_segments is not None
    # STT1/STT2 preview lanes represent raw candidate timing and must survive
    # subtitle magnet / cut-boundary save cycles unchanged.
    effective_stt_preview_segments = (
        stt_preview_segments
        if explicit_stt_preview_update
        else project_stt_preview_segments(project)
    )
    project["_hot_open_stt_preview_segments_cache"] = copy_project_rows(effective_stt_preview_segments)
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
        status_threshold = recheck_threshold() if segments else None

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
            new_seg.update({
                key: value
                for key, value in subtitle_status_payload(new_seg, threshold=status_threshold).items()
                if value not in (None, "")
            })
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
    editor_media_files = _ordered_media_paths(project.get("media", []))
    editor_clip_boundaries = _editor_clip_boundaries(clips)
    editor_workspace = _editor_workspace_state(project, workspace)

    if voice_activity_segments is not None:
        _store_project_voice_activity_segments(
            project,
            _normalize_project_voice_activity_segments(
                voice_activity_segments,
                priority_as_int=True,
            ),
        )
    elif media_paths is not None:
        clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
        editor_clip_boundaries = _editor_clip_boundaries(clips)

    _store_editor_state_after_save(
        project,
        voice_activity_segments=voice_activity_segments,
        media_paths=media_paths,
        stt_preview_segments=stt_preview_segments,
        effective_stt_preview_segments=effective_stt_preview_segments,
        segments=segments,
        project_segment_rows=project_segment_rows,
        editor_media_files=editor_media_files,
        editor_workspace=editor_workspace,
        editor_clip_boundaries=editor_clip_boundaries,
        primary_fps=primary_fps,
        cut_boundaries=existing_cut_boundaries,
        provisional_cut_boundaries=existing_provisional_cut_boundaries,
    )

    # ── 사용자 설정 ──
    _store_project_model_settings_snapshot(
        project,
        effective_user_settings=effective_user_settings,
        user_settings_provided=user_settings is not None,
    )

    # ── 작업 환경 ──
    if workspace is not None:
        workspace = _store_project_workspace(project, workspace)

    if active_work_mode:
        active_work_mode = _store_project_active_work_mode(project, active_work_mode)

    _store_project_roughcut_payload(
        project,
        roughcut_state=roughcut_state,
        middle_segments=middle_segments,
        preliminary_middle_segments=preliminary_middle_segments,
        roughcut_result=roughcut_result,
    )

    editor_stt = (project.get("editor_state", {}) or {}).get("stt", {}) or {}
    candidate_tracks = editor_stt.get("candidate_tracks")
    _store_project_stt_candidate_tracks(project, candidate_tracks)

    if persist_analysis_artifacts and segments is not None:
        _persist_project_analysis_artifacts(
            filepath,
            project,
            segments=segments,
            settings=effective_user_settings,
        )

    project["mode"] = "multiclip" if len(project_media_files(project)) > 1 else "single"

    try:
        _store_project_recovery_checkpoint(
            project,
            filepath=filepath,
            segments=project_segment_rows,
            settings=effective_user_settings,
            srt_path=srt_path,
            recovery_state=recovery_state if isinstance(recovery_state, dict) else None,
        )
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
        settings=effective_user_settings,
        primary_fps=primary_fps,
        provisional_boundaries=existing_provisional_cut_boundaries,
    )
    _augment_project_frame_metadata(project, probe_cache=probe_cache)
    _externalize_project_payload(
        filepath,
        project,
        segments=project_segment_rows,
        user_settings=effective_user_settings,
        rewrite_stt_reference_tracks=bool(rewrite_stt_reference_tracks),
        recover_external_assets_on_empty=bool(recover_external_assets_on_empty),
    )
    _prune_project_payload_for_vector_storage(project)
    _write_json(filepath, project)


def save_project_roughcut_state(
    filepath: str,
    *,
    middle_segments: Optional[List[dict]] = None,
    roughcut_result: Optional[dict] = None,
    roughcut_state: Optional[dict] = None,
    preliminary_middle_segments: Optional[List[dict]] = None,
    active_work_mode: Optional[str] = None,
) -> None:
    """Persist only roughcut metadata without rebuilding subtitle tracks.

    Post-generation roughcut runs happen while the editor should already be
    interactive. Reusing the full project save path here rewrites every subtitle
    row and external text asset, which can visibly freeze the timeline.
    """
    if not os.path.exists(filepath):
        return
    project = read_project_file(filepath)
    project["version"] = PROJECT_SCHEMA_VERSION
    project["phase"] = "PHASE2"
    project["updated_at"] = datetime.now().isoformat()
    if active_work_mode:
        _store_project_active_work_mode(project, active_work_mode)
    _store_project_roughcut_payload(
        project,
        roughcut_state=roughcut_state,
        middle_segments=middle_segments,
        preliminary_middle_segments=preliminary_middle_segments,
        roughcut_result=roughcut_result,
    )
    _sanitize_project_workspace_fields(project)
    _prune_project_payload_for_vector_storage(project)
    write_project_file(filepath, project)


def _persist_project_analysis_artifacts(
    filepath: str,
    project: dict,
    *,
    segments: list[dict] | None,
    settings: dict | None,
) -> None:
    segment_rows = segments if isinstance(segments, list) else list(segments or [])
    primary_media_path = _project_primary_media_path(project)

    try:
        from core.engine.subtitle_accuracy_graph import persist_subtitle_accuracy_graph

        graph_result = persist_subtitle_accuracy_graph(
            segment_rows,
            settings,
            media_path=primary_media_path,
            project_path=filepath,
        )
        _store_project_analysis_artifact(
            project,
            schema_key="subtitle_accuracy_graph_schema",
            path_key="subtitle_accuracy_graph_path",
            summary_key="subtitle_accuracy_graph_summary",
            count_key="subtitle_accuracy_graph_segment_count",
            result=graph_result,
        )
    except Exception:
        pass

    try:
        from core.audio.stt_lattice import persist_stt_lattice_artifact

        lattice_result = persist_stt_lattice_artifact(
            segment_rows,
            settings,
            media_path=primary_media_path,
            project_path=filepath,
        )
        _store_project_analysis_artifact(
            project,
            schema_key="stt_lattice_schema",
            path_key="stt_lattice_artifact_path",
            summary_key="stt_lattice_summary",
            count_key="stt_lattice_segment_count",
            result=lattice_result,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────
# 로드 / 목록
# ─────────────────────────────────────────────

def load_project(filepath: str, *, hydrate_text_assets: bool = True) -> dict | None:
    """프로젝트 JSON 로드 → dict 반환"""
    if not os.path.exists(filepath):
        return None
    project = _read_json(filepath)
    hydrate_project_runtime_views(project)
    project["version"] = PROJECT_SCHEMA_VERSION
    project["phase"] = "PHASE2"
    project.setdefault("roughcut_state", {})
    try:
        refresh_project_recovery_state(project)
    except Exception:
        pass
    if hydrate_text_assets:
        hydrate_project_text_asset_cache(project)
    else:
        _strip_text_asset_runtime_cache(project)
    return project


def _strip_text_asset_runtime_cache(project: dict | None) -> None:
    """Drop large text-asset caches for fast UI project entry."""
    if not isinstance(project, dict):
        return
    project.pop("_external_subtitle_segments_cache", None)
    project.pop("_external_stt_tracks_cache", None)
    if not project_uses_external_text_assets(project):
        return
    editor_state = project.get("editor_state")
    if not isinstance(editor_state, dict):
        return
    stt_state = editor_state.get("stt")
    if isinstance(stt_state, dict) and isinstance(stt_state.get("candidate_tracks"), dict):
        stt_state["candidate_tracks"] = {}


def list_projects() -> list:
    """projects/ 폴더 내 모든 프로젝트 목록 반환 (최근 수정순)"""
    ensure_projects_dir()
    result = []
    for fname in os.listdir(PROJECTS_DIR):
        if not is_project_file_path(fname):
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
    """프로젝트에서 표시/스냅용 컷 경계 rows 반환.

    우선순위:
    1. analysis.cut_boundaries 정식 컷 경계
    2. 멀티클립 클립 경계(하위 호환 fallback)
    """
    confirmed = copy_project_rows(project_cut_boundaries(project) or [])
    if confirmed:
        return confirmed

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
    project_user_settings = sanitize_persisted_settings(project.get("user_settings", {}))
    if "user_settings" in project:
        project["user_settings"] = project_user_settings
    project["version"] = PROJECT_SCHEMA_VERSION
    project["phase"] = "PHASE2"

    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
    existing_paths = set(_clip_source_paths(clips))
    max_order = max((c.get("order", 0) for c in clips), default=-1)
    cumulative = max((c.get("timeline_end", 0.0) for c in clips), default=0.0)
    incoming_paths = [str(path) for path in list(new_paths or []) if path and path not in existing_paths]
    probe_cache: dict[str, dict] = {}
    new_clips, cumulative = _build_clip_rows(
        incoming_paths,
        start_timeline_sec=cumulative,
        start_order=max_order + 1,
        probe_cache=probe_cache,
    )
    clips.extend(new_clips)

    project.setdefault("timeline", {"tracks": []})
    project["timeline"]["total_duration"] = cumulative
    project["timeline"]["tracks"] = [{
        "id": "video_track_0",
        "type": "video",
        "clips": clips
    }]

    project["media"] = _project_media_rows_from_clips(clips, allow_missing_fps=True)
    primary_fps = project_primary_fps(project)
    existing_segments = project_segments_to_editor(project)
    _store_project_editor_state(
        project,
        media_files=_ordered_media_paths(project.get("media", [])),
        segments=existing_segments,
        workspace=_editor_workspace_state(project),
        clip_boundaries=_editor_clip_boundaries(clips),
        cut_boundaries=project_cut_boundaries(project),
        provisional_cut_boundaries=project_cut_provisional_boundaries(project),
        primary_fps=primary_fps,
    )
    project.setdefault("roughcut_state", {})

    project["updated_at"] = datetime.now().isoformat()
    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(project, settings=project_user_settings)
    _augment_project_frame_metadata(project, probe_cache=probe_cache)
    _externalize_project_payload(
        filepath,
        project,
        segments=existing_segments,
        user_settings=project_user_settings,
    )
    _prune_project_payload_for_vector_storage(project)
    _write_json(filepath, project)


def merge_srt_to_project(filepath: str) -> int | None:
    """프로젝트 내 각 클립의 개별 SRT를 찾아서 segments에 병합"""
    if not os.path.exists(filepath):
        return None

    project = _read_json(filepath)
    project_user_settings = sanitize_persisted_settings(project.get("user_settings", {}))
    if "user_settings" in project:
        project["user_settings"] = project_user_settings
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
    primary_fps = project_primary_fps(project)
    editor_segments = _editor_seed_segments(all_segments)
    _store_project_editor_state(
        project,
        media_files=_clip_source_paths(clips),
        segments=editor_segments,
        workspace=_editor_workspace_state(project),
        clip_boundaries=_editor_clip_boundaries(clips),
        cut_boundaries=project_cut_boundaries(project),
        provisional_cut_boundaries=project_cut_provisional_boundaries(project),
        primary_fps=primary_fps,
    )
    project.setdefault("roughcut_state", {})
    project["updated_at"] = datetime.now().isoformat()
    _sanitize_project_workspace_fields(project)
    sync_project_cut_boundaries(project, settings=project_user_settings)
    _augment_project_frame_metadata(project)
    _externalize_project_payload(
        filepath,
        project,
        segments=editor_segments,
        user_settings=project_user_settings,
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
    payload = data
    if isinstance(data, dict):
        data["project_path"] = os.path.abspath(filepath)
        payload = build_storage_project_payload(data)
        payload["project_path"] = os.path.abspath(filepath)
    write_project_file(filepath, payload)
