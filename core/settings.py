# Version: 03.14.19
# Phase: PHASE2
"""
core/settings.py
앱 전체 설정 로딩/저장 통합 모듈
"""
import os, json
from core.runtime import config
from core.accuracy_policy import apply_accuracy_first_runtime_settings

SETTINGS_PATH = os.path.join(config.DATASET_DIR, "user_settings.json")
_RUNTIME_SETTINGS_OVERRIDE: dict | None = None


def _settings_path() -> str:
    return os.path.join(config.DATASET_DIR, "user_settings.json")


def set_runtime_settings_override(settings: dict | None) -> None:
    global _RUNTIME_SETTINGS_OVERRIDE
    _RUNTIME_SETTINGS_OVERRIDE = dict(settings or {}) if settings else None


def clear_runtime_settings_override() -> None:
    set_runtime_settings_override(None)


def runtime_settings_override() -> dict:
    return dict(_RUNTIME_SETTINGS_OVERRIDE or {})


def load_settings() -> dict:
    base = dict(getattr(config, "DEFAULT_ADV_SETTINGS", {}) or {})
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            base.update(data)
        if _RUNTIME_SETTINGS_OVERRIDE:
            base.update(_RUNTIME_SETTINGS_OVERRIDE)
        return apply_accuracy_first_runtime_settings(base)
    except FileNotFoundError:
        if _RUNTIME_SETTINGS_OVERRIDE:
            base.update(_RUNTIME_SETTINGS_OVERRIDE)
        return apply_accuracy_first_runtime_settings(base)
    except Exception as e:
        try:
            from core.runtime.logger import get_logger
            get_logger().log(f"⚠️ 설정 로드 실패: {e}")
        except Exception:
            pass
        if _RUNTIME_SETTINGS_OVERRIDE:
            base.update(_RUNTIME_SETTINGS_OVERRIDE)
        return apply_accuracy_first_runtime_settings(base)


def save_settings(data: dict):
    settings_path = _settings_path()
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_model_key(settings: dict | None = None) -> str:
    s = settings or load_settings()
    max_spk = int(s.get("max_speakers", 1))
    dia_flag = "O" if max_spk > 1 else "X"
    stt = s.get("selected_whisper_model", "기본")
    if s.get("stt_ensemble_enabled"):
        stt2 = s.get("selected_whisper_model_secondary", "")
        stt = f"{stt}+{stt2}"
    return f"STT:{stt}|LLM:{s.get('selected_model','기본')}|DIA:{dia_flag}"
