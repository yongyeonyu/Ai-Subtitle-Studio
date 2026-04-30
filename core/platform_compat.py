# Version: 03.01.19
# Phase: PHASE2
"""
core/platform_compat.py
Cross-platform subprocess/path helpers for macOS and Windows.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import config

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


def demucs_binary() -> str:
    return resolve_executable("demucs", "DEMUCS_BINARY")


def subprocess_env(extra: dict | None = None, *, strip_qt: bool = False) -> dict:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
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
