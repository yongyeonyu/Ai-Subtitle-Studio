from __future__ import annotations

"""Optional C++ helpers for native subtitle resource plan summaries."""

import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import threading
from typing import Any

_FALSE_VALUES = {"0", "false", "off", "no"}
_BUILD_LOCK = threading.Lock()


def _env_enabled(name: str, default: str = "1") -> bool:
    value = str(os.environ.get(name, default) or default).strip().lower()
    return value not in _FALSE_VALUES


def _extension_suffix() -> str:
    return str(sysconfig.get_config_var("EXT_SUFFIX") or ".so")


def _source_path() -> Path:
    return Path(__file__).resolve().with_name("native") / "_native_subtitle_resource.cpp"


def _extension_path() -> Path:
    return Path(__file__).resolve().with_name(f"_native_subtitle_resource{_extension_suffix()}")


def _compiler_path() -> str | None:
    configured = str(os.environ.get("CXX", "") or "").strip()
    if configured:
        return configured
    for name in ("clang++", "c++", "g++"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _compile_native_extension() -> bool:
    if not _env_enabled("AI_SUBTITLE_NATIVE_RESOURCE_SUMMARY", "1"):
        return False
    if not _env_enabled("AI_SUBTITLE_NATIVE_RESOURCE_SUMMARY_BUILD", "1"):
        return False

    source = _source_path()
    output = _extension_path()
    if not source.exists():
        return output.exists()
    if output.exists() and output.stat().st_mtime >= source.stat().st_mtime:
        return True

    compiler = _compiler_path()
    include_dir = sysconfig.get_paths().get("include")
    if not compiler or not include_dir:
        return output.exists()

    with _BUILD_LOCK:
        if output.exists() and output.stat().st_mtime >= source.stat().st_mtime:
            return True

        tmp_output = output.with_name(f"{output.name}.tmp")
        cmd = [
            compiler,
            "-O3",
            "-std=c++17",
            "-shared",
            "-fPIC",
            "-I",
            str(include_dir),
            str(source),
            "-o",
            str(tmp_output),
        ]
        if sys.platform == "darwin":
            cmd.extend(["-undefined", "dynamic_lookup"])
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            os.replace(tmp_output, output)
            return True
        except Exception:
            try:
                tmp_output.unlink()
            except OSError:
                pass
            return output.exists()


def _load_native_module():
    if not _env_enabled("AI_SUBTITLE_NATIVE_RESOURCE_SUMMARY", "1"):
        return None
    _compile_native_extension()
    try:
        return importlib.import_module("core._native_subtitle_resource")
    except Exception:
        return None


_native = _load_native_module()

HAS_NATIVE_SUBTITLE_RESOURCE = _native is not None


def native_subtitle_resource_enabled() -> bool:
    if _native is None:
        return False
    return _env_enabled("AI_SUBTITLE_NATIVE_RESOURCE_SUMMARY", "1")


def _routing_rows(rows: list[dict[str, Any]]) -> tuple[list[str], list[str], list[int], list[int]]:
    tasks: list[str] = []
    policies: list[str] = []
    gpu_lanes: list[int] = []
    ane_lanes: list[int] = []
    for row in list(rows or []):
        task = str(row.get("task") or "").strip()
        if not task:
            continue
        accelerator = dict(row.get("accelerator") or {})
        tasks.append(task)
        policies.append(str(accelerator.get("policy") or row.get("policy") or "").strip())
        gpu_lanes.append(max(0, int(float(accelerator.get("gpu_lanes", row.get("gpu_lanes", 0)) or 0))))
        ane_lanes.append(max(0, int(float(accelerator.get("ane_lanes", row.get("ane_lanes", 0)) or 0))))
    return tasks, policies, gpu_lanes, ane_lanes


def resource_lane_summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not native_subtitle_resource_enabled():
        return None
    try:
        tasks, policies, gpu_lanes, ane_lanes = _routing_rows(rows)
        result = _native.resource_lane_summary(tasks, policies, gpu_lanes, ane_lanes)
        if not isinstance(result, dict):
            return None
        result["native_backend"] = "cpp"
        return result
    except Exception:
        return None


__all__ = [
    "HAS_NATIVE_SUBTITLE_RESOURCE",
    "native_subtitle_resource_enabled",
    "resource_lane_summary",
]
