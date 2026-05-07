# Version: 03.01.37
# Phase: PHASE2
"""
core/media_info.py
ffprobe 기반 미디어 정보 조회 유틸 + metadata cache
"""
from __future__ import annotations

import subprocess
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.media_fingerprint import media_fingerprint_digest
from core.native_json import loads_json, read_json_path
from core.performance import atomic_write_json, ffprobe_worker_count, media_probe_cache_dir
from core.platform_compat import ffprobe_binary, hidden_subprocess_kwargs

_CACHE_SCHEMA = 1
_MEDIA_PROBE_MEM_CACHE_MAX = 384
_MEM_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_MEM_CACHE_LOCK = threading.RLock()


def _default_result() -> dict:
    return {
        "duration": 0.0, "width": 0, "height": 0, "fps": 0.0,
        "info_txt": "오디오 파일", "len_txt": "-"
    }


def _copy_result(info: dict) -> dict:
    return dict(info or _default_result())


def _fingerprint(filepath: str) -> tuple[str, Path] | tuple[None, None]:
    try:
        Path(filepath).expanduser().stat()
        digest = media_fingerprint_digest(filepath, sample_bytes=512 * 1024, include_samples=True)
        return digest, media_probe_cache_dir() / f"{digest}.json"
    except Exception:
        return None, None


def _read_cache(cache_key: str, cache_path: Path) -> dict | None:
    with _MEM_CACHE_LOCK:
        cached = _MEM_CACHE.get(cache_key)
        if cached is not None:
            _MEM_CACHE.move_to_end(cache_key)
            return _copy_result(cached)
    try:
        payload = read_json_path(cache_path)
    except Exception:
        return None
    if payload.get("schema") != _CACHE_SCHEMA or payload.get("key") != cache_key:
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    _cache_put(cache_key, _copy_result(result))
    return _copy_result(result)


def _cache_put(cache_key: str, result: dict) -> None:
    with _MEM_CACHE_LOCK:
        _MEM_CACHE[cache_key] = _copy_result(result)
        _MEM_CACHE.move_to_end(cache_key)
        while len(_MEM_CACHE) > _MEDIA_PROBE_MEM_CACHE_MAX:
            _MEM_CACHE.popitem(last=False)


def _write_cache(cache_key: str, cache_path: Path, result: dict) -> None:
    try:
        payload = {"schema": _CACHE_SCHEMA, "key": cache_key, "result": _copy_result(result)}
        atomic_write_json(cache_path, payload)
        _cache_put(cache_key, result)
    except Exception:
        pass


def probe_media(filepath: str, *, use_cache: bool = True) -> dict:
    """
    Returns: {duration, width, height, fps, info_txt, len_txt}
    """
    result = _default_result()
    cache_key, cache_path = _fingerprint(filepath) if use_cache else (None, None)
    if cache_key and cache_path:
        cached = _read_cache(cache_key, cache_path)
        if cached is not None:
            return cached

    try:
        cmd = [
            ffprobe_binary(), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate:format=duration",
            "-of", "json", filepath,
        ]
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=5,
            **hidden_subprocess_kwargs(),
        )
        probe = loads_json(proc.stdout or "{}")
        fmt = probe.get("format", {})
        duration = float(fmt.get("duration", 0)) if fmt.get("duration") else 0.0
        streams = probe.get("streams", [])

        if streams:
            strm = streams[0]
            if duration == 0.0:
                duration = float(strm.get("duration", 0)) if strm.get("duration") else 0.0
            w, h = strm.get("width", 0), strm.get("height", 0)
            fps_str = strm.get("r_frame_rate", "0/0")
            if "/" in fps_str:
                n, d = fps_str.split("/")
                fps = int(n) / int(d) if int(d) != 0 else 0.0
            else:
                fps = float(fps_str)
            result["width"] = w
            result["height"] = h
            result["fps"] = fps
            result["info_txt"] = f"{w}x{h} ({fps:.2f}fps)" if w and h else "오디오 파일"

        result["duration"] = duration
        if duration > 0:
            m, s = divmod(int(duration), 60)
            h_val, m = divmod(m, 60)
            result["len_txt"] = (
                f"{h_val:02d}:{m:02d}:{s:02d}" if h_val > 0 else f"{m:02d}:{s:02d}"
            )
    except Exception:
        pass
    if cache_key and cache_path and result.get("duration", 0.0) > 0:
        _write_cache(cache_key, cache_path, result)
    return _copy_result(result)


def probe_media_many(filepaths: list[str], *, max_workers: int | None = None) -> list[dict]:
    """Probe several media files in input order with bounded parallelism."""
    files = list(filepaths or [])
    if not files:
        return []
    workers = ffprobe_worker_count(len(files)) if max_workers is None else max(1, min(len(files), int(max_workers)))
    if workers <= 1 or len(files) <= 1:
        return [probe_media(path) for path in files]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ffprobe-cache") as executor:
        return list(executor.map(probe_media, files))


def clear_media_probe_cache_memory() -> None:
    with _MEM_CACHE_LOCK:
        _MEM_CACHE.clear()
