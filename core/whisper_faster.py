# Version: 02.01.00
# Phase: PHASE1-B
"""
core/whisper_faster.py
Windows 전용 Whisper 백엔드 (faster-whisper)
- 아직 미구현 (스텁)
"""

from logger import get_logger


def run_whisper(chunk_paths: list, model: str, language: str, temperature_tuple: str):
    """
    faster-whisper 실행 (미구현)
    """
    get_logger().log("❌ Windows Whisper 백엔드는 아직 미구현입니다.")
    get_logger().log("   pip install faster-whisper 후 구현 예정")
    return None