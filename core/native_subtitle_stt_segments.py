from __future__ import annotations

"""Optional C++ helpers for STT1/STT2 subtitle lane summaries."""

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
    return Path(__file__).resolve().with_name("native") / "_native_subtitle_stt_segments.cpp"


def _extension_path() -> Path:
    return Path(__file__).resolve().with_name(f"_native_subtitle_stt_segments{_extension_suffix()}")


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
    if not _env_enabled("AI_SUBTITLE_NATIVE_STT_SEGMENTS", "1"):
        return False
    if not _env_enabled("AI_SUBTITLE_NATIVE_STT_SEGMENTS_BUILD", "1"):
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
    if not _env_enabled("AI_SUBTITLE_NATIVE_STT_SEGMENTS", "1"):
        return None
    _compile_native_extension()
    try:
        return importlib.import_module("core._native_subtitle_stt_segments")
    except Exception:
        return None


_native = _load_native_module()

HAS_NATIVE_SUBTITLE_STT_SEGMENTS = _native is not None


def native_subtitle_stt_segments_enabled() -> bool:
    if _native is None:
        return False
    return _env_enabled("AI_SUBTITLE_NATIVE_STT_SEGMENTS", "1")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _source_code(row: dict[str, Any]) -> int:
    for key in ("stt_selected_source", "stt_source", "stt_preview_source", "stt_ensemble_source", "source"):
        label = str(row.get(key) or "").strip().upper()
        if "STT2" in label:
            return 2
        if "RECHECK" in label:
            return 3
        if "STT1" in label:
            return 1
    return 0


def _segment_vectors(rows: list[dict[str, Any]]) -> tuple[list[float], list[float], list[int], list[int], list[int], list[int]]:
    starts: list[float] = []
    ends: list[float] = []
    source_codes: list[int] = []
    recheck_flags: list[int] = []
    precision_flags: list[int] = []
    secondary_hint_flags: list[int] = []
    for row in list(rows or []):
        try:
            start = float(row.get("start", 0.0) or 0.0)
        except Exception:
            start = 0.0
        try:
            end = float(row.get("end", start) or start)
        except Exception:
            end = start
        starts.append(start)
        ends.append(end)
        source_codes.append(_source_code(row))
        recheck_flags.append(1 if _truthy(row.get("stt_recheck_applied")) else 0)
        precision_flags.append(1 if _truthy(row.get("stt_word_precision_applied")) else 0)
        secondary_hint_flags.append(1 if _truthy(row.get("stt_route_secondary_recheck_hint")) else 0)
    return starts, ends, source_codes, recheck_flags, precision_flags, secondary_hint_flags


def _python_stt_segments_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    starts, ends, source_codes, recheck_flags, precision_flags, secondary_hint_flags = _segment_vectors(rows)
    count = min(len(starts), len(ends), len(source_codes), len(recheck_flags), len(precision_flags), len(secondary_hint_flags))
    stt1_selected = 0
    stt2_selected = 0
    recheck_applied = 0
    word_precision = 0
    secondary_hints = 0
    unknown_source = 0
    invalid = 0
    non_monotonic = 0
    overlaps = 0
    source_switches = 0
    total_duration = 0.0
    stt1_duration = 0.0
    stt2_duration = 0.0
    previous_start: float | None = None
    previous_end: float | None = None
    previous_source: int | None = None
    for idx in range(count):
        start = starts[idx]
        end = ends[idx]
        source = source_codes[idx]
        duration = max(0.0, end - start)
        if end > start:
            total_duration += duration
        else:
            invalid += 1
        if previous_start is not None and start < previous_start:
            non_monotonic += 1
        if previous_end is not None and start < previous_end:
            overlaps += 1
        if previous_source is not None and previous_source > 0 and source > 0 and previous_source != source:
            source_switches += 1
        if source == 1:
            stt1_selected += 1
            stt1_duration += duration
        elif source in {2, 3}:
            stt2_selected += 1
            stt2_duration += duration
        else:
            unknown_source += 1
        recheck_applied += 1 if recheck_flags[idx] else 0
        word_precision += 1 if precision_flags[idx] else 0
        secondary_hints += 1 if secondary_hint_flags[idx] else 0
        previous_start = start
        previous_end = end
        previous_source = source
    return {
        "schema": "ai_subtitle_studio.subtitle_stt_segments.summary.v1",
        "segment_count": count,
        "stt1_selected_count": stt1_selected,
        "stt2_selected_count": stt2_selected,
        "recheck_applied_count": recheck_applied,
        "word_precision_count": word_precision,
        "secondary_hint_count": secondary_hints,
        "unknown_source_count": unknown_source,
        "invalid_duration_count": invalid,
        "non_monotonic_count": non_monotonic,
        "overlap_count": overlaps,
        "source_switch_count": source_switches,
        "total_duration": round(total_duration, 6),
        "stt1_duration": round(stt1_duration, 6),
        "stt2_duration": round(stt2_duration, 6),
        "stt2_coverage_ratio": round(stt2_duration / total_duration, 6) if total_duration > 0 else 0.0,
        "stt2_active": stt2_selected > 0 or recheck_applied > 0,
        "selective_recheck_active": recheck_applied > 0,
        "stable_for_timeline_feed": invalid == 0 and non_monotonic == 0,
        "native_backend": "python",
    }


def stt_segments_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if native_subtitle_stt_segments_enabled():
        try:
            result = _native.stt_segments_summary(*_segment_vectors(rows))
            if isinstance(result, dict):
                return dict(result)
        except Exception:
            pass
    return _python_stt_segments_summary(rows)


__all__ = [
    "HAS_NATIVE_SUBTITLE_STT_SEGMENTS",
    "native_subtitle_stt_segments_enabled",
    "stt_segments_summary",
]
