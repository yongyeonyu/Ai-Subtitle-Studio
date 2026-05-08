from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.optimization.backend_policy import normalize_backend_policy, profile_backend


@dataclass(frozen=True, slots=True)
class VadBackendChoice:
    provider: str
    reason: str


def normalize_vad_provider(value: Any) -> str:
    text = str(value or "none").strip().lower().replace("-", "_")
    if text in {"ten", "tenvad"}:
        return "ten_vad"
    if text in {"silero_vad"}:
        return "silero"
    if text in {"off", "disabled", "사용 안함", "none"}:
        return "none"
    return text or "none"


def select_vad_backend(requested: str, settings: dict[str, Any] | None = None) -> VadBackendChoice:
    data = dict(settings or {})
    provider = normalize_vad_provider(requested)
    policy = normalize_backend_policy(data.get("vad_backend_policy", "auto"))
    prof = normalize_vad_provider(profile_backend("vad", data))
    if prof and prof != "none" and policy == "auto":
        return VadBackendChoice(prof, "autotuned_profile")
    if policy == "fast":
        return VadBackendChoice("ten_vad", "fast_policy")
    if policy == "quality":
        return VadBackendChoice("silero", "quality_policy")
    if policy == "legacy":
        return VadBackendChoice(provider, "legacy_policy")
    return VadBackendChoice(provider, "selected_provider")


__all__ = ["VadBackendChoice", "normalize_vad_provider", "select_vad_backend"]
