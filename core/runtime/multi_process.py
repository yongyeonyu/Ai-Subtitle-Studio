from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from core.performance import (
    adaptive_llm_worker_count,
    adaptive_worker_count,
    apple_silicon_runtime_profile,
    atomic_write_json,
    current_resource_snapshot,
    distributed_worker_ceiling,
    hardware_profile,
    native_thread_budget,
    performance_profile,
    runtime_scheduler_reserve_cores,
)
from core.native_macos_acceleration import (
    EXPERIMENTAL_SWIFT_POLICY_KEYS,
    mac_native_backend_plan,
    mac_native_runtime_overrides,
)
from core.runtime import config
from core.runtime.memory_manager import process_rss_bytes, runtime_disk_cache_usage


_TRUE_VALUES = {"1", "true", "yes", "on", "enabled", "enable"}
_FALSE_VALUES = {"0", "false", "no", "off", "disabled", "disable", "끄기", "끔"}

# BENCH LOCK 2026-05-09 (Apple M5, X5_시승기_후반.MP4 4K HEVC):
# cut-boundary pioneer 4 workers and follower 4-way CPU verification beat
# 6/8/10-way fanout and MPS for this workload. Do not tune these constants
# without rerunning the recorded cut-boundary benchmark matrix.
BENCH_LOCKED_CUT_PIONEER_WORKERS = 4
BENCH_LOCKED_CUT_FOLLOWER_WORKERS = 4
BENCH_LOCKED_CUT_FOLLOWER_OUTER_SPLITS = 4


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _positive_int(value: Any, default: int = 0) -> int:
    parsed = _int_value(value, default)
    return parsed if parsed > 0 else default


def _setting_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return bool(default)


def runtime_monitor_dir() -> Path:
    path = Path(config.OUTPUT_DIR) / "runtime_monitor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def manual_lora_runtime_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a manual-LoRA runtime profile with one core reserved for stop/exit."""
    merged = dict(settings or {})
    profile = hardware_profile()
    logical = max(1, int(profile.get("logical_cores", 1) or 1))
    reserve = 1 if logical > 1 else 0
    # BENCH LOCK 2026-05-09: CPU fanout kept improving up to all 10 logical
    # cores, but manual LoRA must leave one core for immediate stop/exit.
    native_threads = max(1, logical - reserve)
    merged["runtime_performance_profile"] = "max"
    merged["runtime_hardware_acceleration_enabled"] = True
    merged["runtime_scheduler_auto_enabled"] = True
    merged["runtime_scheduler_reserve_cores"] = reserve
    merged["runtime_native_threads_auto_enabled"] = True
    merged["runtime_native_threads"] = native_threads
    merged["runtime_manual_lora_full_speed"] = True
    return merged


def _core_topology_counts(profile: dict[str, Any] | None = None) -> tuple[int, int, int, int]:
    data = dict(profile or {})
    logical = max(1, _int_value(data.get("logical_cores"), os.cpu_count() or 1))
    physical = max(1, _int_value(data.get("physical_cores"), logical))
    performance = max(1, _int_value(data.get("performance_cores"), physical))
    efficiency = max(0, _int_value(data.get("efficiency_cores"), max(0, logical - performance)))
    performance = max(1, min(performance, logical))
    efficiency = max(0, min(efficiency, max(0, logical - performance)))
    return logical, physical, performance, efficiency


def apply_apple_m_subtitle_pipeline_plan(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply one Apple Silicon worker budget across the whole subtitle pipeline.

    The slow cases reported by the user came from each stage choosing its own
    conservative defaults: cut-boundary workers, FFmpeg chunking, STT, word
    timestamp rechecks, and LLM post-processing were not looking at the same
    Apple M core budget.  This plan keeps quality-critical STT behavior
    selective while letting CPU/native stages fan out over performance cores
    plus a bounded number of efficiency cores.
    """
    merged = dict(settings or {})
    if not _setting_bool(merged.get("apple_m_pipeline_parallel_enabled"), True):
        return merged
    if not bool(getattr(config, "IS_APPLE_SILICON", False)):
        return merged

    try:
        profile = dict(hardware_profile() or {})
    except Exception:
        profile = {}
    logical, physical, performance, efficiency = _core_topology_counts(profile)
    chip_settings = dict(merged)
    chip_settings.setdefault("runtime_performance_profile", "max")
    chip_settings.setdefault("runtime_hardware_acceleration_enabled", True)
    chip_plan = (
        apple_silicon_runtime_profile(chip_settings, profile=profile)
        if _setting_bool(merged.get("apple_m_chip_aware_scheduler_enabled"), True)
        else {}
    )
    chip_pipeline = dict(chip_plan.get("pipeline") or {})
    chip_cpu = dict(chip_plan.get("cpu") or {})
    chip_npu = dict(chip_plan.get("npu") or {})

    balanced_workers = max(1, min(logical, performance + min(efficiency, 2)))
    wide_workers = max(1, min(logical, performance + min(efficiency, 4)))
    llm_workers = max(1, min(logical, max(2, min(6, performance + (1 if efficiency >= 4 else 0)))))
    local_llm_workers = 2
    memory_gb = float(profile.get("memory_bytes", 0) or 0) / (1024 ** 3)
    if memory_gb >= 32 and logical >= 12:
        local_llm_workers = 3

    interactive_reserve = _positive_int(chip_plan.get("interactive_reserve_cores"), 1 if logical > 1 else 0)
    if chip_pipeline:
        balanced_workers = _positive_int(chip_pipeline.get("cut_follower_workers"), balanced_workers)
        wide_workers = _positive_int(chip_pipeline.get("audio_workers"), wide_workers)
        llm_workers = _positive_int(chip_pipeline.get("llm_resource_max"), llm_workers)
        local_llm_workers = _positive_int(chip_pipeline.get("local_llm_workers"), local_llm_workers)
    native_threads = _positive_int(chip_cpu.get("native_threads"), max(1, logical - interactive_reserve))
    ffmpeg_threads = _positive_int(chip_pipeline.get("ffmpeg_filter_threads"), balanced_workers)
    direct_ffmpeg_chunk_min_sec = float(chip_pipeline.get("direct_ffmpeg_chunk_min_sec", 1.0) or 1.0)
    # BENCH LOCK 2026-05-10: keep follower streaming deliberately less chatty.
    # The 20%/8-row/0.1s M5 path caused frequent provisional/formal merge churn
    # and was slower than the earlier benchmark-stable cadence on long 4K clips.
    stream_start_percent = max(25, _positive_int(chip_pipeline.get("cut_follower_stream_start_percent"), 25))
    stream_batch_size = max(16, _positive_int(chip_pipeline.get("cut_follower_stream_batch_size"), 16))
    stt_primary_slots = _positive_int(chip_pipeline.get("stt_primary_slots"), 1)
    npu_slots = _positive_int(chip_npu.get("coreml_slots"), 0)

    respect_manual = _setting_bool(merged.get("apple_m_pipeline_respect_manual_worker_settings"), False)

    def set_opt(key: str, value: Any, *, manual_zero_is_auto: bool = True) -> None:
        if respect_manual and key in merged:
            current = merged.get(key)
            if current not in (None, "") and (manual_zero_is_auto or _positive_int(current, 0) > 0):
                return
        merged[key] = value

    set_opt("runtime_performance_profile", "max")
    set_opt("runtime_hardware_acceleration_enabled", True)
    set_opt("runtime_backend_autotune_enabled", True)
    set_opt("runtime_native_threads_auto_enabled", True)
    set_opt("runtime_native_threads", native_threads)
    set_opt("runtime_scheduler_auto_enabled", True)
    set_opt("runtime_scheduler_reserve_cores", int(interactive_reserve))
    set_opt("runtime_scheduler_ramp_up_enabled", False)

    set_opt("stt_backend_policy", "native")
    set_opt("whisperkit_native_auto_enabled", True)
    set_opt("stt_persistent_runtime_reuse_enabled", True)
    # BENCH LOCK 2026-05-09: 1-minute SRT-referenced X5 sample picked
    # WhisperKit quality for STT1 by compact CER. Turbo/MLX stays STT2/recheck.
    set_opt("stt_primary_fast_native_enabled", False)
    set_opt("stt_primary_fast_native_model", getattr(config, "WHISPERKIT_QUALITY_MODEL", "whisperkit-persistent:large-v3-v20240930_626MB"))
    set_opt("stt_primary_gpu_slots", stt_primary_slots)
    set_opt("stt_npu_coreml_slots", npu_slots)
    set_opt("stt_accelerator_distribution", "gpu+npu+cpu" if npu_slots else "gpu+cpu")
    mode = str(merged.get("subtitle_mode") or merged.get("simple_operation_mode") or "").strip().lower()
    if mode in {"high", "precise", "정밀", "높음"}:
        word_ts_mode = "selective"
        word_ts_enabled = True
        word_ts_max_segments = 32
        word_ts_max_audio_sec = 100.0
    elif mode in {"fast", "speed", "quick", "빠름"}:
        word_ts_mode = "off"
        word_ts_enabled = False
        word_ts_max_segments = 0
        word_ts_max_audio_sec = 0.0
    else:
        word_ts_mode = "selective"
        word_ts_enabled = True
        word_ts_max_segments = 16
        word_ts_max_audio_sec = 70.0
    set_opt("stt_ensemble_selective_enabled", False)
    set_opt("stt_ensemble_parallel_enabled", False)
    set_opt("stt_word_timestamps_mode", word_ts_mode)
    set_opt("stt_word_timestamps_default_enabled", False)
    set_opt("stt_word_timestamps_precision_enabled", word_ts_enabled)
    set_opt("stt_word_timestamps_precision_threshold", 72.0)
    set_opt("stt_word_timestamps_precision_max_segments", word_ts_max_segments)
    set_opt("stt_word_timestamps_precision_max_audio_sec", word_ts_max_audio_sec)
    set_opt("stt_word_timestamps_precision_keep_text", True)
    set_opt("stt_word_timestamps_precision_max_timing_shift_sec", 0.55)
    set_opt("stt_word_timestamps_precision_min_duration_ratio", 0.45)
    set_opt("stt_word_timestamps_precision_max_duration_ratio", 1.8)

    set_opt("audio_extract_backend_policy", "native")
    set_opt("macos_native_fast_audio_flatten_enabled", True)
    set_opt("io_workers", wide_workers)
    set_opt("audio_chunk_route_max_workers", wide_workers)
    set_opt("ffmpeg_filter_threads", ffmpeg_threads)
    set_opt("ff_threads", ffmpeg_threads)
    set_opt("direct_ffmpeg_chunk_min_sec", direct_ffmpeg_chunk_min_sec)

    set_opt("cut_boundary_backend_policy", "native")
    set_opt("scan_cut_pioneer_workers", BENCH_LOCKED_CUT_PIONEER_WORKERS)
    set_opt("scan_cut_verify_workers", BENCH_LOCKED_CUT_FOLLOWER_WORKERS)
    set_opt("scan_cut_pioneer_cpu_max_workers", BENCH_LOCKED_CUT_PIONEER_WORKERS)
    set_opt("scan_cut_follower_cpu_max_workers", BENCH_LOCKED_CUT_FOLLOWER_WORKERS)
    set_opt("scan_cut_follower_outer_splits", BENCH_LOCKED_CUT_FOLLOWER_OUTER_SPLITS)
    set_opt("scan_cut_pioneer_worker_overlap_steps", 1)
    set_opt("scan_cut_cv2_threads_per_worker", 1)
    set_opt("scan_cut_follower_stream_start_percent", stream_start_percent)
    set_opt("scan_cut_follower_stream_batch_size", max(BENCH_LOCKED_CUT_FOLLOWER_OUTER_SPLITS, stream_batch_size))
    set_opt("scan_cut_follower_stream_min_interval_sec", 0.75)
    # The follower verifier compares many tiny thumbnail grids. On Apple
    # Silicon this micro-kernel is usually faster on CPU unless the user
    # explicitly opts into MPS for benchmarking, so keep the default off but
    # do not override an explicit user opt-in.
    if merged.get("scan_cut_follower_mps_enabled") in (None, ""):
        merged["scan_cut_follower_mps_enabled"] = False
    set_opt("scan_cut_follower_dense_flow_enabled", True)

    set_opt("llm_threads_auto_enabled", True)
    set_opt("llm_workers_auto_enabled", True)
    set_opt("subtitle_native_prepass_workers", wide_workers)
    set_opt("subtitle_native_prepass_workers_resource_max", wide_workers)
    native_overrides = mac_native_runtime_overrides(merged)
    for key, value in native_overrides.items():
        # Native policy helpers are benchmark-gated centrally. Apply them
        # directly so stale manual settings cannot re-enable a slower path.
        if key in EXPERIMENTAL_SWIFT_POLICY_KEYS or key == "native_swift_policy_experimental_enabled":
            merged[key] = value
        else:
            set_opt(key, value)
    set_opt("llm_workers", min(llm_workers, 4))
    set_opt("llm_threads_resource_max", llm_workers)
    set_opt("local_ollama_llm_max_workers", local_llm_workers)
    set_opt("roughcut_llm_threads_auto_enabled", True)
    set_opt("roughcut_llm_threads_resource_max", max(1, min(4, performance)))

    set_opt("editor_live_stt_preview_follow_video_enabled", False)
    set_opt("editor_live_stt_preview_follow_interval_sec", 2.0)

    merged["_apple_m_pipeline_parallel_plan"] = {
        "schema": "ai_subtitle_studio.apple_m_pipeline.v2",
        "chip_aware": bool(chip_pipeline),
        "chip_profile": chip_plan,
        "logical_cores": logical,
        "physical_cores": physical,
        "performance_cores": performance,
        "efficiency_cores": efficiency,
        "gpu_cores": int(profile.get("gpu_cores", 0) or 0),
        "neural_engine_cores": int(profile.get("neural_engine_cores", 0) or 0),
        "native_threads": native_threads,
        "audio_workers": wide_workers,
        "cut_pioneer_workers": BENCH_LOCKED_CUT_PIONEER_WORKERS,
        "cut_follower_workers": BENCH_LOCKED_CUT_FOLLOWER_WORKERS,
        "cut_follower_outer_splits": BENCH_LOCKED_CUT_FOLLOWER_OUTER_SPLITS,
        "llm_workers": min(llm_workers, 4),
        "llm_resource_max": llm_workers,
        "local_llm_workers": local_llm_workers,
        "stt_primary_gpu_slots": stt_primary_slots,
        "stt_npu_coreml_slots": npu_slots,
        "native_cpp_llm_macro_groups": bool(native_overrides["native_cpp_llm_macro_groups_enabled"]),
        "native_swift_quality_min_segments": int(native_overrides["native_swift_quality_scoring_min_segments"]),
        "native_swift_common_split_min_items": int(native_overrides["native_swift_common_split_min_items"]),
        "native_backend_plan": mac_native_backend_plan(merged),
    }
    return merged


def _normalize_accelerator_name(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "cpu"
    if raw in {"ane", "ne", "npu", "coreml", "neural_engine", "apple-neural-engine"}:
        return "npu"
    if raw in {"gpu", "cuda", "mps", "metal", "mlx"}:
        return "gpu"
    return "cpu"


def _mixed_accelerator_parallelism_floor(task: str, accelerators: list[str], workload: int) -> int:
    task_key = str(task or "").strip().lower()
    if workload <= 1 or task_key not in {
        "stt",
        "vad",
        "diarize",
        "audio_ml",
        "ml",
        "subtitle_llm",
        "roughcut_llm",
    }:
        return 0
    normalized: list[str] = []
    for item in accelerators:
        name = _normalize_accelerator_name(item)
        if name not in normalized:
            normalized.append(name)
    non_cpu = [item for item in normalized if item != "cpu"]
    if len(non_cpu) >= 2:
        return max(2, min(int(workload), len(non_cpu) + (1 if "cpu" in normalized else 0)))
    if len(non_cpu) == 1 and "cpu" in normalized:
        return min(int(workload), 2)
    return 0


def _cut_boundary_topology_worker_limit(
    task: str,
    settings: dict[str, Any],
    *,
    workload: int,
    accelerators: list[str],
) -> tuple[int, dict[str, Any]]:
    task_key = str(task or "").strip().lower()
    if task_key not in {"cut_pioneer", "cut_follower"}:
        return 0, {}

    workload = max(1, _positive_int(workload, 1))
    try:
        profile = dict(hardware_profile() or {})
    except Exception:
        profile = {}
    logical = max(1, int(profile.get("logical_cores", 1) or 1))
    physical = max(1, int(profile.get("physical_cores", logical) or logical))
    perf = max(1, int(profile.get("performance_cores", physical) or physical))
    efficiency = max(0, int(profile.get("efficiency_cores", 0) or 0))
    if task_key == "cut_follower" and any(name != "cpu" for name in accelerators):
        return 1, {
            "reason": "single_gpu_queue",
            "logical_cores": logical,
            "performance_cores": perf,
            "efficiency_cores": efficiency,
        }

    setting_key = (
        "scan_cut_pioneer_cpu_max_workers"
        if task_key == "cut_pioneer"
        else "scan_cut_follower_cpu_max_workers"
    )
    configured = _positive_int(settings.get(setting_key), 0)
    if configured > 0:
        limit = configured
        reason = "configured"
    elif task_key == "cut_pioneer":
        # BENCH LOCK 2026-05-09: cut-boundary pioneer was fastest and most
        # stable at 4 workers on the real 4K HEVC benchmark. Larger topology
        # fanout created more decode contention and can miss seam candidates
        # without overlap, so topology does not auto-expand this task anymore.
        limit = BENCH_LOCKED_CUT_PIONEER_WORKERS
        reason = "bench_locked_four_way_pioneer"
    else:
        limit = BENCH_LOCKED_CUT_FOLLOWER_WORKERS
        reason = "bench_locked_four_way_follower"

    limit = max(1, min(workload, logical, int(limit or 1)))
    return limit, {
        "reason": reason,
        "logical_cores": logical,
        "performance_cores": perf,
        "efficiency_cores": efficiency,
        "setting_key": setting_key,
    }


def runtime_acceleration_snapshot(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = dict(settings or {})
    acceleration_enabled = _setting_bool(settings.get("runtime_hardware_acceleration_enabled"), True)
    try:
        accelerators = dict(hardware_profile().get("accelerators", {}) or {})
    except Exception:
        accelerators = {}
    try:
        from core.audio.npu_acceleration import apple_neural_engine_available
        from core.audio.torch_acceleration import torch_acceleration_snapshot
    except Exception:
        def apple_neural_engine_available() -> bool:  # type: ignore[no-redef]
            return False

        def torch_acceleration_snapshot(*args, **kwargs) -> dict[str, Any]:  # type: ignore[no-redef]
            return {}

    torch_snapshot = dict(torch_acceleration_snapshot(settings=settings, task="runtime") or {})
    ordered_backends = list(torch_snapshot.get("ordered_backends") or [])
    hardware_gpu_available = any(
        bool(accelerators.get(key))
        for key in (
            "metal",
            "metal_gpu",
            "mlx",
            "mlx_whisper",
            "cuda",
            "cuda_cli",
            "directml",
            "openvino",
        )
    )
    gpu_available = bool(
        acceleration_enabled
        and (
            torch_snapshot.get("gpu_available")
            or hardware_gpu_available
            or accelerators.get("opencl")
        )
    )
    npu_available = bool(
        acceleration_enabled
        and _setting_bool(settings.get("runtime_npu_acceleration_enabled"), True)
        and apple_neural_engine_available()
    )
    available = {
        "cpu": True,
        "gpu": gpu_available,
        "npu": npu_available,
    }
    labels = [name.upper() for name, enabled in available.items() if enabled]
    return {
        "available": available,
        "ordered_backends": ordered_backends,
        "torch": torch_snapshot,
        "summary": " + ".join(labels) if labels else "CPU",
    }


def runtime_parallel_worker_plan(
    *,
    settings: dict[str, Any] | None = None,
    task: str,
    workload: int,
    requested: Any = None,
    minimum: int = 1,
    maximum: int | None = None,
    reserve_task: str | None = None,
    accelerators: list[str] | tuple[str, ...] | None = None,
) -> tuple[int, dict[str, Any]]:
    settings = dict(settings or {})
    reserve_key = str(reserve_task or task or "cpu").strip().lower()
    minimum_count = max(1, _positive_int(minimum, 1))
    workload_count = _positive_int(workload, 0)
    reserve_cores_count = _int_value(runtime_scheduler_reserve_cores(settings, task=reserve_key), 0)
    worker_ceiling = distributed_worker_ceiling(
        settings,
        task=reserve_key,
        workload=workload_count,
        reserve_cores=reserve_cores_count,
        minimum=minimum_count,
    )
    worker_ceiling_count = max(1, _positive_int(worker_ceiling, minimum_count))
    configured_maximum = _positive_int(maximum, worker_ceiling_count) if maximum is not None else worker_ceiling_count
    worker_upper_bound = max(minimum_count, min(max(1, configured_maximum), worker_ceiling_count))
    base_worker_upper_bound = int(worker_upper_bound)
    accelerator_names = [
        _normalize_accelerator_name(item)
        for item in list(accelerators or [])
        if str(item or "").strip()
    ]
    topology_limit, topology_meta = _cut_boundary_topology_worker_limit(
        task,
        settings,
        workload=workload_count,
        accelerators=accelerator_names,
    )
    if topology_limit > 0 and topology_limit < worker_upper_bound:
        worker_upper_bound = max(minimum_count, int(topology_limit))
    workers, meta = adaptive_worker_count(
        task=task,
        settings=settings,
        requested=requested,
        workload=workload_count,
        minimum=minimum_count,
        maximum=worker_upper_bound,
    )
    workers = max(
        minimum_count,
        min(_positive_int(workers, minimum_count), worker_upper_bound, max(1, workload_count or 1)),
    )
    meta = dict(meta or {})
    mix_floor = _mixed_accelerator_parallelism_floor(task, accelerator_names, workload_count)
    if mix_floor > int(workers or 0):
        accelerator_workers = min(worker_upper_bound, max(minimum_count, mix_floor))
        if accelerator_workers > int(workers or 0):
            workers = accelerator_workers
            meta["accelerator_mix_floor"] = int(mix_floor)
            meta["accelerator_mix_applied"] = True
        else:
            meta["accelerator_mix_floor"] = int(mix_floor)
            meta["accelerator_mix_blocked_by_ceiling"] = True
    meta["worker_ceiling"] = int(worker_ceiling_count)
    meta["worker_upper_bound"] = int(worker_upper_bound)
    if topology_limit > 0:
        meta["worker_topology_limit"] = int(topology_limit)
        meta["worker_topology"] = topology_meta
        meta["worker_topology_applied"] = int(worker_upper_bound) < int(base_worker_upper_bound)
    meta["reserve_cores"] = int(reserve_cores_count)
    meta["accelerators"] = accelerator_names
    meta["coordinator"] = "runtime_parallel_worker_plan"
    return workers, meta


def runtime_llm_worker_plan(
    *,
    settings: dict[str, Any] | None = None,
    workload: int,
    provider: str = "ollama",
    model: str = "",
    task: str = "subtitle",
    requested: Any = None,
) -> tuple[int, dict[str, Any]]:
    workers, meta = adaptive_llm_worker_count(
        settings=settings,
        requested=requested,
        workload=workload,
        provider=provider,
        model=model,
        task=task,
    )
    meta = dict(meta or {})
    meta["coordinator"] = "runtime_llm_worker_plan"
    return workers, meta


class RuntimeResourceCoordinator:
    def __init__(self, *, settings: dict[str, Any] | None = None, logger: Any = None) -> None:
        self.settings = dict(settings or {})
        self.logger = logger
        self._latest: dict[str, Any] = {}
        self._exit_mode = False
        self._last_logged_stage = ""
        self._last_snapshot_at = 0.0
        self._last_logged_at = 0.0
        self._last_system_cpu_percent = 0.0
        self._last_process_cpu_percent = 0.0
        self._last_disk_usage_at = 0.0
        self._last_disk_usage: dict[str, Any] = {"total_bytes": 0, "file_count": 0}
        self._psutil_process = None
        try:
            import psutil  # type: ignore

            self._psutil_process = psutil.Process(os.getpid())
            psutil.cpu_percent(interval=None)
            self._psutil_process.cpu_percent(interval=None)
        except Exception:
            self._psutil_process = None

    def set_exit_mode(self, active: bool) -> None:
        self._exit_mode = bool(active)

    def latest_snapshot(self) -> dict[str, Any]:
        return dict(self._latest or {})

    def poll(self, *, window=None) -> dict[str, Any]:
        now = time.time()
        resource = current_resource_snapshot(self.settings)
        rss_bytes = int(resource.get("process_rss_bytes", 0) or 0) or process_rss_bytes()
        if not self._last_disk_usage or (now - self._last_disk_usage_at) >= 60.0:
            self._last_disk_usage = runtime_disk_cache_usage()
            self._last_disk_usage_at = now
        disk_usage = dict(self._last_disk_usage or {})
        accelerators = runtime_acceleration_snapshot(self.settings)
        system_cpu = self._sample_system_cpu_percent()
        process_cpu = self._sample_process_cpu_percent()
        active = self._active_runtime_labels(window)
        stage = self._pressure_stage(resource, rss_bytes)
        snapshot = {
            "timestamp": round(now, 3),
            "profile": performance_profile(self.settings),
            "exit_mode": bool(self._exit_mode),
            "system_cpu_percent": round(system_cpu, 2),
            "process_cpu_percent": round(process_cpu, 2),
            "logical_cores": int(resource.get("logical_cores", 1) or 1),
            "physical_cores": int(resource.get("physical_cores", 1) or 1),
            "native_thread_budget": int(native_thread_budget(self.settings)),
            "rss_bytes": int(rss_bytes),
            "rss_gb": round(rss_bytes / float(1024 ** 3), 4),
            "free_memory_gb": round(float(resource.get("available_memory_bytes", 0) or 0) / float(1024 ** 3), 4),
            "free_memory_ratio": round(float(resource.get("available_memory_ratio", 1.0) or 1.0), 4),
            "disk_cache_gb": round(float(disk_usage.get("total_bytes", 0) or 0) / float(1024 ** 3), 4),
            "disk_cache_files": int(disk_usage.get("file_count", 0) or 0),
            "accelerators": accelerators,
            "pressure_stage": stage,
            "active_labels": active,
            "active_label_count": len(active),
            "resource": resource,
        }
        self._latest = snapshot
        self._last_snapshot_at = time.time()
        self._write_snapshot(snapshot)
        self._maybe_log(snapshot)
        return dict(snapshot)

    def status_html(self, snapshot: dict[str, Any] | None = None) -> str:
        data = dict(snapshot or self._latest or {})
        if not data:
            return ""
        return (
            "<div style='margin-top:6px; padding-top:5px; border-top:1px solid #22313A;'>"
            f"<div style='color:#DCE7F3; font-size:8px;'>CPU {float(data.get('system_cpu_percent', 0.0)):.0f}% · "
            f"PROC {float(data.get('process_cpu_percent', 0.0)):.0f}% · "
            f"RAM {float(data.get('rss_gb', 0.0)):.2f}GB</div>"
            "</div>"
        )

    def status_color(self, snapshot: dict[str, Any] | None = None) -> str:
        data = dict(snapshot or self._latest or {})
        stage = str(data.get("pressure_stage", "normal") or "normal")
        return {
            "normal": "#34C759",
            "warning": "#FFD60A",
            "critical": "#FF453A",
            "exit": "#FF9500",
        }.get(stage, "#34C759")

    def status_plain(self, snapshot: dict[str, Any] | None = None) -> str:
        data = dict(snapshot or self._latest or {})
        if not data:
            return ""
        active = ", ".join(str(item) for item in list(data.get("active_labels", []) or [])[:4]) or "idle"
        return (
            f"cpu={float(data.get('system_cpu_percent', 0.0)):.0f}% "
            f"proc={float(data.get('process_cpu_percent', 0.0)):.0f}% "
            f"ram={float(data.get('rss_gb', 0.0)):.2f}GB "
            f"free={float(data.get('free_memory_gb', 0.0)):.2f}GB "
            f"cache={float(data.get('disk_cache_gb', 0.0)):.2f}GB "
            f"active={active}"
        )

    def _pressure_stage(self, resource: dict[str, Any], rss_bytes: int) -> str:
        native_stage = str(resource.get("memory_pressure_stage", "") or "").strip().lower()
        if native_stage in {"warning", "critical"}:
            return native_stage
        available_ratio = float(resource.get("available_memory_ratio", 1.0) or 1.0)
        available_gb = float(resource.get("available_memory_bytes", 0) or 0) / float(1024 ** 3)
        memory_bytes = max(0, int(resource.get("memory_bytes", 0) or 0))
        rss_ratio = (float(rss_bytes) / float(memory_bytes)) if memory_bytes > 0 else 0.0
        if self._exit_mode:
            return "exit"
        if available_ratio <= 0.12 or available_gb <= 1.5 or rss_ratio >= 0.78:
            return "critical"
        if available_ratio <= 0.20 or available_gb <= 3.0 or rss_ratio >= 0.64:
            return "warning"
        return "normal"

    def _active_runtime_labels(self, window) -> list[str]:
        labels: list[str] = []
        if window is None:
            return labels
        try:
            if bool(getattr(window, "_auto_processing_active", False)):
                labels.append("auto")
        except Exception:
            pass
        for backend_name, label in (("backend", "pipeline"), ("backend_fast", "fast")):
            try:
                backend = getattr(window, backend_name, None)
                if backend is not None and bool(getattr(backend, "_active", False)):
                    labels.append(label)
            except Exception:
                pass
        try:
            editor = getattr(window, "_editor_widget", None)
            if editor is not None and bool(getattr(editor, "_is_ai_processing", False)):
                labels.append("editor")
            if editor is not None and bool(getattr(editor, "_stt_mode_enabled", False)):
                labels.append("stt")
        except Exception:
            pass
        if self._exit_mode:
            labels.append("exit")
        return labels

    def _sample_system_cpu_percent(self) -> float:
        try:
            import psutil  # type: ignore

            self._last_system_cpu_percent = float(psutil.cpu_percent(interval=None) or 0.0)
        except Exception:
            pass
        return self._last_system_cpu_percent

    def _sample_process_cpu_percent(self) -> float:
        proc = self._psutil_process
        if proc is None:
            return self._last_process_cpu_percent
        try:
            self._last_process_cpu_percent = float(proc.cpu_percent(interval=None) or 0.0)
        except Exception:
            pass
        return self._last_process_cpu_percent

    def _write_snapshot(self, snapshot: dict[str, Any]) -> None:
        try:
            atomic_write_json(runtime_monitor_dir() / "latest.json", snapshot)
        except Exception:
            pass

    def _maybe_log(self, snapshot: dict[str, Any]) -> None:
        if self.logger is None:
            return
        if not _setting_bool(self.settings.get("runtime_monitor_terminal_log_enabled"), False):
            return
        stage = str(snapshot.get("pressure_stage", "normal") or "normal")
        active_labels = list(snapshot.get("active_labels", []) or [])
        if stage == "normal" and not active_labels:
            return
        now = time.time()
        if stage == self._last_logged_stage and (now - self._last_logged_at) < 30.0:
            return
        self._last_logged_stage = stage
        self._last_logged_at = now
        try:
            self.logger.log(
                "📊 [Runtime] "
                f"CPU {float(snapshot.get('system_cpu_percent', 0.0)):.0f}% · "
                f"PROC {float(snapshot.get('process_cpu_percent', 0.0)):.0f}% · "
                f"RAM {float(snapshot.get('rss_gb', 0.0)):.2f}GB · "
                f"FREE {float(snapshot.get('free_memory_gb', 0.0)):.2f}GB · "
                f"CACHE {float(snapshot.get('disk_cache_gb', 0.0)):.2f}GB · "
                f"ACTIVE {', '.join(active_labels or ['idle'])}"
            )
        except Exception:
            pass


__all__ = [
    "RuntimeResourceCoordinator",
    "manual_lora_runtime_settings",
    "runtime_acceleration_snapshot",
    "runtime_llm_worker_plan",
    "runtime_monitor_dir",
    "runtime_parallel_worker_plan",
]
