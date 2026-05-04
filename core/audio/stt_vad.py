# Version: 03.01.19
# Phase: PHASE2
"""
VAD-only detector for manual STT mode.

This creates speech-region segments only. It does not run Whisper or LLM.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.runtime.logger import get_logger


def detect_stt_speech_segments(media_path: str) -> list[dict]:
    """Return highly sensitive speech regions for STT follow-along mode."""
    if not media_path or not os.path.exists(media_path):
        raise FileNotFoundError(media_path or "")

    with tempfile.TemporaryDirectory(prefix="ai_subtitle_stt_vad_") as td:
        wav_path = os.path.join(td, "stt_vad.wav")
        _extract_stt_vad_wav(media_path, wav_path)
        return _detect_silero_high_sensitivity(wav_path)


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


def _detect_silero_high_sensitivity(wav_path: str) -> list[dict]:
    import torch

    get_logger().log("🎙️ STT 모드: 최고 민감도 VAD 음성 구간 탐지 시작")
    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False,
    )
    get_speech_timestamps, _, read_audio, _, _ = utils
    audio_data = read_audio(wav_path, sampling_rate=16000)
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
    segs = [
        {
            "start": round(max(0.0, item["start"] / 16000.0), 2),
            "end": round(max(0.0, item["end"] / 16000.0), 2),
            "text": "",
            "stt_mode": True,
            "stt_pending": True,
            "original_text": "",
            "dictated_text": "",
        }
        for item in raw
        if item.get("end", 0) > item.get("start", 0)
    ]
    get_logger().log(f"🎙️ STT 모드: VAD 음성 구간 {len(segs)}개 생성")
    return segs
