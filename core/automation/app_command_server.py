from __future__ import annotations

import socket
import threading
import time
from typing import Any, Callable

from core.automation.app_command_protocol import (
    APP_COMMAND_BUFFER_SIZE,
    build_command_result,
    decode_command_payload,
    encode_command_result,
)
from core.runtime.stage_metrics import _elapsed_ms, record_stage_done, record_stage_ready, record_stage_start

_CONCURRENT_READ_COMMANDS = {"ping", "status", "guided-subtitle-status"}
_UDP_SAFE_RESULT_BYTES = min(APP_COMMAND_BUFFER_SIZE - 1024, 60000)
_UDP_COMPACT_READ_BYTES = 8192
_UDP_COMPACT_RESULT_BYTES = 8192
_READ_HANDLER_TIMEOUT_SEC = 1.0


def _trim_text_items(values: Any, *, limit: int = 8, max_chars: int = 220) -> list[str]:
    out: list[str] = []
    for item in list(values or [])[-limit:]:
        text = str(item or "")
        out.append(text[:max_chars])
    return out


def _compact_runtime_resource(value: Any) -> dict[str, Any]:
    data = dict(value or {}) if isinstance(value, dict) else {}
    return {
        "timestamp": data.get("timestamp"),
        "profile": data.get("profile"),
        "pressure_stage": data.get("pressure_stage") or data.get("memory_pressure_stage"),
        "rss_gb": data.get("rss_gb"),
        "free_memory_gb": data.get("free_memory_gb"),
        "free_memory_ratio": data.get("free_memory_ratio"),
        "active_label_count": data.get("active_label_count"),
        "active_labels": _trim_text_items(data.get("active_labels"), limit=6, max_chars=80),
    }


def _compact_widget_geometry(value: Any) -> dict[str, Any]:
    data = dict(value or {}) if isinstance(value, dict) else {}
    compact: dict[str, Any] = {}
    for key in ("x", "y", "width", "height", "right", "bottom", "visible", "enabled"):
        if key in data:
            compact[key] = data.get(key)
    return compact


def _compact_geometry_snapshot(value: Any) -> dict[str, Any]:
    data = dict(value or {}) if isinstance(value, dict) else {}
    compact: dict[str, Any] = {}
    for key in (
        "main_window",
        "workspace_splitter",
        "right_workspace",
        "stack",
        "editor",
        "editor_splitter",
        "text_edit",
        "video_frame",
        "video_player",
        "timeline_frame",
        "timeline",
        "timeline_canvas",
        "timeline_global_canvas",
        "bottom_work_panel",
        "global_menu_bar",
    ):
        rect = _compact_widget_geometry(data.get(key))
        if rect:
            compact[key] = rect
    for key in ("workspace_splitter_sizes", "editor_splitter_sizes"):
        values = data.get(key)
        if isinstance(values, list):
            compact[key] = [int(item) for item in values[:8] if isinstance(item, (int, float))]
    return compact


def _compact_editor_runtime(value: Any) -> dict[str, Any]:
    data = dict(value or {}) if isinstance(value, dict) else {}
    segment_keys = ("active_segment", "previous_segment", "next_segment")
    compact: dict[str, Any] = {}
    for key in (
        "playhead_sec",
        "shadow_playhead_sec",
        "shadow_playhead_active",
        "total_duration",
        "active_seg_line",
        "active_seg_start",
        "segment_count",
        "gap_count",
        "diamond_left",
        "diamond_right",
        "smart_split_ready",
        "inline_edit_active",
        "inline_edit_mode",
        "inline_edit_text_length",
        "inline_edit_cursor",
        "split_pending_sec",
        "timeline_pps",
        "timeline_scroll_x",
        "timeline_fit_locked",
        "playback_center_lock",
        "start_button_text",
        "start_button_enabled",
        "video_visible",
        "video_playback_state",
        "video_backend",
        "video_source_path",
        "video_pending_source_path",
        "video_source_ready",
        "video_media_source_loaded",
        "video_position_ms",
        "video_duration_ms",
        "active_footer_menu_id",
    ):
        if key in data:
            compact[key] = data.get(key)
    for key in segment_keys:
        segment = dict(data.get(key) or {}) if isinstance(data.get(key), dict) else {}
        if not segment:
            compact[key] = {}
            continue
        compact[key] = {
            "line": segment.get("line"),
            "start": segment.get("start"),
            "end": segment.get("end"),
            "text": str(segment.get("text", "") or "")[:160],
            "is_gap": bool(segment.get("is_gap", False)),
        }
    geometry = _compact_geometry_snapshot(data.get("geometry"))
    if geometry:
        compact["geometry"] = geometry
    return compact


def _compact_roughcut_state(value: Any) -> dict[str, Any]:
    data = dict(value or {}) if isinstance(value, dict) else {}
    compact: dict[str, Any] = {}
    for key in ("status", "pending", "running", "thread_alive", "major_count"):
        if key in data:
            compact[key] = data.get(key)
    return compact


def _compact_roughcut_runtime(value: Any) -> dict[str, Any]:
    data = dict(value or {}) if isinstance(value, dict) else {}
    compact: dict[str, Any] = {}
    for key in (
        "has_result",
        "selected_candidate_id",
        "candidate_count",
        "selected_chapter_id",
        "selected_segment_id",
        "selected_chapter_title",
        "candidate_state",
        "filter_value",
        "filter_summary",
        "selection_summary",
        "order_summary",
        "sequence_preview_active",
        "visible_row_count",
        "total_row_count",
        "video_host_attached",
        "video_placeholder_visible",
        "player_menu_visible",
    ):
        if key in data:
            compact[key] = data.get(key)
    candidate_ids = list(data.get("candidate_ids") or [])
    if candidate_ids:
        compact["candidate_ids"] = [str(item or "") for item in candidate_ids[:6]]
    visible_ids = list(data.get("visible_chapter_ids") or [])
    if visible_ids:
        compact["visible_chapter_ids"] = [str(item or "") for item in visible_ids[:12]]
    visible_segments = list(data.get("visible_segment_ids") or [])
    if visible_segments:
        compact["visible_segment_ids"] = [str(item or "") for item in visible_segments[:8]]
    return compact


def _compact_status_data(value: Any, *, encoded_bytes: int, send_fallback: bool = False) -> dict[str, Any]:
    data = dict(value or {}) if isinstance(value, dict) else {}
    queue = dict(data.get("queue_runtime") or {}) if isinstance(data.get("queue_runtime"), dict) else {}
    compact = {
        "status_response_truncated": True,
        "status_response_original_bytes": int(encoded_bytes),
        "editor_open": bool(data.get("editor_open", False)),
        "editor_media_path": str(data.get("editor_media_path", "") or ""),
        "editor_state": str(data.get("editor_state", "") or ""),
        "current_project_path": str(data.get("current_project_path", "") or ""),
        "current_work_mode": str(data.get("current_work_mode", "") or ""),
        "backend_active": bool(data.get("backend_active", False)),
        "auto_processing_active": bool(data.get("auto_processing_active", False)),
        "generation_stage": str(data.get("generation_stage", "") or ""),
        "last_stage_key": str(data.get("last_stage_key", "") or ""),
        "subtitle_count": data.get("subtitle_count"),
        "roughcut_state": _compact_roughcut_state(data.get("roughcut_state")),
        "roughcut_runtime": _compact_roughcut_runtime(data.get("roughcut_runtime")),
        "runtime_timestamp": data.get("runtime_timestamp"),
        "editor_runtime": _compact_editor_runtime(data.get("editor_runtime")),
        "editor_aux_counts": dict(data.get("editor_aux_counts") or {}) if isinstance(data.get("editor_aux_counts"), dict) else {},
        "editor_stt": dict(data.get("editor_stt") or {}) if isinstance(data.get("editor_stt"), dict) else {},
        "queue_runtime": {
            "row_count": queue.get("row_count"),
            "done_rows": queue.get("done_rows"),
            "error_rows": queue.get("error_rows"),
            "all_done": queue.get("all_done"),
        },
        "personalization_runtime": dict(data.get("personalization_runtime") or {})
        if isinstance(data.get("personalization_runtime"), dict)
        else {},
        "runtime_resource": _compact_runtime_resource(data.get("runtime_resource")),
        "recent_logs": _trim_text_items(data.get("recent_logs"), limit=8, max_chars=180),
        "recent_stage_logs": _trim_text_items(data.get("recent_stage_logs"), limit=8, max_chars=180),
    }
    if send_fallback:
        compact["status_response_send_fallback"] = True
    return compact


def _compact_result_for_udp(
    result: dict[str, Any],
    *,
    encoded_bytes: int,
    send_fallback: bool = False,
) -> dict[str, Any]:
    command = str(result.get("command", "") or "")
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    compact_data = (
        _compact_status_data(data, encoded_bytes=encoded_bytes, send_fallback=send_fallback)
        if command in _CONCURRENT_READ_COMMANDS
        else {"response_truncated": True, "response_original_bytes": int(encoded_bytes)}
    )
    return build_command_result(
        command,
        ok=bool(result.get("ok", False)),
        accepted=result.get("accepted"),
        queued=bool(result.get("queued", False)),
        message=str(result.get("message", "") or ""),
        error=str(result.get("error", "") or ""),
        data=compact_data,
    )


def _minimal_result_for_udp(result: dict[str, Any], *, encoded_bytes: int) -> dict[str, Any]:
    command = str(result.get("command", "") or "")
    data = (
        {
            "status_response_truncated": True,
            "status_response_send_fallback": True,
            "status_response_original_bytes": int(encoded_bytes),
        }
        if command in _CONCURRENT_READ_COMMANDS
        else {
            "response_truncated": True,
            "response_send_fallback": True,
            "response_original_bytes": int(encoded_bytes),
        }
    )
    return build_command_result(
        command,
        ok=bool(result.get("ok", False)),
        accepted=result.get("accepted"),
        queued=bool(result.get("queued", False)),
        message=str(result.get("message", "") or ""),
        error=str(result.get("error", "") or ""),
        data=data,
    )


class LocalAppCommandServer:
    def __init__(self, sock: socket.socket):
        self._socket = sock
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._handler_lock = threading.Lock()
        self._read_cache_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None
        self._last_read_results: dict[str, dict[str, Any]] = {}
        self._pending: list[dict[str, Any]] = []
        self._closed = False

    def start(self) -> None:
        with self._lock:
            if self._closed:
                return
            thread = self._thread
            if thread is not None and thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._serve,
                daemon=True,
                name="app-command-server",
            )
            self._thread.start()

    def close(self) -> None:
        with self._lock:
            self._closed = True
        try:
            self._socket.close()
        except OSError:
            pass

    def set_handler(self, handler: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        pending: list[dict[str, Any]]
        with self._lock:
            self._handler = handler
            pending = list(self._pending)
            self._pending.clear()
        for payload in pending:
            try:
                handler(dict(payload))
            except Exception:
                continue

    def _serve(self) -> None:
        while True:
            with self._lock:
                if self._closed:
                    return
            try:
                raw, addr = self._socket.recvfrom(APP_COMMAND_BUFFER_SIZE)
            except OSError:
                return
            threading.Thread(
                target=self._handle_request,
                args=(raw, addr),
                daemon=True,
                name="app-command-request",
            ).start()

    def _handle_request(self, raw: bytes, addr: tuple[str, int]) -> None:
        result = self._dispatch(raw)
        try:
            encoded = encode_command_result(result)
            command = str(result.get("command", "") or "")
            compact_limit = (
                _UDP_COMPACT_READ_BYTES
                if command in _CONCURRENT_READ_COMMANDS
                else _UDP_COMPACT_RESULT_BYTES
            )
            if len(encoded) > compact_limit:
                # 자동화 응답은 중간 크기 payload도 먼저 compact해 UDP fallback/timeout 오인을 피한다.
                result = _compact_result_for_udp(result, encoded_bytes=len(encoded))
                encoded = encode_command_result(result)
            if len(encoded) > _UDP_SAFE_RESULT_BYTES:
                # UDP automation hot path: oversized status payloads fail at
                # sendto() and look like app_unreachable. Send a compact status
                # instead so QA can distinguish app health from payload bloat.
                result = _compact_result_for_udp(result, encoded_bytes=len(encoded))
                encoded = encode_command_result(result)
            if len(encoded) > _UDP_SAFE_RESULT_BYTES:
                result = _minimal_result_for_udp(result, encoded_bytes=len(encoded))
                encoded = encode_command_result(result)
            with self._send_lock:
                try:
                    self._socket.sendto(encoded, addr)
                except OSError:
                    # UDP send failure is usually EMSGSIZE under heavy status
                    # payloads. Reply with a tiny health packet so automation
                    # records "truncated" instead of a misleading app timeout.
                    if command in _CONCURRENT_READ_COMMANDS:
                        fallback_result = _compact_result_for_udp(
                            result,
                            encoded_bytes=len(encoded),
                            send_fallback=True,
                        )
                        fallback = encode_command_result(fallback_result)
                        if len(fallback) <= _UDP_SAFE_RESULT_BYTES:
                            self._socket.sendto(fallback, addr)
                            return
                    minimal = encode_command_result(_minimal_result_for_udp(result, encoded_bytes=len(encoded)))
                    self._socket.sendto(minimal, addr)
        except OSError:
            return

    def _dispatch(self, raw: bytes) -> dict[str, Any]:
        received_at = time.perf_counter()
        payload = decode_command_payload(raw)
        command = payload.get("command", "")
        if not command:
            return build_command_result(command, ok=False, accepted=False, error="missing_command")
        stage_name = f"app_command:{command}"
        record_stage_ready(
            stage_name,
            resource_label="automation",
            queue_depth=self._pending_depth(),
            metrics={"payload_bytes": len(raw or b"")},
        )
        with self._lock:
            handler = self._handler
            if handler is None:
                self._pending.append(payload)
                result = build_command_result(
                    command,
                    ok=True,
                    accepted=True,
                    queued=True,
                    message="queued_until_main_window_ready",
                )
                record_stage_done(
                    stage_name,
                    resource_label="automation",
                    wait_ms=_elapsed_ms(received_at),
                    queue_depth=len(self._pending),
                    ok=True,
                    metrics={"queued_until_main_window_ready": True},
                )
                return result
        try:
            if command in _CONCURRENT_READ_COMMANDS:
                record_stage_start(
                    stage_name,
                    resource_label="automation",
                    wait_ms=_elapsed_ms(received_at),
                    queue_depth=self._pending_depth(),
                )
                handler_started = time.perf_counter()
                result = self._dispatch_read_with_timeout(command, payload, handler)
            else:
                lock_started = time.perf_counter()
                self._handler_lock.acquire()
                lock_wait_ms = _elapsed_ms(lock_started)
                handler_started = time.perf_counter()
                record_stage_start(
                    stage_name,
                    resource_label="automation",
                    wait_ms=lock_wait_ms,
                    queue_depth=self._pending_depth(),
                )
                try:
                    result = handler(payload)
                finally:
                    self._handler_lock.release()
        except Exception as exc:
            record_stage_done(
                stage_name,
                resource_label="automation",
                worker_busy_ms=_elapsed_ms(locals().get("handler_started", received_at)),
                queue_depth=self._pending_depth(),
                ok=False,
                metrics={"error": "handler_exception"},
            )
            return build_command_result(
                command,
                ok=False,
                accepted=False,
                error="handler_exception",
                message=str(exc),
            )
        if not isinstance(result, dict):
            result = build_command_result(command, ok=True, accepted=True)
        result_data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if command in _CONCURRENT_READ_COMMANDS and not bool(result_data.get("status_handler_timeout", False)):
            self._remember_read_result(command, result)
        record_stage_done(
            stage_name,
            resource_label="automation",
            worker_busy_ms=_elapsed_ms(locals().get("handler_started", received_at)),
            queue_depth=self._pending_depth(),
            ok=bool(result.get("ok", True)),
            metrics={"accepted": bool(result.get("accepted", True)), "queued": bool(result.get("queued", False))},
        )
        return result

    def _remember_read_result(self, command: str, result: dict[str, Any]) -> None:
        with self._read_cache_lock:
            self._last_read_results[str(command or "")] = dict(result or {})

    def _cached_read_result(self, command: str) -> dict[str, Any] | None:
        with self._read_cache_lock:
            cached = self._last_read_results.get(str(command or ""))
            if cached is None and command == "guided-subtitle-status":
                cached = self._last_read_results.get("status")
            return dict(cached or {}) if cached else None

    def _read_timeout_result(self, command: str) -> dict[str, Any]:
        cached = self._cached_read_result(command)
        if isinstance(cached, dict) and cached:
            data = dict(cached.get("data") or {}) if isinstance(cached.get("data"), dict) else {}
            data["status_handler_timeout"] = True
            data["status_response_cached"] = True
            cached["data"] = data
            cached["command"] = command
            cached["message"] = str(cached.get("message") or "status_handler_timeout")
            return cached
        return build_command_result(
            command,
            ok=True,
            accepted=True,
            message="pong" if command == "ping" else "status_handler_timeout",
            data={
                "status_handler_timeout": True,
                "status_response_cached": False,
            },
        )

    def _dispatch_read_with_timeout(
        self,
        command: str,
        payload: dict[str, Any],
        handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        done = threading.Event()
        box: dict[str, Any] = {}

        def call_handler() -> None:
            try:
                result = handler(payload)
                if isinstance(result, dict):
                    box["result"] = result
                    self._remember_read_result(command, result)
                else:
                    box["result"] = build_command_result(command, ok=True, accepted=True)
            except Exception as exc:
                box["exc"] = exc
            finally:
                done.set()

        # status/ping은 생성 hot path 중에도 살아 있어야 하므로 handler가 막히면 캐시로 즉시 답한다.
        threading.Thread(target=call_handler, daemon=True, name=f"app-command-read:{command}").start()
        if done.wait(_READ_HANDLER_TIMEOUT_SEC):
            if "exc" in box:
                raise box["exc"]
            return dict(box.get("result") or build_command_result(command, ok=True, accepted=True))
        return self._read_timeout_result(command)

    def _pending_depth(self) -> int:
        with self._lock:
            pending = len(self._pending)
        # 앱 명령 서버의 핵심 hot path다. lock 대기 중인 stateful 명령을 queue_depth에 포함해
        # generation/save 중 ping/status가 왜 흔들렸는지 status snapshot만으로 추적한다.
        try:
            return pending + (1 if self._handler_lock.locked() else 0)
        except Exception:
            return pending
