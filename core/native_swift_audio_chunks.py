from __future__ import annotations

from typing import Any

from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime.config import IS_MAC


def _enabled() -> bool:
    if not IS_MAC:
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_AUDIO_CHUNKS")


def audio_chunk_manifest_via_swift(
    chunk_dir: str,
    *,
    fallback_step_sec: float = 0.0,
    require_vad_start: bool = False,
) -> list[dict[str, Any]] | None:
    if not _enabled():
        return None
    decoded = request_native_core_task(
        "audio_chunk_manifest",
        {
            "chunk_dir": str(chunk_dir or ""),
            "fallback_step_sec": float(fallback_step_sec or 0.0),
            "require_vad_start": bool(require_vad_start),
        },
    )
    if not isinstance(decoded, dict):
        return None
    rows = decoded.get("chunks")
    if not isinstance(rows, list):
        return None
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "")
        name = str(row.get("name") or "")
        if not path or not name:
            continue
        try:
            out.append(
                {
                    "name": name,
                    "path": path,
                    "start": float(row.get("start", 0.0) or 0.0),
                    "duration": float(row.get("duration", 0.0) or 0.0),
                    "end": float(row.get("end", 0.0) or 0.0),
                    "has_vad_start": bool(row.get("has_vad_start", False)),
                }
            )
        except (TypeError, ValueError):
            continue
    return out


__all__ = ["audio_chunk_manifest_via_swift"]
