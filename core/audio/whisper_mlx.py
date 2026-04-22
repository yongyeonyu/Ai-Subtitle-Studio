# Version: 02.02.00
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
import threading
import uuid
from logger import get_logger


def _build_worker_script() -> str:
    return r"""
import json
import os
import sys
import mlx_whisper

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

for raw in sys.stdin:
    if not raw:
        break

    try:
        msg = json.loads(raw)
    except Exception as e:
        print(json.dumps({"error": f"bad_request: {e}"}, ensure_ascii=False), flush=True)
        continue

    op = msg.get("op", "transcribe")
    if op == "quit":
        break

    task_id = msg.get("task_id", "")
    model = msg.get("model", "")
    language = msg.get("language", "")
    temperature_values = msg.get("temperature_values") or [0.0]
    temperature = tuple(float(x) for x in temperature_values)
    chunk_paths = msg.get("chunk_paths") or []

    for idx, p in enumerate(chunk_paths):
        try:
            result = mlx_whisper.transcribe(
                p,
                path_or_hf_repo=model,
                language=language,
                word_timestamps=True,
                temperature=temperature,
                condition_on_previous_text=False,
                verbose=False,
            )
            print(json.dumps({
                "task_id": task_id,
                "index": idx,
                "result": result,
            }, ensure_ascii=False), flush=True)
        except Exception as e:
            print(json.dumps({
                "task_id": task_id,
                "index": idx,
                "error": str(e),
            }, ensure_ascii=False), flush=True)

    print(json.dumps({
        "task_id": task_id,
        "done": True,
    }, ensure_ascii=False), flush=True)

os._exit(0)
"""

def _attach_stderr_logger(proc):
    def _reader():
        try:
            for line in proc.stderr:
                line = line.rstrip()
                if line:
                    get_logger().log(f"[mlx-whisper] {line}")
        except Exception:
            pass

    threading.Thread(
        target=_reader,
        daemon=True,
        name="mlx-whisper-stderr"
    ).start()

def ensure_worker(proc=None):
    if proc and proc.poll() is None:
        return proc

    new_proc = subprocess.Popen(
        [sys.executable, "-u", "-c", _build_worker_script()],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    _attach_stderr_logger(new_proc)
    get_logger().log("🍎 MLX Whisper persistent worker 시작")
    return new_proc

def submit_task(proc, chunk_paths: list, model: str, language: str, temperature_values: list[float]):
    if proc is None or proc.poll() is not None:
        raise RuntimeError("MLX Whisper worker가 실행 중이 아닙니다.")

    task_id = uuid.uuid4().hex
    payload = {
        "op": "transcribe",
        "task_id": task_id,
        "chunk_paths": list(chunk_paths),
        "model": model,
        "language": language,
        "temperature_values": list(temperature_values),
    }
    proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    return task_id

def stop_worker(proc):
    if not proc:
        return

    try:
        if proc.poll() is None and proc.stdin:
            proc.stdin.write(json.dumps({"op": "quit"}, ensure_ascii=False) + "\n")
            proc.stdin.flush()
    except Exception:
        pass

    try:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

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