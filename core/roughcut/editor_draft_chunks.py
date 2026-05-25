from __future__ import annotations

from bisect import bisect_left, bisect_right
from typing import Any, Callable

from core.llm.openai_provider import is_codex_model
from core.native_swift_roughcut import roughcut_boundary_candidates_via_swift

from .roughcut_settings import merge_roughcut_settings

BoundaryCandidateBackend = Callable[..., list[dict[str, Any]] | None]


def _int_setting(settings: dict[str, Any], key: str, default: int, *, minimum: int = 1, maximum: int = 9999) -> int:
    try:
        value = int(float(settings.get(key, default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _roughcut_effective_llm_model(settings: dict[str, Any] | None) -> tuple[str, str]:
    source = settings or {}
    merged = merge_roughcut_settings(source)
    use_override = bool(merged.get("roughcut_llm_use_override", False))
    provider = str(merged.get("roughcut_llm_provider") or "inherit").strip()
    model = str(merged.get("roughcut_llm_model") or "").strip()
    if not use_override or provider == "inherit":
        provider = str(source.get("selected_llm_provider") or "ollama").strip()
    if not use_override or model in ("", "inherit"):
        model = str(source.get("selected_model") or "").strip()
    return provider, model


def _roughcut_llm_uses_codex(settings: dict[str, Any] | None) -> bool:
    _provider, model = _roughcut_effective_llm_model(settings)
    return is_codex_model(model)


def _plan_editor_roughcut_core_ranges(
    rows: list[dict[str, Any]],
    settings: dict[str, Any],
    *,
    max_rows: int,
    target_rows: int,
    cut_boundaries: list[Any] | None = None,
    provisional_cut_boundaries: list[Any] | None = None,
    candidate_backend: BoundaryCandidateBackend | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    row_count = len(rows)
    min_core, target_core, max_core = _roughcut_chunk_bounds(settings, max_rows=max_rows, target_rows=target_rows)
    backend = candidate_backend or roughcut_boundary_candidates_via_swift
    confirmed_candidates = _boundary_break_candidates(rows, cut_boundaries or [], source="confirmed", candidate_backend=backend)
    provisional_candidates = _boundary_break_candidates(
        rows,
        provisional_cut_boundaries or [],
        source="provisional",
        candidate_backend=backend,
    )
    confirmed_index = _indexed_chunk_break_candidates(confirmed_candidates)
    provisional_index = _indexed_chunk_break_candidates(provisional_candidates)
    start = 0
    chunks: list[dict[str, Any]] = []
    while start < row_count:
        remaining = row_count - start
        if remaining <= max_core:
            end = row_count - 1
            source = "tail"
        else:
            min_end = min(row_count - 1, start + min_core - 1)
            max_end = min(row_count - 1, start + max_core - 1)
            target_end = min(row_count - 1, start + target_core - 1)
            latest_safe_end = row_count - min_core - 1
            if latest_safe_end >= min_end:
                target_end = min(target_end, latest_safe_end)
                max_end = min(max_end, max(min_end, latest_safe_end))
            choice = _pick_chunk_break_candidate(
                confirmed_candidates=confirmed_index,
                provisional_candidates=provisional_index,
                min_end=min_end,
                target_end=target_end,
                max_end=max_end,
            )
            if choice is not None:
                end = int(choice["end_index"])
                source = str(choice.get("source") or "boundary")
            else:
                end = max(min_end, min(max_end, target_end))
                source = "row_window"
        chunks.append(
            {
                "core_start_index": start,
                "core_end_index": end,
                "source": source,
            }
        )
        start = end + 1
    return chunks


def _roughcut_chunk_bounds(settings: dict[str, Any], *, max_rows: int, target_rows: int) -> tuple[int, int, int]:
    min_raw = int(settings.get("roughcut_llm_chunk_min_rows", 8) or 8)
    max_raw = int(settings.get("roughcut_llm_chunk_max_rows", 18) or 18)
    if _roughcut_llm_uses_codex(settings) and bool(merge_roughcut_settings(settings).get("roughcut_llm_rows_auto_enabled", True)):
        codex_chunk = _int_setting(
            merge_roughcut_settings(settings),
            "roughcut_codex_chunk_rows",
            72,
            minimum=1,
            maximum=max(1, max_rows),
        )
        max_raw = max(max_raw, codex_chunk, int(target_rows or 0))
    min_core = max(1, min(max_rows, min_raw))
    max_core = max(min_core, min(max_rows, max_raw))
    target_core = max(min_core, min(max_core, int(target_rows or max_rows)))
    return min_core, target_core, max_core


def _boundary_break_candidates(
    rows: list[dict[str, Any]],
    boundary_rows: list[Any],
    *,
    source: str,
    candidate_backend: BoundaryCandidateBackend | None = None,
) -> list[dict[str, Any]]:
    if len(rows) < 2 or not boundary_rows:
        return []
    if _roughcut_native_candidate_plan_worthwhile(rows, boundary_rows):
        backend = candidate_backend or roughcut_boundary_candidates_via_swift
        native = backend(rows, list(boundary_rows or []), source=source)
        if native is not None:
            return native
    midpoints = _roughcut_row_midpoints(rows)
    midpoint_values = [midpoint for _idx, midpoint in midpoints]
    monotonic = _is_nondecreasing(midpoint_values)
    best_by_index: dict[int, dict[str, Any]] = {}
    for item in list(boundary_rows or []):
        boundary_time = _boundary_time(item)
        if boundary_time is None:
            continue
        end_index, distance = _nearest_roughcut_midpoint(
            midpoints,
            midpoint_values,
            boundary_time,
            use_bisect=monotonic,
        )
        current = best_by_index.get(end_index)
        if current is None or distance < float(current.get("distance", 999999.0)):
            best_by_index[end_index] = {
                "end_index": end_index,
                "source": source,
                "distance": distance,
                "time": boundary_time,
            }
    return [best_by_index[index] for index in sorted(best_by_index)]


def _roughcut_row_midpoints(rows: list[dict[str, Any]]) -> list[tuple[int, float]]:
    return [
        (
            idx,
            (float(rows[idx]["end"]) + float(rows[idx + 1]["start"])) / 2.0,
        )
        for idx in range(len(rows) - 1)
    ]


def _is_nondecreasing(values: list[float]) -> bool:
    return all(values[index] <= values[index + 1] for index in range(len(values) - 1))


def _roughcut_native_candidate_plan_worthwhile(rows: list[dict[str, Any]], boundary_rows: list[Any]) -> bool:
    if len(rows) < 32 or len(boundary_rows) < 24:
        return False
    values = [midpoint for _idx, midpoint in _roughcut_row_midpoints(rows)]
    return _is_nondecreasing(values) and (len(values) * len(boundary_rows)) >= 4096


def _nearest_roughcut_midpoint(
    midpoints: list[tuple[int, float]],
    midpoint_values: list[float],
    boundary_time: float,
    *,
    use_bisect: bool,
) -> tuple[int, float]:
    if not midpoints:
        return 0, 0.0
    if not use_bisect:
        return min(
            ((idx, abs(midpoint - boundary_time)) for idx, midpoint in midpoints),
            key=lambda pair: pair[1],
        )
    pos = bisect_left(midpoint_values, boundary_time)
    candidate_positions: list[int] = []
    if pos < len(midpoint_values):
        candidate_positions.append(pos)
    if pos > 0:
        left_value = midpoint_values[pos - 1]
        candidate_positions.append(bisect_left(midpoint_values, left_value, 0, pos))
    best_position = min(
        candidate_positions,
        key=lambda item: (abs(midpoint_values[item] - boundary_time), item),
    )
    idx, midpoint = midpoints[best_position]
    return idx, abs(midpoint - boundary_time)


def _pick_chunk_break_candidate(
    *,
    confirmed_candidates,
    provisional_candidates,
    min_end: int,
    target_end: int,
    max_end: int,
) -> dict[str, Any] | None:
    for pool in (confirmed_candidates, provisional_candidates):
        filtered = _chunk_break_candidate_window(pool, min_end=min_end, max_end=max_end)
        if filtered:
            _end_index, _order, item = min(
                filtered,
                key=lambda entry: (
                    abs(int(entry[0]) - target_end),
                    float(entry[2].get("distance", 999999.0)),
                    int(entry[1]),
                ),
            )
            return item
    return None


def _indexed_chunk_break_candidates(candidates: list[dict[str, Any]] | None) -> dict[str, Any]:
    entries: list[tuple[int, int, dict[str, Any]]] = []
    for order, item in enumerate(candidates or []):
        if not isinstance(item, dict):
            continue
        try:
            end_index = int(item.get("end_index", -1))
        except (TypeError, ValueError):
            continue
        entries.append((end_index, order, item))
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    return {
        "ends": [entry[0] for entry in entries],
        "entries": entries,
    }


def _chunk_break_candidate_window(pool, *, min_end: int, max_end: int) -> list[tuple[int, int, dict[str, Any]]]:
    if isinstance(pool, dict):
        ends = pool.get("ends")
        entries = pool.get("entries")
        if isinstance(ends, list) and isinstance(entries, list):
            left = bisect_left(ends, min_end)
            right = bisect_right(ends, max_end)
            return list(entries[left:right])
    out: list[tuple[int, int, dict[str, Any]]] = []
    for order, item in enumerate(pool or []):
        if not isinstance(item, dict):
            continue
        try:
            end_index = int(item.get("end_index", -1))
        except (TypeError, ValueError):
            continue
        if min_end <= end_index <= max_end:
            out.append((end_index, order, item))
    return out


def _boundary_time(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, dict):
        return None
    for key in ("timeline_sec", "time", "sec", "timestamp", "start", "at"):
        candidate = value.get(key)
        if candidate in (None, ""):
            continue
        try:
            return float(candidate)
        except (TypeError, ValueError):
            continue
    return None
