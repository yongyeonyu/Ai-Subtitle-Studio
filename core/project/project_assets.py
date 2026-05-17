from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Any

from core.coerce import safe_float as _safe_float, safe_round_int as _safe_int
from core.frame_time import frame_to_sec, normalize_fps, normalize_segments_to_frame_grid, sec_to_nearest_frame
from core.project.project_format import project_primary_fps
from core.project.project_srt import parse_srt_to_segments, strip_whisper_control_tokens
from core.utils import seconds_to_srt_time


PROJECT_TEXT_ASSET_SCHEMA = "ai_subtitle_studio.project_text_assets.v1"
PROJECT_TEXT_ASSET_TIMEBASE_SCHEMA = "ai_subtitle_studio.project_text_assets.timebase.v1"
PROJECT_EXTERNAL_STORAGE = "external_srt"
SRT_FRAME_QUANTIZATION_MODE = "frame_grid_to_srt_millisecond"

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


def _iter_project_rows(rows: Any):
    if rows is None:
        return ()
    return rows


def copy_project_rows(rows: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in _iter_project_rows(rows) if isinstance(row, dict)]


def copy_project_track_rows(tracks: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(tracks, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for source, rows in tracks.items():
        copied = copy_project_rows(rows)
        if copied:
            out[str(source)] = copied
    return out


def copy_project_track_rows_with_counts(
    tracks: Any,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    if not isinstance(tracks, dict):
        return {}, {}
    out: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}
    for source, rows in tracks.items():
        copied = copy_project_rows(rows)
        if copied:
            source_key = str(source)
            out[source_key] = copied
            counts[source_key] = len(copied)
    return out, counts


def stt_candidate_track_counts(tracks: Any, *, count_key: str = "segment_count") -> dict[str, int]:
    if not isinstance(tracks, dict):
        return {}
    counts: dict[str, int] = {}
    for source, rows in tracks.items():
        if isinstance(rows, list):
            counts[str(source)] = len(rows)
            continue
        if isinstance(rows, dict):
            try:
                counts[str(source)] = int(rows.get(count_key, 0) or 0)
            except (TypeError, ValueError):
                continue
    return counts


def _track_metadata_rows(track: dict[str, Any]) -> list[Any]:
    metadata = track.get("metadata")
    return metadata if isinstance(metadata, list) else []


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


def _existing_stt_track_manifest(
    project: dict[str, Any] | None,
    *,
    key: str,
    source: str,
) -> dict[str, Any]:
    if not isinstance(project, dict):
        return {}
    asset_storage = project.get("asset_storage")
    tracks = asset_storage.get("tracks") if isinstance(asset_storage, dict) else {}
    track = tracks.get(key) if isinstance(tracks, dict) else None
    if isinstance(track, dict):
        preserved = dict(track)
    else:
        preserved = _inferred_track_ref(project, key)
    if not preserved:
        return {}
    preserved.setdefault("schema", PROJECT_TEXT_ASSET_SCHEMA)
    preserved.setdefault("key", key)
    preserved.setdefault("format", "srt")
    preserved.setdefault("source", source)
    if not str(preserved.get("path", "") or "").strip():
        inferred = _inferred_track_path(project, key)
        if inferred:
            project_path = _project_file_path(project)
            preserved["path"] = relative_asset_path(project_path, inferred) if project_path else inferred
    return preserved


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
    rows: Any,
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
    for idx, row in enumerate(_iter_project_rows(rows)):
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


def _subtitle_gap_vector_rows(
    segments: list[dict[str, Any]] | None,
    *,
    primary_fps: float,
) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps or 30.0)
    out: list[dict[str, Any]] = []
    for idx, seg in enumerate(segments or []):
        if not isinstance(seg, dict) or not bool(seg.get("is_gap")):
            continue
        timing = _segment_frame_payload(seg, default_fps=fps, min_frames=1)
        clip: dict[str, Any] = {}
        if seg.get("_clip_idx") is not None:
            clip["index"] = int(seg.get("_clip_idx") or 0)
        if seg.get("_clip_file"):
            clip["file"] = str(seg.get("_clip_file") or "")
        item = {
            "id": str(seg.get("id") or f"subtitle_gap_vector_{len(out) + 1:04d}"),
            "kind": "subtitle_gap",
            "source_index": int(seg.get("index", idx + 1) or idx + 1),
            "line": int(seg.get("line", idx) or idx),
            "time": {
                "unit": "frame",
                "start_frame": int(timing["start_frame"]),
                "end_frame": int(timing["end_frame"]),
                "timeline_frame_rate": float(timing["timeline_frame_rate"]),
            },
            "flags": {
                "is_gap": True,
            },
        }
        if clip:
            item["clip"] = clip
        out.append(item)
    return out


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


def _materialize_project_rows(rows: Any) -> list[Any]:
    if isinstance(rows, list):
        return rows
    return list(() if rows is None else rows)


def _write_srt_entry(handle, serial: int, start: float, end: float, text: str) -> None:
    handle.write(f"{serial}\n")
    handle.write(f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}\n")
    handle.write(text)
    handle.write("\n\n")


def write_srt_track(
    rows: list[dict[str, Any]],
    srt_path: str,
    *,
    metadata_source: str = "",
    metadata_default_fps: float | None = None,
) -> dict[str, Any]:
    os.makedirs(os.path.dirname(os.path.abspath(srt_path)), exist_ok=True)
    source_rows = _materialize_project_rows(rows)
    inferred_fps = None
    for row in source_rows:
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
        normalize_segments_to_frame_grid(source_rows, inferred_fps, min_frames=1, preserve_order=True)
        if inferred_fps is not None
        else copy_project_rows(source_rows)
    )
    serial = 1
    persisted: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] | None = [] if metadata_default_fps is not None else None
    with open(srt_path, "w", encoding="utf-8") as handle:
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
            _write_srt_entry(handle, serial, start, end, text)
            persisted_row = {**row, "start": start, "end": end, "text": text}
            persisted.append(persisted_row)
            if metadata is not None:
                metadata.append(
                    compact_segment_metadata(
                        persisted_row,
                        serial,
                        source=metadata_source,
                        default_fps=float(metadata_default_fps or 30.0),
                    )
                )
            serial += 1
    return {
        "path": srt_path,
        "count": len(persisted),
        "signature": _track_signature(persisted),
        "size_bytes": os.path.getsize(srt_path) if os.path.exists(srt_path) else 0,
        "metadata": metadata if metadata is not None else [],
        "rows": persisted,
    }


def _track_manifest(project_path: str, key: str, srt_info: dict[str, Any], metadata: list[dict[str, Any]]) -> dict[str, Any]:
    first_meta = metadata[0] if metadata and isinstance(metadata[0], dict) else {}
    return {
        "schema": PROJECT_TEXT_ASSET_SCHEMA,
        "key": key,
        "format": "srt",
        "path": relative_asset_path(project_path, str(srt_info.get("path") or "")),
        "segment_count": int(srt_info.get("count", 0) or 0),
        "signature": str(srt_info.get("signature", "") or ""),
        "size_bytes": int(srt_info.get("size_bytes", 0) or 0),
        "timebase": {
            "schema": PROJECT_TEXT_ASSET_TIMEBASE_SCHEMA,
            "unit": "frame",
            "primary_fps": normalize_fps(first_meta.get("timeline_frame_rate") or 30.0),
            "srt_quantization": SRT_FRAME_QUANTIZATION_MODE,
        },
        "metadata": metadata,
    }


def _merge_srt_metadata(
    rows: Any,
    metadata: list[Any],
    *,
    source: str = "",
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(_iter_project_rows(rows)):
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
        if source or any(
            key in item
            for key in (
                "_stt_original_candidate_start_frame",
                "_stt_original_candidate_end_frame",
                "_stt_original_candidate_start",
                "_stt_original_candidate_end",
                "original_start",
                "original_end",
            )
        ):
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
    if isinstance(track, dict) and track:
        return track
    if key == _FINAL_TRACK:
        direct = subtitles.get("external_track")
        if isinstance(direct, dict) and direct:
            return direct
        external_tracks = subtitles.get("external_tracks")
        if (
            isinstance(external_tracks, dict)
            and isinstance(external_tracks.get(_FINAL_TRACK), dict)
            and external_tracks.get(_FINAL_TRACK)
        ):
            return external_tracks[_FINAL_TRACK]
    inferred = _inferred_track_ref(project, key)
    return inferred if inferred else {}


def _track_ref(track: dict[str, Any]) -> dict[str, Any]:
    return {
        key: track.get(key)
        for key in ("schema", "key", "format", "path", "segment_count", "signature", "size_bytes", "source")
        if key in track
    }


def _track_rows_from_write_result(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = result.get("rows") if isinstance(result, dict) else None
    return rows if isinstance(rows, list) else []


def _track_metadata_from_write_result(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    metadata = result.get("metadata") if isinstance(result, dict) else None
    return metadata if isinstance(metadata, list) else []


def _external_stt_track_payload(stt_external_tracks: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    refs: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    if not isinstance(stt_external_tracks, dict):
        return refs, counts
    for source, track in stt_external_tracks.items():
        if not isinstance(track, dict) or not track:
            continue
        source_key = str(source)
        refs[source_key] = _track_ref(track)
        try:
            counts[source_key] = int(track.get("segment_count", 0) or 0)
        except (TypeError, ValueError):
            continue
    return refs, counts


def strip_external_text_runtime_payload(project: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(project, dict):
        return project
    project.pop("segments", None)
    subtitles = dict(project.get("subtitles", {}) or {})
    subtitles.pop("segments", None)
    subtitles["storage"] = PROJECT_EXTERNAL_STORAGE
    project["subtitles"] = subtitles

    editor_state = project.get("editor_state")
    if isinstance(editor_state, dict):
        editor_state = dict(editor_state)
        editor_subtitles = dict(editor_state.get("subtitles", {}) or {})
        editor_subtitles["segments"] = []
        editor_subtitles["storage"] = PROJECT_EXTERNAL_STORAGE
        editor_state["subtitles"] = editor_subtitles

        rendering = dict(editor_state.get("rendering", {}) or {})
        canvas = dict(rendering.get("subtitle_canvas", {}) or {})
        canvas["segments"] = []
        rendering["subtitle_canvas"] = canvas
        editor_state["rendering"] = rendering

        stt_state = dict(editor_state.get("stt", {}) or {})
        stt_state["preview_segments"] = []
        stt_state["candidate_tracks"] = {}
        editor_state["stt"] = stt_state

        editor_analysis = dict(editor_state.get("analysis", {}) or {})
        editor_analysis.pop("stt_candidate_tracks", None)
        editor_state["analysis"] = editor_analysis
        project["editor_state"] = editor_state

    analysis = dict(project.get("analysis", {}) or {})
    analysis.pop("stt_candidate_tracks", None)
    project["analysis"] = analysis
    return project


def load_external_subtitle_segments(project: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []
    hot_cached = project.get("_hot_open_subtitle_segments_cache")
    if isinstance(hot_cached, list) and hot_cached:
        return copy_project_rows(hot_cached)
    track = _track_from_project(project, _FINAL_TRACK)
    path = resolve_project_asset_path(project, track.get("path"))
    primary_fps = _project_primary_fps(project)
    if path and os.path.exists(path):
        return _merge_srt_metadata(
            parse_srt_to_segments(path),
            _track_metadata_rows(track),
            primary_fps=primary_fps,
        )
    cached = project.get("_external_subtitle_segments_cache")
    return copy_project_rows(cached)


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
            _track_metadata_rows(track),
            source=source,
            primary_fps=primary_fps,
        )
        rows = sanitize_stt_track_rows(rows, source=source, primary_fps=primary_fps)
        if rows:
            out[source] = rows
    if out:
        return out
    cached = project.get("_external_stt_tracks_cache")
    return copy_project_track_rows(cached)


def hydrate_project_text_asset_cache(project: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(project, dict) or not project_uses_external_text_assets(project):
        return project
    subtitles = load_external_subtitle_segments(project)
    if subtitles:
        project["_external_subtitle_segments_cache"] = subtitles
    stt_tracks = load_external_stt_tracks(project)
    if stt_tracks:
        project["_external_stt_tracks_cache"] = stt_tracks
        stt_counts = stt_candidate_track_counts(stt_tracks)
        editor_state = project.setdefault("editor_state", {})
        if isinstance(editor_state, dict):
            stt_state = editor_state.setdefault("stt", {})
            if isinstance(stt_state, dict):
                stt_state["candidate_tracks"] = copy_project_track_rows(stt_tracks)
                stt_state["candidate_counts"] = dict(stt_counts)
    return project


def externalize_project_text_assets(
    project_path: str,
    project: dict[str, Any],
    *,
    final_segments: list[dict[str, Any]] | None = None,
    stt_tracks: dict[str, list[dict[str, Any]]] | None = None,
    rewrite_stt_reference_tracks: bool = True,
) -> dict[str, Any]:
    if not project_path or not isinstance(project, dict):
        return project
    asset_dir = project_asset_dir(project_path)
    subtitle_dir = os.path.join(asset_dir, "subtitles")
    os.makedirs(subtitle_dir, exist_ok=True)
    primary_fps = _project_primary_fps(project)
    final_segments = normalize_segments_to_frame_grid(
        final_segments,
        primary_fps,
        min_frames=1,
        preserve_order=True,
    )
    gap_vector_rows = _subtitle_gap_vector_rows(final_segments, primary_fps=primary_fps)
    stt_tracks = dict(stt_tracks or {})

    tracks_manifest: dict[str, Any] = {}
    final_info = write_srt_track(
        final_segments,
        os.path.join(subtitle_dir, "final.srt"),
        metadata_default_fps=primary_fps,
    )
    final_rows = _track_rows_from_write_result(final_info)
    final_metadata = _track_metadata_from_write_result(final_info)
    final_track = _track_manifest(project_path, _FINAL_TRACK, final_info, final_metadata)
    tracks_manifest[_FINAL_TRACK] = final_track
    project["_hot_open_subtitle_segments_cache"] = final_rows
    final_track_ref = _track_ref(final_track)

    stt_external_tracks: dict[str, Any] = {}
    for source in ("STT1", "STT2"):
        key = f"{_STT_TRACK_PREFIX}{source.lower()}"
        if not rewrite_stt_reference_tracks:
            preserved = _existing_stt_track_manifest(
                project,
                key=key,
                source=source,
            )
            if preserved:
                tracks_manifest[key] = preserved
                stt_external_tracks[source] = preserved
                continue
        rows = sanitize_stt_track_rows(
            stt_tracks.get(source),
            source=source,
            primary_fps=primary_fps,
        )
        if not rows:
            continue
        info = write_srt_track(
            rows,
            os.path.join(subtitle_dir, f"{source.lower()}.srt"),
            metadata_source=source,
            metadata_default_fps=primary_fps,
        )
        metadata = _track_metadata_from_write_result(info)
        track = _track_manifest(project_path, key, info, metadata)
        track["source"] = source
        tracks_manifest[key] = track
        stt_external_tracks[source] = track
    stt_track_refs, stt_track_counts = _external_stt_track_payload(stt_external_tracks)

    project["asset_storage"] = {
        "schema": PROJECT_TEXT_ASSET_SCHEMA,
        "mode": PROJECT_EXTERNAL_STORAGE,
        "base_dir": relative_asset_path(project_path, asset_dir),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "timebase": {
            "schema": PROJECT_TEXT_ASSET_TIMEBASE_SCHEMA,
            "unit": "frame",
            "primary_fps": primary_fps,
            "srt_quantization": SRT_FRAME_QUANTIZATION_MODE,
        },
        "tracks": tracks_manifest,
    }

    subtitles = project.setdefault("subtitles", {})
    subtitles["storage"] = PROJECT_EXTERNAL_STORAGE
    subtitles["srt_path"] = final_track["path"]
    subtitles["segment_count"] = final_track["segment_count"]
    subtitles["segment_signature"] = final_track["signature"]
    subtitles["external_track"] = dict(final_track_ref)
    subtitles["external_tracks"] = {_FINAL_TRACK: dict(final_track_ref)}
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
        canvas["gap_segments"] = gap_vector_rows
        canvas["segment_signature"] = final_track["signature"]
        canvas["source"] = PROJECT_EXTERNAL_STORAGE
        stt_state = editor_state.setdefault("stt", {})
        stt_state["preview_segments"] = []
        stt_state["candidate_tracks"] = {}
        stt_state["external_tracks"] = {source: dict(ref) for source, ref in stt_track_refs.items()}
        stt_state["candidate_counts"] = dict(stt_track_counts)
        editor_analysis = editor_state.setdefault("analysis", {})
        if isinstance(editor_analysis, dict):
            editor_analysis.pop("stt_candidate_tracks", None)
            editor_analysis["external_stt_tracks"] = {source: dict(ref) for source, ref in stt_track_refs.items()}
    analysis = project.setdefault("analysis", {})
    analysis.pop("stt_candidate_tracks", None)
    analysis["stt_candidate_schema"] = "stt_candidate_tracks.external_srt.v1"
    analysis["external_stt_tracks"] = {source: dict(ref) for source, ref in stt_track_refs.items()}
    analysis["stt_candidate_counts"] = dict(stt_track_counts)
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
    "copy_project_rows",
    "copy_project_track_rows",
    "copy_project_track_rows_with_counts",
    "externalize_project_text_assets",
    "hydrate_project_text_asset_cache",
    "load_external_stt_tracks",
    "load_external_subtitle_segments",
    "project_asset_dir",
    "project_uses_external_text_assets",
    "relative_asset_path",
    "resolve_project_asset_path",
    "sanitize_stt_track_rows",
    "strip_external_text_runtime_payload",
    "write_srt_track",
]
