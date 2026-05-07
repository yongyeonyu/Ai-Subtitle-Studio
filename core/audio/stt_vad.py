# Version: 03.01.19
# Phase: PHASE2
"""
VAD-only detector for manual STT mode.

This creates speech-region segments only. It does not run Whisper or LLM.
"""
from __future__ import annotations

import os
import json
import hashlib
import subprocess
import tempfile
import time

from core.media_fingerprint import media_file_fingerprint, media_fingerprint_digest
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.runtime import config
from core.runtime.logger import get_logger
from core.audio.runtime_cleanup import clear_audio_model_memory_caches
from core.audio.torch_acceleration import move_torch_model_to_preferred_device, move_torch_tensor_to_device


_STT_VAD_CACHE_VERSION = 3


def _stt_vad_cache_identity(media_path: str) -> dict:
    try:
        source = os.path.abspath(str(media_path or ""))
        stat = os.stat(source)
        source_size = int(stat.st_size)
        source_mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
        source_fingerprint = media_file_fingerprint(source, sample_bytes=512 * 1024, include_samples=True)
        source_digest = media_fingerprint_digest(source, sample_bytes=512 * 1024, include_samples=True)
    except Exception:
        source = os.path.abspath(str(media_path or ""))
        source_size = 0
        source_mtime_ns = 0
        source_fingerprint = source
        source_digest = hashlib.sha1(source.encode("utf-8", errors="ignore")).hexdigest()
    return {
        "version": _STT_VAD_CACHE_VERSION,
        "source": source,
        "source_size": source_size,
        "source_mtime_ns": source_mtime_ns,
        "source_fingerprint": source_fingerprint,
        "source_fingerprint_digest": source_digest,
        "detector": "silero_ten_vad_ensemble",
        "threshold": 0.22,
        "min_speech_duration_ms": 80,
        "min_silence_duration_ms": 180,
        "speech_pad_ms": 90,
        "sample_rate": 16000,
        "providers": ["silero", "ten_vad"],
        "ensemble": True,
    }


def _stt_vad_cache_path(identity: dict) -> str:
    cache_root = os.path.join(config.OUTPUT_DIR, "_analysis_cache", "stt_vad")
    os.makedirs(cache_root, exist_ok=True)
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    key = hashlib.sha256(raw).hexdigest()[:32]
    return os.path.join(cache_root, f"stt_vad_{key}.json")


def _load_stt_vad_cache(media_path: str) -> list[dict] | None:
    identity = _stt_vad_cache_identity(media_path)
    cache_path = _stt_vad_cache_path(identity)
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if dict(payload.get("identity") or {}) != identity:
            return None
        return [dict(row) for row in list(payload.get("segments") or []) if isinstance(row, dict)]
    except Exception:
        return None


def _write_stt_vad_cache(media_path: str, segments: list[dict]) -> None:
    try:
        identity = _stt_vad_cache_identity(media_path)
        cache_path = _stt_vad_cache_path(identity)
        payload = {
            "schema": "ai_subtitle_studio.stt_vad_cache.v1",
            "created_at": time.time(),
            "identity": identity,
            "segments": [dict(row) for row in list(segments or []) if isinstance(row, dict)],
        }
        tmp_path = f"{cache_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, cache_path)
    except Exception:
        pass


def detect_stt_speech_segments(media_path: str) -> list[dict]:
    """Return highly sensitive speech regions for STT follow-along mode."""
    if not media_path or not os.path.exists(media_path):
        raise FileNotFoundError(media_path or "")

    cached = _load_stt_vad_cache(media_path)
    if cached is not None:
        get_logger().log(f"🎙️ STT 모드: VAD 캐시 재사용 ({len(cached)}개)")
        return cached

    try:
        from core.media_info import probe_media
        from core.frame_time import normalize_fps
        from core.stt_mode.vad_ensemble import detect_stt_work_segments

        info = probe_media(media_path)
        fps = normalize_fps(info.get("fps", 30.0) or 30.0)
        segments = detect_stt_work_segments(media_path, fps=fps)
        if segments:
            _write_stt_vad_cache(media_path, segments)
            get_logger().log(f"🎙️ STT 모드: VAD 앙상블 음성 구간 {len(segments)}개 생성")
            return segments
    except Exception as exc:
        get_logger().log(f"⚠️ STT 모드: VAD 앙상블 실패, Silero 단독으로 계속합니다: {exc}")

    with tempfile.TemporaryDirectory(prefix="ai_subtitle_stt_vad_") as td:
        wav_path = os.path.join(td, "stt_vad.wav")
        _extract_stt_vad_wav(media_path, wav_path)
        segments = _detect_silero_high_sensitivity(wav_path)
        _write_stt_vad_cache(media_path, segments)
        return segments


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
        device_name = move_torch_model_to_preferred_device(model, log_label="STT 모드 VAD")
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
    finally:
        try:
            if model is not None and hasattr(model, "to"):
                model.to("cpu")
        except Exception:
            pass
        del audio_data
        del model
        clear_audio_model_memory_caches(include_gpu=True)
