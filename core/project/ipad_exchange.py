from __future__ import annotations

import os
import hashlib
from pathlib import Path
from typing import Any

from core.media_fingerprint import media_file_fingerprint, media_fingerprint_digest

IPAD_EXCHANGE_SCHEMA = "ai_subtitle_studio.ipad_exchange.v1"


def _abs(path: Any) -> str:
    return os.path.abspath(os.path.expanduser(str(path or "")))


def _sync_provider(path: str) -> str:
    lowered = path.lower()
    if "mobile documents" in lowered or "icloud" in lowered:
        return "icloud"
    if "/cloudstorage/" in lowered:
        return "cloudstorage"
    if "/volumes/" in lowered:
        return "external_or_nas"
    return "local"


def _portable_fingerprint_digest(path: str, *, sample_bytes: int = 1024 * 1024) -> str:
    abs_path = _abs(path)
    try:
        stat = os.stat(abs_path)
    except OSError:
        return ""
    digest = hashlib.sha1()
    digest.update(str(int(getattr(stat, "st_size", 0) or 0)).encode("ascii", errors="ignore"))
    try:
        with open(abs_path, "rb") as handle:
            sample_size = max(1, int(sample_bytes))
            digest.update(handle.read(sample_size))
            if int(getattr(stat, "st_size", 0) or 0) > sample_size:
                handle.seek(max(0, int(getattr(stat, "st_size", 0) or 0) - sample_size))
                digest.update(handle.read(sample_size))
    except OSError:
        return ""
    return digest.hexdigest()


def _file_record(path: str, *, project_root: str = "") -> dict[str, Any]:
    abs_path = _abs(path)
    exists = bool(abs_path and os.path.exists(abs_path))
    try:
        stat = os.stat(abs_path)
        size = int(getattr(stat, "st_size", 0) or 0)
        mtime_ns = int(getattr(stat, "st_mtime_ns", int(getattr(stat, "st_mtime", 0.0) * 1_000_000_000)))
    except OSError:
        size = 0
        mtime_ns = 0
    rel = ""
    if project_root:
        try:
            rel = os.path.relpath(abs_path, project_root)
        except ValueError:
            rel = ""
    return {
        "path": abs_path,
        "relative_path": rel,
        "name": os.path.basename(abs_path),
        "suffix": Path(abs_path).suffix.lower(),
        "exists": exists,
        "size": size,
        "mtime_ns": mtime_ns,
        "sync_provider": _sync_provider(abs_path),
        "fingerprint": media_file_fingerprint(abs_path) if exists else "",
        "fingerprint_digest": media_fingerprint_digest(abs_path) if exists else "",
        "portable_fingerprint_digest": _portable_fingerprint_digest(abs_path) if exists else "",
    }


def build_ipad_exchange_manifest(
    *,
    project_path: str = "",
    media_paths: list[str] | tuple[str, ...] | None = None,
    bundle_name: str = "",
) -> dict[str, Any]:
    project_abs = _abs(project_path) if project_path else ""
    project_root = os.path.dirname(project_abs) if project_abs else ""
    files = [_file_record(path, project_root=project_root) for path in (media_paths or [])]
    return {
        "schema": IPAD_EXCHANGE_SCHEMA,
        "bundle_name": str(bundle_name or (Path(project_abs).stem if project_abs else "ipad_exchange")),
        "project": _file_record(project_abs, project_root=project_root) if project_abs else {},
        "media": files,
        "media_count": len(files),
        "all_files_exist": all(item.get("exists") for item in files) and (not project_abs or os.path.exists(project_abs)),
        "sync_providers": sorted({str(item.get("sync_provider") or "local") for item in files}),
    }


def _resolved_record_path(record: dict[str, Any], bundle_root: str = "") -> str:
    root = _abs(bundle_root) if bundle_root else ""
    rel = str(record.get("relative_path") or "").strip()
    if root and rel and rel not in {".", os.curdir}:
        candidate = os.path.abspath(os.path.join(root, rel))
        if os.path.exists(candidate):
            return candidate
    path = str(record.get("path") or "")
    if path and os.path.exists(path):
        return path
    if root and rel:
        return os.path.abspath(os.path.join(root, rel))
    return path


def validate_ipad_exchange_manifest(manifest: dict[str, Any] | None, *, bundle_root: str = "") -> dict[str, Any]:
    data = dict(manifest or {}) if isinstance(manifest, dict) else {}
    root = str(bundle_root or data.get("bundle_root") or "").strip()
    records = []
    if isinstance(data.get("project"), dict) and data.get("project"):
        records.append(("project", data["project"]))
    for item in list(data.get("media") or []):
        if isinstance(item, dict):
            records.append(("media", item))

    missing = []
    stale = []
    valid = []
    for kind, record in records:
        path = _resolved_record_path(record, root)
        name = str(record.get("name") or os.path.basename(path))
        if not path or not os.path.exists(path):
            missing.append({"kind": kind, "name": name, "path": path})
            continue
        expected_portable = str(record.get("portable_fingerprint_digest") or "")
        current_portable = _portable_fingerprint_digest(path) if expected_portable else ""
        expected = expected_portable or str(record.get("fingerprint_digest") or "")
        current = current_portable or media_fingerprint_digest(path)
        if expected and current != expected:
            stale.append({"kind": kind, "name": name, "path": path, "expected": expected, "current": current})
        else:
            valid.append({"kind": kind, "name": name, "path": path})

    return {
        "schema": IPAD_EXCHANGE_SCHEMA,
        "valid": not missing and not stale,
        "valid_count": len(valid),
        "missing": missing,
        "stale": stale,
    }
