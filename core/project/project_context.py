# Version: 03.09.29
# Phase: PHASE2
"""
core/project/project_context.py
Project JSON adapter for editor / roughcut state separation.
"""
from __future__ import annotations

from bisect import bisect_right
import hashlib
import json
import os
from typing import Any

from core.coerce import safe_float as _safe_float, safe_int as _safe_int
from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame, sec_to_nearest_frame
from core.work_mode import EDITOR_MODE, normalize_work_mode
from core.project.subtitle_status import recheck_threshold, subtitle_status_payload
from core.cut_boundary import (
    CUT_BOUNDARY_PROVISIONAL_SCHEMA,
    CUT_BOUNDARY_SCHEMA,
    normalize_cut_boundaries,
    project_cut_provisional_boundaries,
)
from core.project.project_assets import (
    copy_project_rows,
    load_external_stt_tracks,
    load_external_subtitle_segments,
    project_uses_external_text_assets,
    sanitize_stt_track_rows,
    stt_candidate_track_counts,
)
from core.project.project_analysis_store import normalize_project_voice_activity_segment
from core.project.project_format import project_primary_fps, project_total_duration
from core.native_json import dumps_json_bytes

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
    "stt_preview_sublane",
    "stt_preview_sublane_count",
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
    "_stt_original_candidate_start",
    "_stt_original_candidate_end",
    "_stt_original_candidate_start_frame",
    "_stt_original_candidate_end_frame",
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

SUBTITLE_STATUS_PAYLOAD_KEYS = (
    "subtitle_review_state",
    "subtitle_status_color",
    "subtitle_status_schema",
    "subtitle_status_score",
    "subtitle_status_source",
)


def sanitize_workspace_state(workspace: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(workspace, dict):
        return {}
    return {
        str(key): value
        for key, value in workspace.items()
        if str(key) not in NON_PERSISTED_WORKSPACE_KEYS
    }

def _project_segment_status_payload(seg: dict[str, Any], *, threshold: float | None = None) -> dict[str, Any]:
    if isinstance(seg, dict) and all(key in seg for key in SUBTITLE_STATUS_PAYLOAD_KEYS):
        state = str(seg.get("subtitle_review_state", "") or "").strip()
        schema = str(seg.get("subtitle_status_schema", "") or "").strip()
        if state and schema:
            return {
                key: seg.get(key)
                for key in SUBTITLE_STATUS_PAYLOAD_KEYS
                if seg.get(key) not in (None, "")
            }
    return {
        key: value
        for key, value in subtitle_status_payload(seg, threshold=threshold).items()
        if value not in (None, "")
    }


def _restore_original_candidate_timing(
    item: dict[str, Any],
    source: dict[str, Any],
    *,
    default_fps: float,
) -> None:
    raw_start_frame = item.get("_stt_original_candidate_start_frame")
    raw_end_frame = item.get("_stt_original_candidate_end_frame")
    has_raw_candidate_timing = (
        raw_start_frame is not None
        or raw_end_frame is not None
        or "_stt_original_candidate_start" in source
        or "_stt_original_candidate_end" in source
        or "original_start" in source
        or "original_end" in source
    )
    if not has_raw_candidate_timing:
        return
    raw_frame_rate = normalize_fps(
        source.get("timeline_frame_rate")
        or source.get("frame_rate")
        or default_fps
    )
    raw_start = _safe_float(
        source.get(
            "_stt_original_candidate_start",
            source.get("original_start", item.get("start", 0.0)),
        )
    )
    raw_end = _safe_float(
        source.get(
            "_stt_original_candidate_end",
            source.get("original_end", item.get("end", raw_start)),
        ),
        raw_start,
    )
    if raw_start_frame is None:
        raw_start_frame = sec_to_nearest_frame(raw_start, raw_frame_rate)
    if raw_end_frame is None:
        raw_end_frame = sec_to_nearest_frame(raw_end, raw_frame_rate)
    raw_start_frame = _safe_int(raw_start_frame)
    raw_end_frame = max(raw_start_frame, _safe_int(raw_end_frame, raw_start_frame))
    item["_stt_original_candidate_start_frame"] = raw_start_frame
    item["_stt_original_candidate_end_frame"] = raw_end_frame
    item["_stt_original_candidate_start"] = frame_to_sec(raw_start_frame, raw_frame_rate)
    item["_stt_original_candidate_end"] = frame_to_sec(raw_end_frame, raw_frame_rate)


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
    primary_fps = project_primary_fps(project)
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
        seg = normalize_project_voice_activity_segment(
            item,
            idx,
            start=start,
            end=end,
            include_id=False,
        )
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
    primary_fps = project_primary_fps(project)
    analysis = project.get("analysis", {}) or {}
    raw = analysis.get("cut_boundaries")
    if not isinstance(raw, list):
        raw = ((project.get("editor_state", {}) or {}).get("multiclip", {}) or {}).get("cut_boundaries")
    if not isinstance(raw, list):
        return []
    return normalize_cut_boundaries(raw, primary_fps=primary_fps)


def project_cut_boundary_provisional_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    primary_fps = project_primary_fps(project)
    return project_cut_provisional_boundaries(project, primary_fps=primary_fps)


def project_stt_preview_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    editor_state = project.get("editor_state", {}) or {}
    stt_state = editor_state.get("stt", {}) or {}
    primary_fps = project_primary_fps(project)
    external_text_assets = project_uses_external_text_assets(project)
    raw_segments = _project_stt_preview_raw_segments(project, editor_state, stt_state)
    normalized: list[dict[str, Any]] | None = None
    if raw_segments is None:
        normalized = _normalize_stt_preview_segments_from_tracks(
            _project_stt_preview_track_source(
                project,
                editor_state,
                stt_state,
                external_text_assets=external_text_assets,
            ),
            primary_fps=primary_fps,
        )
    if normalized is None:
        normalized = _normalize_stt_preview_segments(raw_segments, primary_fps=primary_fps)
    if not normalized:
        normalized = _normalize_stt_preview_segments(
            _project_stt_preview_segments_from_lattice_artifact(project),
            primary_fps=primary_fps,
        )
    if not normalized:
        return []
    normalized = _trim_segments_to_project_duration(normalized, project, primary_fps=primary_fps)
    if not normalized:
        return []
    _attach_clip_context_from_boundaries(normalized, project_clip_boundaries(project))
    return normalized


def _project_total_duration(project: dict[str, Any]) -> float:
    total = project_total_duration(project)
    if total > 0.0:
        return total
    boundaries = project_clip_boundaries(project)
    return max((_safe_float(boundary.get("end"), 0.0) for boundary in boundaries if isinstance(boundary, dict)), default=0.0)


def _trim_segments_to_project_duration(
    rows: list[dict[str, Any]],
    project: dict[str, Any],
    *,
    primary_fps: float,
) -> list[dict[str, Any]]:
    total_duration = _project_total_duration(project)
    if total_duration <= 0.0 or not rows:
        return list(rows or [])
    tolerance = max(0.1, 2.0 / max(1.0, float(primary_fps or 30.0)))
    out: list[dict[str, Any]] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        item = dict(row)
        start = _safe_float(item.get("start", item.get("timeline_start", 0.0)), 0.0)
        end = _safe_float(item.get("end", item.get("timeline_end", start)), start)
        if start > total_duration + tolerance:
            continue
        if end > total_duration + tolerance:
            fps = normalize_fps(item.get("timeline_frame_rate") or item.get("frame_rate") or primary_fps or 30.0)
            clamped_end = max(start, total_duration)
            item["end"] = clamped_end
            item["timeline_end"] = clamped_end
            if item.get("end_frame") is not None or item.get("timeline_end_frame") is not None:
                end_frame = sec_to_frame(clamped_end, fps)
                item["end_frame"] = end_frame
                item["timeline_end_frame"] = end_frame
                frame_range = dict(item.get("frame_range") or {})
                frame_range["end"] = end_frame
                frame_range["timeline_frame_rate"] = fps
                item["frame_range"] = frame_range
        out.append(item)
    return out


def _attach_clip_context_from_boundaries(segments: list[dict[str, Any]], boundaries: list[dict[str, Any]]) -> None:
    if not segments or not boundaries:
        return
    indexed = [
        (
            _safe_float(boundary.get("start")),
            _safe_float(boundary.get("end")),
            idx,
            boundary,
        )
        for idx, boundary in enumerate(boundaries)
    ]
    indexed.sort(key=lambda item: (item[0], item[1], item[2]))
    starts = [item[0] for item in indexed]
    for seg in segments:
        if not isinstance(seg, dict) or seg.get("_clip_idx") is not None:
            continue
        start = _safe_float(seg.get("start", 0.0))
        candidate = bisect_right(starts, start) - 1
        for probe in (candidate, candidate - 1, candidate + 1):
            if probe < 0 or probe >= len(indexed):
                continue
            boundary_start, boundary_end, idx, boundary = indexed[probe]
            is_last = idx == len(boundaries) - 1
            if boundary_start <= start < boundary_end or (is_last and start <= boundary_end + 0.001):
                seg["_clip_idx"] = int(idx)
                if boundary.get("file"):
                    seg["_clip_file"] = str(boundary.get("file") or "")
                break


def _project_stt_preview_raw_segments(
    project: dict[str, Any],
    editor_state: dict[str, Any],
    stt_state: dict[str, Any],
) -> list[dict[str, Any]] | None:
    raw_segments = stt_state.get("preview_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raw_segments = project.get("_hot_open_stt_preview_segments_cache")
    if not isinstance(raw_segments, list) or not raw_segments:
        raw_segments = editor_state.get("stt_preview_segments")
    return raw_segments if isinstance(raw_segments, list) and raw_segments else None


def _project_stt_preview_track_source(
    project: dict[str, Any],
    editor_state: dict[str, Any],
    stt_state: dict[str, Any],
    *,
    external_text_assets: bool,
) -> dict[str, list[dict[str, Any]]] | None:
    tracks = stt_state.get("candidate_tracks")
    if isinstance(tracks, dict) and tracks:
        return tracks
    if external_text_assets:
        return load_external_stt_tracks(project)
    tracks = (editor_state.get("analysis", {}) or {}).get("stt_candidate_tracks")
    if not isinstance(tracks, dict):
        tracks = (project.get("analysis", {}) or {}).get("stt_candidate_tracks")
    return tracks if isinstance(tracks, dict) else None


def _project_stt_lattice_artifact_path(project: dict[str, Any]) -> str:
    analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
    artifact_path = str(
        analysis.get("stt_lattice_artifact_path")
        or ((project.get("editor_state", {}) or {}).get("analysis", {}) or {}).get("stt_lattice_artifact_path")
        or ""
    )
    if not artifact_path:
        return ""
    if not os.path.isabs(artifact_path):
        base = str(project.get("_project_file_path") or project.get("project_path") or "")
        if base:
            artifact_path = os.path.join(os.path.dirname(os.path.abspath(base)), artifact_path)
    return artifact_path


def _load_project_stt_lattice_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    artifact_path = _project_stt_lattice_artifact_path(project)
    if not artifact_path or not os.path.exists(artifact_path):
        return []
    try:
        with open(artifact_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return []
    rows = payload.get("segments") if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _project_stt_preview_segments_from_lattice_artifact(project: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _load_project_stt_lattice_segments(project)
    if not rows:
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()
    for row in rows:
        candidates = row.get("candidate_lattice")
        if not isinstance(candidates, list):
            candidates = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            source = _normalize_stt_source(
                candidate.get("source")
                or candidate.get("stt_preview_source")
                or row.get("source")
                or row.get("stt_preview_source")
            )
            if source not in {"STT1", "STT2"}:
                continue
            text = str(candidate.get("text", row.get("text", "")) or "").strip()
            if not text:
                continue
            start = _safe_float(candidate.get("start", row.get("start", 0.0)), 0.0)
            end = _safe_float(candidate.get("end", row.get("end", start)), start)
            key = (source, round(start * 1000), round(end * 1000), text)
            if key in seen:
                continue
            seen.add(key)
            raw_source = str(candidate.get("source") or row.get("source") or source)
            item = {
                "index": len(out) + 1,
                "start": start,
                "end": max(start, end),
                "text": text,
                "speaker": str(candidate.get("speaker", row.get("speaker", row.get("spk", "00"))) or "00"),
                "stt_preview_source": source,
                "stt_source": source,
                "stt_ensemble_source": raw_source,
                "stt_pending": True,
                "_live_stt_preview": True,
            }
            if candidate.get("score") not in (None, ""):
                item["score"] = candidate.get("score")
                item["stt_score"] = candidate.get("score")
            for key_name in (
                "confidence",
                "words",
                "quality",
                "quality_history",
                "quality_candidates",
                "_clip_idx",
                "_clip_file",
            ):
                if key_name in candidate:
                    item[key_name] = candidate.get(key_name)
                elif key_name in row:
                    item[key_name] = row.get(key_name)
            out.append(item)
    out.sort(key=lambda item: (_safe_float(item.get("start")), 0 if item.get("stt_preview_source") == "STT1" else 1))
    for idx, item in enumerate(out, start=1):
        item["index"] = idx
    return out


def _project_raw_subtitle_segments(
    project: dict[str, Any],
    editor_subtitles: dict[str, Any],
    vector_canvas: dict[str, Any],
    *,
    external_text_assets: bool,
) -> list[dict[str, Any]]:
    raw_segments = _segments_from_subtitle_canvas_vector(vector_canvas)
    gap_segments = [dict(seg) for seg in raw_segments if isinstance(seg, dict) and bool(seg.get("is_gap"))] if raw_segments else []
    if external_text_assets:
        merged_segments = _merge_gap_segments_into_project_rows(
            load_external_subtitle_segments(project),
            gap_segments,
        )
        if merged_segments:
            return merged_segments
        if isinstance(project.get("_hot_open_subtitle_segments_cache"), list):
            merged_segments = _merge_gap_segments_into_project_rows(
                copy_project_rows(project.get("_hot_open_subtitle_segments_cache")),
                gap_segments,
            )
            if merged_segments:
                return merged_segments
        return []
    if (not raw_segments) and isinstance(project.get("_hot_open_subtitle_segments_cache"), list):
        raw_segments = _merge_gap_segments_into_project_rows(
            copy_project_rows(project.get("_hot_open_subtitle_segments_cache")),
            gap_segments,
        )
    if not isinstance(raw_segments, list):
        raw_segments = editor_subtitles.get("segments")
    if not isinstance(raw_segments, list):
        raw_segments = project.get("segments")
    if not isinstance(raw_segments, list):
        raw_segments = (project.get("subtitles", {}) or {}).get("segments", [])
    return raw_segments if isinstance(raw_segments, list) else []


def project_segments_to_editor(
    project: dict[str, Any],
    *,
    include_analysis_candidates: bool = True,
) -> list[dict[str, Any]]:
    editor_state = project.get("editor_state", {}) or {}
    editor_subtitles = editor_state.get("subtitles", {}) or {}
    vector_canvas = ((editor_state.get("rendering", {}) or {}).get("subtitle_canvas", {}) or {})
    external_text_assets = project_uses_external_text_assets(project)
    raw_segments = _project_raw_subtitle_segments(
        project,
        editor_subtitles,
        vector_canvas,
        external_text_assets=external_text_assets,
    )
    if not raw_segments:
        return []

    boundaries = project_clip_boundaries(project)
    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", []) or []
    ordered_clips = [
        clip for clip in sorted(clips, key=lambda item: item.get("order", 0)) if isinstance(clip, dict)
    ]
    clip_by_id = {str(clip.get("id", "")): clip for clip in clips if clip.get("id")}
    clip_by_path = {
        str(clip.get("source_path", "") or ""): clip
        for clip in ordered_clips
        if clip.get("source_path")
    }
    boundary_rows = [
        (
            _safe_float(boundary.get("start")),
            _safe_float(boundary.get("end")),
            b_idx,
            boundary,
        )
        for b_idx, boundary in enumerate(boundaries)
    ]
    boundary_rows.sort(key=lambda item: (item[0], item[1], item[2]))
    boundary_starts = [item[0] for item in boundary_rows]
    boundary_by_file = {
        str(boundary.get("file") or ""): (b_idx, boundary)
        for b_idx, boundary in enumerate(boundaries)
        if boundary.get("file")
    }
    primary_fps = project_primary_fps(project)
    status_threshold = recheck_threshold() if raw_segments else None

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
            resolved = boundary_by_file.get(clip_file)
            if resolved is not None:
                clip_idx, _boundary = resolved
        if clip_idx is None and boundary_rows:
            candidate = bisect_right(boundary_starts, start) - 1
            for probe in (candidate, candidate - 1, candidate + 1):
                if probe < 0 or probe >= len(boundary_rows):
                    continue
                boundary_start, boundary_end, b_idx, boundary = boundary_rows[probe]
                is_last = b_idx == len(boundaries) - 1
                if boundary_start <= start < boundary_end or (is_last and start <= boundary_end + 0.001):
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
        if bool(seg.get("is_gap")):
            item["is_gap"] = True
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
        clip = None
        if clip_id in clip_by_id:
            clip = clip_by_id[clip_id]
        elif clip_file:
            clip = clip_by_path.get(clip_file)
        elif clip_idx is not None and 0 <= int(clip_idx) < len(ordered_clips):
            clip = ordered_clips[int(clip_idx)]

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
        if clip is not None:
            source_fps = normalize_fps(clip.get("fps") or clip.get("source_frame_rate") or segment_fps)
            item.setdefault("source_frame_rate", source_fps)
            clip_offset = _safe_float(clip.get("timeline_start"), 0.0)
            clip_local_start = max(0.0, start - clip_offset)
            clip_local_end = max(clip_local_start, end - clip_offset)
            item.setdefault("clip_local_start_frame", sec_to_frame(clip_local_start, source_fps))
            item.setdefault("clip_local_end_frame", sec_to_frame(clip_local_end, source_fps))
            frame_range = dict(item.get("frame_range") or {})
            frame_range.setdefault("source_frame_rate", source_fps)
            frame_range.setdefault("clip_local_start", item.get("clip_local_start_frame"))
            frame_range.setdefault("clip_local_end", item.get("clip_local_end_frame"))
            item["frame_range"] = frame_range
        for key in ("quality", "quality_history", "quality_candidates", "quality_stale"):
            if key in seg:
                value = seg.get(key)
                if isinstance(value, (dict, list, bool)):
                    item[key] = value
        for key in STT_SEGMENT_METADATA_KEYS:
            if key in seg:
                item[key] = seg.get(key)
        _restore_original_candidate_timing(item, seg, default_fps=segment_fps)
        if not bool(item.get("is_gap")):
            item.update(_project_segment_status_payload(item, threshold=status_threshold))
        out.append(item)
    out = _trim_segments_to_project_duration(out, project, primary_fps=primary_fps)
    if out and include_analysis_candidates and external_text_assets:
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


def _candidate_rows_with_source_copy(rows: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for source, row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        source_text = str(source or row.get("source") or row.get("stt_preview_source") or "")
        item["source"] = source_text
        item["stt_preview_source"] = source_text
        out.append(item)
    return out


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
    by_frame: dict[tuple[int, int], list[tuple[str, dict[str, Any]]]] = {}
    for source, rows in tracks.items():
        source_text = str(source or "")
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            by_frame.setdefault(_candidate_lookup_key(row, primary_fps), []).append((source_text, row))
    for seg in segments:
        if not isinstance(seg, dict) or seg.get("stt_candidates"):
            continue
        candidates = by_frame.get(_candidate_lookup_key(seg, primary_fps), [])
        if candidates:
            seg["stt_candidates"] = _candidate_rows_with_source_copy(candidates)


def _attach_lattice_candidates_from_artifact(segments: list[dict[str, Any]], project: dict[str, Any]) -> None:
    rows = _load_project_stt_lattice_segments(project)
    if not rows:
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
    normalized_media_files = [os.path.abspath(path) for path in media_files if path]
    normalized_segments = _normalize_editor_segments(segments, primary_fps=fps)
    normalized_gap_segments = _normalize_gap_segments(segments, primary_fps=fps)
    segment_signature_value = segment_signature(normalized_segments)
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
        "media_files": normalized_media_files,
        "single_clip": {
            "source_path": normalized_media_files[0] if normalized_media_files and mode == "single" else "",
        },
        "multiclip": {
            "files": normalized_media_files if mode == "multiclip" else [],
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
            "segment_signature": segment_signature_value,
        },
        "rendering": {
            "subtitle_canvas": build_subtitle_canvas_vector_state(
                normalized_segments,
                gap_segments=normalized_gap_segments,
                primary_fps=fps,
                segment_signature_value=segment_signature_value,
            ),
        },
        "stt": {
            "schema": "stt_candidates.v1",
            "preview_segments": stt_preview,
            "candidate_tracks": stt_candidate_tracks,
            "candidate_counts": stt_candidate_track_counts(stt_candidate_tracks),
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
        raw_frame_rate = normalize_fps(
            row.get("timeline_frame_rate")
            or row.get("frame_rate")
            or parent.get("timeline_frame_rate")
            or parent.get("frame_rate")
            or fps
        )
        raw_start_frame = row.get(
            "_stt_original_candidate_start_frame",
            parent.get("_stt_original_candidate_start_frame"),
        )
        raw_end_frame = row.get(
            "_stt_original_candidate_end_frame",
            parent.get("_stt_original_candidate_end_frame"),
        )
        raw_start = _safe_float(
            row.get(
                "_stt_original_candidate_start",
                row.get("original_start", parent.get("_stt_original_candidate_start", parent.get("original_start", start))),
            ),
            start,
        )
        raw_end = _safe_float(
            row.get(
                "_stt_original_candidate_end",
                row.get("original_end", parent.get("_stt_original_candidate_end", parent.get("original_end", end))),
            ),
            raw_start,
        )
        if raw_start_frame is None:
            raw_start_frame = sec_to_nearest_frame(raw_start, raw_frame_rate)
        if raw_end_frame is None:
            raw_end_frame = sec_to_nearest_frame(raw_end, raw_frame_rate)
        raw_start_frame = _safe_int(raw_start_frame)
        raw_end_frame = max(raw_start_frame + 1, _safe_int(raw_end_frame, raw_start_frame))
        raw_start = frame_to_sec(raw_start_frame, raw_frame_rate)
        raw_end = frame_to_sec(raw_end_frame, raw_frame_rate)
        start_frame = row.get("start_frame", row.get("timeline_start_frame"))
        end_frame = row.get("end_frame", row.get("timeline_end_frame"))
        if start_frame is None:
            start_frame = sec_to_nearest_frame(start, fps)
        if end_frame is None:
            end_frame = sec_to_nearest_frame(max(start, end), fps)
        start_frame = _safe_int(start_frame)
        end_frame = max(start_frame + 1, _safe_int(end_frame, start_frame))
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
            "_stt_original_candidate_start": raw_start,
            "_stt_original_candidate_end": max(raw_start, raw_end),
            "_stt_original_candidate_start_frame": raw_start_frame,
            "_stt_original_candidate_end_frame": raw_end_frame,
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
            "stt_preview_sublane",
            "stt_preview_sublane_count",
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

    return {
        source: sanitize_stt_track_rows(rows, source=source, primary_fps=fps)
        for source, rows in tracks.items()
        if rows
    }


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
    payload = dumps_json_bytes(compact, sort_keys=True, compact=True)
    return hashlib.sha256(payload).hexdigest()


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
    gap_segments: list[dict[str, Any]] | None = None,
    primary_fps: float = 30.0,
    segment_signature_value: str | None = None,
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
    gap_objects: list[dict[str, Any]] = []
    for idx, seg in enumerate(gap_segments or []):
        if not isinstance(seg, dict):
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
            "id": str(seg.get("id") or f"subtitle_gap_vector_{idx + 1:04d}"),
            "kind": "subtitle_gap",
            "source_index": int(seg.get("index", idx + 1) or idx + 1),
            "line": int(seg.get("line", idx) or idx),
            "time": {
                "unit": "frame",
                "start_frame": start_frame,
                "end_frame": end_frame,
                "timeline_frame_rate": local_fps,
            },
            "flags": {
                "is_gap": True,
            },
        }
        if clip:
            obj["clip"] = clip
        gap_objects.append(obj)
    return {
        "schema": SUBTITLE_CANVAS_VECTOR_SCHEMA,
        "coordinate_space": {
            "x": "timeline_frame",
            "y": "lane_unit",
            "time_unit": "frame",
            "timeline_frame_rate": fps,
        },
        "renderer": {
            "preferred": "qt-widgets-qpaint",
            "active_surface": "timeline-qwidget-2d",
            "fallback": "qt-scenegraph-explicit-opt-in",
        },
        "segments": objects,
        "gap_segments": gap_objects,
        "segment_signature": (
            str(segment_signature_value)
            if segment_signature_value is not None
            else segment_signature(segments or [])
        ),
    }


def _segments_from_subtitle_canvas_vector(vector_canvas: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not isinstance(vector_canvas, dict):
        return None
    if str(vector_canvas.get("schema", "") or "") != SUBTITLE_CANVAS_VECTOR_SCHEMA:
        return None
    rows = vector_canvas.get("segments")
    gap_rows = vector_canvas.get("gap_segments")
    if not isinstance(rows, list) and not isinstance(gap_rows, list):
        return None
    fps = normalize_fps(
        ((vector_canvas.get("coordinate_space", {}) or {}).get("timeline_frame_rate"))
        or 30.0
    )
    out: list[dict[str, Any]] = []
    def append_row(row: dict[str, Any], idx: int, *, is_gap: bool) -> None:
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
            "text": "" if is_gap else str(row.get("text", "") or ""),
            "speaker": str(row.get("speaker", "00") or "00"),
            "speaker_list": list(row.get("speaker_list", []) or []),
        }
        if is_gap:
            item["is_gap"] = True
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
    for idx, row in enumerate(rows or []):
        if isinstance(row, dict):
            append_row(row, idx, is_gap=False)
    for idx, row in enumerate(gap_rows or []):
        if isinstance(row, dict):
            append_row(row, idx, is_gap=True)
    out.sort(key=_project_segment_sort_key)
    for idx, seg in enumerate(out):
        seg["line"] = idx
    return out


def _normalize_editor_segments(segments: list[dict[str, Any]], *, primary_fps: float = 30.0) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps or 30.0)
    status_threshold = recheck_threshold() if segments else None
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
        _restore_original_candidate_timing(item, seg, default_fps=fps)
        item.update(_project_segment_status_payload(item, threshold=status_threshold))
        out.append(item)
    return out


def _normalize_gap_segments(segments: list[dict[str, Any]], *, primary_fps: float = 30.0) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps or 30.0)
    out: list[dict[str, Any]] = []
    for idx, seg in enumerate(segments or []):
        if not isinstance(seg, dict) or not bool(seg.get("is_gap")):
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
            "text": "",
            "speaker": str(seg.get("speaker", seg.get("spk", "00")) or "00"),
            "speaker_list": list(seg.get("speaker_list", []) or []),
            "is_gap": True,
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
            "id",
            "index",
            "_clip_idx",
            "_clip_file",
            "clip_local_start_frame",
            "clip_local_end_frame",
            "source_frame_rate",
        ):
            if key in seg:
                item[key] = seg.get(key)
        out.append(item)
    return out


def _project_segment_sort_key(seg: dict[str, Any]) -> tuple[float, float, int, int, int]:
    start = _safe_float(seg.get("start", seg.get("timeline_start", 0.0)))
    end = _safe_float(seg.get("end", seg.get("timeline_end", start)), start)
    line = _safe_int(seg.get("line"), 0)
    index = _safe_int(seg.get("index"), 0)
    return (start, end, int(bool(seg.get("is_gap"))), line, index)


def _merge_gap_segments_into_project_rows(
    subtitle_rows: list[dict[str, Any]] | None,
    gap_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    rows = [dict(seg) for seg in (subtitle_rows or []) if isinstance(seg, dict)]
    rows.extend(dict(seg) for seg in (gap_rows or []) if isinstance(seg, dict))
    if not rows:
        return []
    rows.sort(key=_project_segment_sort_key)
    for idx, seg in enumerate(rows):
        seg["line"] = idx
    return rows


def _normalize_stt_preview_segments(
    segments: list[dict[str, Any]],
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps or 30.0)
    status_threshold = recheck_threshold() if segments else None
    out: list[dict[str, Any]] = []
    _append_normalized_stt_preview_segments(
        out,
        segments,
        fps=fps,
        status_threshold=status_threshold,
    )
    return out


def _append_normalized_stt_preview_segments(
    out: list[dict[str, Any]],
    segments: list[dict[str, Any]] | None,
    *,
    fps: float,
    status_threshold: float | None,
    source_override: str | None = None,
) -> None:
    for idx, seg in enumerate(segments or []):
        item = _normalized_stt_preview_segment(
            seg,
            index=idx + 1,
            fps=fps,
            status_threshold=status_threshold,
            source_override=source_override,
        )
        if item is not None:
            out.append(item)


def _normalize_stt_preview_segments_from_tracks(
    tracks: dict[str, list[dict[str, Any]]] | None,
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    if not isinstance(tracks, dict) or not tracks:
        return []
    fps = normalize_fps(primary_fps or 30.0)
    status_threshold = recheck_threshold()
    out: list[dict[str, Any]] = []
    for source, rows in tracks.items():
        if not isinstance(rows, list) or not rows:
            continue
        _append_normalized_stt_preview_segments(
            out,
            rows,
            fps=fps,
            status_threshold=status_threshold,
            source_override=str(source),
        )
    return out


def _normalized_stt_preview_segment(
    seg: dict[str, Any],
    *,
    index: int,
    fps: float,
    status_threshold: float | None,
    source_override: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(seg, dict):
        return None
    text = str(seg.get("text", "") or "").strip()
    if not text:
        return None
    source = str(
        source_override
        or seg.get("stt_preview_source")
        or seg.get("stt_source")
        or seg.get("stt_ensemble_source")
        or "STT1"
    )
    preserve_raw_candidate_timing = source.strip().upper() in {"STT1", "STT2"}
    raw_frame_rate = normalize_fps(
        seg.get("timeline_frame_rate")
        or seg.get("frame_rate")
        or fps
    )
    raw_start_frame = seg.get("_stt_original_candidate_start_frame")
    raw_end_frame = seg.get("_stt_original_candidate_end_frame")
    raw_start = _safe_float(
        seg.get(
            "_stt_original_candidate_start",
            seg.get("original_start", seg.get("start", seg.get("timeline_start", 0.0))),
        )
    )
    raw_end = _safe_float(
        seg.get(
            "_stt_original_candidate_end",
            seg.get("original_end", seg.get("end", seg.get("timeline_end", raw_start))),
        ),
        raw_start,
    )
    if raw_start_frame is None:
        raw_start_frame = sec_to_nearest_frame(raw_start, raw_frame_rate)
    if raw_end_frame is None:
        raw_end_frame = sec_to_nearest_frame(raw_end, raw_frame_rate)
    raw_start_frame = _safe_int(raw_start_frame)
    raw_end_frame = max(raw_start_frame + 1, _safe_int(raw_end_frame, raw_start_frame))
    raw_start = frame_to_sec(raw_start_frame, raw_frame_rate)
    raw_end = frame_to_sec(raw_end_frame, raw_frame_rate)
    start = raw_start
    end = raw_end
    frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
    start_frame = seg.get("start_frame", seg.get("timeline_start_frame", frame_range.get("start")))
    end_frame = seg.get("end_frame", seg.get("timeline_end_frame", frame_range.get("end")))
    if preserve_raw_candidate_timing and start_frame is None:
        start_frame = raw_start_frame
    if preserve_raw_candidate_timing and end_frame is None:
        end_frame = raw_end_frame
    if start_frame is not None and not preserve_raw_candidate_timing:
        start = frame_to_sec(start_frame, fps)
    if end_frame is not None and not preserve_raw_candidate_timing:
        end = frame_to_sec(end_frame, fps)
    item = {
        "index": int(seg.get("index", index) or index),
        "start": start,
        "end": max(start, end),
        "text": text,
        "speaker": str(seg.get("speaker", seg.get("spk", "00")) or "00"),
        "stt_preview_source": source,
        "stt_pending": True,
        "_live_stt_preview": True,
    }
    if preserve_raw_candidate_timing:
        item["_stt_original_candidate_start"] = raw_start
        item["_stt_original_candidate_end"] = raw_end
        item["_stt_original_candidate_start_frame"] = raw_start_frame
        item["_stt_original_candidate_end_frame"] = raw_end_frame
    for key in ("_clip_idx", "_clip_file", "words", "quality", "quality_history", "quality_candidates"):
        if key in seg:
            item[key] = seg.get(key)
    for key in STT_SEGMENT_METADATA_KEYS:
        if key in seg and key not in item:
            item[key] = seg.get(key)
    item.update(_project_segment_status_payload(item, threshold=status_threshold))
    if start_frame is None:
        start_frame = sec_to_nearest_frame(start, fps)
    if end_frame is None:
        end_frame = sec_to_nearest_frame(end, fps)
    item["start_frame"] = _safe_int(start_frame)
    item["end_frame"] = max(item["start_frame"] + 1, _safe_int(end_frame, item["start_frame"]))
    item["timeline_start_frame"] = item["start_frame"]
    item["timeline_end_frame"] = item["end_frame"]
    item["frame_rate"] = fps
    item["timeline_frame_rate"] = fps
    item["timeline_start"] = frame_to_sec(item["timeline_start_frame"], fps)
    item["timeline_end"] = frame_to_sec(item["timeline_end_frame"], fps)
    item["frame_range"] = {
        "unit": "frame",
        "start": item["start_frame"],
        "end": item["end_frame"],
        "timeline_frame_rate": fps,
    }
    return item


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
