from __future__ import annotations

"""Optional C++ helpers for native subtitle segment invariant summaries."""

import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import threading
from typing import Any

_FALSE_VALUES = {"0", "false", "off", "no"}
_BUILD_LOCK = threading.Lock()


def _env_enabled(name: str, default: str = "1") -> bool:
    value = str(os.environ.get(name, default) or default).strip().lower()
    return value not in _FALSE_VALUES


def _extension_suffix() -> str:
    return str(sysconfig.get_config_var("EXT_SUFFIX") or ".so")


def _source_path() -> Path:
    return Path(__file__).resolve().with_name("native") / "_native_subtitle_segments.cpp"


def _extension_path() -> Path:
    return Path(__file__).resolve().with_name(f"_native_subtitle_segments{_extension_suffix()}")


def _compiler_path() -> str | None:
    configured = str(os.environ.get("CXX", "") or "").strip()
    if configured:
        return configured
    for name in ("clang++", "c++", "g++"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _compile_native_extension() -> bool:
    if not _env_enabled("AI_SUBTITLE_NATIVE_SEGMENTS", "1"):
        return False
    if not _env_enabled("AI_SUBTITLE_NATIVE_SEGMENTS_BUILD", "1"):
        return False

    source = _source_path()
    output = _extension_path()
    if not source.exists():
        return output.exists()
    if output.exists() and output.stat().st_mtime >= source.stat().st_mtime:
        return True

    compiler = _compiler_path()
    include_dir = sysconfig.get_paths().get("include")
    if not compiler or not include_dir:
        return output.exists()

    with _BUILD_LOCK:
        if output.exists() and output.stat().st_mtime >= source.stat().st_mtime:
            return True

        tmp_output = output.with_name(f"{output.name}.tmp")
        cmd = [
            compiler,
            "-O3",
            "-std=c++17",
            "-shared",
            "-fPIC",
            "-I",
            str(include_dir),
            str(source),
            "-o",
            str(tmp_output),
        ]
        if sys.platform == "darwin":
            cmd.extend(["-undefined", "dynamic_lookup"])
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            os.replace(tmp_output, output)
            return True
        except Exception:
            try:
                tmp_output.unlink()
            except OSError:
                pass
            return output.exists()


def _load_native_module():
    if not _env_enabled("AI_SUBTITLE_NATIVE_SEGMENTS", "1"):
        return None
    _compile_native_extension()
    try:
        return importlib.import_module("core._native_subtitle_segments")
    except Exception:
        return None


_native = _load_native_module()

HAS_NATIVE_SUBTITLE_SEGMENTS = _native is not None


def native_subtitle_segments_enabled() -> bool:
    if _native is None:
        return False
    return _env_enabled("AI_SUBTITLE_NATIVE_SEGMENTS", "1")


def _segment_vectors(rows: list[dict[str, Any]]) -> tuple[list[float], list[float], list[int]]:
    starts: list[float] = []
    ends: list[float] = []
    text_lengths: list[int] = []
    for row in list(rows or []):
        try:
            start = float(row.get("start", 0.0) or 0.0)
        except Exception:
            start = 0.0
        try:
            end = float(row.get("end", start) or start)
        except Exception:
            end = start
        text = str(row.get("text") or "").strip()
        starts.append(start)
        ends.append(end)
        text_lengths.append(len(text))
    return starts, ends, text_lengths


def _python_segment_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    starts, ends, text_lengths = _segment_vectors(rows)
    count = min(len(starts), len(ends), len(text_lengths))
    invalid = 0
    non_monotonic = 0
    overlaps = 0
    empty = 0
    total_duration = 0.0
    max_gap = 0.0
    previous_start: float | None = None
    previous_end: float | None = None
    for idx in range(count):
        start = starts[idx]
        end = ends[idx]
        chars = text_lengths[idx]
        if chars <= 0:
            empty += 1
        if end > start:
            total_duration += end - start
        else:
            invalid += 1
        if previous_start is not None and start < previous_start:
            non_monotonic += 1
        if previous_end is not None:
            if start < previous_end:
                overlaps += 1
            else:
                max_gap = max(max_gap, start - previous_end)
        previous_start = start
        previous_end = end
    total_chars = sum(text_lengths[:count])
    return {
        "schema": "ai_subtitle_studio.subtitle_segments.summary.v1",
        "segment_count": count,
        "invalid_duration_count": invalid,
        "non_monotonic_count": non_monotonic,
        "overlap_count": overlaps,
        "empty_text_count": empty,
        "total_duration": round(total_duration, 6),
        "first_start": round(starts[0], 6) if count else 0.0,
        "last_end": round(ends[count - 1], 6) if count else 0.0,
        "max_gap": round(max_gap, 6),
        "max_chars": max(text_lengths[:count], default=0),
        "avg_chars": round(total_chars / count, 6) if count else 0.0,
        "stable_for_save_reopen": invalid == 0 and non_monotonic == 0,
        "native_backend": "python",
    }


def segment_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if native_subtitle_segments_enabled():
        try:
            starts, ends, text_lengths = _segment_vectors(rows)
            result = _native.segment_summary(starts, ends, text_lengths)
            if isinstance(result, dict):
                return dict(result)
        except Exception:
            pass
    return _python_segment_summary(rows)


__all__ = [
    "HAS_NATIVE_SUBTITLE_SEGMENTS",
    "native_subtitle_segments_enabled",
    "segment_summary",
]
