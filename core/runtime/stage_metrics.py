from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_MAX_EVENTS = 240
_LOCK = threading.Lock()
_EVENTS: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
_STAGES: dict[str, dict[str, Any]] = {}
_RESOURCES: dict[str, dict[str, Any]] = {}
_COUNTER = 0


def _now_ms() -> int:
    return int(time.time() * 1000)


def _elapsed_ms(started: float) -> float:
    return round(max(0.0, time.perf_counter() - started) * 1000.0, 3)


def classify_resource_label(stage: str, fallback: str = "general") -> str:
    text = str(stage or "").strip().lower()
    if not text:
        return fallback
    checks = (
        ("stt1", ("stt1", "stt_transcribe", "whisperkit", "word", "단어")),
        ("stt2", ("stt2", "fast-stt2", "mlx", "komix", "재검사")),
        ("vad", ("vad", "silero", "음성 위치")),
        ("subtitle_optimize", ("subtitle_optimize", "subtitle optimize", "optimizer", "자막 최적화", "교정/분리")),
        ("llm", ("llm", "lora", "러프컷", "roughcut", "자막 최적화")),
        ("cut", ("cut", "boundary", "컷 경계")),
        ("score", ("score", "quality", "검수", "자가진단", "scoring")),
        ("save", ("save", "export", "저장", "내보내기")),
        ("render", ("render", "paint", "timeline", "waveform", "playhead", "렌더")),
        ("native", ("native", "swift", "bridge")),
        ("automation", ("app_command", "automation", "guided-subtitle", "ping", "status")),
        ("memory", ("memory", "trim", "checkpoint", "메모리")),
        ("audio", ("audio", "ffmpeg", "clearvoice", "오디오", "음성 향상")),
    )
    for label, tokens in checks:
        if any(token in text for token in tokens):
            return label
    return fallback


def record_stage_event(
    stage: str,
    *,
    event: str,
    resource_label: str | None = None,
    wait_ms: float | None = None,
    worker_busy_ms: float | None = None,
    worker_idle_ms: float | None = None,
    queue_depth: int | None = None,
    ok: bool | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    global _COUNTER
    stage_key = str(stage or "unknown").strip() or "unknown"
    event_name = str(event or "stage_event").strip() or "stage_event"
    label = str(resource_label or classify_resource_label(stage_key)).strip() or "general"
    row: dict[str, Any] = {
        "sequence": 0,
        "captured_at_ms": _now_ms(),
        "stage": stage_key,
        "event": event_name,
        "resource_label": label,
    }
    if wait_ms is not None:
        row["stage_wait_ms"] = round(max(0.0, float(wait_ms)), 3)
    if worker_busy_ms is not None:
        row["worker_busy_ms"] = round(max(0.0, float(worker_busy_ms)), 3)
    if worker_idle_ms is not None:
        row["worker_idle_ms"] = round(max(0.0, float(worker_idle_ms)), 3)
    if queue_depth is not None:
        row["queue_depth"] = max(0, int(queue_depth))
    if ok is not None:
        row["ok"] = bool(ok)
    if isinstance(metrics, dict) and metrics:
        row["metrics"] = dict(metrics)

    with _LOCK:
        _COUNTER += 1
        row["sequence"] = _COUNTER
        _EVENTS.append(dict(row))
        _merge_bucket(_STAGES, stage_key, row)
        _merge_bucket(_RESOURCES, label, row)
    return dict(row)


def _merge_bucket(target: dict[str, dict[str, Any]], key: str, row: dict[str, Any]) -> None:
    bucket = dict(target.get(key) or {})
    bucket["last_event"] = row["event"]
    bucket["last_stage"] = row["stage"]
    bucket["last_sequence"] = int(row["sequence"])
    bucket["last_at_ms"] = int(row["captured_at_ms"])
    bucket["event_count"] = int(bucket.get("event_count", 0) or 0) + 1
    event_counter_key = f"{row['event']}_count"
    bucket[event_counter_key] = int(bucket.get(event_counter_key, 0) or 0) + 1
    if "stage_wait_ms" in row:
        bucket["total_stage_wait_ms"] = round(float(bucket.get("total_stage_wait_ms", 0.0) or 0.0) + float(row["stage_wait_ms"]), 3)
    if "worker_busy_ms" in row:
        bucket["total_worker_busy_ms"] = round(float(bucket.get("total_worker_busy_ms", 0.0) or 0.0) + float(row["worker_busy_ms"]), 3)
    if "worker_idle_ms" in row:
        bucket["total_worker_idle_ms"] = round(float(bucket.get("total_worker_idle_ms", 0.0) or 0.0) + float(row["worker_idle_ms"]), 3)
    if "queue_depth" in row:
        bucket["max_queue_depth"] = max(int(bucket.get("max_queue_depth", 0) or 0), int(row["queue_depth"]))
        bucket["last_queue_depth"] = int(row["queue_depth"])
    if "ok" in row and not bool(row["ok"]):
        bucket["failure_count"] = int(bucket.get("failure_count", 0) or 0) + 1
    metrics = row.get("metrics")
    if isinstance(metrics, dict):
        native = dict(bucket.get("native_bridge") or {})
        for name in ("payload_bytes", "encode_ms", "native_ms", "decode_ms"):
            if name not in metrics:
                continue
            value = float(metrics.get(name, 0.0) or 0.0)
            if name == "payload_bytes":
                native["total_payload_bytes"] = int(native.get("total_payload_bytes", 0) or 0) + int(value)
            else:
                native[f"total_{name}"] = round(float(native.get(f"total_{name}", 0.0) or 0.0) + value, 3)
        if native:
            bucket["native_bridge"] = native
    target[key] = bucket


def record_stage_ready(stage: str, **kwargs: Any) -> dict[str, Any]:
    return record_stage_event(stage, event="stage_ready", **kwargs)


def record_stage_start(stage: str, **kwargs: Any) -> dict[str, Any]:
    return record_stage_event(stage, event="stage_start", **kwargs)


def record_stage_done(stage: str, **kwargs: Any) -> dict[str, Any]:
    return record_stage_event(stage, event="stage_done", **kwargs)


def record_native_bridge_metric(
    name: str,
    *,
    payload_bytes: int = 0,
    encode_ms: float = 0.0,
    native_ms: float = 0.0,
    decode_ms: float = 0.0,
    ok: bool = True,
) -> dict[str, Any]:
    return record_stage_done(
        f"native:{name}",
        resource_label="native",
        ok=ok,
        metrics={
            "payload_bytes": max(0, int(payload_bytes or 0)),
            "encode_ms": round(max(0.0, float(encode_ms or 0.0)), 3),
            "native_ms": round(max(0.0, float(native_ms or 0.0)), 3),
            "decode_ms": round(max(0.0, float(decode_ms or 0.0)), 3),
        },
    )


def snapshot_stage_metrics(*, max_events: int = 50, include_stages: bool = True) -> dict[str, Any]:
    with _LOCK:
        events = list(_EVENTS)[-max(0, int(max_events or 0)):]
        stages = {key: dict(value) for key, value in _STAGES.items()}
        resources = {key: dict(value) for key, value in _RESOURCES.items()}
        event_count = int(_COUNTER)
    active_cutoff_ms = _now_ms() - 10_000
    active_resources = sorted(
        key for key, value in resources.items()
        if int(value.get("last_at_ms", 0) or 0) >= active_cutoff_ms
    )
    payload = {
        "schema": "ai_subtitle_studio.stage_metrics.v1",
        "event_count": event_count,
        "stage_count": len(stages),
        "resource_count": len(resources),
        "active_resources": active_resources,
        "recent_events": [dict(item) for item in events],
        "resources": resources,
    }
    if include_stages:
        payload["stages"] = stages
    return payload


def reset_stage_metrics() -> None:
    global _COUNTER
    with _LOCK:
        _EVENTS.clear()
        _STAGES.clear()
        _RESOURCES.clear()
        _COUNTER = 0


__all__ = [
    "_elapsed_ms",
    "classify_resource_label",
    "record_native_bridge_metric",
    "record_stage_done",
    "record_stage_event",
    "record_stage_ready",
    "record_stage_start",
    "reset_stage_metrics",
    "snapshot_stage_metrics",
]
