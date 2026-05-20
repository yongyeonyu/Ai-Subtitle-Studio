from __future__ import annotations

import gc
import heapq
import os
import sys
import tempfile
import time
import tracemalloc
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator

from core.performance import atomic_write_json, current_resource_snapshot
from core.runtime import config
from core.runtime.memory_trim_summary import record_stage_trim_summary
from core.runtime.stage_metrics import classify_resource_label, record_stage_done

_DISK_USAGE_CACHE_MAX_AGE_SEC = 15.0
_RUNTIME_DISK_USAGE_CACHE: dict[tuple[str, ...], tuple[float, dict[str, Any]]] = {}
_RUNTIME_DISK_ROOT_INDEX_MAX_AGE_SEC = 90.0
_RUNTIME_DISK_ROOT_INDEX: dict[str, dict[str, Any]] = {}
_DiskFileEntry = tuple[float, int, str]
_RSS_PSUTIL_PROCESS: Any = None
_RSS_PSUTIL_UNAVAILABLE = False
_RUSAGE_VALUE_IS_KB = bool(os.name == "posix" and getattr(os, "uname", lambda: None)().sysname.lower() != "darwin")
_RUNTIME_TRIM_TARGETS = (
    ("core.media_info", "clear_media_probe_cache_memory"),
    ("core.project.project_io", "clear_project_file_cache"),
    ("core.personalization.lora_vector_retriever", "clear_lora_retrieval_caches"),
    ("core.native_macos_memory", "clear_native_memory_snapshot_cache"),
    ("core.native_swift_policy", "trim_native_policy_worker_cache"),
)
_RUNTIME_TRIM_CALLABLES: list[tuple[str, Callable[[], Any]]] | None = None
_NATIVE_PRUNE_CALLABLE_UNSET = object()
_NATIVE_PRUNE_CALLABLE: Callable[..., dict[str, Any] | None] | None | object = _NATIVE_PRUNE_CALLABLE_UNSET


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)


def _trim_failure_record(action: str, exc: BaseException) -> dict[str, str]:
    return {
        "action": str(action or "unknown"),
        "error_type": type(exc).__name__,
        "message": str(exc)[:180],
    }


def _coerce_float(value: object, default: float, *, min_value: float | None = None, max_value: float | None = None) -> float:
    try:
        value_float = float(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None and value_float < min_value:
        return min_value
    if max_value is not None and value_float > max_value:
        return max_value
    return value_float


def process_rss_bytes() -> int:
    global _RSS_PSUTIL_PROCESS, _RSS_PSUTIL_UNAVAILABLE
    if not _RSS_PSUTIL_UNAVAILABLE:
        try:
            import psutil  # type: ignore
        except ImportError:
            _RSS_PSUTIL_UNAVAILABLE = True
        else:
            try:
                if _RSS_PSUTIL_PROCESS is None:
                    _RSS_PSUTIL_PROCESS = psutil.Process(os.getpid())
                return max(0, int(_RSS_PSUTIL_PROCESS.memory_info().rss))
            except (OSError, RuntimeError, AttributeError, TypeError, psutil.Error):
                _RSS_PSUTIL_PROCESS = None

    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss or 0)
        if value <= 0:
            return 0
        if _RUSAGE_VALUE_IS_KB:
            return value * 1024
        return value
    except (ImportError, OSError, RuntimeError, AttributeError, TypeError, ValueError):
        return 0


def runtime_memory_monitor_dir() -> Path:
    path = Path(config.OUTPUT_DIR) / "memory_monitor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_runtime_disk_cache_paths() -> list[Path]:
    return list(_default_runtime_disk_cache_paths_cached(
        str(config.OUTPUT_DIR),
        str(config.DATASET_DIR),
        tempfile.gettempdir(),
    ))


@lru_cache(maxsize=8)
def _default_runtime_disk_cache_paths_cached(
    output_dir_text: str,
    dataset_dir_text: str,
    temp_dir_text: str,
) -> tuple[Path, ...]:
    output_dir = Path(output_dir_text)
    dataset_dir = Path(dataset_dir_text)
    temp_dir = Path(temp_dir_text)
    paths = [
        dataset_dir / "video_preview_cache",
        output_dir / ".media_probe_cache",
        output_dir / "cut_boundary_cache",
        output_dir / "waveform_cache",
        output_dir / "_analysis_cache",
        output_dir / "_audio_fingerprint",
        temp_dir / "ai_subtitle_studio_waveform_cache",
        temp_dir / "ai_subtitle_studio_roughcut",
        temp_dir / "ai_subtitle_studio_roughcut_thumbnails",
    ]
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return tuple(deduped)


def runtime_disk_cache_usage(paths: list[str | Path] | None = None) -> dict[str, Any]:
    roots = [Path(p) for p in (paths or default_runtime_disk_cache_paths())]
    cache_key = tuple(str(root) for root in roots)
    cached = _RUNTIME_DISK_USAGE_CACHE.get(cache_key)
    now = time.time()
    if cached is not None and (now - cached[0]) < _DISK_USAGE_CACHE_MAX_AGE_SEC:
        return dict(cached[1])
    total_bytes = 0
    file_count = 0
    directories: list[dict[str, Any]] = []
    for root in roots:
        root_entry = _runtime_disk_root_entry(root, now=now)
        size = int(root_entry.get("bytes", 0) or 0)
        files = int(root_entry.get("files", 0) or 0)
        total_bytes += size
        file_count += files
        directories.append({
            "path": str(root),
            "exists": bool(root_entry.get("exists", False)),
            "bytes": size,
            "files": files,
        })
    result = {
        "paths": [str(root) for root in roots],
        "total_bytes": total_bytes,
        "total_gb": round(total_bytes / float(1024 ** 3), 4),
        "file_count": file_count,
        "directories": directories,
    }
    _RUNTIME_DISK_USAGE_CACHE[cache_key] = (now, result)
    return dict(result)


def _directory_usage(root: Path) -> tuple[int, int]:
    total_bytes = 0
    file_count = 0
    for _mtime, size, _path in _iter_directory_file_entries(root):
        total_bytes += size
        file_count += 1
    return total_bytes, file_count


def _iter_directory_file_entries(root: Path) -> Iterator[_DiskFileEntry]:
    stack = [str(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    yield (
                        float(stat.st_mtime or 0.0),
                        max(0, int(stat.st_size or 0)),
                        entry.path,
                    )
        except OSError:
            continue


def _iter_runtime_cache_file_entries(roots: list[Path]) -> Iterator[_DiskFileEntry]:
    for root in roots:
        root_entry = _runtime_disk_root_entry(root)
        if not bool(root_entry.get("exists", False)):
            continue
        if bool(root_entry.get("is_file", False)):
            for path_text, (mtime, size) in (root_entry.get("entries") or {}).items():
                yield (float(mtime or 0.0), max(0, int(size or 0)), path_text)
            continue
        for path_text, (mtime, size) in (root_entry.get("entries") or {}).items():
            yield (float(mtime or 0.0), max(0, int(size or 0)), path_text)


def _runtime_cache_total_bytes(roots: list[Path]) -> int:
    total_bytes = 0
    for root in roots:
        total_bytes += int(_runtime_disk_root_entry(root).get("bytes", 0) or 0)
    return total_bytes


def _invalidate_runtime_disk_usage_cache(roots: list[Path]) -> None:
    root_keys: set[str] = set()
    for root in roots:
        root_keys.add(str(root))
        root_keys.add(_expanded_resolved_path_text(str(root)))
    for cache_key in list(_RUNTIME_DISK_USAGE_CACHE.keys()):
        if any(part in root_keys for part in cache_key):
            _RUNTIME_DISK_USAGE_CACHE.pop(cache_key, None)


def _invalidate_runtime_disk_root_index(roots: list[Path]) -> None:
    for root in roots:
        _RUNTIME_DISK_ROOT_INDEX.pop(_runtime_disk_root_key(root), None)


def _runtime_disk_root_key(root: Path) -> str:
    return _expanded_resolved_path_text(str(root))


@lru_cache(maxsize=1024)
def _expanded_resolved_path_text(path_text: str) -> str:
    path = Path(path_text).expanduser()
    try:
        return str(path.resolve(strict=False))
    except OSError:
        return str(path)


def _scan_runtime_disk_root(root: Path, *, now: float | None = None) -> dict[str, Any]:
    root = Path(root).expanduser()
    now = float(now if now is not None else time.time())
    key = _runtime_disk_root_key(root)
    if not root.exists():
        entry = {
            "root": str(root),
            "exists": False,
            "bytes": 0,
            "files": 0,
            "entries": {},
            "is_file": False,
            "scanned_at": now,
        }
        _RUNTIME_DISK_ROOT_INDEX[key] = entry
        return entry
    if root.is_file():
        try:
            stat = root.stat()
        except OSError:
            entry = {
                "root": str(root),
                "exists": False,
                "bytes": 0,
                "files": 0,
                "entries": {},
                "is_file": False,
                "scanned_at": now,
            }
            _RUNTIME_DISK_ROOT_INDEX[key] = entry
            return entry
        path_text = str(root)
        entry = {
            "root": path_text,
            "exists": True,
            "bytes": max(0, int(stat.st_size or 0)),
            "files": 1,
            "entries": {path_text: (float(stat.st_mtime or 0.0), max(0, int(stat.st_size or 0)))},
            "is_file": True,
            "scanned_at": now,
        }
        _RUNTIME_DISK_ROOT_INDEX[key] = entry
        return entry
    file_entries: dict[str, tuple[float, int]] = {}
    total_bytes = 0
    file_count = 0
    for mtime, size, path_text in _iter_directory_file_entries(root):
        file_entries[path_text] = (mtime, size)
        total_bytes += size
        file_count += 1
    entry = {
        "root": str(root),
        "exists": True,
        "bytes": total_bytes,
        "files": file_count,
        "entries": file_entries,
        "is_file": False,
        "scanned_at": now,
    }
    _RUNTIME_DISK_ROOT_INDEX[key] = entry
    return entry


def _runtime_disk_root_entry(
    root: Path,
    *,
    now: float | None = None,
    force_rescan: bool = False,
) -> dict[str, Any]:
    key = _runtime_disk_root_key(root)
    cached = _RUNTIME_DISK_ROOT_INDEX.get(key)
    now = float(now if now is not None else time.time())
    if (
        force_rescan
        or cached is None
        or (now - float(cached.get("scanned_at", 0.0) or 0.0)) >= _RUNTIME_DISK_ROOT_INDEX_MAX_AGE_SEC
    ):
        return _scan_runtime_disk_root(root, now=now)
    return cached


def _runtime_cache_root_for_path(path: Path, roots: list[Path] | None = None) -> Path | None:
    candidates = roots or default_runtime_disk_cache_paths()
    target = _expanded_resolved_path_text(str(path))
    for root in candidates:
        root_text = _expanded_resolved_path_text(str(root))
        if target == root_text or target.startswith(root_text + os.sep):
            return root
    return None


def _runtime_root_entries(root_entry: dict[str, Any]) -> dict[str, tuple[float, int]]:
    entries = root_entry.get("entries")
    if isinstance(entries, dict):
        return entries
    fresh: dict[str, tuple[float, int]] = {}
    root_entry["entries"] = fresh
    return fresh


def register_runtime_cache_path(
    path: str | Path,
    *,
    root: str | Path | None = None,
    size_bytes: int | None = None,
) -> None:
    target = Path(path).expanduser()
    root_path = Path(root).expanduser() if root is not None else _runtime_cache_root_for_path(target)
    if root_path is None:
        return
    now = time.time()
    root_entry = _runtime_disk_root_entry(root_path, now=now)
    path_text = str(target)
    try:
        stat = target.stat()
        new_size = max(0, int(size_bytes if size_bytes is not None else (stat.st_size or 0)))
        new_mtime = float(stat.st_mtime or now)
    except OSError:
        return
    old_mtime, old_size = (0.0, 0)
    entries = _runtime_root_entries(root_entry)
    old_entry = entries.get(path_text)
    if old_entry is not None:
        old_mtime, old_size = old_entry
    if bool(root_entry.get("is_file", False)):
        root_entry["exists"] = True
        root_entry["bytes"] = new_size
        root_entry["files"] = 1
        root_entry["entries"] = {path_text: (new_mtime, new_size)}
        root_entry["scanned_at"] = now
        _invalidate_runtime_disk_usage_cache([root_path])
        return
    if path_text not in entries:
        root_entry["files"] = int(root_entry.get("files", 0) or 0) + 1
    root_entry["bytes"] = int(root_entry.get("bytes", 0) or 0) - int(old_size or 0) + new_size
    entries[path_text] = (new_mtime, new_size)
    root_entry["entries"] = entries
    root_entry["exists"] = True
    root_entry["scanned_at"] = now
    _RUNTIME_DISK_ROOT_INDEX[_runtime_disk_root_key(root_path)] = root_entry
    _invalidate_runtime_disk_usage_cache([root_path])


def unregister_runtime_cache_path(
    path: str | Path,
    *,
    root: str | Path | None = None,
    size_bytes: int | None = None,
) -> None:
    target = Path(path).expanduser()
    root_path = Path(root).expanduser() if root is not None else _runtime_cache_root_for_path(target)
    if root_path is None:
        return
    root_entry = _runtime_disk_root_entry(root_path)
    path_text = str(target)
    entries = _runtime_root_entries(root_entry)
    old_entry = entries.pop(path_text, None)
    old_size = int(old_entry[1] if old_entry is not None else (size_bytes or 0))
    if bool(root_entry.get("is_file", False)):
        root_entry["exists"] = False
        root_entry["bytes"] = 0
        root_entry["files"] = 0
        root_entry["entries"] = {}
        root_entry["scanned_at"] = time.time()
        _RUNTIME_DISK_ROOT_INDEX[_runtime_disk_root_key(root_path)] = root_entry
        _invalidate_runtime_disk_usage_cache([root_path])
        return
    if old_entry is None and size_bytes is None:
        _invalidate_runtime_disk_usage_cache([root_path])
        return
    root_entry["entries"] = entries
    root_entry["bytes"] = max(0, int(root_entry.get("bytes", 0) or 0) - old_size)
    if old_entry is not None:
        root_entry["files"] = max(0, int(root_entry.get("files", 0) or 0) - 1)
    root_entry["scanned_at"] = time.time()
    _RUNTIME_DISK_ROOT_INDEX[_runtime_disk_root_key(root_path)] = root_entry
    _invalidate_runtime_disk_usage_cache([root_path])


def runtime_disk_cache_budget_bytes(settings: dict[str, Any] | None = None) -> int:
    data = dict(settings or {})
    default_gb = float(getattr(config, "DEFAULT_ADV_SETTINGS", {}).get("runtime_memory_disk_cache_budget_gb", 12.0) or 12.0)
    total_gb = float(data.get("runtime_memory_disk_cache_budget_gb", default_gb) or default_gb)
    return max(256 * 1024 * 1024, int(total_gb * (1024 ** 3)))


def scaled_runtime_cache_budget_bytes(
    *,
    ratio: float,
    minimum_bytes: int,
    maximum_bytes: int,
    settings: dict[str, Any] | None = None,
) -> int:
    scaled = int(runtime_disk_cache_budget_bytes(settings) * max(0.0, float(ratio or 0.0)))
    return max(int(minimum_bytes), min(int(maximum_bytes), scaled))


def prune_runtime_disk_caches(
    *,
    paths: list[str | Path] | None = None,
    target_total_bytes: int,
) -> dict[str, Any]:
    target_total_bytes = max(0, int(target_total_bytes or 0))
    roots = [Path(p) for p in (paths or default_runtime_disk_cache_paths())]
    native_result = _prune_runtime_disk_caches_native(roots, target_total_bytes=target_total_bytes)
    if native_result is not None:
        _invalidate_runtime_disk_root_index(roots)
        _invalidate_runtime_disk_usage_cache(roots)
        return native_result

    total_bytes = _runtime_cache_total_bytes(roots)
    if total_bytes <= target_total_bytes:
        return {
            "removed_files": 0,
            "removed_bytes": 0,
            "remaining_bytes": max(0, total_bytes),
            "target_total_bytes": target_total_bytes,
        }
    file_heap: list[tuple[float, str, str, int]] = []
    total_bytes = 0
    for mtime, size, path in _iter_runtime_cache_file_entries(roots):
        total_bytes += size
        file_heap.append((mtime, os.path.basename(path), path, size))
    heapq.heapify(file_heap)

    removed_files = 0
    removed_bytes = 0
    if total_bytes > target_total_bytes:
        while file_heap and total_bytes > target_total_bytes:
            _mtime, _basename, path, size = heapq.heappop(file_heap)
            try:
                os.unlink(path)
            except OSError:
                continue
            total_bytes -= size
            removed_files += 1
            removed_bytes += size
            unregister_runtime_cache_path(path, size_bytes=size)
    _invalidate_runtime_disk_usage_cache(roots)
    return {
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "remaining_bytes": max(0, total_bytes),
        "target_total_bytes": target_total_bytes,
    }


def _prune_runtime_disk_caches_native(
    roots: list[Path],
    *,
    target_total_bytes: int,
) -> dict[str, Any] | None:
    func = _native_prune_callable()
    if func is None:
        return None
    try:
        return func(
            roots,
            target_total_bytes=target_total_bytes,
        )
    except Exception:
        return None


def _native_prune_callable() -> Callable[..., dict[str, Any] | None] | None:
    global _NATIVE_PRUNE_CALLABLE
    if _NATIVE_PRUNE_CALLABLE is not _NATIVE_PRUNE_CALLABLE_UNSET:
        return _NATIVE_PRUNE_CALLABLE
    try:
        from core.native_swift_runtime_cache import prune_runtime_disk_caches_via_swift
    except ImportError:
        _NATIVE_PRUNE_CALLABLE = None
        return None
    _NATIVE_PRUNE_CALLABLE = prune_runtime_disk_caches_via_swift
    return prune_runtime_disk_caches_via_swift


def _runtime_trim_callables() -> list[tuple[str, Callable[[], Any]]]:
    global _RUNTIME_TRIM_CALLABLES
    if _RUNTIME_TRIM_CALLABLES is not None:
        return _RUNTIME_TRIM_CALLABLES
    resolved: list[tuple[str, Callable[[], Any]]] = []
    for module_name, func_name in _RUNTIME_TRIM_TARGETS:
        try:
            module = __import__(module_name, fromlist=[func_name])
            func = getattr(module, func_name, None)
        except (ImportError, AttributeError):
            continue
        if callable(func):
            resolved.append((f"{module_name}.{func_name}", func))
    _RUNTIME_TRIM_CALLABLES = resolved
    return resolved


def trim_runtime_memory_caches(*, stage: str = "warning", include_gpu: bool = False) -> dict[str, Any]:
    trim_started = time.perf_counter()
    stage_text = str(stage or "warning").strip().lower()
    actions: list[str] = []
    action_timings: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    settings: dict[str, Any] = {}
    try:
        from core.settings import load_settings

        settings = dict(load_settings() or {})
    except Exception as exc:
        failures.append(_trim_failure_record("core.settings.load_settings", exc))
        settings = {}
    for action_name, func in _runtime_trim_callables():
        action_started = time.perf_counter()
        try:
            func()
            actions.append(action_name)
            action_timings.append({
                "action": action_name,
                "elapsed_ms": _elapsed_ms(action_started),
                "ok": True,
            })
        except Exception as exc:
            action_timings.append({
                "action": action_name,
                "elapsed_ms": _elapsed_ms(action_started),
                "ok": False,
            })
            failures.append(_trim_failure_record(action_name, exc))
            continue
    gc_started = time.perf_counter()
    try:
        gc.collect()
        actions.append("gc.collect")
        action_timings.append({
            "action": "gc.collect",
            "elapsed_ms": _elapsed_ms(gc_started),
            "ok": True,
        })
    except Exception as exc:
        action_timings.append({
            "action": "gc.collect",
            "elapsed_ms": _elapsed_ms(gc_started),
            "ok": False,
        })
        failures.append(_trim_failure_record("gc.collect", exc))
    relief_started = time.perf_counter()
    try:
        from core.native_macos_memory import native_allocator_pressure_relief

        relief = native_allocator_pressure_relief(settings, stage=stage_text)
        if relief.get("ok"):
            released_mb = round(float(relief.get("released_bytes", 0) or 0) / float(1024 ** 2), 2)
            actions.append(f"macos.malloc_zone_pressure_relief:{released_mb}MB")
            action_timings.append({
                "action": "macos.malloc_zone_pressure_relief",
                "elapsed_ms": _elapsed_ms(relief_started),
                "ok": True,
            })
        else:
            action_timings.append({
                "action": "macos.malloc_zone_pressure_relief",
                "elapsed_ms": _elapsed_ms(relief_started),
                "ok": False,
            })
    except Exception as exc:
        action_timings.append({
            "action": "macos.malloc_zone_pressure_relief",
            "elapsed_ms": _elapsed_ms(relief_started),
            "ok": False,
        })
        failures.append(_trim_failure_record("macos.malloc_zone_pressure_relief", exc))
    if include_gpu:
        torch_module = sys.modules.get("torch")
        if torch_module is not None:
            mps_started = time.perf_counter()
            try:
                from core.audio.torch_acceleration import allow_mps_empty_cache

                mps = getattr(torch_module, "mps", None)
                empty_cache = getattr(mps, "empty_cache", None)
                if allow_mps_empty_cache() and callable(empty_cache):
                    empty_cache()
                    actions.append("torch.mps.empty_cache")
                    action_timings.append({
                        "action": "torch.mps.empty_cache",
                        "elapsed_ms": _elapsed_ms(mps_started),
                        "ok": True,
                    })
            except Exception as exc:
                action_timings.append({
                    "action": "torch.mps.empty_cache",
                    "elapsed_ms": _elapsed_ms(mps_started),
                    "ok": False,
                })
                failures.append(_trim_failure_record("torch.mps.empty_cache", exc))
            cuda_started = time.perf_counter()
            try:
                cuda = getattr(torch_module, "cuda", None)
                if cuda is not None and callable(getattr(cuda, "is_available", None)) and cuda.is_available():
                    empty_cache = getattr(cuda, "empty_cache", None)
                    if callable(empty_cache):
                        empty_cache()
                        actions.append("torch.cuda.empty_cache")
                        action_timings.append({
                            "action": "torch.cuda.empty_cache",
                            "elapsed_ms": _elapsed_ms(cuda_started),
                            "ok": True,
                        })
            except Exception as exc:
                action_timings.append({
                    "action": "torch.cuda.empty_cache",
                    "elapsed_ms": _elapsed_ms(cuda_started),
                    "ok": False,
                })
                failures.append(_trim_failure_record("torch.cuda.empty_cache", exc))
        mlx_core = sys.modules.get("mlx.core")
        if mlx_core is not None:
            mlx_started = time.perf_counter()
            try:
                clear_cache = getattr(mlx_core, "clear_cache", None)
                if callable(clear_cache):
                    clear_cache()
                    actions.append("mlx.core.clear_cache")
                    action_timings.append({
                        "action": "mlx.core.clear_cache",
                        "elapsed_ms": _elapsed_ms(mlx_started),
                        "ok": True,
                    })
            except Exception as exc:
                action_timings.append({
                    "action": "mlx.core.clear_cache",
                    "elapsed_ms": _elapsed_ms(mlx_started),
                    "ok": False,
                })
                failures.append(_trim_failure_record("mlx.core.clear_cache", exc))
    return {
        "stage": stage_text,
        "actions": actions,
        "elapsed_ms": _elapsed_ms(trim_started),
        "action_timings": action_timings,
        "failures": failures,
    }


class SubtitleGenerationMemoryGuard:
    """Stage-aware memory guard for the subtitle generation pipeline.

    The app already has a UI-level memory monitor. This guard is intentionally
    scoped to long-running generation stages so heavy STT/VAD/LLM phases can
    publish snapshots and trim caches without waiting for the global timer.
    """

    def __init__(
        self,
        *,
        settings: dict[str, Any] | None = None,
        logger: Any = None,
        diagnostics_dir: str | Path | None = None,
        cache_paths: list[str | Path] | None = None,
        pressure_callback: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self.settings = dict(settings or {})
        self.enabled = bool(self.settings.get("subtitle_generation_memory_guard_enabled", True))
        self.logger = logger
        self.manager = RuntimeMemoryManager(
            settings=self.settings,
            logger=logger,
            diagnostics_dir=diagnostics_dir,
            cache_paths=cache_paths,
        )
        self.manager.register_trim_callback("subtitle_generation", self._handle_pressure)
        self.pressure_callback = pressure_callback
        interval_ms = float(self.settings.get("subtitle_generation_memory_checkpoint_interval_ms", 3000) or 3000)
        self.min_interval_sec = max(0.25, interval_ms / 1000.0)
        self.gpu_trim_cooldown_sec = max(
            2.0,
            float(self.settings.get("subtitle_generation_gpu_trim_cooldown_sec", 8.0) or 8.0),
        )
        self.stage = "idle"
        self._last_checkpoint_at = 0.0
        self._last_gpu_trim_at = 0.0
        self._last_notice_key = ""
        self._last_snapshot: dict[str, Any] = {}
        self._stage_trim_summary: dict[str, Any] = {}

    def checkpoint(
        self,
        stage: str,
        *,
        include_gpu: bool = False,
        cleanup: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}
        now = time.time()
        if not force and (now - self._last_checkpoint_at) < self.min_interval_sec:
            return dict(self._last_snapshot)
        self.stage = str(stage or "unknown")
        self._last_checkpoint_at = now
        snapshot = self.manager.poll()
        snapshot["subtitle_generation_stage"] = self.stage
        snapshot["checkpoint_include_gpu"] = bool(include_gpu)
        snapshot["checkpoint_cleanup"] = bool(cleanup)

        pressure_stage = str(snapshot.get("pressure_stage", "normal") or "normal")
        critical_pressure = pressure_stage == "critical"
        # Critical pressure means the warm caches are already hurting generation
        # speed. Even if the caller did not request cleanup for this stage, allow
        # the guard to shed CPU/GPU caches on its cooldown before macOS starts
        # compressing/swapping more aggressively.
        should_gpu_trim = (include_gpu or critical_pressure) and pressure_stage in {"warning", "critical"}
        explicit_cleanup = bool(cleanup)
        should_cleanup = bool(explicit_cleanup or critical_pressure)
        snapshot["checkpoint_auto_cleanup"] = bool(critical_pressure and not cleanup)
        snapshot["checkpoint_auto_include_gpu"] = bool(critical_pressure and not include_gpu)
        snapshot["stage_trim_requested"] = bool(should_cleanup or should_gpu_trim)
        if should_cleanup or should_gpu_trim:
            elapsed_since_trim = now - self._last_gpu_trim_at
            can_trim_now = explicit_cleanup or elapsed_since_trim >= self.gpu_trim_cooldown_sec
            if can_trim_now:
                # Keep trim cost visible so repeated-run slowdown can be traced to a concrete stage/action.
                trim_result = trim_runtime_memory_caches(
                    stage=pressure_stage if pressure_stage != "normal" else "stage",
                    include_gpu=bool(include_gpu or critical_pressure),
                )
                snapshot["stage_trim"] = trim_result
                snapshot["stage_trim_skipped_reason"] = ""
                if include_gpu or critical_pressure:
                    self._last_gpu_trim_at = now
            else:
                snapshot["stage_trim_skipped_reason"] = "cooldown"
                snapshot["stage_trim_cooldown_remaining_sec"] = round(
                    max(0.0, self.gpu_trim_cooldown_sec - elapsed_since_trim),
                    3,
                )
        else:
            snapshot["stage_trim_skipped_reason"] = "not_requested"
        # Repeat-run slowdown is easier to compare when per-chunk stage names roll up
        # into stable family totals inside the latest generation snapshot.
        self._stage_trim_summary = record_stage_trim_summary(
            self._stage_trim_summary,
            stage=self.stage,
            pressure_stage=pressure_stage,
            trim_requested=bool(snapshot.get("stage_trim_requested")),
            trim_result=snapshot.get("stage_trim") if isinstance(snapshot.get("stage_trim"), dict) else None,
            skipped_reason=str(snapshot.get("stage_trim_skipped_reason", "") or ""),
        )
        snapshot["stage_trim_summary"] = dict(self._stage_trim_summary)
        # Generation memory trim is a repeated-run hot path; publish the exact
        # stage/resource cost so status polling can separate useful work from cleanup overhead.
        trim_payload = snapshot.get("stage_trim") if isinstance(snapshot.get("stage_trim"), dict) else {}
        record_stage_done(
            f"memory_checkpoint:{self.stage}",
            resource_label=classify_resource_label(self.stage, fallback="memory"),
            ok=not bool((trim_payload or {}).get("failures")),
            metrics={
                "pressure_stage": pressure_stage,
                "stage_trim_requested": bool(snapshot.get("stage_trim_requested")),
                "stage_trim_elapsed_ms": float((trim_payload or {}).get("elapsed_ms", 0.0) or 0.0),
                "stage_trim_failure_count": len(list((trim_payload or {}).get("failures") or [])),
            },
        )

        self._last_snapshot = dict(snapshot)
        self._write_generation_snapshot(snapshot)
        self._log_pressure_notice(pressure_stage, snapshot)
        return dict(snapshot)

    def stop(self) -> None:
        try:
            self.manager.stop()
        except Exception:
            pass

    def _handle_pressure(self, stage: str, snapshot: dict[str, Any]) -> None:
        payload = dict(snapshot or {})
        payload["subtitle_generation_stage"] = self.stage
        if self.pressure_callback is None:
            return
        try:
            self.pressure_callback(stage, payload)
        except Exception:
            pass

    def _write_generation_snapshot(self, snapshot: dict[str, Any]) -> None:
        try:
            atomic_write_json(self.manager.diagnostics_dir / "subtitle_generation_latest.json", snapshot)
        except Exception:
            pass

    def _log_pressure_notice(self, pressure_stage: str, snapshot: dict[str, Any]) -> None:
        if pressure_stage == "normal":
            return
        key = f"{pressure_stage}:{self.stage}"
        if key == self._last_notice_key:
            return
        self._last_notice_key = key
        if self.logger is None:
            return
        try:
            rss_gb = float(snapshot.get("rss_gb", 0.0) or 0.0)
            free_gb = float(((snapshot.get("resource") or {}).get("available_memory_bytes", 0) or 0)) / float(1024 ** 3)
            self.logger.log(
                f"🧹 [자막 메모리] {self.stage}: {pressure_stage} · "
                f"rss={rss_gb:.2f}GB · free={free_gb:.2f}GB"
            )
        except Exception:
            pass


class RuntimeMemoryManager:
    def __init__(
        self,
        *,
        settings: dict[str, Any] | None = None,
        logger: Any = None,
        diagnostics_dir: str | Path | None = None,
        cache_paths: list[str | Path] | None = None,
    ) -> None:
        self.settings = dict(settings or {})
        self.logger = logger
        self.diagnostics_dir = Path(diagnostics_dir) if diagnostics_dir else runtime_memory_monitor_dir()
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        self.cache_paths = [Path(p) for p in (cache_paths or default_runtime_disk_cache_paths())]
        self.interval_ms = max(1000, int(float(self.settings.get("runtime_memory_monitor_interval_ms", 15000) or 15000)))
        self.disk_cache_budget_bytes = max(
            256 * 1024 * 1024,
            int(float(self.settings.get("runtime_memory_disk_cache_budget_gb", 12.0) or 12.0) * (1024 ** 3)),
        )
        # Hot-path memory policy should stay configurable at runtime for repeatable
        # benchmark experiments without changing user-visible defaults.
        self.warning_pressure_ratio = _coerce_float(
            self.settings.get(
                "runtime_memory_warning_ratio",
                self.settings.get("macos_memory_warning_ratio", 0.20),
            ),
            default=0.20,
            min_value=0.0,
            max_value=1.0,
        )
        self.critical_pressure_ratio = _coerce_float(
            self.settings.get(
                "runtime_memory_critical_ratio",
                self.settings.get("macos_memory_critical_ratio", 0.12),
            ),
            default=0.12,
            min_value=0.0,
            max_value=1.0,
        )
        self.warning_pressure_reserve_gb = _coerce_float(
            self.settings.get("macos_memory_warning_reserve_gb", 3.0),
            default=3.0,
            min_value=0.0,
        )
        self.critical_pressure_reserve_gb = _coerce_float(
            self.settings.get("macos_memory_critical_reserve_gb", 1.5),
            default=1.5,
            min_value=0.0,
        )
        self.warning_pressure_compressed_ratio = _coerce_float(
            # Keep legacy-compressed key compatibility for mixed profile payloads.
            self.settings.get(
                "runtime_memory_warning_compressed_ratio",
                self.settings.get("macos_memory_warning_compressed_ratio", 0.22),
            ),
            default=0.22,
            min_value=0.0,
            max_value=1.0,
        )
        self.critical_pressure_compressed_ratio = _coerce_float(
            # Keep legacy-compressed key compatibility for mixed profile payloads.
            self.settings.get(
                "runtime_memory_critical_compressed_ratio",
                self.settings.get("macos_memory_critical_compressed_ratio", 0.30),
            ),
            default=0.30,
            min_value=0.0,
            max_value=1.0,
        )
        if self.warning_pressure_ratio > self.critical_pressure_ratio:
            self.warning_pressure_ratio, self.critical_pressure_ratio = (
                self.critical_pressure_ratio,
                self.warning_pressure_ratio,
            )
        if self.warning_pressure_reserve_gb < self.critical_pressure_reserve_gb:
            self.warning_pressure_reserve_gb, self.critical_pressure_reserve_gb = (
                self.critical_pressure_reserve_gb,
                self.warning_pressure_reserve_gb,
            )
        self._trim_callbacks: list[tuple[str, Callable[[str, dict[str, Any]], Any]]] = []
        self._history: deque[dict[str, Any]] = deque(maxlen=32)
        self._last_stage = "normal"
        self._last_trim_at = 0.0
        self._last_disk_sample_at = 0.0
        self._last_disk_usage = {"total_bytes": 0, "file_count": 0, "total_gb": 0.0, "directories": []}
        self._trace_enabled = bool(self.settings.get("runtime_memory_tracemalloc_enabled", False))
        self._trace_frames = max(4, int(float(self.settings.get("runtime_memory_tracemalloc_frames", 8) or 8)))
        self._last_trace_snapshot = None
        self._last_leak_report_at = 0.0
        if self._trace_enabled and not tracemalloc.is_tracing():
            try:
                tracemalloc.start(self._trace_frames)
            except Exception:
                self._trace_enabled = False

    def register_trim_callback(self, name: str, callback: Callable[[str, dict[str, Any]], Any]) -> None:
        self._trim_callbacks = [(n, cb) for n, cb in self._trim_callbacks if n != name]
        self._trim_callbacks.append((str(name or "callback"), callback))

    def stop(self) -> None:
        try:
            self._write_latest_snapshot({"state": "stopped", "timestamp": round(time.time(), 3)})
        except Exception:
            pass

    def collect_snapshot(self) -> dict[str, Any]:
        resource = current_resource_snapshot(self.settings)
        rss_bytes = int(resource.get("process_rss_bytes", 0) or 0) or process_rss_bytes()
        memory_bytes = max(0, int(resource.get("memory_bytes", 0) or 0))
        rss_ratio = (float(rss_bytes) / float(memory_bytes)) if memory_bytes > 0 and rss_bytes > 0 else 0.0
        now = time.time()
        if (now - self._last_disk_sample_at) >= 60.0 or not self._last_disk_usage:
            self._last_disk_usage = runtime_disk_cache_usage(self.cache_paths)
            self._last_disk_sample_at = now
        trace_current = 0
        trace_peak = 0
        if self._trace_enabled and tracemalloc.is_tracing():
            try:
                trace_current, trace_peak = tracemalloc.get_traced_memory()
            except Exception:
                trace_current = 0
                trace_peak = 0
        snapshot = {
            "timestamp": round(now, 3),
            "rss_bytes": rss_bytes,
            "rss_gb": round(rss_bytes / float(1024 ** 3), 4),
            "rss_ratio": round(max(0.0, min(1.0, rss_ratio)), 4),
            "trace_current_bytes": int(trace_current or 0),
            "trace_peak_bytes": int(trace_peak or 0),
            "disk_cache_bytes": int(self._last_disk_usage.get("total_bytes", 0) or 0),
            "disk_cache_gb": round(float(self._last_disk_usage.get("total_bytes", 0) or 0) / float(1024 ** 3), 4),
            "disk_cache_files": int(self._last_disk_usage.get("file_count", 0) or 0),
            "pressure_stage": "normal",
            "resource": resource,
        }
        snapshot["pressure_stage"] = self._pressure_stage(snapshot)
        return snapshot

    def poll(self, *, allow_trim: bool = True) -> dict[str, Any]:
        snapshot = self.collect_snapshot()
        stage = str(snapshot.get("pressure_stage", "normal") or "normal")
        if stage != "normal" and not allow_trim:
            snapshot["trim_deferred_reason"] = "busy_runtime_work"
        self._history.append(snapshot)
        self._write_latest_snapshot(snapshot)
        if stage != "normal" and not allow_trim:
            # Active torch/MPS work can still be encoding GPU graphs here; defer
            # gc/cache trim until the next idle poll to avoid racing live tensors.
            self._last_stage = stage
            return snapshot
        if stage != "normal":
            self._maybe_trim(stage, snapshot)
            self._maybe_report_leak(snapshot)
        elif self._last_stage != "normal":
            self._log(f"🧠 메모리 상태 회복: {self._last_stage} -> normal")
        self._last_stage = stage
        return snapshot

    def prune_disk_caches(self, *, stage: str = "warning") -> dict[str, Any]:
        target_ratio = self.warning_disk_cache_trim_ratio if stage == "warning" else self.critical_disk_cache_trim_ratio
        if not self.settings.get("macos_memory_cache_prune_enabled", True):
            target_ratio = self.warning_disk_cache_trim_ratio + 0.15 if stage == "warning" else self.critical_disk_cache_trim_ratio + 0.20
        result = prune_runtime_disk_caches(
            paths=self.cache_paths,
            target_total_bytes=int(self.disk_cache_budget_bytes * target_ratio),
        )
        if int(result.get("removed_files", 0) or 0) > 0:
            self._log(
                f"🧹 디스크 캐시 정리: {result['removed_files']}개 / "
                f"{round(float(result['removed_bytes']) / (1024 ** 2), 1)}MB 제거"
            )
        self._last_disk_usage = runtime_disk_cache_usage(self.cache_paths)
        self._last_disk_sample_at = time.time()
        return result

    def _pressure_stage(self, snapshot: dict[str, Any]) -> str:
        resource = snapshot.get("resource")
        if not isinstance(resource, dict):
            resource = {}
        native_stage = str(resource.get("memory_pressure_stage", "") or "").strip().lower()
        if native_stage == "critical":
            return "critical"
        if native_stage == "warning":
            return "warning"
        available_ratio = float(resource.get("available_memory_ratio", 1.0) or 1.0)
        available_gb = float(resource.get("available_memory_bytes", 0) or 0) / float(1024 ** 3)
        rss_ratio = float(snapshot.get("rss_ratio", 0.0) or 0.0)
        compressed_ratio = float(resource.get("compressed_memory_ratio", 0.0) or resource.get("compressed_ratio", 0.0) or 0.0)
        if (
            available_ratio <= self.critical_pressure_ratio
            or available_gb <= self.critical_pressure_reserve_gb
            or compressed_ratio >= self.critical_pressure_compressed_ratio
        ):
            return "critical"
        if (
            available_ratio <= self.warning_pressure_ratio
            or available_gb <= self.warning_pressure_reserve_gb
            or compressed_ratio >= self.warning_pressure_compressed_ratio
        ):
            return "warning"
        return "normal"

    def _maybe_trim(self, stage: str, snapshot: dict[str, Any]) -> None:
        now = time.time()
        warning_cooldown = _coerce_float(
            self.settings.get("runtime_memory_warning_trim_cooldown_sec", 12.0),
            default=12.0,
            min_value=1.0,
        )
        critical_cooldown = _coerce_float(
            self.settings.get("runtime_memory_critical_trim_cooldown_sec", 6.0),
            default=6.0,
            min_value=1.0,
        )
        cooldown = warning_cooldown if stage == "warning" else critical_cooldown
        if (now - self._last_trim_at) < cooldown and stage == self._last_stage:
            return
        if self.settings.get("macos_memory_trim_runtime_caches_enabled", True):
            trim_runtime_memory_caches(stage=stage, include_gpu=stage == "critical")
        for _name, callback in list(self._trim_callbacks):
            try:
                callback(stage, snapshot)
            except Exception as exc:
                self._log(f"⚠️ 메모리 정리 콜백 실패: {exc}")
        try:
            gc.collect()
        except Exception:
            pass
        if stage == "critical" or (
            stage == "warning"
            and self.settings.get("macos_memory_cache_prune_enabled", True)
            and int(snapshot.get("disk_cache_bytes", 0) or 0) > int(self.disk_cache_budget_bytes * self.warning_disk_cache_trim_ratio)
        ):
            self.prune_disk_caches(stage=stage)
        self._last_trim_at = now

    @property
    def warning_disk_cache_trim_ratio(self) -> float:
        return _coerce_float(
            self.settings.get("runtime_memory_warning_disk_trim_ratio", 0.72),
            default=0.72,
            min_value=0.0,
            max_value=1.0,
        )

    @property
    def critical_disk_cache_trim_ratio(self) -> float:
        return _coerce_float(
            self.settings.get("runtime_memory_critical_disk_trim_ratio", 0.45),
            default=0.45,
            min_value=0.0,
            max_value=1.0,
        )

    def _maybe_report_leak(self, snapshot: dict[str, Any]) -> None:
        if not (self._trace_enabled and tracemalloc.is_tracing()):
            return
        now = time.time()
        if (now - self._last_leak_report_at) < 90.0:
            return
        if len(self._history) < 4:
            return
        first = self._history[0]
        last = self._history[-1]
        growth = int(last.get("rss_bytes", 0) or 0) - int(first.get("rss_bytes", 0) or 0)
        if growth < 256 * 1024 * 1024:
            return
        try:
            current = tracemalloc.take_snapshot()
            previous = self._last_trace_snapshot
            self._last_trace_snapshot = current
            if previous is None:
                return
            stats = current.compare_to(previous, "lineno")
            top = []
            for stat in stats[:10]:
                frame = stat.traceback[0] if stat.traceback else None
                filename = frame.filename if frame else ""
                if "/ai_subtitle_studio/" not in filename:
                    continue
                top.append({
                    "file": filename,
                    "line": int(frame.lineno if frame else 0),
                    "size_diff_kb": round(float(stat.size_diff) / 1024.0, 2),
                    "count_diff": int(stat.count_diff),
                })
            if not top:
                return
            payload = {
                "timestamp": round(now, 3),
                "rss_growth_bytes": growth,
                "rss_growth_mb": round(growth / float(1024 ** 2), 2),
                "pressure_stage": snapshot.get("pressure_stage", "warning"),
                "top_allocations": top,
            }
            atomic_write_json(self.diagnostics_dir / "leak_report.json", payload)
            self._last_leak_report_at = now
            self._log(f"⚠️ 메모리 증가 감지: 최근 RSS +{payload['rss_growth_mb']}MB, leak_report.json 기록")
        except Exception:
            pass

    def _write_latest_snapshot(self, snapshot: dict[str, Any]) -> None:
        try:
            atomic_write_json(self.diagnostics_dir / "latest.json", snapshot)
        except Exception:
            pass

    def _log(self, message: str) -> None:
        if self.logger is None:
            return
        try:
            self.logger.log(message)
        except Exception:
            pass


__all__ = [
    "RuntimeMemoryManager",
    "SubtitleGenerationMemoryGuard",
    "default_runtime_disk_cache_paths",
    "process_rss_bytes",
    "prune_runtime_disk_caches",
    "register_runtime_cache_path",
    "runtime_disk_cache_budget_bytes",
    "runtime_disk_cache_usage",
    "runtime_memory_monitor_dir",
    "scaled_runtime_cache_budget_bytes",
    "trim_runtime_memory_caches",
    "unregister_runtime_cache_path",
]
