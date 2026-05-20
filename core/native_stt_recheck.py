from __future__ import annotations

"""Optional native helpers for STT recheck range planning."""

import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import threading

_FALSE_VALUES = {"0", "false", "off", "no"}
_BUILD_LOCK = threading.Lock()


def _env_enabled(name: str, default: str = "1") -> bool:
    value = str(os.environ.get(name, default) or default).strip().lower()
    return value not in _FALSE_VALUES


def _extension_suffix() -> str:
    return str(sysconfig.get_config_var("EXT_SUFFIX") or ".so")


def _source_path() -> Path:
    return Path(__file__).resolve().with_name("native") / "_native_stt_recheck.cpp"


def _extension_path() -> Path:
    return Path(__file__).resolve().with_name(f"_native_stt_recheck{_extension_suffix()}")


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
    if not _env_enabled("AI_SUBTITLE_NATIVE_STT_RECHECK", "1"):
        return False
    if not _env_enabled("AI_SUBTITLE_NATIVE_STT_RECHECK_BUILD", "1"):
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
    if not _env_enabled("AI_SUBTITLE_NATIVE_STT_RECHECK", "1"):
        return None
    _compile_native_extension()
    try:
        return importlib.import_module("core._native_stt_recheck")
    except Exception:
        return None


_native = _load_native_module()

HAS_NATIVE_STT_RECHECK = _native is not None


def native_stt_recheck_enabled() -> bool:
    if _native is None:
        return False
    return _env_enabled("AI_SUBTITLE_NATIVE_STT_RECHECK", "1")


def stt_recheck_backend() -> str:
    return "cpp" if native_stt_recheck_enabled() else "python"


def uncovered_vad_indices(
    *,
    vad_starts: list[float],
    vad_ends: list[float],
    primary_starts: list[float],
    primary_ends: list[float],
    primary_nonempty: list[int] | list[bool],
    min_duration: float,
    overlap_threshold: float,
) -> list[int] | None:
    if not native_stt_recheck_enabled():
        return None
    try:
        values = _native.uncovered_vad_indices(
            [float(item) for item in list(vad_starts or [])],
            [float(item) for item in list(vad_ends or [])],
            [float(item) for item in list(primary_starts or [])],
            [float(item) for item in list(primary_ends or [])],
            [1 if bool(item) else 0 for item in list(primary_nonempty or [])],
            float(min_duration),
            float(overlap_threshold),
        )
        if not isinstance(values, list):
            return None
        return [int(item) for item in values if int(item) >= 0]
    except Exception:
        return None


def overlap_segment_groups(
    *,
    range_starts: list[float],
    range_ends: list[float],
    segment_starts: list[float],
    segment_ends: list[float],
    min_overlap_ratio: float,
) -> list[list[int]] | None:
    if not native_stt_recheck_enabled():
        return None
    try:
        values = _native.overlap_segment_groups(
            [float(item) for item in list(range_starts or [])],
            [float(item) for item in list(range_ends or [])],
            [float(item) for item in list(segment_starts or [])],
            [float(item) for item in list(segment_ends or [])],
            float(min_overlap_ratio),
        )
        if not isinstance(values, list):
            return None
        groups: list[list[int]] = []
        for row in values:
            if not isinstance(row, list):
                return None
            groups.append([int(item) for item in row if int(item) >= 0])
        return groups
    except Exception:
        return None


def overlap_range_components(
    *,
    range_starts: list[float],
    range_ends: list[float],
    min_overlap_ratio: float,
) -> list[list[int]] | None:
    if not native_stt_recheck_enabled():
        return None
    try:
        values = _native.overlap_range_components(
            [float(item) for item in list(range_starts or [])],
            [float(item) for item in list(range_ends or [])],
            float(min_overlap_ratio),
        )
        if not isinstance(values, list):
            return None
        groups: list[list[int]] = []
        for row in values:
            if not isinstance(row, list):
                return None
            groups.append([int(item) for item in row if int(item) >= 0])
        return groups
    except Exception:
        return None


def low_score_primary_indices(
    *,
    primary_scores: list[float],
    primary_nonempty: list[int] | list[bool],
    threshold: float,
) -> list[int] | None:
    if not native_stt_recheck_enabled():
        return None
    try:
        values = _native.low_score_primary_indices(
            [float(item) for item in list(primary_scores or [])],
            [1 if bool(item) else 0 for item in list(primary_nonempty or [])],
            float(threshold),
        )
        if not isinstance(values, list):
            return None
        return [int(item) for item in values if int(item) >= 0]
    except Exception:
        return None


def match_low_score_pair_indices(
    *,
    primary_starts: list[float],
    primary_ends: list[float],
    primary_scores: list[float],
    primary_nonempty: list[int] | list[bool],
    secondary_starts: list[float],
    secondary_ends: list[float],
    secondary_scores: list[float],
    secondary_nonempty: list[int] | list[bool],
    threshold: float,
    overlap_threshold: float,
) -> list[tuple[int, int]] | None:
    if not native_stt_recheck_enabled():
        return None
    try:
        values = _native.match_low_score_pair_indices(
            [float(item) for item in list(primary_starts or [])],
            [float(item) for item in list(primary_ends or [])],
            [float(item) for item in list(primary_scores or [])],
            [1 if bool(item) else 0 for item in list(primary_nonempty or [])],
            [float(item) for item in list(secondary_starts or [])],
            [float(item) for item in list(secondary_ends or [])],
            [float(item) for item in list(secondary_scores or [])],
            [1 if bool(item) else 0 for item in list(secondary_nonempty or [])],
            float(threshold),
            float(overlap_threshold),
        )
        if not isinstance(values, list):
            return None
        pairs: list[tuple[int, int]] = []
        for row in values:
            if not isinstance(row, list) or len(row) < 2:
                return None
            left = int(row[0])
            right = int(row[1])
            if left >= 0 and right >= 0:
                pairs.append((left, right))
        return pairs
    except Exception:
        return None


__all__ = [
    "HAS_NATIVE_STT_RECHECK",
    "low_score_primary_indices",
    "match_low_score_pair_indices",
    "native_stt_recheck_enabled",
    "overlap_range_components",
    "overlap_segment_groups",
    "stt_recheck_backend",
    "uncovered_vad_indices",
]
