from __future__ import annotations

import atexit
import json
import os
import subprocess
import threading
from typing import Any

import numpy as np

from core.native_swift_subtitle import find_native_cli_path

_WORKER: subprocess.Popen | None = None
_WORKER_LOCK = threading.Lock()


def _enabled() -> bool:
    value = os.environ.get("AI_SUBTITLE_STUDIO_SWIFT_TIMELINE", "").lower()
    if value in {"0", "false", "off", "no"}:
        return False
    return value in {"1", "true", "on", "yes"} or bool(os.environ.get("AI_SUBTITLE_STUDIO_BUNDLE_RESOURCES"))


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
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


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
        payload: dict[str, Any] = json.loads(proc.stdout.decode("utf-8") or "{}")
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
    try:
        proc = subprocess.run(
            [str(cli), command],
            input=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            check=True,
            capture_output=True,
            timeout=timeout,
        )
        decoded = json.loads(proc.stdout.decode("utf-8") or "{}")
    except Exception:
        return None
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
    try:
        encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":"), default=_json_default)
    except Exception:
        return None
    with _WORKER_LOCK:
        worker = _start_worker(cli)
        if worker is None or worker.stdin is None or worker.stdout is None:
            return None
        try:
            worker.stdin.write(encoded.replace("\n", " ") + "\n")
            worker.stdin.flush()
            line = worker.stdout.readline()
            if not line:
                stop_timeline_layout_worker()
                return None
            decoded = json.loads(line)
            if not isinstance(decoded, dict) or decoded.get("error"):
                return None
            return decoded
        except Exception:
            stop_timeline_layout_worker()
            return None


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


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
    "stop_timeline_layout_worker",
]


atexit.register(stop_timeline_layout_worker)
