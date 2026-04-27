# Version: 02.03.11
# Phase: PHASE1-C
"""
core/project/project_phase1b.py
PHASE1-B project save/load extension helpers.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any


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
    canvas = getattr(timeline, 'canvas', None) if timeline else None
    scroll = getattr(timeline, 'scroll', None) if timeline else None
    lock_chk = getattr(timeline, 'lock_chk', None) if timeline else None
    state: dict[str, Any] = {
        'last_playhead': float(getattr(editor, '_current_sec', 0.0) or 0.0),
        'zoom_pps': float(getattr(canvas, 'pps', 0.0) or 0.0) if canvas else 0.0,
        'splitter_sizes': [],
        'terminal_visible': bool(getattr(owner, '_log_visible', False) or getattr(editor, '_log_visible', False) or getattr(editor, 'log_visible', False)),
        'dashboard_mode': getattr(owner, '_dashboard_mode', 'dashboard') or 'dashboard',
        'project_panel_visible': bool(getattr(owner, '_project_panel_visible', True)),
        'last_cursor_block': _selected_segment_line(editor),
        'selected_segment_line': _selected_segment_line(editor),
        'edit_lock': bool(lock_chk.isChecked()) if lock_chk is not None else False,
        'scroll_x': 0,
        'active_clip_idx': int(getattr(editor, '_active_clip_idx', getattr(owner, '_active_clip_idx', 0)) or 0),
    }
    if scroll and scroll.horizontalScrollBar():
        try:
            state['scroll_x'] = int(scroll.horizontalScrollBar().value())
        except Exception:
            pass
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


def _normalize_segments_for_legacy(segments: list[dict[str, Any]] | None, existing: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not segments:
        return existing or []
    out = []
    for idx, seg in enumerate(segments, 1):
        start = float(seg.get('start', 0.0) or 0.0)
        end = float(seg.get('end', 0.0) or 0.0)
        out.append({
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
        })
    return out


def enrich_existing_project_file(project_path: str, owner, editor, segments: list[dict[str, Any]] | None = None, srt_path: str | None = None) -> str:
    if not project_path or not os.path.exists(project_path):
        return project_path
    with open(project_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    media_files = _media_paths(owner, editor, data)
    mode = 'multiclip' if len(media_files) > 1 else 'single'
    data['version'] = '02.03.00'
    data['phase'] = 'PHASE1-B'
    data['mode'] = mode
    data['updated_at'] = datetime.now().isoformat(timespec='seconds')
    data['workspace'] = {**data.get('workspace', {}), **_workspace_snapshot(owner, editor)}
    data['project_meta'] = _project_meta(owner)
    subtitles = dict(data.get('subtitles', {}) or {})
    subtitles['srt_path'] = _safe_abs(srt_path) or subtitles.get('srt_path')
    subtitles['segments'] = _normalize_segments_for_legacy(segments, subtitles.get('segments'))
    data['subtitles'] = subtitles
    if media_files:
        data['media'] = [
            {'order': i, 'path': path, 'type': 'video', 'duration': 0.0, 'offset': 0.0}
            for i, path in enumerate(media_files)
        ]
    with open(project_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return project_path


def apply_project_ui_state(owner, editor, project_path: str) -> None:
    if not project_path or not os.path.exists(project_path):
        return
    try:
        with open(project_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return
    ws = data.get('workspace', {}) or {}
    timeline = getattr(editor, 'timeline', None)
    canvas = getattr(timeline, 'canvas', None) if timeline else None
    scroll = getattr(timeline, 'scroll', None) if timeline else None
    lock_chk = getattr(timeline, 'lock_chk', None) if timeline else None
    try:
        if hasattr(editor, 'splitter') and editor.splitter is not None and ws.get('splitter_sizes'):
            editor.splitter.setSizes(list(ws.get('splitter_sizes', [])))
    except Exception:
        pass
    try:
        pps = float(ws.get('zoom_pps', 0.0) or 0.0)
        if canvas is not None and pps > 0:
            canvas.pps = pps
            canvas.update()
    except Exception:
        pass
    try:
        if lock_chk is not None:
            lock_chk.setChecked(bool(ws.get('edit_lock', False)))
    except Exception:
        pass
    try:
        if scroll and scroll.horizontalScrollBar():
            scroll.horizontalScrollBar().setValue(int(ws.get('scroll_x', 0) or 0))
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
