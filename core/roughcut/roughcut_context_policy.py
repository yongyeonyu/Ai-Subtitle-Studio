from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.personalization.deep_runtime_adaptation import summarize_deep_runtime_events
from core.personalization.lora_models import stable_hash
from core.personalization.lora_store_common import read_jsonl, store_paths

from .roughcut_settings import merge_roughcut_settings


ROUGHCUT_CONTEXT_POLICY_SCHEMA = "ai_subtitle_studio.roughcut_context_policy.v1"
ROUGHCUT_CONTEXT_POLICY_MODEL_ID = "lora_deep_roughcut_context_policy_v1"

_ROW_LIST_KEYS = (
    "subtitle_rows",
    "chunks",
    "chapters",
    "segments",
    "major_segments",
    "subtitles",
    "packed_phrases",
)
_FOCUS_KEYS = ("focus_row_index", "current_row_index", "boundary_row_index", "start_index")


def _safe_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔", "아니오"}
    return bool(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(round(float(value)))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _clamp_int(value: Any, low: int, high: int) -> int:
    low = int(low)
    high = max(low, int(high))
    return max(low, min(high, _safe_int(value, low)))


def _clamp_float(value: Any, low: float, high: float) -> float:
    low = float(low)
    high = max(low, float(high))
    return max(low, min(high, _safe_float(value, low)))


def _candidate_rows(
    payload: dict[str, Any] | None = None,
    subtitle_rows: list[dict[str, Any]] | None = None,
) -> tuple[str, list[Any]]:
    if isinstance(subtitle_rows, list):
        return "subtitle_rows", [row for row in subtitle_rows if isinstance(row, dict)]
    source = payload if isinstance(payload, dict) else {}
    for key in _ROW_LIST_KEYS:
        rows = source.get(key)
        if isinstance(rows, list):
            return key, list(rows)
    return "", []


def _row_count(
    payload: dict[str, Any] | None = None,
    subtitle_rows: list[dict[str, Any]] | None = None,
) -> int:
    _key, rows = _candidate_rows(payload, subtitle_rows)
    return len(rows)


def _row_duration_sec(rows: list[Any], payload: dict[str, Any] | None = None) -> float:
    source = payload if isinstance(payload, dict) else {}
    for key in ("media_duration", "duration", "duration_sec", "video_duration"):
        duration = _safe_float(source.get(key), -1.0)
        if duration > 0.0:
            return duration
    starts: list[float] = []
    ends: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        start = _safe_float(row.get("start"), -1.0)
        end = _safe_float(row.get("end"), -1.0)
        if start >= 0.0:
            starts.append(start)
        if end >= 0.0:
            ends.append(end)
    if starts and ends:
        return max(0.0, max(ends) - min(starts))
    return 0.0


def _boundary_count(payload: dict[str, Any] | None = None) -> tuple[int, int]:
    if not isinstance(payload, dict):
        return 0, 0
    confirmed = 0
    provisional = 0
    for key in ("cut_boundaries", "scene_changes", "cut_points"):
        rows = payload.get(key)
        if isinstance(rows, list):
            confirmed += len(rows)
    rows = payload.get("provisional_cut_boundaries")
    if isinstance(rows, list):
        provisional += len(rows)
    return confirmed, provisional


def _deep_summary(settings: dict[str, Any], store_dir: str | None = None) -> dict[str, Any]:
    if not _safe_bool(settings.get("deep_runtime_adaptation_enabled"), True):
        return {}
    try:
        rows = read_jsonl(store_paths(store_dir)["deep_policy_events"])
    except Exception:
        return {}
    lookback = _clamp_int(settings.get("deep_runtime_adaptation_lookback_events"), 16, 5000)
    return summarize_deep_runtime_events([dict(row) for row in rows[-lookback:] if isinstance(row, dict)])


def _manual_policy(settings: dict[str, Any], row_count: int, rows_key: str) -> dict[str, Any]:
    max_rows = _clamp_int(settings.get("roughcut_llm_max_context_rows"), 1, 500)
    chunk_rows = _clamp_int(settings.get("roughcut_llm_chunk_rows"), 1, 100)
    lookahead_rows = _clamp_int(settings.get("roughcut_llm_lookahead_rows"), 0, 100)
    return {
        "schema": ROUGHCUT_CONTEXT_POLICY_SCHEMA,
        "model": ROUGHCUT_CONTEXT_POLICY_MODEL_ID,
        "auto_enabled": False,
        "reason": "manual_compat",
        "rows_key": rows_key,
        "row_count": row_count,
        "max_context_rows": max_rows,
        "chunk_rows": chunk_rows,
        "lookahead_rows": lookahead_rows,
        "lora_values": {},
        "deep_summary": {},
        "exploration": {},
    }


def _base_policy_values(settings: dict[str, Any], row_count: int, duration_sec: float, cut_count: int) -> tuple[int, int, int, list[str]]:
    min_context = _clamp_int(settings.get("roughcut_llm_context_min_rows"), 16, 500)
    max_context = _clamp_int(settings.get("roughcut_llm_context_max_rows"), min_context, 500)
    min_chunk = _clamp_int(settings.get("roughcut_llm_chunk_min_rows"), 1, 100)
    max_chunk = _clamp_int(settings.get("roughcut_llm_chunk_max_rows"), min_chunk, 100)
    min_lookahead = _clamp_int(settings.get("roughcut_llm_lookahead_min_rows"), 0, 100)
    max_lookahead = _clamp_int(settings.get("roughcut_llm_lookahead_max_rows"), min_lookahead, 100)
    reasons: list[str] = []

    if row_count <= 0:
        context = _clamp_int(settings.get("roughcut_llm_max_context_rows"), min_context, max_context)
        chunk = _clamp_int(settings.get("roughcut_llm_chunk_rows"), min_chunk, max_chunk)
        lookahead = _clamp_int(settings.get("roughcut_llm_lookahead_rows"), min_lookahead, max_lookahead)
        reasons.append("no_rows_default")
        return context, chunk, lookahead, reasons

    if row_count <= 24:
        context = max(min_context, row_count)
        chunk = min_chunk
        lookahead = min_lookahead
        reasons.append("small_context")
    elif row_count <= 80:
        context = max(80, row_count)
        chunk = max(min_chunk, 10)
        lookahead = max(min_lookahead, 6)
        reasons.append("medium_context")
    elif row_count <= max_context:
        context = max(96, row_count)
        chunk = max(min_chunk, 12)
        lookahead = max(min_lookahead, 8)
        reasons.append("wide_context")
    else:
        context = max_context
        chunk = max(min_chunk, 14)
        lookahead = max(min_lookahead, 10)
        reasons.append("long_context_capped")

    density = cut_count / max(1.0, duration_sec / 60.0) if duration_sec > 0.0 else cut_count / max(1, row_count)
    if cut_count >= max(2, row_count // 18) or density >= 1.4:
        chunk -= 2
        lookahead += 1
        reasons.append("dense_cut_boundaries")
    elif cut_count == 0 and row_count >= 80:
        context += 16
        chunk += 1
        reasons.append("sparse_cut_boundaries")

    return (
        _clamp_int(context, min_context, max_context),
        _clamp_int(chunk, min_chunk, max_chunk),
        _clamp_int(lookahead, min_lookahead, max_lookahead),
        reasons,
    )


def _apply_deep_adjustment(
    *,
    context: int,
    chunk: int,
    lookahead: int,
    settings: dict[str, Any],
    summary: dict[str, Any],
    reasons: list[str],
) -> tuple[int, int, int]:
    min_context = _clamp_int(settings.get("roughcut_llm_context_min_rows"), 16, 500)
    max_context = _clamp_int(settings.get("roughcut_llm_context_max_rows"), min_context, 500)
    min_chunk = _clamp_int(settings.get("roughcut_llm_chunk_min_rows"), 1, 100)
    max_chunk = _clamp_int(settings.get("roughcut_llm_chunk_max_rows"), min_chunk, 100)
    min_lookahead = _clamp_int(settings.get("roughcut_llm_lookahead_min_rows"), 0, 100)
    max_lookahead = _clamp_int(settings.get("roughcut_llm_lookahead_max_rows"), min_lookahead, 100)
    if not summary or int(summary.get("event_count", 0) or 0) < _clamp_int(settings.get("deep_runtime_adaptation_min_events"), 1, 5000):
        return context, chunk, lookahead

    context_risk = _safe_float(summary.get("context_risk_ratio"), 0.0)
    rollback = _safe_float(summary.get("llm_rollback_ratio"), 0.0)
    bundle_long = _safe_float(summary.get("subtitle_bundle_long_ratio"), 0.0)
    bundle_short = _safe_float(summary.get("subtitle_bundle_short_ratio"), 0.0)
    style_risk = _safe_float(summary.get("lora_style_risk_ratio"), 0.0)

    if context_risk >= 0.18 or rollback >= 0.08 or style_risk >= 0.18:
        context += 16
        lookahead += 1
        reasons.append("deep_more_context")
    if bundle_long >= 0.12:
        chunk -= 2
        reasons.append("deep_smaller_chunks")
    elif bundle_short >= 0.18 and context_risk < 0.12:
        chunk += 1
        reasons.append("deep_larger_chunks")

    return (
        _clamp_int(context, min_context, max_context),
        _clamp_int(chunk, min_chunk, max_chunk),
        _clamp_int(lookahead, min_lookahead, max_lookahead),
    )


def _blend_with_lora_values(
    *,
    context: int,
    chunk: int,
    lookahead: int,
    settings: dict[str, Any],
    reasons: list[str],
) -> tuple[int, int, int, dict[str, int]]:
    if not _safe_bool(settings.get("roughcut_llm_rows_lora_enabled"), True):
        return context, chunk, lookahead, {}
    min_context = _clamp_int(settings.get("roughcut_llm_context_min_rows"), 16, 500)
    max_context = _clamp_int(settings.get("roughcut_llm_context_max_rows"), min_context, 500)
    min_chunk = _clamp_int(settings.get("roughcut_llm_chunk_min_rows"), 1, 100)
    max_chunk = _clamp_int(settings.get("roughcut_llm_chunk_max_rows"), min_chunk, 100)
    min_lookahead = _clamp_int(settings.get("roughcut_llm_lookahead_min_rows"), 0, 100)
    max_lookahead = _clamp_int(settings.get("roughcut_llm_lookahead_max_rows"), min_lookahead, 100)
    blend = _clamp_float(settings.get("roughcut_llm_rows_lora_blend"), 0.0, 0.85)
    lora_values = {
        "max_context_rows": _clamp_int(settings.get("roughcut_llm_max_context_rows"), min_context, max_context),
        "chunk_rows": _clamp_int(settings.get("roughcut_llm_chunk_rows"), min_chunk, max_chunk),
        "lookahead_rows": _clamp_int(settings.get("roughcut_llm_lookahead_rows"), min_lookahead, max_lookahead),
    }
    if blend <= 0.0:
        return context, chunk, lookahead, lora_values
    context = round((context * (1.0 - blend)) + (lora_values["max_context_rows"] * blend))
    chunk = round((chunk * (1.0 - blend)) + (lora_values["chunk_rows"] * blend))
    lookahead = round((lookahead * (1.0 - blend)) + (lora_values["lookahead_rows"] * blend))
    reasons.append("lora_blend")
    return (
        _clamp_int(context, min_context, max_context),
        _clamp_int(chunk, min_chunk, max_chunk),
        _clamp_int(lookahead, min_lookahead, max_lookahead),
        lora_values,
    )


def _apply_exploration(
    *,
    context: int,
    chunk: int,
    lookahead: int,
    settings: dict[str, Any],
    rows: list[Any],
    reasons: list[str],
) -> tuple[int, int, int, dict[str, Any]]:
    rate = _clamp_float(settings.get("roughcut_llm_rows_exploration_rate"), 0.0, 0.25)
    if rate <= 0.0 or not rows:
        return context, chunk, lookahead, {}
    sample = repr(rows[:2]) + repr(rows[-2:])
    bucket = int(stable_hash(sample)[:8], 16) / float(0xFFFFFFFF)
    if bucket >= rate:
        return context, chunk, lookahead, {"bucket": round(bucket, 6), "applied": False}
    direction = -1 if int(stable_hash(sample + ":direction")[:2], 16) % 2 == 0 else 1
    min_context = _clamp_int(settings.get("roughcut_llm_context_min_rows"), 16, 500)
    max_context = _clamp_int(settings.get("roughcut_llm_context_max_rows"), min_context, 500)
    min_chunk = _clamp_int(settings.get("roughcut_llm_chunk_min_rows"), 1, 100)
    max_chunk = _clamp_int(settings.get("roughcut_llm_chunk_max_rows"), min_chunk, 100)
    min_lookahead = _clamp_int(settings.get("roughcut_llm_lookahead_min_rows"), 0, 100)
    max_lookahead = _clamp_int(settings.get("roughcut_llm_lookahead_max_rows"), min_lookahead, 100)
    context = _clamp_int(context + (direction * 8), min_context, max_context)
    chunk = _clamp_int(chunk + direction, min_chunk, max_chunk)
    lookahead = _clamp_int(lookahead + direction, min_lookahead, max_lookahead)
    reasons.append("deterministic_exploration")
    return context, chunk, lookahead, {"bucket": round(bucket, 6), "direction": direction, "applied": True}


def resolve_roughcut_context_policy(
    settings: dict[str, Any] | None = None,
    *,
    payload: dict[str, Any] | None = None,
    subtitle_rows: list[dict[str, Any]] | None = None,
    store_dir: str | None = None,
) -> dict[str, Any]:
    """Choose roughcut LLM row scope from LoRA evidence, deep events, and current workload."""
    merged = merge_roughcut_settings(settings or {})
    rows_key, rows = _candidate_rows(payload, subtitle_rows)
    count = _row_count(payload, subtitle_rows)
    if not _safe_bool(merged.get("roughcut_llm_rows_auto_enabled"), True):
        return _manual_policy(merged, count, rows_key)

    duration_sec = _row_duration_sec(rows, payload)
    confirmed_cuts, provisional_cuts = _boundary_count(payload)
    cut_count = confirmed_cuts + provisional_cuts
    context, chunk, lookahead, reasons = _base_policy_values(merged, count, duration_sec, cut_count)
    deep_summary = _deep_summary(merged, store_dir=store_dir)
    context, chunk, lookahead = _apply_deep_adjustment(
        context=context,
        chunk=chunk,
        lookahead=lookahead,
        settings=merged,
        summary=deep_summary,
        reasons=reasons,
    )
    context, chunk, lookahead, lora_values = _blend_with_lora_values(
        context=context,
        chunk=chunk,
        lookahead=lookahead,
        settings=merged,
        reasons=reasons,
    )
    context, chunk, lookahead, exploration = _apply_exploration(
        context=context,
        chunk=chunk,
        lookahead=lookahead,
        settings=merged,
        rows=rows,
        reasons=reasons,
    )
    return {
        "schema": ROUGHCUT_CONTEXT_POLICY_SCHEMA,
        "model": ROUGHCUT_CONTEXT_POLICY_MODEL_ID,
        "auto_enabled": True,
        "reason": "+".join(dict.fromkeys(reasons)) or "auto_default",
        "rows_key": rows_key,
        "row_count": count,
        "duration_sec": round(duration_sec, 3),
        "confirmed_cut_count": confirmed_cuts,
        "provisional_cut_count": provisional_cuts,
        "max_context_rows": context,
        "chunk_rows": chunk,
        "lookahead_rows": lookahead,
        "lora_values": lora_values,
        "deep_summary": deep_summary,
        "exploration": exploration,
    }


def trim_roughcut_payload_for_context(payload: dict[str, Any] | None, policy: dict[str, Any]) -> dict[str, Any]:
    """Return a prompt payload capped by the resolved roughcut row policy."""
    out = deepcopy(payload or {})
    max_rows = _clamp_int(policy.get("max_context_rows"), 1, 500)
    trimmed: dict[str, dict[str, int]] = {}
    focus = 0
    for key in _FOCUS_KEYS:
        if key in out:
            focus = _safe_int(out.get(key), 0)
            break
    for key in _ROW_LIST_KEYS:
        rows = out.get(key)
        if not isinstance(rows, list) or len(rows) <= max_rows:
            continue
        start = max(0, min(len(rows) - max_rows, focus - max_rows // 2))
        end = start + max_rows
        out[key] = list(rows[start:end])
        trimmed[key] = {"original": len(rows), "start_index": start, "end_index": end}
    compact_policy = {
        key: value
        for key, value in dict(policy or {}).items()
        if key not in {"deep_summary"}
    }
    if trimmed:
        compact_policy["trimmed"] = trimmed
    out["_roughcut_context_policy"] = compact_policy
    return out


__all__ = [
    "ROUGHCUT_CONTEXT_POLICY_MODEL_ID",
    "ROUGHCUT_CONTEXT_POLICY_SCHEMA",
    "resolve_roughcut_context_policy",
    "trim_roughcut_payload_for_context",
]
