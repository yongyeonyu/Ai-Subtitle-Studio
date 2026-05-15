from __future__ import annotations

import socket
import threading
from typing import Any, Callable

from core.automation.app_command_protocol import (
    APP_COMMAND_BUFFER_SIZE,
    build_command_result,
    decode_command_payload,
    encode_command_result,
)


class LocalAppCommandServer:
    def __init__(self, sock: socket.socket):
        self._socket = sock
        self._lock = threading.Lock()
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
            result = self._dispatch(raw)
            try:
                self._socket.sendto(encode_command_result(result), addr)
            except OSError:
                continue

    def _dispatch(self, raw: bytes) -> dict[str, Any]:
        payload = decode_command_payload(raw)
        command = payload.get("command", "")
        if not command:
            return build_command_result(command, ok=False, accepted=False, error="missing_command")
        with self._lock:
            handler = self._handler
            if handler is None:
                self._pending.append(payload)
                return build_command_result(
                    command,
                    ok=True,
                    accepted=True,
                    queued=True,
                    message="queued_until_main_window_ready",
                )
        try:
            result = handler(payload)
        except Exception as exc:
            return build_command_result(
                command,
                ok=False,
                accepted=False,
                error="handler_exception",
                message=str(exc),
            )
        if not isinstance(result, dict):
            return build_command_result(command, ok=True, accepted=True)
        return result
