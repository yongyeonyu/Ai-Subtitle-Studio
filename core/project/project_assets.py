from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, normalize_segments_to_frame_grid, sec_to_nearest_frame
from core.project.project_format import project_primary_fps
from core.project.project_srt import parse_srt_to_segments, strip_whisper_control_tokens
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
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return int(default)


def _project_primary_fps(project: dict[str, Any] | None) -> float:
    return project_primary_fps(project)


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


def _project_file_path(project: dict[str, Any] | None) -> str:
    if not isinstance(project, dict):
        return ""
    for key in ("_project_file_path", "project_path"):
        value = str(project.get(key) or "").strip()
        if value:
            return os.path.abspath(os.path.expanduser(value))
    return ""


def _inferred_track_path(project: dict[str, Any] | None, key: str) -> str:
    project_path = _project_file_path(project)
    if not project_path:
        return ""
    filename = {
        _FINAL_TRACK: "final.srt",
        f"{_STT_TRACK_PREFIX}stt1": "stt1.srt",
        f"{_STT_TRACK_PREFIX}stt2": "stt2.srt",
    }.get(str(key or "").strip())
    if not filename:
        return ""
    path = os.path.join(project_asset_dir(project_path), "subtitles", filename)
    return path if os.path.exists(path) else ""


def _inferred_track_ref(project: dict[str, Any] | None, key: str) -> dict[str, Any]:
    path = _inferred_track_path(project, key)
    if not path:
        return {}
    project_path = _project_file_path(project)
    stored_path = relative_asset_path(project_path, path) if project_path else path
    track: dict[str, Any] = {
        "schema": PROJECT_TEXT_ASSET_SCHEMA,
        "key": str(key or "").strip(),
        "format": "srt",
        "path": stored_path,
    }
    if str(key).startswith(_STT_TRACK_PREFIX):
        track["source"] = str(key)[len(_STT_TRACK_PREFIX) :].upper()
    return track


def _segment_start(seg: dict[str, Any]) -> float:
    return _safe_float(seg.get("start", seg.get("timeline_start", 0.0)))


def _segment_end(seg: dict[str, Any]) -> float:
    start = _segment_start(seg)
    return max(start, _safe_float(seg.get("end", seg.get("timeline_end", start)), start))


def _segment_timing_fps(seg: dict[str, Any], default: float = 30.0) -> float:
    frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
    return normalize_fps(
        seg.get("timeline_frame_rate")
        or frame_range.get("timeline_frame_rate")
        or seg.get("frame_rate")
        or seg.get("source_frame_rate")
        or default
    )


def _frame_timing_payload(
    start_frame: Any,
    end_frame: Any,
    fps: float,
    *,
    min_frames: int = 1,
) -> dict[str, Any]:
    start_value = max(0, _safe_int(start_frame))
    end_value = _safe_int(end_frame, start_value)
    if min_frames > 0:
        end_value = max(start_value + int(min_frames), end_value)
    else:
        end_value = max(start_value, end_value)
    return {
        "start_frame": start_value,
        "end_frame": end_value,
        "timeline_start_frame": start_value,
        "timeline_end_frame": end_value,
        "frame_rate": fps,
        "timeline_frame_rate": fps,
        "frame_range": {
            "unit": "frame",
            "start": start_value,
            "end": end_value,
            "timeline_frame_rate": fps,
        },
    }


def _segment_frame_payload(
    seg: dict[str, Any],
    *,
    default_fps: float = 30.0,
    min_frames: int = 1,
) -> dict[str, Any]:
    fps = _segment_timing_fps(seg, default_fps)
    frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
    start_frame = seg.get("start_frame", seg.get("timeline_start_frame", frame_range.get("start")))
    end_frame = seg.get("end_frame", seg.get("timeline_end_frame", frame_range.get("end")))
    if start_frame is None:
        start_frame = sec_to_nearest_frame(_segment_start(seg), fps)
    if end_frame is None:
        end_frame = sec_to_nearest_frame(_segment_end(seg), fps)
    return _frame_timing_payload(start_frame, end_frame, fps, min_frames=min_frames)


def _original_candidate_frame_payload(
    seg: dict[str, Any],
    *,
    default_fps: float = 30.0,
    min_frames: int = 1,
    include_seconds: bool = True,
) -> dict[str, Any]:
    fps = _segment_timing_fps(seg, default_fps)
    start_frame = seg.get("_stt_original_candidate_start_frame")
    end_frame = seg.get("_stt_original_candidate_end_frame")
    if start_frame is None:
        raw_start = _safe_float(
            seg.get(
                "_stt_original_candidate_start",
                seg.get("original_start", seg.get("start", seg.get("timeline_start", 0.0))),
            )
        )
        start_frame = sec_to_nearest_frame(raw_start, fps)
    if end_frame is None:
        raw_end = _safe_float(
            seg.get(
                "_stt_original_candidate_end",
                seg.get("original_end", seg.get("end", seg.get("timeline_end", 0.0))),
            )
        )
        end_frame = sec_to_nearest_frame(raw_end, fps)
    payload = {
        "_stt_original_candidate_start_frame": max(0, _safe_int(start_frame)),
        "_stt_original_candidate_end_frame": max(0, _safe_int(end_frame, _safe_int(start_frame))),
    }
    if min_frames > 0 and payload["_stt_original_candidate_end_frame"] <= payload["_stt_original_candidate_start_frame"]:
        payload["_stt_original_candidate_end_frame"] = payload["_stt_original_candidate_start_frame"] + int(min_frames)
    elif payload["_stt_original_candidate_end_frame"] < payload["_stt_original_candidate_start_frame"]:
        payload["_stt_original_candidate_end_frame"] = payload["_stt_original_candidate_start_frame"]
    if include_seconds:
        payload["_stt_original_candidate_start"] = frame_to_sec(payload["_stt_original_candidate_start_frame"], fps)
        payload["_stt_original_candidate_end"] = frame_to_sec(payload["_stt_original_candidate_end_frame"], fps)
    return payload


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
    """Return a stable STT preview track for project assets.

    STT1/STT2 tracks can legitimately overlap because different recognizers and
    rolling-window chunks do not share the final subtitle boundaries.  Keep
    distinct overlapping text, but collapse repeated overlapping rows with the
    same normalized text so reopening a project never erodes the candidate set.
    """
    cleaned: list[tuple[int, dict[str, Any]]] = []
    for idx, row in enumerate(rows or []):
        if not isinstance(row, dict) or row.get("is_gap"):
            continue
        text = strip_whisper_control_tokens(str(row.get("text", "") or ""))
        if not text:
            continue
        start = _segment_start(row)
        end = _segment_end(row)
        if end <= start:
            end = start + 0.1
        item = dict(row)
        item["text"] = text
        if source:
            item["source"] = source
            item["stt_preview_source"] = source
        timing = _segment_frame_payload(item, default_fps=primary_fps, min_frames=1)
        item.update(timing)
        item["start"] = frame_to_sec(timing["start_frame"], timing["timeline_frame_rate"])
        item["end"] = frame_to_sec(timing["end_frame"], timing["timeline_frame_rate"])
        item.update(
            _original_candidate_frame_payload(
                item,
                default_fps=timing["timeline_frame_rate"],
                min_frames=1,
                include_seconds=True,
            )
        )
        cleaned.append((idx, item))

    fps = max(1.0, _safe_float(primary_fps, 30.0))
    selected_pairs: list[tuple[int, dict[str, Any]]] = []
    for original_idx, item in cleaned:
        text_key = _track_text_key(str(item.get("text", "") or ""))
        start = _segment_start(item)
        end = _segment_end(item)
        duplicate_idx = None
        for idx, (_prev_original_idx, previous) in enumerate(selected_pairs):
            if _track_text_key(str(previous.get("text", "") or "")) != text_key:
                continue
            overlap = min(end, _segment_end(previous)) - max(start, _segment_start(previous))
            if overlap > max(0.035, min(0.090, 2.0 / fps)):
                duplicate_idx = idx
                break
        if duplicate_idx is None:
            selected_pairs.append((original_idx, item))
            continue
        previous = selected_pairs[duplicate_idx][1]
        if _stt_track_row_score(item) > _stt_track_row_score(previous):
            selected_pairs[duplicate_idx] = (original_idx, item)

    selected = [dict(item) for _idx, item in sorted(selected_pairs, key=lambda pair: (_segment_start(pair[1]), _segment_end(pair[1]), pair[0]))]

    out: list[dict[str, Any]] = []
    for item in selected:
        timing = _segment_frame_payload(item, default_fps=fps, min_frames=1)
        item.update(timing)
        item["start"] = frame_to_sec(timing["start_frame"], timing["timeline_frame_rate"])
        item["end"] = frame_to_sec(timing["end_frame"], timing["timeline_frame_rate"])
        item.update(
            _original_candidate_frame_payload(
                item,
                default_fps=timing["timeline_frame_rate"],
                min_frames=1,
                include_seconds=True,
            )
        )
        item["index"] = len(out) + 1
        out.append(item)
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


def compact_segment_metadata(
    seg: dict[str, Any],
    index: int,
    *,
    source: str = "",
    default_fps: float = 30.0,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"index": int(index)}
    for key in _COMPACT_META_KEYS:
        if key in seg:
            value = _compact_value(seg.get(key))
            if value not in (None, "", [], {}):
                meta[key] = value
    timing = _segment_frame_payload(seg, default_fps=default_fps, min_frames=1)
    meta.update(timing)
    if source or any(
        key in seg
        for key in (
            "_stt_original_candidate_start_frame",
            "_stt_original_candidate_end_frame",
            "_stt_original_candidate_start",
            "_stt_original_candidate_end",
            "original_start",
            "original_end",
        )
    ):
        meta.update(
            _original_candidate_frame_payload(
                seg,
                default_fps=timing["timeline_frame_rate"],
                min_frames=1,
                include_seconds=False,
            )
        )
    text = str(seg.get("text", "") or "")
    if text:
        meta["text_hash"] = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    if source:
        meta["source"] = source
        meta["stt_preview_source"] = source
    return meta


def write_srt_track(rows: list[dict[str, Any]], srt_path: str) -> dict[str, Any]:
    os.makedirs(os.path.dirname(os.path.abspath(srt_path)), exist_ok=True)
    inferred_fps = None
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        frame_range = row.get("frame_range")
        if isinstance(frame_range, dict) and frame_range.get("timeline_frame_rate") is not None:
            try:
                inferred_fps = normalize_fps(frame_range.get("timeline_frame_rate"))
                break
            except (TypeError, ValueError):
                pass
        for key in ("timeline_frame_rate", "frame_rate"):
            value = row.get(key)
            try:
                if value is not None and float(value) > 0.0:
                    inferred_fps = normalize_fps(value)
                    break
            except (TypeError, ValueError):
                continue
        if inferred_fps is not None:
            break
    prepared_rows = (
        normalize_segments_to_frame_grid(rows, inferred_fps, min_frames=1, preserve_order=True)
        if inferred_fps is not None
        else [dict(row) for row in list(rows or []) if isinstance(row, dict)]
    )
    lines: list[str] = []
    serial = 1
    persisted: list[dict[str, Any]] = []
    for row in prepared_rows:
        if not isinstance(row, dict) or row.get("is_gap"):
            continue
        text = strip_whisper_control_tokens(str(row.get("text", "") or "")).replace(".", "")
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


def _merge_srt_metadata(
    rows: list[dict[str, Any]],
    metadata: list[Any],
    *,
    source: str = "",
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        item = dict(row)
        meta = metadata[idx] if idx < len(metadata) and isinstance(metadata[idx], dict) else {}
        item.update({key: value for key, value in meta.items() if key not in {"text", "start", "end"}})
        item["text"] = strip_whisper_control_tokens(str(row.get("text", "") or ""))
        item["start"] = _safe_float(row.get("start", 0.0))
        item["end"] = _safe_float(row.get("end", item["start"]), item["start"])
        timing = _segment_frame_payload(item, default_fps=primary_fps, min_frames=1)
        item.update(timing)
        item["start"] = frame_to_sec(timing["start_frame"], timing["timeline_frame_rate"])
        item["end"] = frame_to_sec(timing["end_frame"], timing["timeline_frame_rate"])
        item["index"] = int(item.get("index", idx + 1) or idx + 1)
        if source:
            item["source"] = source
            item["stt_preview_source"] = source
            item.update(
                _original_candidate_frame_payload(
                    item,
                    default_fps=timing["timeline_frame_rate"],
                    min_frames=1,
                    include_seconds=True,
                )
            )
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
    inferred = _inferred_track_ref(project, key)
    return inferred if inferred else {}


def _track_ref(track: dict[str, Any]) -> dict[str, Any]:
    return {
        key: track.get(key)
        for key in ("schema", "key", "format", "path", "segment_count", "signature", "size_bytes", "source")
        if key in track
    }


def load_external_subtitle_segments(project: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []
    hot_cached = project.get("_hot_open_subtitle_segments_cache")
    if isinstance(hot_cached, list) and hot_cached:
        return [dict(row) for row in hot_cached if isinstance(row, dict)]
    track = _track_from_project(project, _FINAL_TRACK)
    path = resolve_project_asset_path(project, track.get("path"))
    primary_fps = _project_primary_fps(project)
    if path and os.path.exists(path):
        return _merge_srt_metadata(
            parse_srt_to_segments(path),
            list(track.get("metadata") or []),
            primary_fps=primary_fps,
        )
    cached = project.get("_external_subtitle_segments_cache")
    return [dict(row) for row in cached] if isinstance(cached, list) else []


def load_external_stt_tracks(project: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(project, dict):
        return {}
    primary_fps = _project_primary_fps(project)
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
        if not isinstance(track, dict) or not track:
            track = _track_from_project(project, key)
        if not isinstance(track, dict) or not track:
            continue
        path = resolve_project_asset_path(project, track.get("path"))
        if not path or not os.path.exists(path):
            continue
        rows = _merge_srt_metadata(
            parse_srt_to_segments(path),
            list(track.get("metadata") or []),
            source=source,
            primary_fps=primary_fps,
        )
        rows = sanitize_stt_track_rows(rows, source=source, primary_fps=primary_fps)
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
    primary_fps = _project_primary_fps(project)
    final_segments = normalize_segments_to_frame_grid(
        list(final_segments or []),
        primary_fps,
        min_frames=1,
        preserve_order=True,
    )
    stt_tracks = dict(stt_tracks or {})

    tracks_manifest: dict[str, Any] = {}
    final_info = write_srt_track(final_segments, os.path.join(subtitle_dir, "final.srt"))
    final_metadata = [
        compact_segment_metadata(row, idx + 1, default_fps=primary_fps)
        for idx, row in enumerate(list(final_info.get("rows") or []))
    ]
    final_track = _track_manifest(project_path, _FINAL_TRACK, final_info, final_metadata)
    tracks_manifest[_FINAL_TRACK] = final_track
    project["_hot_open_subtitle_segments_cache"] = [
        dict(row) for row in list(final_info.get("rows") or []) if isinstance(row, dict)
    ]

    stt_external_tracks: dict[str, Any] = {}
    for source in ("STT1", "STT2"):
        rows = sanitize_stt_track_rows(
            list(stt_tracks.get(source) or []),
            source=source,
            primary_fps=primary_fps,
        )
        if not rows:
            continue
        key = f"{_STT_TRACK_PREFIX}{source.lower()}"
        info = write_srt_track(rows, os.path.join(subtitle_dir, f"{source.lower()}.srt"))
        metadata = [
            compact_segment_metadata(row, idx + 1, source=source, default_fps=primary_fps)
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
    if (
        str(subtitles.get("storage", "") or "") == PROJECT_EXTERNAL_STORAGE
        or str(asset_storage.get("mode", "") or "") == PROJECT_EXTERNAL_STORAGE
    ):
        return True
    return bool(
        _inferred_track_path(project, _FINAL_TRACK)
        or _inferred_track_path(project, f"{_STT_TRACK_PREFIX}stt1")
        or _inferred_track_path(project, f"{_STT_TRACK_PREFIX}stt2")
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
