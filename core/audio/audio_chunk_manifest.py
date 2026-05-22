from __future__ import annotations

import os
import re
import threading
import wave
from collections import OrderedDict
from typing import Any

from core.native_swift_audio_chunks import audio_chunk_manifest_via_swift

_VAD_WAV_RE = re.compile(r"vad_\d+_([\d.]+)\.wav$", re.IGNORECASE)
_MANIFEST_CACHE_LOCK = threading.Lock()
_MANIFEST_CACHE: OrderedDict[tuple[Any, ...], list[dict[str, Any]]] = OrderedDict()
_MANIFEST_CACHE_MAX = 16


def chunk_start_from_name(name: str) -> tuple[float, bool]:
    match = _VAD_WAV_RE.search(os.path.basename(str(name or "")))
    if not match:
        return 0.0, False
    try:
        return float(match.group(1)), True
    except (TypeError, ValueError):
        return 0.0, False


def chunk_dir_signature(chunk_dir: str) -> tuple[Any, ...] | None:
    root = os.path.abspath(str(chunk_dir or ""))
    if not root:
        return None
    try:
        root_stat = os.stat(root)
    except OSError:
        return None
    rows: list[tuple[str, int, int]] = []
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if not entry.name.lower().endswith(".wav"):
                    continue
                try:
                    if not entry.is_file():
                        continue
                    stat = entry.stat()
                except OSError:
                    continue
                rows.append((entry.name, int(stat.st_size), int(stat.st_mtime_ns)))
    except OSError:
        return None
    rows.sort()
    checksum = 0
    for name, size, mtime_ns in rows:
        name_sum = 0
        for char in name:
            name_sum = ((name_sum * 131) + ord(char)) & 0xFFFFFFFF
        checksum = ((checksum * 1000003) ^ name_sum ^ int(size) ^ int(mtime_ns)) & 0xFFFFFFFFFFFFFFFF
    return (root, int(root_stat.st_mtime_ns), len(rows), checksum)


def _wav_duration(path: str) -> float:
    try:
        with wave.open(path, "r") as handle:
            rate = float(handle.getframerate() or 0)
            return handle.getnframes() / rate if rate > 0 else 0.0
    except Exception:
        return 0.0


def _normalize_rows(
    rows: list[dict[str, Any]],
    *,
    fallback_step_sec: float,
    require_vad_start: bool,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    fallback_step = max(0.0, float(fallback_step_sec or 0.0))
    for idx, row in enumerate(rows):
        name = str(row.get("name") or "")
        path = str(row.get("path") or "")
        if not name or not path:
            continue
        start = float(row.get("start", 0.0) or 0.0)
        has_vad_start = bool(row.get("has_vad_start", False))
        if require_vad_start and not has_vad_start:
            continue
        if not has_vad_start and fallback_step > 0.0:
            start = idx * fallback_step
        duration = max(0.0, float(row.get("duration", 0.0) or 0.0))
        out.append(
            {
                "name": name,
                "path": path,
                "start": start,
                "duration": duration,
                "end": start + duration,
                "has_vad_start": has_vad_start,
            }
        )
    return out


def _manifest_cache_key(
    chunk_dir: str,
    *,
    fallback_step_sec: float,
    require_vad_start: bool,
    prefer_native: bool,
    signature: tuple[Any, ...] | None = None,
) -> tuple[Any, ...] | None:
    sig = signature if signature is not None else chunk_dir_signature(chunk_dir)
    if sig is None:
        return None
    return (
        sig,
        round(max(0.0, float(fallback_step_sec or 0.0)), 6),
        bool(require_vad_start),
        bool(prefer_native),
    )


def _cached_manifest(cache_key: tuple[Any, ...] | None) -> list[dict[str, Any]] | None:
    if cache_key is None:
        return None
    with _MANIFEST_CACHE_LOCK:
        rows = _MANIFEST_CACHE.get(cache_key)
        if rows is None:
            return None
        _MANIFEST_CACHE.move_to_end(cache_key)
        return [dict(row) for row in rows]


def _store_cached_manifest(cache_key: tuple[Any, ...] | None, rows: list[dict[str, Any]]) -> None:
    if cache_key is None:
        return
    with _MANIFEST_CACHE_LOCK:
        _MANIFEST_CACHE[cache_key] = [dict(row) for row in rows]
        _MANIFEST_CACHE.move_to_end(cache_key)
        while len(_MANIFEST_CACHE) > _MANIFEST_CACHE_MAX:
            _MANIFEST_CACHE.popitem(last=False)


def python_audio_chunk_manifest(
    chunk_dir: str,
    *,
    fallback_step_sec: float = 0.0,
    require_vad_start: bool = False,
) -> list[dict[str, Any]]:
    root = str(chunk_dir or "")
    if not root:
        return []
    rows: list[dict[str, Any]] = []
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if not entry.is_file() or not entry.name.lower().endswith(".wav"):
                    continue
                start, has_vad_start = chunk_start_from_name(entry.name)
                rows.append(
                    {
                        "name": entry.name,
                        "path": entry.path,
                        "start": start,
                        "duration": _wav_duration(entry.path),
                        "has_vad_start": has_vad_start,
                    }
                )
    except Exception:
        return []
    rows.sort(key=lambda row: (float(row.get("start", 0.0) or 0.0), str(row.get("name") or "")))
    return _normalize_rows(
        rows,
        fallback_step_sec=fallback_step_sec,
        require_vad_start=require_vad_start,
    )


def audio_chunk_manifest(
    chunk_dir: str,
    *,
    fallback_step_sec: float = 0.0,
    require_vad_start: bool = False,
    prefer_native: bool = True,
    signature: tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    cache_key = _manifest_cache_key(
        chunk_dir,
        fallback_step_sec=fallback_step_sec,
        require_vad_start=require_vad_start,
        prefer_native=prefer_native,
        signature=signature,
    )
    cached = _cached_manifest(cache_key)
    if cached is not None:
        return cached
    if prefer_native:
        rows = audio_chunk_manifest_via_swift(
            chunk_dir,
            fallback_step_sec=fallback_step_sec,
            require_vad_start=require_vad_start,
        )
        if rows is not None:
            normalized = _normalize_rows(
                rows,
                fallback_step_sec=fallback_step_sec,
                require_vad_start=require_vad_start,
            )
            _store_cached_manifest(cache_key, normalized)
            return normalized
    normalized = python_audio_chunk_manifest(
        chunk_dir,
        fallback_step_sec=fallback_step_sec,
        require_vad_start=require_vad_start,
    )
    _store_cached_manifest(cache_key, normalized)
    return normalized


__all__ = [
    "audio_chunk_manifest",
    "chunk_dir_signature",
    "chunk_start_from_name",
    "python_audio_chunk_manifest",
]
