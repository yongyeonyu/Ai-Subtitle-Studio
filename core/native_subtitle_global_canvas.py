from __future__ import annotations

"""Optional C++ helpers for subtitle global-canvas occupancy summaries."""

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


def _env_enabled(name: str, default: str = "1") -> bool:
    value = str(os.environ.get(name, default) or default).strip().lower()
    return value not in _FALSE_VALUES


def _extension_suffix() -> str:
    return str(sysconfig.get_config_var("EXT_SUFFIX") or ".so")


def _source_path() -> Path:
    return Path(__file__).resolve().with_name("native") / "_native_subtitle_global_canvas.cpp"


def _extension_path() -> Path:
    return Path(__file__).resolve().with_name(f"_native_subtitle_global_canvas{_extension_suffix()}")


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
    if not _env_enabled("AI_SUBTITLE_NATIVE_GLOBAL_CANVAS", "1"):
        return False
    if not _env_enabled("AI_SUBTITLE_NATIVE_GLOBAL_CANVAS_BUILD", "1"):
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
    if not _env_enabled("AI_SUBTITLE_NATIVE_GLOBAL_CANVAS", "1"):
        return None
    _compile_native_extension()
    try:
        return importlib.import_module("core._native_subtitle_global_canvas")
    except Exception:
        return None


_native = _load_native_module()

HAS_NATIVE_SUBTITLE_GLOBAL_CANVAS = _native is not None


def native_subtitle_global_canvas_enabled() -> bool:
    if _native is None:
        return False
    return _env_enabled("AI_SUBTITLE_NATIVE_GLOBAL_CANVAS", "1")


def _segment_vectors(rows: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    starts: list[float] = []
    ends: list[float] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        try:
            start = max(0.0, float(row.get("start", 0.0) or 0.0))
        except Exception:
            start = 0.0
        try:
            end = max(0.0, float(row.get("end", start) or start))
        except Exception:
            end = start
        starts.append(start)
        ends.append(end)
    return starts, ends


def _python_global_canvas_summary(
    rows: list[dict[str, Any]],
    *,
    duration: float = 0.0,
    bin_count: int = 120,
) -> dict[str, Any]:
    starts, ends = _segment_vectors(rows)
    count = min(len(starts), len(ends))
    requested_duration = max(0.0, float(duration or 0.0))
    safe_bin_count = max(1, min(2048, int(bin_count or 120)))
    invalid = 0
    non_monotonic = 0
    max_end = 0.0
    previous_start: float | None = None
    intervals: list[tuple[float, float]] = []
    for idx in range(count):
        start = starts[idx]
        end = ends[idx]
        if previous_start is not None and start < previous_start:
            non_monotonic += 1
        previous_start = start
        max_end = max(max_end, end)
        if end > start:
            intervals.append((start, end))
        else:
            invalid += 1

    canvas_duration = max(requested_duration, max_end)
    bins = [0] * safe_bin_count
    if canvas_duration > 0:
        for start, end in intervals:
            clipped_start = min(max(0.0, start), canvas_duration)
            clipped_end = min(max(0.0, end), canvas_duration)
            if clipped_end <= clipped_start:
                continue
            start_bin = min(safe_bin_count - 1, max(0, int((clipped_start / canvas_duration) * safe_bin_count)))
            end_bin = min(safe_bin_count, max(start_bin + 1, int(math.ceil(clipped_end / canvas_duration * safe_bin_count))))
            for idx in range(start_bin, end_bin):
                bins[idx] += 1

    occupied = sum(1 for value in bins if value > 0)
    dense = sum(1 for value in bins if value > 1)
    max_bin_active = max(bins, default=0)
    max_active_bin_index = next((idx for idx, value in enumerate(bins) if value == max_bin_active and value > 0), -1)
    avg_bin_active = sum(bins) / safe_bin_count if safe_bin_count else 0.0

    sorted_intervals = sorted(intervals)
    coverage = 0.0
    longest_gap = 0.0
    longest_gap_start = 0.0
    longest_gap_end = 0.0
    merged_start: float | None = None
    merged_end: float | None = None
    previous_end: float | None = None
    events: list[tuple[float, int]] = []
    for start, end in sorted_intervals:
        if previous_end is not None and start > previous_end:
            gap = start - previous_end
            # 변경 금지: Swift/C++와 같은 의미로 global canvas 빈 구간 위치를 기록합니다.
            # 하단 minimap artifact가 자막/에디터와 어긋날 때 UI를 건드리지 않고 데이터 위치부터 확인합니다.
            if gap > longest_gap:
                longest_gap = gap
                longest_gap_start = previous_end
                longest_gap_end = start
        if merged_start is None:
            merged_start = start
            merged_end = end
        elif merged_end is not None and start <= merged_end:
            merged_end = max(merged_end, end)
        else:
            coverage += max(0.0, float(merged_end or 0.0) - float(merged_start or 0.0))
            merged_start = start
            merged_end = end
        previous_end = max(previous_end if previous_end is not None else end, end)
        events.append((start, 1))
        events.append((end, -1))
    if merged_start is not None and merged_end is not None:
        coverage += max(0.0, merged_end - merged_start)

    active = 0
    max_active = 0
    for _time, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        max_active = max(max_active, active)

    return {
        "schema": "ai_subtitle_studio.subtitle_global_canvas.summary.v1",
        "segment_count": count,
        "valid_segment_count": len(intervals),
        "invalid_duration_count": invalid,
        "non_monotonic_count": non_monotonic,
        "duration": round(canvas_duration, 6),
        "bin_count": safe_bin_count,
        "bin_width_sec": round(canvas_duration / safe_bin_count, 6) if canvas_duration > 0 else 0.0,
        "occupied_bin_count": occupied,
        "empty_bin_count": max(0, safe_bin_count - occupied),
        "dense_bin_count": dense,
        "max_bin_active": max_bin_active,
        "max_active_bin_index": max_active_bin_index,
        "avg_bin_active": round(avg_bin_active, 6),
        "coverage_duration": round(coverage, 6),
        "coverage_ratio": round(coverage / canvas_duration, 6) if canvas_duration > 0 else 0.0,
        "longest_empty_span_sec": round(longest_gap, 6),
        "longest_empty_start_sec": round(longest_gap_start, 6),
        "longest_empty_end_sec": round(longest_gap_end, 6),
        "max_active_segments": max_active,
        "stable_for_global_canvas": invalid == 0 and non_monotonic == 0,
        "native_backend": "python",
    }


def _python_global_canvas_merged_segments(
    rows: list[dict[str, Any]],
    *,
    lanes: tuple[str, ...] = ("SUBTITLE",),
    output_lane: str = "SUBTITLE",
    max_gap_sec: float = 0.0,
    include_text: bool = True,
) -> list[dict[str, Any]]:
    lane_set = {str(lane or "") for lane in lanes}
    max_gap = max(0.0, float(max_gap_sec or 0.0))
    merged: list[dict[str, Any]] = []
    sortable: list[dict[str, Any]] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        lane = str(row.get("lane", "SUBTITLE") or "SUBTITLE")
        if lane not in lane_set:
            continue
        try:
            start = max(0.0, float(row.get("start", 0.0) or 0.0))
            end = max(start, float(row.get("end", start) or start))
        except Exception:
            continue
        if end <= start:
            continue
        sortable.append(
            {
                "start": start,
                "end": end,
                "lane": lane,
                "text": str(row.get("text", "") or "").strip(),
            }
        )
    for row in sorted(sortable, key=lambda item: float(item.get("start", 0.0) or 0.0)):
        start = float(row["start"])
        end = float(row["end"])
        text = str(row.get("text", "") or "").strip()
        if merged:
            prev = merged[-1]
            if start <= float(prev.get("end", 0.0) or 0.0) + max_gap:
                prev["end"] = max(float(prev.get("end", 0.0) or 0.0), end)
                if include_text and text:
                    prev_text = str(prev.get("text", "") or "").strip()
                    if text not in prev_text:
                        prev["text"] = f"{prev_text} {text}".strip() if prev_text else text
                prev["count"] = int(prev.get("count", 1) or 1) + 1
                continue
        item: dict[str, Any] = {
            "start": start,
            "end": end,
            "lane": str(output_lane or ""),
            "count": 1,
        }
        if include_text:
            item["text"] = text
        merged.append(item)
    return merged


def global_canvas_summary(
    rows: list[dict[str, Any]],
    *,
    duration: float = 0.0,
    bin_count: int = 120,
) -> dict[str, Any]:
    if native_subtitle_global_canvas_enabled():
        try:
            starts, ends = _segment_vectors(rows)
            result = _native.global_canvas_summary(starts, ends, float(duration or 0.0), int(bin_count or 120))
            if isinstance(result, dict):
                return dict(result)
        except Exception:
            pass
    return _python_global_canvas_summary(rows, duration=duration, bin_count=bin_count)


def global_canvas_merged_segments(
    rows: list[dict[str, Any]],
    *,
    lanes: tuple[str, ...] = ("SUBTITLE",),
    output_lane: str = "SUBTITLE",
    max_gap_sec: float = 0.0,
    include_text: bool = True,
) -> list[dict[str, Any]]:
    if native_subtitle_global_canvas_enabled():
        try:
            starts, ends = _segment_vectors(rows)
            texts = [str(row.get("text", "") or "").strip() for row in list(rows or []) if isinstance(row, dict)]
            row_lanes = [str(row.get("lane", "SUBTITLE") or "SUBTITLE") for row in list(rows or []) if isinstance(row, dict)]
            result = _native.global_canvas_merged_segments(
                starts,
                ends,
                texts,
                row_lanes,
                [str(lane or "") for lane in lanes],
                str(output_lane or ""),
                float(max_gap_sec or 0.0),
                bool(include_text),
            )
            if isinstance(result, list):
                return [dict(item) for item in result if isinstance(item, dict)]
        except Exception:
            pass
    return _python_global_canvas_merged_segments(
        rows,
        lanes=lanes,
        output_lane=output_lane,
        max_gap_sec=max_gap_sec,
        include_text=include_text,
    )


__all__ = [
    "HAS_NATIVE_SUBTITLE_GLOBAL_CANVAS",
    "global_canvas_merged_segments",
    "global_canvas_summary",
    "native_subtitle_global_canvas_enabled",
]
