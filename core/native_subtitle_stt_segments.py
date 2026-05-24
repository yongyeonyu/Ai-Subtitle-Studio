from __future__ import annotations

"""Optional C++ helpers for STT1/STT2 subtitle lane summaries."""

import importlib
import math
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
_TIMELINE_FEED_SIGNATURE_OFFSET = 1469598103934665603
_TIMELINE_FEED_SIGNATURE_PRIME = 1099511628211
_UINT64_MASK = 0xFFFFFFFFFFFFFFFF


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


def _milliseconds(value: float) -> int:
    if not math.isfinite(value):
        return 0
    scaled = value * 1000.0
    if scaled >= 0:
        return int(math.floor(scaled + 0.5))
    return int(math.ceil(scaled - 0.5))


def _mix_signature_value(signature: int, value: int) -> int:
    return ((signature ^ (int(value) & _UINT64_MASK)) * _TIMELINE_FEED_SIGNATURE_PRIME) & _UINT64_MASK


def _stable_timeline_feed_signature(
    starts: list[float],
    ends: list[float],
    source_codes: list[int],
    recheck_flags: list[int],
    precision_flags: list[int],
    secondary_hint_flags: list[int],
    count: int,
) -> str:
    signature = _TIMELINE_FEED_SIGNATURE_OFFSET
    for idx in range(count):
        # 변경 금지: C++/Swift와 같은 순서/반올림/uint64 overflow로 STT lane 입력 동일성을 검증합니다.
        # 이 값이 바뀌면 STT 후보, 자막 에디터, 타임라인 세그먼트 싱크 원인 추적이 다시 흐려집니다.
        for value in (
            _milliseconds(starts[idx]),
            _milliseconds(ends[idx]),
            source_codes[idx],
            1 if recheck_flags[idx] else 0,
            1 if precision_flags[idx] else 0,
            1 if secondary_hint_flags[idx] else 0,
        ):
            signature = _mix_signature_value(signature, value)
    return f"{signature:016x}"


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
    has_stt2 = False
    stt2_first_start = 0.0
    stt2_last_end = 0.0
    current_stt2_run_start: float | None = None
    current_stt2_run_end: float | None = None
    current_stt2_run_count = 0
    longest_stt2_run_sec = 0.0
    longest_stt2_run_start = 0.0
    longest_stt2_run_end = 0.0
    longest_stt2_run_count = 0

    def flush_stt2_run() -> None:
        nonlocal current_stt2_run_start
        nonlocal current_stt2_run_end
        nonlocal current_stt2_run_count
        nonlocal longest_stt2_run_sec
        nonlocal longest_stt2_run_start
        nonlocal longest_stt2_run_end
        nonlocal longest_stt2_run_count
        if current_stt2_run_start is None or current_stt2_run_end is None:
            return
        run_sec = max(0.0, current_stt2_run_end - current_stt2_run_start)
        if run_sec > longest_stt2_run_sec or (
            abs(run_sec - longest_stt2_run_sec) <= 0.000_000_001
            and current_stt2_run_count > longest_stt2_run_count
        ):
            longest_stt2_run_sec = run_sec
            longest_stt2_run_start = current_stt2_run_start
            longest_stt2_run_end = current_stt2_run_end
            longest_stt2_run_count = current_stt2_run_count
        current_stt2_run_start = None
        current_stt2_run_end = None
        current_stt2_run_count = 0

    for idx in range(count):
        start = starts[idx]
        end = ends[idx]
        source = source_codes[idx]
        is_stt2_source = source in {2, 3}
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
        # 변경 금지: STT2/RECHECK 연속 선택 구간은 품질 정책 변경이 아니라 artifact 진단값입니다.
        # Swift/C++와 동일하게 연속 STT2 계열 row만 묶어 자막-에디터 싱크 원인 추적에 사용합니다.
        if is_stt2_source:
            if not has_stt2:
                has_stt2 = True
                stt2_first_start = start
                stt2_last_end = end
            else:
                stt2_last_end = max(stt2_last_end, end)
            if current_stt2_run_start is None:
                current_stt2_run_start = start
                current_stt2_run_end = end
                current_stt2_run_count = 1
            else:
                current_stt2_run_end = max(current_stt2_run_end if current_stt2_run_end is not None else end, end)
                current_stt2_run_count += 1
        else:
            flush_stt2_run()
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
    flush_stt2_run()
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
        "stt2_first_start": round(stt2_first_start if has_stt2 else 0.0, 6),
        "stt2_last_end": round(stt2_last_end if has_stt2 else 0.0, 6),
        "longest_stt2_run_sec": round(longest_stt2_run_sec, 6),
        "longest_stt2_run_start": round(longest_stt2_run_start, 6),
        "longest_stt2_run_end": round(longest_stt2_run_end, 6),
        "longest_stt2_run_count": longest_stt2_run_count,
        "stt2_active": stt2_selected > 0 or recheck_applied > 0,
        "selective_recheck_active": recheck_applied > 0,
        "stable_for_timeline_feed": invalid == 0 and non_monotonic == 0,
        "timeline_feed_signature": _stable_timeline_feed_signature(
            starts,
            ends,
            source_codes,
            recheck_flags,
            precision_flags,
            secondary_hint_flags,
            count,
        ),
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
