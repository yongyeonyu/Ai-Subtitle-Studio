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
from core.project.project_assets import (
    load_external_stt_tracks,
    load_external_subtitle_segments,
    project_uses_external_text_assets,
)

STT_SEGMENT_METADATA_KEYS = (
    "stt_candidates",
    "stt_lattice_candidates",
    "vad_candidates",
    "stt_retry_candidates",
    "stt_recheck_candidates",
    "stt_rescue_candidates",
    "manual_stt_candidates",
    "manual_recheck_candidates",
    "manual_rerecognition_candidates",
    "manual_re_recognition_candidates",
    "stt_manual_candidates",
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
    "stt_recheck_applied",
    "stt_recheck_original_scores",
    "stt_lattice_artifact_path",
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
    "subtitle_auto_review",
    "subtitle_auto_review_reasons",
    "subtitle_auto_review_severity",
    "subtitle_auto_review_score",
    "subtitle_auto_review_actions",
    "subtitle_auto_review_summary",
    "subtitle_stage_confidence",
    "subtitle_confidence_label",
    "subtitle_confidence_score",
    "subtitle_confidence_summary",
    "subtitle_completion_report",
    "_stt_lattice_policy",
    "_timing_fusion_policy",
    "_uncertainty_policy",
    "_uncertainty_bucket",
    "_uncertainty_risk_score",
    "_uncertainty_schedule_summary",
    "_llm_gate_policy",
    "_llm_minimize_policy",
    "_llm_candidate_policy",
    "_llm_verifier_policy",
    "_llm_rollback_policy",
    "_user_edit_metrics",
    "_one_click_fix_request",
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

EDITOR_STATE_SCHEMA = "ai_subtitle_studio.editor_state.v2"
SUBTITLE_CANVAS_VECTOR_SCHEMA = "subtitle_canvas.vector.v2"

VECTOR_SEGMENT_META_KEYS = (
    "quality",
    "quality_history",
    "quality_candidates",
    "quality_stale",
    "words",
    "original_text",
    "dictated_text",
    "clip_local_start_frame",
    "clip_local_end_frame",
    "source_frame_rate",
    *STT_SEGMENT_METADATA_KEYS,
)


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
    if (not isinstance(raw_segments, list) or not raw_segments) and project_uses_external_text_assets(project):
        raw_segments = []
        for source, rows in load_external_stt_tracks(project).items():
            for row in rows:
                item = dict(row)
                item["stt_preview_source"] = str(source)
                raw_segments.append(item)
    if not isinstance(raw_segments, list):
        return []
    timebase = (project.get("timeline", {}) or {}).get("timebase", {}) or project.get("frame_timebase", {}) or {}
    primary_fps = normalize_fps(timebase.get("primary_fps", 30.0) or 30.0)
    normalized = _normalize_stt_preview_segments(raw_segments, primary_fps=primary_fps)
    _attach_clip_context_from_boundaries(normalized, project_clip_boundaries(project))
    return normalized


def _attach_clip_context_from_boundaries(segments: list[dict[str, Any]], boundaries: list[dict[str, Any]]) -> None:
    if not segments or not boundaries:
        return
    for seg in segments:
        if not isinstance(seg, dict) or seg.get("_clip_idx") is not None:
            continue
        start = _safe_float(seg.get("start", 0.0))
        for idx, boundary in enumerate(boundaries):
            boundary_start = _safe_float(boundary.get("start"))
            boundary_end = _safe_float(boundary.get("end"))
            is_last = idx == len(boundaries) - 1
            if boundary_start <= start < boundary_end or (is_last and start <= boundary_end + 0.001):
                seg["_clip_idx"] = idx
                if boundary.get("file"):
                    seg["_clip_file"] = str(boundary.get("file") or "")
                break


def project_segments_to_editor(project: dict[str, Any]) -> list[dict[str, Any]]:
    editor_state = project.get("editor_state", {}) or {}
    editor_subtitles = editor_state.get("subtitles", {}) or {}
    vector_canvas = ((editor_state.get("rendering", {}) or {}).get("subtitle_canvas", {}) or {})
    raw_segments = _segments_from_subtitle_canvas_vector(vector_canvas)
    if (not raw_segments) and project_uses_external_text_assets(project):
        raw_segments = load_external_subtitle_segments(project)
    if not isinstance(raw_segments, list):
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
        segment_fps = normalize_fps(
            seg.get("timeline_frame_rate")
            or frame_range.get("timeline_frame_rate")
            or seg.get("frame_rate")
            or primary_fps
        )
        start_frame = seg.get("start_frame", seg.get("timeline_start_frame", frame_range.get("start")))
        end_frame = seg.get("end_frame", seg.get("timeline_end_frame", frame_range.get("end")))
        if start_frame is not None:
            start = frame_to_sec(start_frame, segment_fps)
        if end_frame is not None:
            end = frame_to_sec(end_frame, segment_fps)
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
        if seg.get("id"):
            item["id"] = str(seg.get("id") or "")
        if seg.get("index") is not None:
            item["index"] = _safe_int(seg.get("index"), idx + 1)
        if start_frame is not None:
            item["start_frame"] = _safe_int(start_frame)
            item["timeline_start_frame"] = _safe_int(start_frame)
        if end_frame is not None:
            item["end_frame"] = _safe_int(end_frame)
            item["timeline_end_frame"] = _safe_int(end_frame)
        item["frame_rate"] = segment_fps
        item["timeline_frame_rate"] = segment_fps
        item["frame_range"] = {
            "unit": "frame",
            "start": item.get("start_frame"),
            "end": item.get("end_frame"),
            "timeline_frame_rate": segment_fps,
        }
        if clip_idx is not None:
            item["_clip_idx"] = int(clip_idx)
        if clip_file:
            item["_clip_file"] = clip_file
        if "words" in seg:
            words = seg.get("words")
            item["words"] = list(words or []) if isinstance(words, list) else words
        for key in ("clip_local_start_frame", "clip_local_end_frame", "source_frame_rate"):
            if key in seg:
                item[key] = seg.get(key)
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
    if out and project_uses_external_text_assets(project):
        _attach_external_stt_candidates(out, load_external_stt_tracks(project))
        _attach_lattice_candidates_from_artifact(out, project)
    return out


def _candidate_lookup_key(row: dict[str, Any], primary_fps: float) -> tuple[int, int]:
    frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
    start_frame = row.get("start_frame", row.get("timeline_start_frame", frame_range.get("start")))
    end_frame = row.get("end_frame", row.get("timeline_end_frame", frame_range.get("end")))
    if start_frame is None:
        start_frame = sec_to_frame(_safe_float(row.get("start", row.get("timeline_start", 0.0))), primary_fps)
    if end_frame is None:
        end_frame = sec_to_frame(_safe_float(row.get("end", row.get("timeline_end", 0.0))), primary_fps)
    return _safe_int(start_frame), _safe_int(end_frame)


def _attach_external_stt_candidates(segments: list[dict[str, Any]], tracks: dict[str, list[dict[str, Any]]]) -> None:
    if not tracks:
        return
    primary_fps = normalize_fps(
        next(
            (
                seg.get("timeline_frame_rate") or seg.get("frame_rate")
                for seg in segments
                if isinstance(seg, dict) and (seg.get("timeline_frame_rate") or seg.get("frame_rate"))
            ),
            30.0,
        )
    )
    by_frame: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for source, rows in tracks.items():
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item["source"] = str(source)
            item["stt_preview_source"] = str(source)
            by_frame.setdefault(_candidate_lookup_key(item, primary_fps), []).append(item)
    for seg in segments:
        if not isinstance(seg, dict) or seg.get("stt_candidates"):
            continue
        candidates = by_frame.get(_candidate_lookup_key(seg, primary_fps), [])
        if candidates:
            seg["stt_candidates"] = [dict(candidate) for candidate in candidates]


def _attach_lattice_candidates_from_artifact(segments: list[dict[str, Any]], project: dict[str, Any]) -> None:
    analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
    artifact_path = str(
        analysis.get("stt_lattice_artifact_path")
        or ((project.get("editor_state", {}) or {}).get("analysis", {}) or {}).get("stt_lattice_artifact_path")
        or ""
    )
    if not artifact_path:
        return
    if not os.path.isabs(artifact_path):
        base = str(project.get("_project_file_path") or project.get("project_path") or "")
        if base:
            artifact_path = os.path.join(os.path.dirname(os.path.abspath(base)), artifact_path)
    if not artifact_path or not os.path.exists(artifact_path):
        return
    try:
        with open(artifact_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return
    rows = payload.get("segments") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return
    by_id: dict[str, dict[str, Any]] = {}
    by_time: dict[tuple[float, float], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        segment_id = str(row.get("segment_id", "") or "")
        if segment_id:
            by_id[segment_id] = row
        by_time[(round(_safe_float(row.get("start")), 3), round(_safe_float(row.get("end")), 3))] = row

    for seg in segments:
        if not isinstance(seg, dict):
            continue
        row = by_id.get(str(seg.get("id", "") or ""))
        if row is None:
            row = by_time.get((round(_safe_float(seg.get("start")), 3), round(_safe_float(seg.get("end")), 3)))
        if not isinstance(row, dict):
            continue
        for candidate in list(row.get("candidate_lattice") or []):
            if not isinstance(candidate, dict):
                continue
            key = str(candidate.get("candidate_key", "") or "")
            if key in {"", "current"}:
                continue
            if key == "stt_candidates" and seg.get("stt_candidates"):
                continue
            item = {
                "source": str(candidate.get("source", "") or ""),
                "text": str(candidate.get("text", "") or ""),
                "start": _safe_float(candidate.get("start", seg.get("start", 0.0))),
                "end": _safe_float(candidate.get("end", seg.get("end", seg.get("start", 0.0)))),
            }
            for meta_key in ("score", "confidence", "label", "candidate_role"):
                if candidate.get(meta_key) not in (None, ""):
                    item[meta_key] = candidate.get(meta_key)
            if item["text"]:
                seg.setdefault(key, []).append(item)


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
        "schema": EDITOR_STATE_SCHEMA,
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
            "storage": "vector_canvas",
            "segments": [],
            "segment_count": len(normalized_segments),
            "segment_signature": segment_signature(normalized_segments),
        },
        "rendering": {
            "subtitle_canvas": build_subtitle_canvas_vector_state(
                normalized_segments,
                primary_fps=fps,
            ),
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


def _vector_style_ref(seg: dict[str, Any]) -> str:
    if bool(seg.get("stt_pending")):
        return "subtitle.stt_pending"
    review_state = str(seg.get("subtitle_review_state", "") or "")
    if review_state:
        return f"subtitle.{review_state}"
    quality = seg.get("quality") if isinstance(seg.get("quality"), dict) else {}
    label = str(quality.get("confidence_label", "") or "")
    return f"subtitle.quality.{label}" if label else "subtitle.default"


def build_subtitle_canvas_vector_state(
    segments: list[dict[str, Any]],
    *,
    primary_fps: float = 30.0,
) -> dict[str, Any]:
    """Build a semantic vector layer for future GPU/scene-graph subtitle canvas rendering."""
    fps = normalize_fps(primary_fps or 30.0)
    objects: list[dict[str, Any]] = []
    for idx, seg in enumerate(segments or []):
        if not isinstance(seg, dict) or seg.get("is_gap"):
            continue
        start = _safe_float(seg.get("start", seg.get("timeline_start", 0.0)))
        end = _safe_float(seg.get("end", seg.get("timeline_end", start)), start)
        frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
        local_fps = normalize_fps(
            seg.get("timeline_frame_rate")
            or frame_range.get("timeline_frame_rate")
            or seg.get("frame_rate")
            or seg.get("source_frame_rate")
            or fps
        )
        start_frame = seg.get("start_frame", seg.get("timeline_start_frame", frame_range.get("start")))
        end_frame = seg.get("end_frame", seg.get("timeline_end_frame", frame_range.get("end")))
        if start_frame is None:
            start_frame = sec_to_frame(start, local_fps)
        if end_frame is None:
            end_frame = sec_to_frame(max(start, end), local_fps)
        start_frame = _safe_int(start_frame)
        end_frame = max(start_frame, _safe_int(end_frame, start_frame))
        clip: dict[str, Any] = {}
        if seg.get("_clip_idx") is not None:
            clip["index"] = int(seg.get("_clip_idx") or 0)
        if seg.get("_clip_file"):
            clip["file"] = str(seg.get("_clip_file") or "")
        obj = {
            "id": str(seg.get("id") or f"subtitle_vector_{idx + 1:04d}"),
            "kind": "subtitle_segment",
            "source_index": int(seg.get("index", idx + 1) or idx + 1),
            "line": int(seg.get("line", idx) or idx),
            "time": {
                "unit": "frame",
                "start_frame": start_frame,
                "end_frame": end_frame,
                "timeline_frame_rate": local_fps,
            },
            "text": str(seg.get("text", "") or ""),
            "speaker": str(seg.get("speaker", seg.get("spk", "00")) or "00"),
            "speaker_list": list(seg.get("speaker_list", []) or []),
            "style_ref": _vector_style_ref(seg),
            "flags": {
                "stt_pending": bool(seg.get("stt_pending", False)),
                "stt_mode": bool(seg.get("stt_mode", False)),
            },
        }
        if clip:
            obj["clip"] = clip
        status = {
            key: seg.get(key)
            for key in ("subtitle_review_state", "subtitle_status_color", "subtitle_status_score")
            if seg.get(key) not in (None, "")
        }
        if status:
            obj["status"] = status
        meta = {
            key: seg.get(key)
            for key in VECTOR_SEGMENT_META_KEYS
            if key in seg and seg.get(key) not in (None, "", [], {})
        }
        if meta:
            obj["meta"] = meta
        objects.append(obj)
    return {
        "schema": SUBTITLE_CANVAS_VECTOR_SCHEMA,
        "coordinate_space": {
            "x": "timeline_frame",
            "y": "lane_unit",
            "time_unit": "frame",
            "timeline_frame_rate": fps,
        },
        "renderer": {
            "preferred": "qt-scenegraph-gpu",
            "active_surface": "timeline-qopenglwidget",
            "fallback": "",
        },
        "segments": objects,
        "segment_signature": segment_signature(segments or []),
    }


def _segments_from_subtitle_canvas_vector(vector_canvas: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not isinstance(vector_canvas, dict):
        return None
    if str(vector_canvas.get("schema", "") or "") != SUBTITLE_CANVAS_VECTOR_SCHEMA:
        return None
    rows = vector_canvas.get("segments")
    if not isinstance(rows, list):
        return None
    fps = normalize_fps(
        ((vector_canvas.get("coordinate_space", {}) or {}).get("timeline_frame_rate"))
        or 30.0
    )
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        timing = row.get("time", {}) if isinstance(row.get("time"), dict) else {}
        local_fps = normalize_fps(timing.get("timeline_frame_rate") or fps)
        start_frame = timing.get("start_frame")
        end_frame = timing.get("end_frame")
        start = frame_to_sec(start_frame, local_fps) if start_frame is not None else _safe_float(timing.get("start_sec"))
        end = frame_to_sec(end_frame, local_fps) if end_frame is not None else _safe_float(timing.get("end_sec"), start)
        item = {
            "line": int(row.get("line", idx) or idx),
            "start": start,
            "end": max(start, end),
            "text": str(row.get("text", "") or ""),
            "speaker": str(row.get("speaker", "00") or "00"),
            "speaker_list": list(row.get("speaker_list", []) or []),
        }
        if row.get("id"):
            item["id"] = str(row.get("id") or "")
        if row.get("source_index") is not None:
            item["index"] = _safe_int(row.get("source_index"), idx + 1)
        if start_frame is not None:
            item["start_frame"] = _safe_int(start_frame)
            item["timeline_start_frame"] = item["start_frame"]
        if end_frame is not None:
            item["end_frame"] = _safe_int(end_frame)
            item["timeline_end_frame"] = item["end_frame"]
        item["frame_rate"] = local_fps
        item["timeline_frame_rate"] = local_fps
        item["frame_range"] = {
            "unit": "frame",
            "start": item.get("start_frame"),
            "end": item.get("end_frame"),
            "timeline_frame_rate": local_fps,
        }
        flags = row.get("flags", {}) if isinstance(row.get("flags"), dict) else {}
        item["stt_pending"] = bool(flags.get("stt_pending", False))
        item["stt_mode"] = bool(flags.get("stt_mode", False))
        clip = row.get("clip", {}) if isinstance(row.get("clip"), dict) else {}
        if clip.get("index") is not None:
            item["_clip_idx"] = int(clip.get("index") or 0)
        if clip.get("file"):
            item["_clip_file"] = str(clip.get("file") or "")
        status = row.get("status", {}) if isinstance(row.get("status"), dict) else {}
        for key in ("subtitle_review_state", "subtitle_status_color", "subtitle_status_score"):
            if key in status:
                item[key] = status.get(key)
        meta = row.get("meta", {}) if isinstance(row.get("meta"), dict) else {}
        for key in VECTOR_SEGMENT_META_KEYS:
            if key in meta:
                item[key] = meta.get(key)
        out.append(item)
    return out


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
