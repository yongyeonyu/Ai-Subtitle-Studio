from __future__ import annotations

"""Optional native C++ helpers for subtitle correction-dictionary cleanup."""

from collections import OrderedDict
import hashlib
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import threading
from typing import Any

_FALSE_VALUES = {"0", "false", "off", "no"}
_BUILD_LOCK = threading.Lock()
_COMPILED_CACHE_LOCK = threading.Lock()
_COMPILED_CACHE_MAX = 8
_COMPILED_CACHE: "OrderedDict[tuple[str, int], tuple[tuple[tuple[str, str], ...], Any]]" = OrderedDict()


def _env_enabled(name: str, default: str = "1") -> bool:
    value = str(os.environ.get(name, default) or default).strip().lower()
    return value not in _FALSE_VALUES


def _extension_suffix() -> str:
    return str(sysconfig.get_config_var("EXT_SUFFIX") or ".so")


def _source_path() -> Path:
    return Path(__file__).resolve().with_name("native") / "_native_text_cleanup.cpp"


def _extension_path() -> Path:
    return Path(__file__).resolve().with_name(f"_native_text_cleanup{_extension_suffix()}")


def _compiler_path() -> str | None:
    configured = str(os.environ.get("CXX", "") or "").strip()
    if configured:
        return configured
    for name in ("clang++", "c++", "g++"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _compile_native_extension() -> bool:
    if not _env_enabled("AI_SUBTITLE_NATIVE_TEXT_CLEANUP", "1"):
        return False
    if not _env_enabled("AI_SUBTITLE_NATIVE_TEXT_CLEANUP_BUILD", "1"):
        return False

    source = _source_path()
    output = _extension_path()
    if not source.exists():
        return output.exists()
    if output.exists() and output.stat().st_mtime >= source.stat().st_mtime:
        return True

    compiler = _compiler_path()
    include_dir = sysconfig.get_paths().get("include")
    if not compiler or not include_dir:
        return output.exists()

    with _BUILD_LOCK:
        if output.exists() and output.stat().st_mtime >= source.stat().st_mtime:
            return True

        tmp_output = output.with_name(f"{output.name}.tmp")
        cmd = [
            compiler,
            "-O3",
            "-std=c++17",
            "-shared",
            "-fPIC",
            "-I",
            str(include_dir),
            str(source),
            "-o",
            str(tmp_output),
        ]
        if sys.platform == "darwin":
            cmd.extend(["-undefined", "dynamic_lookup"])
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            os.replace(tmp_output, output)
            return True
        except Exception:
            try:
                tmp_output.unlink()
            except Exception:
                pass
            return output.exists()


def _load_native_module():
    if not _env_enabled("AI_SUBTITLE_NATIVE_TEXT_CLEANUP", "1"):
        return None
    _compile_native_extension()
    try:
        return importlib.import_module("core._native_text_cleanup")
    except Exception:
        return None


_native = _load_native_module()

HAS_NATIVE_TEXT_CLEANUP = _native is not None


def native_text_cleanup_enabled() -> bool:
    if _native is None:
        return False
    return _env_enabled("AI_SUBTITLE_NATIVE_TEXT_CLEANUP", "1")


def correction_backend() -> str:
    if not native_text_cleanup_enabled():
        return "python"
    if hasattr(_native, "compile_corrections") and hasattr(_native, "apply_corrections_batch_compiled"):
        return "cpp-db"
    return "cpp"


def _correction_items(corrections: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not isinstance(corrections, dict):
        return ()
    items: list[tuple[str, str]] = []
    for old, new in corrections.items():
        old_text = str(old or "")
        if not old_text:
            continue
        items.append((old_text, str(new or "")))
    return tuple(items)


def _items_digest(items: tuple[tuple[str, str], ...]) -> str:
    digest = hashlib.blake2b(digest_size=16)
    for old, new in items:
        old_bytes = old.encode("utf-8", errors="surrogatepass")
        new_bytes = new.encode("utf-8", errors="surrogatepass")
        digest.update(len(old_bytes).to_bytes(8, "little", signed=False))
        digest.update(old_bytes)
        digest.update(len(new_bytes).to_bytes(8, "little", signed=False))
        digest.update(new_bytes)
    return digest.hexdigest()


def correction_index_token(corrections: dict[str, str] | None) -> tuple[str, int]:
    """Return a stable token for the effective correction DB contents."""

    items = _correction_items(corrections)
    if not items:
        return ("0", 0)
    return (_items_digest(items), len(items))


def _compiled_correction_db(corrections: dict[str, str] | None) -> Any | None:
    if not native_text_cleanup_enabled():
        return None
    if not hasattr(_native, "compile_corrections"):
        return None
    items = _correction_items(corrections)
    if not items:
        return None
    token = (_items_digest(items), len(items))
    with _COMPILED_CACHE_LOCK:
        cached = _COMPILED_CACHE.get(token)
        if cached is not None and cached[0] == items:
            _COMPILED_CACHE.move_to_end(token)
            return cached[1]
    try:
        compiled = _native.compile_corrections(dict(items))
    except Exception:
        return None
    with _COMPILED_CACHE_LOCK:
        _COMPILED_CACHE[token] = (items, compiled)
        _COMPILED_CACHE.move_to_end(token)
        while len(_COMPILED_CACHE) > _COMPILED_CACHE_MAX:
            _COMPILED_CACHE.popitem(last=False)
    return compiled


def clear_correction_index_cache() -> None:
    with _COMPILED_CACHE_LOCK:
        _COMPILED_CACHE.clear()


def _normalize_native_out(native_out: Any) -> tuple[str, list[tuple[str, str]]]:
    updated, applied = native_out
    return str(updated), [
        (str(pair[0]), str(pair[1]))
        for pair in list(applied or [])
        if isinstance(pair, (list, tuple)) and len(pair) >= 2
    ]


def apply_corrections(text: str, corrections: dict[str, str] | None) -> tuple[str, list[tuple[str, str]]] | None:
    if not text or not corrections or not native_text_cleanup_enabled():
        return None
    try:
        compiled = _compiled_correction_db(corrections)
        if compiled is not None and hasattr(_native, "apply_corrections_compiled"):
            return _normalize_native_out(_native.apply_corrections_compiled(str(text), compiled))
        return _normalize_native_out(_native.apply_corrections(str(text), dict(_correction_items(corrections))))
    except Exception:
        return None


def apply_corrections_batch(
    texts: list[str] | tuple[str, ...],
    corrections: dict[str, str] | None,
) -> tuple[list[str], list[list[tuple[str, str]]]] | None:
    if not texts or not corrections or not native_text_cleanup_enabled():
        return None
    try:
        compiled = _compiled_correction_db(corrections)
        if compiled is not None and hasattr(_native, "apply_corrections_batch_compiled"):
            updated, applied = _native.apply_corrections_batch_compiled(list(texts), compiled)
        else:
            updated, applied = _native.apply_corrections_batch(list(texts), dict(_correction_items(corrections)))
        out_texts = [str(item) for item in list(updated or [])]
        out_applied: list[list[tuple[str, str]]] = []
        for batch in list(applied or []):
            items: list[tuple[str, str]] = []
            for pair in list(batch or []):
                if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                    items.append((str(pair[0]), str(pair[1])))
            out_applied.append(items)
        return out_texts, out_applied
    except Exception:
        return None


__all__ = [
    "HAS_NATIVE_TEXT_CLEANUP",
    "apply_corrections",
    "apply_corrections_batch",
    "clear_correction_index_cache",
    "correction_backend",
    "correction_index_token",
    "native_text_cleanup_enabled",
]
