# Version: 01.00.00
"""
[Version History]
- v0.1.0 (Build 00.01.00) : 최초 생성. 영상 길이 및 AI 모델 설정별 실제 소요 시간을 누적 학습하여 예상 시간 계산.
"""
import os
import json

HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset", "time_history.json")

def _load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: pass
    return {}

def _save_history(data):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception: pass

def get_expected_time(model_key: str, video_duration_sec: float) -> float:
    """학습된 데이터를 바탕으로 예상 소요 시간(초)을 반환. 데이터가 없으면 -1 반환."""
    data = _load_history()
    if model_key in data:
        stats = data[model_key]
        if stats.get("count", 0) > 0:
            speed_ratio = stats["total_processing_time"] / stats["total_video_duration"]
            return video_duration_sec * speed_ratio
    return -1.0

def add_history(model_key: str, video_duration_sec: float, processing_time_sec: float):
    """작업이 끝나면 실제 걸린 시간을 학습(저장)합니다."""
    data = _load_history()
    if model_key not in data:
        data[model_key] = {"total_video_duration": 0.0, "total_processing_time": 0.0, "count": 0}
    
    data[model_key]["total_video_duration"] += video_duration_sec
    data[model_key]["total_processing_time"] += processing_time_sec
    data[model_key]["count"] += 1
    _save_history(data)