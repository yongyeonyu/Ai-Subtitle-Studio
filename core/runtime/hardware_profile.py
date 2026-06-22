# Version: 04.00.01
"""Lightweight macOS/Apple Silicon hardware discovery.

Keep this module free of heavy ML imports. It is used early during startup to
decide native thread budgets and accelerator routing.
"""
from __future__ import annotations

import importlib.util
import os
import platform
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.coerce import positive_int as _positive_int
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def darwin_sysctl_int(name: str) -> int:
    if platform.system() != "Darwin":
        return 0
    try:
        proc = subprocess.run(
            ["sysctl", "-n", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1.0,
        )
        return _positive_int((proc.stdout or "").strip(), 0)
    except Exception:
        return 0


def darwin_sysctl_str(name: str) -> str:
    if platform.system() != "Darwin":
        return ""
    try:
        proc = subprocess.run(
            ["sysctl", "-n", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1.0,
        )
        return str(proc.stdout or "").strip()
    except Exception:
        return ""


def _apple_chip_parts(brand: str) -> tuple[str, int, str]:
    text = str(brand or "").strip()
    match = re.search(r"\bApple\s+(M(?P<generation>\d+)(?:\s+(?P<tier>Ultra|Max|Pro))?)\b", text, re.IGNORECASE)
    if not match:
        return text, 0, "base"
    chip_name = "Apple " + re.sub(r"\s+", " ", match.group(1).strip())
    generation = _positive_int(match.group("generation"), 0)
    tier = str(match.group("tier") or "base").strip().lower()
    return chip_name, generation, tier or "base"


@lru_cache(maxsize=1)
def _apple_gpu_core_count() -> int:
    if platform.system() != "Darwin":
        return 0
    try:
        proc = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2.5,
        )
    except Exception:
        return 0
    text = str(proc.stdout or "")
    for pattern in (
        r"Total Number of Cores:\s*(\d+)",
        r"GPU Cores:\s*(\d+)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _positive_int(match.group(1), 0)
    return 0


def _apple_neural_engine_core_estimate(chip_generation: int) -> int:
    # Apple does not expose ANE cores through a stable public sysctl. For M-series
    # scheduling we only need a slot estimate, and all current M-series chips
    # expose a Core ML / Neural Engine path with a 16-core class ANE.
    return 16 if chip_generation > 0 else 0


@lru_cache(maxsize=1)
def hardware_profile() -> dict[str, Any]:
    logical = max(1, os.cpu_count() or 1)
    physical = darwin_sysctl_int("hw.physicalcpu") or logical
    performance_cores = darwin_sysctl_int("hw.perflevel0.physicalcpu")
    efficiency_cores = darwin_sysctl_int("hw.perflevel1.physicalcpu")
    memory_bytes = darwin_sysctl_int("hw.memsize")
    brand_string = darwin_sysctl_str("machdep.cpu.brand_string") or platform.processor()
    chip_name, chip_generation, chip_tier = _apple_chip_parts(brand_string)

    if performance_cores <= 0:
        # Some macOS hosts may not expose perflevel sysctl values. Use physical
        # cores as a stability-first cap for CPU-bound worker defaults.
        performance_cores = physical

    is_darwin_arm = platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}
    accelerators = {
        "xcodebuild": bool(shutil.which("xcodebuild")),
        "swift": bool(shutil.which("swift")),
        "mlx": importlib.util.find_spec("mlx") is not None,
        "mlx_whisper": importlib.util.find_spec("mlx_whisper") is not None,
        "torch": importlib.util.find_spec("torch") is not None,
        "coreml_cli": bool(shutil.which("argmax-cli") or shutil.which("whisperkit-cli")),
        "cuda_cli": bool(shutil.which("nvidia-smi")),
        "directml": importlib.util.find_spec("torch_directml") is not None,
        "openvino": importlib.util.find_spec("openvino") is not None,
    }
    accelerators["whisperkit_persistent_worker"] = bool(shutil.which("WhisperKitPersistentWorker"))
    if accelerators["cuda_cli"]:
        accelerators["cuda"] = True
    gpu_cores = _apple_gpu_core_count() if is_darwin_arm else 0
    neural_engine_cores = _apple_neural_engine_core_estimate(chip_generation) if is_darwin_arm else 0
    if is_darwin_arm:
        # Metal is hardware-provided on Apple Silicon. MLX availability is
        # tracked separately because STT model routing still needs mlx-whisper.
        accelerators["metal"] = True
        accelerators["metal_gpu"] = True
        accelerators["metal_gpu_cores"] = gpu_cores
        # Apple Neural Engine access is generally routed through Core ML /
        # WhisperKit rather than direct Python APIs.
        accelerators["neural_engine_path"] = bool(
            accelerators["coreml_cli"] or accelerators["whisperkit_persistent_worker"] or neural_engine_cores
        )

    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "brand_string": brand_string,
        "chip_name": chip_name,
        "chip_generation": chip_generation,
        "chip_tier": chip_tier,
        "logical_cores": logical,
        "physical_cores": max(1, physical),
        "performance_cores": max(1, performance_cores),
        "efficiency_cores": max(0, efficiency_cores),
        "gpu_cores": max(0, gpu_cores),
        "neural_engine_cores": max(0, neural_engine_cores),
        "memory_bytes": max(0, memory_bytes),
        "accelerators": accelerators,
    }
