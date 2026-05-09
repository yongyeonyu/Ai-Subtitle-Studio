from __future__ import annotations

from typing import Any

from .profile_store import load_optimization_profile


_AUTO_VALUES = {"", "auto", "자동", "default", "profile"}


def normalize_backend_policy(value: Any, default: str = "auto") -> str:
    text = str(value if value is not None else default).strip().lower()
    if text in _AUTO_VALUES:
        return "auto"
    if text in {"off", "none", "disabled", "disable", "사용 안함", "끄기", "끔"}:
        return "disabled"
    if text in {"legacy", "python", "safe"}:
        return "legacy"
    if text in {"fast", "speed", "빠름"}:
        return "fast"
    if text in {"quality", "accurate", "정확도", "정확"}:
        return "quality"
    if text in {"native", "cpp", "c++", "swift", "swiftpm", "metal", "coreml", "whisperkit"}:
        return "native"
    return text or str(default or "auto")


def autotune_enabled(settings: dict[str, Any] | None) -> bool:
    data = dict(settings or {})
    value = data.get("runtime_backend_autotune_enabled", True)
    text = str(value).strip().lower()
    return text not in {"0", "false", "off", "no", "disabled", "끄기", "끔"}


def profile_backend(task: str, settings: dict[str, Any] | None = None) -> str:
    if not autotune_enabled(settings):
        return ""
    try:
        profile = load_optimization_profile()
        return str(profile.selected_backends.get(str(task or "")) or "").strip().lower()
    except Exception:
        return ""


def profile_model(task: str, settings: dict[str, Any] | None = None) -> str:
    if not autotune_enabled(settings):
        return ""
    try:
        profile = load_optimization_profile()
        return str(profile.selected_models.get(str(task or "")) or "").strip()
    except Exception:
        return ""
