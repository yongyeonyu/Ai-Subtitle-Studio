# Version: 03.10.03
# Phase: PHASE2
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
from core.runtime.logger import get_logger
from core.llm.secure_keys import get_api_key
from core.platform_compat import subprocess_env


def _build_worker_script() -> str:
    return r"""
import json
import os
import sys
import contextlib
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
    fallback_model = msg.get("fallback_model", "")
    language = msg.get("language", "")
    temperature_values = msg.get("temperature_values") or [0.0]
    temperature = tuple(float(x) for x in temperature_values)
    chunk_paths = msg.get("chunk_paths") or []

    for idx, p in enumerate(chunk_paths):
        try:
            with contextlib.redirect_stdout(sys.stderr):
                result = mlx_whisper.transcribe(
                    p,
                    path_or_hf_repo=model,
                    language=language,
                    word_timestamps=True,
                    temperature=temperature,
                    condition_on_previous_text=False,
                    verbose=False,
                )
            loaded_model = model
            print(json.dumps({
                "backend": "mlx-whisper",
                "task_id": task_id,
                "index": idx,
                "result": result,
                "loaded_model": loaded_model,
                "language_probability": result.get("language_probability"),
            }, ensure_ascii=False), flush=True)
        except Exception as e:
            if fallback_model and fallback_model != model:
                try:
                    with contextlib.redirect_stdout(sys.stderr):
                        result = mlx_whisper.transcribe(
                            p,
                            path_or_hf_repo=fallback_model,
                            language=language,
                            word_timestamps=True,
                            temperature=temperature,
                            condition_on_previous_text=False,
                            verbose=False,
                        )
                    print(json.dumps({
                        "backend": "mlx-whisper",
                        "task_id": task_id,
                        "index": idx,
                        "result": result,
                        "loaded_model": fallback_model,
                        "fallback_from": model,
                        "language_probability": result.get("language_probability"),
                    }, ensure_ascii=False), flush=True)
                except Exception as fallback_e:
                    print(json.dumps({
                        "task_id": task_id,
                        "index": idx,
                        "error": str(fallback_e),
                        "fallback_from": model,
                    }, ensure_ascii=False), flush=True)
            else:
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
    ignored_fragments = (
        "resource_tracker: There appear to be",
        "leaked semaphore objects to clean up at shutdown",
    )

    def _reader():
        try:
            for line in proc.stderr:
                line = line.rstrip()
                if any(fragment in line for fragment in ignored_fragments):
                    continue
                if "frames/s" in line and ("%" in line or "it/s" in line):
                    continue
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

    env = _worker_env()

    new_proc = subprocess.Popen(
        [sys.executable, "-u", "-c", _build_worker_script()],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    _attach_stderr_logger(new_proc)
    get_logger().log("🍎 MLX Whisper persistent worker 시작")
    return new_proc

def _fallback_model_name(model: str) -> str:
    requested = str(model or "")
    if "ghost613" in requested.lower():
        return "mlx-community/whisper-large-v3-mlx"
    return ""


def submit_task(proc, chunk_paths: list, model: str, language: str, temperature_values: list[float]):
    if proc is None or proc.poll() is not None:
        raise RuntimeError("MLX Whisper worker가 실행 중이 아닙니다.")

    task_id = uuid.uuid4().hex
    payload = {
        "op": "transcribe",
        "task_id": task_id,
        "chunk_paths": list(chunk_paths),
        "model": model,
        "fallback_model": _fallback_model_name(model),
        "language": language,
        "temperature_values": list(temperature_values),
    }
    proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    return task_id

def _merged_pythonwarnings(current: str | None, rule: str) -> str:
    parts = [p for p in (current or "").split(",") if p]
    if rule not in parts:
        parts.append(rule)
    return ",".join(parts)

def _worker_env() -> dict:
    env = subprocess_env()
    token = env.get("HF_TOKEN") or env.get("HUGGINGFACE_HUB_TOKEN") or get_api_key("huggingface")
    if token:
        env.setdefault("HF_TOKEN", token)
        env.setdefault("HUGGINGFACE_HUB_TOKEN", token)
    env["PYTHONWARNINGS"] = _merged_pythonwarnings(
        env.get("PYTHONWARNINGS"),
        "ignore:resource_tracker:UserWarning:multiprocessing.resource_tracker",
    )
    return env

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
import mlx_whisper, json, sys, os, contextlib
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

for p in {safe_paths}:
    try:
        with contextlib.redirect_stdout(sys.stderr):
            r = mlx_whisper.transcribe(
                p,
                path_or_hf_repo={safe_model},
                language='{language}',
                word_timestamps=True,
                temperature={temperature_tuple},
                condition_on_previous_text=False
            )
        r["backend"] = "mlx-whisper"
        print(json.dumps(r, ensure_ascii=False), flush=True)
    except Exception as e:
        fallback_model = "mlx-community/whisper-large-v3-mlx" if "ghost613" in {safe_model}.lower() else ""
        if fallback_model:
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    r = mlx_whisper.transcribe(
                        p,
                        path_or_hf_repo=fallback_model,
                        language='{language}',
                        word_timestamps=True,
                        temperature={temperature_tuple},
                        condition_on_previous_text=False
                    )
                r["backend"] = "mlx-whisper"
                r["loaded_model"] = fallback_model
                r["fallback_from"] = {safe_model}
                print(json.dumps(r, ensure_ascii=False), flush=True)
            except Exception as fallback_e:
                print(json.dumps({{"error": str(fallback_e), "fallback_from": {safe_model}}}, ensure_ascii=False), flush=True)
        else:
            print(json.dumps({{"error": str(e)}}, ensure_ascii=False), flush=True)
os._exit(0)
"""

    env = _worker_env()

    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    return proc
