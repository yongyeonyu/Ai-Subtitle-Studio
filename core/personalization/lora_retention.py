from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from core.personalization.lora_models import iso_now, stable_hash
from core.personalization.lora_storage import (
    JSONL_KINDS,
    initialize_lora_personalization_store,
    load_learned_rules,
    load_retention_policy,
    refresh_lora_personalization_manifest,
    save_dedupe_index,
    save_learned_rules,
    store_paths,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _row_signature(row: dict[str, Any]) -> str:
    return str(row.get("signature") or row.get("dedupe_hash") or stable_hash(dict(row or {})))


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _nested_value(payload: dict[str, Any], dotted_key: str) -> Any:
    current: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _created_timestamp(row: dict[str, Any], fallback_index: int) -> float:
    for key in ("last_used_at", "updated_at", "created_at", "captured_at"):
        text = str(row.get(key) or "").strip()
        if not text:
            continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
    return float(fallback_index)


def _explicit_score(row: dict[str, Any]) -> float | None:
    for key in (
        "score",
        "quality_score",
        "confidence_score",
        "stt_score",
        "metrics.final_score",
        "metrics.quality_score",
        "metadata.score",
    ):
        value = _nested_value(row, key)
        if value is None:
            continue
        try:
            score = float(value)
        except Exception:
            continue
        return score * 100.0 if 0.0 <= score <= 1.0 else score
    return None


def _retention_rank(kind: str, row: dict[str, Any], index: int) -> tuple[float, float, float]:
    score = _explicit_score(row)
    if score is None:
        score = 72.0 if kind == "truth_table" else 55.0

    status = str(row.get("status") or "").strip().lower()
    if status in {"failed", "error"}:
        score -= 25.0
    elif status in {"skipped", "cancelled"}:
        score -= 12.0
    elif status in {"complete", "reviewed"}:
        score += 4.0

    usage = max(
        _coerce_int(row.get("usage_count"), 0),
        _coerce_int(row.get("frequency"), 0),
        _coerce_int(_nested_value(row, "metadata.usage_count"), 0),
    )
    score += min(12.0, math.log1p(max(0, usage)) * 3.0)
    if bool(row.get("pinned") or _nested_value(row, "metadata.pinned")):
        score += 1_000_000.0

    return (score, float(usage), _created_timestamp(row, index))


def _target_remove_count(
    *,
    total_rows: int,
    appended_rows: int,
    policy: dict[str, Any],
    training_event: bool,
) -> int:
    min_keep = max(0, int(policy.get("min_keep", 0) or 0))
    max_rows = max(min_keep, int(policy.get("max_rows", min_keep) or min_keep))
    remove_per_training = max(0, int(policy.get("remove_per_training", 0) or 0))
    over_capacity = max(0, total_rows - max_rows)
    incremental = min(max(0, appended_rows), remove_per_training) if training_event else 0
    target = max(over_capacity, incremental)
    return max(0, min(target, total_rows - min_keep))


def _prune_jsonl_kind(
    *,
    kind: str,
    rows: list[dict[str, Any]],
    policy: dict[str, Any],
    appended_rows: int,
    training_event: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    remove_count = _target_remove_count(
        total_rows=len(rows),
        appended_rows=appended_rows,
        policy=policy,
        training_event=training_event,
    )
    if remove_count <= 0:
        return rows, []
    ranked = sorted(
        enumerate(rows),
        key=lambda pair: _retention_rank(kind, pair[1], pair[0]),
    )
    remove_indexes = {index for index, _row in ranked[:remove_count]}
    removed = [dict(row) for index, row in enumerate(rows) if index in remove_indexes]
    kept = [dict(row) for index, row in enumerate(rows) if index not in remove_indexes]
    return kept, removed


def _rule_rank(item: dict[str, Any], index: int) -> tuple[float, float, float]:
    confidence = _coerce_float(item.get("confidence"), 0.0)
    frequency = _coerce_int(item.get("frequency"), 0)
    score = confidence * 100.0 + min(15.0, math.log1p(max(0, frequency)) * 4.0)
    if bool(item.get("pinned") or _nested_value(item, "metadata.pinned")):
        score += 1_000_000.0
    return (score, float(frequency), _created_timestamp(item, index))


def _prune_rules(
    *,
    rule_kind: str,
    policy: dict[str, Any],
    store_dir: str | Path | None,
) -> list[dict[str, Any]]:
    payload = load_learned_rules(rule_kind, store_dir)
    items = [dict(item) for item in list(payload.get("items") or [])]
    max_items = max(0, int(policy.get("max_items", len(items)) or len(items)))
    if max_items <= 0 or len(items) <= max_items:
        return []
    ranked = sorted(enumerate(items), key=lambda pair: _rule_rank(pair[1], pair[0]))
    remove_indexes = {index for index, _item in ranked[: len(items) - max_items]}
    removed = [dict(item) for index, item in enumerate(items) if index in remove_indexes]
    kept = [dict(item) for index, item in enumerate(items) if index not in remove_indexes]
    save_learned_rules(
        rule_kind,
        kept,
        store_dir=store_dir,
        metadata=dict(payload.get("metadata") or {}),
    )
    return removed


def _rebuild_dedupe_index(store_dir: str | Path | None = None) -> None:
    paths = store_paths(store_dir)
    entries: dict[str, dict[str, Any]] = {kind: {} for kind in JSONL_KINDS}
    for kind in JSONL_KINDS:
        for row in _read_jsonl(paths[kind]):
            signature = _row_signature(row)
            entries[kind][signature] = {
                "signature": signature,
                "file": JSONL_KINDS[kind],
                "captured_at": str(row.get("captured_at") or row.get("created_at") or iso_now()),
            }
    save_dedupe_index(
        {
            "schema": "ai_subtitle_studio.personalization_dedupe_index.v1",
            "updated_at": iso_now(),
            "entries": entries,
        },
        store_dir,
    )


def prune_low_value_personalization_data(
    *,
    store_dir: str | Path | None = None,
    trigger: str = "manual",
    appended_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    policy = load_retention_policy(store_dir)
    if not bool(policy.get("enabled", True)):
        return {"enabled": False, "trigger": trigger, "removed": {}, "total_removed": 0}

    paths = store_paths(store_dir)
    appended = dict(appended_counts or {})
    training_event = str(trigger or "").startswith("training") or str(trigger or "").startswith("trial")
    removed: dict[str, list[dict[str, Any]]] = {}

    jsonl_policies = dict(policy.get("jsonl") or {})
    for kind, kind_policy in jsonl_policies.items():
        if kind not in JSONL_KINDS or kind not in paths:
            continue
        rows = _read_jsonl(paths[kind])
        kept, removed_rows = _prune_jsonl_kind(
            kind=kind,
            rows=rows,
            policy=dict(kind_policy or {}),
            appended_rows=max(0, int(appended.get(kind, 0) or 0)),
            training_event=training_event,
        )
        if removed_rows:
            _write_jsonl(paths[kind], kept)
            removed[kind] = removed_rows

    rule_policies = dict(policy.get("rules") or {})
    for rule_kind in ("split", "line_break"):
        removed_rules = _prune_rules(
            rule_kind=rule_kind,
            policy=dict(rule_policies.get(rule_kind) or {}),
            store_dir=store_dir,
        )
        if removed_rules:
            removed[f"{rule_kind}_rules"] = removed_rules

    if removed:
        _rebuild_dedupe_index(store_dir)
    manifest = refresh_lora_personalization_manifest(store_dir)
    removed_counts = {key: len(value) for key, value in removed.items()}
    total_removed = sum(removed_counts.values())
    if total_removed > 0:
        history_row = {
            "schema": "ai_subtitle_studio.personalization_retention_event.v1",
            "created_at": iso_now(),
            "trigger": str(trigger or "manual"),
            "removed_counts": removed_counts,
            "total_removed": total_removed,
        }
        _append_jsonl(paths["retention_history"], history_row)
        manifest = refresh_lora_personalization_manifest(store_dir)
    return {
        "enabled": True,
        "trigger": str(trigger or "manual"),
        "removed": removed_counts,
        "total_removed": total_removed,
        "policy": policy,
        "manifest": manifest,
    }


__all__ = [
    "prune_low_value_personalization_data",
]
