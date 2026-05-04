# Version: 03.09.29
# Phase: PHASE2
"""
core/project/project_context.py
Project JSON adapter for editor / roughcut state separation.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.work_mode import EDITOR_MODE, normalize_work_mode
from core.project.subtitle_status import subtitle_status_payload
from core.cut_boundary import (
    CUT_BOUNDARY_PROVISIONAL_SCHEMA,
    CUT_BOUNDARY_SCHEMA,
    normalize_cut_boundaries,
    project_cut_provisional_boundaries,
)

STT_SEGMENT_METADATA_KEYS = (
    "stt_candidates",
    "stt_selected_source",
    "stt_ensemble_source",
    "stt_ensemble_similarity",
    "stt_ensemble_needs_llm_review",
    "stt_ensemble_inserted_from_stt2",
    "stt_ensemble_primary_locked",
    "stt_ensemble_word_rover",
    "stt_ensemble_llm_selected_source",
    "stt_ensemble_llm_selected_label",
    "stt_ensemble_context_prev",
    "stt_ensemble_context_next",
    "stt_preview_source",
    "score",
    "stt_score",
    "score_color",
    "stt_score_color",
    "stt_score_label",
    "stt_score_flags",
    "stt_score_components",
    "subtitle_review_state",
    "subtitle_status_color",
    "subtitle_status_schema",
    "subtitle_status_score",
    "subtitle_status_source",
    "_live_stt_preview",
)

NON_PERSISTED_WORKSPACE_KEYS = {
    "zoom_pps",
    "pps",
    "scroll_position",
    "scroll_x",
    "timeline_zoom",
    "timeline_pps",
}


def sanitize_workspace_state(workspace: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(workspace, dict):
        return {}
    return {
        str(key): value
        for key, value in workspace.items()
        if str(key) not in NON_PERSISTED_WORKSPACE_KEYS
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def project_media_files(project: dict[str, Any]) -> list[str]:
    editor_state = project.get("editor_state", {}) or {}
    media_files = editor_state.get("media_files")
    if isinstance(media_files, list) and media_files:
        return [str(path) for path in media_files if path]

    media = project.get("media", []) or []
    if media:
        return [
            str(item.get("path", ""))
            for item in sorted(media, key=lambda item: item.get("order", 0))
            if item.get("path")
        ]

    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", []) or []
    return [
        str(clip.get("source_path", ""))
        for clip in sorted(clips, key=lambda item: item.get("order", 0))
        if clip.get("source_path")
    ]


def project_clip_boundaries(project: dict[str, Any]) -> list[dict[str, Any]]:
    editor_state = project.get("editor_state", {}) or {}
    multiclip = editor_state.get("multiclip", {}) or {}
    stored = multiclip.get("boundaries")
    if isinstance(stored, list) and stored:
        return [_normalize_boundary(item, idx) for idx, item in enumerate(stored)]

    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", []) or []
    boundaries = []
    for idx, clip in enumerate(sorted(clips, key=lambda item: item.get("order", 0))):
        path = str(clip.get("source_path", "") or "")
        start = _safe_float(clip.get("timeline_start"))
        end = _safe_float(clip.get("timeline_end"), start)
        boundaries.append(
            {
                "start": start,
                "end": max(start, end),
                "file": path,
                "name": os.path.basename(path),
            }
        )
    return boundaries


def project_mode(project: dict[str, Any]) -> str:
    editor_state = project.get("editor_state", {}) or {}
    mode = str(editor_state.get("mode") or project.get("mode") or "")
    if mode in {"single", "multiclip"}:
        return mode
    return "multiclip" if len(project_media_files(project)) > 1 else "single"


def project_workspace(project: dict[str, Any]) -> dict[str, Any]:
    editor_state = project.get("editor_state", {}) or {}
    workspace = editor_state.get("workspace")
    if isinstance(workspace, dict) and workspace:
        return sanitize_workspace_state(workspace)
    workspace = project.get("workspace")
    return sanitize_workspace_state(workspace)


def project_active_work_mode(project: dict[str, Any]) -> str:
    mode = str(project_workspace(project).get("active_work_mode", "") or "")
    return normalize_work_mode(mode, EDITOR_MODE)


def project_roughcut_state(project: dict[str, Any]) -> dict[str, Any]:
    state = project.get("roughcut_state", {}) or {}
    return dict(state) if isinstance(state, dict) else {}


def project_voice_activity_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    editor_analysis = (project.get("editor_state", {}) or {}).get("analysis", {}) or {}
    raw_segments = editor_analysis.get("voice_activity_segments")
    if not isinstance(raw_segments, list):
        raw_segments = (project.get("analysis", {}) or {}).get("voice_activity_segments", [])
    if not isinstance(raw_segments, list):
        return []
    timebase = (project.get("timeline", {}) or {}).get("timebase", {}) or project.get("frame_timebase", {}) or {}
    primary_fps = normalize_fps(timebase.get("primary_fps", 30.0) or 30.0)
    out = []
    for idx, item in enumerate(raw_segments):
        if not isinstance(item, dict):
            continue
        start = _safe_float(item.get("start", 0.0))
        end = _safe_float(item.get("end", start), start)
        frame_range = item.get("frame_range", {}) if isinstance(item.get("frame_range"), dict) else {}
        start_frame = item.get("start_frame", item.get("timeline_start_frame", frame_range.get("start")))
        end_frame = item.get("end_frame", item.get("timeline_end_frame", frame_range.get("end")))
        if start_frame is not None:
            start = frame_to_sec(start_frame, primary_fps)
        if end_frame is not None:
            end = frame_to_sec(end_frame, primary_fps)
        seg = {
            "index": int(item.get("index", idx + 1) or idx + 1),
            "start": start,
            "end": max(start, end),
            "kind": str(item.get("kind", "uncertain") or "uncertain"),
            "label": str(item.get("label", "") or ""),
            "source": str(item.get("source", "") or ""),
            "color": str(item.get("color", "") or ""),
        }
        for key in ("score", "priority", "alpha", "selection_state", "selected_source"):
            if key in item:
                seg[key] = item.get(key)
        if start_frame is not None:
            seg["start_frame"] = _safe_int(start_frame)
            seg["timeline_start_frame"] = _safe_int(start_frame)
        if end_frame is not None:
            seg["end_frame"] = _safe_int(end_frame)
            seg["timeline_end_frame"] = _safe_int(end_frame)
        seg["frame_rate"] = primary_fps
        seg["timeline_frame_rate"] = primary_fps
        seg["frame_range"] = {
            "unit": "frame",
            "start": seg.get("start_frame"),
            "end": seg.get("end_frame"),
            "timeline_frame_rate": primary_fps,
        }
        out.append(seg)
    return out


def project_cut_boundary_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    timebase = (project.get("timeline", {}) or {}).get("timebase", {}) or project.get("frame_timebase", {}) or {}
    primary_fps = normalize_fps(timebase.get("primary_fps", 30.0) or 30.0)
    analysis = project.get("analysis", {}) or {}
    raw = analysis.get("cut_boundaries")
    if not isinstance(raw, list):
        raw = ((project.get("editor_state", {}) or {}).get("multiclip", {}) or {}).get("cut_boundaries")
    if not isinstance(raw, list):
        return []
    return normalize_cut_boundaries(raw, primary_fps=primary_fps)


def project_cut_boundary_provisional_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    timebase = (project.get("timeline", {}) or {}).get("timebase", {}) or project.get("frame_timebase", {}) or {}
    primary_fps = normalize_fps(timebase.get("primary_fps", 30.0) or 30.0)
    return project_cut_provisional_boundaries(project, primary_fps=primary_fps)


def project_stt_preview_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    editor_state = project.get("editor_state", {}) or {}
    stt_state = editor_state.get("stt", {}) or {}
    raw_segments = stt_state.get("preview_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raw_segments = editor_state.get("stt_preview_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        tracks = stt_state.get("candidate_tracks")
        if not isinstance(tracks, dict):
            tracks = (editor_state.get("analysis", {}) or {}).get("stt_candidate_tracks")
        if not isinstance(tracks, dict):
            tracks = (project.get("analysis", {}) or {}).get("stt_candidate_tracks")
        if isinstance(tracks, dict):
            raw_segments = []
            for source, rows in tracks.items():
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if isinstance(row, dict):
                        item = dict(row)
                        item["stt_preview_source"] = str(source)
                        raw_segments.append(item)
    if not isinstance(raw_segments, list):
        return []
    timebase = (project.get("timeline", {}) or {}).get("timebase", {}) or project.get("frame_timebase", {}) or {}
    primary_fps = normalize_fps(timebase.get("primary_fps", 30.0) or 30.0)
    return _normalize_stt_preview_segments(raw_segments, primary_fps=primary_fps)


def project_segments_to_editor(project: dict[str, Any]) -> list[dict[str, Any]]:
    editor_state = project.get("editor_state", {}) or {}
    editor_subtitles = editor_state.get("subtitles", {}) or {}
    raw_segments = editor_subtitles.get("segments")
    if not isinstance(raw_segments, list):
        raw_segments = project.get("segments")
    if not isinstance(raw_segments, list):
        raw_segments = (project.get("subtitles", {}) or {}).get("segments", [])

    boundaries = project_clip_boundaries(project)
    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", []) or []
    clip_by_id = {str(clip.get("id", "")): clip for clip in clips if clip.get("id")}
    timebase = (project.get("timeline", {}) or {}).get("timebase", {}) or project.get("frame_timebase", {}) or {}
    primary_fps = normalize_fps(timebase.get("primary_fps", 30.0) or 30.0)

    out = []
    for idx, seg in enumerate(raw_segments or []):
        start = _safe_float(seg.get("start", seg.get("timeline_start", 0.0)))
        end = _safe_float(seg.get("end", seg.get("timeline_end", start)), start)
        frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
        start_frame = seg.get("start_frame", seg.get("timeline_start_frame", frame_range.get("start")))
        end_frame = seg.get("end_frame", seg.get("timeline_end_frame", frame_range.get("end")))
        if start_frame is not None:
            start = frame_to_sec(start_frame, primary_fps)
        if end_frame is not None:
            end = frame_to_sec(end_frame, primary_fps)
        clip_file = str(seg.get("_clip_file", "") or "")
        clip_idx = seg.get("_clip_idx")

        clip_id = str(seg.get("clip_id", "") or "")
        if not clip_file and clip_id in clip_by_id:
            clip = clip_by_id[clip_id]
            clip_file = str(clip.get("source_path", "") or "")
        if clip_idx is None and clip_file and boundaries:
            for b_idx, boundary in enumerate(boundaries):
                if boundary.get("file") == clip_file:
                    clip_idx = b_idx
                    break
        if clip_idx is None and boundaries:
            for b_idx, boundary in enumerate(boundaries):
                if _safe_float(boundary.get("start")) <= start < _safe_float(boundary.get("end")) + 0.001:
                    clip_idx = b_idx
                    clip_file = str(boundary.get("file", "") or clip_file)
                    break

        item = {
            "line": idx,
            "start": start,
            "end": max(start, end),
            "text": str(seg.get("text", "") or ""),
            "speaker": str(seg.get("speaker", seg.get("spk", "00")) or "00"),
            "speaker_list": list(seg.get("speaker_list", []) or []),
            "stt_mode": bool(seg.get("stt_mode", False)),
            "stt_pending": bool(seg.get("stt_pending", False)),
            "original_text": str(seg.get("original_text", "") or ""),
            "dictated_text": str(seg.get("dictated_text", "") or ""),
        }
        if start_frame is not None:
            item["start_frame"] = _safe_int(start_frame)
            item["timeline_start_frame"] = _safe_int(start_frame)
        if end_frame is not None:
            item["end_frame"] = _safe_int(end_frame)
            item["timeline_end_frame"] = _safe_int(end_frame)
        item["frame_rate"] = primary_fps
        item["timeline_frame_rate"] = primary_fps
        item["frame_range"] = {
            "unit": "frame",
            "start": item.get("start_frame"),
            "end": item.get("end_frame"),
            "timeline_frame_rate": primary_fps,
        }
        if clip_idx is not None:
            item["_clip_idx"] = int(clip_idx)
        if clip_file:
            item["_clip_file"] = clip_file
        if seg.get("words"):
            item["words"] = list(seg.get("words") or [])
        for key in ("quality", "quality_history", "quality_candidates", "quality_stale"):
            if key in seg:
                value = seg.get(key)
                if isinstance(value, (dict, list, bool)):
                    item[key] = value
        for key in STT_SEGMENT_METADATA_KEYS:
            if key in seg:
                item[key] = seg.get(key)
        item.update({key: value for key, value in subtitle_status_payload(item).items() if value not in (None, "")})
        out.append(item)
    return out


def build_editor_state(
    *,
    mode: str,
    media_files: list[str],
    segments: list[dict[str, Any]],
    workspace: dict[str, Any] | None = None,
    clip_boundaries: list[dict[str, Any]] | None = None,
    stt_preview_segments: list[dict[str, Any]] | None = None,
    cut_boundaries: list[dict[str, Any]] | None = None,
    provisional_cut_boundaries: list[dict[str, Any]] | None = None,
    primary_fps: float | None = None,
) -> dict[str, Any]:
    mode = "multiclip" if mode == "multiclip" or len(media_files) > 1 else "single"
    fps = normalize_fps(primary_fps or 30.0)
    normalized_segments = _normalize_editor_segments(segments, primary_fps=fps)
    boundaries = [_normalize_boundary(item, idx) for idx, item in enumerate(clip_boundaries or [])]
    stt_preview = _normalize_stt_preview_segments(
        stt_preview_segments or [],
        primary_fps=fps,
    )
    stt_candidate_tracks = build_stt_candidate_tracks(
        normalized_segments,
        stt_preview,
        primary_fps=fps,
    )
    cut_boundary_rows = normalize_cut_boundaries(
        cut_boundaries or [],
        primary_fps=fps,
    )
    provisional_cut_boundary_rows = normalize_cut_boundaries(
        provisional_cut_boundaries or [],
        primary_fps=fps,
    )
    return {
        "schema": "ai_subtitle_studio.editor_state.v1",
        "mode": mode,
        "media_files": [os.path.abspath(path) for path in media_files if path],
        "single_clip": {
            "source_path": os.path.abspath(media_files[0]) if media_files and mode == "single" else "",
        },
        "multiclip": {
            "files": [os.path.abspath(path) for path in media_files if path] if mode == "multiclip" else [],
            "boundaries": boundaries if mode == "multiclip" else [],
            "cut_boundary_schema": CUT_BOUNDARY_SCHEMA,
            "cut_boundaries": cut_boundary_rows if mode == "multiclip" else [],
            "cut_boundary_provisional_schema": CUT_BOUNDARY_PROVISIONAL_SCHEMA,
            "cut_boundary_provisional_boundaries": provisional_cut_boundary_rows if mode == "multiclip" else [],
        },
        "subtitles": {
            "segments": normalized_segments,
            "segment_signature": segment_signature(normalized_segments),
        },
        "stt": {
            "schema": "stt_candidates.v1",
            "preview_segments": stt_preview,
            "candidate_tracks": stt_candidate_tracks,
            "candidate_counts": {
                source: len(rows)
                for source, rows in stt_candidate_tracks.items()
            },
        },
        "analysis": {
            "cut_boundary_schema": CUT_BOUNDARY_SCHEMA,
            "cut_boundaries": cut_boundary_rows,
            "cut_boundary_provisional_schema": CUT_BOUNDARY_PROVISIONAL_SCHEMA,
            "cut_boundary_provisional_boundaries": provisional_cut_boundary_rows,
            "stt_candidate_tracks": stt_candidate_tracks,
        },
        "workspace": sanitize_workspace_state(workspace),
    }


def build_stt_candidate_tracks(
    segments: list[dict[str, Any]] | None,
    preview_segments: list[dict[str, Any]] | None = None,
    *,
    primary_fps: float = 30.0,
) -> dict[str, list[dict[str, Any]]]:
    """Persist STT1/STT2 candidate subtitles as independent project tracks."""
    fps = normalize_fps(primary_fps or 30.0)
    tracks: dict[str, list[dict[str, Any]]] = {"STT1": [], "STT2": []}
    seen: set[tuple[str, int, int, str]] = set()

    def add_row(source: str, row: dict[str, Any], parent: dict[str, Any] | None = None) -> None:
        if not isinstance(row, dict):
            return
        source_key = _normalize_stt_source(source or row.get("source") or row.get("stt_preview_source"))
        if source_key not in tracks:
            return
        text = str(row.get("text", "") or "").strip()
        if not text:
            return
        parent = parent or {}
        start = _safe_float(row.get("start", row.get("timeline_start", parent.get("start", 0.0))))
        end = _safe_float(row.get("end", row.get("timeline_end", parent.get("end", start))), start)
        start_frame = row.get("start_frame", row.get("timeline_start_frame"))
        end_frame = row.get("end_frame", row.get("timeline_end_frame"))
        if start_frame is None:
            start_frame = int(start * fps)
        if end_frame is None:
            end_frame = int(max(start, end) * fps)
        start_frame = _safe_int(start_frame)
        end_frame = max(start_frame, _safe_int(end_frame, start_frame))
        key = (source_key, start_frame, end_frame, text)
        if key in seen:
            return
        seen.add(key)
        item = {
            "index": len(tracks[source_key]) + 1,
            "source": source_key,
            "start": frame_to_sec(start_frame, fps),
            "end": frame_to_sec(end_frame, fps),
            "text": text,
            "speaker": str(row.get("speaker", row.get("spk", parent.get("speaker", "00"))) or "00"),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "timeline_start_frame": start_frame,
            "timeline_end_frame": end_frame,
            "frame_rate": fps,
            "timeline_frame_rate": fps,
            "frame_range": {
                "unit": "frame",
                "start": start_frame,
                "end": end_frame,
                "timeline_frame_rate": fps,
            },
        }
        for key_name in (
            "_clip_idx",
            "_clip_file",
            "score",
            "stt_score",
            "score_color",
            "stt_score_color",
            "stt_score_label",
            "stt_score_flags",
            "stt_score_components",
            "avg_logprob",
            "no_speech_prob",
            "compression_ratio",
            "words",
            "quality",
            "quality_history",
            "quality_candidates",
        ):
            if key_name in row:
                item[key_name] = row.get(key_name)
            elif key_name in parent:
                item[key_name] = parent.get(key_name)
        tracks[source_key].append(item)

    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        for candidate in list(seg.get("stt_candidates") or []):
            add_row(str(candidate.get("source", "")), candidate, seg)

    for seg in preview_segments or []:
        if not isinstance(seg, dict):
            continue
        add_row(str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1"), seg, seg)

    return {source: rows for source, rows in tracks.items() if rows}


def _normalize_stt_source(source: Any) -> str:
    text = str(source or "").upper().strip()
    if "STT2" in text or text in {"SECONDARY", "S2"}:
        return "STT2"
    if "STT1" in text or text in {"PRIMARY", "S1", ""}:
        return "STT1"
    return text


def segment_signature(segments: list[dict[str, Any]]) -> str:
    compact = []
    for seg in segments or []:
        if seg.get("is_gap"):
            continue
        compact.append(
            {
                "start": round(_safe_float(seg.get("start")), 3),
                "end": round(_safe_float(seg.get("end")), 3),
                "text": str(seg.get("text", "") or ""),
                "speaker": str(seg.get("speaker", "") or ""),
                "speaker_list": list(seg.get("speaker_list", []) or []),
            }
        )
    payload = json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_editor_segments(segments: list[dict[str, Any]], *, primary_fps: float = 30.0) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps or 30.0)
    out = []
    for idx, seg in enumerate(segments or []):
        if seg.get("is_gap"):
            continue
        start = _safe_float(seg.get("start", seg.get("timeline_start", 0.0)))
        end = _safe_float(seg.get("end", seg.get("timeline_end", start)), start)
        frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
        start_frame = seg.get("start_frame", seg.get("timeline_start_frame", frame_range.get("start")))
        end_frame = seg.get("end_frame", seg.get("timeline_end_frame", frame_range.get("end")))
        if start_frame is None:
            start_frame = sec_to_frame(start, fps)
        else:
            start = frame_to_sec(start_frame, fps)
        if end_frame is None:
            end_frame = sec_to_frame(max(start, end), fps)
        else:
            end = frame_to_sec(end_frame, fps)
        start_frame = _safe_int(start_frame)
        end_frame = max(start_frame, _safe_int(end_frame, start_frame))
        item = {
            "line": int(seg.get("line", idx) or idx),
            "start": frame_to_sec(start_frame, fps),
            "end": frame_to_sec(end_frame, fps),
            "text": str(seg.get("text", "") or ""),
            "speaker": str(seg.get("speaker", seg.get("spk", "00")) or "00"),
            "speaker_list": list(seg.get("speaker_list", []) or []),
            "stt_mode": bool(seg.get("stt_mode", False)),
            "stt_pending": bool(seg.get("stt_pending", False)),
            "original_text": str(seg.get("original_text", "") or ""),
            "dictated_text": str(seg.get("dictated_text", "") or ""),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "timeline_start_frame": start_frame,
            "timeline_end_frame": end_frame,
            "frame_rate": fps,
            "timeline_frame_rate": fps,
            "frame_range": {
                "unit": "frame",
                "start": start_frame,
                "end": end_frame,
                "timeline_frame_rate": fps,
            },
        }
        for key in (
            "_clip_idx",
            "_clip_file",
            "words",
            "quality",
            "quality_history",
            "quality_candidates",
            "quality_stale",
            "clip_local_start_frame",
            "clip_local_end_frame",
            "source_frame_rate",
        ):
            if key in seg:
                item[key] = seg.get(key)
        for key in STT_SEGMENT_METADATA_KEYS:
            if key in seg:
                item[key] = seg.get(key)
        item.update({key: value for key, value in subtitle_status_payload(item).items() if value not in (None, "")})
        out.append(item)
    return out


def _normalize_stt_preview_segments(
    segments: list[dict[str, Any]],
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps or 30.0)
    out = []
    for idx, seg in enumerate(segments or []):
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text", "") or "").strip()
        if not text:
            continue
        start = _safe_float(seg.get("start", seg.get("timeline_start", 0.0)))
        end = _safe_float(seg.get("end", seg.get("timeline_end", start)), start)
        frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
        start_frame = seg.get("start_frame", seg.get("timeline_start_frame", frame_range.get("start")))
        end_frame = seg.get("end_frame", seg.get("timeline_end_frame", frame_range.get("end")))
        if start_frame is not None:
            start = frame_to_sec(start_frame, fps)
        if end_frame is not None:
            end = frame_to_sec(end_frame, fps)
        item = {
            "index": int(seg.get("index", idx + 1) or idx + 1),
            "start": start,
            "end": max(start, end),
            "text": text,
            "speaker": str(seg.get("speaker", seg.get("spk", "00")) or "00"),
            "stt_preview_source": str(
                seg.get("stt_preview_source")
                or seg.get("stt_source")
                or seg.get("stt_ensemble_source")
                or "STT1"
            ),
            "stt_pending": True,
            "_live_stt_preview": True,
        }
        for key in ("_clip_idx", "_clip_file", "words", "quality", "quality_history", "quality_candidates"):
            if key in seg:
                item[key] = seg.get(key)
        for key in STT_SEGMENT_METADATA_KEYS:
            if key in seg and key not in item:
                item[key] = seg.get(key)
        item.update({key: value for key, value in subtitle_status_payload(item).items() if value not in (None, "")})
        if start_frame is None:
            start_frame = int(start * fps)
        if end_frame is None:
            end_frame = int(end * fps)
        item["start_frame"] = _safe_int(start_frame)
        item["end_frame"] = _safe_int(end_frame)
        item["timeline_start_frame"] = item["start_frame"]
        item["timeline_end_frame"] = item["end_frame"]
        item["frame_rate"] = fps
        item["timeline_frame_rate"] = fps
        item["frame_range"] = {
            "unit": "frame",
            "start": item["start_frame"],
            "end": item["end_frame"],
            "timeline_frame_rate": fps,
        }
        out.append(item)
    return out


def _normalize_boundary(item: dict[str, Any], idx: int) -> dict[str, Any]:
    path = str(item.get("file", item.get("source_path", "")) or "")
    start = _safe_float(item.get("start", item.get("timeline_start", 0.0)))
    end = _safe_float(item.get("end", item.get("timeline_end", start)), start)
    return {
        "start": start,
        "end": max(start, end),
        "file": path,
        "name": str(item.get("name") or os.path.basename(path) or f"clip_{idx + 1}"),
    }
