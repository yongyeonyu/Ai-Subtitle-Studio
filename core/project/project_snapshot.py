# Version: 03.14.28
# Phase: PHASE2
"""
core/project/project_snapshot.py
Project JSON save/load helpers for PHASE1-B.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from core.runtime import config
from core.frame_time import normalize_fps, sec_to_frame
from core.project.project_context import STT_SEGMENT_METADATA_KEYS, build_editor_state, project_stt_preview_segments
from core.project.project_assets import externalize_project_text_assets, hydrate_project_text_asset_cache
from core.project.subtitle_status import subtitle_status_payload
from core.project.project_io import read_project_file, write_project_file

PROJECTS_DIR = getattr(config, "PROJECTS_DIR", os.path.join(config.BASE_DIR, 'projects'))
os.makedirs(PROJECTS_DIR, exist_ok=True)
PROJECT_SCHEMA_VERSION = '03.00.26'
PROJECT_STORAGE_SCHEMA = "ai_subtitle_studio.project.vector.v1"


def _safe_name(name: str) -> str:
    banned = r'<>:"/\|?*'
    out = ''.join('_' if c in banned else c for c in (name or '').strip())
    out = out.strip().strip('.')
    return out or 'untitled_project'


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


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
        fps = _editor_primary_fps(editor)
        playhead_sec = float(getattr(editor, '_current_sec', 0.0) or 0.0)
        canvas = getattr(timeline, 'canvas', None) if timeline else None
        if canvas is not None:
            playhead_sec = float(getattr(canvas, 'playhead_sec', playhead_sec) or playhead_sec)
        state['playhead_frame'] = sec_to_frame(playhead_sec, fps)
        state['playhead_sec'] = state['playhead_frame'] / fps
        state['timeline_frame_rate'] = fps
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


def _editor_primary_fps(editor) -> float:
    try:
        player = getattr(editor, "video_player", None)
        return normalize_fps(
            getattr(editor, "video_fps", None)
            or getattr(player, "frame_rate", None)
            or 30.0
        )
    except Exception:
        return 30.0


def _normalized_segments(segments: list[dict[str, Any]], *, primary_fps: float = 30.0) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps)
    out = []
    for seg in segments or []:
        start = float(seg.get('start', 0.0) or 0.0)
        end = float(seg.get('end', start) or start)
        frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
        start_frame = seg.get("start_frame", seg.get("timeline_start_frame", frame_range.get("start")))
        end_frame = seg.get("end_frame", seg.get("timeline_end_frame", frame_range.get("end")))
        if start_frame is None:
            start_frame = sec_to_frame(start, fps)
        if end_frame is None:
            end_frame = sec_to_frame(max(start, end), fps)
        start_frame = _safe_int(start_frame)
        end_frame = max(start_frame, _safe_int(end_frame, start_frame))
        item = {
            'start': start_frame / fps,
            'end': end_frame / fps,
            'text': str(seg.get('text', '') or ''),
            'speaker': str(seg.get('speaker', seg.get('spk', '00')) or '00'),
            'speaker_list': list(seg.get('speaker_list', [])) if seg.get('speaker_list') else [],
            'stt_mode': bool(seg.get('stt_mode', False)),
            'stt_pending': bool(seg.get('stt_pending', False)),
            'original_text': str(seg.get('original_text', '') or ''),
            'dictated_text': str(seg.get('dictated_text', '') or ''),
            'start_frame': start_frame,
            'end_frame': end_frame,
            'timeline_start_frame': start_frame,
            'timeline_end_frame': end_frame,
            'frame_rate': fps,
            'timeline_frame_rate': fps,
            'frame_range': {
                'unit': 'frame',
                'start': start_frame,
                'end': end_frame,
                'timeline_frame_rate': fps,
            },
        }
        for key in STT_SEGMENT_METADATA_KEYS:
            if key in seg:
                item[key] = seg.get(key)
        for key in ("quality", "quality_history", "quality_candidates", "quality_stale"):
            if key in seg:
                item[key] = seg.get(key)
        item.update({key: value for key, value in subtitle_status_payload(item).items() if value not in (None, "")})
        out.append(item)
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
    stt_preview_segments = list(getattr(editor, "_live_stt_preview_segments", []) or []) if editor is not None else []
    existing_project = {}
    try:
        if os.path.exists(project_path):
            existing_project = read_project_file(project_path)
            if not stt_preview_segments:
                stt_preview_segments = project_stt_preview_segments(existing_project)
    except Exception:
        existing_project = {}
    provisional_cut_boundaries = []
    voice_activity_segments = []
    if editor is not None:
        canvas = getattr(getattr(editor, "timeline", None), "canvas", None)
        if canvas is not None:
            try:
                if hasattr(canvas, "_refresh_voice_activity_segments"):
                    canvas._refresh_voice_activity_segments()
                voice_activity_segments = list(getattr(canvas, "voice_activity_segments", []) or [])
                provisional_cut_boundaries = list(getattr(canvas, "scan_boundary_times", []) or [])
            except Exception:
                voice_activity_segments = []
                provisional_cut_boundaries = []
        if not provisional_cut_boundaries:
            provisional_cut_boundaries = list(getattr(editor, "_auto_cut_boundary_scan_lines", []) or [])

    cut_boundaries = [
        row if isinstance(row, dict) else {"timeline_sec": row, "time": row, "status": "verified"}
        for row in list(getattr(owner, '_project_boundary_times', []) or [])
    ]
    primary_fps = _editor_primary_fps(editor) if editor is not None else 30.0
    editor_state = build_editor_state(
        mode=mode,
        media_files=media_files,
        segments=segments or [],
        workspace=_ui_state(editor) if editor is not None else {},
        clip_boundaries=list(getattr(owner, '_multiclip_boundaries', []) or []),
        stt_preview_segments=stt_preview_segments,
        cut_boundaries=cut_boundaries,
        provisional_cut_boundaries=provisional_cut_boundaries,
        primary_fps=primary_fps,
    )
    payload = {
        'version': PROJECT_SCHEMA_VERSION,
        'storage_schema': PROJECT_STORAGE_SCHEMA,
        'phase': 'PHASE2',
        'mode': mode,
        'project_path': os.path.abspath(project_path),
        'project_name': os.path.splitext(os.path.basename(project_path))[0],
        'saved_at': datetime.now().isoformat(timespec='seconds'),
        'media_files': media_files,
        'srt_path': os.path.abspath(srt_path) if srt_path else None,
        'subtitles': {
            'storage': 'editor_state.rendering.subtitle_canvas',
            'segment_count': len(segments or []),
            'srt_path': os.path.abspath(srt_path) if srt_path else '',
        },
        'ui_state': editor_state.get('workspace', {}),
        'editor_state': editor_state,
        'project_meta': {
            'project_boundary_times': list(getattr(owner, '_project_boundary_times', []) or []),
            'multiclip_boundaries': list(getattr(owner, '_multiclip_boundaries', []) or []),
            'sorted_files': list(getattr(owner, '_multiclip_files', []) or []),
        },
    }
    if voice_activity_segments:
        payload.setdefault("analysis", {})
        payload["analysis"]["voice_activity_schema"] = "subtitle_detection.v1"
        payload["analysis"]["voice_activity_segments"] = voice_activity_segments
        payload["editor_state"].setdefault("analysis", {})
        payload["editor_state"]["analysis"]["voice_activity_segments"] = voice_activity_segments
    stt_tracks = (editor_state.get("stt", {}) or {}).get("candidate_tracks")
    if isinstance(stt_tracks, dict) and stt_tracks:
        payload.setdefault("analysis", {})
        payload["analysis"]["stt_candidate_schema"] = "stt_candidate_tracks.v1"
        payload["analysis"]["stt_candidate_tracks"] = stt_tracks
        payload["analysis"]["stt_candidate_counts"] = {
            str(source): len(rows)
            for source, rows in stt_tracks.items()
            if isinstance(rows, list)
        }
    payload['roughcut_state'] = existing_project.get('roughcut_state', {}) if isinstance(existing_project, dict) else {}
    payload.setdefault('roughcut_state', {})
    externalize_project_text_assets(
        project_path,
        payload,
        final_segments=segments or [],
        stt_tracks=stt_tracks if isinstance(stt_tracks, dict) else {},
    )
    return payload


def save_project_snapshot(owner, segments: list[dict[str, Any]] | None = None, srt_path: str | None = None, reason: str = 'manual') -> str:
    payload = build_project_payload(owner, segments=segments, srt_path=srt_path)
    payload['save_reason'] = reason
    project_path = payload['project_path']
    write_project_file(project_path, payload)
    setattr(owner, '_current_project_path', project_path)
    return project_path


def load_project_snapshot(project_path: str) -> dict[str, Any]:
    return hydrate_project_text_asset_cache(read_project_file(project_path)) or {}
