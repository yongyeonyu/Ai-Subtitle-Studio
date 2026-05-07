# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""VAD provider adapters for STT Mode."""
from __future__ import annotations

import os
import subprocess
import tempfile
import wave
from typing import Any

from core.frame_time import normalize_fps
from core.audio.torch_acceleration import move_torch_model_to_preferred_device, move_torch_tensor_to_device
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.runtime.logger import get_logger
from core.audio.runtime_cleanup import clear_audio_model_memory_caches
from core.stt_mode.vad_ensemble import normalize_vad_candidate


def _extract_stt_vad_wav(media_path: str, wav_path: str) -> None:
    filters = ",".join(
        [
            "highpass=f=70",
            "lowpass=f=7800",
            "afftdn=nf=-32",
            "dynaudnorm=f=120:g=8:p=0.95",
            "loudnorm=I=-16:LRA=11:tp=-1.5",
        ]
    )
    cmd = [
        ffmpeg_binary(),
        "-y",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        media_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-af",
        filters,
        "-acodec",
        "pcm_s16le",
        wav_path,
    ]
    subprocess.run(cmd, check=True, timeout=180, **hidden_subprocess_kwargs())
    if not os.path.exists(wav_path) or os.path.getsize(wav_path) <= 1024:
        raise RuntimeError("STT VAD wav extraction failed")


def _detect_silero_wav(wav_path: str, settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    import torch

    model = None
    audio_data = None
    device_name = "cpu"
    try:
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
        )
        device_name = move_torch_model_to_preferred_device(model, settings=settings, log_label="STT VAD")
        get_speech_timestamps, _, read_audio, _, _ = utils
        audio_data = read_audio(wav_path, sampling_rate=16000)
        audio_data = move_torch_tensor_to_device(audio_data, device_name)
        raw = get_speech_timestamps(
            audio_data,
            model,
            sampling_rate=16000,
            threshold=0.22,
            min_speech_duration_ms=80,
            min_silence_duration_ms=180,
            speech_pad_ms=90,
            window_size_samples=512,
        )
        return [
            {
                "provider": "silero",
                "start": max(0.0, float(item["start"]) / 16000.0),
                "end": max(0.0, float(item["end"]) / 16000.0),
                "score": 0.42,
                "raw": dict(item),
            }
            for item in raw
            if item.get("end", 0) > item.get("start", 0)
        ]
    finally:
        try:
            if model is not None and hasattr(model, "to"):
                model.to("cpu")
        except Exception:
            pass
        del audio_data
        del model
        clear_audio_model_memory_caches(include_gpu=True)


def _vad_flags_to_segments(
    flags: list[int],
    *,
    hop_sec: float,
    min_speech_sec: float,
    min_silence_sec: float,
    speech_pad_sec: float,
    provider: str,
) -> list[dict[str, Any]]:
    raw: list[tuple[float, float]] = []
    start_idx = None
    for idx, flag in enumerate(flags):
        if flag and start_idx is None:
            start_idx = idx
        elif not flag and start_idx is not None:
            raw.append((start_idx * hop_sec, idx * hop_sec))
            start_idx = None
    if start_idx is not None:
        raw.append((start_idx * hop_sec, len(flags) * hop_sec))

    merged: list[list[float]] = []
    for start, end in raw:
        if end - start < max(0.0, min_speech_sec):
            continue
        start = max(0.0, start - max(0.0, speech_pad_sec))
        end += max(0.0, speech_pad_sec)
        if merged and start - merged[-1][1] <= max(0.0, min_silence_sec):
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [
        {
            "provider": provider,
            "start": round(start, 4),
            "end": round(end, 4),
            "score": 0.4,
        }
        for start, end in merged
        if end > start
    ]


def _detect_ten_vad_wav(wav_path: str, settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    import numpy as np
    from ten_vad import TenVad

    settings = settings or {}
    hop_size = int(settings.get("ten_vad_hop_size", 256) or 256)
    threshold = float(settings.get("ten_vad_threshold", settings.get("vad_threshold", 0.5)) or 0.5)
    min_speech = float(settings.get("vad_min_speech", settings.get("stt_mode_min_work_segment_sec", 0.25)) or 0.25)
    min_silence = float(settings.get("vad_min_silence", settings.get("stt_mode_merge_gap_sec", 0.35)) or 0.35)
    speech_pad = float(settings.get("vad_speech_pad", 0.2) or 0.2)

    with wave.open(wav_path, "rb") as wav:
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if sample_rate != 16000 or channels != 1 or sample_width != 2:
        raise RuntimeError("TEN VAD requires 16kHz mono int16 WAV")

    audio = np.frombuffer(frames, dtype=np.int16)
    frame_count = len(audio) // hop_size
    if frame_count <= 0:
        return []
    detector = TenVad(hop_size, threshold)
    flags: list[int] = []
    for idx in range(frame_count):
        frame = np.ascontiguousarray(audio[idx * hop_size:(idx + 1) * hop_size])
        _probability, flag = detector.process(frame)
        flags.append(int(flag))
    return _vad_flags_to_segments(
        flags,
        hop_sec=hop_size / 16000.0,
        min_speech_sec=min_speech,
        min_silence_sec=min_silence,
        speech_pad_sec=speech_pad,
        provider="ten_vad",
    )


def detect_vad_candidates_from_wav(
    wav_path: str,
    *,
    provider: str,
    settings: dict[str, Any] | None = None,
    fps: float | int | str | None = None,
) -> list[dict[str, Any]]:
    provider_key = str(provider or "").strip().lower()
    timeline_fps = normalize_fps(fps or 30.0)
    if provider_key in {"silero", "silero_vad", "silero-vad"}:
        rows = _detect_silero_wav(wav_path, settings=settings)
        provider_key = "silero"
    elif provider_key in {"ten", "ten_vad", "ten-vad", "tenvad"}:
        rows = _detect_ten_vad_wav(wav_path, settings=settings)
        provider_key = "ten_vad"
    else:
        raise ValueError(f"unsupported_vad_provider:{provider}")
    return [
        normalize_vad_candidate(row, provider=provider_key, fps=timeline_fps)
        for row in rows
        if isinstance(row, dict)
    ]


def detect_vad_candidates(
    media_path: str,
    *,
    provider: str,
    settings: dict[str, Any] | None = None,
    fps: float | int | str | None = None,
) -> list[dict[str, Any]]:
    if not media_path or not os.path.exists(media_path):
        raise FileNotFoundError(media_path or "")
    with tempfile.TemporaryDirectory(prefix="ai_subtitle_stt_vad_") as td:
        wav_path = os.path.join(td, "stt_vad.wav")
        _extract_stt_vad_wav(media_path, wav_path)
        try:
            return detect_vad_candidates_from_wav(wav_path, provider=provider, settings=settings, fps=fps)
        except Exception as exc:
            get_logger().log(f"  [STT VAD] {provider} provider failed: {exc}")
            return []


__all__ = [
    "detect_vad_candidates",
    "detect_vad_candidates_from_wav",
]
