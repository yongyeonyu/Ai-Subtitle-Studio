from __future__ import annotations

import time
from typing import Any, Callable

from core.automation.app_command_protocol import normalize_command_name, send_command_to_app


READ_ONLY_COMMANDS = {
    "ping",
    "status",
    "guided-subtitle-status",
    "capture-snapshot",
    "snapshot",
    "capture-dictionary-snapshot",
}
READINESS_RETRY_COMMANDS = {
    "ping",
    "status",
    "guided-subtitle-status",
}
NOT_READY_MESSAGE = "queued_until_main_window_ready"


def command_is_read_only(command: Any) -> bool:
    return normalize_command_name(command) in READ_ONLY_COMMANDS


def result_is_waiting_for_app(result: dict[str, Any] | None) -> bool:
    data = result if isinstance(result, dict) else {}
    return str(data.get("message", "") or "") == NOT_READY_MESSAGE


def send_app_command_with_readiness_retry(
    payload: dict[str, Any],
    *,
    timeout_sec: float,
    retry_sleep_sec: float = 0.15,
    sender: Callable[..., dict[str, Any]] = send_command_to_app,
) -> dict[str, Any]:
    command = normalize_command_name((payload or {}).get("command", ""))
    timeout = max(0.1, float(timeout_sec or 0.1))
    if command not in READINESS_RETRY_COMMANDS:
        return sender(payload, timeout_sec=timeout)

    deadline = time.monotonic() + timeout
    last_result: dict[str, Any] | None = None
    last_error: OSError | None = None
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempt_timeout = max(0.1, min(1.0, remaining))
        try:
            result = sender(payload, timeout_sec=attempt_timeout)
        except OSError as exc:
            last_error = exc
        else:
            last_result = result
            if not result_is_waiting_for_app(result):
                return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        # 앱 시작/부하 직후에는 UDP 서버만 먼저 응답하고 main_window 핸들러가 늦게 붙는다.
        # 순수 상태 조회만 재시도해 스냅샷/편집 명령의 중복 실행 위험을 피한다.
        time.sleep(min(max(0.0, float(retry_sleep_sec or 0.0)), remaining))
    if last_result is not None:
        return last_result
    if last_error is not None:
        raise last_error
    return sender(payload, timeout_sec=timeout)
