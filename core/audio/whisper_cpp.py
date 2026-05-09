# Version: 03.25.01
# Phase: NATIVE_STT_PIPELINE_RELEASED
"""Optional whisper.cpp CLI backend for native STT experiments."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from core.platform_compat import hidden_subprocess_kwargs
from core.runtime.logger import get_logger


WHISPER_CPP_PREFIXES = ("whisper.cpp:", "whisper_cpp:", "whisper-cpp:")


def is_whisper_cpp_model(model: str) -> bool:
    lowered = str(model or "").strip().lower()
    return bool(lowered.startswith(WHISPER_CPP_PREFIXES) or "whisper.cpp" in lowered)


def whisper_cpp_model_selector(model: str) -> str:
    value = str(model or "").strip()
    lowered = value.lower()
    for prefix in WHISPER_CPP_PREFIXES:
        if lowered.startswith(prefix):
            return value[len(prefix):].strip() or "large-v3-turbo"
    if "whisper.cpp" in lowered:
        return "large-v3-turbo"
    return value or "large-v3-turbo"


def find_whisper_cpp_binary() -> str:
    explicit = os.environ.get("WHISPER_CPP_BINARY") or os.environ.get("AI_SUBTITLE_WHISPER_CPP_BIN")
    candidates = [explicit] if explicit else []
    candidates.extend([
        shutil.which("whisper-cli"),
        shutil.which("whisper-cpp"),
        shutil.which("whisper.cpp"),
        shutil.which("main"),
    ])
    repo_root = Path(__file__).resolve().parents[2]
    candidates.extend([
        repo_root / "tools" / "whisper.cpp" / "build" / "bin" / "whisper-cli",
        repo_root / "tools" / "whisper.cpp" / "main",
        repo_root / "bin" / "whisper-cli",
    ])
    for candidate in candidates:
        if not candidate:
            continue
        text = os.path.expanduser(os.path.expandvars(str(candidate)))
        found = shutil.which(text) or text
        if os.path.exists(found) and os.access(found, os.X_OK):
            return found
    return ""


def _model_filename_candidates(selector: str) -> list[str]:
    raw = str(selector or "").strip()
    if not raw:
        raw = "large-v3-turbo"
    stem = raw
    if "/" in stem:
        stem = stem.rsplit("/", 1)[-1]
    stem = stem.replace("whisper-", "").replace("mlx-", "")
    names = [raw]
    if not stem.startswith("ggml-"):
        names.append(f"ggml-{stem}.bin")
    if not stem.endswith(".bin"):
        names.append(f"{stem}.bin")
    names.append(stem)
    return list(dict.fromkeys(name for name in names if name))


def resolve_whisper_cpp_model_path(model: str) -> str:
    explicit = os.environ.get("AI_SUBTITLE_WHISPER_CPP_MODEL") or os.environ.get("WHISPER_CPP_MODEL")
    if explicit:
        path = Path(os.path.expandvars(os.path.expanduser(explicit)))
        if path.exists():
            return str(path)

    selector = whisper_cpp_model_selector(model)
    direct = Path(os.path.expandvars(os.path.expanduser(selector)))
    if direct.exists():
        return str(direct)

    repo_root = Path(__file__).resolve().parents[2]
    search_dirs = [
        os.environ.get("AI_SUBTITLE_WHISPER_CPP_MODEL_DIR"),
        os.environ.get("WHISPER_CPP_MODEL_DIR"),
        repo_root / "models" / "whisper.cpp",
        repo_root / "models" / "ggml",
        repo_root / "tools" / "whisper.cpp" / "models",
        Path("/opt/homebrew/opt/whisper-cpp/share/whisper-cpp"),
        Path("/usr/local/opt/whisper-cpp/share/whisper-cpp"),
        Path.home() / "Library" / "Application Support" / "ai_subtitle_studio" / "models" / "whisper.cpp",
        Path.home() / ".cache" / "whisper.cpp",
        Path.home() / "Downloads",
    ]
    for directory in search_dirs:
        if not directory:
            continue
        root = Path(os.path.expandvars(os.path.expanduser(str(directory))))
        if not root.exists():
            continue
        for name in _model_filename_candidates(selector):
            candidate = root / name
            if candidate.exists() and candidate.is_file():
                return str(candidate)
    return ""


def _thread_count() -> int:
    raw = os.environ.get("AI_SUBTITLE_WHISPER_CPP_THREADS") or os.environ.get("WHISPER_CPP_THREADS")
    try:
        value = int(raw or 0)
    except Exception:
        value = 0
    if value > 0:
        return max(1, min(16, value))
    try:
        return max(1, min(8, (os.cpu_count() or 4) - 1))
    except Exception:
        return 4


def _attach_stderr_logger(proc, log_label: str = "STT"):
    label = (log_label or "STT").strip() or "STT"

    def _reader():
        try:
            for line in proc.stderr:
                text = str(line or "").rstrip()
                if text:
                    get_logger().log(f"[{label}] [whisper.cpp] {text}")
        except Exception:
            pass

    threading.Thread(target=_reader, daemon=True, name="whisper-cpp-stderr").start()


def run_whisper(
    chunk_paths: list,
    model: str,
    language: str,
    temperature_tuple: str = "(0.0,)",
    log_label: str = "STT",
    word_timestamps: bool = False,
    options: dict | None = None,
):
    """Run whisper.cpp in a small JSONL-compatible worker subprocess."""
    binary = find_whisper_cpp_binary()
    model_path = resolve_whisper_cpp_model_path(model)
    if not binary:
        get_logger().log(
            "  ⚠️ [whisper.cpp STT] whisper-cli 바이너리를 찾지 못했습니다. "
            "WHISPER_CPP_BINARY를 지정하면 native 백엔드를 사용할 수 있습니다."
        )
        return None
    if not model_path:
        selector = whisper_cpp_model_selector(model)
        get_logger().log(
            f"  ⚠️ [whisper.cpp STT] ggml 모델 파일을 찾지 못했습니다: {selector}. "
            "AI_SUBTITLE_WHISPER_CPP_MODEL 또는 WHISPER_CPP_MODEL_DIR를 지정해 주세요."
        )
        return None

    label = (log_label or "STT").strip() or "STT"
    get_logger().log(f"  🧪 [{label}] whisper.cpp native worker 시작: {Path(model_path).name}")
    task = {
        "binary": binary,
        "model_path": model_path,
        "chunk_paths": list(chunk_paths or []),
        "language": str(language or "ko"),
        "threads": _thread_count(),
        "word_timestamps": bool(word_timestamps),
        "options": dict(options or {}),
    }
    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", _build_worker_script()],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **hidden_subprocess_kwargs(strip_qt=True),
        )
        proc.stdin.write(json.dumps(task, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        proc.stdin.close()
    except Exception as exc:
        get_logger().log(f"  ⚠️ [whisper.cpp STT] worker 시작 실패: {exc}")
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        return None

    _attach_stderr_logger(proc, log_label=label)
    return proc


def _build_worker_script() -> str:
    return r'''
import json
import os
import re
import subprocess
import sys
import tempfile
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


def parse_clock(value):
    text = str(value or "").strip()
    if not text:
        return 0.0
    parts = text.replace(",", ".").split(":")
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        return float(text)
    except Exception:
        return 0.0


def parse_json_segments(payload, duration, want_words):
    transcription = payload.get("transcription")
    if not isinstance(transcription, list):
        transcription = payload.get("segments")
    if not isinstance(transcription, list):
        text = str(payload.get("text") or "").strip()
        return [{"start": 0.0, "end": duration, "text": text, "words": []}] if text else []

    segments = []
    for item in transcription:
        if not isinstance(item, dict):
            continue
        offsets = item.get("offsets") if isinstance(item.get("offsets"), dict) else {}
        timestamps = item.get("timestamps") if isinstance(item.get("timestamps"), dict) else {}
        if offsets and offsets.get("from") is not None and offsets.get("to") is not None:
            try:
                start = float(offsets.get("from") or 0.0) / 1000.0
                end = float(offsets.get("to") or 0.0) / 1000.0
            except Exception:
                start, end = 0.0, duration
        elif timestamps:
            start = parse_clock(timestamps.get("from"))
            end = parse_clock(timestamps.get("to"))
        else:
            try:
                start = float(item.get("start", 0.0) or 0.0)
                end = float(item.get("end", duration) or duration)
            except Exception:
                start, end = 0.0, duration
        text = str(item.get("text") or "").strip()
        words = []
        if want_words:
            for token in item.get("tokens") or item.get("words") or []:
                if not isinstance(token, dict):
                    continue
                word = str(token.get("word") or token.get("text") or "").strip()
                if not word:
                    continue
                token_offsets = token.get("offsets") if isinstance(token.get("offsets"), dict) else {}
                try:
                    if token_offsets:
                        w_start = float(token_offsets.get("from") or 0.0) / 1000.0
                        w_end = float(token_offsets.get("to") or 0.0) / 1000.0
                    else:
                        w_start = float(token.get("start", start) or start)
                        w_end = float(token.get("end", end) or end)
                except Exception:
                    w_start, w_end = start, end
                if w_end > w_start:
                    words.append({"word": word, "start": w_start, "end": w_end})
        if text and end > start:
            segments.append({"start": start, "end": end, "text": text, "words": words})
    return segments


def parse_stdout_segments(stdout, duration):
    segments = []
    pattern = re.compile(r"\[?\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\]?\s*(.*)")
    for line in (stdout or "").splitlines():
        match = pattern.search(line)
        if not match:
            continue
        text = match.group(3).strip()
        if text:
            segments.append({
                "start": parse_clock(match.group(1)),
                "end": parse_clock(match.group(2)),
                "text": text,
                "words": [],
            })
    if segments:
        return segments
    filtered = [
        line.strip()
        for line in (stdout or "").splitlines()
        if line.strip() and not line.lower().startswith(("whisper_", "system_info", "main:"))
    ]
    text = " ".join(filtered).strip()
    return [{"start": 0.0, "end": duration, "text": text, "words": []}] if text else []


def run_cli(binary, model_path, audio_path, language, threads, want_words):
    duration = wav_duration(audio_path)
    with tempfile.TemporaryDirectory(prefix="whisper_cpp_") as tmp:
        output_base = os.path.join(tmp, "result")
        common = [binary, "-m", model_path, "-f", audio_path, "-t", str(max(1, int(threads or 1))), "-np"]
        if language:
            common.extend(["-l", language])
        attempts = [
            [*common, "-ojf", "-of", output_base],
            [*common, "-oj", "-of", output_base],
            common,
        ]
        if want_words:
            attempts.insert(0, [*common, "-ojf", "-owts", "-of", output_base])

        last = None
        for cmd in attempts:
            proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True)
            last = proc
            if proc.stderr:
                sys.stderr.write(proc.stderr)
                sys.stderr.flush()
            json_path = output_base + ".json"
            if proc.returncode == 0 and os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8", errors="replace") as handle:
                    return parse_json_segments(json.load(handle), duration, want_words)
            if proc.returncode == 0:
                segments = parse_stdout_segments(proc.stdout, duration)
                if segments:
                    return segments
        detail = (last.stderr or last.stdout or "unknown whisper.cpp failure").strip() if last else "whisper.cpp did not run"
        raise RuntimeError(detail[:1200])


try:
    task = json.loads(sys.stdin.readline())
except Exception as exc:
    write_json({"fatal_error": str(exc), "stage": "task_decode"})
    sys.exit(1)

binary = task.get("binary") or "whisper-cli"
model_path = task.get("model_path") or ""
language = task.get("language") or "ko"
threads = int(task.get("threads") or 4)
want_words = bool(task.get("word_timestamps", False))

for path in task.get("chunk_paths") or []:
    try:
        segments = run_cli(binary, model_path, path, language, threads, want_words)
        write_json({
            "backend": "whisper.cpp",
            "loaded_model": os.path.basename(model_path),
            "segments": segments,
            "chunk_path": path,
            "word_timestamps": want_words,
        })
    except Exception as exc:
        write_json({"error": str(exc), "stage": "whisper_cpp_transcribe", "chunk_path": path})
        sys.exit(3)
'''


__all__ = [
    "WHISPER_CPP_PREFIXES",
    "find_whisper_cpp_binary",
    "is_whisper_cpp_model",
    "resolve_whisper_cpp_model_path",
    "run_whisper",
    "whisper_cpp_model_selector",
]
