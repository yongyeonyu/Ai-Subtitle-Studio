from __future__ import annotations

from functools import lru_cache

from core.audio.whisper_coreml import DEFAULT_COREML_MODEL_ID, find_whisperkit_cli, is_coreml_whisper_model
from core.performance import hardware_profile
from core.runtime import config
from core.runtime.logger import get_logger


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off", "disabled", "disable", "끄기", "끔"}
_NPU_UNAVAILABLE_NOTICE_KEYS: set[tuple[str, str]] = set()
_NPU_MODEL_MAP = {
    "large-v3": DEFAULT_COREML_MODEL_ID,
    "whisper-large-v3": DEFAULT_COREML_MODEL_ID,
    "openai/whisper-large-v3": DEFAULT_COREML_MODEL_ID,
    "mlx-community/whisper-large-v3-mlx": DEFAULT_COREML_MODEL_ID,
}


def _setting_bool(value, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return bool(default)


@lru_cache(maxsize=1)
def apple_neural_engine_available() -> bool:
    if not config.IS_MAC:
        return False
    cli = str(find_whisperkit_cli() or "").strip()
    if cli:
        return True
    try:
        accelerators = dict(hardware_profile().get("accelerators", {}) or {})
    except Exception:
        accelerators = {}
    return bool(accelerators.get("neural_engine_path"))


def whisper_model_npu_target(model: str) -> str:
    raw = str(model or "").strip()
    if not raw:
        return ""
    if is_coreml_whisper_model(raw):
        return raw
    return _NPU_MODEL_MAP.get(raw.lower(), "")


def npu_whisper_routing_enabled(settings: dict | None = None, *, purpose: str = "stt") -> bool:
    if not config.IS_MAC:
        return False
    loaded = dict(settings or {})
    if not _setting_bool(loaded.get("runtime_npu_acceleration_enabled"), True):
        return False
    if purpose == "live_stt":
        return _setting_bool(loaded.get("live_stt_npu_prefer_enabled"), True)
    return _setting_bool(loaded.get("stt_npu_prefer_enabled"), True)


def prefer_npu_whisper_model(
    model: str,
    settings: dict | None = None,
    *,
    purpose: str = "stt",
    log_label: str = "STT",
    emit_log: bool = True,
) -> str:
    raw = str(model or "").strip()
    if not raw:
        return raw
    if is_coreml_whisper_model(raw):
        return raw
    target = whisper_model_npu_target(raw)
    if not target:
        return raw
    if not npu_whisper_routing_enabled(settings, purpose=purpose):
        return raw
    if not apple_neural_engine_available():
        key = (purpose, raw.lower())
        if emit_log and key not in _NPU_UNAVAILABLE_NOTICE_KEYS:
            _NPU_UNAVAILABLE_NOTICE_KEYS.add(key)
            get_logger().log(
                f"⚠️ [{log_label}] Apple NPU Whisper 경로를 사용할 수 없어 기존 모델을 유지합니다: "
                "whisperkit-cli/argmax-cli 설치 후 Core ML 라우팅이 활성화됩니다."
            )
        return raw
    if emit_log and raw != target:
        get_logger().log(f"⚡ [{log_label}] Apple NPU 우선 라우팅: {raw} -> {target}")
    return target


__all__ = [
    "apple_neural_engine_available",
    "npu_whisper_routing_enabled",
    "prefer_npu_whisper_model",
    "whisper_model_npu_target",
]
