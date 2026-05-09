# Version: 02.03.00
# Phase: PHASE1-B
"""
core/time_history.py
[v01.01.01] 누적 평균 + 최근 학습값 혼합 예상 시간 알고리즘
- 기존 누적 평균 50%
- 최근 학습값 50%
- 하위 호환: 기존 cumulative/EMA 데이터도 정상 동작
"""
import os
import json

HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dataset", "time_history.json"
)

_EMA_ALPHA = 0.4
_CUMULATIVE_WEIGHT = 0.5
_RECENT_WEIGHT = 0.5


def _load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_history(data):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _cumulative_speed_ratio(stats: dict) -> float:
    total_vid = float(stats.get("total_video_duration", 0.0) or 0.0)
    total_proc = float(stats.get("total_processing_time", 0.0) or 0.0)
    if total_vid > 0 and total_proc > 0:
        return total_proc / total_vid
    return 0.0


def _recent_speed_ratio(stats: dict) -> float:
    last_ratio = float(stats.get("last_speed_ratio", 0.0) or 0.0)
    if last_ratio > 0:
        return last_ratio
    ema_ratio = float(stats.get("ema_speed_ratio", 0.0) or 0.0)
    if ema_ratio > 0:
        return ema_ratio
    return 0.0


def _blended_speed_ratio(stats: dict) -> float:
    cumulative_ratio = _cumulative_speed_ratio(stats)
    recent_ratio = _recent_speed_ratio(stats)
    if cumulative_ratio > 0 and recent_ratio > 0:
        return (cumulative_ratio * _CUMULATIVE_WEIGHT) + (recent_ratio * _RECENT_WEIGHT)
    return recent_ratio if recent_ratio > 0 else cumulative_ratio


def get_expected_time(model_key: str, video_duration_sec: float) -> float:
    """누적 평균 + 최근 학습값 혼합 예상 소요 시간(초) 반환. 데이터 없으면 -1."""
    data = _load_history()
    if model_key not in data:
        return -1.0

    stats = data[model_key]
    count = stats.get("count", 0)
    if count <= 0:
        return -1.0

    blended_ratio = float(stats.get("blended_speed_ratio", 0.0) or 0.0)
    if blended_ratio <= 0:
        blended_ratio = _blended_speed_ratio(stats)
    if blended_ratio > 0:
        return video_duration_sec * blended_ratio

    return -1.0


def add_history(model_key: str, video_duration_sec: float, processing_time_sec: float):
    """작업 완료 시 누적 평균 + 최근 학습값 혼합 기준으로 학습."""
    if video_duration_sec <= 0:
        return

    data = _load_history()
    if model_key not in data:
        data[model_key] = {
            "total_video_duration": 0.0,
            "total_processing_time": 0.0,
            "count": 0,
            "ema_speed_ratio": 0.0,
            "last_speed_ratio": 0.0,
            "blended_speed_ratio": 0.0,
        }

    stats = data[model_key]
    latest_ratio = processing_time_sec / video_duration_sec

    # 누적 (하위 호환 유지)
    stats["total_video_duration"] += video_duration_sec
    stats["total_processing_time"] += processing_time_sec
    stats["count"] += 1
    stats["last_speed_ratio"] = latest_ratio

    # EMA 업데이트
    old_ema = stats.get("ema_speed_ratio", 0.0)
    if old_ema <= 0 or stats["count"] == 1:
        # 첫 번째 데이터: EMA = 최신값
        stats["ema_speed_ratio"] = latest_ratio
    else:
        # EMA = α × 최신 + (1-α) × 이전
        stats["ema_speed_ratio"] = _EMA_ALPHA * latest_ratio + (1 - _EMA_ALPHA) * old_ema

    stats["blended_speed_ratio"] = _blended_speed_ratio(stats)

    _save_history(data)
