from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime.config import IS_MAC
from core.runtime.setting_utils import setting_bool

APPLE_SPEECH_STT_BACKEND = "apple_speech"
APPLE_SPEECH_VAD_BACKEND = "apple_speech_detector"
APPLE_SPEECH_DEFAULT_LOCALE = "ko-KR"


@dataclass(frozen=True, slots=True)
class AppleSpeechSupport:
    available: bool
    detector_available: bool
    reason: str
    locale: str


def apple_speech_locale(settings: dict[str, Any] | None = None, default: str = APPLE_SPEECH_DEFAULT_LOCALE) -> str:
    data = dict(settings or {})
    locale = str(data.get("stt_apple_speech_locale") or default).strip()
    return locale or default


def apple_speech_model(locale: str | None = None) -> str:
    return f"{APPLE_SPEECH_STT_BACKEND}:{str(locale or APPLE_SPEECH_DEFAULT_LOCALE).strip() or APPLE_SPEECH_DEFAULT_LOCALE}"


def apple_speech_benchmark_only(settings: dict[str, Any] | None = None) -> bool:
    return setting_bool(dict(settings or {}).get("stt_apple_speech_benchmark_only"), True)


def apple_speech_challenger_enabled(settings: dict[str, Any] | None = None) -> bool:
    if not IS_MAC:
        return False
    data = dict(settings or {})
    if not setting_bool(data.get("stt_apple_speech_challenger_enabled"), False):
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_CORE")


def apple_speech_vad_coupled_enabled(settings: dict[str, Any] | None = None) -> bool:
    if not apple_speech_challenger_enabled(settings):
        return False
    return setting_bool(dict(settings or {}).get("stt_apple_speech_vad_coupled_enabled"), True)


def apple_speech_support(
    settings: dict[str, Any] | None = None,
    *,
    locale: str | None = None,
) -> AppleSpeechSupport:
    resolved_locale = apple_speech_locale(settings, default=str(locale or APPLE_SPEECH_DEFAULT_LOCALE))
    if not IS_MAC:
        return AppleSpeechSupport(False, False, "mac_only", resolved_locale)
    if not native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_CORE"):
        return AppleSpeechSupport(False, False, "native_swift_disabled", resolved_locale)
    decoded = request_native_core_task(
        "apple_speech_support",
        {"locale": resolved_locale},
    )
    if not isinstance(decoded, dict):
        return AppleSpeechSupport(False, False, "native_probe_unavailable", resolved_locale)
    return AppleSpeechSupport(
        bool(decoded.get("available")),
        bool(decoded.get("detector_available")),
        str(decoded.get("reason") or ("available" if decoded.get("available") else "unavailable")),
        str(decoded.get("locale") or resolved_locale),
    )


__all__ = [
    "APPLE_SPEECH_DEFAULT_LOCALE",
    "APPLE_SPEECH_STT_BACKEND",
    "APPLE_SPEECH_VAD_BACKEND",
    "AppleSpeechSupport",
    "apple_speech_benchmark_only",
    "apple_speech_challenger_enabled",
    "apple_speech_locale",
    "apple_speech_model",
    "apple_speech_support",
    "apple_speech_vad_coupled_enabled",
]
