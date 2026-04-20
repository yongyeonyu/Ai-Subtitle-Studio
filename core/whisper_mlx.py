# Version: 02.01.00
# Phase: PHASE1-B
"""
core/whisper_mlx.py
macOS (Apple Silicon) 전용 Whisper 백엔드
- MLX Whisper subprocess 실행
- media_processor.py에서 분리
"""

import sys
import subprocess
import json
from logger import get_logger


def run_whisper(chunk_paths: list, model: str, language: str, temperature_tuple: str):
    """
    MLX Whisper를 subprocess로 실행하고,
    각 청크별 결과를 yield합니다.

    Returns:
        generator: (json_line: str) — 청크별 JSON 결과
    """
    safe_model = json.dumps(model)
    safe_paths = json.dumps(chunk_paths)

    script = f"""
import mlx_whisper, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

for p in {safe_paths}:
    try:
        r = mlx_whisper.transcribe(
            p,
            path_or_hf_repo={safe_model},
            language='{language}',
            word_timestamps=True,
            temperature={temperature_tuple},
            condition_on_previous_text=False
        )
        print(json.dumps(r, ensure_ascii=False), flush=True)
    except Exception as e:
        print(json.dumps({{"error": str(e)}}, ensure_ascii=False), flush=True)
os._exit(0)
"""

    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace"
    )

    return proc