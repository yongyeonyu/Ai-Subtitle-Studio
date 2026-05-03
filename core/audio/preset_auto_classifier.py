# Version: 03.12.02
# Phase: PHASE2
from __future__ import annotations

import json
import math
import os
import tempfile
import urllib.request
import wave

import numpy as np

from core.audio.audio_presets import apply_audio_preset, curated_audio_preset_names
from core.audio.stt_quality_presets import apply_stt_quality_preset, normalize_stt_quality_key
from core.llm.gemini_provider import resolve_gemini_model
from core.llm.ollama_provider import _build_generate_request, ensure_ollama_server
from core.llm.openai_provider import is_openai_model, resolve_openai_model
from core.llm.secure_keys import get_api_key
from core.media_info import probe_media
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs


SUPPORTED_AUDIO_PRESETS = curated_audio_preset_names()
SUPPORTED_STT_PRESETS = ("fast", "balanced", "precise")


def auto_classify_media_presets(media_path: str, settings: dict | None = None) -> dict:
    settings = dict(settings or {})
    media_path = str(media_path or "").strip()
    if not media_path or not os.path.exists(media_path):
        raise FileNotFoundError("자동 판정을 위한 미디어 파일을 찾을 수 없습니다.")

    with tempfile.TemporaryDirectory(prefix="audio_preset_auto_") as tmpdir:
        sample = prepare_audio_sample(media_path, tmpdir=tmpdir)
        features = analyze_sample_features(
            sample["wav_path"],
            start_sec=sample["representative_start_sec"],
            duration_sec=sample["representative_duration_sec"],
        )
        features.update({
            "media_duration_sec": round(float(sample["media_duration_sec"]), 3),
            "window_start_sec": round(float(sample["window_start_sec"]), 3),
            "window_duration_sec": round(float(sample["window_duration_sec"]), 3),
            "representative_start_sec": round(float(sample["representative_start_sec"]), 3),
            "representative_duration_sec": round(float(sample["representative_duration_sec"]), 3),
        })

    decision = _llm_classify(features, settings)
    if not isinstance(decision, dict):
        decision = {}
    fallback = _heuristic_decision(features)
    audio_preset = str(decision.get("audio_preset") or fallback["audio_preset"]).strip()
    stt_quality = normalize_stt_quality_key(decision.get("stt_quality_preset") or fallback["stt_quality_preset"])
    if audio_preset not in SUPPORTED_AUDIO_PRESETS:
        audio_preset = fallback["audio_preset"]
    confidence = _safe_confidence(decision.get("confidence"), fallback["confidence"])
    reason = str(decision.get("reason") or fallback["reason"]).strip()
    result = {
        "audio_preset": audio_preset,
        "stt_quality_preset": stt_quality,
        "confidence": confidence,
        "reason": reason,
        "features": features,
        "llm_used": bool(decision),
    }
    return result


def apply_auto_classified_presets(settings: dict, decision: dict) -> dict:
    updated = dict(settings or {})
    updated = apply_stt_quality_preset(updated, decision.get("stt_quality_preset") or "balanced")
    updated = apply_audio_preset(updated, decision.get("audio_preset") or "")
    updated["audio_preset_auto_decision"] = {
        "audio_preset": updated.get("audio_preset", ""),
        "stt_quality_preset": updated.get("stt_quality_preset", "balanced"),
        "confidence": float(decision.get("confidence", 0.0) or 0.0),
        "reason": str(decision.get("reason") or ""),
        "llm_used": bool(decision.get("llm_used", False)),
    }
    return updated


def prepare_audio_sample(media_path: str, *, tmpdir: str | None = None) -> dict:
    info = probe_media(media_path)
    duration = float(info.get("duration", 0.0) or 0.0)
    if duration <= 0.0:
        raise RuntimeError("미디어 길이를 확인하지 못해 자동 판정을 진행할 수 없습니다.")

    center = duration / 3.0
    start = max(0.0, center - 90.0)
    span = min(180.0, max(60.0, duration - start))
    if start + span > duration:
        span = max(30.0, duration - start)
        start = max(0.0, duration - span)

    tmpdir = str(tmpdir or tempfile.mkdtemp(prefix="audio_preset_auto_"))
    wav_path = os.path.join(tmpdir, "sample.wav")
    cmd = [
        ffmpeg_binary(),
        "-y",
        "-ss", f"{start:.3f}",
        "-t", f"{span:.3f}",
        "-i", media_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-sample_fmt", "s16",
        wav_path,
    ]
    import subprocess
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        **hidden_subprocess_kwargs(),
    )
    if proc.returncode != 0 or not os.path.exists(wav_path):
        raise RuntimeError(f"자동 판정용 오디오 샘플 추출 실패: {proc.stderr[:300]}")

    rep_start, rep_duration = choose_representative_window(wav_path)
    if rep_duration <= 0.0:
        rep_start, rep_duration = 0.0, min(60.0, span)
    return {
        "wav_path": wav_path,
        "media_duration_sec": duration,
        "window_start_sec": start,
        "window_duration_sec": span,
        "representative_start_sec": rep_start,
        "representative_duration_sec": rep_duration,
    }


def choose_representative_window(wav_path: str) -> tuple[float, float]:
    rate, samples = _load_wav(wav_path)
    if samples.size == 0:
        return 0.0, 0.0
    total_sec = len(samples) / float(rate)
    if total_sec <= 60.0:
        return 0.0, total_sec
    best_start = 0.0
    best_score = -1.0
    window_sec = 60.0
    frame_size = int(rate * 0.02)
    max_start = max(0.0, total_sec - window_sec)
    candidate_count = 10
    starts = np.linspace(0.0, max_start, num=candidate_count) if max_start > 0.0 else np.array([0.0])
    for start_sec in starts:
        start_idx = int(start_sec * rate)
        end_idx = min(len(samples), start_idx + int(window_sec * rate))
        chunk = samples[start_idx:end_idx]
        if chunk.size == 0:
            continue
        score = _speech_presence_score(chunk, frame_size)
        if score > best_score:
            best_score = score
            best_start = float(start_sec)
    return best_start, min(window_sec, total_sec - best_start)


def analyze_sample_features(wav_path: str, *, start_sec: float = 0.0, duration_sec: float | None = None) -> dict:
    rate, samples = _load_wav(wav_path)
    if samples.size and (start_sec > 0.0 or duration_sec is not None):
        start_idx = max(0, int(float(start_sec) * rate))
        end_idx = len(samples) if duration_sec is None else min(len(samples), start_idx + int(float(duration_sec) * rate))
        samples = samples[start_idx:end_idx]
    if samples.size == 0:
        return {
            "rms_mean": 0.0,
            "rms_p90": 0.0,
            "silence_ratio": 1.0,
            "zero_crossing_rate": 0.0,
            "low_band_ratio": 0.0,
            "mid_band_ratio": 0.0,
            "high_band_ratio": 0.0,
            "spectral_centroid_hz": 0.0,
        }

    frame_size = max(1, int(rate * 0.02))
    usable = (samples.size // frame_size) * frame_size
    frames = samples[:usable].reshape(-1, frame_size) if usable else samples[:1].reshape(1, -1)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    silence_ratio = float(np.mean(rms < 0.015))
    zc = np.mean(np.abs(np.diff(np.sign(frames), axis=1)) > 0, axis=1) / 2.0
    zero_crossing_rate = float(np.mean(zc))

    spectrum = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / rate)
    total_energy = float(np.sum(spectrum) or 1.0)
    low_band_ratio = float(np.sum(spectrum[freqs < 250]) / total_energy)
    mid_band_ratio = float(np.sum(spectrum[(freqs >= 250) & (freqs < 2000)]) / total_energy)
    high_band_ratio = float(np.sum(spectrum[freqs >= 2000]) / total_energy)
    spectral_centroid_hz = float(np.sum(freqs * spectrum) / total_energy)

    return {
        "rms_mean": round(float(np.mean(rms)), 6),
        "rms_p90": round(float(np.percentile(rms, 90)), 6),
        "silence_ratio": round(silence_ratio, 6),
        "zero_crossing_rate": round(zero_crossing_rate, 6),
        "low_band_ratio": round(low_band_ratio, 6),
        "mid_band_ratio": round(mid_band_ratio, 6),
        "high_band_ratio": round(high_band_ratio, 6),
        "spectral_centroid_hz": round(spectral_centroid_hz, 3),
    }


def _load_wav(wav_path: str) -> tuple[int, np.ndarray]:
    with wave.open(wav_path, "rb") as wf:
        rate = int(wf.getframerate() or 16000)
        frames = wf.readframes(wf.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return rate, samples


def _speech_presence_score(samples: np.ndarray, frame_size: int) -> float:
    if samples.size == 0:
        return -1.0
    usable = (samples.size // frame_size) * frame_size
    if usable <= 0:
        rms = math.sqrt(float(np.mean(np.square(samples))) or 0.0)
        return rms
    frames = samples[:usable].reshape(-1, frame_size)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    silence_ratio = float(np.mean(rms < 0.015))
    return float(np.mean(rms) * (1.0 - silence_ratio) * (1.0 + np.percentile(rms, 90)))


def _heuristic_decision(features: dict) -> dict:
    low = float(features.get("low_band_ratio", 0.0) or 0.0)
    high = float(features.get("high_band_ratio", 0.0) or 0.0)
    silence = float(features.get("silence_ratio", 1.0) or 1.0)
    rms = float(features.get("rms_mean", 0.0) or 0.0)
    zcr = float(features.get("zero_crossing_rate", 0.0) or 0.0)

    mic_present = rms >= 0.024 and silence <= 0.68 and high <= 0.20
    if low >= 0.58:
        environment = "차안"
    elif high >= 0.12 or zcr >= 0.16 or float(features.get("spectral_centroid_hz", 0.0) or 0.0) >= 2500.0:
        environment = "실외"
    else:
        environment = "실내"

    audio_preset = f"{environment}-마이크{'유' if mic_present else '무'}"
    if environment == "실내" and mic_present:
        stt_quality = "balanced"
    elif environment == "실내":
        stt_quality = "balanced"
    else:
        stt_quality = "precise"
    if rms < 0.012 and silence > 0.82:
        stt_quality = "fast"
    return {
        "audio_preset": audio_preset,
        "stt_quality_preset": stt_quality,
        "confidence": 0.62,
        "reason": f"휴리스틱 판정: {environment}, 마이크 {'유' if mic_present else '무'} 추정",
    }


def _llm_classify(features: dict, settings: dict) -> dict:
    model_name = str(settings.get("selected_model") or "").strip()
    provider = str(settings.get("selected_llm_provider") or "").strip().lower()
    if not model_name or "사용 안함" in model_name:
        return {}

    prompt = _build_llm_prompt(features)
    try:
        if provider == "google":
            api_key = get_api_key("google")
            return _gemini_json(api_key, model_name, prompt)
        if provider == "openai" or is_openai_model(model_name):
            api_key = get_api_key("openai")
            return _openai_json(api_key, model_name, prompt)
        return _ollama_json(model_name, prompt)
    except Exception:
        return {}


def _build_llm_prompt(features: dict) -> str:
    return (
        "너는 오디오 전처리 분류기다. 반드시 JSON 객체만 반환해.\n"
        "허용 audio_preset: "
        f"{', '.join(SUPPORTED_AUDIO_PRESETS)}\n"
        "허용 stt_quality_preset: fast, balanced, precise\n"
        "판정 기준:\n"
        "- 환경은 실내/실외/차안 중 하나\n"
        "- 마이크 유무는 외부 마이크/내장 마이크 체감 기준으로 판단\n"
        "- 잡음이 많거나 차내/실외 성격이면 precise 쪽을 우선\n"
        "- 입력 특징값만 근거로 보수적으로 판단\n\n"
        "반환 형식:\n"
        '{"audio_preset":"실내-마이크유","stt_quality_preset":"balanced","confidence":0.84,"reason":"짧은 한국어 설명"}\n\n'
        f"입력 특징값:\n{json.dumps(features, ensure_ascii=False, indent=2)}"
    )


def _ollama_json(model: str, prompt: str) -> dict:
    ensure_ollama_server(wait_sec=4.0)
    req = _build_generate_request(model, prompt, keep_alive=0)
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return _parse_json_response(str(payload.get("response", "") or ""))


def _openai_json(api_key: str, model_name: str, prompt: str) -> dict:
    if not api_key:
        return {}
    body = json.dumps({
        "model": resolve_openai_model(model_name),
        "input": prompt,
        "text": {"format": {"type": "json_object"}},
        "reasoning": {"effort": "minimal"},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    text = payload.get("output_text", "") or ""
    if not text:
        parts = []
        for item in payload.get("output", []) or []:
            for content in item.get("content", []) or []:
                if isinstance(content.get("text"), str):
                    parts.append(content["text"])
        text = "\n".join(parts)
    return _parse_json_response(text)


def _gemini_json(api_key: str, model_name: str, prompt: str) -> dict:
    if not api_key:
        return {}
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=resolve_gemini_model(model_name),
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )
    return _parse_json_response(response.text or "")


def _parse_json_response(text: str) -> dict:
    text = str(text or "").strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start:end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
    return {}


def _safe_confidence(value, fallback: float) -> float:
    try:
        conf = float(value)
    except Exception:
        conf = float(fallback)
    return max(0.0, min(1.0, conf))
