# Version: 04.00.01
# Phase: MAC_NATIVE_REFACTOR
"""STT runtime routing policy for Apple Silicon native backends."""

from __future__ import annotations

from core.runtime.logger import get_logger


def resolve_runtime_whisper_model(model: str, *, log_label: str = "STT") -> tuple[str, bool]:
    raw = str(model or "").strip()
    if not raw:
        return raw, False
    from core.audio.whisper_transformers import (
        is_transformers_whisper_model,
        transformers_whisper_fallback_model,
        transformers_whisper_runtime_status,
    )

    if not is_transformers_whisper_model(raw):
        return raw, False
    available, reason = transformers_whisper_runtime_status()
    if available:
        return raw, False
    fallback_model = str(transformers_whisper_fallback_model(raw) or "").strip()
    if fallback_model and fallback_model != raw:
        get_logger().log(
            f"  ↩️ [{log_label}] Transformers Whisper 런타임 사용 불가 ({reason}) → {fallback_model} fallback"
        )
        return fallback_model, True
    get_logger().log(f"  ⚠️ [{log_label}] Transformers Whisper 런타임 사용 불가: {reason}")
    return raw, False


def whisper_runtime_accelerator(model: str, settings: dict | None = None) -> str:
    raw = str(model or "").strip()
    if not raw:
        return "cpu"
    from core.audio.torch_acceleration import torch_acceleration_snapshot
    from core.audio.whisper_coreml import is_coreml_whisper_model
    from core.audio.whisper_cpp import is_whisper_cpp_model
    from core.audio.whisperkit_persistent import is_whisperkit_persistent_model
    from core.audio.whisper_transformers import is_transformers_whisper_model

    lowered = raw.lower()
    if is_coreml_whisper_model(raw) or is_whisperkit_persistent_model(raw):
        return "npu"
    if is_whisper_cpp_model(raw):
        return "cpu"
    if (
        "mlx-community/" in lowered
        or lowered.startswith("mlx:")
        or lowered.startswith("mlx_")
        or lowered.endswith("-mlx")
        or "/mlx-" in lowered
        or "-mlx-" in lowered
    ):
        return "gpu"
    if is_transformers_whisper_model(raw):
        torch_snapshot = torch_acceleration_snapshot(settings=settings, task="stt")
        primary = str(torch_snapshot.get("primary_backend") or "cpu").strip().lower()
        return "gpu" if primary in {"mps", "cuda"} else "cpu"
    return "cpu"


def ensemble_scheduler_context(
    primary_model: str,
    secondary_model: str,
    settings: dict | None,
) -> tuple[str, str, str]:
    primary_accel = whisper_runtime_accelerator(primary_model, settings)
    secondary_accel = whisper_runtime_accelerator(secondary_model, settings)
    backend_mix = f"STT1={primary_accel.upper()} STT2={secondary_accel.upper()}"
    return primary_accel, secondary_accel, backend_mix


def ensemble_scheduler_suffix(scheduler_meta: dict, backend_mix: str) -> str:
    details: list[str] = [str(backend_mix or "").strip()]
    reductions = ",".join(scheduler_meta.get("reductions") or [])
    if reductions:
        details.append(reductions)
    if scheduler_meta.get("accelerator_mix_applied"):
        details.append(f"mix-floor={scheduler_meta.get('accelerator_mix_floor')}")
    details = [item for item in details if item]
    return f" ({', '.join(details)})" if details else ""


__all__ = [
    "ensemble_scheduler_context",
    "ensemble_scheduler_suffix",
    "resolve_runtime_whisper_model",
    "whisper_runtime_accelerator",
]
