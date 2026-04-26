# Version: 02.03.02
# Phase: PHASE1-B
"""
기존 SRT 검증/백업 공용 유틸리티.
"""
import datetime
import os
import shutil

from core.media_info import probe_media
from core.path_manager import get_srt_path
from core.srt_parser import parse_srt
from logger import get_logger


def backup_existing_srt(target_file_or_srt: str) -> bool:
    """기존 SRT를 자막백업 폴더로 이동합니다."""
    path = target_file_or_srt or ""
    srt_path = path if path.lower().endswith(".srt") else get_srt_path(path)
    if not srt_path or not os.path.exists(srt_path):
        return False

    try:
        backup_dir = os.path.join(os.path.dirname(srt_path), "자막백업")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(backup_dir, f"{os.path.basename(srt_path)}.{timestamp}.bak")
        shutil.move(srt_path, dst)
        get_logger().log(f"📦 기존 자막 백업 이동: {os.path.basename(srt_path)} → 자막백업")
        return True
    except Exception as e:
        get_logger().log(f"⚠️ 기존 자막 백업 이동 실패: {os.path.basename(srt_path)} / {e}")
        return False


def find_media_for_srt(srt_path: str) -> str:
    base_path = os.path.splitext(srt_path)[0]
    media_exts = (".mp4", ".mov", ".MOV", ".MP4", ".wav", ".m4a", ".m2a", ".mp3", ".aac")
    return next((base_path + ext for ext in media_exts if os.path.exists(base_path + ext)), "")


def validate_srt_duration(srt_path: str, media_path: str, tolerance_sec: float = 1.0) -> tuple[bool, str]:
    """
    SRT 마지막 end time이 영상/오디오 길이를 넘으면 False를 반환합니다.
    duration 조회 실패 시 오탐 방지를 위해 True로 둡니다.
    """
    if not srt_path or not media_path or not os.path.exists(srt_path) or not os.path.exists(media_path):
        return True, ""

    try:
        media_duration = float(probe_media(media_path).get("duration", 0.0) or 0.0)
    except Exception:
        return True, ""
    if media_duration <= 0.0:
        return True, ""

    try:
        segments = parse_srt(srt_path)
    except Exception as e:
        return False, f"기존 자막을 읽을 수 없습니다.\n{srt_path}\n\n{e}"

    if not segments:
        return True, ""

    last_end = max(float(seg.get("end", 0.0) or 0.0) for seg in segments)
    if last_end > media_duration + float(tolerance_sec):
        return (
            False,
            "기존 자막 시간이 영상 길이보다 깁니다.\n"
            f"영상 길이: {media_duration:.2f}초\n"
            f"자막 종료: {last_end:.2f}초\n\n"
            "잘못된 자막으로 판단해 자막백업 폴더로 이동합니다.",
        )
    return True, ""
