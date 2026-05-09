from __future__ import annotations

import atexit
import json
import os
import subprocess
import threading
from typing import Any

from core.native_swift_subtitle import find_native_cli_path
from core.runtime.config import IS_MAC

_WORKER: subprocess.Popen | None = None
_WORKER_LOCK = threading.Lock()


def _setting_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"0", "false", "off", "no", "사용 안함", "끔"}:
        return False
    if normalized in {"1", "true", "on", "yes", "사용", "켬"}:
        return True
    return bool(default)


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(float(value))
    except Exception:
        parsed = int(default)
    return parsed if parsed > 0 else int(default)


def _env_bool(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    normalized = value.strip().casefold()
    if normalized in {"0", "false", "off", "no"}:
        return False
    if normalized in {"1", "true", "on", "yes"}:
        return True
    return None


def _enabled(settings: dict[str, Any] | None, item_count: int) -> bool:
    if not IS_MAC:
        return False
    env = _env_bool("AI_SUBTITLE_STUDIO_SWIFT_QUALITY")
    if env is not None:
        return env
    data = dict(settings or {})
    if not _setting_bool(data.get("mac_native_acceleration_enabled"), True):
        return False
    if not _setting_bool(data.get("native_swift_quality_scoring_enabled"), True):
        return False
    if _setting_bool(data.get("native_swift_quality_scoring_force_enabled"), False):
        return True
    min_segments = _positive_int(data.get("native_swift_quality_scoring_min_segments"), 64)
    return int(item_count or 0) >= min_segments


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


def evaluate_quality_batch_via_swift(
    segments: list[dict[str, Any]],
    *,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    if not segments or not _enabled(settings, len(segments)):
        return None
    cli = find_native_cli_path()
    if cli is None:
        return None
    try:
        payload = json.dumps(
            {"segments": segments, "settings": settings or {}},
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        )
    except Exception:
        return None

    decoded = _request_worker(cli, payload)
    if decoded is None:
        decoded = _request_one_shot(cli, payload, len(segments))
    if decoded is None:
        return None

    metrics = decoded.get("metrics") or []
    if len(metrics) != len(segments):
        return None
    out: list[dict[str, Any]] = []
    for item in metrics:
        if not isinstance(item, dict):
            return None
        flags = item.get("flags")
        if isinstance(flags, list):
            item["flags"] = tuple(str(flag) for flag in flags if flag)
        out.append(item)
    return out


def _start_worker(cli: Any) -> subprocess.Popen | None:
    global _WORKER
    if _WORKER is not None and _WORKER.poll() is None:
        return _WORKER
    try:
        _WORKER = subprocess.Popen(
            [str(cli), "quality-score-jsonl-worker"],
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


def _request_worker(cli: Any, payload: str) -> dict[str, Any] | None:
    with _WORKER_LOCK:
        worker = _start_worker(cli)
        if worker is None or worker.stdin is None or worker.stdout is None:
            return None
        try:
            worker.stdin.write(payload.replace("\n", " ") + "\n")
            worker.stdin.flush()
            line = worker.stdout.readline()
            if not line:
                _stop_worker()
                return None
            decoded = json.loads(line)
            if decoded.get("error"):
                return None
            return decoded
        except Exception:
            _stop_worker()
            return None


def _request_one_shot(cli: Any, payload: str, count: int) -> dict[str, Any] | None:
    try:
        proc = subprocess.run(
            [str(cli), "quality-score-json"],
            input=payload.encode("utf-8"),
            check=True,
            capture_output=True,
            timeout=max(10.0, min(90.0, 2.0 + count * 0.02)),
        )
        return json.loads(proc.stdout.decode("utf-8") or "{}")
    except Exception:
        return None


def _stop_worker() -> None:
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


atexit.register(_stop_worker)


__all__ = ["evaluate_quality_batch_via_swift"]
