from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from core.personalization.lora_models import iso_now, stable_hash
from core.personalization.lora_quality_buckets import (
    LORA_BUCKET_FILENAMES,
    LORA_BUCKET_HIGH,
    LORA_BUCKET_LOW,
    LORA_BUCKET_MEDIUM,
    LORA_BUCKET_PENDING_DELETE,
    strip_lora_quality_metadata,
)
from core.runtime import config


LORA_PERSONALIZATION_DIR = Path(config.DATASET_DIR) / "lora_personalization"
LORA_INTERNAL_CACHE_DIR_NAME = ".cache"
LORA_INTERNAL_CACHE_DIR = LORA_PERSONALIZATION_DIR / LORA_INTERNAL_CACHE_DIR_NAME
LORA_MANIFEST_PATH = LORA_INTERNAL_CACHE_DIR / "manifest.json"
TRUTH_TABLE_PATH = LORA_INTERNAL_CACHE_DIR / "truth_table.jsonl"
TRAINING_QUEUE_PATH = LORA_INTERNAL_CACHE_DIR / "training_queue.json"
LEARNED_SPLIT_RULES_PATH = LORA_INTERNAL_CACHE_DIR / "learned_split_rules.json"
LEARNED_LINE_BREAK_RULES_PATH = LORA_INTERNAL_CACHE_DIR / "learned_line_break_rules.json"
SETTING_TRIALS_PATH = LORA_INTERNAL_CACHE_DIR / "setting_trials.jsonl"
PROMPT_TRIALS_PATH = LORA_INTERNAL_CACHE_DIR / "prompt_trials.jsonl"
BEST_SETTINGS_PATH = LORA_INTERNAL_CACHE_DIR / "best_settings.json"
EXCLUDED_PARENTHETICALS_PATH = LORA_INTERNAL_CACHE_DIR / "excluded_parentheticals.jsonl"
DEDUPE_INDEX_PATH = LORA_INTERNAL_CACHE_DIR / "dedupe_index.json"
TRAINED_ADAPTERS_DIR = LORA_INTERNAL_CACHE_DIR / "trained_adapters"
LLM_REVIEW_REQUEST_PATH = LORA_INTERNAL_CACHE_DIR / "llm_review_request.json"
LLM_REVIEW_RESULT_PATH = LORA_INTERNAL_CACHE_DIR / "llm_review_result.json"
RETENTION_POLICY_PATH = LORA_INTERNAL_CACHE_DIR / "retention_policy.json"
RETENTION_HISTORY_PATH = LORA_INTERNAL_CACHE_DIR / "retention_history.jsonl"
UNIFIED_LORA_DATA_PATH = LORA_PERSONALIZATION_DIR / LORA_BUCKET_FILENAMES[LORA_BUCKET_HIGH]
LORA_MEDIUM_DATA_PATH = LORA_PERSONALIZATION_DIR / LORA_BUCKET_FILENAMES[LORA_BUCKET_MEDIUM]
LORA_LOW_DATA_PATH = LORA_PERSONALIZATION_DIR / LORA_BUCKET_FILENAMES[LORA_BUCKET_LOW]
LORA_PENDING_DELETE_DATA_PATH = LORA_PERSONALIZATION_DIR / LORA_BUCKET_FILENAMES[LORA_BUCKET_PENDING_DELETE]
LEGACY_UNIFIED_LORA_DATA_PATH = LORA_PERSONALIZATION_DIR / "lora_data_bundle.json"
LEGACY_UNIFIED_LORA_ZIP_PATH = LORA_PERSONALIZATION_DIR / "lora_data_bundle.zip"
UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME = "lora_data_bundle.json"
UNIFIED_LORA_ARCHIVE_MANIFEST_NAME = "manifest.json"
VOICE_LORA_BRIDGE_PATH = LORA_INTERNAL_CACHE_DIR / "voice_lora_bridge.jsonl"
VOICE_LORA_PROFILE_MANIFEST_PATH = LORA_INTERNAL_CACHE_DIR / "voice_lora_profile_manifest.json"
VOICE_LORA_TRAINING_PLAN_PATH = LORA_INTERNAL_CACHE_DIR / "voice_lora_training_plan.json"
VOICE_LORA_DATASET_MANIFEST_PATH = LORA_INTERNAL_CACHE_DIR / "voice_lora_dataset_manifest.json"
STT1_WHISPER_ADAPTER_DATASET_PATH = LORA_INTERNAL_CACHE_DIR / "stt1_whisper_adapter_dataset.jsonl"
STT1_WHISPER_ADAPTER_DATASET_MANIFEST_PATH = LORA_INTERNAL_CACHE_DIR / "stt1_whisper_adapter_dataset_manifest.json"
STT1_WHISPER_ADAPTER_TRAINING_PLAN_PATH = LORA_INTERNAL_CACHE_DIR / "stt1_whisper_adapter_training_plan.json"
STT1_WHISPER_ADAPTER_RUNTIME_MANIFEST_PATH = LORA_INTERNAL_CACHE_DIR / "stt1_whisper_adapter_runtime_manifest.json"
TEXT_LORA_DATASET_PATH = LORA_INTERNAL_CACHE_DIR / "text_lora_dataset.jsonl"
TEXT_LORA_MANIFEST_PATH = LORA_INTERNAL_CACHE_DIR / "text_lora_manifest.json"
TEXT_LORA_CORPUS_PATH = LORA_INTERNAL_CACHE_DIR / "text_lora_corpus.jsonl"
TEXT_LORA_CORPUS_MANIFEST_PATH = LORA_INTERNAL_CACHE_DIR / "text_lora_corpus_manifest.json"
TEXT_LORA_TRAINING_PLAN_PATH = LORA_INTERNAL_CACHE_DIR / "text_lora_training_plan.json"
AUDIO_PRESET_LORA_PATH = LORA_INTERNAL_CACHE_DIR / "audio_preset_lora.jsonl"
MULTIMODAL_LORA_CONTEXT_PATH = LORA_INTERNAL_CACHE_DIR / "multimodal_lora_context.jsonl"
DEEP_POLICY_EVENTS_PATH = LORA_INTERNAL_CACHE_DIR / "deep_policy_events.jsonl"
LORA_RETRIEVAL_INDEX_PATH = LORA_INTERNAL_CACHE_DIR / "lora_retrieval_index.json"
SUBTITLE_PATTERN_INDEX_PATH = LORA_INTERNAL_CACHE_DIR / "subtitle_pattern_index.json"

JSONL_KINDS = {
    "truth_table": TRUTH_TABLE_PATH.name,
    "excluded_parentheticals": EXCLUDED_PARENTHETICALS_PATH.name,
    "setting_trials": SETTING_TRIALS_PATH.name,
    "prompt_trials": PROMPT_TRIALS_PATH.name,
    "voice_lora_bridge": VOICE_LORA_BRIDGE_PATH.name,
    "stt1_whisper_adapter_dataset": STT1_WHISPER_ADAPTER_DATASET_PATH.name,
    "text_lora_dataset": TEXT_LORA_DATASET_PATH.name,
    "text_lora_corpus": TEXT_LORA_CORPUS_PATH.name,
    "audio_preset_lora": AUDIO_PRESET_LORA_PATH.name,
    "multimodal_lora_context": MULTIMODAL_LORA_CONTEXT_PATH.name,
    "deep_policy_events": DEEP_POLICY_EVENTS_PATH.name,
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
    "stt1_whisper_adapter_dataset",
    "stt1_whisper_adapter_dataset_manifest",
    "stt1_whisper_adapter_training_plan",
    "stt1_whisper_adapter_runtime_manifest",
    "voice_lora_profile_manifest",
    "voice_lora_training_plan",
    "voice_lora_dataset_manifest",
    "text_lora_dataset",
    "text_lora_manifest",
    "text_lora_corpus",
    "text_lora_corpus_manifest",
    "text_lora_training_plan",
    "audio_preset_lora",
    "multimodal_lora_context",
    "deep_policy_events",
    "lora_retrieval_index",
    "subtitle_pattern_index",
)
BUNDLE_JSONL_SECTION_KEYS = (
    "truth_table",
    "excluded_parentheticals",
    "setting_trials",
    "prompt_trials",
    "retention_history",
    "voice_lora_bridge",
    "stt1_whisper_adapter_dataset",
    "text_lora_dataset",
    "text_lora_corpus",
    "audio_preset_lora",
    "multimodal_lora_context",
    "deep_policy_events",
)
BUNDLE_JSON_SECTION_KEYS = (
    "training_queue",
    "learned_split_rules",
    "learned_line_break_rules",
    "best_settings",
    "dedupe_index",
    "retention_policy",
    "llm_review_request",
    "llm_review_result",
    "voice_lora_profile_manifest",
    "voice_lora_training_plan",
    "voice_lora_dataset_manifest",
    "stt1_whisper_adapter_dataset_manifest",
    "stt1_whisper_adapter_training_plan",
    "stt1_whisper_adapter_runtime_manifest",
    "text_lora_manifest",
    "text_lora_corpus_manifest",
    "text_lora_training_plan",
    "lora_retrieval_index",
    "subtitle_pattern_index",
)


def store_dir_path(store_dir: str | Path | None = None) -> Path:
    return Path(store_dir) if store_dir else LORA_PERSONALIZATION_DIR


def store_paths(store_dir: str | Path | None = None) -> dict[str, Path]:
    root = store_dir_path(store_dir)
    cache_root = root / LORA_INTERNAL_CACHE_DIR_NAME
    return {
        "root": root,
        "cache_root": cache_root,
        "manifest": cache_root / LORA_MANIFEST_PATH.name,
        "truth_table": cache_root / TRUTH_TABLE_PATH.name,
        "training_queue": cache_root / TRAINING_QUEUE_PATH.name,
        "learned_split_rules": cache_root / LEARNED_SPLIT_RULES_PATH.name,
        "learned_line_break_rules": cache_root / LEARNED_LINE_BREAK_RULES_PATH.name,
        "setting_trials": cache_root / SETTING_TRIALS_PATH.name,
        "prompt_trials": cache_root / PROMPT_TRIALS_PATH.name,
        "best_settings": cache_root / BEST_SETTINGS_PATH.name,
        "excluded_parentheticals": cache_root / EXCLUDED_PARENTHETICALS_PATH.name,
        "dedupe_index": cache_root / DEDUPE_INDEX_PATH.name,
        "trained_adapters": cache_root / TRAINED_ADAPTERS_DIR.name,
        "llm_review_request": cache_root / LLM_REVIEW_REQUEST_PATH.name,
        "llm_review_result": cache_root / LLM_REVIEW_RESULT_PATH.name,
        "retention_policy": cache_root / RETENTION_POLICY_PATH.name,
        "retention_history": cache_root / RETENTION_HISTORY_PATH.name,
        "unified_lora_data": root / UNIFIED_LORA_DATA_PATH.name,
        "lora_data_high": root / UNIFIED_LORA_DATA_PATH.name,
        "lora_data_medium": root / LORA_MEDIUM_DATA_PATH.name,
        "lora_data_low": root / LORA_LOW_DATA_PATH.name,
        "lora_data_pending_delete": root / LORA_PENDING_DELETE_DATA_PATH.name,
        "legacy_unified_lora_data": root / LEGACY_UNIFIED_LORA_DATA_PATH.name,
        "legacy_unified_lora_zip": root / LEGACY_UNIFIED_LORA_ZIP_PATH.name,
        "voice_lora_bridge": cache_root / VOICE_LORA_BRIDGE_PATH.name,
        "voice_lora_profile_manifest": cache_root / VOICE_LORA_PROFILE_MANIFEST_PATH.name,
        "voice_lora_training_plan": cache_root / VOICE_LORA_TRAINING_PLAN_PATH.name,
        "voice_lora_dataset_manifest": cache_root / VOICE_LORA_DATASET_MANIFEST_PATH.name,
        "voice_lora_clips": cache_root / TRAINED_ADAPTERS_DIR.name / "personal_voice_lora" / "clips",
        "stt1_whisper_adapter_dataset": cache_root / STT1_WHISPER_ADAPTER_DATASET_PATH.name,
        "stt1_whisper_adapter_dataset_manifest": cache_root / STT1_WHISPER_ADAPTER_DATASET_MANIFEST_PATH.name,
        "stt1_whisper_adapter_training_plan": cache_root / STT1_WHISPER_ADAPTER_TRAINING_PLAN_PATH.name,
        "stt1_whisper_adapter_runtime_manifest": cache_root / STT1_WHISPER_ADAPTER_RUNTIME_MANIFEST_PATH.name,
        "stt1_whisper_adapter_clips": cache_root / TRAINED_ADAPTERS_DIR.name / "personal_stt1_whisper_adapter" / "clips",
        "text_lora_dataset": cache_root / TEXT_LORA_DATASET_PATH.name,
        "text_lora_manifest": cache_root / TEXT_LORA_MANIFEST_PATH.name,
        "text_lora_corpus": cache_root / TEXT_LORA_CORPUS_PATH.name,
        "text_lora_corpus_manifest": cache_root / TEXT_LORA_CORPUS_MANIFEST_PATH.name,
        "text_lora_training_plan": cache_root / TEXT_LORA_TRAINING_PLAN_PATH.name,
        "audio_preset_lora": cache_root / AUDIO_PRESET_LORA_PATH.name,
        "multimodal_lora_context": cache_root / MULTIMODAL_LORA_CONTEXT_PATH.name,
        "deep_policy_events": cache_root / DEEP_POLICY_EVENTS_PATH.name,
        "lora_retrieval_index": cache_root / LORA_RETRIEVAL_INDEX_PATH.name,
        "subtitle_pattern_index": cache_root / SUBTITLE_PATTERN_INDEX_PATH.name,
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


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def default_queue() -> dict[str, Any]:
    return {
        "schema": "ai_subtitle_studio.personalization_training_queue.v1",
        "updated_at": iso_now(),
        "items": [],
    }


def default_learned_rules(schema_name: str) -> dict[str, Any]:
    return {
        "schema": schema_name,
        "updated_at": iso_now(),
        "metadata": {},
        "items": [],
    }


def default_best_settings() -> dict[str, Any]:
    return {
        "schema": "ai_subtitle_studio.personalization_best_settings.v1",
        "updated_at": iso_now(),
        "global_recommended_defaults": {},
        "by_media_id": {},
        "by_media_path": {},
        "by_audio_profile": {},
        "by_style_cluster": {},
    }


def default_dedupe_index() -> dict[str, Any]:
    return {
        "schema": "ai_subtitle_studio.personalization_dedupe_index.v1",
        "updated_at": iso_now(),
        "entries": {kind: {} for kind in JSONL_KINDS},
    }


def default_retention_policy() -> dict[str, Any]:
    return {
        "schema": "ai_subtitle_studio.personalization_retention_policy.v1",
        "updated_at": iso_now(),
        "enabled": True,
        "strategy": "quality_bucketed_pattern_first_pruning",
        "auto_delete_pending": True,
        "sort_kept_rows": True,
        "protect_min_keep_for_pending": False,
        "notes": [
            "After new personalization training, delete pending-delete rows and keep active LoRA rows ordered high/medium/low.",
            "Rows are scored by explicit quality, compact subtitle-pattern signals, usage, and status.",
            "Rows without useful pattern payloads are treated as pending-delete so the store stays small and fast.",
            "Minimum keep counts protect small datasets from accidental deletion.",
            "Quality-bucket archives use a strict hard size cap, with smaller soft targets to keep runtime bundle reads fast.",
        ],
        "bundle_budgets": {
            "hard_max_bytes": 3 * 1024 * 1024 * 1024,
            "soft_max_bytes_by_bucket": {
                "high": 1536 * 1024 * 1024,
                "medium": 640 * 1024 * 1024,
                "low": 256 * 1024 * 1024,
                "pending_delete": 96 * 1024 * 1024,
            },
            "attachment_soft_max_bytes_by_bucket": {
                "high": 768 * 1024 * 1024,
                "medium": 0,
                "low": 0,
                "pending_delete": 0,
            },
        },
        "jsonl": {
            "truth_table": {"min_keep": 512, "max_rows": 12000, "remove_per_training": 1},
            "excluded_parentheticals": {"min_keep": 256, "max_rows": 4000, "remove_per_training": 1},
            "setting_trials": {"min_keep": 64, "max_rows": 2048, "remove_per_training": 1},
            "prompt_trials": {"min_keep": 64, "max_rows": 2048, "remove_per_training": 1},
            "voice_lora_bridge": {"min_keep": 0, "max_rows": 0, "remove_per_training": 0},
            "stt1_whisper_adapter_dataset": {"min_keep": 128, "max_rows": 4096, "remove_per_training": 1},
            "text_lora_dataset": {"min_keep": 256, "max_rows": 6000, "remove_per_training": 2},
            "text_lora_corpus": {"min_keep": 256, "max_rows": 6000, "remove_per_training": 2},
            "audio_preset_lora": {"min_keep": 64, "max_rows": 2048, "remove_per_training": 1},
            "multimodal_lora_context": {"min_keep": 128, "max_rows": 4096, "remove_per_training": 2},
            "deep_policy_events": {"min_keep": 256, "max_rows": 6000, "remove_per_training": 2},
        },
        "rules": {
            "split": {"max_items": 256},
            "line_break": {"max_items": 256},
        },
    }


def row_signature(row: dict[str, Any]) -> str:
    return str(row.get("dedupe_hash") or row.get("signature") or stable_hash(strip_lora_quality_metadata(dict(row or {}))))


def bundle_file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "size_bytes": 0}
    try:
        return {"path": str(path), "exists": True, "size_bytes": int(path.stat().st_size)}
    except OSError:
        return {"path": str(path), "exists": True, "size_bytes": 0}


def count_ready_voice_audio_items(plan: dict[str, Any]) -> int:
    ready = 0
    for item in list((plan or {}).get("items") or []):
        raw = str(item.get("audio_path") or "").strip()
        if raw and Path(raw).exists():
            ready += 1
    return ready
