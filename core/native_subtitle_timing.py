from __future__ import annotations

"""Optional C++ timing metrics for subtitle benchmark scoring."""

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
    return Path(__file__).resolve().with_name("native") / "_native_subtitle_timing.cpp"


def _extension_path() -> Path:
    return Path(__file__).resolve().with_name(f"_native_subtitle_timing{_extension_suffix()}")


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
    if not _env_enabled("AI_SUBTITLE_NATIVE_TIMING_METRICS", "1"):
        return False
    if not _env_enabled("AI_SUBTITLE_NATIVE_TIMING_METRICS_BUILD", "1"):
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
    if not _env_enabled("AI_SUBTITLE_NATIVE_TIMING_METRICS", "1"):
        return None
    _compile_native_extension()
    try:
        return importlib.import_module("core._native_subtitle_timing")
    except Exception:
        return None


_native = _load_native_module()

HAS_NATIVE_SUBTITLE_TIMING = _native is not None


def native_subtitle_timing_enabled() -> bool:
    if _native is None:
        return False
    return _env_enabled("AI_SUBTITLE_NATIVE_TIMING_METRICS", "1")


def subtitle_timing_backend() -> str:
    return "cpp" if native_subtitle_timing_enabled() else "python"


def _times(rows: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    starts: list[float] = []
    ends: list[float] = []
    for row in rows:
        if not str(row.get("text", "") or "").strip():
            continue
        start = float(row.get("start", 0.0) or 0.0)
        end = float(row.get("end", start) or start)
        starts.append(start)
        ends.append(end)
    return starts, ends


def timing_metrics(
    hypothesis: list[dict[str, Any]],
    reference: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not native_subtitle_timing_enabled():
        return None
    try:
        hyp_starts, hyp_ends = _times(list(hypothesis or []))
        ref_starts, ref_ends = _times(list(reference or []))
        result = _native.timing_metrics(hyp_starts, hyp_ends, ref_starts, ref_ends)
        if not isinstance(result, dict):
            return None
        return {
            "timing_mae_sec": float(result.get("timing_mae_sec", 0.0) or 0.0),
            "overlap_score": float(result.get("overlap_score", 0.0) or 0.0),
            "matched_pairs": int(result.get("matched_pairs", 0) or 0),
            "native_backend": "cpp",
        }
    except Exception:
        return None


__all__ = [
    "HAS_NATIVE_SUBTITLE_TIMING",
    "native_subtitle_timing_enabled",
    "subtitle_timing_backend",
    "timing_metrics",
]
