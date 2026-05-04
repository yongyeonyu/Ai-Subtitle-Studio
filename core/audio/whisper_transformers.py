# Version: 03.10.03
# Phase: PHASE2
"""
core/audio/whisper_transformers.py
Hugging Face Transformers Whisper backend for experimental Korean fine-tuned models.
"""
from __future__ import annotations

import json
import os  # noqa: F401 - tests patch module os.environ shared by subprocess_env()
import subprocess
import sys
import threading

from core.llm.secure_keys import get_api_key
from core.platform_compat import subprocess_env


TRANSFORMERS_KOREAN_WHISPER_MODELS = {
    "o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2",
    "o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO",
    "o0dimplz0o/Fine-Tuned-Whisper-Large-v2-Zeroth-STT-KO",
}


def is_transformers_whisper_model(model: str) -> bool:
    return str(model or "").strip() in TRANSFORMERS_KOREAN_WHISPER_MODELS


def run_whisper(chunk_paths: list, model: str, language: str, temperature_tuple: str = "(0.0,)", log_label: str = "STT"):
    """Run a Transformers ASR worker and stream one JSON line per chunk."""
    env = _huggingface_env()
    proc = subprocess.Popen(
        [sys.executable, "-u", "-c", _build_worker_script()],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    task = {
        "chunk_paths": list(chunk_paths or []),
        "model": str(model or ""),
        "language": str(language or "ko"),
        "temperature_tuple": str(temperature_tuple or "(0.0,)"),
    }
    try:
        proc.stdin.write(json.dumps(task, ensure_ascii=False) + "\n")
        proc.stdin.flush()
    except Exception:
        proc.kill()
        return None
    _attach_stderr_logger(proc, log_label=log_label)
    return proc


def _huggingface_env() -> dict:
    env = subprocess_env()
    token = env.get("HF_TOKEN") or env.get("HUGGINGFACE_HUB_TOKEN") or get_api_key("huggingface")
    if token:
        env.setdefault("HF_TOKEN", token)
        env.setdefault("HUGGINGFACE_HUB_TOKEN", token)
    return env


def _format_stderr_log(line: str, log_label: str = "STT") -> str:
    label = (log_label or "STT").strip() or "STT"
    text = str(line or "").rstrip()
    if not text:
        return ""
    if _suppress_stderr_line(text):
        return ""
    if text.lstrip().startswith(f"[{label}]"):
        return text
    return f"[{label}] {text}"


def _suppress_stderr_line(text: str) -> bool:
    noise = (
        "A custom logits processor of type",
        "Ignoring clean_up_tokenization_spaces=True for BPE tokenizer WhisperTokenizer",
        "MallocStackLogging: can't turn off malloc stack logging",
    )
    return any(fragment in str(text or "") for fragment in noise)


def _attach_stderr_logger(proc, log_label: str = "STT"):
    def _log_stderr():
        from core.runtime.logger import get_logger

        for line in proc.stderr:
            line = _format_stderr_log(line, log_label=log_label)
            if line:
                get_logger().log(line)

    threading.Thread(target=_log_stderr, daemon=True, name="whisper-transformers-stderr").start()


def _build_worker_script() -> str:
    return r'''
import json
import os
import sys
import traceback


def write_json(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


try:
    task = json.loads(sys.stdin.readline())
except Exception as exc:
    write_json({"fatal_error": str(exc), "stage": "task_decode"})
    sys.exit(1)

chunk_paths = task.get("chunk_paths") or []
model_id = task.get("model") or ""
language = task.get("language") or "ko"

try:
    import torch
    from transformers import pipeline
except Exception as exc:
    sys.stderr.write(traceback.format_exc())
    sys.stderr.flush()
    write_json({"fatal_error": str(exc), "stage": "import", "model": model_id})
    sys.exit(1)

try:
    if torch.cuda.is_available():
        device = "cuda:0"
        torch_dtype = torch.float16
    elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        device = "mps"
        torch_dtype = torch.float16
    else:
        device = "cpu"
        torch_dtype = torch.float32

    sys.stderr.write(f"  [HF] device={device}, dtype={torch_dtype}\n")
    sys.stderr.flush()
    asr = pipeline(
        "automatic-speech-recognition",
        model=model_id,
        dtype=torch_dtype,
        device=device,
    )
    sys.stderr.write("  [HF] model load complete\n")
    sys.stderr.flush()
except Exception as exc:
    sys.stderr.write(traceback.format_exc())
    sys.stderr.flush()
    write_json({"fatal_error": str(exc), "stage": "model_load", "model": model_id})
    sys.exit(2)

for chunk_path in chunk_paths:
    try:
        result = asr(
            chunk_path,
            return_timestamps=True,
            generate_kwargs={"language": language, "task": "transcribe"},
        )
        segments = []
        for item in result.get("chunks", []) or []:
            ts = item.get("timestamp") or (None, None)
            start = 0.0 if ts[0] is None else float(ts[0])
            end = start if ts[1] is None else float(ts[1])
            text = str(item.get("text") or "").strip()
            if text:
                segments.append({"start": start, "end": max(start, end), "text": text, "words": []})
        if not segments and str(result.get("text") or "").strip():
            segments.append({"start": 0.0, "end": 0.0, "text": str(result.get("text") or "").strip(), "words": []})
        write_json({
            "backend": "transformers-whisper",
            "loaded_model": model_id,
            "segments": segments,
            "chunk_path": chunk_path,
        })
    except Exception as exc:
        sys.stderr.write(traceback.format_exc())
        sys.stderr.flush()
        write_json({"error": str(exc), "stage": "transcribe", "chunk_path": chunk_path})
        sys.exit(3)
'''
