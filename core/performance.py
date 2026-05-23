# Version: 03.07.01
# Phase: PHASE2
"""
Runtime performance helpers.

This branch targets macOS native execution. Optional native dependencies remain
soft-detected so first-run setup can fall back cleanly while App Store packaging
work moves the hot paths into Swift/C++ helpers.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from core.coerce import positive_int as _positive_int
from core.native_json import dumps_json_bytes
from core.runtime.hardware_profile import darwin_sysctl_int as _sysctl_int
from core.runtime.hardware_profile import hardware_profile
from core.runtime import qt_runtime as _qt_runtime
from core.runtime.setting_utils import setting_bool as _setting_bool


configure_qt_application_font = _qt_runtime.configure_qt_application_font
configure_qt_runtime = _qt_runtime.configure_qt_runtime
configure_qt_tooltip_theme = _qt_runtime.configure_qt_tooltip_theme
qt_application_font_family = _qt_runtime.qt_application_font_family
qt_tooltip_stylesheet = _qt_runtime.qt_tooltip_stylesheet
_QT_GPU_RENDERING_SETTINGS_REQUEST = _qt_runtime._qt_gpu_rendering_settings_request


def _qt_gpu_rendering_settings_request() -> tuple[bool | None, bool | None, str]:
    """Compatibility hook for tests and legacy callers patching core.performance."""
    return _QT_GPU_RENDERING_SETTINGS_REQUEST()


def configure_qt_gpu_rendering_before_app() -> None:
    """Apply Qt GPU setup while keeping the historical patch point alive."""
    original = _qt_runtime._qt_gpu_rendering_settings_request
    _qt_runtime._qt_gpu_rendering_settings_request = _qt_gpu_rendering_settings_request
    try:
        _qt_runtime.configure_qt_gpu_rendering_before_app()
    finally:
        _qt_runtime._qt_gpu_rendering_settings_request = original


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_JSON_WRITE_LOCK = threading.Lock()
_RAMP_LOCK = threading.Lock()
_RUNTIME_RAMP_STARTED_AT = 0.0

def apple_silicon_runtime_profile(
    settings: dict[str, Any] | None = None,
    *,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return chip-aware CPU/GPU/NPU allocation targets for Apple Silicon."""
    settings = dict(settings or {})
    profile = dict(profile or hardware_profile())
    is_apple_silicon = (
        str(profile.get("system") or "") == "Darwin"
        and str(profile.get("machine") or "").lower() in {"arm64", "aarch64"}
    )
    if not is_apple_silicon:
        return {}

    logical = max(1, int(profile.get("logical_cores", 1) or 1))
    performance = max(1, int(profile.get("performance_cores", 1) or 1))
    efficiency = max(0, int(profile.get("efficiency_cores", max(0, logical - performance)) or 0))
    gpu_cores = max(0, int(profile.get("gpu_cores", 0) or 0))
    ane_cores = max(0, int(profile.get("neural_engine_cores", 0) or 0))
    memory_gb = float(profile.get("memory_bytes", 0) or 0) / float(1024 ** 3)
    generation = max(0, int(profile.get("chip_generation", 0) or 0))
    tier = str(profile.get("chip_tier") or "base").lower()

    if generation >= 5:
        balanced = performance + min(efficiency, 3)
        wide = logical
        sustained = performance + min(efficiency, 4)
        chip_reason = "m5_or_newer_perf_plus_efficiency"
    elif generation >= 3:
        balanced = performance + min(efficiency, 2)
        wide = performance + min(efficiency, 4)
        sustained = performance + min(efficiency, 3)
        chip_reason = "m3_m4_balanced_efficiency"
    else:
        balanced = performance + min(efficiency, 2)
        wide = performance + min(efficiency, 4)
        sustained = balanced
        chip_reason = "generic_apple_silicon"

    interactive_reserve = 1 if logical > 1 else 0
    logical_cap = max(1, logical - interactive_reserve)
    balanced = max(1, min(logical_cap, balanced))
    wide = max(1, min(logical_cap, wide))
    sustained = max(1, min(logical_cap, sustained))

    gpu_stt_slots = 1
    if memory_gb >= 24 and (gpu_cores >= 16 or tier in {"pro", "max", "ultra"}):
        gpu_stt_slots = 2
    if memory_gb >= 64 and tier in {"max", "ultra"}:
        gpu_stt_slots = 3

    npu_slots = 1 if ane_cores > 0 else 0
    if memory_gb >= 32 and tier in {"pro", "max", "ultra"}:
        npu_slots = min(2, max(1, npu_slots))

    local_llm_workers = 2
    if memory_gb >= 32 and logical >= 12:
        local_llm_workers = 3
    if memory_gb < 14:
        local_llm_workers = 1

    llm_resource_max = max(1, min(logical_cap, performance + min(efficiency, 2), 6))
    emergency_reserve = 1 if logical > 1 else 0
    # BENCH LOCK 2026-05-09 (Apple M5, X5_시승기_후반.MP4 4K HEVC):
    # The generic CPU profile still exposes wide/balanced workers for audio and
    # native prepasses, but cut-boundary scan/verify stays fixed at 4. Measured
    # 6/8/10 pioneer workers and 6/8/10 follower splits were slower or missed
    # boundary candidates at worker seams.
    cut_boundary_workers = 4
    # BENCH LOCK 2026-05-10: starting follower verification at 20% with 8-row
    # streaming batches made provisional/formal boundary merging too chatty on
    # long 4K clips. The earlier benchmark-stable cadence was faster end-to-end.
    cut_follower_stream_start_percent = 25
    cut_follower_stream_batch_size = 16
    profile_payload = {
        "schema": "ai_subtitle_studio.apple_silicon_chip_profile.v1",
        "chip_name": profile.get("chip_name") or profile.get("brand_string") or "Apple Silicon",
        "chip_generation": generation,
        "chip_tier": tier,
        "reason": chip_reason,
        "logical_cores": logical,
        "performance_cores": performance,
        "efficiency_cores": efficiency,
        "gpu_cores": gpu_cores,
        "neural_engine_cores": ane_cores,
        "memory_gb": round(memory_gb, 2),
        "interactive_reserve_cores": interactive_reserve,
        "emergency_reserve_cores": emergency_reserve,
        "cpu": {
            "native_threads": logical_cap,
            "wide_workers": wide,
            "balanced_workers": balanced,
            "sustained_workers": sustained,
            "p_core_workers": performance,
            "e_core_assist_workers": min(efficiency, max(0, wide - performance)),
        },
        "gpu": {
            "available": bool(gpu_cores),
            "cores": gpu_cores,
            "stt_slots": gpu_stt_slots,
            "mlx_slots": gpu_stt_slots,
            "timeline_render_slots": 1 if gpu_cores else 0,
        },
        "npu": {
            "available": bool(npu_slots),
            "estimated_cores": ane_cores,
            "coreml_slots": npu_slots,
            "prefer_for": ["whisperkit_prefill", "vad_coreml", "live_stt"] if npu_slots else [],
        },
        "pipeline": {
            "audio_workers": wide,
            "ffmpeg_filter_threads": sustained,
            "direct_ffmpeg_chunk_min_sec": 0.75 if generation >= 5 else 1.0,
            "cut_pioneer_workers": cut_boundary_workers,
            "cut_follower_workers": cut_boundary_workers,
            "cut_follower_outer_splits": cut_boundary_workers,
            "cut_follower_stream_start_percent": cut_follower_stream_start_percent,
            "cut_follower_stream_batch_size": cut_follower_stream_batch_size,
            "subtitle_prepass_workers": wide,
            "llm_workers": min(4, llm_resource_max),
            "llm_resource_max": llm_resource_max,
            "local_llm_workers": local_llm_workers,
            "stt_primary_slots": gpu_stt_slots,
            "stt_secondary_slots": 1,
            "word_timestamp_slots": 1,
        },
    }
    return profile_payload


def performance_profile(settings: dict[str, Any] | None = None) -> str:
    settings = dict(settings or {})
    value = os.environ.get("AI_SUBTITLE_PERFORMANCE_PROFILE")
    if value is None:
        value = settings.get("runtime_performance_profile")
    text = str(value or "balanced").strip().lower()
    aliases = {
        "turbo": "max",
        "maximum": "max",
        "hardware_max": "max",
        "full": "max",
        "eco": "balanced",
        "safe": "balanced",
    }
    return aliases.get(text, text if text in {"balanced", "max"} else "balanced")


def hardware_max_profile_enabled(settings: dict[str, Any] | None = None) -> bool:
    settings = dict(settings or {})
    explicit = settings.get("runtime_hardware_acceleration_enabled")
    if explicit is not None and not _safe_bool(explicit, True):
        return False
    return performance_profile(settings) == "max"


def native_thread_budget(settings: dict[str, Any] | None = None) -> int:
    settings = dict(settings or {})
    profile = hardware_profile()
    logical = max(1, int(profile.get("logical_cores", 1) or 1))
    physical = max(1, int(profile.get("physical_cores", logical) or logical))
    perf = max(1, int(profile.get("performance_cores", physical) or physical))
    reserve = max(0, int(runtime_scheduler_reserve_cores(settings, task="cpu")))
    if hardware_max_profile_enabled(settings):
        default = max(1, logical - reserve)
    else:
        default = min(max(1, perf), physical)
    profile_requested = 0
    if _safe_bool(settings.get("runtime_native_threads_auto_enabled"), True):
        profile_requested = _runtime_profile_native_threads(settings)
    requested = profile_requested or _positive_int(settings.get("runtime_native_threads"), 0)
    return max(1, min(requested or default, logical))


def _runtime_profile_native_threads(settings: dict[str, Any]) -> int:
    if "pytest" in sys.modules:
        return 0
    if not _safe_bool(settings.get("runtime_backend_autotune_enabled"), True):
        return 0
    try:
        from core.optimization.profile_store import load_optimization_profile

        profile = load_optimization_profile()
        return _positive_int(profile.selected_backends.get("native_threads"), 0)
    except Exception:
        return 0


def native_runtime_env_overrides(settings: dict[str, Any] | None = None) -> dict[str, str]:
    settings = dict(settings or {})
    if not _safe_bool(settings.get("runtime_native_threads_auto_enabled"), True):
        return {}
    budget = native_thread_budget(settings)
    out = {
        "AI_SUBTITLE_NATIVE_THREADS": str(budget),
        "AI_SUBTITLE_NATIVE_JSON": "1" if _safe_bool(settings.get("runtime_native_json_enabled"), True) else "0",
        "AI_SUBTITLE_NATIVE_TEXT_SIMILARITY": (
            "1" if _safe_bool(settings.get("runtime_native_text_similarity_enabled"), True) else "0"
        ),
        "AI_SUBTITLE_NATIVE_CUT_BOUNDARY": (
            "1" if _safe_bool(settings.get("runtime_native_cut_boundary_enabled"), True) else "0"
        ),
        "AI_SUBTITLE_OLLAMA_PY_CLIENT": (
            "1" if _safe_bool(settings.get("ollama_python_client_enabled"), True) else "0"
        ),
        "OMP_NUM_THREADS": str(budget),
        "OPENBLAS_NUM_THREADS": str(budget),
        "MKL_NUM_THREADS": str(budget),
        "NUMEXPR_NUM_THREADS": str(budget),
        "VECLIB_MAXIMUM_THREADS": str(budget),
        "ACCELERATE_NUM_THREADS": str(budget),
        "TOKENIZERS_PARALLELISM": "true" if budget >= 4 else "false",
    }
    if platform.system() == "Darwin":
        out.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    return out


def configure_native_runtime(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Configure native library thread budgets without importing heavy stacks."""
    overrides = native_runtime_env_overrides(settings)
    for key, value in overrides.items():
        os.environ.setdefault(key, value)

    budget = _positive_int(os.environ.get("AI_SUBTITLE_NATIVE_THREADS"), native_thread_budget(settings))
    torch_configured = False
    torch_mod = sys.modules.get("torch")
    if torch_mod is not None:
        try:
            torch_mod.set_num_threads(max(1, budget))
            torch_configured = True
        except Exception:
            pass
        try:
            torch_mod.set_num_interop_threads(max(1, min(4, budget)))
        except Exception:
            pass

    return {
        "schema": "ai_subtitle_studio.native_runtime.v1",
        "profile": performance_profile(settings),
        "native_threads": budget,
        "env_keys": sorted(overrides.keys()),
        "torch_configured": torch_configured,
        "hardware": hardware_profile(),
    }


def bounded_worker_count(
    requested: Any = None,
    *,
    kind: str = "io",
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    """Return a conservative worker count for the current machine.

    `requested` is honored when valid, then clamped to a platform-aware cap.
    """
    profile = hardware_profile()
    logical = int(profile["logical_cores"])
    physical = int(profile["physical_cores"])
    perf = int(profile["performance_cores"])

    if kind == "ffprobe":
        default = min(4, max(1, logical // 2))
        cap = min(8, max(1, logical))
    elif kind == "cpu":
        default = max(1, perf)
        cap = max(1, physical)
    elif kind == "llm":
        default = min(6, max(1, perf))
        cap = min(12, max(1, logical))
    else:
        default = min(12, max(4, logical))
        cap = min(16, max(1, logical))

    if maximum is not None:
        cap = min(cap, max(1, int(maximum)))
    minimum = max(1, int(minimum))
    value = _positive_int(requested, default)
    return max(minimum, min(value, cap))


def distributed_worker_ceiling(
    settings: dict[str, Any] | None = None,
    *,
    task: str = "cpu",
    workload: int = 1,
    reserve_cores: int | None = None,
    minimum: int = 1,
) -> int:
    """Return a UI-safe parallelism ceiling for foreground CPU work.

    In `max` profile we try to use nearly all logical cores, but still keep a
    small reserve so the UI thread and OS compositor can breathe.
    """
    settings = dict(settings or {})
    workload = max(1, int(workload or 1))
    minimum = max(1, int(minimum or 1))
    profile = hardware_profile()
    logical = max(1, int(profile.get("logical_cores", 1) or 1))
    physical = max(1, int(profile.get("physical_cores", logical) or logical))
    perf = max(1, int(profile.get("performance_cores", physical) or physical))
    task_text = str(task or "cpu").strip().lower()

    configured_reserve = runtime_scheduler_reserve_cores(settings, task=task_text)
    reserve = configured_reserve if reserve_cores is None else max(0, int(reserve_cores))

    if hardware_max_profile_enabled(settings):
        ceiling = max(1, logical - reserve)
    elif task_text in {"io", "prefetch"}:
        ceiling = min(logical, max(4, perf))
    else:
        ceiling = max(1, physical)
    return max(minimum, min(workload, ceiling))


def runtime_scheduler_reserve_cores(
    settings: dict[str, Any] | None = None,
    *,
    task: str = "cpu",
    exiting: bool = False,
) -> int:
    """Return the core reserve that should be kept away from worker pools.

    In `max` profile we prefer full-core usage for CPU/IO fan-out, except for
    manual LoRA full-learning where we deliberately keep one logical core free
    so stop/exit stays responsive. When the app is exiting we keep no reserve
    at all so cleanup can finish immediately.
    """
    settings = dict(settings or {})
    if exiting:
        return 0
    profile = hardware_profile()
    logical = max(1, int(profile.get("logical_cores", 1) or 1))
    default_reserve = 1 if logical >= 4 else 0
    try:
        configured = int(float(settings.get("runtime_scheduler_reserve_cores", default_reserve)))
    except (TypeError, ValueError):
        configured = default_reserve
    configured = max(0, configured)
    if not hardware_max_profile_enabled(settings):
        return configured
    task_text = str(task or "cpu").strip().lower()
    if task_text in {
        "manual_lora",
        "lora_manual",
        "manual_training",
        "manual_full_training",
        "lora_full",
    }:
        return 1 if logical > 1 else 0
    interactive_tasks = {
        "cpu",
        "io",
        "prefetch",
        "cut_pioneer",
        "cut_follower",
        "stt",
        "lora",
        "cleanup",
        "shutdown",
        "subtitle_prepass",
    }
    if task_text in {
        "exit",
    }:
        return 0
    benchmark_profile = str(settings.get("benchmark_runtime_profile") or "").strip().lower()
    full_core_requested = benchmark_profile == "apple_m_full_core_throughput" or _setting_bool(
        settings.get("apple_m_full_core_aggressive_enabled"),
        False,
    )
    if full_core_requested:
        # Explicit benchmark mode: the user asked to saturate cores, so worker
        # ceilings may consume the usual interactive reserve outside manual LoRA.
        return 0
    if task_text in interactive_tasks:
        return max(1 if logical > 1 else 0, configured)
    return min(configured, 1)


def balanced_task_slices(
    total_items: int,
    workers: int,
    *,
    min_batch_size: int = 1,
) -> list[tuple[int, int]]:
    """Split work into contiguous balanced slices with low scheduler overhead."""
    total = max(0, int(total_items or 0))
    if total <= 0:
        return []
    worker_count = max(1, int(workers or 1))
    min_batch = max(1, int(min_batch_size or 1))
    slice_count = min(worker_count, total)
    while slice_count > 1 and (total // slice_count) < min_batch:
        slice_count -= 1
    base = total // slice_count
    remainder = total % slice_count
    out: list[tuple[int, int]] = []
    start = 0
    for idx in range(slice_count):
        size = base + (1 if idx < remainder else 0)
        end = min(total, start + size)
        if end > start:
            out.append((start, end))
        start = end
    return out


def _safe_bool(value: Any, default: bool = True) -> bool:
    return _setting_bool(
        value,
        default,
        false_values={"0", "false", "off", "no", "끔", "아니오"},
        false_only_strings=True,
        empty_is_default=False,
    )


def mark_runtime_scheduler_start(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Start a gentle resource ramp for foreground processing.

    The pipeline starts at one worker, then gradually allows more parallel work
    after the app proves stable. This keeps the start button responsive and
    avoids waking ffmpeg/STT/LLM work all at once.
    """
    global _RUNTIME_RAMP_STARTED_AT
    settings = dict(settings or {})
    enabled = _safe_bool(settings.get("runtime_scheduler_ramp_up_enabled"), True)
    now = time.monotonic()
    with _RAMP_LOCK:
        _RUNTIME_RAMP_STARTED_AT = now if enabled else 0.0
    return {
        "schema": "ai_subtitle_studio.runtime_scheduler_ramp.v1",
        "enabled": enabled,
        "started_at_monotonic": _RUNTIME_RAMP_STARTED_AT,
        "initial_sec": max(0.0, float(settings.get("runtime_scheduler_ramp_initial_sec", 45.0) or 45.0)),
        "step_sec": max(1.0, float(settings.get("runtime_scheduler_ramp_step_sec", 60.0) or 60.0)),
    }


def runtime_scheduler_ramp_elapsed() -> float:
    with _RAMP_LOCK:
        started = float(_RUNTIME_RAMP_STARTED_AT or 0.0)
    if started <= 0.0:
        return 0.0
    return max(0.0, time.monotonic() - started)


def _ramp_worker_cap(
    settings: dict[str, Any] | None,
    *,
    task: str,
    current_cap: int,
) -> tuple[int, dict[str, Any]]:
    settings = dict(settings or {})
    current_cap = max(1, int(current_cap or 1))
    if hardware_max_profile_enabled(settings):
        return current_cap, {"enabled": False, "cap": current_cap, "reason": "hardware_max_profile"}
    if not _safe_bool(settings.get("runtime_scheduler_ramp_up_enabled"), True):
        return current_cap, {"enabled": False, "cap": current_cap, "reason": "disabled"}
    elapsed = runtime_scheduler_ramp_elapsed()
    if elapsed <= 0.0:
        return current_cap, {"enabled": False, "cap": current_cap, "reason": "not_started"}

    initial_sec = max(0.0, float(settings.get("runtime_scheduler_ramp_initial_sec", 45.0) or 45.0))
    step_sec = max(1.0, float(settings.get("runtime_scheduler_ramp_step_sec", 60.0) or 60.0))
    task_text = str(task or "worker").strip().lower()
    if elapsed < initial_sec:
        cap = 1
        phase = "warmup"
    else:
        cap = 2 + int((elapsed - initial_sec) // step_sec)
        phase = "ramping"
    if task_text in {"llm", "subtitle_llm", "roughcut_llm"} or "llm" in task_text:
        # Local model runners are the easiest thing to destabilize on MacBook
        # Air-class machines, so they ramp one step slower than CPU workers.
        cap = max(1, cap - 1)
    cap = max(1, min(current_cap, cap))
    return cap, {
        "enabled": True,
        "cap": cap,
        "elapsed_sec": round(elapsed, 3),
        "initial_sec": initial_sec,
        "step_sec": step_sec,
        "phase": phase,
    }


def _available_memory_bytes() -> int:
    try:
        import psutil  # type: ignore

        return max(0, int(psutil.virtual_memory().available))
    except Exception:
        pass
    if platform.system() == "Darwin":
        try:
            page_size = _sysctl_int("hw.pagesize") or 4096
            proc = subprocess.run(
                ["vm_stat"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1.0,
            )
            free_pages = 0
            for line in (proc.stdout or "").splitlines():
                if any(key in line for key in ("Pages free", "Pages inactive", "Pages speculative")):
                    number = "".join(ch for ch in line.split(":", 1)[-1] if ch.isdigit())
                    free_pages += _positive_int(number, 0)
            return max(0, free_pages * page_size)
        except Exception:
            return 0
    return 0


def _darwin_battery_state() -> dict[str, Any]:
    if platform.system() != "Darwin":
        return {"on_battery": False, "battery_percent": None}
    try:
        proc = subprocess.run(
            ["pmset", "-g", "batt"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=0.8,
        )
    except Exception:
        return {"on_battery": False, "battery_percent": None}
    text = proc.stdout or ""
    on_battery = "Battery Power" in text
    percent = None
    for token in text.replace(";", " ").split():
        if token.endswith("%"):
            percent = _positive_int(token.rstrip("%"), 0)
            break
    return {"on_battery": bool(on_battery), "battery_percent": percent if isinstance(percent, int) and percent > 0 else None}


def _darwin_user_idle_seconds() -> float | None:
    if platform.system() != "Darwin":
        return None
    try:
        proc = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=0.8,
        )
    except Exception:
        return None
    for line in (proc.stdout or "").splitlines():
        if "HIDIdleTime" not in line:
            continue
        raw = line.split("=", 1)[-1].strip()
        try:
            return max(0.0, float(raw) / 1_000_000_000.0)
        except Exception:
            return None
    return None


def current_resource_snapshot(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = dict(settings or {})
    profile = hardware_profile()
    logical = max(1, int(profile.get("logical_cores", 1) or 1))
    memory_bytes = max(0, int(profile.get("memory_bytes", 0) or 0))
    native_memory: dict[str, Any] | None = None
    try:
        from core.native_macos_memory import native_memory_snapshot

        native_memory = native_memory_snapshot(settings)
    except Exception:
        native_memory = None
    available = int((native_memory or {}).get("available_memory_bytes", 0) or 0)
    if available <= 0:
        available = _available_memory_bytes()
    if memory_bytes <= 0:
        memory_bytes = max(0, int((native_memory or {}).get("memory_bytes", 0) or 0))
        if memory_bytes <= 0:
            try:
                import psutil  # type: ignore

                memory_bytes = max(0, int(psutil.virtual_memory().total))
            except Exception:
                memory_bytes = 0
    try:
        load_1m = float(os.getloadavg()[0])
    except Exception:
        load_1m = 0.0
    load_ratio = max(0.0, load_1m / float(logical))
    available_ratio = (float(available) / float(memory_bytes)) if memory_bytes > 0 and available > 0 else 1.0
    battery = _darwin_battery_state()
    idle_seconds = _darwin_user_idle_seconds()
    user_active = bool(idle_seconds is not None and idle_seconds < 15.0)
    snapshot = {
        **profile,
        "cpu_load_1m": round(load_1m, 4),
        "cpu_load_ratio": round(load_ratio, 4),
        "available_memory_bytes": available,
        "available_memory_ratio": round(max(0.0, min(1.0, available_ratio)), 4),
        "on_battery": bool(battery.get("on_battery")),
        "battery_percent": battery.get("battery_percent"),
        "user_idle_seconds": None if idle_seconds is None else round(float(idle_seconds), 3),
        "user_active": user_active,
    }
    if native_memory:
        snapshot["native_memory"] = native_memory
        snapshot["memory_pressure_stage"] = str(native_memory.get("pressure_stage", "") or "")
        snapshot["compressed_memory_ratio"] = float(native_memory.get("compressed_memory_ratio", 0.0) or 0.0)
        snapshot["compressed_memory_bytes"] = int(native_memory.get("compressed_bytes", 0) or 0)
        if int(native_memory.get("process_rss_bytes", 0) or 0) > 0:
            snapshot["process_rss_bytes"] = int(native_memory.get("process_rss_bytes", 0) or 0)
    return snapshot


def _resource_pressure_reduction(snapshot: dict[str, Any], settings: dict[str, Any] | None = None) -> tuple[int, list[str]]:
    settings = dict(settings or {})
    reduction = 0
    reasons: list[str] = []
    load_ratio = float(snapshot.get("cpu_load_ratio", 0.0) or 0.0)
    available_ratio = float(snapshot.get("available_memory_ratio", 1.0) or 1.0)
    available_gb = float(snapshot.get("available_memory_bytes", 0) or 0) / (1024 ** 3)
    max_profile = hardware_max_profile_enabled(settings)
    extreme_load = 2.50 if max_profile else 1.50
    severe_load = 1.60 if max_profile else 1.15
    very_high_load = 1.15 if max_profile else 0.97
    high_load = 0.92 if max_profile else 0.72
    very_low_mem_ratio = 0.10 if max_profile else 0.15
    low_mem_ratio = 0.16 if max_profile else 0.25
    very_low_mem_gb = 1.25 if max_profile else 2.0
    low_mem_gb = 2.5 if max_profile else 4.0
    if load_ratio >= extreme_load:
        reduction += 4
        reasons.append("extreme_cpu_load")
    elif load_ratio >= severe_load:
        reduction += 3
        reasons.append("severe_cpu_load")
    elif load_ratio >= very_high_load:
        reduction += 2
        reasons.append("very_high_cpu_load")
    elif load_ratio >= high_load:
        reduction += 1
        reasons.append("high_cpu_load")
    if (available_gb and available_gb < very_low_mem_gb) or available_ratio < very_low_mem_ratio:
        reduction += 2
        reasons.append("very_low_memory")
    elif (available_gb and available_gb < low_mem_gb) or available_ratio < low_mem_ratio:
        reduction += 1
        reasons.append("low_memory")
    if not max_profile and _safe_bool(settings.get("scheduler_reduce_on_battery"), True) and snapshot.get("on_battery"):
        reduction += 1
        reasons.append("battery_power")
    if not max_profile and _safe_bool(settings.get("scheduler_reduce_on_user_input"), True) and snapshot.get("user_active"):
        reduction += 1
        reasons.append("user_active")
    return reduction, reasons


def adaptive_worker_count(
    *,
    task: str,
    settings: dict[str, Any] | None = None,
    requested: Any = None,
    workload: int = 1,
    minimum: int = 1,
    maximum: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """Choose non-LLM worker counts from resources, workload, battery, and user input."""
    settings = dict(settings or {})
    task_text = str(task or "worker").strip().lower()
    workload = max(1, int(workload or 1))
    auto_key = f"{task_text}_workers_auto_enabled"
    auto_enabled = _safe_bool(settings.get(auto_key, settings.get("runtime_scheduler_auto_enabled", True)), True)
    kind = "io" if task_text in {"io", "lora", "prefetch"} else "cpu"
    max_profile = hardware_max_profile_enabled(settings)
    profile = hardware_profile()
    logical = max(1, int(profile.get("logical_cores", 1) or 1))
    if task_text in {"cut_pioneer", "cut_follower", "stt"}:
        if task_text == "stt":
            default_max = 2
        else:
            default_max = logical if max_profile else 4
    elif task_text == "lora":
        default_max = logical if max_profile else 4
    else:
        default_max = logical if max_profile else (maximum or 8)
    max_cap = max(1, int(maximum or _positive_int(settings.get(f"{task_text}_workers_resource_max"), default_max) or default_max))
    base = bounded_worker_count(requested, kind=kind, minimum=minimum, maximum=max_cap)
    if max_profile and auto_enabled:
        base = max(base, min(workload, max_cap, logical))
    base = max(minimum, min(base, workload, max_cap))
    snapshot = current_resource_snapshot(settings)
    if not auto_enabled:
        return base, {
            "schema": "ai_subtitle_studio.runtime_scheduler.v1",
            "task": task_text,
            "profile": performance_profile(settings),
            "auto_enabled": False,
            "workers": base,
            "requested": requested,
            "workload": workload,
            "reason": "manual_compat",
            "resource": snapshot,
        }

    reduction, reasons = _resource_pressure_reduction(snapshot, settings)
    if workload <= 1:
        reasons.append("single_item_workload")
    workers = max(minimum, min(base - reduction, workload, max_cap))
    if task_text == "stt" and workload >= 2 and not reasons:
        workers = min(workers, 2)
    ramp_cap, ramp_meta = _ramp_worker_cap(settings, task=task_text, current_cap=workers)
    if ramp_meta.get("enabled") and ramp_cap < workers:
        workers = max(minimum, ramp_cap)
        reasons.append(f"ramp_up_{ramp_meta.get('phase', 'active')}")
    meta = {
        "schema": "ai_subtitle_studio.runtime_scheduler.v1",
        "task": task_text,
        "profile": performance_profile(settings),
        "auto_enabled": True,
        "workers": workers,
        "requested": requested,
        "workload": workload,
        "reason": "resource_adaptive",
        "reductions": sorted(set(reasons)),
        "ramp": ramp_meta,
        "resource": snapshot,
    }
    return workers, meta


def _model_size_penalty(model: str) -> int:
    text = str(model or "").lower()
    if any(token in text for token in ("70b", "72b", "34b", "32b", "27b", "22b", "14b")):
        return 2
    if any(token in text for token in ("13b", "12b", "10b", "8b", "7.8b", "7b")):
        return 1
    return 0


def adaptive_llm_worker_count(
    *,
    settings: dict[str, Any] | None = None,
    requested: Any = None,
    workload: int = 1,
    provider: str = "ollama",
    model: str = "",
    task: str = "subtitle",
) -> tuple[int, dict[str, Any]]:
    """Choose LLM workers from current machine resources and workload.

    API providers stay single-worker to avoid rate-limit/cost surprises. Local
    providers are allowed to scale up only when CPU load and memory headroom are
    healthy.
    """
    settings = dict(settings or {})
    workload = max(1, int(workload or 1))
    provider_text = str(provider or "").strip().lower()
    task_text = str(task or "subtitle").strip().lower()
    auto_key = "roughcut_llm_threads_auto_enabled" if task_text == "roughcut" else "llm_threads_auto_enabled"
    auto_enabled = _safe_bool(settings.get(auto_key), True)
    is_api = provider_text in {"openai", "google", "gemini", "anthropic"} or "gemini" in str(model or "").lower() or str(model or "").lower().startswith("gpt")

    if is_api:
        meta = {
            "auto_enabled": auto_enabled,
            "profile": performance_profile(settings),
            "provider": provider_text or "api",
            "model": str(model or ""),
            "task": task_text,
            "workload": workload,
            "reason": "api_single_worker",
        }
        return 1, meta

    if not auto_enabled:
        workers = max(1, _positive_int(requested, bounded_worker_count(kind="llm", minimum=1, maximum=16)))
        return workers, {
            "auto_enabled": False,
            "profile": performance_profile(settings),
            "provider": provider_text or "ollama",
            "model": str(model or ""),
            "task": task_text,
            "workload": workload,
            "reason": "manual_compat",
        }

    snapshot = current_resource_snapshot(settings)
    perf = max(1, int(snapshot.get("performance_cores", 1) or 1))
    logical = max(1, int(snapshot.get("logical_cores", 1) or 1))
    memory_gb = float(snapshot.get("memory_bytes", 0) or 0) / (1024 ** 3)
    available_gb = float(snapshot.get("available_memory_bytes", 0) or 0) / (1024 ** 3)
    available_ratio = float(snapshot.get("available_memory_ratio", 1.0) or 1.0)
    load_ratio = float(snapshot.get("cpu_load_ratio", 0.0) or 0.0)

    base = max(1, min(4 if task_text == "subtitle" else 3, max(1, perf // 2)))
    if hardware_max_profile_enabled(settings):
        if memory_gb >= 32 and available_gb >= 12:
            base = max(base, min(4, logical // 2))
        elif memory_gb >= 16 and available_gb >= 4:
            base = max(base, 2)
    if logical >= 12 and memory_gb >= 24 and load_ratio <= 0.55 and available_ratio >= 0.35:
        base += 1
    if workload <= 2:
        base = 1
    elif workload <= 8:
        base = min(base, 2)
    reductions, reduction_reasons = _resource_pressure_reduction(snapshot, settings)
    base -= reductions
    base -= _model_size_penalty(model)

    maximum = _positive_int(settings.get("llm_threads_resource_max"), 0) or 6
    if task_text == "roughcut":
        maximum = _positive_int(settings.get("roughcut_llm_threads_resource_max"), 0) or min(maximum, 4)
    workers = max(1, min(int(base), int(maximum), workload))
    ramp_cap, ramp_meta = _ramp_worker_cap(settings, task=f"{task_text}_llm", current_cap=workers)
    if ramp_meta.get("enabled") and ramp_cap < workers:
        workers = max(1, ramp_cap)
        reduction_reasons.append(f"ramp_up_{ramp_meta.get('phase', 'active')}")
    meta = {
        "auto_enabled": True,
        "profile": performance_profile(settings),
        "provider": provider_text or "ollama",
        "model": str(model or ""),
        "task": task_text,
        "workload": workload,
        "workers": workers,
        "reason": "resource_adaptive",
        "reductions": sorted(set(reduction_reasons)),
        "ramp": ramp_meta,
        "resource": snapshot,
    }
    return workers, meta


def ffprobe_worker_count(file_count: int) -> int:
    return max(1, min(int(file_count or 1), bounded_worker_count(kind="ffprobe")))


def media_probe_cache_dir() -> Path:
    cache_root = PROJECT_ROOT / "output" / ".media_probe_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root


def atomic_write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(dumps_json_bytes(payload, indent=None))
        with _JSON_WRITE_LOCK:
            os.replace(tmp_name, target)
    except Exception:
        try:
            os.remove(tmp_name)
        except Exception:
            pass
        raise
