from __future__ import annotations

"""Optional C++ helpers for native subtitle segment invariant summaries."""

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
_SEGMENT_FEED_SIGNATURE_OFFSET = 1469598103934665603
_SEGMENT_FEED_SIGNATURE_PRIME = 1099511628211
_UINT64_MASK = 0xFFFFFFFFFFFFFFFF


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


def _milliseconds(value: float) -> int:
    if not math.isfinite(value):
        return 0
    scaled = value * 1000.0
    if scaled >= 0:
        return int(math.floor(scaled + 0.5))
    return int(math.ceil(scaled - 0.5))


def _mix_signature_value(signature: int, value: int) -> int:
    return ((signature ^ (int(value) & _UINT64_MASK)) * _SEGMENT_FEED_SIGNATURE_PRIME) & _UINT64_MASK


def _text_signature(text: str) -> int:
    signature = _SEGMENT_FEED_SIGNATURE_OFFSET
    for byte in text.encode("utf-8"):
        signature = _mix_signature_value(signature, byte)
    return signature


def _segment_feed_signature(starts: list[float], ends: list[float], text_lengths: list[int], texts: list[str], count: int) -> str:
    signature = _SEGMENT_FEED_SIGNATURE_OFFSET
    for idx in range(count):
        # 변경 금지: C++/Swift와 같은 start/end ms, text length, UTF-8 text hash 순서로 final segment feed를 검증합니다.
        # 자막 에디터/타임라인/저장 SRT가 갈라질 때 이 값을 비교해 데이터 drift 지점을 좁힙니다.
        for value in (
            _milliseconds(starts[idx]),
            _milliseconds(ends[idx]),
            text_lengths[idx],
            _text_signature(texts[idx]),
        ):
            signature = _mix_signature_value(signature, value)
    return f"{signature:016x}"


def _segment_vectors(rows: list[dict[str, Any]]) -> tuple[list[float], list[float], list[int], list[str]]:
    starts: list[float] = []
    ends: list[float] = []
    text_lengths: list[int] = []
    texts: list[str] = []
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
        texts.append(text)
    return starts, ends, text_lengths, texts


def _apply_final_stability_contract(summary: dict[str, Any]) -> dict[str, Any]:
    result = dict(summary or {})
    try:
        invalid = int(result.get("invalid_duration_count", 0) or 0)
        non_monotonic = int(result.get("non_monotonic_count", 0) or 0)
        overlaps = int(result.get("overlap_count", 0) or 0)
    except Exception:
        return result
    result["stable_for_save_reopen"] = invalid == 0 and non_monotonic == 0 and overlaps == 0
    return result


def _python_segment_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    starts, ends, text_lengths, texts = _segment_vectors(rows)
    count = min(len(starts), len(ends), len(text_lengths))
    invalid = 0
    non_monotonic = 0
    overlaps = 0
    empty = 0
    total_duration = 0.0
    max_gap = 0.0
    max_gap_index = -1
    max_overlap = 0.0
    max_overlap_index = -1
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
                overlap = previous_end - start
                # 변경 금지: Swift/C++와 같은 현재 세그먼트 index 기준으로 최악 겹침 위치를 기록합니다.
                # 자막 세그먼트와 에디터 row가 갈라지는 X5/마카오 구간 추적용 계약입니다.
                if overlap > max_overlap:
                    max_overlap = overlap
                    max_overlap_index = idx
            else:
                gap = start - previous_end
                if gap > max_gap:
                    max_gap = gap
                    max_gap_index = idx
        previous_start = start
        previous_end = end
    total_chars = sum(text_lengths[:count])
    return _apply_final_stability_contract({
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
        "max_gap_index": max_gap_index,
        "max_overlap": round(max_overlap, 6),
        "max_overlap_index": max_overlap_index,
        "max_chars": max(text_lengths[:count], default=0),
        "avg_chars": round(total_chars / count, 6) if count else 0.0,
        "stable_for_save_reopen": False,
        "segment_feed_signature": _segment_feed_signature(starts, ends, text_lengths, texts, count),
        "native_backend": "python",
    })


def segment_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if native_subtitle_segments_enabled():
        try:
            starts, ends, text_lengths, texts = _segment_vectors(rows)
            result = _native.segment_summary(starts, ends, text_lengths, texts)
            if isinstance(result, dict):
                return _apply_final_stability_contract(result)
        except Exception:
            pass
    return _python_segment_summary(rows)


__all__ = [
    "HAS_NATIVE_SUBTITLE_SEGMENTS",
    "native_subtitle_segments_enabled",
    "segment_summary",
]
