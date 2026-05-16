from __future__ import annotations

import json
import os
import shutil
import threading
import time
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from core.personalization.lora_models import iso_now
from core.personalization.lora_quality_buckets import (
    LORA_ALL_BUCKETS,
    LORA_BUCKET_FILENAMES,
    LORA_BUCKET_HIGH,
    LORA_BUCKET_LABELS,
    LORA_BUCKET_PENDING_DELETE,
    lora_bucket_for_row,
    lora_row_sort_key,
    ranked_lora_rows,
)
from core.personalization.lora_store_common import (
    BUNDLE_JSON_SECTION_KEYS,
    BUNDLE_JSONL_SECTION_KEYS,
    JSONL_KINDS,
    UNIFIED_LORA_ARCHIVE_MANIFEST_NAME,
    UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME,
    UNIFIED_LORA_BUNDLE_SOURCE_KEYS,
    bundle_file_info,
    count_ready_voice_audio_items,
    default_best_settings,
    default_dedupe_index,
    default_learned_rules,
    default_queue,
    default_retention_policy,
    read_json,
    read_jsonl,
    row_signature,
    store_dir_path,
    store_paths,
    write_json,
    write_jsonl,
)
from core.native_json import dumps_json_bytes


LORA_ARCHIVE_COMPRESSION_NAME = "deflated_compact_patterns"
LORA_ARCHIVE_COMPRESSION_LEVEL = 6
LORA_BUNDLE_HARD_MAX_BYTES = 3 * 1024 * 1024 * 1024
LORA_BUNDLE_SOFT_MAX_BYTES_BY_BUCKET = {
    LORA_BUCKET_HIGH: 1536 * 1024 * 1024,
    "medium": 640 * 1024 * 1024,
    "low": 256 * 1024 * 1024,
    "pending_delete": 96 * 1024 * 1024,
}
LORA_BUNDLE_ATTACHMENT_SOFT_MAX_BYTES_BY_BUCKET = {
    LORA_BUCKET_HIGH: 768 * 1024 * 1024,
    "medium": 0,
    "low": 0,
    "pending_delete": 0,
}
_LORA_BUCKET_PATH_KEYS = {
    "high": "lora_data_high",
    "medium": "lora_data_medium",
    "low": "lora_data_low",
    "pending_delete": "lora_data_pending_delete",
}
_LEGACY_CACHE_DIR_NAMES = ("config_backups",)
_ROOT_METADATA_FILE_NAMES = (".DS_Store",)
_UNIFIED_LORA_ARCHIVE_WRITE_LOCK = threading.RLock()
_UNIFIED_LORA_TMP_STALE_SECONDS = 900


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return int(default)
    return parsed if parsed > 0 else int(default)


def _json_bytes(
    payload: Any,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
    compact: bool = False,
) -> bytes:
    return dumps_json_bytes(
        payload,
        indent=indent,
        sort_keys=sort_keys,
        compact=compact,
    )


def _serialized_json_size_bytes(payload: Any) -> int:
    try:
        return len(_json_bytes(payload, compact=True))
    except (TypeError, ValueError, OverflowError):
        return 0


def _iter_tree_file_paths(root: Path) -> list[str]:
    if not root.exists():
        return []
    stack = [str(root)]
    files: list[str] = []
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                            continue
                        if entry.is_file(follow_symlinks=False):
                            files.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    files.sort()
    return files


def _bundle_budget_settings(paths: dict[str, Path], bucket: str) -> dict[str, int]:
    return _bundle_budget_settings_from_policy(
        read_json(paths["retention_policy"], default_retention_policy()),
        bucket,
    )


def _bundle_budget_settings_from_policy(policy: dict[str, Any] | None, bucket: str) -> dict[str, int]:
    bundle_policy = dict((policy or {}).get("bundle_budgets") or {})
    soft_map = dict(bundle_policy.get("soft_max_bytes_by_bucket") or {})
    attachment_soft_map = dict(bundle_policy.get("attachment_soft_max_bytes_by_bucket") or {})
    hard_max_bytes = _coerce_positive_int(bundle_policy.get("hard_max_bytes"), LORA_BUNDLE_HARD_MAX_BYTES)
    soft_max_bytes = _coerce_positive_int(
        soft_map.get(bucket),
        int(LORA_BUNDLE_SOFT_MAX_BYTES_BY_BUCKET.get(bucket, hard_max_bytes)),
    )
    attachment_soft_max_bytes = max(
        0,
        int(attachment_soft_map.get(bucket, LORA_BUNDLE_ATTACHMENT_SOFT_MAX_BYTES_BY_BUCKET.get(bucket, 0)) or 0),
    )
    soft_max_bytes = min(soft_max_bytes, hard_max_bytes)
    attachment_soft_max_bytes = min(attachment_soft_max_bytes, hard_max_bytes)
    return {
        "hard_max_bytes": hard_max_bytes,
        "soft_max_bytes": soft_max_bytes,
        "attachment_soft_max_bytes": attachment_soft_max_bytes,
    }


def _bundle_record_count(payload: dict[str, Any]) -> int:
    counts = dict((payload or {}).get("counts") or {})
    try:
        return int(counts.get("unified_training_records", 0) or 0)
    except Exception:
        return len(list((payload or {}).get("records") or []))


def _iter_lora_archive_attachment_files(paths: dict[str, Path]) -> list[Path]:
    root = paths["trained_adapters"]
    return [Path(path) for path in _iter_tree_file_paths(root)]


def _attachment_total_bytes(paths: dict[str, Path]) -> int:
    total = 0
    for item in _iter_lora_archive_attachment_files(paths):
        try:
            total += int(item.stat().st_size)
        except OSError:
            continue
    return total


def _attachment_scan(paths: dict[str, Path]) -> tuple[list[Path], int]:
    files = _iter_lora_archive_attachment_files(paths)
    total = 0
    for item in files:
        try:
            total += int(item.stat().st_size)
        except OSError:
            continue
    return files, total


def _bucket_archive_path(paths: dict[str, Path], bucket: str | None = None) -> Path:
    key = _LORA_BUCKET_PATH_KEYS.get(str(bucket or LORA_BUCKET_HIGH), _LORA_BUCKET_PATH_KEYS[LORA_BUCKET_HIGH])
    return paths[key]


def _bucket_archive_paths(paths: dict[str, Path]) -> dict[str, Path]:
    return {bucket: _bucket_archive_path(paths, bucket) for bucket in LORA_ALL_BUCKETS}


def _cleanup_stale_unified_lora_temp_files(path: Path, *, stale_after_seconds: int | None = None) -> int:
    removed = 0
    parent = path.parent
    if not parent.exists():
        return removed
    stale_seconds = _UNIFIED_LORA_TMP_STALE_SECONDS if stale_after_seconds is None else max(0, int(stale_after_seconds))
    now = time.time()
    for item in parent.glob(f"{path.name}.*.tmp"):
        if not item.is_file():
            continue
        if stale_seconds > 0:
            try:
                age_seconds = max(0.0, now - float(item.stat().st_mtime))
            except OSError:
                continue
            if age_seconds < stale_seconds:
                continue
        try:
            item.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def _cleanup_all_lora_temp_files(paths: dict[str, Path]) -> int:
    removed = 0
    for path in _bucket_archive_paths(paths).values():
        removed += _cleanup_stale_unified_lora_temp_files(path, stale_after_seconds=0)
    legacy_zip = paths.get("legacy_unified_lora_zip")
    if legacy_zip is not None:
        removed += _cleanup_stale_unified_lora_temp_files(legacy_zip, stale_after_seconds=0)
    return removed


def _legacy_cache_conflict_path(conflicts_dir: Path, relative: Path) -> Path:
    target = conflicts_dir / relative
    if not target.exists():
        return target
    return target.with_name(f"{target.stem}.{uuid.uuid4().hex}{target.suffix}")


def _move_legacy_cache_file(legacy_path: Path, target_path: Path, conflicts_dir: Path) -> str:
    if not legacy_path.exists() or legacy_path == target_path:
        return ""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        conflict_path = _legacy_cache_conflict_path(conflicts_dir, Path(legacy_path.name))
        conflict_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            legacy_path.replace(conflict_path)
            return "conflicted"
        except OSError:
            return ""
    try:
        legacy_path.replace(target_path)
        return "moved"
    except OSError:
        try:
            shutil.copy2(legacy_path, target_path)
            legacy_path.unlink()
            return "copied"
        except OSError:
            return ""


def _move_legacy_cache_dir(legacy_dir: Path, target_dir: Path, conflicts_dir: Path) -> tuple[int, int]:
    if not legacy_dir.exists() or legacy_dir == target_dir:
        return 0, 0
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if not target_dir.exists():
        try:
            legacy_dir.replace(target_dir)
            moved_files = sum(1 for item in target_dir.rglob("*") if item.is_file())
            return moved_files, 0
        except OSError:
            target_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    conflicted = 0
    for item in sorted(legacy_dir.rglob("*")):
        if item.is_dir():
            continue
        try:
            relative = item.relative_to(legacy_dir)
        except ValueError:
            continue
        target = target_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            conflict_path = _legacy_cache_conflict_path(conflicts_dir / legacy_dir.name, relative)
            conflict_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                item.replace(conflict_path)
                conflicted += 1
            except OSError:
                continue
            continue
        try:
            item.replace(target)
            moved += 1
        except OSError:
            try:
                shutil.copy2(item, target)
                item.unlink()
                moved += 1
            except OSError:
                continue
    try:
        shutil.rmtree(legacy_dir)
    except OSError:
        pass
    return moved, conflicted


def _migrate_legacy_lora_cache_layout(
    paths: dict[str, Path],
    *,
    cleanup_temp_files: bool = False,
) -> dict[str, int]:
    root = paths["root"]
    cache_root = paths["cache_root"]
    cache_root.mkdir(parents=True, exist_ok=True)
    conflicts_dir = cache_root / "legacy_root_conflicts"
    migrated_files = 0
    conflicted_files = 0

    for key in dict.fromkeys(("manifest", *UNIFIED_LORA_BUNDLE_SOURCE_KEYS)):
        target = paths.get(key)
        if target is None:
            continue
        legacy = root / target.name
        result = _move_legacy_cache_file(legacy, target, conflicts_dir)
        if result in {"moved", "copied"}:
            migrated_files += 1
        elif result == "conflicted":
            conflicted_files += 1

    for dir_name in (paths["trained_adapters"].name, *_LEGACY_CACHE_DIR_NAMES):
        moved, conflicted = _move_legacy_cache_dir(root / dir_name, cache_root / dir_name, conflicts_dir)
        migrated_files += moved
        conflicted_files += conflicted

    for file_name in _ROOT_METADATA_FILE_NAMES:
        try:
            (root / file_name).unlink()
        except OSError:
            pass

    removed_tmp_files = _cleanup_all_lora_temp_files(paths) if cleanup_temp_files else 0
    return {
        "migrated_files": migrated_files,
        "conflicted_files": conflicted_files,
        "removed_tmp_files": removed_tmp_files,
    }


def _write_unified_lora_archive(
    path: Path,
    payload: dict[str, Any],
    paths: dict[str, Path],
    *,
    bucket: str = LORA_BUCKET_HIGH,
    include_attachments: bool = False,
    attachment_files: list[Path] | None = None,
    attachment_bytes: int | None = None,
) -> None:
    with _UNIFIED_LORA_ARCHIVE_WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        _cleanup_stale_unified_lora_temp_files(path)
        if include_attachments:
            attachment_files = list(attachment_files or _iter_lora_archive_attachment_files(paths))
            if attachment_bytes is None:
                attachment_bytes = 0
                for item in attachment_files:
                    try:
                        attachment_bytes += int(item.stat().st_size)
                    except OSError:
                        continue
        else:
            attachment_files = []
            attachment_bytes = 0
        metadata = {
            "schema": "ai_subtitle_studio.lora_unified_data_archive_manifest.v1",
            "updated_at": iso_now(),
            "payload_file": UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME,
            "payload_schema": str(payload.get("schema") or ""),
            "quality_bucket": bucket,
            "quality_bucket_label": LORA_BUCKET_LABELS.get(bucket, bucket),
            "record_count": _bundle_record_count(payload),
            "attachment_files": len(attachment_files),
            "attachment_bytes": attachment_bytes,
            "compression": LORA_ARCHIVE_COMPRESSION_NAME,
            "compression_level": LORA_ARCHIVE_COMPRESSION_LEVEL,
        }
        fd, tmp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
        )
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            with zipfile.ZipFile(
                tmp_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=LORA_ARCHIVE_COMPRESSION_LEVEL,
            ) as archive:
                metadata_bytes = _json_bytes(metadata, indent=2)
                payload_bytes = _json_bytes(payload, indent=2)
                archive.writestr(UNIFIED_LORA_ARCHIVE_MANIFEST_NAME, metadata_bytes)
                archive.writestr(UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME, payload_bytes)
                for item in attachment_files:
                    archive.write(item, f"attachments/{item.relative_to(paths['root']).as_posix()}")
            try:
                tmp_path.replace(path)
            except FileNotFoundError:
                if not tmp_path.exists():
                    fd, retry_name = tempfile.mkstemp(
                        dir=path.parent,
                        prefix=f"{path.name}.",
                        suffix=".tmp",
                    )
                    os.close(fd)
                    retry_path = Path(retry_name)
                    with zipfile.ZipFile(
                        retry_path,
                        "w",
                        compression=zipfile.ZIP_DEFLATED,
                        compresslevel=LORA_ARCHIVE_COMPRESSION_LEVEL,
                    ) as archive:
                        archive.writestr(UNIFIED_LORA_ARCHIVE_MANIFEST_NAME, metadata_bytes)
                        archive.writestr(UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME, payload_bytes)
                        for item in attachment_files:
                            archive.write(item, f"attachments/{item.relative_to(paths['root']).as_posix()}")
                    retry_path.replace(path)
                    tmp_path = retry_path
                else:
                    raise
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass


def _read_unified_lora_payload(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as archive:
                names = set(archive.namelist())
                payload_name = UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME
                if payload_name not in names:
                    payload_name = next((name for name in names if name.endswith(".json")), "")
                if not payload_name:
                    return default
                return json.loads(archive.read(payload_name).decode("utf-8"))
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _restore_unified_lora_archive_attachments(path: Path, paths: dict[str, Path]) -> int:
    if paths["trained_adapters"].exists():
        shutil.rmtree(paths["trained_adapters"])
    paths["trained_adapters"].mkdir(parents=True, exist_ok=True)
    if not path.exists() or not zipfile.is_zipfile(path):
        return 0

    restored = 0
    root = paths["root"].resolve()
    try:
        with zipfile.ZipFile(path, "r") as archive:
            for name in archive.namelist():
                if not name.startswith("attachments/") or name.endswith("/"):
                    continue
                relative = Path(name[len("attachments/") :])
                if relative.is_absolute() or ".." in relative.parts:
                    continue
                if relative.parts and relative.parts[0] == paths["trained_adapters"].name:
                    target = paths["cache_root"] / relative
                else:
                    target = paths["root"] / relative
                try:
                    resolved_target = target.resolve()
                except OSError:
                    continue
                if root not in resolved_target.parents and resolved_target != root:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
                restored += 1
    except Exception:
        return restored
    return restored


def _existing_unified_lora_data_path(paths: dict[str, Path]) -> Path:
    target = paths["unified_lora_data"]
    if target.exists():
        return target
    legacy_zip = paths.get("legacy_unified_lora_zip")
    if legacy_zip is not None and legacy_zip.exists():
        return legacy_zip
    legacy = paths.get("legacy_unified_lora_data")
    if legacy is not None and legacy.exists():
        return legacy
    return target


def _remove_legacy_unified_lora_json(paths: dict[str, Path]) -> None:
    for key in ("legacy_unified_lora_data", "legacy_unified_lora_zip"):
        legacy = paths.get(key)
        if legacy is None or not legacy.exists():
            continue
        try:
            legacy.unlink()
        except OSError:
            pass


def _merge_unified_lora_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    valid_payloads = [
        dict(payload)
        for payload in list(payloads or [])
        if isinstance(payload, dict) and str(payload.get("schema") or "") == "ai_subtitle_studio.lora_unified_data_bundle.v1"
    ]
    if not valid_payloads:
        return {}
    if len(valid_payloads) == 1:
        return valid_payloads[0]

    merged_sections: dict[str, Any] = {}
    for key in BUNDLE_JSONL_SECTION_KEYS:
        rows: list[dict[str, Any]] = []
        for payload in valid_payloads:
            section_rows = ((payload.get("sections") or {}).get(key) or [])
            rows.extend(dict(row) for row in list(section_rows) if isinstance(row, dict))
        merged_sections[key] = ranked_lora_rows(key, rows)

    for key in BUNDLE_JSON_SECTION_KEYS:
        if key in {"learned_split_rules", "learned_line_break_rules"}:
            base = _default_json_section(key)
            items: list[dict[str, Any]] = []
            for payload in valid_payloads:
                section = dict((payload.get("sections") or {}).get(key) or {})
                items.extend(dict(item) for item in list(section.get("items") or []) if isinstance(item, dict))
            base["items"] = items
            merged_sections[key] = base
            continue
        for payload in valid_payloads:
            section = (payload.get("sections") or {}).get(key)
            if isinstance(section, dict) and section:
                merged_sections[key] = dict(section)
                break
        else:
            merged_sections[key] = _default_json_section(key)

    records = [
        {"kind": kind, "record": row}
        for kind in (
            "truth_table",
            "excluded_parentheticals",
            "setting_trials",
            "prompt_trials",
            "voice_lora_bridge",
            "stt1_whisper_adapter_dataset",
            "text_lora_dataset",
            "text_lora_corpus",
            "audio_preset_lora",
            "multimodal_lora_context",
            "deep_policy_events",
        )
        for row in merged_sections.get(kind, [])
    ]
    counts = _bundle_counts_from_rows(
        truth_rows=merged_sections["truth_table"],
        excluded_rows=merged_sections["excluded_parentheticals"],
        setting_trials=merged_sections["setting_trials"],
        prompt_trials=merged_sections["prompt_trials"],
        retention_history=merged_sections["retention_history"],
        voice_bridge_rows=merged_sections["voice_lora_bridge"],
        stt1_whisper_adapter_dataset_rows=merged_sections["stt1_whisper_adapter_dataset"],
        text_lora_dataset_rows=merged_sections["text_lora_dataset"],
        text_lora_corpus_rows=merged_sections["text_lora_corpus"],
        audio_preset_rows=merged_sections["audio_preset_lora"],
        multimodal_context_rows=merged_sections["multimodal_lora_context"],
        deep_policy_event_rows=merged_sections["deep_policy_events"],
        voice_training_plan=dict(merged_sections.get("voice_lora_training_plan") or {}),
        stt1_whisper_adapter_plan=dict(merged_sections.get("stt1_whisper_adapter_training_plan") or {}),
        stt1_whisper_runtime_manifest=dict(merged_sections.get("stt1_whisper_adapter_runtime_manifest") or {}),
        retrieval_index={},
        subtitle_pattern_index={},
    )
    first = valid_payloads[0]
    return {
        "schema": "ai_subtitle_studio.lora_unified_data_bundle.v1",
        "updated_at": iso_now(),
        "storage_mode": "quality_bucketed_zip_bundle",
        "bundle_role": "merged_user_managed_lora_learning_files",
        "archive_format": str(first.get("archive_format") or "zip"),
        "archive_compression": LORA_ARCHIVE_COMPRESSION_NAME,
        "archive_compression_level": LORA_ARCHIVE_COMPRESSION_LEVEL,
        "archive_payload_file": UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME,
        "store_dir": str(first.get("store_dir") or ""),
        "managed_file": str(first.get("managed_file") or ""),
        "quality_bucket": "merged",
        "quality_bucket_label": "상/중/하/삭제예정 통합",
        "quality_buckets": {
            str(payload.get("quality_bucket") or ""): dict(payload.get("counts") or {})
            for payload in valid_payloads
            if payload.get("quality_bucket")
        },
        "internal_cache_files": dict(first.get("internal_cache_files") or {}),
        "counts": counts,
        "sections": merged_sections,
        "records": records,
        "notes": [
            "This payload was merged from quality-bucket LoRA ZIP files.",
            "Runtime retrieval resolves conflicts by score index before applying settings.",
        ],
    }


def _explicit_bundle_source_paths(bundle_path: str | Path) -> list[Path]:
    selected = Path(bundle_path)
    bucket_names = set(LORA_BUCKET_FILENAMES.values())
    if selected.name not in bucket_names:
        return [selected]
    siblings = [selected.parent / LORA_BUCKET_FILENAMES[bucket] for bucket in LORA_ALL_BUCKETS]
    existing = [path for path in siblings if path.exists()]
    return existing or [selected]


def load_unified_lora_data_bundle(bundle_path: str | Path | None = None, store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    if bundle_path:
        payloads = [_read_unified_lora_payload(path, {}) for path in _explicit_bundle_source_paths(bundle_path)]
        return _merge_unified_lora_payloads([payload for payload in payloads if isinstance(payload, dict)])
    bucket_paths = [path for path in _bucket_archive_paths(paths).values() if path.exists()]
    if bucket_paths:
        payloads = [_read_unified_lora_payload(path, {}) for path in bucket_paths]
        return _merge_unified_lora_payloads([payload for payload in payloads if isinstance(payload, dict)])
    source_path = _existing_unified_lora_data_path(paths)
    payload = _read_unified_lora_payload(source_path, {})
    return payload if isinstance(payload, dict) else {}


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


def _bundle_counts_from_rows(
    *,
    truth_rows: list[dict[str, Any]],
    excluded_rows: list[dict[str, Any]],
    setting_trials: list[dict[str, Any]],
    prompt_trials: list[dict[str, Any]],
    voice_bridge_rows: list[dict[str, Any]],
    stt1_whisper_adapter_dataset_rows: list[dict[str, Any]],
    text_lora_dataset_rows: list[dict[str, Any]],
    text_lora_corpus_rows: list[dict[str, Any]],
    audio_preset_rows: list[dict[str, Any]],
    multimodal_context_rows: list[dict[str, Any]],
    deep_policy_event_rows: list[dict[str, Any]] | None = None,
    retention_history: list[dict[str, Any]] | None = None,
    voice_training_plan: dict[str, Any] | None = None,
    stt1_whisper_adapter_plan: dict[str, Any] | None = None,
    stt1_whisper_runtime_manifest: dict[str, Any] | None = None,
    retrieval_index: dict[str, Any] | None = None,
    subtitle_pattern_index: dict[str, Any] | None = None,
) -> dict[str, int]:
    voice_training_plan = dict(voice_training_plan or {})
    stt1_whisper_adapter_plan = dict(stt1_whisper_adapter_plan or {})
    stt1_whisper_runtime_manifest = dict(stt1_whisper_runtime_manifest or {})
    retrieval_index = dict(retrieval_index or {})
    subtitle_pattern_index = dict(subtitle_pattern_index or {})
    return {
        "truth_table_rows": len(truth_rows),
        "excluded_parenthetical_rows": len(excluded_rows),
        "setting_trial_rows": len(setting_trials),
        "prompt_trial_rows": len(prompt_trials),
        "retention_history_rows": len(retention_history or []),
        "voice_lora_bridge_rows": len(voice_bridge_rows),
        "voice_lora_training_items": len(list(voice_training_plan.get("items") or [])),
        "voice_lora_stored_audio_items": count_ready_voice_audio_items(voice_training_plan),
        "stt1_whisper_adapter_dataset_rows": len(stt1_whisper_adapter_dataset_rows),
        "stt1_whisper_adapter_training_items": len(list(stt1_whisper_adapter_plan.get("items") or [])),
        "stt1_whisper_adapter_audio_items": sum(
            1 for item in list(stt1_whisper_adapter_plan.get("items") or []) if bool((item or {}).get("audio_ready"))
        ),
        "stt1_whisper_adapter_runtime_ready": 1 if bool(stt1_whisper_runtime_manifest.get("runtime_ready")) else 0,
        "text_lora_dataset_rows": len(text_lora_dataset_rows),
        "text_lora_corpus_rows": len(text_lora_corpus_rows),
        "audio_preset_lora_rows": len(audio_preset_rows),
        "multimodal_lora_context_rows": len(multimodal_context_rows),
        "deep_policy_event_rows": len(deep_policy_event_rows or []),
        "lora_retrieval_index_docs": int(retrieval_index.get("doc_count", 0) or 0),
        "subtitle_pattern_index_patterns": int(subtitle_pattern_index.get("pattern_count", 0) or 0),
        "unified_training_records": (
            len(truth_rows)
            + len(excluded_rows)
            + len(setting_trials)
            + len(prompt_trials)
            + len(voice_bridge_rows)
            + len(stt1_whisper_adapter_dataset_rows)
            + len(text_lora_dataset_rows)
            + len(text_lora_corpus_rows)
            + len(audio_preset_rows)
            + len(multimodal_context_rows)
            + len(deep_policy_event_rows or [])
        ),
    }


def _bundle_counts_from_cache(paths: dict[str, Path]) -> dict[str, int]:
    return _bundle_counts_from_rows(
        truth_rows=read_jsonl(paths["truth_table"]),
        excluded_rows=read_jsonl(paths["excluded_parentheticals"]),
        setting_trials=read_jsonl(paths["setting_trials"]),
        prompt_trials=read_jsonl(paths["prompt_trials"]),
        retention_history=read_jsonl(paths["retention_history"]),
        voice_bridge_rows=read_jsonl(paths["voice_lora_bridge"]),
        stt1_whisper_adapter_dataset_rows=read_jsonl(paths["stt1_whisper_adapter_dataset"]),
        text_lora_dataset_rows=read_jsonl(paths["text_lora_dataset"]),
        text_lora_corpus_rows=read_jsonl(paths["text_lora_corpus"]),
        audio_preset_rows=read_jsonl(paths["audio_preset_lora"]),
        multimodal_context_rows=read_jsonl(paths["multimodal_lora_context"]),
        deep_policy_event_rows=read_jsonl(paths["deep_policy_events"]),
        voice_training_plan=read_json(paths["voice_lora_training_plan"], {}),
        stt1_whisper_adapter_plan=read_json(paths["stt1_whisper_adapter_training_plan"], {}),
        stt1_whisper_runtime_manifest=read_json(paths["stt1_whisper_adapter_runtime_manifest"], {}),
        retrieval_index=read_json(paths["lora_retrieval_index"], {}),
        subtitle_pattern_index=read_json(paths["subtitle_pattern_index"], {}),
    )


def _load_unified_lora_bundle_sources(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "jsonl_sections": {
            key: read_jsonl(paths[key])
            for key in BUNDLE_JSONL_SECTION_KEYS
        },
        "json_sections": {
            "training_queue": read_json(paths["training_queue"], default_queue()),
            "learned_split_rules": read_json(
                paths["learned_split_rules"],
                default_learned_rules("ai_subtitle_studio.learned_split_rules.v1"),
            ),
            "learned_line_break_rules": read_json(
                paths["learned_line_break_rules"],
                default_learned_rules("ai_subtitle_studio.learned_line_break_rules.v1"),
            ),
            "best_settings": read_json(paths["best_settings"], default_best_settings()),
            "retention_policy": read_json(paths["retention_policy"], default_retention_policy()),
            "llm_review_request": read_json(paths["llm_review_request"], {}),
            "llm_review_result": read_json(paths["llm_review_result"], {}),
            "voice_lora_profile_manifest": read_json(paths["voice_lora_profile_manifest"], {}),
            "voice_lora_training_plan": read_json(paths["voice_lora_training_plan"], {}),
            "voice_lora_dataset_manifest": read_json(paths["voice_lora_dataset_manifest"], {}),
            "stt1_whisper_adapter_dataset_manifest": read_json(paths["stt1_whisper_adapter_dataset_manifest"], {}),
            "stt1_whisper_adapter_training_plan": read_json(paths["stt1_whisper_adapter_training_plan"], {}),
            "stt1_whisper_adapter_runtime_manifest": read_json(paths["stt1_whisper_adapter_runtime_manifest"], {}),
            "text_lora_manifest": read_json(paths["text_lora_manifest"], {}),
            "text_lora_corpus_manifest": read_json(paths["text_lora_corpus_manifest"], {}),
            "text_lora_training_plan": read_json(paths["text_lora_training_plan"], {}),
            "lora_retrieval_index": read_json(paths["lora_retrieval_index"], {}),
            "subtitle_pattern_index": read_json(paths["subtitle_pattern_index"], {}),
        },
    }


def _bundle_counts_from_sources(sources: dict[str, Any]) -> dict[str, int]:
    jsonl_sections = dict(sources.get("jsonl_sections") or {})
    json_sections = dict(sources.get("json_sections") or {})
    return _bundle_counts_from_rows(
        truth_rows=list(jsonl_sections.get("truth_table") or []),
        excluded_rows=list(jsonl_sections.get("excluded_parentheticals") or []),
        setting_trials=list(jsonl_sections.get("setting_trials") or []),
        prompt_trials=list(jsonl_sections.get("prompt_trials") or []),
        retention_history=list(jsonl_sections.get("retention_history") or []),
        voice_bridge_rows=list(jsonl_sections.get("voice_lora_bridge") or []),
        stt1_whisper_adapter_dataset_rows=list(jsonl_sections.get("stt1_whisper_adapter_dataset") or []),
        text_lora_dataset_rows=list(jsonl_sections.get("text_lora_dataset") or []),
        text_lora_corpus_rows=list(jsonl_sections.get("text_lora_corpus") or []),
        audio_preset_rows=list(jsonl_sections.get("audio_preset_lora") or []),
        multimodal_context_rows=list(jsonl_sections.get("multimodal_lora_context") or []),
        deep_policy_event_rows=list(jsonl_sections.get("deep_policy_events") or []),
        voice_training_plan=dict(json_sections.get("voice_lora_training_plan") or {}),
        stt1_whisper_adapter_plan=dict(json_sections.get("stt1_whisper_adapter_training_plan") or {}),
        stt1_whisper_runtime_manifest=dict(json_sections.get("stt1_whisper_adapter_runtime_manifest") or {}),
        retrieval_index=dict(json_sections.get("lora_retrieval_index") or {}),
        subtitle_pattern_index=dict(json_sections.get("subtitle_pattern_index") or {}),
    )


def _filter_rows_for_bucket(kind: str, rows: list[dict[str, Any]], bucket: str | None) -> list[dict[str, Any]]:
    if not bucket:
        return ranked_lora_rows(kind, rows)
    return ranked_lora_rows(kind, rows, bucket=bucket)


def _filter_json_section_for_bucket(key: str, payload: dict[str, Any], bucket: str | None) -> dict[str, Any]:
    if not bucket:
        return dict(payload or {})
    if key in {"learned_split_rules", "learned_line_break_rules"}:
        out = dict(payload or _default_json_section(key))
        out["items"] = _filter_rows_for_bucket(key, list(out.get("items") or []), bucket)
        return out
    if key == "best_settings" and bucket != LORA_BUCKET_HIGH:
        return default_best_settings()
    if key == "lora_retrieval_index":
        return {}
    if key == "subtitle_pattern_index" and bucket != LORA_BUCKET_HIGH:
        return {}
    return dict(payload or {})


def _records_from_jsonl_sections(jsonl_sections: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {"kind": kind, "record": row}
        for kind in (
            "truth_table",
            "excluded_parentheticals",
            "setting_trials",
            "prompt_trials",
            "voice_lora_bridge",
            "stt1_whisper_adapter_dataset",
            "text_lora_dataset",
            "text_lora_corpus",
            "audio_preset_lora",
            "multimodal_lora_context",
            "deep_policy_events",
        )
        for row in list((jsonl_sections or {}).get(kind) or [])
        if isinstance(row, dict)
    ]


def _apply_bundle_size_budget(
    payload: dict[str, Any],
    paths: dict[str, Path],
    *,
    bucket: str,
    retention_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(payload or {})
    sections = dict(out.get("sections") or {})
    jsonl_sections = {
        key: [dict(row) for row in list(sections.get(key) or []) if isinstance(row, dict)]
        for key in BUNDLE_JSONL_SECTION_KEYS
    }
    budget = _bundle_budget_settings_from_policy(retention_policy, bucket)
    skeleton = dict(out)
    skeleton_sections = dict(sections)
    for key in BUNDLE_JSONL_SECTION_KEYS:
        skeleton_sections[key] = []
    skeleton["sections"] = skeleton_sections
    skeleton["records"] = []
    fixed_bytes = _serialized_json_size_bytes(skeleton)
    current_estimated_bytes = _serialized_json_size_bytes(out)
    kept_counts = {key: len(rows) for key, rows in jsonl_sections.items()}
    trimmed_records = 0

    if current_estimated_bytes > budget["soft_max_bytes"]:
        available_bytes = max(0, budget["soft_max_bytes"] - fixed_bytes)
        candidates: list[tuple[tuple[int, float, float, float, int], str, dict[str, Any], int]] = []
        for kind, rows in jsonl_sections.items():
            for index, row in enumerate(rows):
                row_size = _serialized_json_size_bytes(row)
                record_size = _serialized_json_size_bytes({"kind": kind, "record": row})
                candidates.append((lora_row_sort_key(kind, row, index), kind, row, row_size + record_size + 16))
        candidates.sort(key=lambda item: item[0])
        kept_by_kind: dict[str, list[dict[str, Any]]] = {key: [] for key in BUNDLE_JSONL_SECTION_KEYS}
        used_bytes = 0
        for _sort_key, kind, row, row_budget_bytes in candidates:
            if kept_by_kind and not any(kept_by_kind.values()):
                kept_by_kind[kind].append(dict(row))
                used_bytes += row_budget_bytes
                continue
            if used_bytes + row_budget_bytes > available_bytes:
                continue
            kept_by_kind[kind].append(dict(row))
            used_bytes += row_budget_bytes
        for kind in BUNDLE_JSONL_SECTION_KEYS:
            jsonl_sections[kind] = ranked_lora_rows(kind, kept_by_kind.get(kind, []))
        kept_counts = {key: len(rows) for key, rows in jsonl_sections.items()}
        trimmed_records = len(candidates) - sum(kept_counts.values())
        out["records"] = _records_from_jsonl_sections(jsonl_sections)
        sections.update(jsonl_sections)
        out["sections"] = sections
        out["counts"] = _bundle_counts_from_rows(
            truth_rows=jsonl_sections["truth_table"],
            excluded_rows=jsonl_sections["excluded_parentheticals"],
            setting_trials=jsonl_sections["setting_trials"],
            prompt_trials=jsonl_sections["prompt_trials"],
            retention_history=jsonl_sections["retention_history"],
            voice_bridge_rows=jsonl_sections["voice_lora_bridge"],
            stt1_whisper_adapter_dataset_rows=jsonl_sections["stt1_whisper_adapter_dataset"],
            text_lora_dataset_rows=jsonl_sections["text_lora_dataset"],
            text_lora_corpus_rows=jsonl_sections["text_lora_corpus"],
            audio_preset_rows=jsonl_sections["audio_preset_lora"],
            multimodal_context_rows=jsonl_sections["multimodal_lora_context"],
            deep_policy_event_rows=jsonl_sections["deep_policy_events"],
            voice_training_plan=dict(sections.get("voice_lora_training_plan") or {}),
            stt1_whisper_adapter_plan=dict(sections.get("stt1_whisper_adapter_training_plan") or {}),
            stt1_whisper_runtime_manifest=dict(sections.get("stt1_whisper_adapter_runtime_manifest") or {}),
            retrieval_index=dict(sections.get("lora_retrieval_index") or {}),
            subtitle_pattern_index=dict(sections.get("subtitle_pattern_index") or {}),
        )
        if trimmed_records > 0:
            notes = list(out.get("notes") or [])
            notes.append(
                f"Strict LoRA bundle budget trimmed {trimmed_records} lower-ranked rows from the {bucket} archive to keep runtime reads fast."
            )
            out["notes"] = notes

    out["bundle_budget"] = {
        **budget,
        "estimated_payload_bytes": _serialized_json_size_bytes(out),
        "fixed_payload_bytes": fixed_bytes,
        "trimmed_records": int(trimmed_records),
        "kept_row_counts": kept_counts,
    }
    return out


def _build_unified_lora_data_bundle(
    paths: dict[str, Path],
    *,
    bucket: str | None = None,
    sources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    loaded_sources = sources if isinstance(sources, dict) else _load_unified_lora_bundle_sources(paths)
    raw_jsonl_sections = dict(loaded_sources.get("jsonl_sections") or {})
    raw_json_sections = dict(loaded_sources.get("json_sections") or {})
    jsonl_sections = {
        key: _filter_rows_for_bucket(key, list(raw_jsonl_sections.get(key) or []), bucket)
        for key in BUNDLE_JSONL_SECTION_KEYS
    }
    voice_training_plan = dict(raw_json_sections.get("voice_lora_training_plan") or {})
    stt1_whisper_adapter_plan = dict(raw_json_sections.get("stt1_whisper_adapter_training_plan") or {})
    stt1_whisper_runtime_manifest = dict(raw_json_sections.get("stt1_whisper_adapter_runtime_manifest") or {})
    retrieval_index = {}
    subtitle_pattern_index = (
        dict(raw_json_sections.get("subtitle_pattern_index") or {})
        if bucket == LORA_BUCKET_HIGH
        else {}
    )
    records = _records_from_jsonl_sections(jsonl_sections)
    sections = {
        **jsonl_sections,
        "training_queue": dict(raw_json_sections.get("training_queue") or default_queue()),
        "learned_split_rules": _filter_json_section_for_bucket(
            "learned_split_rules",
            dict(
                raw_json_sections.get("learned_split_rules")
                or default_learned_rules("ai_subtitle_studio.learned_split_rules.v1")
            ),
            bucket,
        ),
        "learned_line_break_rules": _filter_json_section_for_bucket(
            "learned_line_break_rules",
            dict(
                raw_json_sections.get("learned_line_break_rules")
                or default_learned_rules("ai_subtitle_studio.learned_line_break_rules.v1")
            ),
            bucket,
        ),
        "best_settings": _filter_json_section_for_bucket(
            "best_settings",
            dict(raw_json_sections.get("best_settings") or default_best_settings()),
            bucket,
        ),
        "retention_policy": dict(raw_json_sections.get("retention_policy") or default_retention_policy()),
        "llm_review_request": dict(raw_json_sections.get("llm_review_request") or {}),
        "llm_review_result": dict(raw_json_sections.get("llm_review_result") or {}),
        "voice_lora_profile_manifest": dict(raw_json_sections.get("voice_lora_profile_manifest") or {}),
        "voice_lora_training_plan": voice_training_plan,
        "voice_lora_dataset_manifest": dict(raw_json_sections.get("voice_lora_dataset_manifest") or {}),
        "stt1_whisper_adapter_dataset_manifest": dict(
            raw_json_sections.get("stt1_whisper_adapter_dataset_manifest") or {}
        ),
        "stt1_whisper_adapter_training_plan": stt1_whisper_adapter_plan,
        "stt1_whisper_adapter_runtime_manifest": stt1_whisper_runtime_manifest,
        "text_lora_manifest": dict(raw_json_sections.get("text_lora_manifest") or {}),
        "text_lora_corpus_manifest": dict(raw_json_sections.get("text_lora_corpus_manifest") or {}),
        "text_lora_training_plan": dict(raw_json_sections.get("text_lora_training_plan") or {}),
        "lora_retrieval_index": retrieval_index,
        "subtitle_pattern_index": subtitle_pattern_index,
    }
    managed_path = _bucket_archive_path(paths, bucket or LORA_BUCKET_HIGH)
    bucket_label = LORA_BUCKET_LABELS.get(str(bucket or ""), "전체")
    payload = {
        "schema": "ai_subtitle_studio.lora_unified_data_bundle.v1",
        "updated_at": iso_now(),
        "storage_mode": "quality_bucketed_zip_bundle",
        "bundle_role": "quality_bucket_user_managed_lora_learning_file",
        "archive_format": "zip",
        "archive_compression": LORA_ARCHIVE_COMPRESSION_NAME,
        "archive_compression_level": LORA_ARCHIVE_COMPRESSION_LEVEL,
        "archive_payload_file": UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME,
        "store_dir": str(paths["root"]),
        "managed_file": str(managed_path),
        "quality_bucket": str(bucket or "all"),
        "quality_bucket_label": bucket_label,
        "internal_cache_files": {key: str(paths[key]) for key in UNIFIED_LORA_BUNDLE_SOURCE_KEYS if key in paths},
        "counts": _bundle_counts_from_rows(
            truth_rows=jsonl_sections["truth_table"],
            excluded_rows=jsonl_sections["excluded_parentheticals"],
            setting_trials=jsonl_sections["setting_trials"],
            prompt_trials=jsonl_sections["prompt_trials"],
            retention_history=jsonl_sections["retention_history"],
            voice_bridge_rows=jsonl_sections["voice_lora_bridge"],
            stt1_whisper_adapter_dataset_rows=jsonl_sections["stt1_whisper_adapter_dataset"],
            text_lora_dataset_rows=jsonl_sections["text_lora_dataset"],
            text_lora_corpus_rows=jsonl_sections["text_lora_corpus"],
            audio_preset_rows=jsonl_sections["audio_preset_lora"],
            multimodal_context_rows=jsonl_sections["multimodal_lora_context"],
            deep_policy_event_rows=jsonl_sections["deep_policy_events"],
            voice_training_plan=voice_training_plan,
            stt1_whisper_adapter_plan=stt1_whisper_adapter_plan,
            stt1_whisper_runtime_manifest=stt1_whisper_runtime_manifest,
            retrieval_index=retrieval_index,
            subtitle_pattern_index=subtitle_pattern_index,
        ),
        "sections": sections,
        "records": records,
        "notes": [
            "This payload is stored inside one of four quality-bucket LoRA personalization learning ZIP files.",
            "Buckets are recomputed from the current score index, so pending-delete rows can be promoted after their score improves.",
            "The app may rebuild internal cache shard files from this file for fast append, pruning, and UI inspection.",
            "Use sections for exact restore/review and records for flat training-data scans.",
        ],
    }
    if bucket:
        return _apply_bundle_size_budget(
            payload,
            paths,
            bucket=bucket,
            retention_policy=dict(raw_json_sections.get("retention_policy") or default_retention_policy()),
        )
    return payload


def refresh_unified_lora_data_bundle(
    store_dir: str | Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    with _UNIFIED_LORA_ARCHIVE_WRITE_LOCK:
        paths = store_paths(store_dir)
        migration = _migrate_legacy_lora_cache_layout(paths, cleanup_temp_files=True)
        targets = _bucket_archive_paths(paths)
        existing_targets = [path for path in targets.values() if path.exists()]
        needs_refresh = bool(force or len(existing_targets) != len(targets))
        if not needs_refresh:
            try:
                oldest_target_mtime = min(float(path.stat().st_mtime) for path in targets.values())
                needs_refresh = _source_max_mtime(paths) > oldest_target_mtime
            except OSError:
                needs_refresh = True
        counts: dict[str, Any] = {}
        bucket_files: dict[str, Any] = {}
        if needs_refresh:
            bundle_sources = _load_unified_lora_bundle_sources(paths)
            attachment_files: list[Path] = []
            attachment_total_bytes = 0
            if paths["trained_adapters"].exists():
                attachment_files, attachment_total_bytes = _attachment_scan(paths)
            for bucket, target in targets.items():
                payload = _build_unified_lora_data_bundle(paths, bucket=bucket, sources=bundle_sources)
                bundle_budget = dict(payload.get("bundle_budget") or {})
                estimated_payload_bytes = int(bundle_budget.get("estimated_payload_bytes", 0) or 0)
                current_attachment_total_bytes = attachment_total_bytes if bucket == LORA_BUCKET_HIGH else 0
                include_attachments = (
                    bucket == LORA_BUCKET_HIGH
                    and current_attachment_total_bytes > 0
                    and current_attachment_total_bytes <= int(bundle_budget.get("attachment_soft_max_bytes", 0) or 0)
                    and estimated_payload_bytes + current_attachment_total_bytes <= int(bundle_budget.get("soft_max_bytes", 0) or 0)
                    and estimated_payload_bytes + current_attachment_total_bytes <= int(bundle_budget.get("hard_max_bytes", 0) or 0)
                )
                if bucket == LORA_BUCKET_HIGH and current_attachment_total_bytes > 0 and not include_attachments:
                    notes = list(payload.get("notes") or [])
                    notes.append(
                        "Large trained-adapter attachments were excluded from the high bundle so runtime archive reads stay lightweight."
                    )
                    payload["notes"] = notes
                    bundle_budget["estimated_payload_bytes"] = _serialized_json_size_bytes(payload)
                    payload["bundle_budget"] = bundle_budget
                bucket_counts = dict(payload.get("counts") or {})
                bucket_files[bucket] = {
                    **bundle_file_info(target),
                    "quality_bucket": bucket,
                    "quality_bucket_label": LORA_BUCKET_LABELS.get(bucket, bucket),
                    "record_count": int(bucket_counts.get("unified_training_records", 0) or 0),
                    "counts": bucket_counts,
                    "bundle_budget": bundle_budget,
                    "include_attachments": include_attachments,
                    "attachment_candidate_bytes": current_attachment_total_bytes,
                }
                _write_unified_lora_archive(
                    target,
                    payload,
                    paths,
                    bucket=bucket,
                    include_attachments=include_attachments,
                    attachment_files=attachment_files if bucket == LORA_BUCKET_HIGH else None,
                    attachment_bytes=current_attachment_total_bytes if bucket == LORA_BUCKET_HIGH else None,
                )
                bucket_files[bucket].update(bundle_file_info(target))
            counts = _bundle_counts_from_sources(bundle_sources)
            _remove_legacy_unified_lora_json(paths)
        if not bucket_files:
            bucket_files = {
                bucket: {
                    **bundle_file_info(path),
                    "quality_bucket": bucket,
                    "quality_bucket_label": LORA_BUCKET_LABELS.get(bucket, bucket),
                    "record_count": _bundle_record_count(_read_unified_lora_payload(path, {})) if path.exists() else 0,
                }
                for bucket, path in targets.items()
            }
        if not counts:
            counts = _bundle_counts_from_cache(paths)
        target = paths["unified_lora_data"]
        return {
            **bundle_file_info(target),
            "refreshed": needs_refresh,
            "removed_tmp_files": int(migration.get("removed_tmp_files", 0) or 0),
            "counts": counts,
            "record_count": int(counts.get("unified_training_records", 0) or 0),
            "bucket_files": bucket_files,
        }


def _cache_record_count(paths: dict[str, Path]) -> int:
    return sum(len(read_jsonl(paths[key])) for key in BUNDLE_JSONL_SECTION_KEYS if paths.get(key) is not None and paths[key].exists())


def _should_restore_from_existing_bundle(paths: dict[str, Path]) -> bool:
    bundle_path = _existing_unified_lora_data_path(paths)
    if not bundle_path.exists():
        return False
    if _cache_record_count(paths) > 0:
        return False
    payload = _read_unified_lora_payload(bundle_path, {})
    if not isinstance(payload, dict) or str(payload.get("schema") or "") != "ai_subtitle_studio.lora_unified_data_bundle.v1":
        return False
    return _bundle_record_count(payload) > 0


def _default_json_section(key: str) -> dict[str, Any]:
    if key == "training_queue":
        return default_queue()
    if key == "learned_split_rules":
        return default_learned_rules("ai_subtitle_studio.learned_split_rules.v1")
    if key == "learned_line_break_rules":
        return default_learned_rules("ai_subtitle_studio.learned_line_break_rules.v1")
    if key == "best_settings":
        return default_best_settings()
    if key == "dedupe_index":
        return default_dedupe_index()
    if key == "retention_policy":
        return default_retention_policy()
    return {}


def _rebuild_dedupe_index_from_cache(paths: dict[str, Path]) -> dict[str, Any]:
    dedupe_entries: dict[str, dict[str, Any]] = {kind: {} for kind in JSONL_KINDS}
    for kind in JSONL_KINDS:
        rows = read_jsonl(paths[kind])
        unique_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            signature = row_signature(row)
            if signature in seen:
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
    payload = {
        "schema": "ai_subtitle_studio.personalization_dedupe_index.v1",
        "updated_at": iso_now(),
        "entries": dedupe_entries,
    }
    write_json(paths["dedupe_index"], payload)
    return payload


def restore_lora_personalization_store_from_bundle(
    bundle_path: str | Path | None = None,
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["cache_root"].mkdir(parents=True, exist_ok=True)
    if bundle_path:
        source_paths = _explicit_bundle_source_paths(bundle_path)
    else:
        bucket_paths = [path for path in _bucket_archive_paths(paths).values() if path.exists()]
        source_paths = bucket_paths if bucket_paths else [_existing_unified_lora_data_path(paths)]
    source_path = source_paths[0]
    payloads = [_read_unified_lora_payload(path, {}) for path in source_paths]
    payload = _merge_unified_lora_payloads([item for item in payloads if isinstance(item, dict)])
    if not isinstance(payload, dict) or str(payload.get("schema") or "") != "ai_subtitle_studio.lora_unified_data_bundle.v1":
        raise ValueError(f"Unsupported LoRA learning bundle: {source_path}")

    restored_attachment_files = _restore_unified_lora_archive_attachments(source_path, paths)
    sections = dict(payload.get("sections") or {})

    restored_jsonl_counts: dict[str, int] = {}
    for key in BUNDLE_JSONL_SECTION_KEYS:
        section_rows = sections.get(key, [])
        rows = [dict(row) for row in list(section_rows or []) if isinstance(row, dict)]
        write_jsonl(paths[key], rows)
        restored_jsonl_counts[key] = len(rows)

    restored_json_keys: list[str] = []
    for key in BUNDLE_JSON_SECTION_KEYS:
        section_payload = sections.get(key, _default_json_section(key))
        if not isinstance(section_payload, dict):
            section_payload = _default_json_section(key)
        write_json(paths[key], section_payload)
        restored_json_keys.append(key)

    _rebuild_dedupe_index_from_cache(paths)
    manifest = refresh_lora_personalization_manifest(store_dir)
    return {
        "schema": "ai_subtitle_studio.lora_unified_data_bundle.restore_result.v1",
        "source_path": str(source_path),
        "target_path": str(paths["unified_lora_data"]),
        "restored_jsonl_counts": restored_jsonl_counts,
        "restored_json_keys": restored_json_keys,
        "restored_attachment_files": restored_attachment_files,
        "record_count": int((manifest.get("counts") or {}).get("unified_lora_data_records", 0) or 0),
        "manifest": manifest,
    }


def delete_pending_lora_data(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    initialize_lora_personalization_store(store_dir)
    removed: dict[str, int] = {}

    for key in BUNDLE_JSONL_SECTION_KEYS:
        rows = read_jsonl(paths[key])
        kept = ranked_lora_rows(key, [row for row in rows if lora_bucket_for_row(key, row) != LORA_BUCKET_PENDING_DELETE])
        if len(kept) != len(rows):
            write_jsonl(paths[key], kept)
            removed[key] = len(rows) - len(kept)

    for key in ("learned_split_rules", "learned_line_break_rules"):
        payload = read_json(paths[key], _default_json_section(key))
        items = [dict(item) for item in list((payload or {}).get("items") or []) if isinstance(item, dict)]
        kept_items = ranked_lora_rows(key, [item for item in items if lora_bucket_for_row(key, item) != LORA_BUCKET_PENDING_DELETE])
        if len(kept_items) != len(items):
            payload = dict(payload or _default_json_section(key))
            payload["items"] = kept_items
            payload["updated_at"] = iso_now()
            write_json(paths[key], payload)
            removed[key] = len(items) - len(kept_items)

    pending_zip = _bucket_archive_path(paths, LORA_BUCKET_PENDING_DELETE)
    removed_pending_zip = False
    try:
        if pending_zip.exists():
            pending_zip.unlink()
            removed_pending_zip = True
    except OSError:
        removed_pending_zip = False

    _rebuild_dedupe_index_from_cache(paths)
    bundle_result = refresh_unified_lora_data_bundle(store_dir, force=True)
    try:
        if pending_zip.exists():
            pending_zip.unlink()
            removed_pending_zip = True
    except OSError:
        pass
    manifest = refresh_lora_personalization_manifest(store_dir, refresh_bundle=False)
    return {
        "schema": "ai_subtitle_studio.lora_pending_delete_cleanup_result.v1",
        "updated_at": iso_now(),
        "removed": removed,
        "total_removed": sum(int(value or 0) for value in removed.values()),
        "removed_pending_zip": removed_pending_zip,
        "pending_zip": str(pending_zip),
        "bundle": bundle_result,
        "manifest": manifest,
    }


def reset_lora_personalization_store(store_dir: str | Path | None = None) -> dict[str, Any]:
    root = store_dir_path(store_dir)
    try:
        resolved_root = root.resolve()
    except OSError:
        resolved_root = root.absolute()
    if str(resolved_root) in {"", str(Path(resolved_root.anchor))}:
        raise ValueError(f"Refusing to reset unsafe LoRA store path: {resolved_root}")

    deleted_files = 0
    deleted_dirs = 0
    deleted_bytes = 0
    if root.exists():
        for path in root.rglob("*"):
            try:
                if path.is_file() or path.is_symlink():
                    deleted_files += 1
                    if path.is_file():
                        deleted_bytes += int(path.stat().st_size)
                elif path.is_dir():
                    deleted_dirs += 1
            except OSError:
                continue
        shutil.rmtree(root)

    manifest = initialize_lora_personalization_store(store_dir)
    return {
        "schema": "ai_subtitle_studio.lora_personalization_reset_result.v1",
        "reset_at": iso_now(),
        "store_dir": str(root),
        "deleted_files": deleted_files,
        "deleted_dirs": deleted_dirs,
        "deleted_bytes": deleted_bytes,
        "manifest": manifest,
    }


def initialize_lora_personalization_store(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["cache_root"].mkdir(parents=True, exist_ok=True)
    _migrate_legacy_lora_cache_layout(paths, cleanup_temp_files=True)
    paths["trained_adapters"].mkdir(parents=True, exist_ok=True)
    if _should_restore_from_existing_bundle(paths):
        return restore_lora_personalization_store_from_bundle(_existing_unified_lora_data_path(paths), store_dir)["manifest"]
    for key in BUNDLE_JSONL_SECTION_KEYS:
        paths[key].touch(exist_ok=True)
    if not paths["training_queue"].exists():
        write_json(paths["training_queue"], default_queue())
    if not paths["learned_split_rules"].exists():
        write_json(paths["learned_split_rules"], default_learned_rules("ai_subtitle_studio.learned_split_rules.v1"))
    if not paths["learned_line_break_rules"].exists():
        write_json(paths["learned_line_break_rules"], default_learned_rules("ai_subtitle_studio.learned_line_break_rules.v1"))
    if not paths["best_settings"].exists():
        write_json(paths["best_settings"], default_best_settings())
    if not paths["dedupe_index"].exists():
        write_json(paths["dedupe_index"], default_dedupe_index())
    if not paths["retention_policy"].exists():
        write_json(paths["retention_policy"], default_retention_policy())
    bucket_archives_missing = not all(path.exists() for path in _bucket_archive_paths(paths).values())
    defer_legacy_zip_migration = bucket_archives_missing and paths["legacy_unified_lora_zip"].exists()
    return refresh_lora_personalization_manifest(
        store_dir,
        refresh_bundle=bucket_archives_missing and not defer_legacy_zip_migration,
    )


def refresh_lora_personalization_manifest(
    store_dir: str | Path | None = None,
    *,
    refresh_bundle: bool = True,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    _migrate_legacy_lora_cache_layout(paths, cleanup_temp_files=False)
    voice_training_plan = read_json(paths["voice_lora_training_plan"], {})
    stt1_whisper_adapter_plan = read_json(paths["stt1_whisper_adapter_training_plan"], {})
    stt1_whisper_runtime_manifest = read_json(paths["stt1_whisper_adapter_runtime_manifest"], {})
    counts = {
        "truth_table_rows": len(read_jsonl(paths["truth_table"])),
        "excluded_parenthetical_rows": len(read_jsonl(paths["excluded_parentheticals"])),
        "setting_trial_rows": len(read_jsonl(paths["setting_trials"])),
        "prompt_trial_rows": len(read_jsonl(paths["prompt_trials"])),
        "stt1_whisper_adapter_dataset_rows": len(read_jsonl(paths["stt1_whisper_adapter_dataset"])),
        "text_lora_dataset_rows": len(read_jsonl(paths["text_lora_dataset"])),
        "text_lora_corpus_rows": len(read_jsonl(paths["text_lora_corpus"])),
        "audio_preset_lora_rows": len(read_jsonl(paths["audio_preset_lora"])),
        "multimodal_lora_context_rows": len(read_jsonl(paths["multimodal_lora_context"])),
        "deep_policy_event_rows": len(read_jsonl(paths["deep_policy_events"])),
        "queue_items": len(list((read_json(paths["training_queue"], default_queue()) or {}).get("items") or [])),
        "learned_split_rules": len(list((read_json(paths["learned_split_rules"], {}) or {}).get("items") or [])),
        "learned_line_break_rules": len(list((read_json(paths["learned_line_break_rules"], {}) or {}).get("items") or [])),
        "dedupe_entry_count": sum(
            len(dict(v or {})) for v in dict((read_json(paths["dedupe_index"], default_dedupe_index()) or {}).get("entries") or {}).values()
        ),
        "llm_review_request_files": 1 if paths["llm_review_request"].exists() else 0,
        "llm_review_result_files": 1 if paths["llm_review_result"].exists() else 0,
        "retention_history_rows": len(read_jsonl(paths["retention_history"])),
        "voice_lora_bridge_rows": len(read_jsonl(paths["voice_lora_bridge"])),
        "voice_lora_profile_count": len(list((read_json(paths["voice_lora_profile_manifest"], {}) or {}).get("speaker_profiles") or [])),
        "voice_lora_training_items": len(list((voice_training_plan or {}).get("items") or [])),
        "voice_lora_stored_audio_items": count_ready_voice_audio_items(voice_training_plan),
        "stt1_whisper_adapter_training_items": len(list((stt1_whisper_adapter_plan or {}).get("items") or [])),
        "stt1_whisper_adapter_audio_items": sum(
            1 for item in list((stt1_whisper_adapter_plan or {}).get("items") or []) if bool((item or {}).get("audio_ready"))
        ),
        "stt1_whisper_adapter_runtime_ready": 1 if bool((stt1_whisper_runtime_manifest or {}).get("runtime_ready")) else 0,
    }
    retrieval_index = read_json(paths["lora_retrieval_index"], {})
    subtitle_pattern_index = read_json(paths["subtitle_pattern_index"], {})
    counts.update(
        {
            "lora_retrieval_index_docs": int((retrieval_index or {}).get("doc_count", 0) or 0),
            "lora_retrieval_index_bytes": int(bundle_file_info(paths["lora_retrieval_index"]).get("size_bytes", 0) or 0),
            "subtitle_pattern_index_patterns": int((subtitle_pattern_index or {}).get("pattern_count", 0) or 0),
            "subtitle_pattern_index_bytes": int(bundle_file_info(paths["subtitle_pattern_index"]).get("size_bytes", 0) or 0),
        }
    )
    if refresh_bundle:
        bundle_info = refresh_unified_lora_data_bundle(store_dir)
    else:
        bundle_info = {
            **bundle_file_info(paths["unified_lora_data"]),
            "refreshed": False,
            "counts": {},
            "record_count": 0,
            "bucket_files": {
                bucket: {
                    **bundle_file_info(path),
                    "quality_bucket": bucket,
                    "quality_bucket_label": LORA_BUCKET_LABELS.get(bucket, bucket),
                }
                for bucket, path in _bucket_archive_paths(paths).items()
            },
        }
    bundle_counts = dict(bundle_info.get("counts") or {})
    bucket_files = dict(bundle_info.get("bucket_files") or {})
    if not bucket_files:
        bucket_files = {
            bucket: {
                **bundle_file_info(path),
                "quality_bucket": bucket,
                "quality_bucket_label": LORA_BUCKET_LABELS.get(bucket, bucket),
            }
            for bucket, path in _bucket_archive_paths(paths).items()
        }
    existing_bucket_infos = [dict(info) for info in bucket_files.values() if bool(dict(info).get("exists"))]
    counts.update(
        {
            "unified_lora_data_files": len(existing_bucket_infos),
            "unified_lora_data_bytes": sum(int(info.get("size_bytes", 0) or 0) for info in existing_bucket_infos),
            "unified_lora_data_records": int(
                bundle_counts.get("unified_training_records", 0)
                or counts.get("truth_table_rows", 0)
                + counts.get("excluded_parenthetical_rows", 0)
                + counts.get("setting_trial_rows", 0)
                + counts.get("prompt_trial_rows", 0)
                + counts.get("voice_lora_bridge_rows", 0)
                + counts.get("stt1_whisper_adapter_dataset_rows", 0)
                + counts.get("text_lora_dataset_rows", 0)
                + counts.get("text_lora_corpus_rows", 0)
                + counts.get("audio_preset_lora_rows", 0)
                + counts.get("multimodal_lora_context_rows", 0)
                + counts.get("deep_policy_event_rows", 0)
            ),
        }
    )
    manifest = {
        "schema": "ai_subtitle_studio.lora_personalization_manifest.v1",
        "updated_at": iso_now(),
        "store_dir": str(paths["root"]),
        "files": {key: str(value) for key, value in paths.items() if key != "root"},
        "counts": counts,
        "primary_lora_learning_file": str(paths["unified_lora_data"]),
        "lora_learning_files": {
            bucket: str(_bucket_archive_path(paths, bucket))
            for bucket in LORA_ALL_BUCKETS
        },
        "lora_learning_file_info": bucket_files,
        "notes": [
            "PHASE3 ground-truth personalization storage root",
            "LoRA learning data is split into high/medium/low/pending-delete user-managed ZIP files",
            "high subtitle quality uses all LoRA buckets; balanced quality uses only high-score LoRA",
            "internal JSON/JSONL shard files live under .cache and can be rebuilt from the bundle",
            "source media is referenced in place by default",
        ],
    }
    write_json(paths["manifest"], manifest)
    return manifest
