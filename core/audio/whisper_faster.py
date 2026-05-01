# Version: 03.01.23
# Phase: PHASE2
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
from pathlib import Path

from core.platform_compat import hidden_subprocess_kwargs
from logger import get_logger


def run_whisper(chunk_paths: list, model: str, language: str, temperature_tuple: str):
    """
    faster-whisper를 별도 프로세스로 실행.
    media_processor.py 호환: Popen-like 객체 반환 (stdout.readline() 가능)
    """
    fw_model = _convert_model_name(model)

    # whisper_worker.py 경로
    worker_script = Path(__file__).with_name("whisper_worker.py")
    if not worker_script.exists():
        get_logger().log(f"  ❌ faster-whisper worker 없음: {worker_script}")
        return None

    task = {
        "chunk_paths": chunk_paths,
        "model": fw_model,
        "fallback_model": _fallback_model_name(fw_model),
        "language": language,
    }

    get_logger().log(f"  🔧 faster-whisper subprocess 시작: {fw_model}")

    proc = subprocess.Popen(
        [sys.executable, str(worker_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_subprocess_kwargs(strip_qt=True),
    )

    # 작업 정보 전송
    try:
        proc.stdin.write(json.dumps(task, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        proc.stdin.close()
    except Exception as e:
        get_logger().log(f"  ❌ faster-whisper 작업 전송 실패: {e}")
        try:
            proc.kill()
        except Exception:
            pass
        return None

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
    requested_raw = (mlx_model or "").strip()

    conversions = {
        "mlx-community/whisper-large-v3-mlx": "large-v3",
        "mlx-community/whisper-large-v3-turbo": "large-v3-turbo",
        "youngouk/ghost613-turbo-korean-4bit-mlx": "ghost613/faster-whisper-large-v3-turbo-korean",
        "mlx-community/whisper-large-v2-mlx": "large-v2",
        "mlx-community/whisper-medium-mlx": "medium",
        "mlx-community/whisper-medium.en-mlx": "medium.en",
        "mlx-community/whisper-small-mlx": "small",
        "mlx-community/whisper-small.en-mlx": "small.en",
        "mlx-community/whisper-base-mlx": "base",
        "mlx-community/whisper-base.en-mlx": "base.en",
        "mlx-community/whisper-tiny-mlx": "tiny",
        "mlx-community/whisper-tiny.en-mlx": "tiny.en",
        "mlx-community/distil-whisper-large-v3": "distil-large-v3",
    }
    if requested_raw in conversions and conversions[requested_raw] not in ("large-v3", "medium"):
        return conversions[requested_raw]

    requested = requested_raw.lower()

    # ✅ 로컬 모델 폴더 우선 확인
    project_root = Path(__file__).resolve().parents[2]
    local_models = {
        "large-v3": project_root / "models" / "faster-whisper-large-v3",
        "medium": project_root / "models" / "faster-whisper-medium",
    }
    for size, path in local_models.items():
        if any((path / name).exists() for name in ("model.bin", "model.safetensors", "config.json")):
            if requested in (size, f"mlx-community/whisper-{size}-mlx", f"whisper-{size}-mlx"):
                get_logger().log(f"  📂 로컬 모델 사용: {path}")
                return str(path)

    # If local model was explicitly requested but not found, return a non-repo local path
    # so faster-whisper fails fast locally instead of entering Hugging Face download.
    if requested in ("large-v3", "mlx-community/whisper-large-v3-mlx", "whisper-large-v3-mlx"):
        missing = project_root / "models" / "__missing_faster_whisper_large_v3__"
        get_logger().log(f"  [FAIL] local large-v3 model missing: {missing}")
        return str(missing)
    if requested in ("medium", "mlx-community/whisper-medium-mlx", "whisper-medium-mlx"):
        missing = project_root / "models" / "__missing_faster_whisper_medium__"
        get_logger().log(f"  [FAIL] local medium model missing: {missing}")
        return str(missing)

    # 온라인 모델명 변환
    if requested_raw in conversions:
        return conversions[requested_raw]

    stripped = requested_raw.replace("mlx-community/", "").replace("-mlx", "")
    valid = [
        "tiny.en", "tiny", "base.en", "base", "small.en", "small",
        "medium.en", "medium", "large-v1", "large-v2", "large-v3",
        "large", "distil-large-v2", "distil-medium.en", "distil-small.en",
        "distil-large-v3", "large-v3-turbo", "turbo",
        "ghost613/faster-whisper-large-v3-turbo-korean",
    ]
    if requested_raw in valid:
        return requested_raw

    for key, val in conversions.items():
        if val in stripped:
            return val

    get_logger().log(f"  ⚠️ 모델명 변환 불가: {requested_raw} → medium 사용")
    return "medium"


def _fallback_model_name(model: str) -> str:
    requested = str(model or "")
    if "ghost613" in requested.lower():
        return "large-v3"
    return ""
