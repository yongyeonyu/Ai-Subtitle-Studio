# Version: 03.24.01
# Phase: PHASE2
"""Shared audio/STT model memory cleanup helpers."""
from __future__ import annotations

import gc

from core.audio.torch_acceleration import trim_torch_memory_caches


def clear_audio_model_memory_caches(*, include_gpu: bool = True) -> None:
    """Release Python and accelerator caches after audio/STT/VAD model work."""
    try:
        gc.collect()
    except Exception:
        pass
    if not include_gpu:
        return
    try:
        trim_torch_memory_caches(include_sync=True)
    except Exception:
        pass
    try:
        import mlx.core as mx

        synchronize = getattr(mx, "synchronize", None)
        if callable(synchronize):
            synchronize()
        clear_cache = getattr(mx, "clear_cache", None)
        if callable(clear_cache):
            clear_cache()
    except Exception:
        pass


__all__ = ["clear_audio_model_memory_caches"]
