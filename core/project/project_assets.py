from __future__ import annotations

import hashlib
import os
from bisect import bisect_right
from datetime import datetime
from typing import Any

from core.project.project_srt import parse_srt_to_segments
from core.utils import seconds_to_srt_time


PROJECT_TEXT_ASSET_SCHEMA = "ai_subtitle_studio.project_text_assets.v1"
PROJECT_EXTERNAL_STORAGE = "external_srt"

_FINAL_TRACK = "final"
_STT_TRACK_PREFIX = "stt_"

_TEXT_KEYS = {
    "text",
    "original_text",
    "dictated_text",
    "prompt",
    "prompt_text",
    "context",
    "stt_ensemble_context_prev",
    "stt_ensemble_context_next",
    "llm_note",
}

_HEAVY_KEYS = {
    "words",
    "quality_candidates",
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
}

_COMPACT_META_KEYS = {
    "id",
    "index",
    "line",
    "speaker",
    "speaker_list",
    "stt_mode",
    "stt_pending",
    "_live_stt_preview",
    "_clip_idx",
    "_clip_file",
    "clip_id",
    "clip_local_start_frame",
    "clip_local_end_frame",
    "source_frame_rate",
    "start_frame",
    "end_frame",
    "timeline_start_frame",
    "timeline_end_frame",
    "frame_rate",
    "timeline_frame_rate",
    "frame_range",
    "quality",
    "quality_history",
    "quality_stale",
    "stt_selected_source",
    "stt_ensemble_source",
    "stt_ensemble_similarity",
    "stt_ensemble_needs_llm_review",
    "stt_ensemble_inserted_from_stt2",
    "stt_ensemble_primary_locked",
    "stt_ensemble_word_rover",
    "stt_ensemble_llm_selected_source",
    "stt_ensemble_llm_selected_label",
    "stt_recheck_applied",
    "stt_recheck_original_scores",
    "stt_lattice_artifact_path",
    "stt_preview_source",
    "source",
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
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_path_name(name: str) -> str:
    out = "".join("_" if c in '<>:"/\\|?*' else c for c in str(name or "").strip())
    return out.strip().strip(".") or "project"


def project_asset_dir(project_path: str) -> str:
    folder = os.path.dirname(os.path.abspath(project_path))
    stem = os.path.splitext(os.path.basename(project_path))[0]
    return os.path.join(folder, f"{_safe_path_name(stem)}.assets")


def relative_asset_path(project_path: str, asset_path: str) -> str:
    try:
        return os.path.relpath(os.path.abspath(asset_path), os.path.dirname(os.path.abspath(project_path)))
    except Exception:
        return os.path.abspath(asset_path)


def resolve_project_asset_path(project: dict[str, Any] | None, path: str | None) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    if os.path.isabs(text):
        return text
    base = ""
    if isinstance(project, dict):
        base = str(project.get("_project_file_path") or project.get("project_path") or "")
    if base:
        return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(base)), text))
    return os.path.abspath(text)


def _segment_start(seg: dict[str, Any]) -> float:
    return _safe_float(seg.get("start", seg.get("timeline_start", 0.0)))


def _segment_end(seg: dict[str, Any]) -> float:
    start = _segment_start(seg)
    return max(start, _safe_float(seg.get("end", seg.get("timeline_end", start)), start))


def _track_signature(rows: list[dict[str, Any]]) -> str:
    compact = [
        {
            "start": round(_segment_start(row), 3),
            "end": round(_segment_end(row), 3),
            "text": str(row.get("text", "") or ""),
            "speaker": str(row.get("speaker", row.get("spk", "")) or ""),
        }
        for row in rows or []
        if isinstance(row, dict) and str(row.get("text", "") or "").strip()
    ]
    payload = repr(compact).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _track_text_key(text: str) -> str:
    return "".join(str(text or "").lower().split())


def _stt_track_row_score(row: dict[str, Any]) -> float:
    score = None
    for key in ("stt_score", "score"):
        try:
            value = float(row.get(key))
        except (TypeError, ValueError):
            continue
        score = value * 100.0 if 0.0 < value <= 1.0 else value
        break
    if score is None:
        score = 55.0
    text_len = len(str(row.get("text", "") or "").strip())
    duration = max(0.0, _segment_end(row) - _segment_start(row))
    # Favor good ASR confidence and enough text, but avoid huge rolling-window
    # candidates winning over multiple focused subtitle candidates.
    return float(score) + min(text_len, 80) * 0.08 + min(duration, 4.0) * 0.20 - max(0.0, duration - 8.0) * 3.0


def sanitize_stt_track_rows(
    rows: list[dict[str, Any]] | None,
    *,
    source: str = "",
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    """Return a compact, non-overlapping STT preview track for project assets."""
    cleaned: list[tuple[int, dict[str, Any]]] = []
    for idx, row in enumerate(rows or []):
        if not isinstance(row, dict) or row.get("is_gap"):
            continue
        text = str(row.get("text", "") or "").strip()
        if not text:
            continue
        start = _segment_start(row)
        end = _segment_end(row)
        if end <= start:
            end = start + 0.1
        item = dict(row)
        item["start"] = start
        item["end"] = end
        item["text"] = text.replace("\u2028", "\n")
        if source:
            item["source"] = source
            item["stt_preview_source"] = source
        cleaned.append((idx, item))
    if len(cleaned) <= 1:
        out: list[dict[str, Any]] = []
        for i, (_idx, item) in enumerate(cleaned):
            row = dict(item)
            row["index"] = i + 1
            out.append(row)
        return out

    best_by_exact_key: dict[tuple[int, int, str], tuple[int, dict[str, Any]]] = {}
    fps = max(1.0, _safe_float(primary_fps, 30.0))
    for original_idx, item in cleaned:
        start_frame = int(round(_segment_start(item) * fps))
        end_frame = int(round(_segment_end(item) * fps))
        key = (start_frame, end_frame, _track_text_key(str(item.get("text", "") or "")))
        previous = best_by_exact_key.get(key)
        if previous is None or _stt_track_row_score(item) > _stt_track_row_score(previous[1]):
            best_by_exact_key[key] = (original_idx, item)

    candidates = sorted(
        best_by_exact_key.values(),
        key=lambda pair: (_segment_end(pair[1]), _segment_start(pair[1]), pair[0]),
    )
    ends = [_segment_end(item) for _idx, item in candidates]
    tolerance = max(0.035, min(0.090, 2.0 / fps))
    weights = [_stt_track_row_score(item) for _idx, item in candidates]
    prev_indices = [
        bisect_right(ends, _segment_start(item) + tolerance, 0, i) - 1
        for i, (_idx, item) in enumerate(candidates)
    ]
    dp = [0.0] * (len(candidates) + 1)
    take = [False] * len(candidates)
    for i, weight in enumerate(weights, start=1):
        include = weight + dp[prev_indices[i - 1] + 1]
        exclude = dp[i - 1]
        if include > exclude:
            dp[i] = include
            take[i - 1] = True
        else:
            dp[i] = exclude

    selected_pairs: list[tuple[int, dict[str, Any]]] = []
    i = len(candidates) - 1
    while i >= 0:
        include = weights[i] + dp[prev_indices[i] + 1]
        if take[i] and include >= dp[i]:
            selected_pairs.append(candidates[i])
            i = prev_indices[i]
        else:
            i -= 1
    selected_pairs.reverse()
    selected = [dict(item) for _idx, item in sorted(selected_pairs, key=lambda pair: (_segment_start(pair[1]), _segment_end(pair[1]), pair[0]))]

    out: list[dict[str, Any]] = []
    for item in selected:
        if out:
            prev = out[-1]
            overlap = _segment_end(prev) - _segment_start(item)
            if overlap > 0.0:
                if overlap <= tolerance:
                    prev["end"] = max(_segment_start(prev) + 0.05, _segment_start(item))
                else:
                    if _stt_track_row_score(item) > _stt_track_row_score(prev):
                        out.pop()
                    else:
                        continue
        if _segment_end(item) <= _segment_start(item):
            item["end"] = _segment_start(item) + 0.05
        item["index"] = len(out) + 1
        out.append(item)
    for item in out:
        start = _segment_start(item)
        end = _segment_end(item)
        start_frame = int(round(start * fps))
        end_frame = max(start_frame + 1, int(round(end * fps)))
        item["start_frame"] = start_frame
        item["end_frame"] = end_frame
        item["timeline_start_frame"] = start_frame
        item["timeline_end_frame"] = end_frame
        item["frame_rate"] = fps
        item["timeline_frame_rate"] = fps
        item["frame_range"] = {
            "unit": "frame",
            "start": start_frame,
            "end": end_frame,
            "timeline_frame_rate": fps,
        }
    return out


def _compact_value(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(value, dict):
        out = {}
        for key, nested in value.items():
            key_text = str(key)
            if key_text in _TEXT_KEYS or key_text in _HEAVY_KEYS:
                continue
            compact = _compact_value(nested, depth + 1)
            if compact not in (None, "", [], {}):
                out[key_text] = compact
        return out
    if isinstance(value, list):
        out = []
        for item in value[:32]:
            compact = _compact_value(item, depth + 1)
            if compact not in (None, "", [], {}):
                out.append(compact)
        return out
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def compact_segment_metadata(seg: dict[str, Any], index: int, *, source: str = "") -> dict[str, Any]:
    meta: dict[str, Any] = {"index": int(index)}
    for key in _COMPACT_META_KEYS:
        if key in seg:
            value = _compact_value(seg.get(key))
            if value not in (None, "", [], {}):
                meta[key] = value
    text = str(seg.get("text", "") or "")
    if text:
        meta["text_hash"] = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    if source:
        meta["source"] = source
        meta["stt_preview_source"] = source
    return meta


def write_srt_track(rows: list[dict[str, Any]], srt_path: str) -> dict[str, Any]:
    os.makedirs(os.path.dirname(os.path.abspath(srt_path)), exist_ok=True)
    lines: list[str] = []
    serial = 1
    persisted: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict) or row.get("is_gap"):
            continue
        text = str(row.get("text", "") or "").strip().replace("\u2028", "\n")
        if not text:
            continue
        start = _segment_start(row)
        end = _segment_end(row)
        if end <= start:
            end = start + 0.1
        lines.extend(
            [
                str(serial),
                f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}",
                text,
                "",
            ]
        )
        persisted.append({**row, "start": start, "end": end, "text": text})
        serial += 1
    with open(srt_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return {
        "path": srt_path,
        "count": len(persisted),
        "signature": _track_signature(persisted),
        "size_bytes": os.path.getsize(srt_path) if os.path.exists(srt_path) else 0,
        "rows": persisted,
    }


def _track_manifest(project_path: str, key: str, srt_info: dict[str, Any], metadata: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": PROJECT_TEXT_ASSET_SCHEMA,
        "key": key,
        "format": "srt",
        "path": relative_asset_path(project_path, str(srt_info.get("path") or "")),
        "segment_count": int(srt_info.get("count", 0) or 0),
        "signature": str(srt_info.get("signature", "") or ""),
        "size_bytes": int(srt_info.get("size_bytes", 0) or 0),
        "metadata": metadata,
    }


def _merge_srt_metadata(rows: list[dict[str, Any]], metadata: list[Any], *, source: str = "") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        item = dict(row)
        meta = metadata[idx] if idx < len(metadata) and isinstance(metadata[idx], dict) else {}
        item.update({key: value for key, value in meta.items() if key not in {"text", "start", "end"}})
        item["text"] = str(row.get("text", "") or "")
        item["start"] = _safe_float(row.get("start", 0.0))
        item["end"] = _safe_float(row.get("end", item["start"]), item["start"])
        item["index"] = int(item.get("index", idx + 1) or idx + 1)
        if source:
            item["source"] = source
            item["stt_preview_source"] = source
        out.append(item)
    return out


def _track_from_project(project: dict[str, Any], key: str) -> dict[str, Any]:
    subtitles = project.get("subtitles", {}) if isinstance(project.get("subtitles"), dict) else {}
    asset_storage = project.get("asset_storage", {}) if isinstance(project.get("asset_storage"), dict) else {}
    tracks = asset_storage.get("tracks", {}) if isinstance(asset_storage.get("tracks"), dict) else {}
    track = tracks.get(key)
    if isinstance(track, dict):
        return track
    if key == _FINAL_TRACK:
        direct = subtitles.get("external_track")
        if isinstance(direct, dict):
            return direct
        external_tracks = subtitles.get("external_tracks")
        if isinstance(external_tracks, dict) and isinstance(external_tracks.get(_FINAL_TRACK), dict):
            return external_tracks[_FINAL_TRACK]
    return {}


def _track_ref(track: dict[str, Any]) -> dict[str, Any]:
    return {
        key: track.get(key)
        for key in ("schema", "key", "format", "path", "segment_count", "signature", "size_bytes", "source")
        if key in track
    }


def load_external_subtitle_segments(project: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []
    track = _track_from_project(project, _FINAL_TRACK)
    path = resolve_project_asset_path(project, track.get("path"))
    if path and os.path.exists(path):
        return _merge_srt_metadata(parse_srt_to_segments(path), list(track.get("metadata") or []))
    cached = project.get("_external_subtitle_segments_cache")
    return [dict(row) for row in cached] if isinstance(cached, list) else []


def load_external_stt_tracks(project: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(project, dict):
        return {}
    asset_storage = project.get("asset_storage", {}) if isinstance(project.get("asset_storage"), dict) else {}
    tracks = asset_storage.get("tracks", {}) if isinstance(asset_storage.get("tracks"), dict) else {}
    analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
    external_stt = analysis.get("external_stt_tracks") if isinstance(analysis.get("external_stt_tracks"), dict) else {}
    out: dict[str, list[dict[str, Any]]] = {}
    for source in ("STT1", "STT2"):
        key = f"{_STT_TRACK_PREFIX}{source.lower()}"
        track = tracks.get(key)
        if not isinstance(track, dict):
            track = external_stt.get(source) if isinstance(external_stt, dict) else {}
        if not isinstance(track, dict):
            continue
        path = resolve_project_asset_path(project, track.get("path"))
        if not path or not os.path.exists(path):
            continue
        rows = _merge_srt_metadata(parse_srt_to_segments(path), list(track.get("metadata") or []), source=source)
        rows = sanitize_stt_track_rows(rows, source=source)
        if rows:
            out[source] = rows
    if out:
        return out
    cached = project.get("_external_stt_tracks_cache")
    if isinstance(cached, dict):
        return {
            str(source): [dict(row) for row in rows]
            for source, rows in cached.items()
            if isinstance(rows, list)
        }
    return out


def hydrate_project_text_asset_cache(project: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(project, dict) or not project_uses_external_text_assets(project):
        return project
    subtitles = load_external_subtitle_segments(project)
    if subtitles:
        project["_external_subtitle_segments_cache"] = subtitles
    stt_tracks = load_external_stt_tracks(project)
    if stt_tracks:
        project["_external_stt_tracks_cache"] = {
            source: [dict(row) for row in rows]
            for source, rows in stt_tracks.items()
        }
        editor_state = project.setdefault("editor_state", {})
        if isinstance(editor_state, dict):
            stt_state = editor_state.setdefault("stt", {})
            if isinstance(stt_state, dict):
                stt_state["candidate_tracks"] = {
                    source: [dict(row) for row in rows]
                    for source, rows in stt_tracks.items()
                }
                stt_state["candidate_counts"] = {
                    source: len(rows)
                    for source, rows in stt_tracks.items()
                }
    return project


def externalize_project_text_assets(
    project_path: str,
    project: dict[str, Any],
    *,
    final_segments: list[dict[str, Any]] | None = None,
    stt_tracks: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    if not project_path or not isinstance(project, dict):
        return project
    asset_dir = project_asset_dir(project_path)
    subtitle_dir = os.path.join(asset_dir, "subtitles")
    os.makedirs(subtitle_dir, exist_ok=True)
    final_segments = list(final_segments or [])
    stt_tracks = dict(stt_tracks or {})

    tracks_manifest: dict[str, Any] = {}
    final_info = write_srt_track(final_segments, os.path.join(subtitle_dir, "final.srt"))
    final_metadata = [
        compact_segment_metadata(row, idx + 1)
        for idx, row in enumerate(list(final_info.get("rows") or []))
    ]
    final_track = _track_manifest(project_path, _FINAL_TRACK, final_info, final_metadata)
    tracks_manifest[_FINAL_TRACK] = final_track

    stt_external_tracks: dict[str, Any] = {}
    for source in ("STT1", "STT2"):
        rows = sanitize_stt_track_rows(list(stt_tracks.get(source) or []), source=source)
        if not rows:
            continue
        key = f"{_STT_TRACK_PREFIX}{source.lower()}"
        info = write_srt_track(rows, os.path.join(subtitle_dir, f"{source.lower()}.srt"))
        metadata = [
            compact_segment_metadata(row, idx + 1, source=source)
            for idx, row in enumerate(list(info.get("rows") or []))
        ]
        track = _track_manifest(project_path, key, info, metadata)
        track["source"] = source
        tracks_manifest[key] = track
        stt_external_tracks[source] = track

    project["asset_storage"] = {
        "schema": PROJECT_TEXT_ASSET_SCHEMA,
        "mode": PROJECT_EXTERNAL_STORAGE,
        "base_dir": relative_asset_path(project_path, asset_dir),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "tracks": tracks_manifest,
    }

    subtitles = project.setdefault("subtitles", {})
    subtitles["storage"] = PROJECT_EXTERNAL_STORAGE
    subtitles["srt_path"] = final_track["path"]
    subtitles["segment_count"] = final_track["segment_count"]
    subtitles["segment_signature"] = final_track["signature"]
    subtitles["external_track"] = _track_ref(final_track)
    subtitles["external_tracks"] = {_FINAL_TRACK: _track_ref(final_track)}
    subtitles.pop("segments", None)

    editor_state = project.get("editor_state")
    if isinstance(editor_state, dict):
        editor_subtitles = editor_state.setdefault("subtitles", {})
        editor_subtitles["storage"] = PROJECT_EXTERNAL_STORAGE
        editor_subtitles["segments"] = []
        editor_subtitles["segment_count"] = final_track["segment_count"]
        editor_subtitles["segment_signature"] = final_track["signature"]
        editor_subtitles["srt_path"] = final_track["path"]
        rendering = editor_state.setdefault("rendering", {})
        canvas = rendering.setdefault("subtitle_canvas", {})
        canvas.setdefault("schema", "subtitle_canvas.vector.v2")
        canvas["segments"] = []
        canvas["segment_signature"] = final_track["signature"]
        canvas["source"] = PROJECT_EXTERNAL_STORAGE
        stt_state = editor_state.setdefault("stt", {})
        stt_state["preview_segments"] = []
        stt_state["candidate_tracks"] = {}
        stt_state["external_tracks"] = {
            source: _track_ref(track)
            for source, track in stt_external_tracks.items()
        }
        stt_state["candidate_counts"] = {
            source: int(track.get("segment_count", 0) or 0)
            for source, track in stt_external_tracks.items()
        }
        editor_analysis = editor_state.setdefault("analysis", {})
        if isinstance(editor_analysis, dict):
            editor_analysis.pop("stt_candidate_tracks", None)
            editor_analysis["external_stt_tracks"] = {
                source: _track_ref(track)
                for source, track in stt_external_tracks.items()
            }
    analysis = project.setdefault("analysis", {})
    analysis.pop("stt_candidate_tracks", None)
    analysis["stt_candidate_schema"] = "stt_candidate_tracks.external_srt.v1"
    analysis["external_stt_tracks"] = {
        source: _track_ref(track)
        for source, track in stt_external_tracks.items()
    }
    analysis["stt_candidate_counts"] = {
        source: int(track.get("segment_count", 0) or 0)
        for source, track in stt_external_tracks.items()
    }
    return project


def project_uses_external_text_assets(project: dict[str, Any] | None) -> bool:
    if not isinstance(project, dict):
        return False
    subtitles = project.get("subtitles", {}) if isinstance(project.get("subtitles"), dict) else {}
    asset_storage = project.get("asset_storage", {}) if isinstance(project.get("asset_storage"), dict) else {}
    return (
        str(subtitles.get("storage", "") or "") == PROJECT_EXTERNAL_STORAGE
        or str(asset_storage.get("mode", "") or "") == PROJECT_EXTERNAL_STORAGE
    )


__all__ = [
    "PROJECT_EXTERNAL_STORAGE",
    "PROJECT_TEXT_ASSET_SCHEMA",
    "externalize_project_text_assets",
    "hydrate_project_text_asset_cache",
    "load_external_stt_tracks",
    "load_external_subtitle_segments",
    "project_asset_dir",
    "project_uses_external_text_assets",
    "relative_asset_path",
    "resolve_project_asset_path",
    "sanitize_stt_track_rows",
    "write_srt_track",
]
