from __future__ import annotations

from typing import Any

from core.performance import hardware_profile, runtime_scheduler_reserve_cores
from core.runtime.setting_utils import setting_bool

LIVE_NLE_PROJECTION_BUDGET_SCHEMA = "ai_subtitle_studio.live_nle_projection_budget.v1"
_FOREGROUND_ACTION_LABELS = {"save", "export", "close", "exit", "shutdown", "cleanup"}


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _deduped_labels(values: Any) -> list[str]:
    labels: list[str] = []
    for item in list(values or []):
        label = str(item or "").strip().lower()
        if label and label not in labels:
            labels.append(label)
    return labels


def live_nle_projection_scheduler_budget(
    settings: dict[str, Any] | None = None,
    *,
    active_labels: list[str] | tuple[str, ...] | None = None,
    runtime_resource: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the read-only live NLE projection budget.

    Live STT/VAD/NLE track visibility is a UI/status projection layer. It must
    not request worker threads from the subtitle conversion path; it should use
    existing row snapshots, coalesce status updates, and drop stale preview
    frames when the runtime is busy.
    """
    data = dict(settings or {})
    resource = dict(runtime_resource or {})
    labels = _deduped_labels(active_labels or resource.get("active_labels") or [])
    exit_active = "exit" in labels
    pressure_stage = str(
        resource.get("pressure_stage")
        or resource.get("memory_pressure_stage")
        or "normal"
    ).strip().lower()
    try:
        profile = dict(hardware_profile() or {})
    except Exception:
        profile = {}
    logical = max(1, _int_value(profile.get("logical_cores"), 1))
    configured_reserve = max(
        0,
        _int_value(
            runtime_scheduler_reserve_cores(
                data,
                task="subtitle_prepass",
                exiting=exit_active or pressure_stage == "exit",
            ),
            0,
        ),
    )
    required_reserve = 0 if exit_active or pressure_stage == "exit" else (1 if logical > 1 else 0)
    interactive_reserve = max(configured_reserve, required_reserve)
    available_worker_budget = max(1, logical - interactive_reserve)
    foreground_labels = [label for label in labels if label in _FOREGROUND_ACTION_LABELS]
    pressure_throttled = pressure_stage in {"warning", "critical", "exit"}
    projection_allowed = pressure_stage not in {"critical", "exit"} and "exit" not in labels
    coalesce_interval_ms = 900 if (foreground_labels or pressure_throttled) else 450
    return {
        "schema": LIVE_NLE_PROJECTION_BUDGET_SCHEMA,
        "projection_allowed": bool(projection_allowed),
        "projection_mode": "coalesced_snapshot",
        "dedicated_worker_count": 0,
        "max_projection_workers": 0,
        "uses_existing_row_snapshots": True,
        "shares_subtitle_worker_pool": False,
        "coalesces_updates": True,
        "drops_stale_preview_frames": True,
        "coalesce_interval_ms": int(coalesce_interval_ms),
        "interactive_reserve_cores": int(interactive_reserve),
        "required_interactive_reserve_cores": int(required_reserve),
        "available_worker_budget": int(available_worker_budget),
        "pressure_stage": pressure_stage or "normal",
        "active_labels": labels,
        "foreground_action_labels": foreground_labels,
        "foreground_action_active": bool(foreground_labels),
        "vad_audio_prep_worker_cap": min(2, available_worker_budget),
        "stt1_policy": "current_high_quality_native_path",
        "stt2_policy": "selective_quality_preserving_budget",
        "word_precision_policy": "selective_quality_preserving_budget",
        "accelerator_terms": ["ANE", "GPU", "CPU"],
        "quality_policy": "final_authority_unchanged",
    }


def apple_m_accelerator_flag_report(settings: dict[str, Any] | None) -> dict[str, bool]:
    """Return boolean accelerator flags for the Apple Silicon pipeline report."""
    data = dict(settings or {})
    return {
        "whisperkit_native_allocator_can_raise_workers": setting_bool(
            data.get("stt_whisperkit_native_allocator_can_raise_workers"),
            True,
        ),
        "audio_torch_gpu_enabled": setting_bool(data.get("audio_torch_gpu_enabled"), True),
        "ffmpeg_videotoolbox_decode_enabled": setting_bool(
            data.get("ffmpeg_videotoolbox_decode_enabled"),
            True,
        ),
        "scan_cut_pioneer_pipe_hwaccel_enabled": setting_bool(
            data.get("scan_cut_pioneer_pipe_hwaccel_enabled"),
            True,
        ),
        "lora_gpu_acceleration_enabled": setting_bool(data.get("lora_gpu_acceleration_enabled"), True),
        "stt_window_ensemble": setting_bool(data.get("stt_window_ensemble_enabled"), False),
        "full_parallel_stt_experiment": setting_bool(
            data.get("apple_m_aggressive_full_parallel_stt_enabled"),
            False,
        ),
    }


def normalize_accelerator_name(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "cpu"
    if raw in {"ane", "ne", "npu", "coreml", "neural_engine", "apple-neural-engine"}:
        return "npu"
    if raw in {"gpu", "cuda", "mps", "metal", "mlx"}:
        return "gpu"
    return "cpu"


def mixed_accelerator_parallelism_floor(task: str, accelerators: list[str], workload: int) -> int:
    task_key = str(task or "").strip().lower()
    if workload <= 1 or task_key not in {
        "stt",
        "stt_window",
        "stt_precision",
        "vad",
        "diarize",
        "audio_ml",
        "ml",
        "subtitle_llm",
        "subtitle_optimize",
        "roughcut_llm",
    }:
        return 0
    normalized: list[str] = []
    for item in accelerators:
        name = normalize_accelerator_name(item)
        if name not in normalized:
            normalized.append(name)
    non_cpu = [item for item in normalized if item != "cpu"]
    if len(non_cpu) >= 2:
        if task_key in {"stt", "stt_window", "stt_precision"}:
            return max(2, min(int(workload), len(non_cpu) + 1))
        return max(2, min(int(workload), len(non_cpu) + (1 if "cpu" in normalized else 0)))
    if len(non_cpu) == 1 and "cpu" in normalized:
        return min(int(workload), 2)
    return 0


def _thread_is_alive(owner: Any, attr: str) -> bool:
    try:
        thread = getattr(owner, attr, None)
        return bool(thread is not None and thread.is_alive())
    except Exception:
        return False


def cut_boundary_runtime_active(backend: Any) -> bool:
    return any(
        _thread_is_alive(backend, attr)
        for attr in ("_cut_boundary_prescan_thread", "_cut_boundary_follower_thread")
    )


def subtitle_llm_runtime_active(editor: Any) -> bool:
    try:
        stage = str(getattr(editor, "_last_live_processing_stage", "") or "")
    except Exception:
        stage = ""
    return "자막 LLM" in stage or "subtitle_llm" in stage.lower()


def subtitle_optimize_runtime_active(editor: Any) -> bool:
    try:
        stage = str(getattr(editor, "_last_live_processing_stage", "") or "")
    except Exception:
        stage = ""
    lowered = stage.lower()
    return any(
        token in lowered
        for token in (
            "subtitle_optimize",
            "subtitle optimize",
            "optimizer",
            "stt+자막 llm",
            "교정/분리",
        )
    ) or "자막 최적화" in stage


def roughcut_llm_runtime_active(editor: Any) -> bool:
    try:
        status = str(getattr(editor, "_roughcut_draft_status", "") or "").strip().lower()
        if status in {"queued", "running", "saving"}:
            return True
        if bool(getattr(editor, "_roughcut_draft_pending", False)):
            return True
        return _thread_is_alive(editor, "_roughcut_draft_thread")
    except Exception:
        return False


def active_runtime_labels_from_window(window: Any, *, exit_mode: bool = False) -> list[str]:
    labels: list[str] = []
    if window is not None:
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
                if backend is not None and cut_boundary_runtime_active(backend):
                    labels.append("cut_boundary")
            except Exception:
                continue
        try:
            editor = getattr(window, "_editor_widget", None)
            if editor is not None and bool(getattr(editor, "_is_ai_processing", False)):
                labels.append("editor")
            if editor is not None and bool(getattr(editor, "_stt_mode_enabled", False)):
                labels.append("stt")
            if editor is not None and bool(getattr(editor, "_stt_vad_running", False)):
                labels.append("vad")
            if editor is not None and subtitle_llm_runtime_active(editor):
                labels.append("subtitle_llm")
            if editor is not None and subtitle_optimize_runtime_active(editor):
                labels.append("subtitle_optimize")
            if editor is not None and roughcut_llm_runtime_active(editor):
                labels.append("roughcut_llm")
            if editor is not None and (
                bool(getattr(editor, "_deferred_project_save_pending", False))
                or bool(getattr(editor, "_deferred_project_save_running", False))
            ):
                labels.append("save")
            if editor is not None and (
                bool(getattr(editor, "_auto_export_video_running", False))
                or bool(getattr(editor, "_subtitle_overlay_export_running", False))
            ):
                labels.append("export")
            if editor is not None and bool(getattr(editor, "_editor_widget_closing", False)):
                labels.append("close")
        except Exception:
            pass
    if exit_mode:
        labels.append("exit")
    deduped: list[str] = []
    for label in labels:
        if label not in deduped:
            deduped.append(label)
    return deduped


__all__ = [
    "LIVE_NLE_PROJECTION_BUDGET_SCHEMA",
    "active_runtime_labels_from_window",
    "apple_m_accelerator_flag_report",
    "cut_boundary_runtime_active",
    "live_nle_projection_scheduler_budget",
    "mixed_accelerator_parallelism_floor",
    "normalize_accelerator_name",
    "roughcut_llm_runtime_active",
    "subtitle_llm_runtime_active",
    "subtitle_optimize_runtime_active",
]
