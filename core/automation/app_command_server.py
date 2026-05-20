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


class LocalAppCommandServer:
    def __init__(self, sock: socket.socket):
        self._socket = sock
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._handler_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None
        self._pending: list[dict[str, Any]] = []
        self._closed = False

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
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
            with self._send_lock:
                self._socket.sendto(encode_command_result(result), addr)
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
            # Keep status/ping diagnostics readable while a slow automation command is busy.
            if command in _CONCURRENT_READ_COMMANDS:
                record_stage_start(
                    stage_name,
                    resource_label="automation",
                    wait_ms=_elapsed_ms(received_at),
                    queue_depth=self._pending_depth(),
                )
                handler_started = time.perf_counter()
                result = handler(payload)
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
        record_stage_done(
            stage_name,
            resource_label="automation",
            worker_busy_ms=_elapsed_ms(locals().get("handler_started", received_at)),
            queue_depth=self._pending_depth(),
            ok=bool(result.get("ok", True)),
            metrics={"accepted": bool(result.get("accepted", True)), "queued": bool(result.get("queued", False))},
        )
        return result

    def _pending_depth(self) -> int:
        with self._lock:
            pending = len(self._pending)
        # 앱 명령 서버의 핵심 hot path다. lock 대기 중인 stateful 명령을 queue_depth에 포함해
        # generation/save 중 ping/status가 왜 흔들렸는지 status snapshot만으로 추적한다.
        try:
            return pending + (1 if self._handler_lock.locked() else 0)
        except Exception:
            return pending
