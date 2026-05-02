# Version: 03.09.28
# Phase: PHASE2
"""
core/project/project_snapshot.py
Project JSON save/load helpers for PHASE1-B.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import config
from core.project.project_context import build_editor_state

PROJECTS_DIR = os.path.join(config.BASE_DIR, 'projects')
os.makedirs(PROJECTS_DIR, exist_ok=True)
PROJECT_SCHEMA_VERSION = '03.00.26'


def _safe_name(name: str) -> str:
    banned = r'<>:"/\|?*'
    out = ''.join('_' if c in banned else c for c in (name or '').strip())
    out = out.strip().strip('.')
    return out or 'untitled_project'


def _editor_from_owner(owner):
    for key in ('_editor_widget', 'editor', 'current_editor'):
        obj = getattr(owner, key, None)
        if obj is not None:
            return obj
    return None


def _selected_segment_line(editor) -> int | None:
    try:
        te = getattr(editor, 'text_edit', None)
        if te is None:
            return None
        return te.textCursor().blockNumber()
    except Exception:
        return None


def _ui_state(editor) -> dict[str, Any]:
    state: dict[str, Any] = {}
    try:
        timeline = getattr(editor, 'timeline', None)
        lock_chk = getattr(timeline, 'lock_chk', None) if timeline else None
        state['playhead_sec'] = float(getattr(editor, '_current_sec', 0.0) or 0.0)
        state['selected_segment_line'] = _selected_segment_line(editor)
        state['edit_lock'] = bool(lock_chk.isChecked()) if lock_chk is not None else False
        state['log_visible'] = bool(getattr(editor, '_log_visible', False) or getattr(editor, 'log_visible', False))
        if hasattr(editor, 'splitter') and editor.splitter is not None:
            try:
                state['splitter_sizes'] = list(editor.splitter.sizes())
            except Exception:
                pass
        if hasattr(editor, '_active_clip_idx'):
            state['active_clip_idx'] = int(getattr(editor, '_active_clip_idx', 0) or 0)
    except Exception:
        pass
    return state


def _normalized_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for seg in segments or []:
        out.append({
            'start': float(seg.get('start', 0.0) or 0.0),
            'end': float(seg.get('end', 0.0) or 0.0),
            'text': str(seg.get('text', '') or ''),
            'speaker': str(seg.get('speaker', seg.get('spk', '00')) or '00'),
            'speaker_list': list(seg.get('speaker_list', [])) if seg.get('speaker_list') else [],
            'stt_mode': bool(seg.get('stt_mode', False)),
            'stt_pending': bool(seg.get('stt_pending', False)),
            'original_text': str(seg.get('original_text', '') or ''),
            'dictated_text': str(seg.get('dictated_text', '') or ''),
        })
    return out


def _auto_project_path(owner, media_files: list[str], mode: str) -> str:
    current = getattr(owner, '_current_project_path', None)
    if current:
        return current
    project_name = getattr(owner, '_project_name', None)
    if project_name:
        base = _safe_name(project_name)
    elif mode == 'multiclip':
        if media_files:
            first = os.path.splitext(os.path.basename(media_files[0]))[0]
            base = _safe_name(f'{first}_multiclip')
        else:
            base = 'multiclip_project'
    else:
        media_path = media_files[0] if media_files else getattr(_editor_from_owner(owner), 'media_path', '')
        base = _safe_name(os.path.splitext(os.path.basename(media_path))[0] if media_path else 'single_project')
    return os.path.join(PROJECTS_DIR, f'{base}.json')


def build_project_payload(owner, segments: list[dict[str, Any]] | None = None, srt_path: str | None = None) -> dict[str, Any]:
    editor = _editor_from_owner(owner)
    media_files = []
    if getattr(owner, '_multiclip_files', None):
        media_files = [os.path.abspath(p) for p in list(getattr(owner, '_multiclip_files', []))]
    elif editor is not None and getattr(editor, 'media_path', None):
        media_files = [os.path.abspath(editor.media_path)]
    mode = 'multiclip' if len(media_files) > 1 else 'single'
    project_path = _auto_project_path(owner, media_files, mode)
    editor_state = build_editor_state(
        mode=mode,
        media_files=media_files,
        segments=segments or [],
        workspace=_ui_state(editor) if editor is not None else {},
        clip_boundaries=list(getattr(owner, '_multiclip_boundaries', []) or []),
    )
    payload = {
        'version': PROJECT_SCHEMA_VERSION,
        'phase': 'PHASE2',
        'mode': mode,
        'project_path': os.path.abspath(project_path),
        'project_name': os.path.splitext(os.path.basename(project_path))[0],
        'saved_at': datetime.now().isoformat(timespec='seconds'),
        'media_files': media_files,
        'srt_path': os.path.abspath(srt_path) if srt_path else None,
        'segments': _normalized_segments(segments or []),
        'ui_state': editor_state.get('workspace', {}),
        'editor_state': editor_state,
        'project_meta': {
            'project_boundary_times': list(getattr(owner, '_project_boundary_times', []) or []),
            'multiclip_boundaries': list(getattr(owner, '_multiclip_boundaries', []) or []),
            'sorted_files': list(getattr(owner, '_multiclip_files', []) or []),
        },
    }
    try:
        if os.path.exists(project_path):
            with open(project_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            payload['roughcut_state'] = existing.get('roughcut_state', {})
    except Exception:
        payload['roughcut_state'] = {}
    payload.setdefault('roughcut_state', {})
    return payload


def save_project_snapshot(owner, segments: list[dict[str, Any]] | None = None, srt_path: str | None = None, reason: str = 'manual') -> str:
    payload = build_project_payload(owner, segments=segments, srt_path=srt_path)
    payload['save_reason'] = reason
    project_path = payload['project_path']
    os.makedirs(os.path.dirname(project_path), exist_ok=True)
    with open(project_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    setattr(owner, '_current_project_path', project_path)
    return project_path


def load_project_snapshot(project_path: str) -> dict[str, Any]:
    with open(project_path, 'r', encoding='utf-8') as f:
        return json.load(f)
