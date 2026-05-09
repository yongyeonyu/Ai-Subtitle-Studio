from __future__ import annotations

"""Optional native C++ helpers for cut-boundary verification."""

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
    return Path(__file__).resolve().with_name("native") / "_native_cut_boundary.cpp"


def _extension_path() -> Path:
    return Path(__file__).resolve().with_name(f"_native_cut_boundary{_extension_suffix()}")


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
    if not _env_enabled("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", "1"):
        return False
    if not _env_enabled("AI_SUBTITLE_NATIVE_CUT_BOUNDARY_BUILD", "1"):
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
            except Exception:
                pass
            return output.exists()


def _load_native_module():
    if not _env_enabled("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", "1"):
        return None
    _compile_native_extension()
    try:
        return importlib.import_module("core._native_cut_boundary")
    except Exception:  # pragma: no cover - exercised when extension is unavailable.
        return None


_native = _load_native_module()


HAS_NATIVE_CUT_BOUNDARY = _native is not None


def native_cut_boundary_enabled() -> bool:
    if _native is None:
        return False
    return _env_enabled("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", "1")


def cut_boundary_backend() -> str:
    return "cpp" if native_cut_boundary_enabled() else "python"


def delta_bytes(left: bytes, right: bytes, *, target_samples: int = 64) -> float | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        return float(_native.delta_bytes(left, right, int(target_samples or 64)))
    except Exception:
        return None


def gray_delta(
    prev_thumb: Any,
    next_thumb: Any,
    *,
    region_threshold: float,
    target_samples: int,
) -> tuple[float, int, list[float]] | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        score, hits, deltas = _native.gray_delta(
            prev_thumb,
            next_thumb,
            float(region_threshold),
            int(target_samples or 64),
        )
        return float(score), int(hits), [float(item) for item in list(deltas or [])]
    except Exception:
        return None


def color_avg_delta(
    prev_avg: Any,
    next_avg: Any,
    *,
    threshold: float,
    weight_luma: float,
    weight_chroma: float,
) -> tuple[float, int, list[float]] | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        score, hits, deltas = _native.color_avg_delta(
            prev_avg,
            next_avg,
            float(threshold),
            float(weight_luma),
            float(weight_chroma),
        )
        return float(score), int(hits), [float(item) for item in list(deltas or [])]
    except Exception:
        return None


def dense_flow_pair_metrics(
    prev_gray: Any,
    next_gray: Any,
    flow: Any,
    *,
    diff_threshold: float,
) -> dict[str, float] | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        import numpy as np

        prev_arr = np.ascontiguousarray(prev_gray, dtype=np.uint8)
        next_arr = np.ascontiguousarray(next_gray, dtype=np.uint8)
        flow_arr = np.ascontiguousarray(flow, dtype=np.float32)
        if prev_arr.ndim != 2 or next_arr.shape != prev_arr.shape:
            return None
        if flow_arr.ndim != 3 or flow_arr.shape[:2] != prev_arr.shape or flow_arr.shape[2] < 2:
            return None
        values = _native.dense_flow_pair_metrics(
            prev_arr,
            next_arr,
            flow_arr,
            float(diff_threshold),
        )
        if not isinstance(values, dict):
            return None
        return {str(key): float(value) for key, value in values.items()}
    except Exception:
        return None


def waveform_peaks_f32le(
    raw: bytes | bytearray | memoryview | None,
    *,
    sample_rate: int,
    points_per_second: int,
    duration: float | None = None,
):
    if not raw or not native_cut_boundary_enabled():
        return None
    try:
        import numpy as np

        peaks_bytes, dur = _native.waveform_peaks_f32le(
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


def interval_overlaps(
    segment_starts: Any,
    segment_ends: Any,
    vad_starts: Any,
    vad_ends: Any,
) -> list[float] | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        values = _native.interval_overlaps(segment_starts, segment_ends, vad_starts, vad_ends)
        return [float(item) for item in list(values or [])]
    except Exception:
        return None


def word_split_groups(
    starts: Any,
    ends: Any,
    char_counts: Any,
    natural_breaks: Any,
    vad_indexes: Any,
    *,
    max_chars: int,
    max_duration: float,
    max_cps: float,
    min_duration: float,
    gap_break_sec: float,
    word_gap_break_sec: float,
) -> list[tuple[int, int]] | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        values = _native.word_split_groups(
            starts,
            ends,
            char_counts,
            natural_breaks,
            vad_indexes,
            int(max_chars),
            float(max_duration),
            float(max_cps),
            float(min_duration),
            float(gap_break_sec),
            float(word_gap_break_sec),
        )
        groups: list[tuple[int, int]] = []
        for item in list(values or []):
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                return None
            groups.append((int(item[0]), int(item[1])))
        return groups
    except Exception:
        return None


def llm_macro_group_ranges(
    cut_before: Any,
    needs_llm: Any,
    *,
    min_rows: int,
    max_rows: int,
) -> list[tuple[int, int, bool, int]] | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        values = _native.llm_macro_group_ranges(
            cut_before,
            needs_llm,
            int(min_rows),
            int(max_rows),
        )
        groups: list[tuple[int, int, bool, int]] = []
        for item in list(values or []):
            if not isinstance(item, (list, tuple)) or len(item) < 4:
                return None
            groups.append((int(item[0]), int(item[1]), bool(item[2]), int(item[3])))
        return groups
    except Exception:
        return None
