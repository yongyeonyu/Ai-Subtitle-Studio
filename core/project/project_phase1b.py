# Version: 03.14.28
# Phase: PHASE2
"""
core/project/project_phase1b.py
PHASE1-B project save/load extension helpers.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from core.project.project_context import (
    STT_SEGMENT_METADATA_KEYS,
    build_editor_state,
    project_segments_to_editor,
    project_stt_preview_segments,
    sanitize_workspace_state,
)
from core.project.project_io import read_project_file, write_project_file
from core.project.project_manager import (
    _prune_project_payload_for_vector_storage,
    build_model_settings_snapshot,
    _augment_project_frame_metadata,
)
from core.project.project_assets import externalize_project_text_assets
from core.cut_boundary import cut_boundary_enabled, project_cut_boundaries, split_segments_by_cut_boundaries, sync_project_cut_boundaries
from core.frame_time import normalize_fps
from core.work_mode import EDITOR_MODE, normalize_work_mode

PROJECT_SCHEMA_VERSION = '03.00.26'


def _safe_abs(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return os.path.abspath(path)
    except Exception:
        return path


def _selected_segment_line(editor) -> int | None:
    try:
        te = getattr(editor, 'text_edit', None)
        if te is None:
            return None
        return te.textCursor().blockNumber()
    except Exception:
        return None


def _workspace_snapshot(owner, editor) -> dict[str, Any]:
    timeline = getattr(editor, 'timeline', None)
    lock_chk = getattr(timeline, 'lock_chk', None) if timeline else None
    state: dict[str, Any] = {
        'last_playhead': float(getattr(editor, '_current_sec', 0.0) or 0.0),
        'splitter_sizes': [],
        'terminal_visible': bool(getattr(owner, '_log_visible', False) or getattr(editor, '_log_visible', False) or getattr(editor, 'log_visible', False)),
        'dashboard_mode': getattr(owner, '_dashboard_mode', 'dashboard') or 'dashboard',
        'project_panel_visible': bool(getattr(owner, '_project_panel_visible', True)),
        'active_work_mode': normalize_work_mode(getattr(owner, '_current_work_mode', EDITOR_MODE)),
        'last_cursor_block': _selected_segment_line(editor),
        'selected_segment_line': _selected_segment_line(editor),
        'edit_lock': bool(lock_chk.isChecked()) if lock_chk is not None else False,
        'active_clip_idx': int(getattr(editor, '_active_clip_idx', getattr(owner, '_active_clip_idx', 0)) or 0),
    }
    if hasattr(editor, 'splitter') and editor.splitter is not None:
        try:
            state['splitter_sizes'] = list(editor.splitter.sizes())
        except Exception:
            pass
    return state


def _project_meta(owner) -> dict[str, Any]:
    return {
        'sorted_files': [_safe_abs(p) for p in list(getattr(owner, '_multiclip_files', []) or [])],
        'project_boundary_times': list(getattr(owner, '_project_boundary_times', []) or []),
        'multiclip_boundaries': list(getattr(owner, '_multiclip_boundaries', []) or []),
    }


def _media_paths(owner, editor, project_data: dict[str, Any]) -> list[str]:
    media_files = []
    if getattr(owner, '_multiclip_files', None):
        media_files = [_safe_abs(p) for p in list(getattr(owner, '_multiclip_files', []) or [])]
    elif getattr(editor, 'media_path', None):
        media_files = [_safe_abs(editor.media_path)]
    elif isinstance(project_data.get('media'), list):
        for item in project_data.get('media', []):
            p = item.get('path') if isinstance(item, dict) else None
            if p:
                media_files.append(_safe_abs(p))
    return [p for p in media_files if p]


def _project_primary_fps(project_data: dict[str, Any]) -> float:
    timeline = project_data.get('timeline', {}) if isinstance(project_data.get('timeline'), dict) else {}
    timebase = timeline.get('timebase', {}) if isinstance(timeline.get('timebase'), dict) else {}
    try:
        fps = float(timebase.get('primary_fps', 0.0) or 0.0)
    except Exception:
        fps = 0.0
    if fps > 0.0:
        return normalize_fps(fps)
    tracks = timeline.get('tracks', []) if isinstance(timeline.get('tracks'), list) else []
    for track in tracks:
        clips = track.get('clips', []) if isinstance(track, dict) and isinstance(track.get('clips'), list) else []
        for clip in clips:
            try:
                fps = float(clip.get('fps', 0.0) or 0.0)
            except Exception:
                fps = 0.0
            if fps > 0.0:
                return normalize_fps(fps)
    return normalize_fps(30.0)


def _normalize_segments_for_legacy(segments: list[dict[str, Any]] | None, existing: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not segments:
        return existing or []
    existing_by_id: dict[str, dict[str, Any]] = {}
    existing_by_time: dict[tuple[float, float], dict[str, Any]] = {}
    for row in existing or []:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get('id', '') or '')
        if row_id:
            existing_by_id[row_id] = row
        start = float(row.get('timeline_start', row.get('start', 0.0)) or 0.0)
        end = float(row.get('timeline_end', row.get('end', start)) or start)
        existing_by_time[(round(start, 3), round(end, 3))] = row
    out = []
    for idx, seg in enumerate(segments, 1):
        start = float(seg.get('start', seg.get('timeline_start', 0.0)) or 0.0)
        end = float(seg.get('end', seg.get('timeline_end', start)) or start)
        item = {
            'id': seg.get('id', f'seg_{idx:04d}'),
            'index': idx,
            'timeline_start': start,
            'timeline_end': end,
            'clip_id': seg.get('clip_id', 'clip_0'),
            'clip_local_start': float(seg.get('clip_local_start', start) or start),
            'clip_local_end': float(seg.get('clip_local_end', end) or end),
            'text': str(seg.get('text', '') or ''),
            'speaker': str(seg.get('speaker', seg.get('spk', '00')) or '00'),
            'tags': list(seg.get('tags', []) or []),
            'llm_note': str(seg.get('llm_note', '') or ''),
            'srt_synced': bool(seg.get('srt_synced', True)),
            'is_deleted': bool(seg.get('is_deleted', False)),
            'stt_mode': bool(seg.get('stt_mode', False)),
            'stt_pending': bool(seg.get('stt_pending', False)),
            'original_text': str(seg.get('original_text', '') or ''),
            'dictated_text': str(seg.get('dictated_text', '') or ''),
        }
        for key in STT_SEGMENT_METADATA_KEYS:
            if key in seg:
                item[key] = seg.get(key)
        existing_seg = existing_by_id.get(str(seg.get('id', '') or '')) or existing_by_time.get((round(start, 3), round(end, 3)))
        if isinstance(existing_seg, dict):
            for key in STT_SEGMENT_METADATA_KEYS:
                if key in existing_seg and key not in item:
                    item[key] = existing_seg.get(key)
        out.append(item)
    return out


def enrich_existing_project_file(project_path: str, owner, editor, segments: list[dict[str, Any]] | None = None, srt_path: str | None = None) -> str:
    if not project_path or not os.path.exists(project_path):
        return project_path
    data = read_project_file(project_path)
    media_files = _media_paths(owner, editor, data)
    mode = 'multiclip' if len(media_files) > 1 else 'single'
    data['version'] = PROJECT_SCHEMA_VERSION
    data['phase'] = 'PHASE2'
    data['mode'] = mode
    data['updated_at'] = datetime.now().isoformat(timespec='seconds')
    data['workspace'] = sanitize_workspace_state({**data.get('workspace', {}), **_workspace_snapshot(owner, editor)})
    editor_settings = dict(getattr(editor, 'settings', {}) or {})
    if editor_settings:
        data['user_settings'] = editor_settings
        data['model_settings'] = build_model_settings_snapshot(editor_settings)
    cut_boundaries = project_cut_boundaries(data)
    if segments is not None:
        segments = split_segments_by_cut_boundaries(
            segments,
            cut_boundaries,
            enabled=cut_boundary_enabled(editor_settings or data.get('user_settings', {})),
        )
    data['project_meta'] = _project_meta(owner)
    existing_segments = project_segments_to_editor(data)
    normalized_segments = _normalize_segments_for_legacy(segments, existing_segments)
    primary_fps = _project_primary_fps(data)
    subtitles = dict(data.get('subtitles', {}) or {})
    subtitles['srt_path'] = _safe_abs(srt_path) or subtitles.get('srt_path')
    subtitles.pop('segments', None)
    subtitles['storage'] = 'editor_state.rendering.subtitle_canvas'
    subtitles['segment_count'] = len(normalized_segments)
    data['subtitles'] = subtitles
    data['editor_state'] = build_editor_state(
        mode=mode,
        media_files=media_files,
        segments=normalized_segments,
        workspace=data['workspace'],
        clip_boundaries=list(getattr(owner, '_multiclip_boundaries', []) or []),
        stt_preview_segments=project_stt_preview_segments(data),
        cut_boundaries=cut_boundaries,
        primary_fps=primary_fps,
    )
    data.setdefault('roughcut_state', {})
    if media_files:
        data['media'] = [
            {'order': i, 'path': path, 'type': 'video', 'duration': 0.0, 'offset': 0.0}
            for i, path in enumerate(media_files)
        ]
    _augment_project_frame_metadata(data)
    sync_project_cut_boundaries(data, settings=editor_settings or data.get('user_settings', {}))
    externalize_project_text_assets(
        project_path,
        data,
        final_segments=project_segments_to_editor(data),
        stt_tracks=((data.get("editor_state", {}) or {}).get("stt", {}) or {}).get("candidate_tracks") or {},
    )
    _prune_project_payload_for_vector_storage(data)
    data["project_path"] = os.path.abspath(project_path)
    write_project_file(project_path, data)
    return project_path


def restore_project_stt_preview_segments(editor, project: dict[str, Any] | None) -> int:
    """Restore persisted STT1/STT2 candidate lanes into the editor timeline."""
    if editor is None or not isinstance(project, dict):
        return 0
    previews = project_stt_preview_segments(project)
    restored = [dict(row) for row in previews if isinstance(row, dict)]
    try:
        setattr(editor, "_live_stt_preview_segments", restored)
    except Exception:
        return 0
    if not restored:
        return 0

    redraw = getattr(editor, "_redraw_timeline_with_live_preview", None)
    if callable(redraw):
        try:
            redraw()
            return len(restored)
        except Exception:
            pass

    update_with_preview = getattr(editor, "_update_timeline_with_confirmed_and_preview", None)
    if callable(update_with_preview):
        try:
            current = getattr(editor, "_get_current_segments", lambda: [])()
            update_with_preview(list(current or []))
            return len(restored)
        except Exception:
            pass

    timeline = getattr(editor, "timeline", None)
    if timeline is not None and hasattr(timeline, "update_segments"):
        try:
            current = list(getattr(editor, "_get_current_segments", lambda: [])() or [])
        except Exception:
            current = list(getattr(editor, "_cached_segs", []) or [])
        def _sort_sec(seg: dict[str, Any], key: str) -> float:
            try:
                return float(seg.get(key, 0.0) or 0.0)
            except Exception:
                return 0.0
        combined = sorted(
            [
                dict(seg)
                for seg in current + restored
                if isinstance(seg, dict) and not seg.get("is_gap")
            ],
            key=lambda seg: (
                _sort_sec(seg, "start"),
                _sort_sec(seg, "end"),
                str(seg.get("stt_preview_source", "") or ""),
            ),
        )
        try:
            total_dur = max(float(seg.get("end", 0.0) or 0.0) for seg in combined) if combined else 0.0
        except Exception:
            total_dur = 0.0
        try:
            video_player = getattr(editor, "video_player", None)
            total_dur = max(total_dur, float(getattr(video_player, "total_time", 0.0) or 0.0))
        except Exception:
            pass
        try:
            timeline.update_segments(combined, getattr(editor, "_active_seg_start", None), total_dur)
        except Exception:
            pass
    return len(restored)


def apply_project_ui_state(owner, editor, project_path: str) -> None:
    if not project_path or not os.path.exists(project_path):
        return
    try:
        data = read_project_file(project_path)
    except Exception:
        return
    ws = data.get('workspace', {}) or {}
    timeline = getattr(editor, 'timeline', None)
    lock_chk = getattr(timeline, 'lock_chk', None) if timeline else None
    try:
        if hasattr(editor, 'splitter') and editor.splitter is not None and ws.get('splitter_sizes'):
            editor.splitter.setSizes(list(ws.get('splitter_sizes', [])))
    except Exception:
        pass
    try:
        if timeline is not None and hasattr(timeline, 'fit_to_view'):
            timeline.fit_to_view()
    except Exception:
        pass
    try:
        if lock_chk is not None:
            lock_chk.setChecked(bool(ws.get('edit_lock', False)))
    except Exception:
        pass
    try:
        sec = float(ws.get('last_playhead', 0.0) or 0.0)
        if timeline and hasattr(timeline, 'set_playhead'):
            timeline.set_playhead(sec)
        setattr(editor, '_current_sec', sec)
    except Exception:
        pass
    try:
        line = ws.get('selected_segment_line', ws.get('last_cursor_block'))
        te = getattr(editor, 'text_edit', None)
        if te is not None and line is not None:
            cur = te.textCursor()
            block = te.document().findBlockByNumber(int(line))
            if block.isValid():
                cur.setPosition(block.position())
                te.setTextCursor(cur)
    except Exception:
        pass
    try:
        setattr(editor, '_active_clip_idx', int(ws.get('active_clip_idx', 0) or 0))
    except Exception:
        pass
    try:
        restore_project_stt_preview_segments(editor, data)
    except Exception:
        pass
    try:
        restore_stt = getattr(editor, "_restore_stt_mode_project_state", None)
        if callable(restore_stt):
            restore_stt(data)
    except Exception:
        pass
    try:
        if hasattr(owner, '_log_visible'):
            owner._log_visible = bool(ws.get('terminal_visible', False))
        if hasattr(owner, '_apply_log_visible'):
            owner._apply_log_visible(bool(ws.get('terminal_visible', False)))
        if hasattr(owner, '_dashboard_mode'):
            owner._dashboard_mode = ws.get('dashboard_mode', 'dashboard') or 'dashboard'
        if hasattr(owner, '_project_panel_visible'):
            owner._project_panel_visible = bool(ws.get('project_panel_visible', True))
    except Exception:
        pass
