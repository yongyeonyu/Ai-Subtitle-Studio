from __future__ import annotations

import json
import socket
from typing import Any

from core.runtime import config

APP_COMMAND_SCHEMA = "ai_subtitle_studio.app_command.v1"
APP_COMMAND_RESULT_SCHEMA = "ai_subtitle_studio.app_command_result.v1"
APP_COMMAND_HOST = "127.0.0.1"
APP_COMMAND_BUFFER_SIZE = 65535
APP_COMMAND_TIMEOUT_SEC = 8.0


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def normalize_command_name(value: Any) -> str:
    return _safe_str(value).replace("_", "-").lower()


def normalize_command_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    command = normalize_command_name(data.get("command"))
    paths = data.get("paths")
    if isinstance(paths, (str, bytes)):
        normalized_paths = [_safe_str(paths)]
    elif isinstance(paths, list):
        normalized_paths = [_safe_str(path) for path in paths if _safe_str(path)]
    else:
        normalized_paths = []
    normalized = {
        "schema": APP_COMMAND_SCHEMA,
        "command": command,
        "path": _safe_str(data.get("path")),
        "folder": _safe_str(data.get("folder")),
        "paths": normalized_paths,
        "options": dict(data.get("options") or {}) if isinstance(data.get("options"), dict) else {},
    }
    if not normalized["path"] and normalized_paths:
        normalized["path"] = normalized_paths[0]
    if not normalized["folder"] and command == "queue-folder":
        normalized["folder"] = normalized["path"]
    if not normalized["folder"] and command == "start-multiclip" and not normalized_paths:
        normalized["folder"] = normalized["path"]
    return normalized


def build_command_payload(command: str, **fields: Any) -> dict[str, Any]:
    payload = dict(fields)
    payload["command"] = command
    return normalize_command_payload(payload)


def build_command_result(
    command: str,
    *,
    ok: bool,
    accepted: bool | None = None,
    queued: bool = False,
    message: str = "",
    error: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": APP_COMMAND_RESULT_SCHEMA,
        "command": normalize_command_name(command),
        "ok": bool(ok),
        "accepted": bool(ok if accepted is None else accepted),
        "queued": bool(queued),
        "message": _safe_str(message),
        "error": _safe_str(error),
        "data": dict(data or {}),
    }


def _json_default(value: Any) -> Any:
    return str(value)


def encode_command_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        normalize_command_payload(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def decode_command_payload(raw: bytes | str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    return normalize_command_payload(payload)


def encode_command_result(result: dict[str, Any]) -> bytes:
    data = result if isinstance(result, dict) else {}
    command = normalize_command_name(data.get("command"))
    encoded = build_command_result(
        command,
        ok=bool(data.get("ok", False)),
        accepted=data.get("accepted"),
        queued=bool(data.get("queued", False)),
        message=data.get("message", ""),
        error=data.get("error", ""),
        data=data.get("data") if isinstance(data.get("data"), dict) else {},
    )
    return json.dumps(
        encoded,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def decode_command_result(raw: bytes | str) -> dict[str, Any]:
    try:
        result = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return build_command_result("", ok=False, accepted=False, error="invalid_response")
    return build_command_result(
        result.get("command", ""),
        ok=bool(result.get("ok", False)),
        accepted=result.get("accepted"),
        queued=bool(result.get("queued", False)),
        message=result.get("message", ""),
        error=result.get("error", ""),
        data=result.get("data") if isinstance(result.get("data"), dict) else {},
    )


def send_command_to_app(
    payload: dict[str, Any],
    *,
    host: str = APP_COMMAND_HOST,
    port: int | None = None,
    timeout_sec: float = APP_COMMAND_TIMEOUT_SEC,
) -> dict[str, Any]:
    target_port = int(port or config.INSTANCE_PORT)
    timeout = max(0.1, float(timeout_sec or APP_COMMAND_TIMEOUT_SEC))
    packet = encode_command_payload(payload)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet, (host, target_port))
        raw, _addr = sock.recvfrom(APP_COMMAND_BUFFER_SIZE)
    return decode_command_result(raw)
