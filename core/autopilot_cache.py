from __future__ import annotations

"""Small cache primitives for AutoPilot stage artifacts and diagnostics."""

import gzip
import hashlib
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

from core.native_json import dumps_json_bytes, dumps_json_text, loads_json


AUTOPILOT_CACHE_SCHEMA = "ai_subtitle_studio.autopilot_cache.v1"
STAGE_CACHE_ALGORITHM_VERSION = "autopilot-stage-cache-v1"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def stable_json_dumps(value: Any) -> str:
    return dumps_json_text(_json_safe(value), sort_keys=True, compact=True)


def _stable_json_bytes(value: Any, *, append_newline: bool = False) -> bytes:
    return dumps_json_bytes(_json_safe(value), sort_keys=True, compact=True, append_newline=append_newline)


def stable_hash(value: Any, *, length: int = 16) -> str:
    digest = hashlib.sha256(_stable_json_bytes(value)).hexdigest()
    return digest[: max(8, int(length or 16))]


def settings_hash(settings: dict[str, Any] | None, *, keys: Iterable[str] | None = None) -> str:
    data = settings or {}
    if keys is None:
        return stable_hash(data)
    key_set = {str(key) for key in keys}
    data = {key: value for key, value in data.items() if str(key) in key_set}
    return stable_hash(data)


def model_hash(models: dict[str, Any] | None = None, **kwargs: Any) -> str:
    if not kwargs:
        return stable_hash(models or {})
    data = dict(models or {})
    data.update(kwargs)
    return stable_hash(data)


def cut_boundary_fingerprint(boundaries: Iterable[Any] | None) -> str:
    rows = []
    for item in boundaries or []:
        if isinstance(item, dict):
            rows.append(
                {
                    "time": item.get("timeline_sec", item.get("time", item.get("start"))),
                    "frame": item.get("timeline_frame", item.get("frame")),
                    "source": item.get("source"),
                    "verified": item.get("verified"),
                    "status": item.get("status"),
                }
            )
        else:
            rows.append(item)
    return stable_hash(rows)


def stage_cache_key(
    *,
    media_fingerprint: dict[str, Any] | str,
    stage: str,
    settings: dict[str, Any] | None = None,
    models: dict[str, Any] | None = None,
    hard_cut_fingerprint: str = "",
    stage_hash: str = "",
    algorithm_version: str = STAGE_CACHE_ALGORITHM_VERSION,
) -> str:
    payload = {
        "schema": AUTOPILOT_CACHE_SCHEMA,
        "algorithm_version": algorithm_version,
        "media_fingerprint": media_fingerprint,
        "stage": str(stage or ""),
        "settings_hash": settings_hash(settings),
        "model_hash": model_hash(models),
        "hard_cut_fingerprint": str(hard_cut_fingerprint or ""),
        "stage_hash": str(stage_hash or ""),
    }
    return stable_hash(payload, length=32)


def _iter_dict_rows(rows: Iterable[dict[str, Any]] | None) -> Iterable[dict[str, Any]]:
    for row in rows or []:
        yield dict(row)


def write_compressed_jsonl(path: str | Path, rows: Iterable[dict[str, Any]], *, prefer_zstd: bool = True) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    row_source = rows or []
    row_list = [dict(row) for row in row_source] if prefer_zstd else None
    codec = "plain"
    final_path = target
    if prefer_zstd:
        try:
            import zstandard as zstd  # type: ignore

            final_path = target if str(target).endswith(".zst") else Path(str(target) + ".zst")
            with open(final_path, "wb") as raw:
                with zstd.ZstdCompressor(level=3).stream_writer(raw) as writer:
                    for row in row_list:
                        writer.write(_stable_json_bytes(row, append_newline=True))
            codec = "zstd"
            return {"schema": AUTOPILOT_CACHE_SCHEMA, "path": str(final_path), "codec": codec, "rows": len(row_list)}
        except Exception:
            codec = "plain"
    if str(target).endswith(".gz"):
        final_path = target
    elif target.suffix:
        final_path = target.with_suffix(target.suffix + ".gz")
    else:
        final_path = Path(str(target) + ".jsonl.gz")
    row_count = 0
    with gzip.open(final_path, "wb") as fh:
        for row in (row_list if row_list is not None else _iter_dict_rows(row_source)):
            fh.write(_stable_json_bytes(row, append_newline=True))
            row_count += 1
    codec = "gzip"
    return {"schema": AUTOPILOT_CACHE_SCHEMA, "path": str(final_path), "codec": codec, "rows": row_count}


def read_compressed_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    suffix = source.suffix.lower()
    rows: list[dict[str, Any]] = []
    if suffix == ".zst":
        try:
            import zstandard as zstd  # type: ignore

            with open(source, "rb") as raw:
                with zstd.ZstdDecompressor().stream_reader(raw) as reader:
                    pending = b""
                    while True:
                        chunk = reader.read(64 * 1024)
                        if not chunk:
                            break
                        lines = (pending + chunk).splitlines(keepends=True)
                        pending = b""
                        if lines and not lines[-1].endswith((b"\n", b"\r")):
                            pending = lines.pop()
                        for line in lines:
                            if line.strip():
                                rows.append(loads_json(line))
                    if pending.strip():
                        rows.append(loads_json(pending))
            return rows
        except Exception:
            return []
    opener = gzip.open if suffix == ".gz" else open
    with opener(source, "rt", encoding="utf-8") as fh:  # type: ignore[arg-type]
        for line in fh:
            if line.strip():
                rows.append(loads_json(line))
    return rows


class NegativeCache:
    def __init__(self, ttl_sec: float = 300.0, max_items: int = 512):
        self.ttl_sec = max(1.0, float(ttl_sec or 300.0))
        self.max_items = max(1, int(max_items or 512))
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def put(self, key: str, value: Any = True) -> None:
        now = time.monotonic()
        raw_key = str(key)
        self._items[raw_key] = (now, value)
        self._items.move_to_end(raw_key)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)

    def get(self, key: str) -> Any | None:
        raw_key = str(key)
        item = self._items.get(raw_key)
        if item is None:
            return None
        created, value = item
        if time.monotonic() - created > self.ttl_sec:
            self._items.pop(raw_key, None)
            return None
        self._items.move_to_end(raw_key)
        return value

    def __contains__(self, key: object) -> bool:
        return self.get(str(key)) is not None


class LRUCacheManager:
    def __init__(self, max_items: int = 128):
        self.max_items = max(1, int(max_items or 128))
        self._items: OrderedDict[str, Any] = OrderedDict()

    def put(self, key: str, value: Any) -> None:
        raw_key = str(key)
        self._items[raw_key] = value
        self._items.move_to_end(raw_key)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)

    def get(self, key: str, default: Any = None) -> Any:
        raw_key = str(key)
        try:
            value = self._items[raw_key]
        except KeyError:
            return default
        self._items.move_to_end(raw_key)
        return value

    def resize(self, max_items: int) -> None:
        self.max_items = max(1, int(max_items or 1))
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": AUTOPILOT_CACHE_SCHEMA,
            "max_items": self.max_items,
            "size": len(self._items),
            "keys": list(self._items.keys()),
        }


__all__ = [
    "AUTOPILOT_CACHE_SCHEMA",
    "STAGE_CACHE_ALGORITHM_VERSION",
    "LRUCacheManager",
    "NegativeCache",
    "cut_boundary_fingerprint",
    "model_hash",
    "read_compressed_jsonl",
    "settings_hash",
    "stable_hash",
    "stable_json_dumps",
    "stage_cache_key",
    "write_compressed_jsonl",
]
