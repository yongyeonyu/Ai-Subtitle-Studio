# Version: 02.02.00
# Phase: PHASE1-B
"""
core/whisper_faster.py
Windows 전용 Whisper 백엔드 (faster-whisper)
- PyQt6 충돌 회피를 위해 별도 subprocess에서 실행
- media_processor.py의 proc.stdout.readline() 인터페이스와 호환
"""
import json
import os
import subprocess
import sys
from logger import get_logger


def run_whisper(chunk_paths: list, model: str, language: str, temperature_tuple: str):
    """
    faster-whisper를 별도 프로세스로 실행.
    media_processor.py 호환: Popen-like 객체 반환 (stdout.readline() 가능)
    """
    fw_model = _convert_model_name(model)

    # whisper_worker.py 경로
    worker_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "whisper_worker.py"
    )

    task = {
        "chunk_paths": chunk_paths,
        "model": fw_model,
        "language": language,
    }

    get_logger().log(f"  🔧 faster-whisper subprocess 시작: {fw_model}")

    proc = subprocess.Popen(
        [sys.executable, worker_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    # 작업 정보 전송
    proc.stdin.write(json.dumps(task, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    proc.stdin.close()

    # stderr 로그를 비동기로 출력
    import threading

    def _log_stderr():
        for line in proc.stderr:
            line = line.rstrip()
            if line:
                get_logger().log(line)

    threading.Thread(target=_log_stderr, daemon=True, name="whisper-stderr").start()

    return proc


def _convert_model_name(mlx_model: str) -> str:
    """mlx-community 모델명을 faster-whisper 호환 모델명으로 변환 (로컬 우선)"""

    # ✅ 로컬 모델 폴더 우선 확인
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_models = {
        "large-v3": os.path.join(project_root, "models", "faster-whisper-large-v3"),
        "medium": os.path.join(project_root, "models", "faster-whisper-medium"),
    }
    for size, path in local_models.items():
        if os.path.exists(os.path.join(path, "model.bin")):
            if size in mlx_model.lower() or mlx_model in ("large-v3", size):
                get_logger().log(f"  📂 로컬 모델 사용: {path}")
                return path

    # 온라인 모델명 변환
    conversions = {
        "mlx-community/whisper-large-v3-mlx": "large-v3",
        "mlx-community/whisper-large-v3-turbo": "large-v3-turbo",
        "mlx-community/whisper-medium-mlx": "medium",
        "mlx-community/whisper-small-mlx": "small",
        "mlx-community/whisper-base-mlx": "base",
        "mlx-community/whisper-tiny-mlx": "tiny",
    }

    if mlx_model in conversions:
        return conversions[mlx_model]

    stripped = mlx_model.replace("mlx-community/", "").replace("-mlx", "")
    for key, val in conversions.items():
        if val in stripped:
            return val

    valid = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3", "large-v3-turbo"]
    if mlx_model in valid:
        return mlx_model

    get_logger().log(f"  ⚠️ 모델명 변환 불가: {mlx_model} → medium 사용")
    return "medium"