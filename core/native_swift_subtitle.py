from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


def _candidate_cli_paths() -> list[Path]:
    paths: list[Path] = []
    env_path = os.environ.get("AI_SUBTITLE_STUDIO_NATIVE_CLI")
    if env_path:
        paths.append(Path(env_path))

    bundle_resources = os.environ.get("AI_SUBTITLE_STUDIO_BUNDLE_RESOURCES")
    if bundle_resources:
        paths.append(Path(bundle_resources) / "native" / "AIStudioNativeCLI")

    root = Path(__file__).resolve().parents[1]
    paths.append(root / "native" / "macos" / "AIStudioNative" / ".build" / "release" / "AIStudioNativeCLI")
    paths.append(root.parent / "native" / "macos" / "AIStudioNative" / ".build" / "release" / "AIStudioNativeCLI")
    return paths


def find_native_cli_path() -> Path | None:
    for path in _candidate_cli_paths():
        if path.exists() and os.access(path, os.X_OK):
            return path
    return None


def native_cli_path() -> Path | None:
    swift_core = os.environ.get("AI_SUBTITLE_STUDIO_SWIFT_CORE", "").lower()
    if swift_core in {"0", "false", "off", "no"}:
        return None
    if swift_core not in {"1", "true", "on", "yes"} and not os.environ.get("AI_SUBTITLE_STUDIO_BUNDLE_RESOURCES"):
        return None
    return find_native_cli_path()


def parse_srt_via_swift(srt_path: str) -> list[dict[str, Any]] | None:
    cli = native_cli_path()
    if cli is None:
        return None
    try:
        proc = subprocess.run(
            [str(cli), "srt-to-json", srt_path],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        rows = json.loads(proc.stdout or "[]")
    except Exception:
        return None
    if not isinstance(rows, list):
        return None

    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text", "") or "").strip()
        if not text:
            continue
        try:
            start = float(row.get("start", 0.0) or 0.0)
            end = float(row.get("end", 0.0) or 0.0)
        except Exception:
            continue
        out.append(
            {
                "start": start,
                "end": end,
                "text": text,
                "is_gap": bool(row.get("is_gap", False)),
            }
        )
    return out


__all__ = ["find_native_cli_path", "native_cli_path", "parse_srt_via_swift"]
