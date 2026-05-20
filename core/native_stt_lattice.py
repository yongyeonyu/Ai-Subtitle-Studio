from __future__ import annotations

"""Optional native helpers for STT lattice word matching."""

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
    return Path(__file__).resolve().with_name("native") / "_native_stt_lattice.cpp"


def _extension_path() -> Path:
    return Path(__file__).resolve().with_name(f"_native_stt_lattice{_extension_suffix()}")


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
    if not _env_enabled("AI_SUBTITLE_NATIVE_STT_LATTICE", "1"):
        return False
    if not _env_enabled("AI_SUBTITLE_NATIVE_STT_LATTICE_BUILD", "1"):
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
    if not _env_enabled("AI_SUBTITLE_NATIVE_STT_LATTICE", "1"):
        return None
    _compile_native_extension()
    try:
        return importlib.import_module("core._native_stt_lattice")
    except Exception:
        return None


_native = _load_native_module()

HAS_NATIVE_STT_LATTICE = _native is not None


def native_stt_lattice_enabled() -> bool:
    if _native is None:
        return False
    return _env_enabled("AI_SUBTITLE_NATIVE_STT_LATTICE", "1")


def stt_lattice_backend() -> str:
    return "cpp" if native_stt_lattice_enabled() else "python"


def best_word_match(
    *,
    anchor_start: float,
    anchor_end: float,
    word_starts: list[float],
    word_ends: list[float],
    textual_scores: list[float],
    used_indices: set[int] | list[int] | tuple[int, ...] | None,
    min_match_score: float,
) -> tuple[int | None, float] | None:
    if not native_stt_lattice_enabled():
        return None
    try:
        values = _native.best_word_match(
            float(anchor_start),
            float(anchor_end),
            [float(item) for item in list(word_starts or [])],
            [float(item) for item in list(word_ends or [])],
            [float(item) for item in list(textual_scores or [])],
            sorted(int(item) for item in (used_indices or ()) if int(item) >= 0),
            float(min_match_score),
        )
        if not isinstance(values, tuple) or len(values) != 2:
            return None
        idx = int(values[0])
        score = float(values[1] or 0.0)
        if idx < 0:
            return None, score
        return idx, score
    except Exception:
        return None


__all__ = [
    "HAS_NATIVE_STT_LATTICE",
    "best_word_match",
    "native_stt_lattice_enabled",
    "stt_lattice_backend",
]
