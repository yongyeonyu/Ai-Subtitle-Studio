from __future__ import annotations

import subprocess
from typing import Any

from core.native_json import dumps_json_text, loads_json_output
from core.native_swift_subtitle import find_native_cli_path, native_swift_runtime_enabled, request_native_core_task


def _enabled() -> bool:
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_PROJECT_IO")


def read_project_via_swift(filepath: str) -> dict[str, Any] | None:
    if not _enabled():
        return None
    payload = request_native_core_task("read_project_json", {"path": filepath})
    payload = payload.get("project") if isinstance(payload, dict) else None
    if payload is None:
        cli = find_native_cli_path()
        if cli is None:
            return None
        try:
            proc = subprocess.run(
                [str(cli), "read-project-json", filepath],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
            )
            payload = loads_json_output(proc.stdout, default={})
        except Exception:
            return None
    return payload if isinstance(payload, dict) else None


def write_project_via_swift(filepath: str, project: dict[str, Any]) -> bool:
    if not _enabled():
        return False
    payload = request_native_core_task("write_project_json", {"path": filepath, "project": project})
    if isinstance(payload, dict) and payload.get("ok") is True:
        return True
    cli = find_native_cli_path()
    if cli is None:
        return False
    try:
        raw = dumps_json_text(project if isinstance(project, dict) else {}, compact=True)
        subprocess.run(
            [str(cli), "write-project-json", filepath],
            input=raw,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        return True
    except Exception:
        return False


__all__ = ["read_project_via_swift", "write_project_via_swift"]
