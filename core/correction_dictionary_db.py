from __future__ import annotations

"""SQLite-backed correction dictionary runtime helpers."""

import hashlib
import os
import sqlite3
import threading
import weakref
from bisect import insort
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping

from core.json_file import read_json_file, write_json_file_atomic
from core.runtime import config


_DB_CACHE_LOCK = threading.RLock()
_SNAPSHOT_CACHE: dict[str, "_CorrectionSnapshot"] = {}
_SYNC_STATE_CACHE: dict[str, tuple[tuple[str, int], tuple[int, int, int]]] = {}
_RUNTIME_INDEX_CACHE: dict[tuple[str, int], "_CorrectionRuntimeIndex"] = {}
_REGISTERED_RUNTIME_DICTS: dict[int, tuple[weakref.ReferenceType["CorrectionDictionary"], str, tuple[str, int]]] = {}
_CANDIDATE_CACHE: "OrderedDict[tuple[str, int, str], tuple[tuple[int, str, str], ...]]" = OrderedDict()
_CANDIDATE_CACHE_MAX = 4096
_SQLITE_TIMEOUT_SEC = 30.0
_SQLITE_MMAP_BYTES = 256 * 1024 * 1024
_INDEXED_QUERY_MIN_ENTRIES = 96
INDEXED_QUERY_MIN_ENTRIES = _INDEXED_QUERY_MIN_ENTRIES


class CorrectionDictionary(dict):
    __slots__ = ("__weakref__",)


@dataclass(frozen=True)
class _CorrectionSnapshot:
    path: str
    db_path: str
    stat_sig: tuple[int, int, int]
    default_token: tuple[str, int]
    token: tuple[str, int]
    data: dict[str, str]


@dataclass(frozen=True)
class _CorrectionRuntimeIndex:
    rows: tuple[tuple[int, str, str], ...]
    head1: dict[str, tuple[tuple[int, str, str], ...]]
    head2: dict[str, tuple[tuple[int, str, str], ...]]


def correction_db_path(correction_json_path: str | None = None) -> str:
    json_path = os.path.abspath(str(correction_json_path or config.CORRECTIONS_FILE))
    base, _ext = os.path.splitext(json_path)
    return f"{base}.sqlite3"


def _normalize_corrections(
    corrections: Mapping[str, Any] | None,
    *,
    default: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    source = corrections if isinstance(corrections, Mapping) else default
    items: list[tuple[str, str]] = []
    for old, new in dict(source or {}).items():
        old_text = str(old or "")
        if not old_text.strip():
            continue
        items.append((old_text, str(new or "")))
    items.sort(key=lambda item: len(item[0]), reverse=True)
    return dict(items)


def _correction_items(corrections: Mapping[str, Any] | None) -> tuple[tuple[str, str], ...]:
    if not isinstance(corrections, Mapping):
        return ()
    return tuple((str(old), str(new)) for old, new in dict(corrections).items() if str(old or "").strip())


def correction_index_token(corrections: Mapping[str, Any] | None) -> tuple[str, int]:
    registered = _registered_runtime_dict(corrections)
    if registered is not None:
        return registered[1]
    items = _correction_items(corrections)
    if not items:
        return ("0", 0)
    digest = hashlib.blake2b(digest_size=16)
    for old, new in items:
        old_bytes = old.encode("utf-8", errors="surrogatepass")
        new_bytes = new.encode("utf-8", errors="surrogatepass")
        digest.update(len(old_bytes).to_bytes(8, "little", signed=False))
        digest.update(old_bytes)
        digest.update(len(new_bytes).to_bytes(8, "little", signed=False))
        digest.update(new_bytes)
    return (digest.hexdigest(), len(items))


def _stat_sig(path: str) -> tuple[int, int, int]:
    try:
        stat = os.stat(path)
        return (1, int(stat.st_mtime_ns), int(stat.st_size))
    except FileNotFoundError:
        return (0, 0, 0)
    except Exception:
        return (-1, 0, 0)


def _default_correction_path() -> str:
    return os.path.abspath(str(getattr(config, "CORRECTIONS_FILE", os.path.join(config.DATASET_DIR, "dataset_correction.json"))))


def _register_runtime_dict(data: "CorrectionDictionary", path: str, token: tuple[str, int]) -> None:
    key = id(data)

    def _cleanup(_ref: weakref.ReferenceType[CorrectionDictionary], *, _key: int = key) -> None:
        with _DB_CACHE_LOCK:
            _REGISTERED_RUNTIME_DICTS.pop(_key, None)

    with _DB_CACHE_LOCK:
        _REGISTERED_RUNTIME_DICTS[key] = (weakref.ref(data, _cleanup), path, token)


def _registered_runtime_dict(corrections: Mapping[str, Any] | None) -> tuple[str, tuple[str, int]] | None:
    if not isinstance(corrections, CorrectionDictionary):
        return None
    key = id(corrections)
    with _DB_CACHE_LOCK:
        entry = _REGISTERED_RUNTIME_DICTS.get(key)
        if entry is None:
            return None
        ref, path, token = entry
        if ref() is corrections:
            return path, token
        _REGISTERED_RUNTIME_DICTS.pop(key, None)
    return None


def _snapshot_for_path(
    correction_json_path: str | None = None,
    *,
    default: Mapping[str, Any] | None = None,
) -> _CorrectionSnapshot:
    json_path = os.path.abspath(str(correction_json_path or _default_correction_path()))
    stat_sig = _stat_sig(json_path)
    default_token = correction_index_token(default)
    with _DB_CACHE_LOCK:
        cached = _SNAPSHOT_CACHE.get(json_path)
        if cached is not None and cached.stat_sig == stat_sig and cached.default_token == default_token:
            return cached

    data = read_json_file(json_path, default=None, expected_type=dict, context="교정사전", log_errors=False)
    normalized = _normalize_corrections(data, default=default)
    snapshot = _CorrectionSnapshot(
        path=json_path,
        db_path=correction_db_path(json_path),
        stat_sig=stat_sig,
        default_token=default_token,
        token=correction_index_token(normalized),
        data=normalized,
    )
    with _DB_CACHE_LOCK:
        _SNAPSHOT_CACHE[json_path] = snapshot
    return snapshot


def _connect_db(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=_SQLITE_TIMEOUT_SEC)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-8192")
    try:
        conn.execute(f"PRAGMA mmap_size={_SQLITE_MMAP_BYTES}")
    except Exception:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS corrections (
            wrong TEXT PRIMARY KEY,
            right TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            wrong_len INTEGER NOT NULL,
            head1 TEXT NOT NULL,
            head2 TEXT NOT NULL
        ) WITHOUT ROWID
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_corrections_ordinal ON corrections(ordinal)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_corrections_head1 ON corrections(head1)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_corrections_head2 ON corrections(head2)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID
        """
    )
    return conn


def _load_meta(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM meta").fetchall()
    return {str(key): str(value) for key, value in rows}


def _rebuild_db(conn: sqlite3.Connection, snapshot: _CorrectionSnapshot) -> None:
    rows = [
        (
            wrong,
            right,
            ordinal,
            len(wrong),
            wrong[:1],
            wrong[:2],
        )
        for ordinal, (wrong, right) in enumerate(snapshot.data.items())
    ]
    with conn:
        conn.execute("DELETE FROM corrections")
        conn.executemany(
            """
            INSERT INTO corrections (wrong, right, ordinal, wrong_len, head1, head2)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.execute("DELETE FROM meta")
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [
                ("token", snapshot.token[0]),
                ("count", str(snapshot.token[1])),
                ("json_exists", str(snapshot.stat_sig[0])),
                ("json_mtime_ns", str(snapshot.stat_sig[1])),
                ("json_size", str(snapshot.stat_sig[2])),
            ],
        )


def _ensure_db_synced(snapshot: _CorrectionSnapshot) -> None:
    sync_key = (snapshot.token, snapshot.stat_sig)
    with _DB_CACHE_LOCK:
        if _SYNC_STATE_CACHE.get(snapshot.path) == sync_key:
            return

    conn = _connect_db(snapshot.db_path)
    try:
        meta = _load_meta(conn)
        meta_sig = (
            int(meta.get("json_exists", "0") or 0),
            int(meta.get("json_mtime_ns", "0") or 0),
            int(meta.get("json_size", "0") or 0),
        )
        meta_token = (str(meta.get("token", "0") or "0"), int(meta.get("count", "0") or 0))
        if meta_sig != snapshot.stat_sig or meta_token != snapshot.token:
            _rebuild_db(conn, snapshot)
    finally:
        conn.close()

    with _DB_CACHE_LOCK:
        _SYNC_STATE_CACHE[snapshot.path] = sync_key


def _clear_candidate_cache(token_prefix: tuple[str, int] | None = None) -> None:
    with _DB_CACHE_LOCK:
        if token_prefix is None:
            _CANDIDATE_CACHE.clear()
            return
        doomed = [key for key in _CANDIDATE_CACHE.keys() if key[:2] == token_prefix]
        for key in doomed:
            _CANDIDATE_CACHE.pop(key, None)


def _invalidate_path(correction_json_path: str | None = None) -> None:
    json_path = os.path.abspath(str(correction_json_path or _default_correction_path()))
    with _DB_CACHE_LOCK:
        snapshot = _SNAPSHOT_CACHE.pop(json_path, None)
        _SYNC_STATE_CACHE.pop(json_path, None)
        if snapshot is not None:
            _RUNTIME_INDEX_CACHE.pop(snapshot.token, None)
    _clear_candidate_cache(snapshot.token if snapshot is not None else None)


def load_corrections(
    correction_json_path: str | None = None,
    *,
    default: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    snapshot = _snapshot_for_path(correction_json_path, default=default)
    if snapshot.token != ("0", 0):
        _ensure_db_synced(snapshot)
    loaded = CorrectionDictionary(snapshot.data)
    _register_runtime_dict(loaded, snapshot.path, snapshot.token)
    return loaded


def save_corrections(
    corrections: Mapping[str, Any] | None,
    correction_json_path: str | None = None,
) -> dict[str, str]:
    json_path = os.path.abspath(str(correction_json_path or _default_correction_path()))
    normalized = _normalize_corrections(corrections)
    os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
    write_json_file_atomic(json_path, normalized, indent=2)
    _invalidate_path(json_path)
    snapshot = _snapshot_for_path(json_path)
    if snapshot.token != ("0", 0):
        _ensure_db_synced(snapshot)
    loaded = CorrectionDictionary(snapshot.data)
    _register_runtime_dict(loaded, snapshot.path, snapshot.token)
    return loaded


def save_correction(
    corrections: Mapping[str, Any] | None,
    original: str,
    corrected: str,
    correction_json_path: str | None = None,
) -> dict[str, str]:
    normalized = _normalize_corrections(corrections)
    original_text = str(original or "")
    if not original_text.strip():
        return dict(normalized)
    normalized[original_text] = str(corrected or "")
    return save_corrections(normalized, correction_json_path)


def _runtime_index(snapshot: _CorrectionSnapshot) -> _CorrectionRuntimeIndex:
    with _DB_CACHE_LOCK:
        cached = _RUNTIME_INDEX_CACHE.get(snapshot.token)
        if cached is not None:
            return cached

    rows = tuple((ordinal, wrong, right) for ordinal, (wrong, right) in enumerate(snapshot.data.items()))
    head1_map: dict[str, list[tuple[int, str, str]]] = {}
    head2_map: dict[str, list[tuple[int, str, str]]] = {}
    for row in rows:
        ordinal, wrong, right = row
        head1_map.setdefault(wrong[:1], []).append((ordinal, wrong, right))
        head2_map.setdefault(wrong[:2], []).append((ordinal, wrong, right))
    runtime_index = _CorrectionRuntimeIndex(
        rows=rows,
        head1={key: tuple(value) for key, value in head1_map.items()},
        head2={key: tuple(value) for key, value in head2_map.items()},
    )
    with _DB_CACHE_LOCK:
        _RUNTIME_INDEX_CACHE[snapshot.token] = runtime_index
    return runtime_index


def _query_candidates(snapshot: _CorrectionSnapshot, text: str) -> tuple[tuple[int, str, str], ...]:
    if not text:
        return ()
    cache_key = (snapshot.token[0], snapshot.token[1], str(text))
    with _DB_CACHE_LOCK:
        cached = _CANDIDATE_CACHE.get(cache_key)
        if cached is not None:
            _CANDIDATE_CACHE.move_to_end(cache_key)
            return cached

    chars = sorted(set(str(text)))
    bigrams = sorted({text[idx : idx + 2] for idx in range(max(0, len(text) - 1))})
    if not chars and not bigrams:
        return ()

    runtime_index = _runtime_index(snapshot)
    seen: set[int] = set()
    rows: list[tuple[int, str, str]] = []
    for token in bigrams:
        for row in runtime_index.head2.get(token, ()):
            if row[0] in seen:
                continue
            rows.append(row)
            seen.add(row[0])
    for token in chars:
        for row in runtime_index.head1.get(token, ()):
            if row[0] in seen:
                continue
            rows.append(row)
            seen.add(row[0])
    rows.sort(key=lambda item: item[0])
    packed = tuple(rows)
    with _DB_CACHE_LOCK:
        _CANDIDATE_CACHE[cache_key] = packed
        _CANDIDATE_CACHE.move_to_end(cache_key)
        while len(_CANDIDATE_CACHE) > _CANDIDATE_CACHE_MAX:
            _CANDIDATE_CACHE.popitem(last=False)
    return packed


def _snapshot_matches_runtime(
    corrections: Mapping[str, Any] | None,
    correction_json_path: str | None = None,
) -> _CorrectionSnapshot | None:
    if not isinstance(corrections, Mapping):
        return None
    snapshot = _snapshot_for_path(correction_json_path)
    registered = _registered_runtime_dict(corrections)
    if registered is not None:
        registered_path, registered_token = registered
        if os.path.abspath(registered_path) == snapshot.path and registered_token == snapshot.token:
            return snapshot
        return None
    if snapshot.token != correction_index_token(corrections):
        return None
    return snapshot


def apply_corrections_indexed(
    text: str,
    corrections: Mapping[str, Any] | None,
    *,
    correction_json_path: str | None = None,
) -> tuple[str, list[tuple[str, str]]] | None:
    if not text or not isinstance(corrections, Mapping):
        return None
    if len(corrections) < _INDEXED_QUERY_MIN_ENTRIES:
        return None
    snapshot = _snapshot_matches_runtime(corrections, correction_json_path)
    if snapshot is None or snapshot.token == ("0", 0):
        return None
    _ensure_db_synced(snapshot)

    current = str(text)
    applied_pairs: list[tuple[str, str]] = []
    rows_by_ordinal = {
        ordinal: (wrong, right)
        for ordinal, wrong, right in _query_candidates(snapshot, current)
    }
    scheduled = set(rows_by_ordinal.keys())
    pending = sorted(scheduled)
    processed: set[int] = set()
    index = 0

    while index < len(pending):
        ordinal = pending[index]
        index += 1
        if ordinal in processed:
            continue
        processed.add(ordinal)
        wrong, right = rows_by_ordinal.get(ordinal, ("", ""))
        if not wrong or wrong not in current:
            continue
        updated = current.replace(wrong, right)
        if updated == current:
            continue
        current = updated
        applied_pairs.append((wrong, right))
        for extra_ordinal, extra_wrong, extra_right in _query_candidates(snapshot, current):
            if extra_ordinal <= ordinal or extra_ordinal in scheduled:
                continue
            rows_by_ordinal[extra_ordinal] = (extra_wrong, extra_right)
            scheduled.add(extra_ordinal)
            insort(pending, extra_ordinal)

    return current, applied_pairs


def corrections_may_apply(
    text: str,
    corrections: Mapping[str, Any] | None,
    *,
    correction_json_path: str | None = None,
) -> bool:
    if not text or not isinstance(corrections, Mapping) or not corrections:
        return False
    if len(corrections) < _INDEXED_QUERY_MIN_ENTRIES:
        return True
    snapshot = _snapshot_matches_runtime(corrections, correction_json_path)
    if snapshot is None:
        return True
    runtime_index = _runtime_index(snapshot)
    chars = set(str(text))
    if any(token in runtime_index.head1 for token in chars):
        return True
    for idx in range(max(0, len(text) - 1)):
        if text[idx : idx + 2] in runtime_index.head2:
            return True
    return False


def correction_search_gate_enabled(corrections: Mapping[str, Any] | None) -> bool:
    return isinstance(corrections, Mapping) and len(corrections) >= _INDEXED_QUERY_MIN_ENTRIES


__all__ = [
    "INDEXED_QUERY_MIN_ENTRIES",
    "apply_corrections_indexed",
    "correction_search_gate_enabled",
    "corrections_may_apply",
    "correction_db_path",
    "correction_index_token",
    "load_corrections",
    "save_correction",
    "save_corrections",
]
