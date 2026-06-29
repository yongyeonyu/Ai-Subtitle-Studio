# Version: 03.14.28
# Phase: PHASE2
"""Shared project file I/O helpers."""
from __future__ import annotations

import os
import struct
import threading
import time
import zlib
from collections import OrderedDict
from hashlib import sha256
from typing import Any

from core.native_json import dumps_json_bytes, json_default, loads_json
from core.project.project_format import build_storage_project_payload, hydrate_project_runtime_views
from core.project.nle_project_state import NLE_PROJECT_STATE_RUNTIME_KEY, attach_project_nle_state
from core.project.nle_persistence_guard import (
    NLE_PERSISTENCE_QUARANTINE_KEY,
    approved_runtime_nle_project_state_persistence_requested,
    strip_unapproved_nle_persistence_fields,
)

try:
    import msgpack  # type: ignore
except Exception:  # pragma: no cover - fallback for minimal environments.
    msgpack = None  # type: ignore

_PROJECT_FILE_CACHE_MAX = 4
_PROJECT_FILE_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_PROJECT_FILE_CACHE_LOCK = threading.RLock()
_PROJECT_BINARY_MAGIC = b"AISS-PROJECT\x01"
_PROJECT_BINARY_HEADER = struct.Struct(">I")
_PROJECT_BINARY_SCHEMA = "ai_subtitle_studio.project_binary.v1"
_PROJECT_COMPRESSION_LEVEL = 1
_PROJECT_COMPRESSION_MIN_BYTES = 8 * 1024 * 1024
_PROJECT_COMPRESSION_MIN_SAVING_RATIO = 0.35
_PROJECT_RUNTIME_KEYS = {
    "_project_file_path",
    "_external_subtitle_segments_cache",
    "_external_stt_tracks_cache",
    "_hot_open_subtitle_segments_cache",
    "_hot_open_stt_preview_segments_cache",
    NLE_PROJECT_STATE_RUNTIME_KEY,
    NLE_PERSISTENCE_QUARANTINE_KEY,
    "_nle_snapshot_readback_parity",
    "project_path",
}


def _project_cache_key(filepath: str) -> str:
    return os.path.abspath(os.path.expanduser(str(filepath or "")))


def _project_file_signature(filepath: str) -> tuple[int, int] | None:
    try:
        stat = os.stat(filepath)
        return int(stat.st_mtime_ns), int(stat.st_size)
    except OSError:
        return None


def _project_file_trace_fields(filepath: str) -> dict[str, Any]:
    key = _project_cache_key(filepath)
    signature = _project_file_signature(key)
    return {
        "project_basename": os.path.basename(key),
        "project_path_hash": sha256(key.encode("utf-8", errors="replace")).hexdigest()[:16],
        "project_exists": signature is not None,
        "project_mtime_ns": int(signature[0]) if signature is not None else 0,
        "project_size_bytes": int(signature[1]) if signature is not None else 0,
        "project_extension": os.path.splitext(key)[1].lower(),
    }


def _trace_project_file_event(event: str, filepath: str, **fields: Any) -> bool:
    try:
        from core.runtime.trace_logger import current_app_trace_logger

        logger = current_app_trace_logger()
        if logger is None:
            return False
        payload = _project_file_trace_fields(filepath)
        payload.update(fields)
        return bool(
            logger.log_event(
                event,
                stage="project-io",
                level="INFO",
                **payload,
            )
        )
    except Exception:
        return False


def clear_project_file_cache(filepath: str | None = None) -> None:
    """Clear cached project JSON data.

    Passing a path clears one project; omitting it clears the full process cache.
    """
    with _PROJECT_FILE_CACHE_LOCK:
        if filepath:
            _PROJECT_FILE_CACHE.pop(_project_cache_key(filepath), None)
        else:
            _PROJECT_FILE_CACHE.clear()


def _cache_project_payload(filepath: str, signature: tuple[int, int] | None, project: dict[str, Any]) -> None:
    key = _project_cache_key(filepath)
    with _PROJECT_FILE_CACHE_LOCK:
        _PROJECT_FILE_CACHE[key] = {"signature": signature, "project": project}
        _PROJECT_FILE_CACHE.move_to_end(key)
        while len(_PROJECT_FILE_CACHE) > _PROJECT_FILE_CACHE_MAX:
            _PROJECT_FILE_CACHE.popitem(last=False)


def prime_project_file_cache(filepath: str, project: dict[str, Any]) -> None:
    """Pin an already-loaded project payload in the process cache."""
    if not isinstance(project, dict):
        return
    key = _project_cache_key(filepath)
    project["_project_file_path"] = key
    signature = _project_file_signature(key)
    _cache_project_payload(key, signature, project)


def _attach_project_path(project: dict[str, Any], filepath: str) -> dict[str, Any]:
    if isinstance(project, dict):
        strip_unapproved_nle_persistence_fields(project, source="project_io.read")
        project["_project_file_path"] = _project_cache_key(filepath)
        attach_project_nle_state(project, project_path=filepath)
    return project


def _attach_nle_snapshot_readback_parity(project: dict[str, Any], filepath: str) -> dict[str, Any]:
    if not isinstance(project, dict):
        return project
    try:
        from core.project.nle_snapshot import attach_nle_snapshot_readback_parity

        attach_nle_snapshot_readback_parity(project, project_path=filepath)
    except Exception:
        pass
    return project


def _project_payload_for_disk(project: dict[str, Any]) -> dict[str, Any]:
    payload = dict(project if isinstance(project, dict) else {})
    strip_unapproved_nle_persistence_fields(payload, source="project_io.write")
    keep_runtime_nle_state = approved_runtime_nle_project_state_persistence_requested(payload)
    for key in _PROJECT_RUNTIME_KEYS:
        if key == NLE_PROJECT_STATE_RUNTIME_KEY and keep_runtime_nle_state:
            continue
        payload.pop(key, None)
    try:
        from core.project.project_assets import project_uses_external_text_assets, strip_external_text_runtime_payload

        if project_uses_external_text_assets(payload):
            strip_external_text_runtime_payload(payload)
    except Exception:
        pass
    return build_storage_project_payload(payload)


def _write_bytes_atomic(path: str, data: bytes) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp-{os.getpid()}-{threading.get_ident()}"
    try:
        with open(tmp_path, "wb") as handle:
            handle.write(data)
            handle.flush()
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            pass


def _project_payload_binary_bytes(project: dict[str, Any]) -> tuple[str, bytes]:
    payload = project if isinstance(project, dict) else {}
    if msgpack is not None:
        return "msgpack", msgpack.packb(
            payload,
            use_bin_type=True,
            strict_types=False,
            default=json_default,
        )
    return "json", _project_payload_json_bytes(payload)


def _project_payload_json_bytes(project: dict[str, Any]) -> bytes:
    return dumps_json_bytes(
        project if isinstance(project, dict) else {},
        indent=None,
        compact=True,
        default=json_default,
    )


def _pack_project_payload(project: dict[str, Any]) -> bytes:
    payload_codec, raw = _project_payload_binary_bytes(project)
    body = raw
    compression = "none"
    if len(raw) >= _PROJECT_COMPRESSION_MIN_BYTES:
        compressed = zlib.compress(raw, level=_PROJECT_COMPRESSION_LEVEL)
        saved_ratio = 1.0 - (len(compressed) / max(1, len(raw)))
        if saved_ratio >= _PROJECT_COMPRESSION_MIN_SAVING_RATIO:
            body = compressed
            compression = "zlib"
    header = {
        "schema": _PROJECT_BINARY_SCHEMA,
        "payload": payload_codec,
        "encoding": "binary" if payload_codec == "msgpack" else "utf-8",
        "compression": compression,
        "compression_level": _PROJECT_COMPRESSION_LEVEL if compression == "zlib" else 0,
        "raw_size": len(raw),
        "body_size": len(body),
        "crc32": f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}",
    }
    header_bytes = dumps_json_bytes(header, indent=None, compact=True, default=json_default)
    return _PROJECT_BINARY_MAGIC + _PROJECT_BINARY_HEADER.pack(len(header_bytes)) + header_bytes + body


def _packed_project_trace_metadata(data: bytes) -> dict[str, Any]:
    if not data.startswith(_PROJECT_BINARY_MAGIC):
        return {
            "payload_codec": "json",
            "payload_compression": "none",
            "payload_raw_size_bytes": len(data),
            "payload_body_size_bytes": len(data),
        }
    try:
        offset = len(_PROJECT_BINARY_MAGIC)
        header_size = _PROJECT_BINARY_HEADER.unpack(data[offset:offset + _PROJECT_BINARY_HEADER.size])[0]
        offset += _PROJECT_BINARY_HEADER.size
        header = loads_json(data[offset:offset + header_size])
        if not isinstance(header, dict):
            return {}
        return {
            "payload_codec": str(header.get("payload") or ""),
            "payload_compression": str(header.get("compression") or ""),
            "payload_raw_size_bytes": int(header.get("raw_size") or 0),
            "payload_body_size_bytes": int(header.get("body_size") or 0),
        }
    except Exception:
        return {}


def _unpack_project_payload(data: bytes) -> dict[str, Any]:
    if data.startswith(_PROJECT_BINARY_MAGIC):
        offset = len(_PROJECT_BINARY_MAGIC)
        if len(data) < offset + _PROJECT_BINARY_HEADER.size:
            return {}
        header_size = _PROJECT_BINARY_HEADER.unpack(data[offset:offset + _PROJECT_BINARY_HEADER.size])[0]
        offset += _PROJECT_BINARY_HEADER.size
        header = loads_json(data[offset:offset + header_size])
        body = data[offset + header_size:]
        if not isinstance(header, dict) or header.get("schema") != _PROJECT_BINARY_SCHEMA:
            return {}
        raw = zlib.decompress(body) if str(header.get("compression") or "none") == "zlib" else body
        if int(header.get("raw_size") or 0) != len(raw):
            return {}
        crc = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
        if str(header.get("crc32") or "") != crc:
            return {}
        payload_codec = str(header.get("payload") or "json")
        if payload_codec == "msgpack":
            if msgpack is None:
                return {}
            payload = msgpack.unpackb(raw, raw=False, strict_map_key=False)
        else:
            payload = loads_json(raw)
        return payload if isinstance(payload, dict) else {}

    payload = loads_json(data)
    return payload if isinstance(payload, dict) else {}


def _read_project_payload_from_disk(key: str) -> dict[str, Any]:
    with open(key, "rb") as handle:
        return _unpack_project_payload(handle.read())


def read_project_storage_payload(filepath: str) -> dict[str, Any]:
    """Read the exact project payload stored on disk without hydrating runtime views."""
    key = _project_cache_key(filepath)
    return _read_project_payload_from_disk(key)


def read_project_file(filepath: str) -> dict[str, Any]:
    """Read a project file with the app-wide encoding/settings."""
    key = _project_cache_key(filepath)
    start = time.perf_counter()
    signature = _project_file_signature(key)
    with _PROJECT_FILE_CACHE_LOCK:
        cached = _PROJECT_FILE_CACHE.get(key)
        if cached and cached.get("signature") == signature:
            _PROJECT_FILE_CACHE.move_to_end(key)
            project = cached.get("project")
            loaded = _attach_project_path(project, key) if isinstance(project, dict) else {}
            _attach_nle_snapshot_readback_parity(loaded, key)
            _trace_project_file_event(
                "project_file_open",
                key,
                event_type="project_io_read",
                action="open_project",
                source="project_file_cache",
                cache_hit=True,
                elapsed_ms=round((time.perf_counter() - start) * 1000.0, 3),
                nle_runtime_state_attached=bool(
                    isinstance(loaded, dict) and NLE_PROJECT_STATE_RUNTIME_KEY in loaded
                ),
            )
            return loaded

    data = _read_project_payload_from_disk(key)
    project = _attach_project_path(data if isinstance(data, dict) else {}, key)
    hydrate_project_runtime_views(project)
    _attach_nle_snapshot_readback_parity(project, key)
    _cache_project_payload(key, signature, project)
    _trace_project_file_event(
        "project_file_open",
        key,
        event_type="project_io_read",
        action="open_project",
        source="project_file_disk",
        cache_hit=False,
        elapsed_ms=round((time.perf_counter() - start) * 1000.0, 3),
        nle_runtime_state_attached=bool(NLE_PROJECT_STATE_RUNTIME_KEY in project),
    )
    return project


def write_project_file(filepath: str, project: dict[str, Any]) -> None:
    """Write a project file as an atomic binary envelope."""
    key = _project_cache_key(filepath)
    start = time.perf_counter()
    folder = os.path.dirname(key)
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = _project_payload_for_disk(project)
    packed = _pack_project_payload(payload)
    stripped_runtime_key_count = sum(
        1
        for runtime_key in _PROJECT_RUNTIME_KEYS
        if isinstance(project, dict) and runtime_key in project and runtime_key not in payload
    )
    _write_bytes_atomic(key, packed)
    prime_project_file_cache(key, project)
    _trace_project_file_event(
        "project_file_save",
        key,
        event_type="project_io_write",
        action="save_project",
        source="project_file_disk",
        elapsed_ms=round((time.perf_counter() - start) * 1000.0, 3),
        storage_clean_nle_runtime=(
            NLE_PROJECT_STATE_RUNTIME_KEY not in payload
            and NLE_PERSISTENCE_QUARANTINE_KEY not in payload
        ),
        storage_has_runtime_nle_key=NLE_PROJECT_STATE_RUNTIME_KEY in payload,
        storage_has_quarantine_key=NLE_PERSISTENCE_QUARANTINE_KEY in payload,
        packed_size_bytes=len(packed),
        stripped_runtime_key_count=stripped_runtime_key_count,
        **_packed_project_trace_metadata(packed),
    )
