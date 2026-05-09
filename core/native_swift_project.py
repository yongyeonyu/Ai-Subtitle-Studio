from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from core.native_swift_subtitle import find_native_cli_path


def _enabled() -> bool:
    value = os.environ.get("AI_SUBTITLE_STUDIO_SWIFT_PROJECT_IO", "").lower()
    if value in {"0", "false", "off", "no"}:
        return False
    return value in {"1", "true", "on", "yes"} or bool(os.environ.get("AI_SUBTITLE_STUDIO_BUNDLE_RESOURCES"))


def read_project_via_swift(filepath: str) -> dict[str, Any] | None:
    if not _enabled():
        return None
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
        payload = json.loads(proc.stdout or "{}")
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_project_via_swift(filepath: str, project: dict[str, Any]) -> bool:
    if not _enabled():
        return False
    cli = find_native_cli_path()
    if cli is None:
        return False
    try:
        raw = json.dumps(project if isinstance(project, dict) else {}, ensure_ascii=False, separators=(",", ":"))
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
