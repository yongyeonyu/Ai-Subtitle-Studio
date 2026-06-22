from __future__ import annotations

import os
import shutil
import threading
import uuid

from core.native_json import dumps_json_bytes
from core.platform_compat import hidden_subprocess_kwargs
from core.runtime import config
from core.runtime.logger import get_logger


WHISPERKIT_PERSISTENT_PREFIX = "whisperkit-persistent:"
_SUPPORTED_WHISPERKIT_SELECTORS = {
    "large-v3",
    "whisper-large-v3",
    "openai/whisper-large-v3",
    "openai_whisper-large-v3",
    "large-v3-v20240930_626mb",
    "large-v3-v20240930_626MB",
    "large-v3-turbo",
    "whisper-large-v3-turbo",
    "openai/whisper-large-v3-turbo",
    "openai_whisper-large-v3_turbo",
    "large-v3-v20240930_turbo_632mb",
    "large-v3-v20240930_turbo_632MB",
}
def is_whisperkit_persistent_model(model: str) -> bool:
    return bool(config.IS_MAC and str(model or "").strip().lower().startswith(WHISPERKIT_PERSISTENT_PREFIX))


def whisperkit_model_selector(model: str) -> str:
    value = str(model or "").strip()
    if value.lower().startswith(WHISPERKIT_PERSISTENT_PREFIX):
        value = value[len(WHISPERKIT_PERSISTENT_PREFIX):].strip()
    return value or "large-v3"


def whisperkit_selector_is_supported(selector: str) -> bool:
    value = str(selector or "").strip()
    if not value:
        return True
    if os.path.exists(os.path.expanduser(value)):
        return True
    return value in _SUPPORTED_WHISPERKIT_SELECTORS or value.lower() in _SUPPORTED_WHISPERKIT_SELECTORS


def is_supported_whisperkit_model(model: str) -> bool:
    return whisperkit_selector_is_supported(whisperkit_model_selector(model))


def find_whisperkit_persistent_worker() -> str:
    explicit = os.environ.get("WHISPERKIT_PERSISTENT_WORKER", "").strip()
    if explicit:
        expanded = os.path.expanduser(explicit)
        if os.path.exists(expanded):
            return expanded
        found = shutil.which(explicit)
        if found:
            return found
    return shutil.which("WhisperKitPersistentWorker") or ""


def _attach_stderr_logger(proc, log_label: str = "STT") -> None:
    def _reader():
        try:
            for line in proc.stderr:
                if isinstance(line, (bytes, bytearray)):
                    text = line.decode("utf-8", errors="replace").strip()
                else:
                    text = str(line or "").strip()
                if text:
                    get_logger().log(f"[{log_label}] [whisperkit-persistent] {text}")
        except Exception:
            pass

    threading.Thread(target=_reader, daemon=True, name="whisperkit-persistent-stderr").start()


def _write_worker_json_line(stdin, payload: dict) -> None:
    if stdin is None:
        raise RuntimeError("Swift WhisperKit worker stdin이 닫혀 있습니다.")
    line = dumps_json_bytes(payload, append_newline=True)
    try:
        if getattr(stdin, "encoding", None):
            stdin.write(line.decode("utf-8"))
        else:
            stdin.write(line)
    except TypeError:
        stdin.write(line.decode("utf-8"))
    stdin.flush()


def ensure_worker(proc=None, log_label: str = "STT"):
    if proc and proc.poll() is None:
        return proc

    if not config.IS_MAC:
        return None
    worker = find_whisperkit_persistent_worker()
    if not worker:
        get_logger().log(
            "  ⚠️ [WhisperKit Native] persistent worker 바이너리를 찾지 못해 MLX Whisper로 대체합니다. "
            "WHISPERKIT_PERSISTENT_WORKER 경로를 지정하면 Swift 백엔드를 사용할 수 있습니다."
        )
        return None

    try:
        new_proc = subprocess.Popen(
            [worker],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            **hidden_subprocess_kwargs(strip_qt=True),
        )
        _attach_stderr_logger(new_proc, log_label=log_label)
        get_logger().log(f"  🍎 [{log_label}] Swift WhisperKit persistent worker 시작")
        return new_proc
    except Exception as exc:
        get_logger().log(f"  ⚠️ [WhisperKit Native] worker 시작 실패, MLX Whisper로 대체합니다: {exc}")
        return None


def submit_task(
    proc,
    chunk_paths: list,
    model: str,
    language: str,
    temperature_values: list[float] | None = None,
    word_timestamps: bool = False,
    concurrent_worker_count: int | None = None,
    stream_results: bool | None = None,
    compute_profile: str | None = None,
) -> str:
    if proc is None or proc.poll() is not None:
        raise RuntimeError("Swift WhisperKit worker가 실행 중이 아닙니다.")
    if not is_supported_whisperkit_model(model):
        raise ValueError(f"unsupported_whisperkit_model:{whisperkit_model_selector(model)}")

    task_id = uuid.uuid4().hex
    payload = {
        "op": "transcribe",
        "task_id": task_id,
        "chunk_paths": list(chunk_paths or []),
        "model": whisperkit_model_selector(model),
        "language": str(language or "ko"),
        "temperature_values": list(temperature_values or [0.0]),
        "word_timestamps": bool(word_timestamps),
    }
    if concurrent_worker_count is not None:
        try:
            payload["concurrent_worker_count"] = max(1, int(concurrent_worker_count or 1))
        except Exception:
            payload["concurrent_worker_count"] = 1
    if stream_results is not None:
        payload["stream_results"] = bool(stream_results)
    if compute_profile is not None:
        payload["compute_profile"] = str(compute_profile or "").strip() or "ane_gpu"
    _write_worker_json_line(proc.stdin, payload)
    return task_id


def stop_worker(proc) -> None:
    if not proc:
        return

    try:
        if proc.poll() is None and proc.stdin:
            _write_worker_json_line(
                proc.stdin,
                {
                    "op": "quit",
                    "task_id": "quit",
                    "chunk_paths": [],
                    "model": "",
                    "language": "ko",
                    "word_timestamps": False,
                },
            )
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


def run_whisper(
    chunk_paths: list,
    model: str,
    language: str,
    temperature_tuple: str = "(0.0,)",
    log_label: str = "STT",
    word_timestamps: bool = False,
):
    """Compatibility wrapper for the Swift WhisperKit JSONL worker.

    This backend is the macOS-native STT path. MLX remains the quality-safe
    fallback when the Swift worker is not built or cannot start.
    """
    if not is_supported_whisperkit_model(model):
        get_logger().log(
            f"  ⚠️ [{log_label}] WhisperKit Native 미지원 모델이라 원래 STT 경로로 되돌립니다: "
            f"{whisperkit_model_selector(model)}"
        )
        return None
    try:
        temp_values = [
            float(part.strip())
            for part in str(temperature_tuple or "(0.0,)")
            .strip()
            .strip("()")
            .split(",")
            if part.strip()
        ] or [0.0]
    except Exception:
        temp_values = [0.0]

    proc = ensure_worker(log_label=log_label)
    if proc is None:
        return None
    try:
        submit_task(
            proc=proc,
            chunk_paths=chunk_paths,
            model=model,
            language=language,
            temperature_values=temp_values,
            word_timestamps=word_timestamps,
            concurrent_worker_count=None,
        )
        return proc
    except Exception as exc:
        get_logger().log(f"  ⚠️ [WhisperKit Native] worker 요청 실패, MLX Whisper로 대체합니다: {exc}")
        stop_worker(proc)
        return None


__all__ = [
    "WHISPERKIT_PERSISTENT_PREFIX",
    "ensure_worker",
    "find_whisperkit_persistent_worker",
    "is_whisperkit_persistent_model",
    "is_supported_whisperkit_model",
    "run_whisper",
    "stop_worker",
    "submit_task",
    "whisperkit_selector_is_supported",
    "whisperkit_model_selector",
]
