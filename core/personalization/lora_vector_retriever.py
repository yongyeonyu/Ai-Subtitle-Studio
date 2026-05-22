from __future__ import annotations

import copy
import os
import threading
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Any

from core.personalization.lora_retrieval_config import (
    LORA_QUERY_CACHE_MAX,
    LORA_RETRIEVAL_HASH_DIM,
    LORA_RETRIEVAL_INDEX_SCHEMA,
    LORA_RETRIEVAL_SCORE_MODEL,
)
from core.personalization.lora_quality_buckets import lora_allowed_buckets_for_quality
from core.personalization.lora_retrieval_index import (
    build_lora_retrieval_index_payload,
    index_is_current,
)
from core.personalization.lora_retrieval_scoring import (
    query_cache_key,
    runtime_settings_from_retrieved_items,
    score_lora_docs,
)
from core.personalization.lora_retrieval_utils import (
    query_facets,
    query_text,
    read_json,
    vectorize_lora_text,
    write_json,
)
from core.personalization.lora_storage import store_paths


_PROCESS_INDEX_CACHE_MAX = 2
_PROCESS_INDEX_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_PROCESS_QUERY_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_INDEX_CACHE_LOCK = threading.RLock()
_QUERY_CACHE_LOCK = threading.RLock()
_LARGE_RUNTIME_INDEX_SKIP_LOGGED: set[str] = set()
_LARGE_RUNTIME_INDEX_SKIP_LOG_LOCK = threading.Lock()
_RUNTIME_INDEX_MAX_MB_DEFAULT = 128.0


def _cache_index_put(cache_key: str, payload: dict[str, Any]) -> None:
    with _INDEX_CACHE_LOCK:
        _PROCESS_INDEX_CACHE[cache_key] = payload
        _PROCESS_INDEX_CACHE.move_to_end(cache_key)
        while len(_PROCESS_INDEX_CACHE) > _PROCESS_INDEX_CACHE_MAX:
            _PROCESS_INDEX_CACHE.popitem(last=False)


def _setting_bool(settings: dict[str, Any] | None, key: str, default: bool) -> bool:
    value = settings.get(key, default) if isinstance(settings, dict) else default
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", ""}
    return bool(value)


def _setting_float(settings: dict[str, Any] | None, key: str, default: float) -> float:
    value = settings.get(key, default) if isinstance(settings, dict) else default
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _runtime_index_max_bytes(settings: dict[str, Any] | None) -> int:
    default_mb = _RUNTIME_INDEX_MAX_MB_DEFAULT
    env_value = os.environ.get("AI_SUBTITLE_LORA_RETRIEVAL_RUNTIME_MAX_MB")
    if env_value:
        try:
            default_mb = float(env_value)
        except ValueError:
            default_mb = _RUNTIME_INDEX_MAX_MB_DEFAULT
    max_mb = _setting_float(settings, "lora_retrieval_runtime_max_index_mb", default_mb)
    return int(max(0.0, max_mb) * 1024 * 1024)


def _large_runtime_index_skip(
    index_path: Path,
    settings: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not _setting_bool(settings, "lora_retrieval_skip_large_runtime_index", True):
        return None
    max_bytes = _runtime_index_max_bytes(settings)
    if max_bytes <= 0:
        return None
    try:
        size_bytes = int(index_path.stat().st_size)
    except OSError:
        return None
    if size_bytes <= max_bytes:
        return None
    return {
        "reason": "large_runtime_index",
        "path": str(index_path),
        "size_bytes": size_bytes,
        "limit_bytes": max_bytes,
    }


def _log_large_runtime_index_skip_once(skip: dict[str, Any]) -> None:
    key = f"{skip.get('path')}:{skip.get('limit_bytes')}"
    with _LARGE_RUNTIME_INDEX_SKIP_LOG_LOCK:
        if key in _LARGE_RUNTIME_INDEX_SKIP_LOGGED:
            return
        _LARGE_RUNTIME_INDEX_SKIP_LOGGED.add(key)
    try:
        from core.runtime.logger import get_logger

        size_mb = float(skip.get("size_bytes", 0) or 0) / 1024 / 1024
        limit_mb = float(skip.get("limit_bytes", 0) or 0) / 1024 / 1024
        get_logger().log(
            "[LoRA/Deep-전처리] LoRA 검색 인덱스가 커서 실시간 검색 생략: "
            f"{size_mb:.1f}MB > {limit_mb:.1f}MB"
        )
    except Exception:
        return


def build_lora_retrieval_index(
    store_dir: str | Path | None = None,
    *,
    force: bool = False,
    cancel_callback=None,
) -> dict[str, Any]:
    with _INDEX_CACHE_LOCK:
        paths = store_paths(store_dir)
        index_path = paths["lora_retrieval_index"]
        existing = read_json(index_path, {})
        if not force and index_is_current(existing, paths):
            _cache_index_put(str(index_path), existing)
            return existing

        index = build_lora_retrieval_index_payload(paths, cancel_callback=cancel_callback)
        if bool(index.get("cancelled")):
            return index
        write_json(index_path, index)
        _cache_index_put(str(index_path), index)
        with _QUERY_CACHE_LOCK:
            _PROCESS_QUERY_CACHE.clear()
        return index


def load_lora_retrieval_index(
    store_dir: str | Path | None = None,
    *,
    rebuild_if_stale: bool = True,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    index_path = paths["lora_retrieval_index"]
    cache_key = str(index_path)
    with _INDEX_CACHE_LOCK:
        cached = _PROCESS_INDEX_CACHE.get(cache_key)
        if cached and index_is_current(cached, paths):
            _PROCESS_INDEX_CACHE.move_to_end(cache_key)
            return cached

        index = read_json(index_path, {})
        if index_is_current(index, paths):
            _cache_index_put(cache_key, index)
            return index
        if rebuild_if_stale:
            return build_lora_retrieval_index(store_dir)
        return index if isinstance(index, dict) else {}


def _cache_get(cache_key: str) -> dict[str, Any] | None:
    with _QUERY_CACHE_LOCK:
        cached = _PROCESS_QUERY_CACHE.get(cache_key)
        if not cached:
            return None
        _PROCESS_QUERY_CACHE.move_to_end(cache_key)
        result = copy.deepcopy(cached)
        result["cache_hit"] = True
        return result


def _cache_put(cache_key: str, payload: dict[str, Any]) -> None:
    with _QUERY_CACHE_LOCK:
        while len(_PROCESS_QUERY_CACHE) >= LORA_QUERY_CACHE_MAX:
            try:
                oldest_key = next(iter(_PROCESS_QUERY_CACHE))
            except StopIteration:
                break
            _PROCESS_QUERY_CACHE.pop(oldest_key, None)
        _PROCESS_QUERY_CACHE[cache_key] = copy.deepcopy(payload)
        _PROCESS_QUERY_CACHE.move_to_end(cache_key)


def clear_lora_retrieval_caches() -> None:
    with _INDEX_CACHE_LOCK:
        _PROCESS_INDEX_CACHE.clear()
    with _QUERY_CACHE_LOCK:
        _PROCESS_QUERY_CACHE.clear()


def retrieve_lora_context(
    text: Any = "",
    *,
    media_path: str = "",
    media_id: str = "",
    settings: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    store_dir: str | Path | None = None,
    limit: int = 16,
    per_kind: int = 5,
    kinds: set[str] | tuple[str, ...] | list[str] | None = None,
    quality_buckets: set[str] | tuple[str, ...] | list[str] | frozenset[str] | None = None,
    rebuild_if_stale: bool = True,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    query = query_text(text, media_path=media_path, media_id=media_id, settings=settings, context=context)
    kind_filter = {str(kind) for kind in kinds} if kinds is not None else None
    bucket_filter = (
        {str(bucket) for bucket in quality_buckets}
        if quality_buckets is not None
        else set(lora_allowed_buckets_for_quality(settings if settings is not None else "precise"))
    )
    facets = query_facets(query, media_path=media_path, settings=settings, context=context)
    skip = _large_runtime_index_skip(paths["lora_retrieval_index"], settings if isinstance(settings, dict) else None)
    if skip is not None:
        _log_large_runtime_index_skip_once(skip)
        return {
            "schema": "ai_subtitle_studio.lora_retrieval_result.v1",
            "score_model": LORA_RETRIEVAL_SCORE_MODEL,
            "cache_hit": False,
            "query": query,
            "query_facets": facets,
            "index_updated_at": None,
            "index_doc_count": 0,
            "kind_counts": {},
            "quality_buckets": sorted(bucket_filter),
            "items": [],
            "by_kind": {},
            "skipped_reason": str(skip["reason"]),
            "index_path": str(skip["path"]),
            "index_size_bytes": int(skip["size_bytes"]),
            "index_size_limit_bytes": int(skip["limit_bytes"]),
        }

    index = load_lora_retrieval_index(store_dir, rebuild_if_stale=rebuild_if_stale)
    cache_key = query_cache_key(
        index,
        query,
        media_path=media_path,
        media_id=media_id,
        settings=settings,
        context=context,
        kinds=kind_filter,
        quality_buckets=bucket_filter,
        limit=limit,
        per_kind=per_kind,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if not bucket_filter:
        ranked = []
    else:
        ranked = score_lora_docs(
            index,
            query,
            media_path=media_path,
            media_id=media_id,
            query_facets=facets,
            kinds=kind_filter,
            quality_buckets=bucket_filter,
            settings=settings,
        )
    selected: list[dict[str, Any]] = []
    kind_counts: dict[str, int] = defaultdict(int)
    seen_docs: set[str] = set()
    for item in ranked:
        doc_id = str(item.get("doc_id") or "")
        kind = str(item.get("kind") or "")
        if doc_id in seen_docs:
            continue
        if int(kind_counts[kind]) >= max(1, int(per_kind or 1)):
            continue
        selected.append(item)
        seen_docs.add(doc_id)
        kind_counts[kind] += 1
        if len(selected) >= max(1, int(limit or 1)):
            break

    result = {
        "schema": "ai_subtitle_studio.lora_retrieval_result.v1",
        "score_model": str(index.get("score_model") or LORA_RETRIEVAL_SCORE_MODEL),
        "cache_hit": False,
        "query": query,
        "query_facets": facets,
        "index_updated_at": index.get("updated_at"),
        "index_doc_count": int(index.get("doc_count", 0) or 0),
        "kind_counts": dict(index.get("kind_counts") or {}),
        "quality_buckets": sorted(bucket_filter),
        "items": selected,
        "by_kind": {
            kind: [item for item in selected if str(item.get("kind") or "") == kind]
            for kind in sorted({str(item.get("kind") or "") for item in selected})
        },
    }
    _cache_put(cache_key, result)
    return result


def lora_retrieval_index_summary(
    store_dir: str | Path | None = None,
    *,
    rebuild_if_stale: bool = True,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    index = load_lora_retrieval_index(store_dir, rebuild_if_stale=False)
    current = index_is_current(index, paths)
    if not current and rebuild_if_stale:
        index = build_lora_retrieval_index(store_dir)
        current = True
    return {
        "path": str(paths["lora_retrieval_index"]),
        "exists": paths["lora_retrieval_index"].exists(),
        "current": current,
        "updated_at": index.get("updated_at"),
        "score_model": str(index.get("score_model") or LORA_RETRIEVAL_SCORE_MODEL),
        "doc_count": int(index.get("doc_count", 0) or 0),
        "kind_counts": dict(index.get("kind_counts") or {}),
        "bm25_terms": int((index.get("bm25") or {}).get("term_count", 0) or 0),
        "query_cache_entries": len(_PROCESS_QUERY_CACHE),
        "hash_dim": int(index.get("hash_dim", LORA_RETRIEVAL_HASH_DIM) or LORA_RETRIEVAL_HASH_DIM),
    }


__all__ = [
    "LORA_RETRIEVAL_HASH_DIM",
    "LORA_RETRIEVAL_INDEX_SCHEMA",
    "LORA_RETRIEVAL_SCORE_MODEL",
    "build_lora_retrieval_index",
    "clear_lora_retrieval_caches",
    "load_lora_retrieval_index",
    "lora_retrieval_index_summary",
    "retrieve_lora_context",
    "runtime_settings_from_retrieved_items",
    "vectorize_lora_text",
]
