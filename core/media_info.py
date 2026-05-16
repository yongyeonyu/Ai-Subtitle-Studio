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
from typing import Any

from core.coerce import safe_float as _safe_float, safe_int as _safe_int
from core.media_fingerprint import media_fingerprint_digest
from core.native_json import loads_json_output, read_json_path
from core.performance import atomic_write_json, ffprobe_worker_count, media_probe_cache_dir
from core.platform_compat import ffprobe_binary, hidden_subprocess_kwargs

try:
    from core.native_swift_media_info import normalize_probe_json_via_swift
except Exception:
    normalize_probe_json_via_swift = None  # type: ignore[assignment]

_CACHE_SCHEMA = 1
_MEDIA_PROBE_MEM_CACHE_MAX = 384
_FINGERPRINT_MEM_CACHE_MAX = 384
_MEM_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_FINGERPRINT_CACHE: "OrderedDict[str, tuple[int, int, str, Path]]" = OrderedDict()
_MEM_CACHE_LOCK = threading.RLock()
_DEFAULT_RESULT = {
    "duration": 0.0,
    "width": 0,
    "height": 0,
    "fps": 0.0,
    "bit_rate": 0,
    "pix_fmt": "",
    "color_space": "",
    "color_transfer": "",
    "color_primaries": "",
    "codec_name": "",
    "profile": "",
    "bits_per_raw_sample": 0,
    "info_txt": "오디오 파일",
    "len_txt": "-",
}


def _default_result() -> dict:
    return dict(_DEFAULT_RESULT)


def _copy_result(info: Any) -> dict:
    return dict(info) if isinstance(info, dict) and info else _default_result()


def copy_media_probe_result(info: Any, *, use_defaults: bool = False) -> dict:
    if use_defaults:
        return _copy_result(info)
    return dict(info) if isinstance(info, dict) and info else {}


def _fingerprint(filepath: str) -> tuple[str, Path] | tuple[None, None]:
    try:
        path = Path(filepath).expanduser()
        stat = path.stat()
        cache_key = str(path.resolve())
        stat_key = (int(getattr(stat, "st_mtime_ns", 0) or 0), int(stat.st_size or 0))
        with _MEM_CACHE_LOCK:
            cached = _FINGERPRINT_CACHE.get(cache_key)
            if cached is not None and cached[0] == stat_key[0] and cached[1] == stat_key[1]:
                _FINGERPRINT_CACHE.move_to_end(cache_key)
                return cached[2], cached[3]
        digest = media_fingerprint_digest(filepath, sample_bytes=512 * 1024, include_samples=True)
        cache_path = media_probe_cache_dir() / f"{digest}.json"
        with _MEM_CACHE_LOCK:
            _FINGERPRINT_CACHE[cache_key] = (stat_key[0], stat_key[1], digest, cache_path)
            _FINGERPRINT_CACHE.move_to_end(cache_key)
            while len(_FINGERPRINT_CACHE) > _FINGERPRINT_MEM_CACHE_MAX:
                _FINGERPRINT_CACHE.popitem(last=False)
        return digest, cache_path
    except Exception:
        return None, None


def _parse_fps(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    if "/" in text:
        numerator_text, denominator_text = text.split("/", 1)
        denominator = _safe_float(denominator_text, 0.0)
        if denominator <= 0.0:
            return 0.0
        return _safe_float(numerator_text, 0.0) / denominator
    return _safe_float(text, 0.0)


def _duration_text(duration: float) -> str:
    total_seconds = max(0, int(duration or 0.0))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _normalize_probe_output_text(output_text: Any) -> dict:
    text = str(output_text or "")
    if normalize_probe_json_via_swift is not None and text:
        try:
            native = normalize_probe_json_via_swift(text)
        except Exception:
            native = None
        if isinstance(native, dict):
            return native
    return _normalize_probe_payload(loads_json_output(text, default={}))


def _normalize_probe_payload(payload: Any) -> dict:
    result = _default_result()
    if not isinstance(payload, dict):
        return result
    fmt = payload.get("format")
    fmt_dict = fmt if isinstance(fmt, dict) else {}
    duration = _safe_float(fmt_dict.get("duration"), 0.0)
    result["bit_rate"] = max(0, _safe_int(fmt_dict.get("bit_rate"), 0))

    streams = payload.get("streams")
    stream = streams[0] if isinstance(streams, list) and streams and isinstance(streams[0], dict) else {}
    if stream:
        if duration <= 0.0:
            duration = _safe_float(stream.get("duration"), 0.0)
        width = max(0, _safe_int(stream.get("width"), 0))
        height = max(0, _safe_int(stream.get("height"), 0))
        fps = _parse_fps(stream.get("r_frame_rate")) or _parse_fps(stream.get("avg_frame_rate"))
        result["width"] = width
        result["height"] = height
        result["fps"] = fps
        result["bit_rate"] = max(0, _safe_int(stream.get("bit_rate"), _safe_int(fmt_dict.get("bit_rate"), 0)))
        result["pix_fmt"] = str(stream.get("pix_fmt", "") or "").strip()
        result["color_space"] = str(stream.get("color_space", "") or "").strip()
        result["color_transfer"] = str(stream.get("color_transfer", "") or "").strip()
        result["color_primaries"] = str(stream.get("color_primaries", "") or "").strip()
        result["codec_name"] = str(stream.get("codec_name", "") or "").strip()
        result["profile"] = str(stream.get("profile", "") or "").strip()
        result["bits_per_raw_sample"] = max(0, _safe_int(stream.get("bits_per_raw_sample"), 0))
        if width and height:
            result["info_txt"] = f"{width}x{height} ({fps:.2f}fps)"

    result["duration"] = duration
    if duration > 0.0:
        result["len_txt"] = _duration_text(duration)
    return result


def media_probe_result_has_fields(info: Any) -> bool:
    if not isinstance(info, dict) or not info:
        return False
    return (
        _safe_float(info.get("duration"), 0.0) > 0.0
        or _safe_float(info.get("fps"), 0.0) > 0.0
        or max(0, _safe_int(info.get("width"), 0)) > 0
        or max(0, _safe_int(info.get("height"), 0)) > 0
    )


def _cache_payload(cache_key: str, result: dict) -> dict:
    return {"schema": _CACHE_SCHEMA, "key": cache_key, "result": result}


def _cache_result_from_payload(cache_key: str, payload: Any) -> dict | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != _CACHE_SCHEMA or payload.get("key") != cache_key:
        return None
    result = payload.get("result")
    return _copy_result(result) if isinstance(result, dict) else None


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
    copied = _cache_result_from_payload(cache_key, payload)
    if copied is None:
        return None
    _cache_put(cache_key, copied, assume_owned=True)
    return _copy_result(copied)


def _cache_put(cache_key: str, result: dict, *, assume_owned: bool = False) -> None:
    stored = result if assume_owned else _copy_result(result)
    with _MEM_CACHE_LOCK:
        _MEM_CACHE[cache_key] = stored
        _MEM_CACHE.move_to_end(cache_key)
        while len(_MEM_CACHE) > _MEDIA_PROBE_MEM_CACHE_MAX:
            _MEM_CACHE.popitem(last=False)


def _write_cache(cache_key: str, cache_path: Path, result: dict) -> None:
    try:
        copied = _copy_result(result)
        atomic_write_json(cache_path, _cache_payload(cache_key, copied))
        _cache_put(cache_key, copied, assume_owned=True)
    except Exception:
        pass


def _probe_batch_plan(files: list[str]) -> tuple[list[str], set[str]]:
    unique_files: list[str] = []
    seen: set[str] = set()
    repeated: set[str] = set()
    for path in files:
        if path in seen:
            repeated.add(path)
            continue
        seen.add(path)
        unique_files.append(path)
    return unique_files, repeated


def _probe_worker_total(unique_count: int, max_workers: int | None) -> int:
    if unique_count <= 0:
        return 0
    if max_workers is None:
        return ffprobe_worker_count(unique_count)
    return max(1, min(unique_count, int(max_workers)))


def _probe_unique_result_map(unique_files: list[str], *, max_workers: int | None = None) -> dict[str, dict]:
    if not unique_files:
        return {}
    workers = _probe_worker_total(len(unique_files), max_workers)
    if workers <= 1 or len(unique_files) <= 1:
        return {path: probe_media(path) for path in unique_files}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ffprobe-cache") as executor:
        return dict(zip(unique_files, executor.map(probe_media, unique_files)))


def _ordered_probe_results(
    files: list[str],
    results_by_path: dict[str, dict],
    repeated_paths: set[str],
) -> list[dict]:
    return [
        _copy_result(results_by_path[path]) if path in repeated_paths else results_by_path[path]
        for path in files
    ]


def probe_media_many_lookup(filepaths: list[str], *, max_workers: int | None = None) -> dict[str, dict]:
    """Probe unique media paths and return a copy-safe path->result map."""
    files = list(filepaths or [])
    if not files:
        return {}
    unique_files, _repeated_paths = _probe_batch_plan(files)
    return _probe_unique_result_map(unique_files, max_workers=max_workers)


def _ffprobe_command(filepath: str) -> list[str]:
    return [
        ffprobe_binary(),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,avg_frame_rate,bit_rate,pix_fmt,color_space,color_transfer,color_primaries,codec_name,profile,bits_per_raw_sample:format=duration,bit_rate",
        "-of",
        "json",
        filepath,
    ]


def probe_media(filepath: str, *, use_cache: bool = True) -> dict:
    """
    Returns: {duration, width, height, fps, bit_rate, pix_fmt, color_space, color_transfer, color_primaries, codec_name, profile, bits_per_raw_sample, info_txt, len_txt}
    """
    cache_key, cache_path = _fingerprint(filepath) if use_cache else (None, None)
    if cache_key and cache_path:
        cached = _read_cache(cache_key, cache_path)
        if cached is not None:
            return cached

    try:
        proc = subprocess.run(
            _ffprobe_command(filepath),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            **hidden_subprocess_kwargs(),
        )
        result = _normalize_probe_output_text(proc.stdout)
    except Exception:
        result = _default_result()
    if cache_key and cache_path and result.get("duration", 0.0) > 0:
        _write_cache(cache_key, cache_path, result)
    return result


def probe_media_many(filepaths: list[str], *, max_workers: int | None = None) -> list[dict]:
    """Probe several media files in input order with bounded parallelism."""
    files = list(filepaths or [])
    if not files:
        return []
    unique_files, repeated_paths = _probe_batch_plan(files)
    unique_only = not repeated_paths
    workers = _probe_worker_total(len(unique_files), max_workers)
    if workers <= 1 or len(unique_files) <= 1:
        if unique_only:
            return [probe_media(path) for path in files]
        results_by_path = _probe_unique_result_map(unique_files, max_workers=workers)
    else:
        if unique_only:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ffprobe-cache") as executor:
                return list(executor.map(probe_media, files))
        results_by_path = _probe_unique_result_map(unique_files, max_workers=workers)
    return _ordered_probe_results(files, results_by_path, repeated_paths)


def clear_media_probe_cache_memory() -> None:
    with _MEM_CACHE_LOCK:
        _MEM_CACHE.clear()
