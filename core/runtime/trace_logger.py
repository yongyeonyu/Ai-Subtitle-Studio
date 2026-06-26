from __future__ import annotations

import hashlib
import os
import platform
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

from core.native_json import dumps_json_bytes
from core.runtime import config
from core.runtime.json_utils import json_safe
from core.runtime.memory_manager import process_rss_bytes
from core.runtime.temp_workspace import ensure_temp_workspace, temp_workspace_root, workspace_usage

TRACE_SCHEMA = "ai_subtitle_studio.trace.v1"
TRACE_MANIFEST_SCHEMA = "ai_subtitle_studio.trace_manifest.v1"
_APP_TRACE_LOGGER: "TraceLogger | None" = None
_APP_TRACE_LOCK = threading.Lock()
_STOP_WRITER = object()


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _short_hash(text: str, *, length: int = 16) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8", errors="replace")).hexdigest()[:length]


def _settings_hash(settings: Any) -> str:
    if settings in (None, "", {}, []):
        return ""
    try:
        payload = dumps_json_bytes(json_safe(settings), sort_keys=True, compact=True)
    except Exception:
        payload = str(settings).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()[:24]


def _git_metadata() -> dict[str, Any]:
    root = Path(getattr(config, "BASE_DIR", "") or ".")

    def _run(args: list[str]) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=0.35,
        )
        return str(proc.stdout or "").strip()

    try:
        commit = _run(["rev-parse", "--short=12", "HEAD"])
    except Exception:
        commit = ""
    try:
        dirty = bool(_run(["status", "--porcelain"]))
    except Exception:
        dirty = False
    return {"commit": commit, "dirty": dirty}


def fps_parts(
    fps: Any = None,
    *,
    fps_num: Any = None,
    fps_den: Any = None,
) -> tuple[int, int]:
    try:
        num = int(fps_num)
        den = int(fps_den)
        if num > 0 and den > 0:
            return num, den
    except Exception:
        pass
    try:
        value = float(fps)
        if value > 0:
            ratio = Fraction(value).limit_denominator(100000)
            return int(ratio.numerator), int(ratio.denominator)
    except Exception:
        pass
    return 0, 0


def media_fingerprint(
    media_path: str | Path | None,
    *,
    duration_sec: Any = None,
    frame_count: Any = None,
    fps: Any = None,
    fps_num: Any = None,
    fps_den: Any = None,
) -> dict[str, Any]:
    path_text = str(media_path or "")
    path = Path(path_text).expanduser() if path_text else None
    stat_size = 0
    stat_mtime_ns = 0
    exists = False
    if path is not None:
        try:
            stat = path.stat()
            stat_size = max(0, int(stat.st_size or 0))
            stat_mtime_ns = int(stat.st_mtime_ns or 0)
            exists = True
        except OSError:
            exists = False
    num, den = fps_parts(fps, fps_num=fps_num, fps_den=fps_den)
    return {
        "basename": path.name if path is not None else "",
        "path_hash": _short_hash(str(path.resolve()) if path is not None and exists else path_text),
        "exists": exists,
        "size": stat_size,
        "mtime_ns": stat_mtime_ns,
        "duration_sec": float(duration_sec or 0.0) if duration_sec not in (None, "") else 0.0,
        "frame_count": int(frame_count or 0) if frame_count not in (None, "") else 0,
        "fps": float(fps or 0.0) if fps not in (None, "") else 0.0,
        "fps_num": num,
        "fps_den": den,
    }


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_bytes(path, dumps_json_bytes(json_safe(payload), sort_keys=True, append_newline=True))


def _atomic_write_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_bytes(path, dumps_json_bytes(json_safe(payload), sort_keys=True) + b"\n")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(dumps_json_bytes(json_safe(payload), sort_keys=True))
        handle.write(b"\n")
        handle.flush()


class TraceLogger:
    def __init__(
        self,
        *,
        root: str | Path | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        media_path: str | Path | None = None,
        media_duration_sec: Any = None,
        media_frame_count: Any = None,
        fps: Any = None,
        fps_num: Any = None,
        fps_den: Any = None,
        mode_settings: Any = None,
        settings_snapshot: Any = None,
        project_id: str = "",
        max_events: int = 100000,
    ) -> None:
        self.root = temp_workspace_root(root)
        self.trace_dir = self.root / "Diagnostics" / "Trace"
        self.runs_dir = self.trace_dir / "runs"
        self.latest_path = self.trace_dir / "latest.jsonl"
        self.run_id = self._unique_run_id(str(run_id or ""))
        self.session_id = str(session_id or uuid.uuid4())
        self.run_dir = self.runs_dir / self.run_id
        self.events_path = self.run_dir / "events.jsonl"
        self.manifest_path = self.run_dir / "manifest.json"
        self.project_id = str(project_id or "")
        self.max_events = max(1, int(max_events or 1))
        self._lock = threading.RLock()
        self._queue: "queue.Queue[dict[str, Any] | object]" = queue.Queue(maxsize=self.max_events)
        self._writer = threading.Thread(
            target=self._writer_loop,
            name=f"AISSTraceWriter-{self.run_id}",
            daemon=True,
        )
        self._seq = 0
        self._event_count = 0
        self._disabled = False
        self._drop_counts: dict[str, int] = {}
        self._last_error = ""
        self.started_ts = _utc_now_text()
        self.manifest = self._build_manifest(
            media_path=media_path,
            media_duration_sec=media_duration_sec,
            media_frame_count=media_frame_count,
            fps=fps,
            fps_num=fps_num,
            fps_den=fps_den,
            mode_settings=mode_settings,
            settings_snapshot=settings_snapshot,
        )
        try:
            ensure_temp_workspace(self.root)
            self.run_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(self.manifest_path, self.manifest)
        except Exception as exc:
            self._disable("manifest_write_failed", exc)
            return
        self._writer.start()
        self.log_event(
            "trace_run_started",
            stage="runtime",
            level="INFO",
            media_id=self.manifest.get("media_fingerprint", {}).get("path_hash", ""),
            project_id=self.project_id,
        )
        self.flush(timeout_sec=1.0)

    def _unique_run_id(self, requested: str) -> str:
        base = requested.strip() or datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        candidate = base
        suffix = 1
        while (self.runs_dir / candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    def _build_manifest(
        self,
        *,
        media_path: str | Path | None,
        media_duration_sec: Any,
        media_frame_count: Any,
        fps: Any,
        fps_num: Any,
        fps_den: Any,
        mode_settings: Any,
        settings_snapshot: Any,
    ) -> dict[str, Any]:
        git = _git_metadata()
        mode_payload = mode_settings if mode_settings not in (None, "", {}, []) else settings_snapshot
        return {
            "schema": TRACE_MANIFEST_SCHEMA,
            "app_name": getattr(config, "APP_NAME", "AI Subtitle Studio"),
            "app_version": getattr(config, "APP_VERSION", ""),
            "git_commit": git.get("commit", ""),
            "git_dirty": bool(git.get("dirty", False)),
            "python_version": platform.python_version(),
            "macos_version": platform.mac_ver()[0],
            "machine": platform.machine(),
            "pid": os.getpid(),
            "started": self.started_ts,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "media_fingerprint": media_fingerprint(
                media_path,
                duration_sec=media_duration_sec,
                frame_count=media_frame_count,
                fps=fps,
                fps_num=fps_num,
                fps_den=fps_den,
            ),
            "mode_settings_snapshot_hash": _settings_hash(mode_payload),
            "workspace_usage": workspace_usage(self.root),
        }

    def _disable(self, reason: str, exc: BaseException | None = None) -> None:
        self._disabled = True
        self._drop_counts[reason] = self._drop_counts.get(reason, 0) + 1
        if exc is not None:
            self._last_error = f"{type(exc).__name__}: {exc}"

    def _drop(self, reason: str) -> None:
        self._drop_counts[reason] = self._drop_counts.get(reason, 0) + 1

    def _record_write_failure(self, exc: BaseException) -> None:
        with self._lock:
            if isinstance(exc, TypeError):
                self._disable("json_serialization_failed", exc)
            elif isinstance(exc, PermissionError):
                self._disable("permission_denied", exc)
            elif isinstance(exc, OSError):
                reason = "disk_full" if getattr(exc, "errno", None) == 28 else "write_failed"
                self._disable(reason, exc)
            else:
                self._disable("write_failed", exc)

    def _writer_loop(self) -> None:
        while True:
            payload = self._queue.get()
            try:
                if payload is _STOP_WRITER:
                    return
                try:
                    assert isinstance(payload, dict)
                    _append_jsonl(self.events_path, payload)
                    _atomic_write_jsonl(self.latest_path, payload)
                except Exception as exc:
                    self._record_write_failure(exc)
            finally:
                self._queue.task_done()

    def _event_payload(
        self,
        event: str,
        *,
        stage: str = "general",
        level: str = "INFO",
        media_id: str = "",
        project_id: str = "",
        **fields: Any,
    ) -> dict[str, Any]:
        self._seq += 1
        payload = {
            "schema": TRACE_SCHEMA,
            "ts": _utc_now_text(),
            "seq": self._seq,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "event": str(event or ""),
            "stage": str(stage or "general"),
            "level": str(level or "INFO").upper(),
            "thread": threading.current_thread().name or "MainThread",
            "media_id": str(media_id or self.manifest.get("media_fingerprint", {}).get("path_hash", "")),
            "project_id": str(project_id or self.project_id),
        }
        payload.update(json_safe(fields))
        if "rss_bytes" not in payload:
            payload["rss_bytes"] = process_rss_bytes()
        if "frame" in payload and "fps" in payload and ("fps_num" not in payload or "fps_den" not in payload):
            num, den = fps_parts(payload.get("fps"))
            payload["fps_num"] = num
            payload["fps_den"] = den
        return payload

    def log_event(self, event: str, *, stage: str = "general", level: str = "INFO", **fields: Any) -> bool:
        with self._lock:
            if self._disabled:
                self._drop("disabled")
                return False
            if self._event_count >= self.max_events:
                self._drop("queue_overflow")
                return False
            try:
                payload = self._event_payload(event, stage=stage, level=level, **fields)
                self._queue.put_nowait(payload)
                self._event_count += 1
                return True
            except TypeError as exc:
                self._disable("json_serialization_failed", exc)
            except queue.Full:
                self._drop("queue_overflow")
            except PermissionError as exc:
                self._disable("permission_denied", exc)
            except OSError as exc:
                reason = "disk_full" if getattr(exc, "errno", None) == 28 else "write_failed"
                self._disable(reason, exc)
            except Exception as exc:
                self._disable("write_failed", exc)
            return False

    def flush(self, timeout_sec: float = 2.0) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout_sec))
        try:
            while True:
                if getattr(self._queue, "unfinished_tasks", 0) <= 0:
                    return not self._disabled
                if time.monotonic() >= deadline:
                    self._drop("flush_timeout")
                    return False
                time.sleep(0.005)
        except Exception as exc:
            self._disable("shutdown_flush_failed", exc)
            return False

    def close(self, timeout_sec: float = 2.0) -> bool:
        try:
            ok = self.log_event("trace_run_closed", stage="runtime", level="INFO")
            ok = self.flush(timeout_sec=timeout_sec) and ok
            if self._writer.is_alive():
                try:
                    self._queue.put(_STOP_WRITER, timeout=max(0.05, min(0.5, timeout_sec)))
                except Exception as exc:
                    self._disable("shutdown_flush_failed", exc)
                    return False
                self._writer.join(timeout=max(0.05, float(timeout_sec)))
                if self._writer.is_alive():
                    self._disable("shutdown_flush_failed", TimeoutError("trace writer did not stop"))
                    return False
            return ok and not self._disabled
        except Exception as exc:
            self._disable("shutdown_flush_failed", exc)
            return False

    def status(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "latest_path": str(self.latest_path),
            "events_path": str(self.events_path),
            "manifest_path": str(self.manifest_path),
            "disabled": self._disabled,
            "drop_counts": dict(self._drop_counts),
            "last_error": self._last_error,
            "event_count": self._event_count,
        }


def trace_enabled(default: bool = True) -> bool:
    raw = os.environ.get("AI_SUBTITLE_STUDIO_TRACE_ENABLED", "")
    if not raw:
        return bool(default)
    return raw.strip().lower() not in {"0", "false", "off", "no", "disabled"}


def start_trace_run(**kwargs: Any) -> TraceLogger | None:
    if not trace_enabled():
        return None
    try:
        return TraceLogger(**kwargs)
    except Exception:
        return None


def initialize_app_trace(**kwargs: Any) -> TraceLogger | None:
    global _APP_TRACE_LOGGER
    if not trace_enabled():
        return None
    with _APP_TRACE_LOCK:
        if _APP_TRACE_LOGGER is None:
            _APP_TRACE_LOGGER = start_trace_run(**kwargs)
        return _APP_TRACE_LOGGER


def current_app_trace_logger() -> TraceLogger | None:
    return _APP_TRACE_LOGGER


def reset_app_trace_after_fork() -> None:
    global _APP_TRACE_LOGGER
    _APP_TRACE_LOGGER = None


try:
    os.register_at_fork(after_in_child=reset_app_trace_after_fork)
except (AttributeError, RuntimeError):
    pass
