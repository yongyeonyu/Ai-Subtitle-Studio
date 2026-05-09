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
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.json_file import read_json_file
from core.native_json import dumps_json_bytes
from core.settings_profiles import hardcoded_default_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_JSON_WRITE_LOCK = threading.Lock()
_RAMP_LOCK = threading.Lock()
_RUNTIME_RAMP_STARTED_AT = 0.0


def _positive_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _sysctl_int(name: str) -> int:
    if platform.system() != "Darwin":
        return 0
    try:
        proc = subprocess.run(
            ["sysctl", "-n", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1.0,
        )
        return _positive_int((proc.stdout or "").strip(), 0)
    except Exception:
        return 0


def _sysctl_str(name: str) -> str:
    if platform.system() != "Darwin":
        return ""
    try:
        proc = subprocess.run(
            ["sysctl", "-n", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1.0,
        )
        return str(proc.stdout or "").strip()
    except Exception:
        return ""


def _apple_chip_parts(brand: str) -> tuple[str, int, str]:
    text = str(brand or "").strip()
    match = re.search(r"\bApple\s+(M(?P<generation>\d+)(?:\s+(?P<tier>Ultra|Max|Pro))?)\b", text, re.IGNORECASE)
    if not match:
        return text, 0, "base"
    chip_name = "Apple " + re.sub(r"\s+", " ", match.group(1).strip())
    generation = _positive_int(match.group("generation"), 0)
    tier = str(match.group("tier") or "base").strip().lower()
    return chip_name, generation, tier or "base"


@lru_cache(maxsize=1)
def _apple_gpu_core_count() -> int:
    if platform.system() != "Darwin":
        return 0
    try:
        proc = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2.5,
        )
    except Exception:
        return 0
    text = str(proc.stdout or "")
    for pattern in (
        r"Total Number of Cores:\s*(\d+)",
        r"GPU Cores:\s*(\d+)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _positive_int(match.group(1), 0)
    return 0


def _apple_neural_engine_core_estimate(chip_generation: int) -> int:
    # Apple does not expose ANE cores through a stable public sysctl. For M-series
    # scheduling we only need a slot estimate, and all current M-series chips
    # expose a Core ML / Neural Engine path with a 16-core class ANE.
    return 16 if chip_generation > 0 else 0


@lru_cache(maxsize=1)
def hardware_profile() -> dict:
    logical = max(1, os.cpu_count() or 1)
    physical = _sysctl_int("hw.physicalcpu") or logical
    performance_cores = _sysctl_int("hw.perflevel0.physicalcpu")
    efficiency_cores = _sysctl_int("hw.perflevel1.physicalcpu")
    memory_bytes = _sysctl_int("hw.memsize")
    brand_string = _sysctl_str("machdep.cpu.brand_string") or platform.processor()
    chip_name, chip_generation, chip_tier = _apple_chip_parts(brand_string)

    if performance_cores <= 0:
        # Some macOS hosts may not expose perflevel sysctl values. Use physical
        # cores as a stability-first cap for CPU-bound worker defaults.
        performance_cores = physical

    is_darwin_arm = platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}
    accelerators = {
        "xcodebuild": bool(shutil.which("xcodebuild")),
        "swift": bool(shutil.which("swift")),
        "mlx": importlib.util.find_spec("mlx") is not None,
        "mlx_whisper": importlib.util.find_spec("mlx_whisper") is not None,
        "torch": importlib.util.find_spec("torch") is not None,
        "coreml_cli": bool(shutil.which("argmax-cli") or shutil.which("whisperkit-cli")),
        "cuda_cli": bool(shutil.which("nvidia-smi")),
        "directml": importlib.util.find_spec("torch_directml") is not None,
        "openvino": importlib.util.find_spec("openvino") is not None,
    }
    worker = PROJECT_ROOT / "experiments" / "whisperkit_persistent_worker" / ".build" / "release" / "WhisperKitPersistentWorker"
    accelerators["whisperkit_persistent_worker"] = worker.exists() or bool(shutil.which("WhisperKitPersistentWorker"))
    if accelerators["cuda_cli"]:
        accelerators["cuda"] = True
    gpu_cores = _apple_gpu_core_count() if is_darwin_arm else 0
    neural_engine_cores = _apple_neural_engine_core_estimate(chip_generation) if is_darwin_arm else 0
    if is_darwin_arm:
        # Metal is hardware-provided on Apple Silicon. MLX availability is
        # tracked separately because STT model routing still needs mlx-whisper.
        accelerators["metal"] = True
        accelerators["metal_gpu"] = True
        accelerators["metal_gpu_cores"] = gpu_cores
        # Apple Neural Engine access is generally routed through Core ML /
        # WhisperKit rather than direct Python APIs.
        accelerators["neural_engine_path"] = bool(
            accelerators["coreml_cli"] or accelerators["whisperkit_persistent_worker"] or neural_engine_cores
        )

    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "brand_string": brand_string,
        "chip_name": chip_name,
        "chip_generation": chip_generation,
        "chip_tier": chip_tier,
        "logical_cores": logical,
        "physical_cores": max(1, physical),
        "performance_cores": max(1, performance_cores),
        "efficiency_cores": max(0, efficiency_cores),
        "gpu_cores": max(0, gpu_cores),
        "neural_engine_cores": max(0, neural_engine_cores),
        "memory_bytes": max(0, memory_bytes),
        "accelerators": accelerators,
    }


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
    max_profile = _safe_bool(settings.get("runtime_hardware_acceleration_enabled"), True) and performance_profile(settings) == "max"

    if generation >= 5:
        balanced = performance + min(efficiency, 3)
        wide = logical
        sustained = performance + min(efficiency, 4)
        follower_start_percent = 20
        chip_reason = "m5_or_newer_perf_plus_efficiency"
    elif generation >= 3:
        balanced = performance + min(efficiency, 2)
        wide = performance + min(efficiency, 4)
        sustained = performance + min(efficiency, 3)
        follower_start_percent = 25
        chip_reason = "m3_m4_balanced_efficiency"
    else:
        balanced = performance + min(efficiency, 2)
        wide = performance + min(efficiency, 4)
        sustained = balanced
        follower_start_percent = 25
        chip_reason = "generic_apple_silicon"

    logical_cap = logical if max_profile else max(1, logical - 1)
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
    interactive_reserve = 0 if max_profile else (1 if logical > 1 else 0)
    emergency_reserve = 1 if logical > 1 else 0
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
            "cut_pioneer_workers": wide,
            "cut_follower_workers": balanced,
            "cut_follower_stream_start_percent": follower_start_percent,
            "cut_follower_stream_batch_size": max(8, balanced * 2),
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
    if hardware_max_profile_enabled(settings):
        default = max(perf, physical, logical)
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
    if task_text in {
        "cpu",
        "io",
        "prefetch",
        "cut_pioneer",
        "cut_follower",
        "stt",
        "lora",
        "cleanup",
        "shutdown",
        "exit",
    }:
        return 0
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
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔", "아니오"}
    return bool(value)


def _qt_gpu_rendering_settings_request() -> tuple[bool | None, bool | None, str]:
    try:
        from core.runtime import config as runtime_config

        settings_path = Path(runtime_config.DATASET_DIR) / "user_settings.json"
        dataset_dir = runtime_config.DATASET_DIR
    except Exception:
        settings_path = PROJECT_ROOT / "dataset" / "user_settings.json"
        dataset_dir = str(settings_path.parent)
    settings = hardcoded_default_settings(
        dataset_dir=dataset_dir,
        include_custom_defaults=True,
        include_folder_settings=False,
    )
    data = read_json_file(settings_path, default={}, expected_type=dict, context="qt_gpu_settings", log_errors=False)
    if isinstance(data, dict):
        settings.update(data)
    scope = str(settings.get("editor_rendering_gpu_scope", settings.get("gpu_rendering_scope", "")) or "").strip().lower()
    gpu_requested = True if scope in {"all", "whole", "full", "global", "전체"} else None
    force_requested = None
    if "editor_rendering_force_qt_opengl" in settings:
        force_requested = _safe_bool(settings.get("editor_rendering_force_qt_opengl"), False)
    elif "force_qt_opengl" in settings:
        force_requested = _safe_bool(settings.get("force_qt_opengl"), False)
    backend = str(
        settings.get(
            "editor_rendering_qt_backend",
            settings.get("gpu_qt_backend", "auto"),
        )
        or "auto"
    ).strip().lower()
    if backend not in {"auto", "metal", "opengl"}:
        backend = "auto"
    return gpu_requested, force_requested, backend


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


def qt_application_font_family() -> str:
    """Return the concrete Qt application font for the current platform."""
    try:
        from core.runtime import config

        configured = str(getattr(config, "FONT", "") or "").strip()
    except Exception:
        configured = ""
    if platform.system() == "Darwin":
        return configured or "Apple SD Gothic Neo"
    return configured


def configure_qt_application_font() -> str:
    """Pin QApplication to a real platform font before widgets trigger aliases."""
    family = qt_application_font_family()
    if not family:
        return ""
    try:
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QApplication
    except Exception:
        return ""
    app = QApplication.instance()
    if app is None:
        return ""
    try:
        font = QFont(app.font())
        if str(font.family() or "") == family:
            return family
        font.setFamily(family)
        app.setFont(font)
        return family
    except Exception:
        return ""


def configure_qt_runtime() -> None:
    """Tune Qt global caches after QApplication is created."""
    configure_qt_application_font()
    try:
        from PyQt6.QtGui import QPixmapCache
    except Exception:
        return

    profile = hardware_profile()
    memory_gb = float(profile.get("memory_bytes") or 0) / (1024 ** 3)
    if memory_gb >= 32:
        limit_kb = 131072
    elif memory_gb >= 16:
        limit_kb = 65536
    else:
        limit_kb = 32768
    try:
        QPixmapCache.setCacheLimit(max(QPixmapCache.cacheLimit(), limit_kb))
    except Exception:
        pass


def configure_qt_gpu_rendering_before_app() -> None:
    """Apply Qt OpenGL setup before QApplication is created.

    Normal app launches default to GPU compositing/OpenGL. Tests and offscreen
    runs remain conservative unless the caller explicitly opts in with env vars.
    """
    if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
        return
    # Default off in real app runs too. On macOS, forcing global Qt OpenGL can
    # crash QtMultimedia/video widgets with Segmentation fault: 11.
    gpu_default = "0"
    settings_gpu, settings_force, settings_backend = _qt_gpu_rendering_settings_request()
    gpu_value = os.environ.get("AI_SUBTITLE_GPU_RENDERING")
    gpu_requested = (
        str(gpu_value if gpu_value is not None else gpu_default).lower() in {"1", "true", "yes", "on"}
        if gpu_value is not None or settings_gpu is None
        else bool(settings_gpu)
    )
    if not gpu_requested:
        return
    force_value = os.environ.get("AI_SUBTITLE_FORCE_QT_OPENGL")
    force_requested = (
        str(force_value if force_value is not None else "0").lower() in {"1", "true", "yes", "on"}
        if force_value is not None or settings_force is None
        else bool(settings_force)
    )
    backend_value = str(os.environ.get("AI_SUBTITLE_QT_GPU_BACKEND", settings_backend or "auto") or "auto").strip().lower()
    if backend_value not in {"auto", "metal", "opengl"}:
        backend_value = "auto"
    if platform.system() == "Darwin" and force_value is None and backend_value != "opengl":
        force_requested = False
    if force_requested:
        backend_value = "opengl"
    if backend_value == "auto":
        backend_value = "metal" if platform.system() == "Darwin" else "opengl"

    if backend_value == "metal" and platform.system() == "Darwin":
        os.environ.setdefault("QSG_RHI_BACKEND", "metal")
        if str(os.environ.get("QT_QUICK_BACKEND", "") or "").strip().lower() == "hardware":
            os.environ.pop("QT_QUICK_BACKEND", None)
        return

    if not force_requested:
        return

    os.environ.setdefault("QT_OPENGL", "desktop")
    os.environ.setdefault("QSG_RHI_BACKEND", "opengl")

    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QSurfaceFormat
        from PyQt6.QtWidgets import QApplication
    except Exception:
        return

    for attr in (
        getattr(Qt.ApplicationAttribute, "AA_ShareOpenGLContexts", None),
        getattr(Qt.ApplicationAttribute, "AA_UseDesktopOpenGL", None),
    ):
        if attr is None:
            continue
        try:
            QApplication.setAttribute(attr, True)
        except Exception:
            pass

    try:
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        if platform.system() == "Darwin":
            fmt.setVersion(3, 2)
        else:
            fmt.setVersion(3, 3)
        fmt.setDepthBufferSize(0)
        fmt.setStencilBufferSize(0)
        fmt.setSamples(0)
        fmt.setSwapInterval(0)
        QSurfaceFormat.setDefaultFormat(fmt)
    except Exception:
        pass
