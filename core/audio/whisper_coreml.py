# Version: 03.08.07
# Phase: PHASE2
"""
Experimental WhisperKit/Core ML backend for macOS.

This wrapper keeps Core ML optional: if the WhisperKit CLI is unavailable,
the caller can safely fall back to the existing MLX path.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from core.runtime import config
from core.platform_compat import hidden_subprocess_kwargs, subprocess_env
from core.runtime.logger import get_logger


COREML_MODEL_PREFIX = "coreml:"
DEFAULT_COREML_MODEL = "large-v3-v20240930_626MB"
DEFAULT_COREML_MODEL_ID = f"{COREML_MODEL_PREFIX}{DEFAULT_COREML_MODEL}"


def is_coreml_whisper_model(model: str) -> bool:
    return config.IS_MAC and str(model or "").strip().lower().startswith(COREML_MODEL_PREFIX)


def coreml_model_selector(model: str) -> str:
    value = str(model or "").strip()
    if value.lower().startswith(COREML_MODEL_PREFIX):
        value = value[len(COREML_MODEL_PREFIX):].strip()
    return value or DEFAULT_COREML_MODEL


def find_whisperkit_cli() -> str:
    explicit = os.environ.get("WHISPERKIT_CLI") or os.environ.get("ARGMAX_CLI")
    if explicit:
        expanded = os.path.expanduser(explicit)
        if os.path.exists(expanded):
            return expanded
        found = shutil.which(explicit)
        if found:
            return found
    return shutil.which("argmax-cli") or shutil.which("whisperkit-cli") or ""


def _format_stderr_log(line: str, log_label: str = "STT") -> str:
    label = (log_label or "STT").strip() or "STT"
    text = str(line or "").rstrip()
    if not text:
        return ""
    if text.lstrip().startswith(f"[{label}]"):
        return text
    return f"[{label}] [coreml] {text}"


def _attach_stderr_logger(proc, log_label: str = "STT"):
    def _log_stderr():
        for line in proc.stderr:
            line = _format_stderr_log(line, log_label=log_label)
            if line:
                get_logger().log(line)

    threading.Thread(target=_log_stderr, daemon=True, name="whisper-coreml-stderr").start()


def run_whisper(chunk_paths: list, model: str, language: str, temperature_tuple: str = "(0.0,)", log_label: str = "STT"):
    """Run WhisperKit CLI in a subprocess and stream one JSON line per chunk."""
    if not config.IS_MAC:
        return None

    cli = find_whisperkit_cli()
    if not cli:
        get_logger().log(
            "  ⚠️ [Core ML STT] whisperkit-cli/argmax-cli를 찾지 못해 MLX Whisper로 대체합니다. "
            "설치: brew install whisperkit-cli"
        )
        return None

    selector = coreml_model_selector(model)
    get_logger().log(f"  🧪 [{log_label}] Core ML WhisperKit 실행 준비: {selector}")
    script = _build_worker_script()
    env = subprocess_env()
    env.setdefault("WHISPERKIT_CLI", cli)
    task = {
        "chunk_paths": list(chunk_paths or []),
        "model": selector,
        "language": str(language or "ko"),
        "cli": cli,
    }
    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            **hidden_subprocess_kwargs(strip_qt=True),
        )
        proc.stdin.write(json.dumps(task, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        proc.stdin.close()
    except Exception as exc:
        get_logger().log(f"  ⚠️ [Core ML STT] worker 시작 실패, MLX Whisper로 대체합니다: {exc}")
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        return None

    _attach_stderr_logger(proc, log_label=log_label)
    return proc


def _build_worker_script() -> str:
    return r'''
import json
import os
import subprocess
import sys
import wave


def write_json(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def wav_duration(path):
    try:
        with wave.open(path, "rb") as wf:
            return max(0.05, wf.getnframes() / float(wf.getframerate() or 16000))
    except Exception:
        return 30.0


def model_args_for(selector):
    model_path = os.environ.get("WHISPERKIT_MODEL_PATH", "").strip()
    if selector and os.path.exists(os.path.expanduser(selector)):
        return ["--model-path", os.path.expanduser(selector)]
    if model_path:
        return ["--model-path", os.path.expanduser(model_path)]
    if selector:
        return ["--model", selector]
    return []


def extract_text(stdout):
    text = (stdout or "").strip()
    if not text:
        return ""
    for raw in reversed([line.strip() for line in text.splitlines() if line.strip()]):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict):
            if str(data.get("text") or "").strip():
                return str(data.get("text") or "").strip()
            if data.get("segments"):
                return " ".join(str(seg.get("text") or "").strip() for seg in data.get("segments") or []).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    filtered = [
        line for line in lines
        if not line.lower().startswith(("loading", "loaded", "model", "transcribing", "progress"))
    ]
    return (filtered[-1] if filtered else lines[-1]).strip()


def run_cli(cli, selector, audio_path, language):
    attempts = []
    args = model_args_for(selector)
    attempts.append([cli, "transcribe", *args, "--audio-path", audio_path, "--language", language])
    attempts.append([cli, "transcribe", *args, "--audio-path", audio_path])
    if args:
        attempts.append([cli, "transcribe", "--audio-path", audio_path])

    last = None
    for cmd in attempts:
        proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True)
        last = proc
        if proc.stderr:
            sys.stderr.write(proc.stderr)
            sys.stderr.flush()
        if proc.returncode == 0:
            text = extract_text(proc.stdout)
            if text:
                return text
    detail = (last.stderr or last.stdout or "unknown Core ML CLI failure").strip() if last else "Core ML CLI did not run"
    raise RuntimeError(detail[:1000])


try:
    task = json.loads(sys.stdin.readline())
except Exception as exc:
    write_json({"fatal_error": str(exc), "stage": "task_decode"})
    sys.exit(1)

cli = task.get("cli") or os.environ.get("WHISPERKIT_CLI") or "argmax-cli"
selector = task.get("model") or ""
language = task.get("language") or "ko"

for path in task.get("chunk_paths") or []:
    try:
        text = run_cli(cli, selector, path, language)
        duration = wav_duration(path)
        write_json({
            "backend": "whisperkit-coreml",
            "loaded_model": selector,
            "segments": [{"start": 0.0, "end": duration, "text": text, "words": []}],
            "chunk_path": path,
        })
    except Exception as exc:
        write_json({"error": str(exc), "stage": "coreml_transcribe", "chunk_path": path, "model": selector})
        sys.exit(3)
'''
