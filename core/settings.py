# Version: 01.00.00
"""
core/settings.py
앱 전체 설정 로딩/저장 통합 모듈
"""
import os, json
import config

SETTINGS_PATH = os.path.join(config.DATASET_DIR, "user_settings.json")


def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        try:
            from logger import get_logger
            get_logger().log(f"⚠️ 설정 로드 실패: {e}")
        except Exception:
            pass
        return {}


def save_settings(data: dict):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_model_key(settings: dict | None = None) -> str:
    s = settings or load_settings()
    max_spk = int(s.get("max_speakers", 1))
    dia_flag = "O" if max_spk > 1 else "X"
    return f"STT:{s.get('selected_whisper_model','기본')}|LLM:{s.get('selected_model','기본')}|DIA:{dia_flag}"