from __future__ import annotations

import atexit
import subprocess
import threading
import time
from typing import Any

import numpy as np

from core.native_json import dumps_json_bytes, dumps_json_text, json_default, loads_json, loads_json_output, write_jsonl_line
from core.native_swift_subtitle import find_native_cli_path, native_swift_runtime_enabled
from core.runtime.stage_metrics import _elapsed_ms, record_native_bridge_metric
from core.timeline_time import segment_display_time_bounds

_WORKER: subprocess.Popen | None = None
_WORKER_LOCK = threading.Lock()


def _enabled() -> bool:
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_TIMELINE")


def _vad_payload(vad_segments: list | tuple | None) -> str:
    rows: list[dict[str, float]] = []
    for item in vad_segments or []:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start", 0.0) or 0.0)
            end = float(item.get("end", start) or start)
        except Exception:
            continue
        if end > start:
            rows.append({"start": start, "end": end})
    return dumps_json_text(rows, compact=True)


def _boundary_time_value(item) -> float:
    try:
        if isinstance(item, dict):
            return float(
                item.get("timeline_sec", item.get("time", item.get("start", item.get("timeline_start", 0.0))))
                or 0.0
            )
        return float(item or 0.0)
    except Exception:
        return 0.0


def build_waveform_columns_via_swift(
    waveform: np.ndarray,
    *,
    width: int,
    total_duration: float,
    vad_segments: list | tuple | None = None,
) -> list[tuple[int, bool]] | None:
    if not _enabled():
        return None
    if waveform is None or int(width or 0) <= 0:
        return None
    cli = find_native_cli_path()
    if cli is None:
        return None
    wf = np.asarray(waveform, dtype=np.float32)
    if wf.size <= 0:
        return None
    try:
        proc = subprocess.run(
            [
                str(cli),
                "timeline-waveform-columns-f32le",
                "--width",
                str(int(width)),
                "--total",
                str(float(total_duration or 0.0)),
                "--vad-json",
                _vad_payload(vad_segments),
            ],
            input=wf.tobytes(),
            check=True,
            capture_output=True,
            timeout=10,
        )
        payload: dict[str, Any] = loads_json_output(proc.stdout, default={})
        heights = payload.get("heights") or []
        speech = payload.get("speech") or []
    except Exception:
        return None
    if len(heights) != int(width) or len(speech) != int(width):
        return None
    return [(max(1, int(h)), bool(s)) for h, s in zip(heights, speech)]


def _run_json_command(command: str, payload: dict[str, Any], *, timeout: float = 5.0) -> dict[str, Any] | None:
    if not _enabled():
        return None
    cli = find_native_cli_path()
    if cli is None:
        return None
    encode_ms = 0.0
    payload_bytes = 0
    started = time.perf_counter()
    decode_ms = 0.0
    ok = False
    try:
        encode_started = time.perf_counter()
        encoded = dumps_json_bytes(payload, compact=True)
        encode_ms = _elapsed_ms(encode_started)
        payload_bytes = len(encoded)
        proc = subprocess.run(
            [str(cli), command],
            input=encoded,
            check=True,
            capture_output=True,
            timeout=timeout,
        )
        decode_started = time.perf_counter()
        decoded = loads_json_output(proc.stdout, default={})
        decode_ms = _elapsed_ms(decode_started)
        ok = isinstance(decoded, dict)
    except Exception:
        return None
    finally:
        record_native_bridge_metric(
            f"timeline:{command}",
            payload_bytes=payload_bytes,
            encode_ms=encode_ms,
            native_ms=_elapsed_ms(started),
            decode_ms=decode_ms,
            ok=ok,
        )
    return decoded if isinstance(decoded, dict) else None


def _start_worker(cli: Any) -> subprocess.Popen | None:
    global _WORKER
    if _WORKER is not None and _WORKER.poll() is None:
        return _WORKER
    try:
        _WORKER = subprocess.Popen(
            [str(cli), "timeline-layout-jsonl-worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
    except Exception:
        _WORKER = None
    return _WORKER


def _request_worker(task: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _enabled():
        return None
    cli = find_native_cli_path()
    if cli is None:
        return None
    request = dict(payload)
    request["task"] = task
    encode_started = time.perf_counter()
    try:
        encoded = dumps_json_text(request, compact=True, default=json_default)
    except Exception:
        return None
    encode_ms = _elapsed_ms(encode_started)
    payload_bytes = len(encoded.encode("utf-8"))
    started = time.perf_counter()
    decode_ms = 0.0
    ok = False
    with _WORKER_LOCK:
        worker = _start_worker(cli)
        if worker is None or worker.stdin is None or worker.stdout is None:
            record_native_bridge_metric(
                f"timeline-jsonl:{task}",
                payload_bytes=payload_bytes,
                encode_ms=encode_ms,
                native_ms=_elapsed_ms(started),
                decode_ms=decode_ms,
                ok=False,
            )
            return None
        try:
            write_jsonl_line(worker.stdin, encoded)
            worker.stdin.flush()
            line = worker.stdout.readline()
            if not line:
                stop_timeline_layout_worker()
                return None
            decode_started = time.perf_counter()
            decoded = loads_json(line)
            decode_ms = _elapsed_ms(decode_started)
            if not isinstance(decoded, dict) or decoded.get("error"):
                return None
            ok = True
            return decoded
        except Exception:
            stop_timeline_layout_worker()
            return None
        finally:
            record_native_bridge_metric(
                f"timeline-jsonl:{task}",
                payload_bytes=payload_bytes,
                encode_ms=encode_ms,
                native_ms=_elapsed_ms(started),
                decode_ms=decode_ms,
                ok=ok,
            )


def build_segment_layout_via_swift(
    segments: list | tuple,
    *,
    view_start: float,
    view_end: float,
    width: int,
    top: int = 0,
    row_height: int = 22,
    lane_gap: int = 2,
    min_width: int = 2,
    pad_sec: float = 0.0,
    playhead_sec: float | None = None,
) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(segments or []):
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start", item.get("timeline_sec", item.get("time", 0.0))) or 0.0)
            end = float(item.get("end", item.get("timeline_end", start)) or start)
        except Exception:
            continue
        line = item.get("line", item.get("number", index))
        try:
            line_value: int | None = int(line) if line is not None else None
        except Exception:
            line_value = None
        lane = item.get("lane", item.get("track", 0))
        try:
            lane_value: int | None = int(lane) if lane is not None else None
        except Exception:
            lane_value = 0
        rows.append(
            {
                "id": str(item.get("id", line_value if line_value is not None else index)),
                "line": line_value,
                "start": start,
                "end": end,
                "lane": lane_value,
                "isGap": bool(item.get("is_gap", False)),
                "isPending": bool(item.get("stt_pending", False)),
            }
        )
    if not rows or int(width or 0) <= 0:
        return None
    payload: dict[str, Any] = {
        "segments": rows,
        "viewStart": float(view_start or 0.0),
        "viewEnd": float(view_end or view_start or 0.0),
        "width": int(width),
        "top": int(top),
        "rowHeight": int(row_height),
        "laneGap": int(lane_gap),
        "minWidth": int(min_width),
        "padSec": float(pad_sec or 0.0),
    }
    if playhead_sec is not None:
        payload["playheadSec"] = float(playhead_sec)
    decoded = _request_worker("segment_layout", payload)
    if decoded is not None:
        return decoded
    return _run_json_command("timeline-segment-layout-json", payload, timeout=5.0)


def playhead_dirty_rect_via_swift(
    *,
    old_sec: float | None,
    new_sec: float,
    view_start: float,
    view_end: float,
    width: int,
    height: int,
    extra_px: int = 12,
) -> dict[str, Any] | None:
    if int(width or 0) <= 0 or int(height or 0) <= 0:
        return None
    payload: dict[str, Any] = {
        "oldSec": None if old_sec is None else float(old_sec),
        "newSec": float(new_sec or 0.0),
        "viewStart": float(view_start or 0.0),
        "viewEnd": float(view_end or view_start or 0.0),
        "width": int(width),
        "height": int(height),
        "extraPx": int(extra_px),
    }
    decoded = _request_worker("playhead_dirty", payload)
    if decoded is not None:
        return decoded
    return _run_json_command("timeline-playhead-dirty-json", payload, timeout=2.0)


def apply_timing_drag_via_swift(
    *,
    edge: str,
    delta: float,
    original_start: float,
    original_end: float,
    min_value: float,
    max_value: float,
    frame_rate: float,
    snap_threshold: float,
    candidates: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        try:
            time_value = float(candidate.get("time", 0.0) or 0.0)
        except Exception:
            continue
        row: dict[str, Any] = {"time": time_value}
        kind = str(candidate.get("kind", "") or "")
        if kind:
            row["kind"] = kind
        try:
            row["threshold"] = max(0.0, float(candidate.get("threshold", snap_threshold) or snap_threshold))
        except Exception:
            row["threshold"] = max(0.0, float(snap_threshold or 0.0))
        rows.append(row)

    payload: dict[str, Any] = {
        "edge": str(edge or ""),
        "delta": float(delta or 0.0),
        "originalStart": float(original_start or 0.0),
        "originalEnd": float(original_end or 0.0),
        "minValue": float(min_value or 0.0),
        "maxValue": float(max_value or 0.0),
        "frameRate": float(frame_rate or 30.0),
        "snapThreshold": float(snap_threshold or 0.0),
        "candidates": rows,
    }
    decoded = _request_worker("timing_drag", payload)
    if decoded is not None:
        return decoded
    return _run_json_command("timeline-timing-drag-json", payload, timeout=2.0)


def compute_subtitle_merge_preview_via_swift(
    *,
    edge: str,
    current_start: float,
    current_end: float,
    previous_start: float | None,
    previous_end: float | None,
    next_start: float | None,
    next_end: float | None,
    frame_rate: float,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "edge": str(edge or ""),
        "currentStart": float(current_start or 0.0),
        "currentEnd": float(current_end or 0.0),
        "frameRate": float(frame_rate or 30.0),
    }
    if previous_start is not None:
        payload["previousStart"] = float(previous_start)
    if previous_end is not None:
        payload["previousEnd"] = float(previous_end)
    if next_start is not None:
        payload["nextStart"] = float(next_start)
    if next_end is not None:
        payload["nextEnd"] = float(next_end)
    decoded = _request_worker("merge_preview", payload)
    if decoded is not None:
        return decoded
    return _run_json_command("timeline-subtitle-merge-preview-json", payload, timeout=2.0)


def apply_subtitle_magnet_via_swift(
    *,
    segments: list | tuple,
    threshold_sec: float,
    boundary_times: list | tuple | None = None,
    provisional_boundaries: list | tuple | None = None,
    vad_segments: list | tuple | None = None,
    speaker_strict: bool = True,
    fps: float = 30.0,
    policy: dict[str, Any] | None = None,
    strategy: str = "extend_current",
) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(segments or []):
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start", 0.0) or 0.0)
            end = float(item.get("end", start) or start)
        except Exception:
            continue
        rows.append(
            {
                "line": int(item.get("line", index) or index),
                "start": start,
                "end": end,
                "text": str(item.get("text", "") or ""),
                "spk": str(item.get("spk", item.get("speaker", "")) or ""),
                "speaker": str(item.get("speaker", item.get("spk", "")) or ""),
                "isGap": bool(item.get("is_gap", False)),
                "startFrame": item.get("start_frame", item.get("timeline_start_frame")),
                "endFrame": item.get("end_frame", item.get("timeline_end_frame")),
                "timelineStartFrame": item.get("timeline_start_frame", item.get("start_frame")),
                "timelineEndFrame": item.get("timeline_end_frame", item.get("end_frame")),
            }
        )
    payload: dict[str, Any] = {
        "segments": rows,
        "thresholdSec": float(threshold_sec or 0.0),
        "boundaryTimes": [_boundary_time_value(value) for value in list(boundary_times or [])],
        "provisionalBoundaries": [_boundary_time_value(value) for value in list(provisional_boundaries or [])],
        "vadSegments": [
            {
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
            }
            for item in list(vad_segments or [])
            if isinstance(item, dict)
        ],
        "speakerStrict": bool(speaker_strict),
        "frameRate": float(fps or 30.0),
        "policy": dict(policy or {}),
        "strategy": str(strategy or "extend_current"),
    }
    decoded = _request_worker("subtitle_magnet", payload)
    if decoded is not None:
        return decoded
    return _run_json_command("timeline-subtitle-magnet-json", payload, timeout=3.0)


def capture_undo_snapshot_via_swift(
    *,
    blocks: list | tuple,
    segments: list | tuple,
    cursor_line: int,
    active_clip_idx: int,
    project_boundary_times: list | tuple | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "blocks": [
            {
                "text": str(text or ""),
                "speakerID": str((meta or {}).get("spk_id", "00") or "00"),
                "start": float((meta or {}).get("start_sec", 0.0) or 0.0),
                "end": (
                    None
                    if (meta or {}).get("end_sec") is None
                    else float((meta or {}).get("end_sec", 0.0) or 0.0)
                ),
                "isGap": bool((meta or {}).get("is_gap", False)),
            }
            for text, meta in list(blocks or [])
            if isinstance(meta, dict)
        ],
        "segments": [
            {
                "line": int(item.get("line", index) or index),
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
                "text": str(item.get("text", "") or ""),
                "speakerID": str(item.get("speaker", item.get("spk", "00")) or "00"),
                "isGap": bool(item.get("is_gap", False)),
            }
            for index, item in enumerate(list(segments or []))
            if isinstance(item, dict)
        ],
        "cursorLine": int(cursor_line or 0),
        "activeClipIndex": int(active_clip_idx or 0),
        "projectBoundaryTimes": [_boundary_time_value(value) for value in list(project_boundary_times or [])],
    }
    decoded = _request_worker("undo_snapshot", payload)
    if decoded is not None:
        return decoded
    return _run_json_command("timeline-undo-snapshot-json", payload, timeout=2.0)


def _editor_segment_row(item: dict[str, Any], index: int = 0) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    try:
        start, end = segment_display_time_bounds(item)
    except Exception:
        return None
    row: dict[str, Any] = {
        "line": int(item.get("line", index) or index),
        "start": start,
        "end": end,
        "text": str(item.get("text", "") or ""),
        "speaker": str(item.get("speaker", item.get("spk", "")) or ""),
        "spk": str(item.get("spk", item.get("speaker", "")) or ""),
        "isGap": bool(item.get("is_gap", False)),
    }
    for key, output_key in (
        ("stt_preview_source", "sttPreviewSource"),
        ("stt_source", "sttSource"),
        ("stt_selected_source", "sttSelectedSource"),
        ("stt_ensemble_source", "sttEnsembleSource"),
        ("stt_ensemble_llm_selected_source", "sttEnsembleLLMSelectedSource"),
        ("_clip_file", "clipFile"),
    ):
        value = item.get(key)
        if value not in (None, ""):
            row[output_key] = value
    for key, output_key in (
        ("score", "score"),
        ("stt_score", "sttScore"),
        ("_clip_idx", "clipIndex"),
        ("start_frame", "startFrame"),
        ("end_frame", "endFrame"),
        ("timeline_start_frame", "timelineStartFrame"),
        ("timeline_end_frame", "timelineEndFrame"),
    ):
        value = item.get(key)
        if value is not None:
            row[output_key] = value
    return row


def build_live_subtitle_preview_via_swift(
    *,
    preview_segments: list | tuple,
    confirmed_segments: list | tuple,
    fps: float = 30.0,
) -> list[dict[str, Any]] | None:
    payload: dict[str, Any] = {
        "previewSegments": [
            row
            for index, item in enumerate(list(preview_segments or []))
            if (row := _editor_segment_row(item, index)) is not None
        ],
        "confirmedSegments": [
            row
            for index, item in enumerate(list(confirmed_segments or []))
            if (row := _editor_segment_row(item, index)) is not None
        ],
        "frameRate": float(fps or 30.0),
    }
    decoded = _request_worker("live_subtitle_preview", payload)
    if decoded is None:
        decoded = _run_json_command("timeline-live-subtitle-preview-json", payload, timeout=2.0)
    rows = decoded.get("drafts") if isinstance(decoded, dict) else None
    return list(rows) if isinstance(rows, list) else None


def plan_stt_candidate_selection_via_swift(
    *,
    current_segments: list | tuple,
    live_preview_segments: list | tuple,
    candidate: dict[str, Any],
    fps: float = 30.0,
) -> dict[str, Any] | None:
    candidate_row = _editor_segment_row(candidate, 0)
    if candidate_row is None:
        return None
    payload: dict[str, Any] = {
        "currentSegments": [
            row
            for index, item in enumerate(list(current_segments or []))
            if (row := _editor_segment_row(item, index)) is not None
        ],
        "livePreviewSegments": [
            row
            for index, item in enumerate(list(live_preview_segments or []))
            if (row := _editor_segment_row(item, index)) is not None
        ],
        "candidate": candidate_row,
        "frameRate": float(fps or 30.0),
    }
    decoded = _request_worker("stt_candidate_selection", payload)
    if decoded is not None:
        return decoded
    return _run_json_command("timeline-stt-candidate-selection-json", payload, timeout=2.0)


def match_srt_project_metadata_via_swift(
    *,
    srt_segments: list | tuple,
    project_segments: list | tuple,
) -> list[int] | None:
    payload: dict[str, Any] = {
        "srtSegments": [
            {
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
                "text": str(item.get("text", "") or ""),
            }
            for item in list(srt_segments or [])
            if isinstance(item, dict)
        ],
        "projectSegments": [
            {
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
                "text": str(item.get("text", "") or ""),
            }
            for item in list(project_segments or [])
            if isinstance(item, dict)
        ],
    }
    decoded = _request_worker("srt_metadata_match", payload)
    if decoded is None:
        decoded = _run_json_command("timeline-srt-metadata-match-json", payload, timeout=2.0)
    rows = decoded.get("matches") if isinstance(decoded, dict) else None
    if not isinstance(rows, list):
        return None
    out: list[int] = []
    for value in rows:
        try:
            out.append(int(value))
        except Exception:
            out.append(-1)
    return out


def prepare_editor_segments_for_load_via_swift(
    *,
    segments: list | tuple,
    fps: float = 30.0,
) -> list[dict[str, Any]] | None:
    payload: dict[str, Any] = {
        "segments": [
            {
                "sourceIndex": int(index),
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
                "text": str(item.get("text", "") or ""),
                "isGap": bool(item.get("is_gap", False)),
            }
            for index, item in enumerate(list(segments or []))
            if isinstance(item, dict)
        ],
        "frameRate": float(fps or 30.0),
    }
    decoded = _request_worker("editor_load_prep", payload)
    if decoded is None:
        decoded = _run_json_command("timeline-editor-load-prep-json", payload, timeout=3.0)
    rows = decoded.get("segments") if isinstance(decoded, dict) else None
    return list(rows) if isinstance(rows, list) else None


def build_subtitle_drag_snap_base_via_swift(
    *,
    segments: list | tuple,
    gap_segments: list | tuple | None = None,
    vad_segments: list | tuple | None = None,
    voice_activity_segments: list | tuple | None = None,
    boundary_times: list | tuple | None = None,
    scan_boundary_times: list | tuple | None = None,
    user_guides: list | tuple | None = None,
    roughcut_ranges: list | tuple | None = None,
    total_duration: float = 0.0,
    fps: float = 30.0,
    include_gap_controls: bool = True,
) -> list[dict[str, Any]] | None:
    payload: dict[str, Any] = {
        "segments": [
            {
                "line": None if item.get("line") is None else int(item.get("line")),
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
                "isGap": bool(item.get("is_gap", False)),
                "sttPending": bool(item.get("stt_pending", False)),
                "liveSTTPreview": bool(item.get("_live_stt_preview", False)),
                "liveSubtitlePreview": bool(item.get("_live_subtitle_preview", False)),
            }
            for item in list(segments or [])
            if isinstance(item, dict)
        ],
        "gapSegments": [
            {
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
            }
            for item in list(gap_segments or [])
            if isinstance(item, dict)
        ],
        "vadSegments": [
            {
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
            }
            for item in list(vad_segments or [])
            if isinstance(item, dict)
        ],
        "voiceActivitySegments": [
            {
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
            }
            for item in list(voice_activity_segments or [])
            if isinstance(item, dict)
        ],
        "boundaryTimes": [_boundary_time_value(value) for value in list(boundary_times or [])],
        "scanBoundaryTimes": [_boundary_time_value(value) for value in list(scan_boundary_times or [])],
        "userGuides": [float(value or 0.0) for value in list(user_guides or [])],
        "roughcutRanges": [
            {
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
            }
            for item in list(roughcut_ranges or [])
            if isinstance(item, dict)
        ],
        "totalDuration": float(total_duration or 0.0),
        "frameRate": float(fps or 30.0),
        "includeGapControls": bool(include_gap_controls),
    }
    decoded = _request_worker("drag_snap_base", payload)
    if decoded is None:
        decoded = _run_json_command("timeline-drag-snap-base-json", payload, timeout=3.0)
    rows = decoded.get("candidates") if isinstance(decoded, dict) else None
    return list(rows) if isinstance(rows, list) else None


def plan_subtitle_timing_edit_via_swift(
    *,
    segments: list | tuple,
    line: int,
    new_start: float,
    new_end: float,
    edge: str,
    fps: float = 30.0,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "segments": [
            {
                "line": int(item.get("line", index) or index),
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0),
                "isGap": bool(item.get("is_gap", False)),
            }
            for index, item in enumerate(list(segments or []))
            if isinstance(item, dict)
        ],
        "line": int(line),
        "newStart": float(new_start or 0.0),
        "newEnd": float(new_end or 0.0),
        "edge": str(edge or ""),
        "frameRate": float(fps or 30.0),
    }
    decoded = _request_worker("segment_timing_edit_plan", payload)
    if decoded is not None:
        return decoded
    return _run_json_command("timeline-segment-timing-edit-plan-json", payload, timeout=3.0)


def stop_timeline_layout_worker() -> None:
    global _WORKER
    worker = _WORKER
    _WORKER = None
    if worker is None:
        return
    try:
        if worker.stdin is not None:
            worker.stdin.close()
    except Exception:
        pass
    try:
        worker.terminate()
    except Exception:
        pass


__all__ = [
    "build_waveform_columns_via_swift",
    "build_segment_layout_via_swift",
    "playhead_dirty_rect_via_swift",
    "apply_timing_drag_via_swift",
    "compute_subtitle_merge_preview_via_swift",
    "apply_subtitle_magnet_via_swift",
    "capture_undo_snapshot_via_swift",
    "build_live_subtitle_preview_via_swift",
    "plan_stt_candidate_selection_via_swift",
    "match_srt_project_metadata_via_swift",
    "prepare_editor_segments_for_load_via_swift",
    "build_subtitle_drag_snap_base_via_swift",
    "plan_subtitle_timing_edit_via_swift",
    "stop_timeline_layout_worker",
]


atexit.register(stop_timeline_layout_worker)
