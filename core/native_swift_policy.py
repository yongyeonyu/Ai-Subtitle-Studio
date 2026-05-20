from __future__ import annotations

import atexit
import subprocess
import threading
import time
from typing import Any

from core.native_json import dumps_json_bytes, dumps_json_text, json_default, loads_json, loads_json_output, write_jsonl_line
from core.native_swift_subtitle import find_native_cli_path
from core.runtime.config import IS_MAC
from core.native_macos_acceleration import mac_native_swift_policy_experimental_enabled
from core.runtime.stage_metrics import _elapsed_ms, record_native_bridge_metric
from core.runtime.setting_utils import KOREAN_FALSE_VALUES, env_bool as _env_bool, setting_bool as _setting_bool

_WORKER: subprocess.Popen | None = None
_WORKER_LOCK = threading.Lock()
_CACHED_LORA_INDEX_IDS: set[str] = set()


def _experimental_policy_enabled(settings: dict[str, Any] | None) -> bool:
    explicit = _env_bool("AI_SUBTITLE_STUDIO_SWIFT_POLICY_EXPERIMENTAL")
    if explicit is not None:
        return explicit
    return mac_native_swift_policy_experimental_enabled(settings)


def _enabled(settings: dict[str, Any] | None, setting_key: str, env_key: str, default: bool = True) -> bool:
    if not IS_MAC:
        return False
    global_env = _env_bool("AI_SUBTITLE_STUDIO_SWIFT_POLICY")
    if global_env is False:
        return False
    local_env = _env_bool(env_key)
    if not _experimental_policy_enabled(settings):
        return False
    if local_env is not None:
        return local_env
    if global_env is not None:
        return global_env
    return _setting_bool(
        (settings or {}).get(setting_key),
        default,
        false_values=KOREAN_FALSE_VALUES,
        false_only_strings=True,
        empty_is_default=False,
    )


def _start_worker(cli: Any) -> subprocess.Popen | None:
    global _WORKER
    if _WORKER is not None and _WORKER.poll() is None:
        return _WORKER
    try:
        _WORKER = subprocess.Popen(
            [str(cli), "native-policy-jsonl-worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
    except Exception:
        _WORKER = None
    return _WORKER


def _request_worker(task: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    cli = find_native_cli_path()
    if cli is None:
        return None
    request = dict(payload)
    request["task"] = task
    encode_started = time.perf_counter()
    try:
        encoded = dumps_json_text(request, compact=True, default=json_default)
    except Exception:
        return None
    encode_ms = _elapsed_ms(encode_started)
    payload_bytes = len(encoded.encode("utf-8"))
    started = time.perf_counter()
    decode_ms = 0.0
    ok = False
    with _WORKER_LOCK:
        worker = _start_worker(cli)
        if worker is None or worker.stdin is None or worker.stdout is None:
            record_native_bridge_metric(
                f"policy-jsonl:{task}",
                payload_bytes=payload_bytes,
                encode_ms=encode_ms,
                native_ms=_elapsed_ms(started),
                decode_ms=decode_ms,
                ok=False,
            )
            return None
        try:
            write_jsonl_line(worker.stdin, encoded)
            worker.stdin.flush()
            line = worker.stdout.readline()
            if not line:
                _stop_worker()
                return None
            decode_started = time.perf_counter()
            decoded = loads_json(line)
            decode_ms = _elapsed_ms(decode_started)
            if not isinstance(decoded, dict) or decoded.get("error"):
                return None
            ok = True
            return decoded
        except Exception:
            _stop_worker()
            return None
        finally:
            record_native_bridge_metric(
                f"policy-jsonl:{task}",
                payload_bytes=payload_bytes,
                encode_ms=encode_ms,
                native_ms=_elapsed_ms(started),
                decode_ms=decode_ms,
                ok=ok,
            )


def _request_one_shot(command: str, payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any] | None:
    cli = find_native_cli_path()
    if cli is None:
        return None
    encode_ms = 0.0
    payload_bytes = 0
    started = time.perf_counter()
    decode_ms = 0.0
    ok = False
    try:
        encode_started = time.perf_counter()
        encoded = dumps_json_bytes(payload, compact=True, default=json_default)
        encode_ms = _elapsed_ms(encode_started)
        payload_bytes = len(encoded)
        proc = subprocess.run(
            [str(cli), command],
            input=encoded,
            check=True,
            capture_output=True,
            timeout=timeout,
        )
        decode_started = time.perf_counter()
        decoded = loads_json_output(proc.stdout, default={})
        decode_ms = _elapsed_ms(decode_started)
        ok = isinstance(decoded, dict) and not bool(decoded.get("error"))
        return decoded if ok else None
    except Exception:
        return None
    finally:
        record_native_bridge_metric(
            f"policy:{command}",
            payload_bytes=payload_bytes,
            encode_ms=encode_ms,
            native_ms=_elapsed_ms(started),
            decode_ms=decode_ms,
            ok=ok,
        )


def build_llm_candidate_options_via_swift(
    text: str,
    threshold: int,
    rules: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    if not _enabled(
        settings,
        "native_swift_llm_candidate_policy_enabled",
        "AI_SUBTITLE_STUDIO_SWIFT_LLM_POLICY",
        default=False,
    ):
        return None
    decoded = _request_worker(
        "llm_candidates",
        {
            "text": text,
            "threshold": threshold,
            "rules": rules or {},
            "settings": settings or {},
        },
    )
    if decoded is None:
        decoded = _request_one_shot(
            "native-policy-llm-candidates-json",
            {"text": text, "threshold": threshold, "rules": rules or {}, "settings": settings or {}},
        )
    candidates = decoded.get("candidates") if isinstance(decoded, dict) else None
    if not isinstance(candidates, list):
        return None
    out: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            return None
        chunks = item.get("chunks")
        if not isinstance(chunks, list):
            return None
        row = dict(item)
        row["chunks"] = [str(chunk) for chunk in chunks if str(chunk or "").strip()]
        out.append(row)
    return out


def build_llm_candidate_options_batch_via_swift(
    items: list[dict[str, Any]],
    *,
    settings: dict[str, Any] | None = None,
) -> list[list[dict[str, Any]]] | None:
    if not items:
        return []
    if not _enabled(
        settings,
        "native_swift_llm_candidate_policy_enabled",
        "AI_SUBTITLE_STUDIO_SWIFT_LLM_POLICY",
        default=False,
    ):
        return None
    payload = {"items": items}
    decoded = _request_worker("llm_candidates_batch", payload)
    if decoded is None:
        decoded = _request_one_shot("native-policy-llm-candidates-batch-json", payload, timeout=max(10.0, len(items) * 0.02))
    rows = decoded.get("results") if isinstance(decoded, dict) else None
    if not isinstance(rows, list) or len(rows) != len(items):
        return None
    out: list[list[dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        candidates = row.get("candidates")
        if not isinstance(candidates, list):
            return None
        parsed: list[dict[str, Any]] = []
        for item in candidates:
            if not isinstance(item, dict) or not isinstance(item.get("chunks"), list):
                return None
            candidate = dict(item)
            candidate["chunks"] = [str(chunk) for chunk in list(candidate.get("chunks") or []) if str(chunk or "").strip()]
            parsed.append(candidate)
        out.append(parsed)
    return out


def rerank_subtitle_candidates_via_swift(
    original_text: Any,
    candidate_lists: list[list[str]],
    settings: dict[str, Any] | None,
    profile: dict[str, Any] | None,
) -> tuple[list[str], dict[str, Any]] | None:
    if not _enabled(settings, "native_swift_deep_policy_enabled", "AI_SUBTITLE_STUDIO_SWIFT_DEEP_POLICY", default=False):
        return None
    decoded = _request_worker(
        "deep_rerank",
        {
            "original_text": original_text,
            "candidate_lists": candidate_lists,
            "settings": settings or {},
            "profile": profile or {},
        },
    )
    if decoded is None:
        decoded = _request_one_shot(
            "native-policy-deep-rerank-json",
            {
                "original_text": original_text,
                "candidate_lists": candidate_lists,
                "settings": settings or {},
                "profile": profile or {},
            },
        )
    if not isinstance(decoded, dict) or not isinstance(decoded.get("chunks"), list):
        return None
    chunks = [str(chunk) for chunk in list(decoded.get("chunks") or []) if str(chunk or "").strip()]
    metadata = decoded.get("metadata") if isinstance(decoded.get("metadata"), dict) else {}
    metadata = dict(metadata or {})
    if metadata.get("model"):
        metadata["model"] = str(metadata["model"])
    return chunks, metadata


def rerank_subtitle_candidates_batch_via_swift(
    items: list[dict[str, Any]],
    *,
    settings: dict[str, Any] | None = None,
) -> list[tuple[list[str], dict[str, Any]]] | None:
    if not items:
        return []
    if not _enabled(settings, "native_swift_deep_policy_enabled", "AI_SUBTITLE_STUDIO_SWIFT_DEEP_POLICY", default=False):
        return None
    payload = {"items": items}
    decoded = _request_worker("deep_rerank_batch", payload)
    if decoded is None:
        decoded = _request_one_shot("native-policy-deep-rerank-batch-json", payload, timeout=max(10.0, len(items) * 0.02))
    rows = decoded.get("results") if isinstance(decoded, dict) else None
    if not isinstance(rows, list) or len(rows) != len(items):
        return None
    out: list[tuple[list[str], dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("chunks"), list):
            return None
        chunks = [str(chunk) for chunk in list(row.get("chunks") or []) if str(chunk or "").strip()]
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        out.append((chunks, dict(metadata or {})))
    return out


def _lora_index_id(index: dict[str, Any]) -> str:
    return "|".join(
        str(item or "")
        for item in (
            index.get("source_signature"),
            index.get("updated_at"),
            index.get("doc_count"),
            index.get("score_model"),
        )
    )


def _ensure_lora_index_cached(index: dict[str, Any], index_id: str) -> bool:
    if index_id in _CACHED_LORA_INDEX_IDS:
        return True
    decoded = _request_worker("lora_index_put", {"index_id": index_id, "index": index})
    if not decoded or not decoded.get("ok"):
        return False
    _CACHED_LORA_INDEX_IDS.add(index_id)
    return True


def score_lora_docs_via_swift(
    index: dict[str, Any],
    query: str,
    *,
    media_path: str = "",
    media_id: str = "",
    query_facets: dict[str, Any] | None = None,
    kinds: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
    quality_buckets: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
    query_vector: dict[str, float] | None = None,
    query_terms: dict[str, int] | None = None,
    media_lookup_keys: list[str] | None = None,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    if not _enabled(
        settings,
        "native_swift_lora_scoring_enabled",
        "AI_SUBTITLE_STUDIO_SWIFT_LORA_SCORING",
        default=False,
    ):
        return None
    docs = list((index or {}).get("docs") or [])
    min_docs = int((settings or {}).get("native_swift_lora_scoring_min_docs", 32) or 32)
    if len(docs) < max(1, min_docs):
        return None
    payload = {
        "query": query,
        "media_path": media_path,
        "media_id": media_id,
        "query_facets": query_facets or {},
        "kinds": sorted(str(kind) for kind in kinds) if kinds is not None else [],
        "quality_buckets": sorted(str(bucket) for bucket in quality_buckets) if quality_buckets is not None else [],
        "query_vector": query_vector or {},
        "query_terms": query_terms or {},
        "media_lookup_keys": media_lookup_keys or [],
    }
    index_id = _lora_index_id(index)
    decoded: dict[str, Any] | None = None
    if index_id and _ensure_lora_index_cached(index, index_id):
        decoded = _request_worker("lora_score_cached", {**payload, "index_id": index_id})
    if decoded is None:
        decoded = _request_one_shot("native-policy-lora-score-json", {**payload, "index": index}, timeout=60.0)
    items = decoded.get("items") if isinstance(decoded, dict) else None
    if not isinstance(items, list):
        return None
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        out.append(dict(item))
    return out


def _stop_worker() -> None:
    global _WORKER
    _CACHED_LORA_INDEX_IDS.clear()
    worker = _WORKER
    _WORKER = None
    if worker is None:
        return
    try:
        if worker.stdin is not None:
            worker.stdin.close()
    except Exception:
        pass
    try:
        worker.terminate()
    except Exception:
        pass


def trim_native_policy_worker_cache() -> bool:
    with _WORKER_LOCK:
        worker = _WORKER
        if worker is None or worker.poll() is not None:
            _CACHED_LORA_INDEX_IDS.clear()
            return False
    decoded = _request_worker("lora_index_clear", {})
    _CACHED_LORA_INDEX_IDS.clear()
    return bool(decoded and decoded.get("ok"))


atexit.register(_stop_worker)


__all__ = [
    "build_llm_candidate_options_batch_via_swift",
    "build_llm_candidate_options_via_swift",
    "rerank_subtitle_candidates_batch_via_swift",
    "rerank_subtitle_candidates_via_swift",
    "score_lora_docs_via_swift",
    "trim_native_policy_worker_cache",
]
