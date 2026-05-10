from __future__ import annotations

import gc
import os
import sys
import tempfile
import time
import tracemalloc
from collections import deque
from pathlib import Path
from typing import Any, Callable

from core.performance import atomic_write_json, current_resource_snapshot
from core.runtime import config


def process_rss_bytes() -> int:
    try:
        import psutil  # type: ignore

        return max(0, int(psutil.Process(os.getpid()).memory_info().rss))
    except Exception:
        pass
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss or 0)
        if value <= 0:
            return 0
        if os.name == "posix" and os.uname().sysname.lower() != "darwin":
            return value * 1024
        return value
    except Exception:
        return 0


def runtime_memory_monitor_dir() -> Path:
    path = Path(config.OUTPUT_DIR) / "memory_monitor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_runtime_disk_cache_paths() -> list[Path]:
    output_dir = Path(config.OUTPUT_DIR)
    temp_dir = Path(tempfile.gettempdir())
    paths = [
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
    return deduped


def runtime_disk_cache_usage(paths: list[str | Path] | None = None) -> dict[str, Any]:
    roots = [Path(p) for p in (paths or default_runtime_disk_cache_paths())]
    total_bytes = 0
    file_count = 0
    directories: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            directories.append({"path": str(root), "exists": False, "bytes": 0, "files": 0})
            continue
        if root.is_file():
            size = max(0, int(root.stat().st_size or 0))
            total_bytes += size
            file_count += 1
            directories.append({"path": str(root), "exists": True, "bytes": size, "files": 1})
            continue
        dir_bytes = 0
        dir_files = 0
        for child in root.rglob("*"):
            try:
                if not child.is_file():
                    continue
                size = max(0, int(child.stat().st_size or 0))
            except Exception:
                continue
            dir_bytes += size
            dir_files += 1
        total_bytes += dir_bytes
        file_count += dir_files
        directories.append({"path": str(root), "exists": True, "bytes": dir_bytes, "files": dir_files})
    return {
        "paths": [str(root) for root in roots],
        "total_bytes": total_bytes,
        "total_gb": round(total_bytes / float(1024 ** 3), 4),
        "file_count": file_count,
        "directories": directories,
    }


def prune_runtime_disk_caches(
    *,
    paths: list[str | Path] | None = None,
    target_total_bytes: int,
) -> dict[str, Any]:
    target_total_bytes = max(0, int(target_total_bytes or 0))
    roots = [Path(p) for p in (paths or default_runtime_disk_cache_paths())]
    file_entries: list[tuple[float, int, Path]] = []
    total_bytes = 0
    for root in roots:
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else list(root.rglob("*"))
        for child in candidates:
            try:
                if not child.is_file():
                    continue
                stat = child.stat()
            except Exception:
                continue
            size = max(0, int(stat.st_size or 0))
            total_bytes += size
            file_entries.append((float(stat.st_mtime or 0.0), size, child))

    removed_files = 0
    removed_bytes = 0
    if total_bytes > target_total_bytes:
        for _mtime, size, path in sorted(file_entries, key=lambda item: (item[0], item[2].name)):
            if total_bytes <= target_total_bytes:
                break
            try:
                path.unlink()
            except Exception:
                continue
            total_bytes -= size
            removed_files += 1
            removed_bytes += size
    return {
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "remaining_bytes": max(0, total_bytes),
        "target_total_bytes": target_total_bytes,
    }


def trim_runtime_memory_caches(*, stage: str = "warning", include_gpu: bool = False) -> dict[str, Any]:
    stage_text = str(stage or "warning").strip().lower()
    actions: list[str] = []
    settings: dict[str, Any] = {}
    try:
        from core.settings import load_settings

        settings = dict(load_settings() or {})
    except Exception:
        settings = {}
    for module_name, func_name in (
        ("core.media_info", "clear_media_probe_cache_memory"),
        ("core.project.project_io", "clear_project_file_cache"),
        ("core.personalization.lora_vector_retriever", "clear_lora_retrieval_caches"),
        ("core.native_macos_memory", "clear_native_memory_snapshot_cache"),
        ("core.native_swift_policy", "trim_native_policy_worker_cache"),
    ):
        try:
            module = __import__(module_name, fromlist=[func_name])
            func = getattr(module, func_name, None)
            if callable(func):
                func()
                actions.append(f"{module_name}.{func_name}")
        except Exception:
            continue
    try:
        gc.collect()
        actions.append("gc.collect")
    except Exception:
        pass
    try:
        from core.native_macos_memory import native_allocator_pressure_relief

        relief = native_allocator_pressure_relief(settings, stage=stage_text)
        if relief.get("ok"):
            released_mb = round(float(relief.get("released_bytes", 0) or 0) / float(1024 ** 2), 2)
            actions.append(f"macos.malloc_zone_pressure_relief:{released_mb}MB")
    except Exception:
        pass
    if include_gpu:
        torch_module = sys.modules.get("torch")
        if torch_module is not None:
            try:
                from core.audio.torch_acceleration import allow_mps_empty_cache

                mps = getattr(torch_module, "mps", None)
                empty_cache = getattr(mps, "empty_cache", None)
                if allow_mps_empty_cache() and callable(empty_cache):
                    empty_cache()
                    actions.append("torch.mps.empty_cache")
            except Exception:
                pass
            try:
                cuda = getattr(torch_module, "cuda", None)
                if cuda is not None and callable(getattr(cuda, "is_available", None)) and cuda.is_available():
                    empty_cache = getattr(cuda, "empty_cache", None)
                    if callable(empty_cache):
                        empty_cache()
                        actions.append("torch.cuda.empty_cache")
            except Exception:
                pass
        mlx_core = sys.modules.get("mlx.core")
        if mlx_core is not None:
            try:
                clear_cache = getattr(mlx_core, "clear_cache", None)
                if callable(clear_cache):
                    clear_cache()
                    actions.append("mlx.core.clear_cache")
            except Exception:
                pass
    return {"stage": stage_text, "actions": actions}


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
        should_gpu_trim = include_gpu and pressure_stage in {"warning", "critical"}
        if cleanup or should_gpu_trim:
            if cleanup or (now - self._last_gpu_trim_at) >= self.gpu_trim_cooldown_sec:
                trim_result = trim_runtime_memory_caches(
                    stage=pressure_stage if pressure_stage != "normal" else "stage",
                    include_gpu=bool(include_gpu),
                )
                snapshot["stage_trim"] = trim_result
                if include_gpu:
                    self._last_gpu_trim_at = now

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

    def poll(self) -> dict[str, Any]:
        snapshot = self.collect_snapshot()
        self._history.append(snapshot)
        self._write_latest_snapshot(snapshot)
        stage = str(snapshot.get("pressure_stage", "normal") or "normal")
        if stage != "normal":
            self._maybe_trim(stage, snapshot)
            self._maybe_report_leak(snapshot)
        elif self._last_stage != "normal":
            self._log(f"🧠 메모리 상태 회복: {self._last_stage} -> normal")
        self._last_stage = stage
        return snapshot

    def prune_disk_caches(self, *, stage: str = "warning") -> dict[str, Any]:
        target_ratio = 0.72 if stage == "warning" else 0.45
        if not self.settings.get("macos_memory_cache_prune_enabled", True):
            target_ratio = 0.85 if stage == "warning" else 0.65
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
        resource = dict(snapshot.get("resource") or {})
        native_stage = str(resource.get("memory_pressure_stage", "") or "").strip().lower()
        if native_stage == "critical":
            return "critical"
        if native_stage == "warning":
            return "warning"
        available_ratio = float(resource.get("available_memory_ratio", 1.0) or 1.0)
        available_gb = float(resource.get("available_memory_bytes", 0) or 0) / float(1024 ** 3)
        rss_ratio = float(snapshot.get("rss_ratio", 0.0) or 0.0)
        if available_ratio <= 0.12 or available_gb <= 1.5 or rss_ratio >= 0.78:
            return "critical"
        if available_ratio <= 0.20 or available_gb <= 3.0 or rss_ratio >= 0.64:
            return "warning"
        return "normal"

    def _maybe_trim(self, stage: str, snapshot: dict[str, Any]) -> None:
        now = time.time()
        cooldown = 12.0 if stage == "warning" else 6.0
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
            and int(snapshot.get("disk_cache_bytes", 0) or 0) > int(self.disk_cache_budget_bytes * 0.72)
        ):
            self.prune_disk_caches(stage=stage)
        self._last_trim_at = now

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
    "runtime_disk_cache_usage",
    "runtime_memory_monitor_dir",
    "trim_runtime_memory_caches",
]
