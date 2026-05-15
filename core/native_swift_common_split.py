from __future__ import annotations

import atexit
import subprocess
import threading
from typing import Any

from core.native_json import dumps_json_text, json_default, loads_json, loads_json_output, write_jsonl_line
from core.native_swift_subtitle import find_native_cli_path
from core.runtime.config import IS_MAC
from core.runtime.setting_utils import KOREAN_FALSE_VALUES, env_bool as _env_bool, positive_int as _positive_int, setting_bool as _setting_bool

_WORKER: subprocess.Popen | None = None
_WORKER_LOCK = threading.Lock()


def _enabled(item_count: int, settings: dict[str, Any] | None = None) -> bool:
    if not IS_MAC:
        return False
    env = _env_bool("AI_SUBTITLE_STUDIO_SWIFT_COMMON_SPLIT")
    if env is not None:
        return env
    data = dict(settings or {})
    if not _setting_bool(data.get("mac_native_acceleration_enabled"), True, false_values=KOREAN_FALSE_VALUES):
        return False
    if not _setting_bool(data.get("native_swift_common_split_enabled"), True, false_values=KOREAN_FALSE_VALUES):
        return False
    if _setting_bool(data.get("native_swift_common_split_force_enabled"), False, false_values=KOREAN_FALSE_VALUES):
        return True
    # Benchmarks show the persistent Swift planner becomes useful on larger
    # batches, while small batches are already faster in Python. Keep packaged
    # macOS builds adaptive instead of forcing a slower native hop.
    min_items = _positive_int(data.get("native_swift_common_split_min_items"), 1_000)
    return int(item_count or 0) >= min_items


def plan_common_split_via_swift(
    items: list[dict[str, Any]],
    *,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    if not items or not _enabled(len(items), settings):
        return None
    cli = find_native_cli_path()
    if cli is None:
        return None
    try:
        payload = dumps_json_text(
            {"segments": items},
            compact=True,
            default=json_default,
        )
    except Exception:
        return None
    decoded = _request_worker(cli, payload)
    if decoded is None:
        decoded = _request_one_shot(cli, payload, len(items))
    if decoded is None:
        return None
    plans = decoded.get("plans") or []
    if len(plans) != len(items):
        return None
    return [dict(plan) for plan in plans if isinstance(plan, dict)]


def _start_worker(cli: Any) -> subprocess.Popen | None:
    global _WORKER
    if _WORKER is not None and _WORKER.poll() is None:
        return _WORKER
    try:
        _WORKER = subprocess.Popen(
            [str(cli), "common-split-plan-jsonl-worker"],
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
            write_jsonl_line(worker.stdin, payload)
            worker.stdin.flush()
            line = worker.stdout.readline()
            if not line:
                _stop_worker()
                return None
            decoded = loads_json(line)
            if decoded.get("error"):
                return None
            return decoded
        except Exception:
            _stop_worker()
            return None


def _request_one_shot(cli: Any, payload: str, count: int) -> dict[str, Any] | None:
    try:
        proc = subprocess.run(
            [str(cli), "common-split-plan-json"],
            input=payload.encode("utf-8"),
            check=True,
            capture_output=True,
            timeout=max(10.0, min(90.0, 2.0 + count * 0.02)),
        )
        return loads_json_output(proc.stdout, default={})
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

__all__ = ["plan_common_split_via_swift"]
