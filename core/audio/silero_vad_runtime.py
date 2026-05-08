from __future__ import annotations

"""Lightweight Silero VAD loader.

The pip package ships local model helpers and avoids the heavier torch.hub
path. Fall back to torch.hub only when the package helper is unavailable.
"""

from typing import Any


def load_silero_vad_runtime(*, onnx: bool = False) -> tuple[Any, tuple[Any, Any, Any, Any, Any], str]:
    try:
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio

        model = load_silero_vad(onnx=bool(onnx))
        utils = (get_speech_timestamps, None, read_audio, None, None)
        return model, utils, "silero_vad_package"
    except Exception:
        import torch

        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=bool(onnx),
        )
        return model, utils, "torch_hub"


__all__ = ["load_silero_vad_runtime"]
