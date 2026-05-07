# Version: 03.24.01
# Phase: PHASE2
"""Shared audio/STT model memory cleanup helpers."""
from __future__ import annotations

import gc


def clear_audio_model_memory_caches(*, include_gpu: bool = True) -> None:
    """Release Python and accelerator caches after audio/STT/VAD model work."""
    try:
        gc.collect()
    except Exception:
        pass
    if not include_gpu:
        return
    try:
        import torch

        if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
        if hasattr(torch, "cuda") and torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    try:
        import mlx.core as mx

        clear_cache = getattr(mx, "clear_cache", None)
        if callable(clear_cache):
            clear_cache()
    except Exception:
        pass


__all__ = ["clear_audio_model_memory_caches"]
