from __future__ import annotations

import os
from typing import Any

from core.runtime import config

BENCH_SAFE_NATIVE_RUNTIME_SETTINGS: dict[str, Any] = {
    "mac_native_acceleration_enabled": True,
    "native_cpp_llm_macro_groups_enabled": True,
    "native_swift_quality_scoring_enabled": True,
    "native_swift_quality_scoring_min_segments": 64,
    "native_swift_common_split_enabled": True,
    "native_swift_common_split_min_items": 1000,
}

EXPERIMENTAL_SWIFT_POLICY_KEYS = (
    "native_swift_llm_candidate_policy_enabled",
    "native_swift_deep_policy_enabled",
    "native_swift_lora_scoring_enabled",
)


def _setting_bool(settings: dict[str, Any], key: str, default: bool = True) -> bool:
    value = settings.get(key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value or "").strip().casefold()
    if text in {"0", "false", "off", "no", "사용 안함", "끔", "미사용"}:
        return False
    if text in {"1", "true", "on", "yes", "사용", "켬"}:
        return True
    return bool(default)


def _positive_int(settings: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(float(settings.get(key, default)))
    except Exception:
        value = int(default)
    return value if value > 0 else int(default)


def _env_bool(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    text = str(value or "").strip().casefold()
    if text in {"0", "false", "off", "no"}:
        return False
    if text in {"1", "true", "on", "yes"}:
        return True
    return None


def mac_native_swift_policy_experimental_enabled(settings: dict[str, Any] | None = None) -> bool:
    data = dict(settings or {})
    env = _env_bool("AI_SUBTITLE_STUDIO_SWIFT_POLICY_EXPERIMENTAL")
    if env is not None:
        return env
    return _setting_bool(data, "native_swift_policy_experimental_enabled", False)


def mac_native_runtime_overrides(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return production-safe macOS native overrides.

    This is intentionally conservative: proven native paths are enabled, while
    Swift LoRA/Deep/LLM policy helpers stay disabled unless a benchmark-only
    experimental switch is explicitly set.  That prevents stale user settings
    from re-enabling slower or ranking-changing policy workers during normal
    subtitle generation.
    """
    data = dict(settings or {})
    out = dict(BENCH_SAFE_NATIVE_RUNTIME_SETTINGS)
    experimental = mac_native_swift_policy_experimental_enabled(data)
    for key in EXPERIMENTAL_SWIFT_POLICY_KEYS:
        out[key] = _setting_bool(data, key, False) if experimental else False
    out["native_swift_policy_experimental_enabled"] = experimental
    return out


def mac_native_backend_plan(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize the safe macOS-native acceleration routes for the pipeline.

    This intentionally separates "native where it helps" from "native because it
    exists".  Previous local benchmarks showed Swift policy helpers were slower
    for LoRA/Deep/LLM candidate ranking and changed LoRA ordering, so those stay
    Python by default while STT, VAD interval math, macro grouping, and large
    batch quality/split work use native routes.
    """
    data = dict(settings or {})
    native_enabled = bool(getattr(config, "IS_MAC", False)) and _setting_bool(data, "mac_native_acceleration_enabled", True)
    experimental_policy = mac_native_swift_policy_experimental_enabled(data)
    swift_quality_min = _positive_int(data, "native_swift_quality_scoring_min_segments", 64)
    swift_split_min = _positive_int(data, "native_swift_common_split_min_items", 1000)
    return {
        "schema": "ai_subtitle_studio.mac_native_backend_plan.v1",
        "enabled": native_enabled,
        "experimental_swift_policy_enabled": experimental_policy,
        "stt": {
            "route": "whisperkit_coreml_mlx",
            "enabled": native_enabled and _setting_bool(data, "whisperkit_native_auto_enabled", True),
            "reason": "WhisperKit/CoreML/MLX are the fastest stable STT routes on Apple Silicon.",
        },
        "vad": {
            "route": "python_vad_native_cpp_overlap",
            "enabled": native_enabled,
            "reason": "VAD models stay as selected, but overlap/alignment math uses the C++ helper.",
        },
        "lora": {
            "route": "python_ranker",
            "enabled": native_enabled and experimental_policy and _setting_bool(data, "native_swift_lora_scoring_enabled", False),
            "default_enabled": False,
            "reason": "Swift LoRA scoring remains opt-in because benchmark parity changed top ranking.",
        },
        "deep_learning": {
            "route": "python_policy",
            "enabled": native_enabled and experimental_policy and _setting_bool(data, "native_swift_deep_policy_enabled", False),
            "default_enabled": False,
            "reason": "Swift Deep rerank remains opt-in because the Python path was faster in the benchmark.",
        },
        "llm": {
            "route": "native_cpp_macro_grouping_external_llm",
            "enabled": native_enabled and _setting_bool(data, "native_cpp_llm_macro_groups_enabled", True),
            "candidate_policy_swift_enabled": native_enabled
            and experimental_policy
            and _setting_bool(data, "native_swift_llm_candidate_policy_enabled", False),
            "reason": "LLM inference stays with the selected provider; C++ handles macro grouping safely.",
        },
        "quality_scoring": {
            "route": "swift_batch",
            "enabled": native_enabled and _setting_bool(data, "native_swift_quality_scoring_enabled", True),
            "min_segments": swift_quality_min,
            "reason": "Swift scorer is used only for large batches where worker overhead is amortized.",
        },
        "common_split": {
            "route": "swift_batch",
            "enabled": native_enabled and _setting_bool(data, "native_swift_common_split_enabled", True),
            "min_items": swift_split_min,
            "reason": "Swift split planner is used only for large batches; Python remains faster for small edits.",
        },
    }


__all__ = [
    "BENCH_SAFE_NATIVE_RUNTIME_SETTINGS",
    "EXPERIMENTAL_SWIFT_POLICY_KEYS",
    "mac_native_backend_plan",
    "mac_native_runtime_overrides",
    "mac_native_swift_policy_experimental_enabled",
]
