# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Portable STT LoRA/runtime policy bundle writer."""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import datetime
from typing import Any

from core.runtime import config
from core.stt_mode.models import STT_LORA_BUNDLE_SCHEMA, STT_MODE_LEARNING_SCHEMA, STT_MODE_STATE_SCHEMA


SIZE_TIERS = {
    "100MB": 100 * 1024 * 1024,
    "300MB": 300 * 1024 * 1024,
    "500MB": 500 * 1024 * 1024,
    "1GB": 1024 * 1024 * 1024,
}

_POLICY_FILES = {
    "stt_dictation_resegment": "stt_dictation_resegment_policy.json",
    "stt_vad_segment_model": "stt_vad_segment_model.json",
    "subtitle_style_policy": "subtitle_style_policy.json",
    "protected_terms": "protected_terms.json",
}


def _now_id() -> str:
    return datetime.now().strftime("%Y_%m_%d_%H%M%S")


def _json_dump(path: str, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _manifest_for_checksum(path: str) -> bytes:
    data = _read_json(path)
    data["checksum"] = ""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def calculate_bundle_checksum(bundle_dir: str) -> str:
    sha = hashlib.sha256()
    for root, _dirs, files in os.walk(bundle_dir):
        for name in sorted(files):
            if name == "checksum.sha256":
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, bundle_dir).replace(os.sep, "/")
            sha.update(rel.encode("utf-8"))
            if rel == "manifest.json":
                sha.update(_manifest_for_checksum(path))
            else:
                with open(path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        sha.update(chunk)
    return sha.hexdigest()


def build_manifest(
    *,
    bundle_id: str,
    size_tier: str = "300MB",
    actual_size_bytes: int = 0,
    checksum: str = "",
) -> dict[str, Any]:
    max_size = SIZE_TIERS.get(str(size_tier), SIZE_TIERS["300MB"])
    return {
        "schema": STT_LORA_BUNDLE_SCHEMA,
        "bundle_id": bundle_id,
        "version": "1",
        "created_by": "desktop",
        "target_runtime": ["desktop", "ipad"],
        "compatible_project_schema": [
            STT_MODE_STATE_SCHEMA,
            STT_MODE_LEARNING_SCHEMA,
        ],
        "size_tier": str(size_tier),
        "actual_size_bytes": int(actual_size_bytes or 0),
        "max_size_bytes": int(max_size),
        "adapters": {
            "stt_dictation_resegment": {
                "id": "stt_dictation_resegment",
                "version": "1",
                "format": "policy_json",
                "file": _POLICY_FILES["stt_dictation_resegment"],
            },
            "stt_vad_segment_model": {
                "id": "stt_vad_segment_model",
                "version": "1",
                "format": "policy_json",
                "file": _POLICY_FILES["stt_vad_segment_model"],
            },
            "subtitle_style_policy": {
                "id": "subtitle_style_policy",
                "version": "1",
                "format": "policy_json",
                "file": _POLICY_FILES["subtitle_style_policy"],
            },
        },
        "protected_terms_file": _POLICY_FILES["protected_terms"],
        "checksum": checksum,
    }


def export_stt_lora_bundle(
    *,
    output_dir: str | None = None,
    bundle_id: str | None = None,
    size_tier: str = "300MB",
    stt_dictation_resegment_policy: dict[str, Any] | None = None,
    stt_vad_segment_model: dict[str, Any] | None = None,
    subtitle_style_policy: dict[str, Any] | None = None,
    protected_terms: list[str] | None = None,
    zip_output: bool = False,
) -> dict[str, Any]:
    root = output_dir or os.path.join(config.OUTPUT_DIR, "stt_lora_bundles")
    os.makedirs(root, exist_ok=True)
    bundle_id = str(bundle_id or f"stt_lora_{_now_id()}")
    bundle_dir = os.path.join(root, bundle_id)
    os.makedirs(bundle_dir, exist_ok=True)

    policies = {
        _POLICY_FILES["stt_dictation_resegment"]: {
            "schema": "ai_subtitle_studio.stt_dictation_resegment_policy.v1",
            "policy": dict(stt_dictation_resegment_policy or {}),
        },
        _POLICY_FILES["stt_vad_segment_model"]: {
            "schema": "ai_subtitle_studio.stt_vad_segment_model.v1",
            "model": dict(stt_vad_segment_model or {}),
        },
        _POLICY_FILES["subtitle_style_policy"]: {
            "schema": "ai_subtitle_studio.subtitle_style_policy.v1",
            "policy": dict(subtitle_style_policy or {}),
        },
        _POLICY_FILES["protected_terms"]: {
            "schema": "ai_subtitle_studio.protected_terms.v1",
            "terms": list(protected_terms or []),
        },
    }
    for filename, payload in policies.items():
        _json_dump(os.path.join(bundle_dir, filename), payload)

    manifest_path = os.path.join(bundle_dir, "manifest.json")
    _json_dump(manifest_path, build_manifest(bundle_id=bundle_id, size_tier=size_tier))
    actual_size = sum(
        os.path.getsize(os.path.join(root_dir, name))
        for root_dir, _dirs, files in os.walk(bundle_dir)
        for name in files
        if name != "checksum.sha256"
    )
    _json_dump(manifest_path, build_manifest(bundle_id=bundle_id, size_tier=size_tier, actual_size_bytes=actual_size))
    checksum = calculate_bundle_checksum(bundle_dir)
    _json_dump(
        manifest_path,
        build_manifest(
            bundle_id=bundle_id,
            size_tier=size_tier,
            actual_size_bytes=actual_size,
            checksum=checksum,
        ),
    )
    with open(os.path.join(bundle_dir, "checksum.sha256"), "w", encoding="utf-8") as handle:
        handle.write(checksum + "\n")

    zip_path = ""
    if zip_output:
        zip_path = f"{bundle_dir}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for root_dir, _dirs, files in os.walk(bundle_dir):
                for name in files:
                    path = os.path.join(root_dir, name)
                    archive.write(path, os.path.relpath(path, bundle_dir))

    return {
        "bundle_id": bundle_id,
        "bundle_dir": bundle_dir,
        "manifest_path": manifest_path,
        "checksum": checksum,
        "zip_path": zip_path,
        "manifest": _read_json(manifest_path),
    }


def validate_stt_lora_bundle(bundle_dir: str) -> dict[str, Any]:
    manifest_path = os.path.join(bundle_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return {"valid": False, "errors": ["missing_manifest"]}
    manifest = _read_json(manifest_path)
    errors: list[str] = []
    if manifest.get("schema") != STT_LORA_BUNDLE_SCHEMA:
        errors.append("invalid_schema")
    for schema in (STT_MODE_STATE_SCHEMA, STT_MODE_LEARNING_SCHEMA):
        if schema not in list(manifest.get("compatible_project_schema") or []):
            errors.append(f"missing_compatible_schema:{schema}")
    adapters = manifest.get("adapters") if isinstance(manifest.get("adapters"), dict) else {}
    for key in ("stt_dictation_resegment", "stt_vad_segment_model", "subtitle_style_policy"):
        adapter = adapters.get(key) if isinstance(adapters.get(key), dict) else {}
        filename = str(adapter.get("file") or "")
        if not filename or not os.path.exists(os.path.join(bundle_dir, filename)):
            errors.append(f"missing_adapter_file:{key}")
    protected_terms_file = str(manifest.get("protected_terms_file") or _POLICY_FILES["protected_terms"])
    if not os.path.exists(os.path.join(bundle_dir, protected_terms_file)):
        errors.append("missing_protected_terms")
    stored = str(manifest.get("checksum") or "").strip()
    calculated = calculate_bundle_checksum(bundle_dir)
    if stored and stored != calculated:
        errors.append("checksum_mismatch")
    return {
        "valid": not errors,
        "errors": errors,
        "manifest": manifest,
        "checksum": calculated,
    }


__all__ = [
    "SIZE_TIERS",
    "build_manifest",
    "calculate_bundle_checksum",
    "export_stt_lora_bundle",
    "validate_stt_lora_bundle",
]
