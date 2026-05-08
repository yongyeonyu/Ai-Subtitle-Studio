# Version: 03.08.12
# Phase: PHASE2
"""
core/platform_compat.py
Cross-platform subprocess/path helpers for macOS and Windows.
"""
from __future__ import annotations

import os
import signal
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.runtime import config

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def is_windows() -> bool:
    return bool(getattr(config, "IS_WINDOWS", False) or os.name == "nt")


def resolve_executable(name: str, env_var: str | None = None) -> str:
    """Return an executable path, preferring env/config/bundled locations."""
    candidates: list[str | Path | None] = []
    if env_var:
        candidates.append(os.environ.get(env_var))

    candidates.extend([
        shutil.which(name),
        shutil.which(f"{name}.exe") if is_windows() and not name.endswith(".exe") else None,
    ])

    exe_name = f"{name}.exe" if is_windows() and not name.endswith(".exe") else name
    candidates.extend([
        PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / exe_name,
        PROJECT_ROOT / "ffmpeg" / "bin" / exe_name,
        PROJECT_ROOT / "bin" / exe_name,
    ])

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(os.path.expandvars(os.path.expanduser(str(candidate))))
        if path.exists():
            return str(path)

    return exe_name


def ffmpeg_binary() -> str:
    return resolve_executable("ffmpeg", "FFMPEG_BINARY")


def ffprobe_binary() -> str:
    return resolve_executable("ffprobe", "FFPROBE_BINARY")


def rnnoise_binary() -> str:
    binary = os.environ.get("RNNOISE_BINARY")
    if binary:
        return resolve_executable(Path(binary).name, "RNNOISE_BINARY")
    demo = resolve_executable("rnnoise_demo", "RNNOISE_BINARY")
    if Path(demo).exists() or shutil.which(demo):
        return demo
    return resolve_executable("rnnoise")


def subprocess_env(extra: dict | None = None, *, strip_qt: bool = False) -> dict:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        from core.performance import native_runtime_env_overrides

        for key, value in native_runtime_env_overrides().items():
            env.setdefault(key, value)
    except Exception:
        pass
    for key in (
        "MallocStackLogging",
        "MallocStackLoggingNoCompact",
        "MallocStackLoggingDirectory",
        "MallocScribble",
        "MallocPreScribble",
        "MallocGuardEdges",
    ):
        env.pop(key, None)
    if strip_qt:
        for key in (
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QML2_IMPORT_PATH",
            "PYQTGRAPH_QT_LIB",
        ):
            env.pop(key, None)
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


def hidden_subprocess_kwargs(*, strip_qt: bool = False, extra_env: dict | None = None) -> dict:
    kwargs = {"env": subprocess_env(extra_env, strip_qt=strip_qt)}
    if is_windows():
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def _is_preview_proxy_ffmpeg_command(command: str) -> bool:
    command = str(command or "")
    if "ffmpeg" not in command.lower():
        return False
    normalized_command = command.replace("\\", "/")
    preview_cache_dir = str(PROJECT_ROOT / "dataset" / "video_preview_cache").replace("\\", "/")
    return (
        preview_cache_dir in normalized_command
        and "_preview_720p" in normalized_command
        and ".tmp.mp4" in normalized_command
    )


def _process_table() -> list[tuple[int, int, str]]:
    try:
        output = subprocess.check_output(
            ["ps", "-axo", "pid=,ppid=,command="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []

    rows: list[tuple[int, int, str]] = []
    for line in output.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        try:
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
        except ValueError:
            continue
    return rows


def _terminate_pids(pids: list[int], *, timeout_sec: float = 0.2) -> int:
    current_pid = os.getpid()
    unique_pids = sorted({int(pid) for pid in pids if int(pid) > 0 and int(pid) != current_pid})
    stopped = 0
    for pid in unique_pids:
        try:
            os.kill(pid, signal.SIGTERM)
            stopped += 1
        except (ProcessLookupError, PermissionError, OSError):
            pass

    if stopped and timeout_sec > 0:
        time.sleep(float(timeout_sec))
        for pid in unique_pids:
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError, OSError):
                continue
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    return stopped


def cleanup_stale_preview_proxy_processes(*, timeout_sec: float = 0.2) -> int:
    """Terminate legacy preview-cache ffmpeg encoders left after app shutdown."""
    if is_windows():
        return 0

    targets: list[int] = []
    current_pid = os.getpid()
    for pid, _ppid, command in _process_table():
        if pid == current_pid:
            continue
        if _is_preview_proxy_ffmpeg_command(command):
            targets.append(pid)

    return _terminate_pids(targets, timeout_sec=timeout_sec)


def _is_heavy_app_child_command(command: str) -> bool:
    lowered = str(command or "").replace("\\", "/").lower()
    heavy_names = (
        "ffmpeg", "ffprobe", "rnnoise",
        "whisper_worker.py", "whisper_transformers.py", "whisper_faster.py",
        "whisper_coreml.py", "whisper_mlx.py", "resemble_enhance_runner.py",
        "ollama runner", "ollama_llama_server",
    )
    return any(name in lowered for name in heavy_names)


def cleanup_app_child_processes(*, root_pid: int | None = None, timeout_sec: float = 0.4) -> int:
    """Terminate heavy subprocess descendants owned by the current app process."""
    if is_windows():
        return 0
    root_pid = int(root_pid or os.getpid())
    rows = _process_table()
    children_by_parent: dict[int, list[tuple[int, str]]] = {}
    for pid, ppid, command in rows:
        children_by_parent.setdefault(ppid, []).append((pid, command))

    targets: list[int] = []
    stack = [root_pid]
    seen = {root_pid}
    while stack:
        parent = stack.pop()
        for pid, command in children_by_parent.get(parent, []):
            if pid in seen:
                continue
            seen.add(pid)
            stack.append(pid)
            if _is_heavy_app_child_command(command):
                targets.append(pid)

    return _terminate_pids(targets, timeout_sec=timeout_sec)


def _is_ollama_runtime_command(command: str) -> bool:
    lowered = str(command or "").replace("\\", "/").lower()
    if "ollama runner" in lowered:
        return True
    if "ollama serve" in lowered:
        return True
    if "ollama_llama_server" in lowered:
        return True
    if "/ollama.app/contents/resources/ollama" in lowered:
        return True
    return "/ollama.app/contents/macos/ollama" in lowered


def _launchctl_has_label(label: str) -> bool:
    target = str(label or "").strip()
    if not target:
        return False
    try:
        output = subprocess.check_output(
            ["launchctl", "list"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False
    return any(line.rstrip().endswith(target) for line in output.splitlines())


def _stop_managed_ollama_service(*, timeout_sec: float = 0.4) -> int:
    if is_windows() or not _launchctl_has_label("homebrew.mxcl.ollama"):
        return 0

    deadline = max(1.5, float(timeout_sec or 0.4) * 6.0)
    brew = shutil.which("brew")
    if brew:
        try:
            result = subprocess.run(
                [brew, "services", "stop", "ollama"],
                capture_output=True,
                text=True,
                timeout=deadline,
                env=subprocess_env(strip_qt=True),
            )
            if result.returncode == 0:
                return 1
        except Exception:
            pass

    uid = os.getuid()
    for domain in (f"gui/{uid}", f"user/{uid}"):
        try:
            result = subprocess.run(
                ["launchctl", "bootout", f"{domain}/homebrew.mxcl.ollama"],
                capture_output=True,
                text=True,
                timeout=deadline,
                env=subprocess_env(strip_qt=True),
            )
            if result.returncode == 0:
                return 1
        except Exception:
            continue
    return 0


def cleanup_ollama_runtime_processes(*, timeout_sec: float = 0.4) -> int:
    """Terminate Ollama server/app processes after unloading models."""
    if is_windows():
        return 0
    service_stopped = _stop_managed_ollama_service(timeout_sec=timeout_sec)
    targets = [
        pid
        for pid, _ppid, command in _process_table()
        if _is_ollama_runtime_command(command)
    ]
    stopped = _terminate_pids(targets, timeout_sec=timeout_sec)
    return stopped or service_stopped


def cleanup_app_runtime_processes(*, logger=None, timeout_sec: float = 0.4) -> dict[str, int]:
    """Release app-owned heavy runtimes at shutdown."""
    result = {
        "ollama_models": 0,
        "ollama_processes": 0,
        "child_processes": 0,
        "legacy_preview_ffmpeg": 0,
    }
    used_shutdown_helper = False
    def _cleanup_ollama_runtime() -> tuple[bool, int, int]:
        try:
            from core.llm.ollama_provider import shutdown_local_ollama_runtime

            shutdown_result = shutdown_local_ollama_runtime(
                None,
                logger=logger,
                log_context="앱 종료",
                timeout_sec=timeout_sec,
            )
            return (
                True,
                len(shutdown_result.get("models", []) or []),
                int(shutdown_result.get("processes", 0) or 0),
            )
        except Exception:
            try:
                from core.llm.ollama_provider import stop_local_llm_models

                stopped_models = stop_local_llm_models(None, logger=logger, log_context="앱 종료")
                return False, len(stopped_models), 0
            except Exception:
                return False, 0, 0

    try:
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="runtime-cleanup") as pool:
            ollama_future = pool.submit(_cleanup_ollama_runtime)
            child_future = pool.submit(cleanup_app_child_processes, timeout_sec=timeout_sec)
            preview_future = pool.submit(cleanup_stale_preview_proxy_processes, timeout_sec=timeout_sec)

            try:
                used_shutdown_helper, result["ollama_models"], result["ollama_processes"] = ollama_future.result()
            except Exception:
                used_shutdown_helper, result["ollama_models"], result["ollama_processes"] = _cleanup_ollama_runtime()
            try:
                result["child_processes"] = int(child_future.result() or 0)
            except Exception:
                result["child_processes"] = int(cleanup_app_child_processes(timeout_sec=timeout_sec) or 0)
            try:
                result["legacy_preview_ffmpeg"] = int(preview_future.result() or 0)
            except Exception:
                result["legacy_preview_ffmpeg"] = int(cleanup_stale_preview_proxy_processes(timeout_sec=timeout_sec) or 0)
    except Exception:
        used_shutdown_helper, result["ollama_models"], result["ollama_processes"] = _cleanup_ollama_runtime()
        result["child_processes"] = int(cleanup_app_child_processes(timeout_sec=timeout_sec) or 0)
        result["legacy_preview_ffmpeg"] = int(cleanup_stale_preview_proxy_processes(timeout_sec=timeout_sec) or 0)
    if not used_shutdown_helper:
        result["ollama_processes"] = cleanup_ollama_runtime_processes(timeout_sec=timeout_sec)
    cleaned_processes = int(result["child_processes"]) + int(result["legacy_preview_ffmpeg"])
    if cleaned_processes and logger:
        try:
            logger.log(f"🧹 앱 종료: 무거운 런타임 프로세스 {cleaned_processes}개 정리 완료")
        except Exception:
            pass
    if result["ollama_processes"] and logger and not used_shutdown_helper:
        try:
            logger.log(f"🛑 앱 종료: Ollama 서버/러너 {result['ollama_processes']}개 종료 완료")
        except Exception:
            pass
    return result
