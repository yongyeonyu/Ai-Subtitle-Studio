from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from core.personalization.lora_models import iso_now
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


def _bundle_record_count(payload: dict[str, Any]) -> int:
    counts = dict((payload or {}).get("counts") or {})
    try:
        return int(counts.get("unified_training_records", 0) or 0)
    except Exception:
        return len(list((payload or {}).get("records") or []))


def _iter_lora_archive_attachment_files(paths: dict[str, Path]) -> list[Path]:
    root = paths["trained_adapters"]
    if not root.exists():
        return []
    files: list[Path] = []
    for item in root.rglob("*"):
        if item.is_file():
            files.append(item)
    return sorted(files)


def _write_unified_lora_archive(path: Path, payload: dict[str, Any], paths: dict[str, Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    attachment_files = _iter_lora_archive_attachment_files(paths)
    attachment_bytes = 0
    for item in attachment_files:
        try:
            attachment_bytes += int(item.stat().st_size)
        except OSError:
            continue
    metadata = {
        "schema": "ai_subtitle_studio.lora_unified_data_archive_manifest.v1",
        "updated_at": iso_now(),
        "payload_file": UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME,
        "payload_schema": str(payload.get("schema") or ""),
        "record_count": _bundle_record_count(payload),
        "attachment_files": len(attachment_files),
        "attachment_bytes": attachment_bytes,
    }
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(UNIFIED_LORA_ARCHIVE_MANIFEST_NAME, json.dumps(metadata, ensure_ascii=False, indent=2))
            archive.writestr(UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME, json.dumps(payload, ensure_ascii=False, indent=2))
            for item in attachment_files:
                archive.write(item, f"attachments/{item.relative_to(paths['root']).as_posix()}")
        tmp_path.replace(path)
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
    legacy = paths.get("legacy_unified_lora_data")
    if legacy is not None and legacy.exists():
        return legacy
    return target


def _remove_legacy_unified_lora_json(paths: dict[str, Path]) -> None:
    legacy = paths.get("legacy_unified_lora_data")
    if legacy is None or not legacy.exists():
        return
    try:
        legacy.unlink()
    except OSError:
        pass


def load_unified_lora_data_bundle(bundle_path: str | Path | None = None, store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    source_path = Path(bundle_path) if bundle_path else _existing_unified_lora_data_path(paths)
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
    text_lora_dataset_rows: list[dict[str, Any]],
    text_lora_corpus_rows: list[dict[str, Any]],
    audio_preset_rows: list[dict[str, Any]],
    multimodal_context_rows: list[dict[str, Any]],
    retention_history: list[dict[str, Any]] | None = None,
    voice_training_plan: dict[str, Any] | None = None,
    retrieval_index: dict[str, Any] | None = None,
) -> dict[str, int]:
    voice_training_plan = dict(voice_training_plan or {})
    retrieval_index = dict(retrieval_index or {})
    return {
        "truth_table_rows": len(truth_rows),
        "excluded_parenthetical_rows": len(excluded_rows),
        "setting_trial_rows": len(setting_trials),
        "prompt_trial_rows": len(prompt_trials),
        "retention_history_rows": len(retention_history or []),
        "voice_lora_bridge_rows": len(voice_bridge_rows),
        "voice_lora_training_items": len(list(voice_training_plan.get("items") or [])),
        "voice_lora_stored_audio_items": count_ready_voice_audio_items(voice_training_plan),
        "text_lora_dataset_rows": len(text_lora_dataset_rows),
        "text_lora_corpus_rows": len(text_lora_corpus_rows),
        "audio_preset_lora_rows": len(audio_preset_rows),
        "multimodal_lora_context_rows": len(multimodal_context_rows),
        "lora_retrieval_index_docs": int(retrieval_index.get("doc_count", 0) or 0),
        "unified_training_records": (
            len(truth_rows)
            + len(excluded_rows)
            + len(setting_trials)
            + len(prompt_trials)
            + len(voice_bridge_rows)
            + len(text_lora_dataset_rows)
            + len(text_lora_corpus_rows)
            + len(audio_preset_rows)
            + len(multimodal_context_rows)
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
        text_lora_dataset_rows=read_jsonl(paths["text_lora_dataset"]),
        text_lora_corpus_rows=read_jsonl(paths["text_lora_corpus"]),
        audio_preset_rows=read_jsonl(paths["audio_preset_lora"]),
        multimodal_context_rows=read_jsonl(paths["multimodal_lora_context"]),
        voice_training_plan=read_json(paths["voice_lora_training_plan"], {}),
        retrieval_index=read_json(paths["lora_retrieval_index"], {}),
    )


def _build_unified_lora_data_bundle(paths: dict[str, Path]) -> dict[str, Any]:
    jsonl_sections = {key: read_jsonl(paths[key]) for key in BUNDLE_JSONL_SECTION_KEYS}
    voice_training_plan = read_json(paths["voice_lora_training_plan"], {})
    retrieval_index = read_json(paths["lora_retrieval_index"], {})
    records = [
        {"kind": kind, "record": row}
        for kind in (
            "truth_table",
            "excluded_parentheticals",
            "setting_trials",
            "prompt_trials",
            "voice_lora_bridge",
            "text_lora_dataset",
            "text_lora_corpus",
            "audio_preset_lora",
            "multimodal_lora_context",
        )
        for row in jsonl_sections.get(kind, [])
    ]
    sections = {
        **jsonl_sections,
        "training_queue": read_json(paths["training_queue"], default_queue()),
        "learned_split_rules": read_json(paths["learned_split_rules"], default_learned_rules("ai_subtitle_studio.learned_split_rules.v1")),
        "learned_line_break_rules": read_json(paths["learned_line_break_rules"], default_learned_rules("ai_subtitle_studio.learned_line_break_rules.v1")),
        "best_settings": read_json(paths["best_settings"], default_best_settings()),
        "retention_policy": read_json(paths["retention_policy"], default_retention_policy()),
        "llm_review_request": read_json(paths["llm_review_request"], {}),
        "llm_review_result": read_json(paths["llm_review_result"], {}),
        "voice_lora_profile_manifest": read_json(paths["voice_lora_profile_manifest"], {}),
        "voice_lora_training_plan": voice_training_plan,
        "voice_lora_dataset_manifest": read_json(paths["voice_lora_dataset_manifest"], {}),
        "text_lora_manifest": read_json(paths["text_lora_manifest"], {}),
        "text_lora_corpus_manifest": read_json(paths["text_lora_corpus_manifest"], {}),
        "text_lora_training_plan": read_json(paths["text_lora_training_plan"], {}),
        "lora_retrieval_index": retrieval_index,
    }
    return {
        "schema": "ai_subtitle_studio.lora_unified_data_bundle.v1",
        "updated_at": iso_now(),
        "storage_mode": "single_file_managed_zip_bundle",
        "bundle_role": "primary_user_managed_lora_learning_file",
        "archive_format": "zip",
        "archive_payload_file": UNIFIED_LORA_ARCHIVE_PAYLOAD_NAME,
        "store_dir": str(paths["root"]),
        "managed_file": str(paths["unified_lora_data"]),
        "internal_cache_files": {key: str(paths[key]) for key in UNIFIED_LORA_BUNDLE_SOURCE_KEYS if key in paths},
        "counts": _bundle_counts_from_rows(
            truth_rows=jsonl_sections["truth_table"],
            excluded_rows=jsonl_sections["excluded_parentheticals"],
            setting_trials=jsonl_sections["setting_trials"],
            prompt_trials=jsonl_sections["prompt_trials"],
            retention_history=jsonl_sections["retention_history"],
            voice_bridge_rows=jsonl_sections["voice_lora_bridge"],
            text_lora_dataset_rows=jsonl_sections["text_lora_dataset"],
            text_lora_corpus_rows=jsonl_sections["text_lora_corpus"],
            audio_preset_rows=jsonl_sections["audio_preset_lora"],
            multimodal_context_rows=jsonl_sections["multimodal_lora_context"],
            voice_training_plan=voice_training_plan,
            retrieval_index=retrieval_index,
        ),
        "sections": sections,
        "records": records,
        "notes": [
            "This payload is stored inside the primary single-file ZIP LoRA personalization learning artifact.",
            "The app may rebuild internal cache shard files from this file for fast append, pruning, and UI inspection.",
            "Use sections for exact restore/review and records for flat training-data scans.",
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
        _write_unified_lora_archive(target, payload, paths)
        _remove_legacy_unified_lora_json(paths)
    if not counts:
        counts = _bundle_counts_from_cache(paths)
    return {
        **bundle_file_info(target),
        "refreshed": needs_refresh,
        "counts": counts,
        "record_count": int(counts.get("unified_training_records", 0) or 0),
    }


def _cache_record_count(paths: dict[str, Path]) -> int:
    return sum(len(read_jsonl(paths[key])) for key in BUNDLE_JSONL_SECTION_KEYS if paths.get(key) is not None and paths[key].exists())


def _should_restore_from_existing_bundle(paths: dict[str, Path]) -> bool:
    bundle_path = _existing_unified_lora_data_path(paths)
    if not bundle_path.exists():
        return False
    payload = _read_unified_lora_payload(bundle_path, {})
    if not isinstance(payload, dict) or str(payload.get("schema") or "") != "ai_subtitle_studio.lora_unified_data_bundle.v1":
        return False
    return _bundle_record_count(payload) > 0 and _cache_record_count(paths) == 0


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
    source_path = Path(bundle_path) if bundle_path else _existing_unified_lora_data_path(paths)
    payload = _read_unified_lora_payload(source_path, {})
    if not isinstance(payload, dict) or str(payload.get("schema") or "") != "ai_subtitle_studio.lora_unified_data_bundle.v1":
        raise ValueError(f"Unsupported LoRA learning bundle: {source_path}")

    paths["root"].mkdir(parents=True, exist_ok=True)
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
    return refresh_lora_personalization_manifest(store_dir)


def refresh_lora_personalization_manifest(store_dir: str | Path | None = None) -> dict[str, Any]:
    paths = store_paths(store_dir)
    voice_training_plan = read_json(paths["voice_lora_training_plan"], {})
    counts = {
        "truth_table_rows": len(read_jsonl(paths["truth_table"])),
        "excluded_parenthetical_rows": len(read_jsonl(paths["excluded_parentheticals"])),
        "setting_trial_rows": len(read_jsonl(paths["setting_trials"])),
        "prompt_trial_rows": len(read_jsonl(paths["prompt_trials"])),
        "text_lora_dataset_rows": len(read_jsonl(paths["text_lora_dataset"])),
        "text_lora_corpus_rows": len(read_jsonl(paths["text_lora_corpus"])),
        "audio_preset_lora_rows": len(read_jsonl(paths["audio_preset_lora"])),
        "multimodal_lora_context_rows": len(read_jsonl(paths["multimodal_lora_context"])),
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
    }
    retrieval_index = read_json(paths["lora_retrieval_index"], {})
    counts.update(
        {
            "lora_retrieval_index_docs": int((retrieval_index or {}).get("doc_count", 0) or 0),
            "lora_retrieval_index_bytes": int(bundle_file_info(paths["lora_retrieval_index"]).get("size_bytes", 0) or 0),
        }
    )
    bundle_info = refresh_unified_lora_data_bundle(store_dir)
    bundle_counts = dict(bundle_info.get("counts") or {})
    counts.update(
        {
            "unified_lora_data_files": 1 if bool(bundle_info.get("exists")) else 0,
            "unified_lora_data_bytes": int(bundle_info.get("size_bytes", 0) or 0),
            "unified_lora_data_records": int(
                bundle_counts.get("unified_training_records", 0)
                or counts.get("truth_table_rows", 0)
                + counts.get("excluded_parenthetical_rows", 0)
                + counts.get("setting_trial_rows", 0)
                + counts.get("prompt_trial_rows", 0)
                + counts.get("voice_lora_bridge_rows", 0)
                + counts.get("text_lora_dataset_rows", 0)
                + counts.get("text_lora_corpus_rows", 0)
                + counts.get("audio_preset_lora_rows", 0)
                + counts.get("multimodal_lora_context_rows", 0)
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
        "notes": [
            "PHASE3 ground-truth personalization storage root",
            "lora_data_bundle.zip is the primary user-managed single-file learning artifact",
            "internal JSON/JSONL shard files are cache files that can be rebuilt from the bundle",
            "source media is referenced in place by default",
        ],
    }
    write_json(paths["manifest"], manifest)
    return manifest
