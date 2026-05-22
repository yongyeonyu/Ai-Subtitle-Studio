from __future__ import annotations

import importlib.util
from typing import Any


def _setting_bool(settings: dict[str, Any] | None, key: str, default: bool) -> bool:
    value = settings.get(key, default) if isinstance(settings, dict) else default
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "on", "yes"}
    return bool(value)


def _setting_int(settings: dict[str, Any] | None, key: str, default: int) -> int:
    value = settings.get(key, default) if isinstance(settings, dict) else default
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def lora_gpu_acceleration_enabled(settings: dict[str, Any] | None = None) -> bool:
    if not _setting_bool(settings, "runtime_hardware_acceleration_enabled", True):
        return False
    return _setting_bool(settings, "lora_gpu_acceleration_enabled", True)


def _torch_module(settings: dict[str, Any] | None = None) -> Any | None:
    if not lora_gpu_acceleration_enabled(settings):
        return None
    try:
        import torch

        return torch
    except Exception:
        return None


def preferred_lora_torch_device(settings: dict[str, Any] | None = None) -> str:
    torch_mod = _torch_module(settings)
    if torch_mod is None:
        return "cpu"
    prefer_mps = _setting_bool(settings, "lora_gpu_prefer_mps", True)
    try:
        if prefer_mps and getattr(getattr(torch_mod, "backends", None), "mps", None):
            if torch_mod.backends.mps.is_available():
                return "mps"
    except Exception:
        pass
    try:
        if hasattr(torch_mod, "cuda") and torch_mod.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def lora_training_acceleration_plan(
    settings: dict[str, Any] | None = None,
    *,
    backend: str = "",
) -> dict[str, Any]:
    backend_name = str(backend or "")
    torch_device = preferred_lora_torch_device(settings)
    mlx_available = _module_exists("mlx") or _module_exists("mlx_lm")
    mlx_training = backend_name.startswith("mlx")
    torch_training = (
        backend_name.startswith("torch")
        or "transformers" in backend_name
        or "peft" in backend_name
        or "whisper" in backend_name
    )
    gpu_training_enabled = bool(mlx_training or (torch_training and torch_device != "cpu"))
    return {
        "enabled": gpu_training_enabled,
        "training_backend": "mlx_metal_gpu" if mlx_training else ("torch_gpu" if torch_training and torch_device != "cpu" else "cpu"),
        "torch_device": torch_device,
        "metal_available": bool(mlx_available or torch_device == "mps"),
        "uses_gpu_for_raw_file_io": False,
        "io_note": "JSON/JSONL/ZIP file I/O stays on CPU/OS; vector training and retrieval math use GPU when available.",
    }


def score_lora_vector_scores_on_gpu(
    inverted_index: dict[str, Any],
    query_vector: dict[str, float],
    *,
    doc_count: int,
    settings: dict[str, Any] | None = None,
) -> dict[int, float] | None:
    if not _setting_bool(settings, "lora_gpu_retrieval_scoring_enabled", True):
        return None
    if not query_vector or doc_count <= 0:
        return {}
    torch_mod = _torch_module(settings)
    if torch_mod is None:
        return None
    device = preferred_lora_torch_device(settings)
    if device == "cpu":
        return None

    indices: list[int] = []
    values: list[float] = []
    for bucket, query_weight in dict(query_vector).items():
        try:
            q_weight = float(query_weight)
        except Exception:
            continue
        if q_weight == 0.0:
            continue
        for doc_index_raw, doc_weight_raw in list(inverted_index.get(str(bucket), []) or []):
            try:
                doc_index = int(doc_index_raw)
                doc_weight = float(doc_weight_raw)
            except Exception:
                continue
            if doc_index < 0 or doc_index >= doc_count or doc_weight == 0.0:
                continue
            indices.append(doc_index)
            values.append(q_weight * doc_weight)

    if not indices:
        return {}
    min_postings = _setting_int(settings, "lora_gpu_retrieval_min_postings", 256)
    if len(indices) < max(0, min_postings) and not _setting_bool(settings, "lora_gpu_force_small_batches", False):
        return None

    try:
        index_tensor = torch_mod.tensor(indices, dtype=torch_mod.long, device=device)
        value_tensor = torch_mod.tensor(values, dtype=torch_mod.float32, device=device)
        scores = torch_mod.zeros(int(doc_count), dtype=torch_mod.float32, device=device)
        scores.index_add_(0, index_tensor, value_tensor)
        nonzero = torch_mod.nonzero(scores, as_tuple=False).flatten()
        if int(nonzero.numel()) <= 0:
            return {}
        selected_scores = scores.index_select(0, nonzero).detach().cpu().tolist()
        selected_indices = nonzero.detach().cpu().tolist()
        return {int(doc_index): float(score) for doc_index, score in zip(selected_indices, selected_scores)}
    except Exception:
        return None


__all__ = [
    "lora_gpu_acceleration_enabled",
    "lora_training_acceleration_plan",
    "preferred_lora_torch_device",
    "score_lora_vector_scores_on_gpu",
]
