from __future__ import annotations

from typing import Any

from core.runtime import config


def whisperkit_empty_result_fallback_model(model: str, settings: dict | None) -> str:
    """Pick a GPU-backed MLX retry model when the Swift WhisperKit worker returns nothing."""
    configured = str((settings or {}).get("stt_whisperkit_empty_fallback_model") or "").strip()
    if configured:
        return configured
    raw = str(model or "").strip().lower()
    if "turbo" in raw:
        return getattr(config, "MLX_FALLBACK_MODEL", "mlx-community/whisper-large-v3-turbo")
    return "mlx-community/whisper-large-v3-mlx"


def whisperkit_empty_fallback_overrides(
    previous_overrides: dict | None,
    fallback_model: str,
) -> dict:
    data = dict(previous_overrides or {})
    data.update(
        {
            "stt_whisperkit_empty_fallback_active": True,
            "stt_whisperkit_empty_fallback_model": fallback_model,
            "stt_npu_prefer_enabled": False,
            "whisperkit_native_auto_enabled": False,
        }
    )
    return data


def stop_empty_whisperkit_worker(owner: Any, proc) -> None:
    """Stop the native worker that produced an empty result before MLX retry."""
    try:
        from core.audio.whisperkit_persistent import stop_worker

        with owner._whisper_lock:
            if proc is not None:
                stop_worker(proc)
            if getattr(owner, "_whisperkit_runner_proc", None) is proc:
                owner._whisperkit_runner_proc = None
            if getattr(owner, "_whisper_proc", None) is proc:
                owner._whisper_proc = None
    except Exception:
        pass


__all__ = [
    "stop_empty_whisperkit_worker",
    "whisperkit_empty_fallback_overrides",
    "whisperkit_empty_result_fallback_model",
]
