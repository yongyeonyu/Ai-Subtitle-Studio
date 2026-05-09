from __future__ import annotations

import atexit
import json
import os
import subprocess
import threading
from typing import Any

from core.native_swift_subtitle import find_native_cli_path

_WORKER: subprocess.Popen | None = None
_WORKER_LOCK = threading.Lock()


def _enabled() -> bool:
    value = os.environ.get("AI_SUBTITLE_STUDIO_SWIFT_QUALITY", "").lower()
    if value in {"0", "false", "off", "no"}:
        return False
    return value in {"1", "true", "on", "yes"}


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
    if not _enabled() or not segments:
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
