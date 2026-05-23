from __future__ import annotations

from typing import Any

from core.runtime.setting_utils import setting_bool


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
            if editor is not None and subtitle_llm_runtime_active(editor):
                labels.append("subtitle_llm")
            if editor is not None and subtitle_optimize_runtime_active(editor):
                labels.append("subtitle_optimize")
            if editor is not None and roughcut_llm_runtime_active(editor):
                labels.append("roughcut_llm")
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
    "active_runtime_labels_from_window",
    "apple_m_accelerator_flag_report",
    "cut_boundary_runtime_active",
    "roughcut_llm_runtime_active",
    "subtitle_llm_runtime_active",
    "subtitle_optimize_runtime_active",
]
