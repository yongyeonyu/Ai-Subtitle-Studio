from __future__ import annotations

from typing import Any


def _summary_bucket() -> dict[str, Any]:
    return {
        "checkpoint_count": 0,
        "requested_count": 0,
        "executed_count": 0,
        "skipped_count": 0,
        "skipped_by_reason": {},
        "total_elapsed_ms": 0.0,
        "total_failure_count": 0,
        "slowest_stage_key": "",
        "slowest_stage_elapsed_ms": 0.0,
        "stages": {},
        "actions": {},
    }


def stage_trim_summary_bucket(summary: dict[str, Any] | None = None) -> dict[str, Any]:
    bucket = dict(summary or {})
    for key, value in _summary_bucket().items():
        if key not in bucket:
            bucket[key] = value if not isinstance(value, dict) else dict(value)
    bucket["stages"] = dict(bucket.get("stages") or {})
    bucket["actions"] = dict(bucket.get("actions") or {})
    bucket["skipped_by_reason"] = dict(bucket.get("skipped_by_reason") or {})
    return bucket


def stage_trim_stage_key(stage: str) -> str:
    text = str(stage or "").strip()
    if not text:
        return "unknown"
    return text.split(":", 1)[0].strip() or "unknown"


def record_stage_trim_summary(
    summary: dict[str, Any] | None,
    *,
    stage: str,
    pressure_stage: str,
    trim_requested: bool,
    trim_result: dict[str, Any] | None = None,
    skipped_reason: str = "",
) -> dict[str, Any]:
    bucket = stage_trim_summary_bucket(summary)
    stage_key = stage_trim_stage_key(stage)
    stage_bucket = dict(bucket["stages"].get(stage_key) or _summary_bucket())
    stage_bucket["stages"] = {}
    stage_bucket["actions"] = {}

    bucket["checkpoint_count"] += 1
    bucket["last_stage"] = str(stage or "")
    bucket["last_stage_key"] = stage_key
    bucket["last_pressure_stage"] = str(pressure_stage or "")

    stage_bucket["checkpoint_count"] += 1
    stage_bucket["last_stage"] = str(stage or "")
    stage_bucket["last_pressure_stage"] = str(pressure_stage or "")

    if trim_requested:
        bucket["requested_count"] += 1
        stage_bucket["requested_count"] += 1

    trim_payload = dict(trim_result or {})
    if trim_payload:
        elapsed_ms = round(float(trim_payload.get("elapsed_ms", 0.0) or 0.0), 3)
        failure_count = len(list(trim_payload.get("failures") or []))
        bucket["executed_count"] += 1
        bucket["total_elapsed_ms"] = round(float(bucket["total_elapsed_ms"]) + elapsed_ms, 3)
        bucket["total_failure_count"] += failure_count
        stage_bucket["executed_count"] += 1
        stage_bucket["total_elapsed_ms"] = round(float(stage_bucket["total_elapsed_ms"]) + elapsed_ms, 3)
        stage_bucket["total_failure_count"] += failure_count
        stage_bucket["last_elapsed_ms"] = elapsed_ms
        if float(stage_bucket["total_elapsed_ms"]) >= float(bucket["slowest_stage_elapsed_ms"] or 0.0):
            bucket["slowest_stage_key"] = stage_key
            bucket["slowest_stage_elapsed_ms"] = round(float(stage_bucket["total_elapsed_ms"]), 3)
        for action in list(trim_payload.get("action_timings") or []):
            if not isinstance(action, dict):
                continue
            action_name = str(action.get("action", "") or "").strip()
            if not action_name:
                continue
            action_bucket = dict(bucket["actions"].get(action_name) or {
                "count": 0,
                "total_elapsed_ms": 0.0,
                "failure_count": 0,
            })
            action_bucket["count"] += 1
            action_bucket["total_elapsed_ms"] = round(
                float(action_bucket.get("total_elapsed_ms", 0.0) or 0.0)
                + float(action.get("elapsed_ms", 0.0) or 0.0),
                3,
            )
            if not bool(action.get("ok", False)):
                action_bucket["failure_count"] += 1
            bucket["actions"][action_name] = action_bucket
    elif trim_requested and skipped_reason:
        reason = str(skipped_reason or "").strip() or "unknown"
        bucket["skipped_count"] += 1
        bucket["skipped_by_reason"][reason] = int(bucket["skipped_by_reason"].get(reason, 0) or 0) + 1
        stage_bucket["skipped_count"] += 1
        stage_bucket["last_skipped_reason"] = reason

    bucket["stages"][stage_key] = stage_bucket
    return bucket


__all__ = [
    "record_stage_trim_summary",
    "stage_trim_stage_key",
    "stage_trim_summary_bucket",
]
