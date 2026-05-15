from __future__ import annotations

import atexit
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from core.native_json import dumps_json_text, json_default, loads_json, write_jsonl_line

_CORE_WORKER: subprocess.Popen | None = None
_CORE_WORKER_LOCK = threading.Lock()
_TRUE_VALUES = {"1", "true", "on", "yes"}
_FALSE_VALUES = {"0", "false", "off", "no"}


def _candidate_cli_paths() -> list[Path]:
    paths: list[Path] = []
    env_path = os.environ.get("AI_SUBTITLE_STUDIO_NATIVE_CLI")
    if env_path:
        paths.append(Path(env_path))

    bundle_resources = os.environ.get("AI_SUBTITLE_STUDIO_BUNDLE_RESOURCES")
    if bundle_resources:
        paths.append(Path(bundle_resources) / "native" / "AIStudioNativeCLI")

    root = Path(__file__).resolve().parents[1]
    for base in (root, root.parent):
        build_root = base / "native" / "macos" / "AIStudioNative" / ".build"
        paths.append(build_root / "release" / "AIStudioNativeCLI")
        paths.append(build_root / "debug" / "AIStudioNativeCLI")
    return paths


def find_native_cli_path() -> Path | None:
    candidates = _candidate_cli_paths()
    for path in candidates[:2]:
        if path.exists() and os.access(path, os.X_OK):
            return path
    built = [path for path in candidates[2:] if path.exists() and os.access(path, os.X_OK)]
    if built:
        return max(built, key=lambda item: item.stat().st_mtime_ns)
    return None


def native_cli_path() -> Path | None:
    if not native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_CORE"):
        return None
    return find_native_cli_path()


def _env_state(name: str) -> bool | None:
    value = str(os.environ.get(name, "") or "").strip().lower()
    if value in _FALSE_VALUES:
        return False
    if value in _TRUE_VALUES:
        return True
    return None


def native_swift_runtime_enabled(feature_env: str | None = None, *, default_on_macos: bool = True) -> bool:
    """Return whether Swift-native acceleration should be attempted.

    This branch is macOS-only in practice, so native Swift is the default when
    running on macOS. Explicit environment flags still win, which keeps tests,
    fallback diagnosis, and emergency disable switches simple.
    """

    core_state = _env_state("AI_SUBTITLE_STUDIO_SWIFT_CORE")
    if core_state is False:
        return False
    if feature_env and feature_env != "AI_SUBTITLE_STUDIO_SWIFT_CORE":
        feature_state = _env_state(feature_env)
        if feature_state is not None:
            return feature_state
    if core_state is True:
        return True
    if os.environ.get("AI_SUBTITLE_STUDIO_BUNDLE_RESOURCES"):
        return True
    return bool(default_on_macos and sys.platform == "darwin")

def _start_core_worker(cli: Path) -> subprocess.Popen | None:
    global _CORE_WORKER
    if _CORE_WORKER is not None and _CORE_WORKER.poll() is None:
        return _CORE_WORKER
    try:
        _CORE_WORKER = subprocess.Popen(
            [str(cli), "core-jsonl-worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
    except Exception:
        _CORE_WORKER = None
    return _CORE_WORKER


def stop_native_core_worker() -> None:
    global _CORE_WORKER
    worker = _CORE_WORKER
    _CORE_WORKER = None
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


def request_native_core_task(task: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    cli = find_native_cli_path()
    if cli is None:
        return None
    request = dict(payload)
    request["task"] = task
    try:
        encoded = dumps_json_text(request, compact=True, default=json_default)
    except Exception:
        return None
    with _CORE_WORKER_LOCK:
        worker = _start_core_worker(cli)
        if worker is None or worker.stdin is None or worker.stdout is None:
            return None
        try:
            write_jsonl_line(worker.stdin, encoded)
            worker.stdin.flush()
            line = worker.stdout.readline()
            if not line:
                stop_native_core_worker()
                return None
            decoded = loads_json(line)
            if not isinstance(decoded, dict) or decoded.get("error"):
                return None
            return decoded
        except Exception:
            stop_native_core_worker()
            return None


def parse_srt_via_swift(srt_path: str) -> list[dict[str, Any]] | None:
    cli = native_cli_path()
    if cli is None:
        return None
    decoded = request_native_core_task("srt_to_json", {"path": srt_path})
    rows = decoded.get("segments") if isinstance(decoded, dict) else None
    if rows is None:
        try:
            proc = subprocess.run(
                [str(cli), "srt-to-json", srt_path],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
            rows = loads_json(proc.stdout or "[]")
        except Exception:
            return None
    if not isinstance(rows, list):
        return None

    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text", "") or "").strip()
        if not text:
            continue
        try:
            start = float(row.get("start", 0.0) or 0.0)
            end = float(row.get("end", 0.0) or 0.0)
        except Exception:
            continue
        out.append(
            {
                "start": start,
                "end": end,
                "text": text,
                "is_gap": bool(row.get("is_gap", False)),
            }
        )
    return out


atexit.register(stop_native_core_worker)


__all__ = [
    "find_native_cli_path",
    "native_cli_path",
    "native_swift_runtime_enabled",
    "parse_srt_via_swift",
    "request_native_core_task",
    "stop_native_core_worker",
]
