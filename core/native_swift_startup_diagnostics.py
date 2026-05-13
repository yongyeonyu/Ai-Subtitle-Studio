from __future__ import annotations

import os
from typing import Any

from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime.config import IS_MAC


def _enabled() -> bool:
    if not IS_MAC:
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_DIAGNOSTICS")


def build_startup_diagnostic_via_swift(
    media_path: str,
    *,
    media: dict[str, Any] | None,
    audio: dict[str, Any] | None,
    settings: dict[str, Any] | None,
    cut_boundaries: list[Any] | None,
    provisional_cut_boundaries: list[Any] | None,
    expected_time_sec: float | None,
    speaker_count_hint: int | None,
) -> dict[str, Any] | None:
    if not _enabled():
        return None
    payload = {
        "media_path": str(media_path or ""),
        "media_name": os.path.basename(str(media_path or "")),
        "media": dict(media or {}),
        "audio": dict(audio or {}),
        "settings": dict(settings or {}),
        "cut_boundaries": list(cut_boundaries or []),
        "provisional_cut_boundaries": list(provisional_cut_boundaries or []),
        "expected_time_sec": float(expected_time_sec or 0.0),
        "speaker_count_hint": speaker_count_hint,
    }
    decoded = request_native_core_task("startup_diagnostic_build", payload)
    return decoded if isinstance(decoded, dict) else None


def attach_expected_processing_time_via_swift(
    diagnostic: dict[str, Any],
    expected_time_sec: float,
    *,
    source: str = "history",
) -> dict[str, Any] | None:
    if not _enabled():
        return None
    decoded = request_native_core_task(
        "startup_diagnostic_attach_expected",
        {
            "diagnostic": dict(diagnostic or {}),
            "expected_time_sec": float(expected_time_sec or 0.0),
            "source": str(source or "history"),
        },
    )
    return decoded if isinstance(decoded, dict) else None


def format_startup_diagnostic_log_via_swift(diagnostic: dict[str, Any]) -> list[str] | None:
    if not _enabled():
        return None
    decoded = request_native_core_task(
        "startup_diagnostic_format_log",
        {"diagnostic": dict(diagnostic or {})},
    )
    if not isinstance(decoded, dict):
        return None
    lines = decoded.get("lines")
    if not isinstance(lines, list):
        return None
    return [str(line) for line in lines]


__all__ = [
    "attach_expected_processing_time_via_swift",
    "build_startup_diagnostic_via_swift",
    "format_startup_diagnostic_log_via_swift",
]
