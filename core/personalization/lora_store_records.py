from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.personalization.lora_models import iso_now
from core.personalization.lora_store_bundle import initialize_lora_personalization_store, refresh_lora_personalization_manifest
from core.personalization.lora_store_common import (
    JSONL_KINDS,
    default_best_settings,
    default_dedupe_index,
    default_learned_rules,
    default_queue,
    default_retention_policy,
    read_json,
    read_jsonl,
    row_signature,
    store_paths,
    write_json,
    write_jsonl,
)


def load_training_queue(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    return read_json(paths["training_queue"], default_queue())


def save_training_queue(
    items: list[dict[str, Any]],
    store_dir: str | Path | None = None,
    *,
    refresh_manifest: bool = True,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    payload = {
        "schema": "ai_subtitle_studio.personalization_training_queue.v1",
        "updated_at": iso_now(),
        "items": list(items or []),
    }
    write_json(paths["training_queue"], payload)
    if refresh_manifest:
        refresh_lora_personalization_manifest(store_dir, refresh_bundle=False)
    return payload


def upsert_training_queue_items(
    items: list[dict[str, Any]],
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    payload = load_training_queue(store_dir)
    current_items = list(payload.get("items") or [])
    by_job_id = {
        str(item.get("job_id") or ""): dict(item)
        for item in current_items
        if str(item.get("job_id") or "")
    }
    ordered_job_ids = [str(item.get("job_id") or "") for item in current_items if str(item.get("job_id") or "")]
    for item in list(items or []):
        job_id = str(item.get("job_id") or "")
        if not job_id:
            continue
        if job_id not in by_job_id:
            ordered_job_ids.append(job_id)
            by_job_id[job_id] = dict(item)
            continue
        existing = dict(by_job_id[job_id])
        merged = dict(item)
        for key in ("status", "progress", "score", "last_error", "attempts", "created_at", "updated_at", "payload"):
            if key in existing:
                merged[key] = existing[key]
        by_job_id[job_id] = merged
    merged = [by_job_id[job_id] for job_id in ordered_job_ids if job_id in by_job_id]
    return save_training_queue(merged, store_dir)


def clear_training_queue(
    store_dir: str | Path | None = None,
    *,
    keep_completed: bool = False,
) -> dict[str, Any]:
    if not keep_completed:
        return save_training_queue([], store_dir)
    payload = load_training_queue(store_dir)
    items = [
        dict(item)
        for item in list(payload.get("items") or [])
        if str(item.get("status") or "").strip().lower() == "complete"
    ]
    return save_training_queue(items, store_dir)


def load_learned_rules(rule_kind: str, store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    if rule_kind == "split":
        return read_json(paths["learned_split_rules"], default_learned_rules("ai_subtitle_studio.learned_split_rules.v1"))
    if rule_kind == "line_break":
        return read_json(paths["learned_line_break_rules"], default_learned_rules("ai_subtitle_studio.learned_line_break_rules.v1"))
    raise ValueError(f"Unsupported rule kind: {rule_kind}")


def save_learned_rules(
    rule_kind: str,
    items: list[dict[str, Any]],
    store_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    if rule_kind == "split":
        path = paths["learned_split_rules"]
        schema_name = "ai_subtitle_studio.learned_split_rules.v1"
    elif rule_kind == "line_break":
        path = paths["learned_line_break_rules"]
        schema_name = "ai_subtitle_studio.learned_line_break_rules.v1"
    else:
        raise ValueError(f"Unsupported rule kind: {rule_kind}")
    payload = {
        "schema": schema_name,
        "updated_at": iso_now(),
        "metadata": dict(metadata or {}),
        "items": list(items or []),
    }
    write_json(path, payload)
    refresh_lora_personalization_manifest(store_dir)
    return payload


def load_best_settings(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    return read_json(paths["best_settings"], default_best_settings())


def save_best_settings(payload: dict[str, Any], store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    merged = default_best_settings()
    merged.update(dict(payload or {}))
    merged["updated_at"] = iso_now()
    write_json(paths["best_settings"], merged)
    refresh_lora_personalization_manifest(store_dir)
    return merged


def load_dedupe_index(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    payload = read_json(paths["dedupe_index"], default_dedupe_index())
    entries = dict(payload.get("entries") or {})
    for kind in JSONL_KINDS:
        entries.setdefault(kind, {})
    payload["entries"] = entries
    return payload


def save_dedupe_index(
    payload: dict[str, Any],
    store_dir: str | Path | None = None,
    *,
    refresh_manifest: bool = True,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    merged = default_dedupe_index()
    merged.update(dict(payload or {}))
    merged["updated_at"] = iso_now()
    entries = dict(merged.get("entries") or {})
    for kind in JSONL_KINDS:
        entries.setdefault(kind, {})
    merged["entries"] = entries
    write_json(paths["dedupe_index"], merged)
    if refresh_manifest:
        refresh_lora_personalization_manifest(store_dir, refresh_bundle=False)
    return merged


def load_retention_policy(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    payload = read_json(paths["retention_policy"], default_retention_policy())
    defaults = default_retention_policy()
    merged = dict(defaults)
    merged.update(dict(payload or {}))
    jsonl_defaults = dict(defaults.get("jsonl") or {})
    jsonl_payload = dict((payload or {}).get("jsonl") or {})
    merged["jsonl"] = {
        key: {**dict(jsonl_defaults.get(key) or {}), **dict(jsonl_payload.get(key) or {})}
        for key in set(jsonl_defaults) | set(jsonl_payload)
    }
    rule_defaults = dict(defaults.get("rules") or {})
    rule_payload = dict((payload or {}).get("rules") or {})
    merged["rules"] = {
        key: {**dict(rule_defaults.get(key) or {}), **dict(rule_payload.get(key) or {})}
        for key in set(rule_defaults) | set(rule_payload)
    }
    return merged


def save_retention_policy(payload: dict[str, Any], store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    merged = default_retention_policy()
    merged.update(dict(payload or {}))
    merged["updated_at"] = iso_now()
    write_json(paths["retention_policy"], merged)
    refresh_lora_personalization_manifest(store_dir)
    return merged


def _append_unique_rows(
    kind: str,
    rows: list[dict[str, Any]],
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    dedupe = load_dedupe_index(store_dir)
    entries = dedupe["entries"][kind]
    existing_rows = read_jsonl(paths[kind])
    appended = 0
    paths[kind].parent.mkdir(parents=True, exist_ok=True)
    with paths[kind].open("a", encoding="utf-8") as handle:
        for row in list(rows or []):
            signature = row_signature(row)
            if signature in entries:
                continue
            row = dict(row)
            row["signature"] = signature
            row.setdefault("captured_at", iso_now())
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            entries[signature] = {
                "signature": signature,
                "file": JSONL_KINDS[kind],
                "captured_at": row["captured_at"],
            }
            appended += 1
            existing_rows.append(row)
    save_dedupe_index(dedupe, store_dir, refresh_manifest=False)
    manifest = refresh_lora_personalization_manifest(store_dir)
    return {
        "kind": kind,
        "path": str(paths[kind]),
        "appended_rows": appended,
        "total_rows": len(existing_rows),
        "manifest": manifest,
    }


def append_truth_table_rows(
    rows: list[dict[str, Any]],
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    return _append_unique_rows("truth_table", rows, store_dir)


def append_excluded_parentheticals(
    rows: list[dict[str, Any]],
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    return _append_unique_rows("excluded_parentheticals", rows, store_dir)


def append_setting_trials(
    rows: list[dict[str, Any]],
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    return _append_unique_rows("setting_trials", rows, store_dir)


def append_prompt_trials(
    rows: list[dict[str, Any]],
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    return _append_unique_rows("prompt_trials", rows, store_dir)


def append_voice_lora_bridge_rows(
    rows: list[dict[str, Any]],
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    return _append_unique_rows("voice_lora_bridge", rows, store_dir)


def append_multimodal_lora_context_rows(
    rows: list[dict[str, Any]],
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    return _append_unique_rows("multimodal_lora_context", rows, store_dir)


def append_deep_policy_events(
    rows: list[dict[str, Any]],
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    return _append_unique_rows("deep_policy_events", rows, store_dir)


def compact_lora_personalization_store(store_dir: str | Path | None = None) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    paths = store_paths(store_dir)
    dedupe_entries: dict[str, dict[str, Any]] = {kind: {} for kind in JSONL_KINDS}
    compacted_counts: dict[str, int] = {}
    removed_counts: dict[str, int] = {}

    for kind in JSONL_KINDS:
        rows = read_jsonl(paths[kind])
        unique_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        removed = 0
        for row in rows:
            signature = row_signature(row)
            if signature in seen:
                removed += 1
                continue
            seen.add(signature)
            row = dict(row)
            row["signature"] = signature
            unique_rows.append(row)
            dedupe_entries[kind][signature] = {
                "signature": signature,
                "file": JSONL_KINDS[kind],
                "captured_at": str(row.get("captured_at") or row.get("created_at") or iso_now()),
            }
        write_jsonl(paths[kind], unique_rows)
        compacted_counts[kind] = len(unique_rows)
        removed_counts[kind] = removed

    save_dedupe_index(
        {
            "schema": "ai_subtitle_studio.personalization_dedupe_index.v1",
            "updated_at": iso_now(),
            "entries": dedupe_entries,
        },
        store_dir,
    )
    manifest = refresh_lora_personalization_manifest(store_dir)
    return {
        "manifest": manifest,
        "compacted_counts": compacted_counts,
        "removed_counts": removed_counts,
    }
