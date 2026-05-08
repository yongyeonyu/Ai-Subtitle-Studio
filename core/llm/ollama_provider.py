# Version: 03.09.02
# Phase: PHASE2
"""Ollama adapter for local subtitle text splitting."""
from __future__ import annotations

import json
import http.client
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from typing import Any


_WARMED: set[str] = set()
_PROBE_OK_UNTIL: dict[str, float] = {}
_PROBE_FAILED_UNTIL: dict[str, float] = {}
_WARM_LOCK = threading.Lock()
_START_LOCK = threading.Lock()
_STOP_LOCK = threading.Lock()
_WARMUP_TIMEOUT_SEC = 8.0
_PROBE_OK_TTL_SEC = 180.0
_PROBE_FAILED_TTL_SEC = 60.0
_SERVER_READY_UNTIL = 0.0
_START_IN_PROGRESS_UNTIL = 0.0
_SERVER_READY_LOGGED_UNTIL = 0.0
_APP_STARTED_RUNTIME = False
_OLLAMA_ROOT_URL = "http://localhost:11434/"
_GENERATE_RETRY_STATUS_CODES = {500, 502, 503, 504}
_PROBE_RETRY_STATUS_CODES = {502, 503, 504}
_TRANSIENT_CONNECTION_FRAGMENTS = (
    "remote end closed connection",
    "connection reset",
    "connection refused",
    "connection aborted",
    "temporarily unavailable",
    "timed out",
    "timeout",
)
_FALLBACK_MODEL_PREFERENCES = (
    "llama3.2:1b",
    "gemma2:2b",
    "llama3.2:latest",
    "exaone3.5:2.4b",
    "qwen2.5:7b",
    "gemma2:9b",
    "exaone3.5:7.8b",
)
_APP_BUNDLE_OLLAMA_BINS = (
    "/Applications/Ollama.app/Contents/MacOS/ollama",
    os.path.expanduser("~/Applications/Ollama.app/Contents/MacOS/ollama"),
)


def _reset_ollama_runtime_state(*, clear_warmed: bool = True) -> None:
    global _APP_STARTED_RUNTIME, _SERVER_READY_UNTIL, _START_IN_PROGRESS_UNTIL, _SERVER_READY_LOGGED_UNTIL

    _SERVER_READY_UNTIL = 0.0
    _START_IN_PROGRESS_UNTIL = 0.0
    _SERVER_READY_LOGGED_UNTIL = 0.0
    _APP_STARTED_RUNTIME = False
    if clear_warmed:
        _WARMED.clear()


def is_ollama_server_running(timeout: float = 0.6) -> bool:
    try:
        req = urllib.request.Request(_OLLAMA_ROOT_URL)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return int(getattr(response, "status", 0) or 0) == 200
    except Exception:
        return False


def _is_ollama_api_ready(timeout: float = 0.8) -> bool:
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response.read(128)
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
        *_APP_BUNDLE_OLLAMA_BINS,
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
    ]
    result: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in result and os.path.exists(candidate):
            result.append(candidate)
    return result


def _start_ollama_server_process() -> bool:
    global _APP_STARTED_RUNTIME

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
            _APP_STARTED_RUNTIME = True
            return True
        except Exception:
            continue

    if os.name == "posix" and os.path.exists("/Applications/Ollama.app"):
        try:
            subprocess.Popen(["open", "-a", "Ollama"], **popen_kwargs)
            _APP_STARTED_RUNTIME = True
            return True
        except Exception:
            pass
    return False


def app_started_ollama_runtime() -> bool:
    return bool(_APP_STARTED_RUNTIME)


def restart_ollama_server(logger=None, *, wait_sec: float = 6.0) -> bool:
    """Restart Ollama runtime processes, then wait until the API is ready."""
    global _SERVER_READY_UNTIL, _START_IN_PROGRESS_UNTIL

    with _STOP_LOCK:
        _SERVER_READY_UNTIL = 0.0
        _START_IN_PROGRESS_UNTIL = 0.0
        stopped = 0
        try:
            from core.platform_compat import cleanup_ollama_runtime_processes

            stopped = cleanup_ollama_runtime_processes(timeout_sec=0.8)
        except Exception:
            stopped = 0
        if logger:
            if stopped:
                logger.log(f"🔄 AI 엔진(Ollama) 재시작 중... 기존 프로세스 {stopped}개 정리")
            else:
                logger.log("🔄 AI 엔진(Ollama) 재시작 중...")
        time.sleep(0.35)
        if not _start_ollama_server_process():
            if logger:
                logger.log("⚠️ AI 엔진(Ollama) 재시작 실패: 실행 파일을 찾을 수 없습니다.")
            return False

        deadline = time.monotonic() + max(1.0, float(wait_sec or 0.0))
        while time.monotonic() < deadline:
            if _is_ollama_api_ready(timeout=0.8):
                _SERVER_READY_UNTIL = time.monotonic() + 10.0
                if logger:
                    logger.log("✅ AI 엔진(Ollama) 재시작 완료")
                return True
            time.sleep(0.25)

        if logger:
            logger.log("⚠️ AI 엔진(Ollama) 재시작 후에도 응답이 없습니다.")
        return False


def ensure_ollama_server(logger=None, *, wait_sec: float = 5.0) -> bool:
    global _SERVER_READY_UNTIL, _START_IN_PROGRESS_UNTIL, _SERVER_READY_LOGGED_UNTIL

    now = time.monotonic()
    if _SERVER_READY_UNTIL > now:
        return True
    if _is_ollama_api_ready():
        _SERVER_READY_UNTIL = time.monotonic() + 10.0
        if logger and _SERVER_READY_LOGGED_UNTIL <= time.monotonic():
            logger.log("✅ AI 엔진(Ollama) 실행 중")
            _SERVER_READY_LOGGED_UNTIL = time.monotonic() + 15.0
        return True

    with _START_LOCK:
        now = time.monotonic()
        if _SERVER_READY_UNTIL > now:
            return True
        if _is_ollama_api_ready():
            _SERVER_READY_UNTIL = time.monotonic() + 10.0
            if logger and _SERVER_READY_LOGGED_UNTIL <= time.monotonic():
                logger.log("✅ AI 엔진(Ollama) 실행 중")
                _SERVER_READY_LOGGED_UNTIL = time.monotonic() + 15.0
            return True

        launched = False
        server_seen = is_ollama_server_running(timeout=0.5)
        if not server_seen and _START_IN_PROGRESS_UNTIL <= now:
            if not _start_ollama_server_process():
                if logger:
                    logger.log("⚠️ AI 엔진(Ollama) 실행 파일을 찾을 수 없습니다. Ollama 설치를 확인하세요.")
                return False
            launched = True
            _START_IN_PROGRESS_UNTIL = now + max(2.0, float(wait_sec or 0.0))
            if logger:
                logger.log("🚀 AI 엔진(Ollama) 자동 시작 중...")
        elif server_seen:
            _START_IN_PROGRESS_UNTIL = now + max(1.0, min(3.0, float(wait_sec or 0.0)))

        deadline = time.monotonic() + max(0.8, float(wait_sec or 0.0))
        while time.monotonic() < deadline:
            if _is_ollama_api_ready(timeout=0.8):
                _SERVER_READY_UNTIL = time.monotonic() + 10.0
                if logger:
                    if launched:
                        logger.log("✅ AI 엔진(Ollama) 자동 시작 완료")
                    elif _SERVER_READY_LOGGED_UNTIL <= time.monotonic():
                        logger.log("✅ AI 엔진(Ollama) 실행 중")
                        _SERVER_READY_LOGGED_UNTIL = time.monotonic() + 15.0
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


def _is_retryable_generate_error(exc: BaseException) -> bool:
    if _is_transient_ollama_connection_error(exc):
        return True
    if _is_timeout_error(exc):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        try:
            return int(getattr(exc, "code", 0) or 0) in _GENERATE_RETRY_STATUS_CODES
        except Exception:
            return False
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        return isinstance(reason, (ConnectionError, socket.timeout, TimeoutError))
    return False


def _is_transient_ollama_connection_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, socket.timeout, TimeoutError, http.client.RemoteDisconnected)):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        try:
            return int(getattr(exc, "code", 0) or 0) in _PROBE_RETRY_STATUS_CODES
        except Exception:
            return False
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (ConnectionError, socket.timeout, TimeoutError, http.client.RemoteDisconnected)):
            return True
    text = f"{exc} {getattr(exc, 'reason', '')}".lower()
    return any(fragment in text for fragment in _TRANSIENT_CONNECTION_FRAGMENTS)


def _build_generate_request(model: str, prompt: str, *, keep_alive: int = -1) -> urllib.request.Request:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": keep_alive,
        "options": {
            "temperature": 0.0,
            "num_predict": 256,
        },
    }).encode("utf-8")

    return urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Connection": "close",
        },
    )


def _read_http_error_body(exc: BaseException) -> str:
    if not isinstance(exc, urllib.error.HTTPError):
        return ""
    fp = getattr(exc, "fp", None)
    if fp is None:
        return ""
    try:
        raw = fp.read()
    except Exception:
        return ""
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return str(raw)


def _extract_ollama_error_message(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = _read_http_error_body(exc)
        if body:
            try:
                parsed = json.loads(body or "{}")
            except Exception:
                parsed = {}
            if isinstance(parsed, dict):
                message = str(parsed.get("error") or "").strip()
                if message:
                    return message
            text = body.strip()
            if text:
                return text
        return str(exc)
    return str(exc)


def _get_ollama_installed_models(timeout: float = 1.5) -> list[str]:
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception:
        return []
    rows = payload.get("models", []) if isinstance(payload, dict) else []
    result: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("model") or "").strip()
        if name and name not in result:
            result.append(name)
    return result


def _probe_ollama_model_once(model: str, *, timeout: float = 8.0) -> dict[str, Any]:
    try:
        req = _build_generate_request(model, "ping", keep_alive=-1)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return {"ok": True, "model": model, "message": ""}
    except Exception as exc:
        return {
            "ok": False,
            "model": model,
            "message": _extract_ollama_error_message(exc),
            "exception": exc,
        }


def _probe_ollama_model(model: str, *, timeout: float = 8.0, attempts: int = 3) -> dict[str, Any]:
    last: dict[str, Any] = {"ok": False, "model": model, "message": "알 수 없는 오류"}
    total = max(1, int(attempts or 1))
    for attempt in range(total):
        last = _probe_ollama_model_once(model, timeout=timeout)
        if last.get("ok"):
            return last
        exc = last.get("exception")
        if attempt >= total - 1 or not isinstance(exc, BaseException) or not _is_transient_ollama_connection_error(exc):
            return last
        ensure_ollama_server(wait_sec=2.0)
        time.sleep(0.35 * (attempt + 1))
    return last


def _candidate_fallback_models(model: str) -> list[str]:
    installed = _get_ollama_installed_models()
    result: list[str] = []
    current = str(model or "").strip()
    for name in _FALLBACK_MODEL_PREFERENCES:
        if name != current and name in installed and name not in result:
            result.append(name)
    for name in installed:
        if name != current and name not in result:
            result.append(name)
    return result


def ollama_probe_timeout(model: str, default: float = 8.0) -> float:
    text = str(model or "").strip().lower()
    timeout = max(3.0, float(default or 8.0))
    if text.startswith("gemma4:"):
        return max(timeout, 20.0)
    return timeout


def _mark_model_probe_ok(model: str, ttl_sec: float = _PROBE_OK_TTL_SEC) -> None:
    text = str(model or "").strip()
    if not text:
        return
    _PROBE_OK_UNTIL[text] = time.monotonic() + max(10.0, float(ttl_sec or _PROBE_OK_TTL_SEC))
    _WARMED.add(text)


def _model_probe_still_valid(model: str) -> bool:
    text = str(model or "").strip()
    if not text:
        return False
    until = float(_PROBE_OK_UNTIL.get(text, 0.0) or 0.0)
    return until > time.monotonic()


def _mark_model_probe_failed(model: str, ttl_sec: float = _PROBE_FAILED_TTL_SEC) -> None:
    text = str(model or "").strip()
    if not text:
        return
    _PROBE_FAILED_UNTIL[text] = time.monotonic() + max(5.0, float(ttl_sec or _PROBE_FAILED_TTL_SEC))


def _model_probe_recently_failed(model: str) -> bool:
    text = str(model or "").strip()
    if not text:
        return False
    until = float(_PROBE_FAILED_UNTIL.get(text, 0.0) or 0.0)
    return until > time.monotonic()


def resolve_ollama_model_for_request(
    model: str,
    logger=None,
    *,
    context: str = "LLM",
    timeout: float = 8.0,
    allow_fallback: bool = True,
) -> str:
    text = str(model or "").strip()
    if not text or "사용 안함" in text:
        return text
    if _model_probe_still_valid(text):
        return text
    if _model_probe_recently_failed(text):
        return text
    if not ensure_ollama_server(logger=logger, wait_sec=4.0):
        return text

    timeout = ollama_probe_timeout(text, timeout)
    probe = _probe_ollama_model(text, timeout=timeout, attempts=3)
    if probe.get("ok"):
        _mark_model_probe_ok(text)
        return text

    message = str(probe.get("message") or "알 수 없는 오류").strip()
    lowered = message.lower()
    model_load_failed = "unable to load model" in lowered or "model" in lowered and "load" in lowered
    if logger:
        if model_load_failed:
            logger.log(f"⚠️ {context}: Ollama 모델 로드 실패 `{text}`")
            logger.log(f"   원인: {message}")
        else:
            logger.log(f"⚠️ {context}: Ollama 모델 사전 점검 실패 `{text}` ({message})")

    if not allow_fallback:
        _mark_model_probe_failed(text)
        return text

    for fallback in _candidate_fallback_models(text):
        candidate = _probe_ollama_model(fallback, timeout=max(3.0, timeout * 0.75), attempts=2)
        if not candidate.get("ok"):
            continue
        _mark_model_probe_ok(fallback)
        if logger:
            logger.log(f"↪️ {context}: `{text}` 대신 `{fallback}` 으로 자동 대체합니다.")
        return fallback

    if logger:
        logger.log(f"⚠️ {context}: 사용 가능한 대체 Ollama 모델을 찾지 못했습니다. 현재 설정 `{text}` 유지")
    _mark_model_probe_failed(text)
    return text


def split_text(model: str, prompt: str, timeout: int = 120) -> list[str] | None:
    if not model or "사용 안함" in model:
        return None
    ensure_ollama_server(wait_sec=4.0)
    last_exc: BaseException | None = None

    for attempt in range(3):
        keep_alive = -1 if attempt == 0 else 0
        try:
            req = _build_generate_request(model, prompt, keep_alive=keep_alive)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out_text = json.loads(resp.read().decode("utf-8")).get("response", "")
            _mark_model_probe_ok(model)
            chunks = _parse_chunks(out_text)
            return chunks or None
        except Exception as exc:
            last_exc = exc
            if not _is_retryable_generate_error(exc) or attempt >= 2:
                raise
            try:
                _WARMED.discard(model)
                ensure_ollama_server(wait_sec=2.0)
            except Exception:
                pass
            time.sleep(0.35 * (attempt + 1))

    if last_exc:
        raise last_exc
    return None


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

            _mark_model_probe_ok(model, ttl_sec=max(_PROBE_OK_TTL_SEC, timeout * 6.0))
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


def running_local_llm_models(timeout: float = 1.5) -> set[str]:
    return _get_ollama_running_models(timeout=timeout)


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


def shutdown_local_ollama_runtime(
    models: list[str] | tuple[str, ...] | set[str] | None = None,
    logger=None,
    log_context: str = "런타임 정리",
    *,
    timeout_sec: float = 0.6,
) -> dict[str, Any]:
    context = str(log_context or "런타임 정리").strip() or "런타임 정리"
    stopped_models = stop_local_llm_models(models, logger=logger, log_context=context)
    stopped_processes = 0
    try:
        from core.platform_compat import cleanup_ollama_runtime_processes

        stopped_processes = int(
            cleanup_ollama_runtime_processes(timeout_sec=max(0.1, float(timeout_sec or 0.6))) or 0
        )
        if _is_ollama_api_ready(timeout=0.15):
            stopped_processes += int(
                cleanup_ollama_runtime_processes(timeout_sec=max(0.2, float(timeout_sec or 0.6))) or 0
            )
    except Exception as exc:
        if logger:
            logger.log(f"⚠️ {context}: Ollama 서버 종료 실패: {exc}")
    if stopped_models or stopped_processes:
        _reset_ollama_runtime_state()
    if stopped_processes and logger:
        logger.log(f"🛑 {context}: Ollama 서버/러너 종료 완료 ({stopped_processes}개)")
    return {
        "models": list(stopped_models),
        "processes": stopped_processes,
    }


def shutdown_local_ollama_runtime_async(
    models: list[str] | tuple[str, ...] | set[str] | None = None,
    logger=None,
    log_context: str = "런타임 정리",
    *,
    timeout_sec: float = 0.6,
) -> threading.Thread:
    thread = threading.Thread(
        target=shutdown_local_ollama_runtime,
        kwargs={
            "models": list(models or []),
            "logger": logger,
            "log_context": log_context,
            "timeout_sec": timeout_sec,
        },
        daemon=True,
        name="ollama-shutdown-runtime",
    )
    thread.start()
    return thread
