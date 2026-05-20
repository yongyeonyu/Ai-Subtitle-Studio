from __future__ import annotations

import atexit
import subprocess
import threading
import time
from typing import Any

from core.native_json import dumps_json_text, json_default, loads_json, loads_json_output, write_jsonl_line
from core.native_swift_subtitle import find_native_cli_path
from core.runtime.config import IS_MAC
from core.runtime.stage_metrics import _elapsed_ms, record_native_bridge_metric
from core.runtime.setting_utils import KOREAN_FALSE_VALUES, env_bool as _env_bool, positive_int as _positive_int, setting_bool as _setting_bool

_WORKER: subprocess.Popen | None = None
_WORKER_LOCK = threading.Lock()


def _enabled(settings: dict[str, Any] | None, item_count: int) -> bool:
    if not IS_MAC:
        return False
    env = _env_bool("AI_SUBTITLE_STUDIO_SWIFT_QUALITY")
    if env is not None:
        return env
    data = dict(settings or {})
    if not _setting_bool(data.get("mac_native_acceleration_enabled"), True, false_values=KOREAN_FALSE_VALUES):
        return False
    if not _setting_bool(data.get("native_swift_quality_scoring_enabled"), True, false_values=KOREAN_FALSE_VALUES):
        return False
    if _setting_bool(data.get("native_swift_quality_scoring_force_enabled"), False, false_values=KOREAN_FALSE_VALUES):
        return True
    min_segments = _positive_int(data.get("native_swift_quality_scoring_min_segments"), 64)
    return int(item_count or 0) >= min_segments


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
    encode_started = time.perf_counter()
    try:
        payload = dumps_json_text(
            {"segments": segments, "settings": settings or {}},
            compact=True,
            default=json_default,
        )
    except Exception:
        return None
    encode_ms = _elapsed_ms(encode_started)
    payload_bytes = len(payload.encode("utf-8"))

    decoded = _request_worker(cli, payload, payload_bytes=payload_bytes, encode_ms=encode_ms)
    if decoded is None:
        decoded = _request_one_shot(cli, payload, len(segments), payload_bytes=payload_bytes, encode_ms=encode_ms)
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


def _request_worker(cli: Any, payload: str, *, payload_bytes: int = 0, encode_ms: float = 0.0) -> dict[str, Any] | None:
    started = time.perf_counter()
    decode_ms = 0.0
    ok = False
    with _WORKER_LOCK:
        worker = _start_worker(cli)
        if worker is None or worker.stdin is None or worker.stdout is None:
            record_native_bridge_metric(
                "quality-score-jsonl-worker",
                payload_bytes=payload_bytes,
                encode_ms=encode_ms,
                native_ms=_elapsed_ms(started),
                decode_ms=decode_ms,
                ok=False,
            )
            return None
        try:
            write_jsonl_line(worker.stdin, payload)
            worker.stdin.flush()
            line = worker.stdout.readline()
            if not line:
                _stop_worker()
                return None
            decode_started = time.perf_counter()
            decoded = loads_json(line)
            decode_ms = _elapsed_ms(decode_started)
            if decoded.get("error"):
                return None
            ok = True
            return decoded
        except Exception:
            _stop_worker()
            return None
        finally:
            record_native_bridge_metric(
                "quality-score-jsonl-worker",
                payload_bytes=payload_bytes,
                encode_ms=encode_ms,
                native_ms=_elapsed_ms(started),
                decode_ms=decode_ms,
                ok=ok,
            )


def _request_one_shot(
    cli: Any,
    payload: str,
    count: int,
    *,
    payload_bytes: int = 0,
    encode_ms: float = 0.0,
) -> dict[str, Any] | None:
    started = time.perf_counter()
    decode_ms = 0.0
    ok = False
    try:
        proc = subprocess.run(
            [str(cli), "quality-score-json"],
            input=payload.encode("utf-8"),
            check=True,
            capture_output=True,
            timeout=max(10.0, min(90.0, 2.0 + count * 0.02)),
        )
        decode_started = time.perf_counter()
        decoded = loads_json_output(proc.stdout, default={})
        decode_ms = _elapsed_ms(decode_started)
        ok = True
        return decoded
    except Exception:
        return None
    finally:
        record_native_bridge_metric(
            "quality-score-json",
            payload_bytes=payload_bytes,
            encode_ms=encode_ms,
            native_ms=_elapsed_ms(started),
            decode_ms=decode_ms,
            ok=ok,
        )


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
