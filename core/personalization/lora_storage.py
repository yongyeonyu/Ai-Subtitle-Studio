from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.personalization.lora_models import iso_now, stable_hash
from core.runtime import config


LORA_PERSONALIZATION_DIR = Path(config.DATASET_DIR) / "lora_personalization"
LORA_MANIFEST_PATH = LORA_PERSONALIZATION_DIR / "manifest.json"
TRUTH_TABLE_PATH = LORA_PERSONALIZATION_DIR / "truth_table.jsonl"
TRAINING_QUEUE_PATH = LORA_PERSONALIZATION_DIR / "training_queue.json"
LEARNED_SPLIT_RULES_PATH = LORA_PERSONALIZATION_DIR / "learned_split_rules.json"
LEARNED_LINE_BREAK_RULES_PATH = LORA_PERSONALIZATION_DIR / "learned_line_break_rules.json"
SETTING_TRIALS_PATH = LORA_PERSONALIZATION_DIR / "setting_trials.jsonl"
PROMPT_TRIALS_PATH = LORA_PERSONALIZATION_DIR / "prompt_trials.jsonl"
BEST_SETTINGS_PATH = LORA_PERSONALIZATION_DIR / "best_settings.json"
EXCLUDED_PARENTHETICALS_PATH = LORA_PERSONALIZATION_DIR / "excluded_parentheticals.jsonl"
DEDUPE_INDEX_PATH = LORA_PERSONALIZATION_DIR / "dedupe_index.json"
TRAINED_ADAPTERS_DIR = LORA_PERSONALIZATION_DIR / "trained_adapters"
LLM_REVIEW_REQUEST_PATH = LORA_PERSONALIZATION_DIR / "llm_review_request.json"
LLM_REVIEW_RESULT_PATH = LORA_PERSONALIZATION_DIR / "llm_review_result.json"
RETENTION_POLICY_PATH = LORA_PERSONALIZATION_DIR / "retention_policy.json"
RETENTION_HISTORY_PATH = LORA_PERSONALIZATION_DIR / "retention_history.jsonl"
UNIFIED_LORA_DATA_PATH = LORA_PERSONALIZATION_DIR / "lora_data_bundle.json"
VOICE_LORA_BRIDGE_PATH = LORA_PERSONALIZATION_DIR / "voice_lora_bridge.jsonl"
VOICE_LORA_PROFILE_MANIFEST_PATH = LORA_PERSONALIZATION_DIR / "voice_lora_profile_manifest.json"
VOICE_LORA_TRAINING_PLAN_PATH = LORA_PERSONALIZATION_DIR / "voice_lora_training_plan.json"
VOICE_LORA_DATASET_MANIFEST_PATH = LORA_PERSONALIZATION_DIR / "voice_lora_dataset_manifest.json"

JSONL_KINDS = {
    "truth_table": TRUTH_TABLE_PATH.name,
    "excluded_parentheticals": EXCLUDED_PARENTHETICALS_PATH.name,
    "setting_trials": SETTING_TRIALS_PATH.name,
    "prompt_trials": PROMPT_TRIALS_PATH.name,
}


def _store_dir(store_dir: str | Path | None = None) -> Path:
    return Path(store_dir) if store_dir else LORA_PERSONALIZATION_DIR


def store_paths(store_dir: str | Path | None = None) -> dict[str, Path]:
    root = _store_dir(store_dir)
    return {
        "root": root,
        "manifest": root / LORA_MANIFEST_PATH.name,
        "truth_table": root / TRUTH_TABLE_PATH.name,
        "training_queue": root / TRAINING_QUEUE_PATH.name,
        "learned_split_rules": root / LEARNED_SPLIT_RULES_PATH.name,
        "learned_line_break_rules": root / LEARNED_LINE_BREAK_RULES_PATH.name,
        "setting_trials": root / SETTING_TRIALS_PATH.name,
        "prompt_trials": root / PROMPT_TRIALS_PATH.name,
        "best_settings": root / BEST_SETTINGS_PATH.name,
        "excluded_parentheticals": root / EXCLUDED_PARENTHETICALS_PATH.name,
        "dedupe_index": root / DEDUPE_INDEX_PATH.name,
        "trained_adapters": root / TRAINED_ADAPTERS_DIR.name,
        "llm_review_request": root / LLM_REVIEW_REQUEST_PATH.name,
        "llm_review_result": root / LLM_REVIEW_RESULT_PATH.name,
        "retention_policy": root / RETENTION_POLICY_PATH.name,
        "retention_history": root / RETENTION_HISTORY_PATH.name,
        "unified_lora_data": root / UNIFIED_LORA_DATA_PATH.name,
        "voice_lora_bridge": root / VOICE_LORA_BRIDGE_PATH.name,
        "voice_lora_profile_manifest": root / VOICE_LORA_PROFILE_MANIFEST_PATH.name,
        "voice_lora_training_plan": root / VOICE_LORA_TRAINING_PLAN_PATH.name,
        "voice_lora_dataset_manifest": root / VOICE_LORA_DATASET_MANIFEST_PATH.name,
        "voice_lora_clips": root / TRAINED_ADAPTERS_DIR.name / "personal_voice_lora" / "clips",
    }


def personalization_path_lookup_keys(path: str | Path | None) -> list[str]:
    raw = str(path or "").strip()
    if not raw:
        return []

    keys: list[str] = []

    def add(value: str) -> None:
        text = str(value or "").strip()
        if text and text not in keys:
            keys.append(text)

    def normalize_slashes(value: str) -> str:
        text = str(value or "").strip().replace("\\", "/")
        if text.lower().startswith("smb://"):
            body = re.sub(r"/{2,}", "/", text[6:]).lstrip("/")
            return f"smb://{body}"
        normalized = re.sub(r"/{2,}", "/", text)
        if value.startswith("\\\\") or text.startswith("//"):
            return f"//{normalized.lstrip('/')}"
        return normalized

    add(raw)
    normalized = normalize_slashes(raw)
    add(normalized)

    is_casefold_target = bool(
        re.match(r"^[A-Za-z]:[\\/]", raw)
        or raw.startswith("\\\\")
        or normalized.startswith("//")
        or normalized.lower().startswith("smb://")
    )
    if is_casefold_target:
        for value in list(keys):
            add(value.casefold())

    return keys


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _default_queue() -> dict[str, Any]:
    return {
        "schema": "ai_subtitle_studio.personalization_training_queue.v1",
        "updated_at": iso_now(),
        "items": [],
    }


def _default_learned_rules(schema_name: str) -> dict[str, Any]:
    return {
        "schema": schema_name,
        "updated_at": iso_now(),
        "metadata": {},
        "items": [],
    }


def _default_best_settings() -> dict[str, Any]:
    return {
        "schema": "ai_subtitle_studio.personalization_best_settings.v1",
        "updated_at": iso_now(),
        "global_recommended_defaults": {},
        "by_media_id": {},
        "by_media_path": {},
        "by_audio_profile": {},
        "by_style_cluster": {},
    }


def _default_dedupe_index() -> dict[str, Any]:
    return {
        "schema": "ai_subtitle_studio.personalization_dedupe_index.v1",
        "updated_at": iso_now(),
        "entries": {kind: {} for kind in JSONL_KINDS},
    }


def _default_retention_policy() -> dict[str, Any]:
    return {
        "schema": "ai_subtitle_studio.personalization_retention_policy.v1",
        "updated_at": iso_now(),
        "enabled": True,
        "strategy": "evolutionary_low_score_pruning",
        "notes": [
            "After new personalization training, remove a small number of low-value rows instead of growing forever.",
            "Rows with explicit scores are pruned by score first; learned rules are pruned by confidence and frequency.",
            "Minimum keep counts protect small datasets from accidental deletion.",
        ],
        "jsonl": {
            "setting_trials": {"min_keep": 64, "max_rows": 2048, "remove_per_training": 1},
            "prompt_trials": {"min_keep": 64, "max_rows": 2048, "remove_per_training": 1},
            "truth_table": {"min_keep": 512, "max_rows": 12000, "remove_per_training": 0},
            "excluded_parentheticals": {"min_keep": 512, "max_rows": 4000, "remove_per_training": 0},
        },
        "rules": {
            "split": {"max_items": 256},
            "line_break": {"max_items": 256},
        },
    }


UNIFIED_LORA_BUNDLE_SOURCE_KEYS = (
    "truth_table",
    "excluded_parentheticals",
    "setting_trials",
    "prompt_trials",
    "training_queue",
    "learned_split_rules",
    "learned_line_break_rules",
    "best_settings",
    "dedupe_index",
    "retention_policy",
    "retention_history",
    "llm_review_request",
    "llm_review_result",
    "voice_lora_bridge",
    "voice_lora_profile_manifest",
    "voice_lora_training_plan",
    "voice_lora_dataset_manifest",
)


def _source_max_mtime(paths: dict[str, Path]) -> float:
    max_mtime = 0.0
    for key in UNIFIED_LORA_BUNDLE_SOURCE_KEYS:
        path = paths.get(key)
        if path is None or not path.exists():
            continue
        try:
            max_mtime = max(max_mtime, float(path.stat().st_mtime))
        except OSError:
            continue
    return max_mtime


def _bundle_file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "size_bytes": 0}
    try:
        return {"path": str(path), "exists": True, "size_bytes": int(path.stat().st_size)}
    except OSError:
        return {"path": str(path), "exists": True, "size_bytes": 0}


def _count_ready_voice_audio_items(plan: dict[str, Any]) -> int:
    ready = 0
    for item in list((plan or {}).get("items") or []):
        raw = str(item.get("audio_path") or "").strip()
        if raw and Path(raw).exists():
            ready += 1
    return ready


def _build_unified_lora_data_bundle(paths: dict[str, Path]) -> dict[str, Any]:
    truth_rows = _read_jsonl(paths["truth_table"])
    excluded_rows = _read_jsonl(paths["excluded_parentheticals"])
    setting_trials = _read_jsonl(paths["setting_trials"])
    prompt_trials = _read_jsonl(paths["prompt_trials"])
    retention_history = _read_jsonl(paths["retention_history"])
    voice_bridge_rows = _read_jsonl(paths["voice_lora_bridge"])
    voice_profile_manifest = _read_json(paths["voice_lora_profile_manifest"], {})
    voice_training_plan = _read_json(paths["voice_lora_training_plan"], {})
    voice_dataset_manifest = _read_json(paths["voice_lora_dataset_manifest"], {})
    records = (
        [{"kind": "truth_table", "record": row} for row in truth_rows]
        + [{"kind": "excluded_parentheticals", "record": row} for row in excluded_rows]
        + [{"kind": "setting_trials", "record": row} for row in setting_trials]
        + [{"kind": "prompt_trials", "record": row} for row in prompt_trials]
        + [{"kind": "voice_lora_bridge", "record": row} for row in voice_bridge_rows]
    )
    return {
        "schema": "ai_subtitle_studio.lora_unified_data_bundle.v1",
        "updated_at": iso_now(),
        "storage_mode": "single_file_bundle",
        "store_dir": str(paths["root"]),
        "counts": {
            "truth_table_rows": len(truth_rows),
            "excluded_parenthetical_rows": len(excluded_rows),
            "setting_trial_rows": len(setting_trials),
            "prompt_trial_rows": len(prompt_trials),
            "retention_history_rows": len(retention_history),
            "voice_lora_bridge_rows": len(voice_bridge_rows),
            "voice_lora_training_items": len(list((voice_training_plan or {}).get("items") or [])),
            "voice_lora_stored_audio_items": _count_ready_voice_audio_items(voice_training_plan),
            "unified_training_records": len(records),
        },
        "sections": {
            "truth_table": truth_rows,
            "excluded_parentheticals": excluded_rows,
            "setting_trials": setting_trials,
            "prompt_trials": prompt_trials,
            "training_queue": _read_json(paths["training_queue"], _default_queue()),
            "learned_split_rules": _read_json(
                paths["learned_split_rules"],
                _default_learned_rules("ai_subtitle_studio.learned_split_rules.v1"),
            ),
            "learned_line_break_rules": _read_json(
                paths["learned_line_break_rules"],
                _default_learned_rules("ai_subtitle_studio.learned_line_break_rules.v1"),
            ),
            "best_settings": _read_json(paths["best_settings"], _default_best_settings()),
            "retention_policy": _read_json(paths["retention_policy"], _default_retention_policy()),
            "retention_history": retention_history,
            "llm_review_request": _read_json(paths["llm_review_request"], {}),
            "llm_review_result": _read_json(paths["llm_review_result"], {}),
            "voice_lora_bridge": voice_bridge_rows,
            "voice_lora_profile_manifest": voice_profile_manifest,
            "voice_lora_training_plan": voice_training_plan,
            "voice_lora_dataset_manifest": voice_dataset_manifest,
        },
        "records": records,
        "notes": [
            "This file is the portable single-file LoRA personalization data bundle.",
            "The app may still maintain shard files internally for fast append and pruning.",
            "Use sections for structured restore/review and records for flat training-data scans.",
        ],
    }


def refresh_unified_lora_data_bundle(
    store_dir: str | Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    target = paths["unified_lora_data"]
    needs_refresh = bool(force or not target.exists())
    if not needs_refresh:
        try:
            needs_refresh = _source_max_mtime(paths) > float(target.stat().st_mtime)
        except OSError:
            needs_refresh = True
    counts: dict[str, Any] = {}
    if needs_refresh:
        payload = _build_unified_lora_data_bundle(paths)
        counts = dict(payload.get("counts") or {})
        _write_json(target, payload)
    if not counts:
        truth_rows = len(_read_jsonl(paths["truth_table"]))
        excluded_rows = len(_read_jsonl(paths["excluded_parentheticals"]))
        setting_rows = len(_read_jsonl(paths["setting_trials"]))
        prompt_rows = len(_read_jsonl(paths["prompt_trials"]))
        voice_rows = len(_read_jsonl(paths["voice_lora_bridge"]))
        voice_training_plan = _read_json(paths["voice_lora_training_plan"], {})
        counts = {
            "truth_table_rows": truth_rows,
            "excluded_parenthetical_rows": excluded_rows,
            "setting_trial_rows": setting_rows,
            "prompt_trial_rows": prompt_rows,
            "voice_lora_bridge_rows": voice_rows,
            "voice_lora_training_items": len(list((voice_training_plan or {}).get("items") or [])),
            "voice_lora_stored_audio_items": _count_ready_voice_audio_items(voice_training_plan),
            "unified_training_records": truth_rows + excluded_rows + setting_rows + prompt_rows + voice_rows,
        }
    return {
        **_bundle_file_info(target),
        "refreshed": needs_refresh,
        "counts": counts,
        "record_count": int(counts.get("unified_training_records", 0) or 0),
    }


def initialize_lora_personalization_store(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["trained_adapters"].mkdir(parents=True, exist_ok=True)
    for key in ("truth_table", "setting_trials", "prompt_trials", "excluded_parentheticals", "retention_history", "voice_lora_bridge"):
        paths[key].touch(exist_ok=True)
    if not paths["training_queue"].exists():
        _write_json(paths["training_queue"], _default_queue())
    if not paths["learned_split_rules"].exists():
        _write_json(
            paths["learned_split_rules"],
            _default_learned_rules("ai_subtitle_studio.learned_split_rules.v1"),
        )
    if not paths["learned_line_break_rules"].exists():
        _write_json(
            paths["learned_line_break_rules"],
            _default_learned_rules("ai_subtitle_studio.learned_line_break_rules.v1"),
        )
    if not paths["best_settings"].exists():
        _write_json(paths["best_settings"], _default_best_settings())
    if not paths["dedupe_index"].exists():
        _write_json(paths["dedupe_index"], _default_dedupe_index())
    if not paths["retention_policy"].exists():
        _write_json(paths["retention_policy"], _default_retention_policy())
    return refresh_lora_personalization_manifest(store_dir)


def refresh_lora_personalization_manifest(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    voice_training_plan = _read_json(paths["voice_lora_training_plan"], {})
    counts = {
        "truth_table_rows": len(_read_jsonl(paths["truth_table"])),
        "excluded_parenthetical_rows": len(_read_jsonl(paths["excluded_parentheticals"])),
        "setting_trial_rows": len(_read_jsonl(paths["setting_trials"])),
        "prompt_trial_rows": len(_read_jsonl(paths["prompt_trials"])),
        "queue_items": len(list((_read_json(paths["training_queue"], _default_queue()) or {}).get("items") or [])),
        "learned_split_rules": len(list((_read_json(paths["learned_split_rules"], {}) or {}).get("items") or [])),
        "learned_line_break_rules": len(list((_read_json(paths["learned_line_break_rules"], {}) or {}).get("items") or [])),
        "dedupe_entry_count": sum(
            len(dict(v or {})) for v in dict((_read_json(paths["dedupe_index"], _default_dedupe_index()) or {}).get("entries") or {}).values()
        ),
        "llm_review_request_files": 1 if paths["llm_review_request"].exists() else 0,
        "llm_review_result_files": 1 if paths["llm_review_result"].exists() else 0,
        "retention_history_rows": len(_read_jsonl(paths["retention_history"])),
        "voice_lora_bridge_rows": len(_read_jsonl(paths["voice_lora_bridge"])),
        "voice_lora_profile_count": len(list((_read_json(paths["voice_lora_profile_manifest"], {}) or {}).get("speaker_profiles") or [])),
        "voice_lora_training_items": len(list((voice_training_plan or {}).get("items") or [])),
        "voice_lora_stored_audio_items": _count_ready_voice_audio_items(voice_training_plan),
    }
    bundle_info = refresh_unified_lora_data_bundle(store_dir)
    counts.update(
        {
        "unified_lora_data_files": 1 if bool(bundle_info.get("exists")) else 0,
        "unified_lora_data_bytes": int(bundle_info.get("size_bytes", 0) or 0),
        "unified_lora_data_records": int(
            counts.get("truth_table_rows", 0)
            + counts.get("excluded_parenthetical_rows", 0)
            + counts.get("setting_trial_rows", 0)
            + counts.get("prompt_trial_rows", 0)
            + counts.get("voice_lora_bridge_rows", 0)
        ),
        }
    )
    manifest = {
        "schema": "ai_subtitle_studio.lora_personalization_manifest.v1",
        "updated_at": iso_now(),
        "store_dir": str(paths["root"]),
        "files": {key: str(value) for key, value in paths.items() if key != "root"},
        "counts": counts,
        "notes": [
            "PHASE3 ground-truth personalization storage root",
            "truth table, training queue, learned rules, setting/prompt trials, best settings, and dedupe index live here",
            "source media is referenced in place by default",
        ],
    }
    _write_json(paths["manifest"], manifest)
    return manifest


def load_training_queue(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    return _read_json(paths["training_queue"], _default_queue())


def save_training_queue(items: list[dict[str, Any]], store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    payload = {
        "schema": "ai_subtitle_studio.personalization_training_queue.v1",
        "updated_at": iso_now(),
        "items": list(items or []),
    }
    _write_json(paths["training_queue"], payload)
    refresh_lora_personalization_manifest(store_dir)
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
        return _read_json(
            paths["learned_split_rules"],
            _default_learned_rules("ai_subtitle_studio.learned_split_rules.v1"),
        )
    if rule_kind == "line_break":
        return _read_json(
            paths["learned_line_break_rules"],
            _default_learned_rules("ai_subtitle_studio.learned_line_break_rules.v1"),
        )
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
    _write_json(path, payload)
    refresh_lora_personalization_manifest(store_dir)
    return payload


def load_best_settings(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    return _read_json(paths["best_settings"], _default_best_settings())


def save_best_settings(payload: dict[str, Any], store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    merged = _default_best_settings()
    merged.update(dict(payload or {}))
    merged["updated_at"] = iso_now()
    _write_json(paths["best_settings"], merged)
    refresh_lora_personalization_manifest(store_dir)
    return merged


def load_dedupe_index(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    payload = _read_json(paths["dedupe_index"], _default_dedupe_index())
    entries = dict(payload.get("entries") or {})
    for kind in JSONL_KINDS:
        entries.setdefault(kind, {})
    payload["entries"] = entries
    return payload


def save_dedupe_index(payload: dict[str, Any], store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    merged = _default_dedupe_index()
    merged.update(dict(payload or {}))
    merged["updated_at"] = iso_now()
    entries = dict(merged.get("entries") or {})
    for kind in JSONL_KINDS:
        entries.setdefault(kind, {})
    merged["entries"] = entries
    _write_json(paths["dedupe_index"], merged)
    refresh_lora_personalization_manifest(store_dir)
    return merged


def load_retention_policy(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    payload = _read_json(paths["retention_policy"], _default_retention_policy())
    defaults = _default_retention_policy()
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
    merged = _default_retention_policy()
    merged.update(dict(payload or {}))
    merged["updated_at"] = iso_now()
    _write_json(paths["retention_policy"], merged)
    refresh_lora_personalization_manifest(store_dir)
    return merged


def _row_signature(row: dict[str, Any]) -> str:
    return str(
        row.get("dedupe_hash")
        or row.get("signature")
        or stable_hash(dict(row or {}))
    )


def _append_unique_rows(
    kind: str,
    rows: list[dict[str, Any]],
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    dedupe = load_dedupe_index(store_dir)
    entries = dedupe["entries"][kind]
    existing_rows = _read_jsonl(paths[kind])
    appended = 0
    with paths[kind].open("a", encoding="utf-8") as handle:
        for row in list(rows or []):
            signature = _row_signature(row)
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
    save_dedupe_index(dedupe, store_dir)
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


def compact_lora_personalization_store(store_dir: str | Path | None = None) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    paths = store_paths(store_dir)
    dedupe_entries: dict[str, dict[str, Any]] = {kind: {} for kind in JSONL_KINDS}
    compacted_counts: dict[str, int] = {}
    removed_counts: dict[str, int] = {}

    for kind in JSONL_KINDS:
        rows = _read_jsonl(paths[kind])
        unique_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        removed = 0
        for row in rows:
            signature = _row_signature(row)
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
        _write_jsonl(paths[kind], unique_rows)
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


__all__ = [
    "BEST_SETTINGS_PATH",
    "DEDUPE_INDEX_PATH",
    "EXCLUDED_PARENTHETICALS_PATH",
    "LEARNED_LINE_BREAK_RULES_PATH",
    "LEARNED_SPLIT_RULES_PATH",
    "LLM_REVIEW_REQUEST_PATH",
    "LLM_REVIEW_RESULT_PATH",
    "LORA_MANIFEST_PATH",
    "LORA_PERSONALIZATION_DIR",
    "PROMPT_TRIALS_PATH",
    "RETENTION_HISTORY_PATH",
    "RETENTION_POLICY_PATH",
    "SETTING_TRIALS_PATH",
    "TRAINED_ADAPTERS_DIR",
    "TRAINING_QUEUE_PATH",
    "TRUTH_TABLE_PATH",
    "UNIFIED_LORA_DATA_PATH",
    "VOICE_LORA_BRIDGE_PATH",
    "VOICE_LORA_DATASET_MANIFEST_PATH",
    "VOICE_LORA_PROFILE_MANIFEST_PATH",
    "VOICE_LORA_TRAINING_PLAN_PATH",
    "append_excluded_parentheticals",
    "append_prompt_trials",
    "append_setting_trials",
    "append_truth_table_rows",
    "compact_lora_personalization_store",
    "initialize_lora_personalization_store",
    "load_best_settings",
    "load_dedupe_index",
    "load_learned_rules",
    "load_retention_policy",
    "load_training_queue",
    "personalization_path_lookup_keys",
    "refresh_lora_personalization_manifest",
    "refresh_unified_lora_data_bundle",
    "clear_training_queue",
    "save_best_settings",
    "save_dedupe_index",
    "save_learned_rules",
    "save_retention_policy",
    "save_training_queue",
    "store_paths",
    "upsert_training_queue_items",
]
