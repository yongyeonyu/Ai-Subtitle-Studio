from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.audio.apple_speech_native import (
    APPLE_SPEECH_STT_BACKEND,
    apple_speech_benchmark_only,
    apple_speech_challenger_enabled,
    apple_speech_model,
    apple_speech_support,
)
from core.optimization.backend_policy import normalize_backend_policy, profile_backend, profile_model
from core.runtime import config


@dataclass(frozen=True, slots=True)
class SttBackendChoice:
    backend: str
    model: str
    reason: str


def _mac_mlx_alias(model: str) -> str:
    if not bool(getattr(config, "IS_MAC", False)):
        return ""
    raw = str(model or "").strip()
    lowered = raw.lower()
    if lowered in {"large-v3", "whisper-large-v3", "openai/whisper-large-v3"}:
        return "mlx-community/whisper-large-v3-mlx"
    if lowered in {
        "large-v3-turbo",
        "whisper-large-v3-turbo",
        "openai/whisper-large-v3-turbo",
    }:
        return "mlx-community/whisper-large-v3-turbo"
    return ""


def _whisper_cpp_ready(model: str) -> bool:
    try:
        from core.audio.whisper_cpp import find_whisper_cpp_binary, resolve_whisper_cpp_model_path

        return bool(find_whisper_cpp_binary() and resolve_whisper_cpp_model_path(model))
    except Exception:
        return False


def _whisperkit_ready() -> bool:
    try:
        from core.audio.whisperkit_persistent import find_whisperkit_persistent_worker

        return bool(find_whisperkit_persistent_worker())
    except Exception:
        return False


def _whisperkit_auto_enabled(settings: dict[str, Any] | None) -> bool:
    value = dict(settings or {}).get("whisperkit_native_auto_enabled", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "사용 안함", "끔"}
    return bool(value)


def _whisperkit_empty_fallback_active(settings: dict[str, Any] | None) -> bool:
    value = dict(settings or {}).get("stt_whisperkit_empty_fallback_active", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "yes", "사용", "켜짐"}
    return bool(value)


def _native_exact_mlx_model_enabled(settings: dict[str, Any] | None) -> bool:
    value = dict(settings or {}).get("stt_native_exact_mlx_model_enabled", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "yes", "사용", "켜짐"}
    return bool(value)


def _whisperkit_model(model: str) -> str:
    raw = str(model or "").strip()
    lowered = raw.lower()
    if lowered.startswith("whisperkit-persistent:"):
        raw = raw.split(":", 1)[1].strip()
        lowered = raw.lower()
    alias = _mac_mlx_alias(raw)
    if alias:
        raw = raw.split("/")[-1].replace("whisper-", "")
    elif lowered.startswith("mlx-community/"):
        candidate = raw.split("/", 1)[1]
        if "large-v3" in candidate.lower():
            raw = candidate
            if raw.startswith("whisper-"):
                raw = raw[len("whisper-"):]
            if raw.endswith("-mlx"):
                raw = raw[:-4]
    if not raw:
        raw = "large-v3-v20240930_turbo_632MB"
    lowered = raw.lower()
    if lowered in {
        "large-v3-turbo",
        "whisper-large-v3-turbo",
        "openai/whisper-large-v3-turbo",
        "openai_whisper-large-v3_turbo",
        "large-v3-v20240930_turbo_632mb",
    }:
        raw = "large-v3-v20240930_turbo_632MB"
    elif lowered in {
        "large-v3",
        "whisper-large-v3",
        "openai/whisper-large-v3",
        "openai_whisper-large-v3",
        "large-v3-v20240930_626mb",
    }:
        raw = "large-v3-v20240930_626MB"
    return f"whisperkit-persistent:{raw}"


def _whisperkit_supported_model(model: str) -> bool:
    try:
        from core.audio.whisperkit_persistent import whisperkit_model_selector, whisperkit_selector_is_supported

        return whisperkit_selector_is_supported(whisperkit_model_selector(_whisperkit_model(model)))
    except Exception:
        return False


def _unwrap_whisperkit_model(model: str) -> str:
    raw = str(model or "").strip()
    if raw.lower().startswith("whisperkit-persistent:"):
        return raw.split(":", 1)[1].strip()
    return raw


def _model_for_backend(backend: str, model: str) -> str:
    backend_key = str(backend or "").strip().lower()
    raw = str(model or "").strip()
    if backend_key == "whisperkit_persistent":
        return _whisperkit_model(raw) if _whisperkit_supported_model(raw) else raw
    if backend_key == "whisper_cpp" and raw and not raw.lower().startswith(("whisper.cpp:", "whisper_cpp:", "whisper-cpp:")):
        return f"whisper.cpp:{raw}"
    if backend_key == "mlx":
        return _mac_mlx_alias(raw) or raw
    return raw


def _infer_backend(model: str) -> str:
    raw = str(model or "").strip()
    lowered = raw.lower()
    if lowered.startswith(f"{APPLE_SPEECH_STT_BACKEND}:"):
        return APPLE_SPEECH_STT_BACKEND
    if lowered.startswith("whisperkit-persistent:"):
        return "whisperkit_persistent"
    if lowered.startswith("coreml:"):
        return "coreml"
    if lowered.startswith("transformers:"):
        return "transformers"
    if lowered in {
        "whisper-medium-komixv2",
        "seastar105/whisper-medium-komixv2",
        "o0dimplz0o/whisper-large-v3-turbo-stt-zeroth-ko-v2",
        "o0dimplz0o/whisper-large-v3-turbo-stt-zeroth-ko",
        "o0dimplz0o/fine-tuned-whisper-large-v2-zeroth-stt-ko",
    }:
        return "transformers"
    if "whisper.cpp" in lowered or lowered.startswith(("whisper_cpp:", "whisper-cpp:")):
        return "whisper_cpp"
    if bool(getattr(config, "IS_MAC", False)) and (
        "mlx-community/" in lowered
        or lowered.startswith("mlx:")
        or lowered.endswith("-mlx")
        or "-mlx-" in lowered
    ):
        return "mlx"
    if bool(getattr(config, "IS_WINDOWS", False)):
        return "faster_whisper"
    return "faster_whisper"


def select_stt_challenger_backends(model: str, settings: dict[str, Any] | None = None) -> list[SttBackendChoice]:
    data = dict(settings or {})
    if not apple_speech_challenger_enabled(data):
        return []
    support = apple_speech_support(data)
    if not support.available:
        return []
    reason = (
        "apple_speech_high_challenger_benchmark_only"
        if apple_speech_benchmark_only(data)
        else "apple_speech_high_challenger"
    )
    return [SttBackendChoice(APPLE_SPEECH_STT_BACKEND, apple_speech_model(support.locale), reason)]


def select_stt_backend(model: str, settings: dict[str, Any] | None = None) -> SttBackendChoice:
    data = dict(settings or {})
    requested_model = str(model or "").strip()
    policy = normalize_backend_policy(data.get("stt_backend_policy", "auto"))
    prof_backend = profile_backend("stt", data)
    prof_model = profile_model("stt", data)

    if requested_model.lower().startswith(f"{APPLE_SPEECH_STT_BACKEND}:"):
        support = apple_speech_support(data, locale=requested_model.split(":", 1)[1].strip() or None)
        if support.available:
            return SttBackendChoice(
                APPLE_SPEECH_STT_BACKEND,
                apple_speech_model(support.locale),
                "explicit_apple_speech_model",
            )
        requested_model = apple_speech_model(support.locale)

    if policy == "disabled":
        return SttBackendChoice(_infer_backend(requested_model), requested_model, "policy_disabled_fallback")
    if requested_model.lower().startswith("whisperkit-persistent:"):
        if not _whisperkit_supported_model(requested_model):
            fallback_model = _unwrap_whisperkit_model(requested_model)
            return SttBackendChoice(
                _infer_backend(fallback_model),
                fallback_model,
                "explicit_whisperkit_unsupported_model_fallback",
            )
        return SttBackendChoice(
            "whisperkit_persistent",
            _whisperkit_model(requested_model),
            "explicit_whisperkit_model",
        )
    if prof_model and (not requested_model or prof_model == requested_model):
        backend = prof_backend or _infer_backend(prof_model)
        if str(backend or "").strip().lower() == "whisperkit_persistent" and not _whisperkit_supported_model(prof_model):
            return SttBackendChoice(
                _infer_backend(prof_model),
                prof_model,
                "autotuned_profile_unsupported_whisperkit_fallback",
            )
        return SttBackendChoice(backend, _model_for_backend(backend, prof_model), "autotuned_profile")
    if prof_backend and policy == "auto":
        if str(prof_backend or "").strip().lower() == "whisperkit_persistent" and not _whisperkit_supported_model(
            requested_model
        ):
            return SttBackendChoice(
                _infer_backend(requested_model),
                requested_model,
                "autotuned_backend_unsupported_whisperkit_fallback",
            )
        return SttBackendChoice(prof_backend, _model_for_backend(prof_backend, requested_model), "autotuned_backend")

    if policy == "quality":
        mlx_alias = _mac_mlx_alias(requested_model)
        if mlx_alias:
            return SttBackendChoice("mlx", mlx_alias, "mac_native_mlx_quality_alias")
        return SttBackendChoice(_infer_backend(requested_model), requested_model, "quality_preserves_selected_model")
    if policy == "fast":
        if bool(getattr(config, "IS_MAC", False)) and requested_model == "mlx-community/whisper-large-v3-mlx":
            return SttBackendChoice("mlx", "mlx-community/whisper-large-v3-turbo", "fast_policy_mlx_turbo")
        mlx_alias = _mac_mlx_alias(requested_model)
        if mlx_alias:
            turbo_alias = "mlx-community/whisper-large-v3-turbo" if "turbo" not in mlx_alias else mlx_alias
            return SttBackendChoice("mlx", turbo_alias, "mac_native_mlx_fast_alias")
        return SttBackendChoice(_infer_backend(requested_model), requested_model, "fast_policy_selected_model")
    if policy == "native":
        model_for_native = requested_model or "large-v3-turbo"
        inferred_backend = _infer_backend(model_for_native)
        if (
            bool(getattr(config, "IS_MAC", False))
            and inferred_backend == "mlx"
            and _native_exact_mlx_model_enabled(data)
        ):
            return SttBackendChoice("mlx", _model_for_backend("mlx", model_for_native), "native_policy_selected_mlx_model")
        if (
            bool(getattr(config, "IS_MAC", False))
            and not _whisperkit_empty_fallback_active(data)
            and _whisperkit_auto_enabled(data)
            and _whisperkit_ready()
            and _whisperkit_supported_model(model_for_native)
        ):
            return SttBackendChoice(
                "whisperkit_persistent",
                _whisperkit_model(model_for_native),
                "native_policy_whisperkit_ready",
            )
        if str(model_for_native).lower().startswith(("whisper.cpp:", "whisper_cpp:", "whisper-cpp:")):
            if _whisper_cpp_ready(model_for_native):
                return SttBackendChoice("whisper_cpp", model_for_native, "native_policy_whisper_cpp_ready")
        cpp_model = model_for_native if str(model_for_native).lower().startswith("whisper.cpp:") else f"whisper.cpp:{model_for_native}"
        if _whisper_cpp_ready(cpp_model):
            return SttBackendChoice("whisper_cpp", cpp_model, "native_policy_whisper_cpp_ready")
        mlx_alias = _mac_mlx_alias(model_for_native) or "mlx-community/whisper-large-v3-turbo"
        return SttBackendChoice("mlx", mlx_alias, "native_policy_mlx_safe_fallback")
    if policy == "legacy":
        return SttBackendChoice(_infer_backend(requested_model), requested_model, "legacy_policy")

    mlx_alias = _mac_mlx_alias(requested_model)
    if mlx_alias:
        if (
            bool(getattr(config, "IS_MAC", False))
            and not _whisperkit_empty_fallback_active(data)
            and _whisperkit_auto_enabled(data)
            and _whisperkit_ready()
        ):
            return SttBackendChoice(
                "whisperkit_persistent",
                _whisperkit_model(requested_model),
                "mac_native_whisperkit_auto_ready",
            )
        return SttBackendChoice("mlx", mlx_alias, "mac_native_mlx_auto_alias")

    return SttBackendChoice(_infer_backend(requested_model), requested_model, "auto_selected_model")


__all__ = ["SttBackendChoice", "select_stt_backend", "select_stt_challenger_backends"]
