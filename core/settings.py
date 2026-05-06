# Version: 03.14.19
# Phase: PHASE2
"""
core/settings.py
앱 전체 설정 로딩/저장 통합 모듈
"""
import os
from core.runtime import config
from core.accuracy_policy import apply_accuracy_first_runtime_settings
from core.json_file import read_json_file, write_json_file_atomic
from core.settings_profiles import hardcoded_default_settings, materialize_user_settings

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


def _persist_materialized_settings(settings: dict) -> None:
    settings_path = _settings_path()
    current = read_json_file(settings_path, default=None, expected_type=dict, context="설정", log_errors=False)
    if current == settings:
        return
    write_json_file_atomic(settings_path, settings, indent=2)


def load_settings() -> dict:
    base = hardcoded_default_settings()
    loaded_data = {}
    data = read_json_file(_settings_path(), default={}, expected_type=dict, context="설정")
    if isinstance(data, dict):
        loaded_data = data
    if loaded_data:
        base.update(loaded_data)
    materialized = materialize_user_settings(base)
    try:
        _persist_materialized_settings(materialized)
    except Exception as e:
        try:
            from core.runtime.logger import get_logger
            get_logger().log(f"⚠️ 설정 저장 동기화 실패: {e}")
        except Exception:
            pass
    runtime = dict(materialized)
    if _RUNTIME_SETTINGS_OVERRIDE:
        runtime.update(_RUNTIME_SETTINGS_OVERRIDE)
    return apply_accuracy_first_runtime_settings(runtime)


def save_settings(data: dict):
    settings_path = _settings_path()
    materialized = materialize_user_settings(data if isinstance(data, dict) else {})
    write_json_file_atomic(settings_path, materialized, indent=2)


def get_model_key(settings: dict | None = None) -> str:
    s = settings or load_settings()
    max_spk = int(s.get("max_speakers", 1))
    dia_flag = "O" if max_spk > 1 else "X"
    stt = s.get("selected_whisper_model", "기본")
    if s.get("stt_ensemble_enabled"):
        stt2 = s.get("selected_whisper_model_secondary", "")
        stt = f"{stt}+{stt2}"
    return f"STT:{stt}|LLM:{s.get('selected_model','기본')}|DIA:{dia_flag}"
