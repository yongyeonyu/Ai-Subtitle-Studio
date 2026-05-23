from __future__ import annotations

"""Optional C++ helpers for native subtitle waveform downsampling."""

import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import threading
from typing import Any

import numpy as np

_FALSE_VALUES = {"0", "false", "off", "no"}
_BUILD_LOCK = threading.Lock()


def _env_enabled(name: str, default: str = "1") -> bool:
    value = str(os.environ.get(name, default) or default).strip().lower()
    return value not in _FALSE_VALUES


def _extension_suffix() -> str:
    return str(sysconfig.get_config_var("EXT_SUFFIX") or ".so")


def _source_path() -> Path:
    return Path(__file__).resolve().with_name("native") / "_native_subtitle_waveform.cpp"


def _extension_path() -> Path:
    return Path(__file__).resolve().with_name(f"_native_subtitle_waveform{_extension_suffix()}")


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
    if not _env_enabled("AI_SUBTITLE_NATIVE_WAVEFORM", "1"):
        return False
    if not _env_enabled("AI_SUBTITLE_NATIVE_WAVEFORM_BUILD", "1"):
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
    if not _env_enabled("AI_SUBTITLE_NATIVE_WAVEFORM", "1"):
        return None
    _compile_native_extension()
    try:
        return importlib.import_module("core._native_subtitle_waveform")
    except Exception:
        return None


_native = _load_native_module()

HAS_NATIVE_SUBTITLE_WAVEFORM = _native is not None


def native_subtitle_waveform_enabled() -> bool:
    if _native is None:
        return False
    return _env_enabled("AI_SUBTITLE_NATIVE_WAVEFORM", "1")


def downsample_f32le(
    raw: bytes | bytearray | memoryview | None,
    *,
    sample_rate: int,
    points_per_second: int,
    duration: float | None = None,
) -> tuple[np.ndarray, float] | None:
    if not raw or not native_subtitle_waveform_enabled():
        return None
    try:
        peaks_bytes, dur = _native.downsample_f32le(
            raw,
            int(sample_rate or 2000),
            int(points_per_second or 100),
            float(duration or 0.0),
        )
        peaks = np.frombuffer(peaks_bytes or b"", dtype=np.float32).copy()
        dur = float(dur or 0.0)
    except Exception:
        return None
    if peaks.size <= 0 or dur <= 0.0:
        return None
    return peaks, dur


def waveform_summary(values: Any, *, speech_threshold: float = 0.02) -> dict[str, Any] | None:
    if not native_subtitle_waveform_enabled():
        return None
    try:
        arr = np.ascontiguousarray(values, dtype=np.float32)
        result = _native.waveform_summary(memoryview(arr), float(speech_threshold or 0.0))
        if not isinstance(result, dict):
            return None
        return dict(result)
    except Exception:
        return None


__all__ = [
    "HAS_NATIVE_SUBTITLE_WAVEFORM",
    "downsample_f32le",
    "native_subtitle_waveform_enabled",
    "waveform_summary",
]
