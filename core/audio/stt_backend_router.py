from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.optimization.backend_policy import normalize_backend_policy, profile_backend, profile_model
from core.runtime import config


@dataclass(frozen=True, slots=True)
class SttBackendChoice:
    backend: str
    model: str
    reason: str


def _infer_backend(model: str) -> str:
    raw = str(model or "").strip()
    lowered = raw.lower()
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
    if "whisper.cpp" in lowered or lowered.startswith("whisper_cpp:"):
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


def select_stt_backend(model: str, settings: dict[str, Any] | None = None) -> SttBackendChoice:
    data = dict(settings or {})
    requested_model = str(model or "").strip()
    policy = normalize_backend_policy(data.get("stt_backend_policy", "auto"))
    prof_backend = profile_backend("stt", data)
    prof_model = profile_model("stt", data)

    if policy == "disabled":
        return SttBackendChoice(_infer_backend(requested_model), requested_model, "policy_disabled_fallback")
    if prof_model:
        backend = prof_backend or _infer_backend(prof_model)
        return SttBackendChoice(backend, prof_model, "autotuned_profile")
    if prof_backend and policy == "auto":
        return SttBackendChoice(prof_backend, requested_model, "autotuned_backend")

    if policy == "quality":
        return SttBackendChoice(_infer_backend(requested_model), requested_model, "quality_preserves_selected_model")
    if policy == "fast":
        if bool(getattr(config, "IS_MAC", False)) and requested_model == "mlx-community/whisper-large-v3-mlx":
            return SttBackendChoice("mlx", "mlx-community/whisper-large-v3-turbo", "fast_policy_mlx_turbo")
        return SttBackendChoice(_infer_backend(requested_model), requested_model, "fast_policy_selected_model")
    if policy == "legacy":
        return SttBackendChoice(_infer_backend(requested_model), requested_model, "legacy_policy")

    return SttBackendChoice(_infer_backend(requested_model), requested_model, "auto_selected_model")


__all__ = ["SttBackendChoice", "select_stt_backend"]
