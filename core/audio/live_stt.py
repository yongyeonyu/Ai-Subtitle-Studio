# Version: 03.01.19
# Phase: PHASE2
"""
core/audio/live_stt.py
마이크 직접 입력용 고성능 STT 유틸.

우선순위:
1. macOS Apple Silicon: MLX Whisper persistent worker
2. Windows/Linux: faster-whisper subprocess
3. 실패 시 기존 SpeechRecognition Google fallback
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass

import config
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.settings import load_settings
from logger import get_logger


_LIVE_MLX_PROC = None
_LIVE_MLX_LOCK = threading.Lock()


@dataclass
class LiveSTTResult:
    text: str
    engine: str
    model: str
    elapsed: float


def transcribe_microphone_once(profile: str = "quality") -> LiveSTTResult:
    """마이크에서 한 문장/구간을 녹음하고 로컬 Whisper 우선으로 텍스트를 반환합니다."""
    start_ts = time.time()
    settings = load_settings()

    import speech_recognition as sr

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.energy_threshold = int(settings.get("live_stt_energy_threshold", 260))
    recognizer.pause_threshold = float(settings.get("live_stt_pause_threshold", 0.65))
    recognizer.non_speaking_duration = float(settings.get("live_stt_non_speaking_duration", 0.25))

    timeout = float(settings.get("live_stt_timeout", 10.0))
    phrase_time_limit = float(settings.get("live_stt_phrase_time_limit", 30.0))

    get_logger().log("🎙️ 마이크 음성 입력 대기 중...")
    with sr.Microphone(sample_rate=16000) as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.35)
        audio = recognizer.listen(
            source,
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
        )

    with tempfile.TemporaryDirectory(prefix="ai_subtitle_live_stt_") as td:
        raw_wav = os.path.join(td, "mic_raw.wav")
        clean_wav = os.path.join(td, "mic_clean.wav")
        with open(raw_wav, "wb") as f:
            f.write(audio.get_wav_data(convert_rate=16000, convert_width=2))

        wav_path = _prepare_live_wav(raw_wav, clean_wav)
        model = _select_live_model(settings, profile)

        try:
            text = _transcribe_local_whisper(wav_path, model)
            text = _postprocess_live_text(text)
            if text:
                return LiveSTTResult(
                    text=text,
                    engine="local-whisper",
                    model=model,
                    elapsed=time.time() - start_ts,
                )
        except Exception as e:
            get_logger().log(f"⚠️ 로컬 마이크 STT 실패, fallback 시도: {e}")

        fallback_text = recognizer.recognize_google(audio, language="ko-KR")
        fallback_text = _postprocess_live_text(fallback_text)
        return LiveSTTResult(
            text=fallback_text,
            engine="google-fallback",
            model="speech_recognition/google",
            elapsed=time.time() - start_ts,
        )


def _prepare_live_wav(raw_wav: str, clean_wav: str) -> str:
    """마이크 입력에 적합한 가벼운 필터를 적용합니다. 실패하면 원본 wav를 사용합니다."""
    filters = ",".join(
        [
            "highpass=f=80",
            "lowpass=f=7600",
            "afftdn=nf=-28",
            "dynaudnorm=f=150:g=9:p=0.95",
            "loudnorm=I=-16:LRA=11:tp=-1.5",
        ]
    )
    try:
        proc = subprocess.run(
            [
                ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
                "-i", raw_wav,
                "-ac", "1",
                "-ar", "16000",
                "-af", filters,
                "-acodec", "pcm_s16le",
                clean_wav,
            ],
            capture_output=True,
            timeout=15,
            **hidden_subprocess_kwargs(),
        )
        if proc.returncode == 0 and os.path.exists(clean_wav) and os.path.getsize(clean_wav) > 0:
            return clean_wav
    except Exception as e:
        get_logger().log(f"⚠️ 마이크 오디오 필터 fallback: {e}")
    return raw_wav


def _select_live_model(settings: dict, profile: str) -> str:
    selected = settings.get("selected_whisper_model") or getattr(
        config, "WHISPER_MODEL", "mlx-community/whisper-large-v3-mlx"
    )
    profile = (profile or "quality").lower()

    if config.IS_MAC:
        if profile == "fast":
            return "mlx-community/whisper-large-v3-turbo"
        if "large" in selected:
            return selected
        return "mlx-community/whisper-large-v3-mlx"

    if profile == "fast":
        return "large-v3-turbo"
    if "large" in str(selected).lower():
        return selected
    return "large-v3"


def _transcribe_local_whisper(wav_path: str, model: str) -> str:
    from core.audio.whisper_transformers import is_transformers_whisper_model

    if is_transformers_whisper_model(model):
        return _transcribe_transformers(wav_path, model)
    if config.IS_MAC:
        return _transcribe_mlx(wav_path, model)
    return _transcribe_faster(wav_path, model)


def _transcribe_transformers(wav_path: str, model: str) -> str:
    from core.audio.whisper_transformers import run_whisper

    proc = run_whisper(
        chunk_paths=[wav_path],
        model=model,
        language=getattr(config, "LANGUAGE", "ko"),
        temperature_tuple="(0.0,)",
    )
    if proc is None:
        raise RuntimeError("transformers-whisper process not available")

    line = proc.stdout.readline()
    proc.wait(timeout=120)
    data = _parse_json_line(line)
    if not data:
        raise RuntimeError("empty transformers-whisper result")
    if data.get("fatal_error"):
        raise RuntimeError(data.get("fatal_error"))
    if data.get("error"):
        raise RuntimeError(data.get("error"))
    return _extract_text(data)


def _transcribe_mlx(wav_path: str, model: str) -> str:
    global _LIVE_MLX_PROC
    from core.audio.whisper_mlx import ensure_worker, submit_task

    with _LIVE_MLX_LOCK:
        _LIVE_MLX_PROC = ensure_worker(_LIVE_MLX_PROC)
        task_id = submit_task(
            proc=_LIVE_MLX_PROC,
            chunk_paths=[wav_path],
            model=model,
            language=getattr(config, "LANGUAGE", "ko"),
            temperature_values=[0.0],
        )

        while True:
            line = _LIVE_MLX_PROC.stdout.readline()
            if not line:
                raise RuntimeError("MLX Whisper worker output closed")
            data = _parse_json_line(line)
            if not data or data.get("task_id") != task_id:
                continue
            if data.get("done"):
                break
            if data.get("fatal_error") or data.get("error"):
                raise RuntimeError(data.get("fatal_error") or data.get("error"))
            return _extract_text(data.get("result") or {})

    return ""


def _transcribe_faster(wav_path: str, model: str) -> str:
    from core.audio.whisper_faster import run_whisper

    proc = run_whisper(
        chunk_paths=[wav_path],
        model=model,
        language=getattr(config, "LANGUAGE", "ko"),
        temperature_tuple="(0.0,)",
    )
    if proc is None:
        raise RuntimeError("faster-whisper process not available")

    line = proc.stdout.readline()
    proc.wait(timeout=60)
    data = _parse_json_line(line)
    if not data:
        raise RuntimeError("empty faster-whisper result")
    if data.get("fatal_error"):
        raise RuntimeError(data.get("fatal_error"))
    if data.get("error"):
        raise RuntimeError(data.get("error"))
    return _extract_text(data)


def _parse_json_line(line: str) -> dict | None:
    try:
        line = (line or "").strip()
        if not line or not line.startswith("{"):
            return None
        return json.loads(line)
    except Exception:
        return None


def _extract_text(result: dict) -> str:
    if not isinstance(result, dict):
        return ""
    if result.get("text"):
        return str(result.get("text") or "")
    parts = []
    for seg in result.get("segments", []) or []:
        txt = str(seg.get("text") or "").strip()
        if txt:
            parts.append(txt)
    return " ".join(parts)


def _postprocess_live_text(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""

    # Whisper가 짧은 마이크 입력에서 같은 어절을 반복하는 경우를 가볍게 정리합니다.
    words = text.split()
    deduped = []
    for word in words:
        if len(deduped) >= 2 and deduped[-1] == word and deduped[-2] == word:
            continue
        deduped.append(word)
    text = " ".join(deduped).strip()

    hallucination_fragments = (
        "시청해 주셔서 감사합니다",
        "시청해주셔서 감사합니다",
        "구독 좋아요",
    )
    if any(fragment == text for fragment in hallucination_fragments):
        return ""

    return text
