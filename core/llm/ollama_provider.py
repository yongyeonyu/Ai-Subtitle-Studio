# Version: 03.09.02
# Phase: PHASE2
"""Ollama adapter for local subtitle text splitting."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request


_WARMED: set[str] = set()
_WARM_LOCK = threading.Lock()
_STOP_LOCK = threading.Lock()
_WARMUP_TIMEOUT_SEC = 8.0
_OLLAMA_ROOT_URL = "http://localhost:11434/"


def is_ollama_server_running(timeout: float = 0.6) -> bool:
    try:
        req = urllib.request.Request(_OLLAMA_ROOT_URL)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return int(getattr(response, "status", 0) or 0) == 200
    except Exception:
        return False


def _iter_ollama_bins() -> list[str]:
    candidates = [
        shutil.which("ollama"),
        shutil.which("ollama.exe"),
        "/opt/homebrew/bin/ollama",
        "/usr/local/bin/ollama",
        os.path.expanduser("~/.ollama/bin/ollama"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
    ]
    result: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in result and os.path.exists(candidate):
            result.append(candidate)
    return result


def _start_ollama_server_process() -> bool:
    popen_kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        popen_kwargs["start_new_session"] = True

    for ollama_bin in _iter_ollama_bins():
        try:
            subprocess.Popen([ollama_bin, "serve"], **popen_kwargs)
            return True
        except Exception:
            continue

    if os.name == "posix" and os.path.exists("/Applications/Ollama.app"):
        try:
            subprocess.Popen(["open", "-a", "Ollama"], **popen_kwargs)
            return True
        except Exception:
            pass
    return False


def ensure_ollama_server(logger=None, *, wait_sec: float = 5.0) -> bool:
    if is_ollama_server_running():
        if logger:
            logger.log("✅ AI 엔진(Ollama) 실행 중")
        return True

    if not _start_ollama_server_process():
        if logger:
            logger.log("⚠️ AI 엔진(Ollama) 실행 파일을 찾을 수 없습니다. Ollama 설치를 확인하세요.")
        return False

    if logger:
        logger.log("🚀 AI 엔진(Ollama) 자동 시작 중...")
    deadline = time.monotonic() + max(0.5, float(wait_sec or 0.0))
    while time.monotonic() < deadline:
        if is_ollama_server_running(timeout=0.4):
            if logger:
                logger.log("✅ AI 엔진(Ollama) 자동 시작 완료")
            return True
        time.sleep(0.25)

    if logger:
        logger.log("⚠️ AI 엔진(Ollama) 자동 시작 확인 실패. Ollama 설치 상태를 확인하세요.")
    return False


def _parse_chunks(out_text: str) -> list[str]:
    try:
        parsed = json.loads(out_text or "")
        if isinstance(parsed, dict) and isinstance(parsed.get("result"), list):
            return [str(x) for x in parsed["result"] if isinstance(x, str)]
        if isinstance(parsed, list):
            return [str(x) for x in parsed if isinstance(x, str)]
    except Exception:
        pass
    return [m for m in re.findall(r'"([^"]*)"', out_text or "") if m != "result" and len(m) > 1]


def split_text(model: str, prompt: str, timeout: int = 120) -> list[str] | None:
    if not model or "사용 안함" in model:
        return None
    ensure_ollama_server(wait_sec=4.0)

    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": -1,
        "options": {
            "temperature": 0.0,
            "num_predict": 256,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Connection": "keep-alive",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out_text = json.loads(resp.read().decode("utf-8")).get("response", "")
    chunks = _parse_chunks(out_text)
    return chunks or None


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    reason = getattr(exc, "reason", None)
    return isinstance(reason, (TimeoutError, socket.timeout))


def warmup_model(model: str, logger=None, timeout: float = _WARMUP_TIMEOUT_SEC) -> None:
    if not model or "사용 안함" in model:
        return

    with _WARM_LOCK:
        if model in _WARMED:
            return
        if not ensure_ollama_server(logger=logger, wait_sec=4.0):
            _WARMED.add(model)
            return

        try:
            body = json.dumps({
                "model": model,
                "prompt": " ",
                "stream": False,
                "keep_alive": -1,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 1,
                },
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Connection": "keep-alive",
                },
            )

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read()

            _WARMED.add(model)
            if logger:
                logger.log(f"🔥 Ollama 워밍업 완료: {model}")
        except Exception as e:
            if _is_timeout_error(e):
                _WARMED.add(model)
                if logger:
                    logger.log(
                        f"⏭️ Ollama 워밍업 건너뜀: {model} 모델 로딩이 {timeout:.0f}초를 넘어 "
                        "실제 LLM 요청에서 이어 처리합니다."
                    )
                return
            if isinstance(e, urllib.error.URLError):
                _WARMED.add(model)
                if logger:
                    logger.log(f"⚠️ Ollama 워밍업 건너뜀: 서버 연결 확인 필요 ({e})")
                return
            if logger:
                logger.log(f"⚠️ Ollama 워밍업 실패: {e}")


def _post_ollama_json(path: str, payload: dict, timeout: float = 2.0) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:11434{path}",
        data=body,
        headers={"Content-Type": "application/json", "Connection": "close"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    try:
        parsed = json.loads(raw or "{}")
    except Exception:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def _get_ollama_running_models(timeout: float = 1.5) -> set[str]:
    try:
        req = urllib.request.Request("http://localhost:11434/api/ps")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception:
        return set()
    models = payload.get("models", []) if isinstance(payload, dict) else []
    names = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name and "사용 안함" not in name:
            names.add(name)
    return names


def _is_local_ollama_model_name(model: str) -> bool:
    text = str(model or "").strip()
    if not text or "사용 안함" in text:
        return False
    lowered = text.lower()
    blocked_tokens = ("gemini", "openai", "gpt-", "api", "claude")
    return not any(token in lowered for token in blocked_tokens)


def stop_local_llm_models(
    models: list[str] | tuple[str, ...] | set[str] | None = None,
    logger=None,
    log_context: str = "홈 이동",
) -> list[str]:
    candidates = {
        str(model).strip()
        for model in (models or [])
        if _is_local_ollama_model_name(str(model or ""))
    }
    candidates.update(_get_ollama_running_models())
    stopped: list[str] = []
    if not candidates:
        return stopped

    cli = shutil.which("ollama")
    with _STOP_LOCK:
        for model in sorted(candidates):
            ok = False
            try:
                _post_ollama_json("/api/generate", {"model": model, "prompt": "", "keep_alive": 0}, timeout=2.0)
                ok = True
            except Exception:
                pass
            if cli:
                try:
                    result = subprocess.run(
                        [cli, "stop", model],
                        capture_output=True,
                        text=True,
                        timeout=2.0,
                    )
                    ok = ok or result.returncode == 0
                except Exception:
                    pass
            if ok:
                stopped.append(model)
                _WARMED.discard(model)
    if stopped and logger:
        context = str(log_context or "런타임 정리").strip() or "런타임 정리"
        logger.log(f"🛑 {context}: Ollama 모델 종료/언로드 완료 ({', '.join(stopped)})")
    return stopped


def stop_local_llm_models_async(
    models: list[str] | tuple[str, ...] | set[str] | None = None,
    logger=None,
    log_context: str = "홈 이동",
) -> threading.Thread:
    thread = threading.Thread(
        target=stop_local_llm_models,
        args=(list(models or []), logger, log_context),
        daemon=True,
        name="ollama-stop-models",
    )
    thread.start()
    return thread
