# Version: 03.14.13
# Phase: PHASE2
from __future__ import annotations

import json
import math
import os
import tempfile
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from core.audio.audio_presets import auto_audio_settings_only
from core.audio.stt_quality_presets import normalize_stt_quality_key
from core.media_info import probe_media
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.runtime import config


AUTO_AUDIO_PRESET_NAME = "auto"
AUDIO_LORA_CORPUS_PATH = Path(config.DATASET_DIR) / "lora_personalization" / "audio_preset_lora.jsonl"


_AUTO_AUDIO_CANDIDATES = (
    {
        "id": "clean_voice",
        "label": "Clean Voice",
        "settings": {
            "selected_audio_ai": "deepfilter",
            "selected_vad": "silero",
            "use_basic_filter": True,
            "ff_ar": 16000,
            "ff_ac": 1,
            "ff_hp": 100,
            "ff_lp": 5200,
            "ff_nf": -24,
            "ff_dynaudnorm_m": 10.0,
            "ff_dynaudnorm_p": 0.95,
            "ff_treble_boost": 0.8,
            "df_hp": 100,
            "df_lp": 5600,
            "df_eq_g": 8,
            "df_comp_th": -28,
            "df_vol": 3.6,
            "vad_threshold": 0.46,
            "vad_min_speech": 0.22,
            "vad_min_silence": 1.6,
            "vad_speech_pad": 0.1,
            "vad_post_stt_align_enabled": True,
        },
    },
    {
        "id": "noisy_voice",
        "label": "Noisy Voice",
        "settings": {
            "selected_audio_ai": "clearvoice",
            "selected_vad": "ten_vad",
            "use_basic_filter": True,
            "ff_ar": 16000,
            "ff_ac": 1,
            "ff_hp": 150,
            "ff_lp": 4600,
            "ff_nf": -30,
            "ff_dynaudnorm_m": 16.0,
            "ff_dynaudnorm_p": 0.97,
            "ff_treble_boost": 3.0,
            "df_hp": 150,
            "df_lp": 5200,
            "df_comp_th": -28,
            "df_vol": 5.0,
            "vad_threshold": 0.55,
            "ten_vad_threshold": 0.55,
            "vad_min_speech": 0.2,
            "vad_min_silence": 1.0,
            "vad_speech_pad": 0.14,
            "vad_post_stt_align_enabled": True,
        },
    },
    {
        "id": "low_rumble",
        "label": "Low Rumble Guard",
        "settings": {
            "selected_audio_ai": "clearvoice",
            "selected_vad": "ten_vad",
            "use_basic_filter": True,
            "ff_ar": 16000,
            "ff_ac": 1,
            "ff_hp": 185,
            "ff_lp": 4200,
            "ff_nf": -30,
            "ff_dynaudnorm_m": 18.0,
            "ff_dynaudnorm_p": 0.97,
            "ff_treble_boost": 2.5,
            "df_hp": 170,
            "df_lp": 4800,
            "df_comp_th": -30,
            "df_vol": 5.1,
            "vad_threshold": 0.52,
            "ten_vad_threshold": 0.52,
            "vad_min_speech": 0.2,
            "vad_min_silence": 1.2,
            "vad_speech_pad": 0.12,
            "vad_post_stt_align_enabled": True,
        },
    },
    {
        "id": "quiet_boost",
        "label": "Quiet Boost",
        "settings": {
            "selected_audio_ai": "deepfilter",
            "selected_vad": "silero",
            "use_basic_filter": True,
            "ff_ar": 16000,
            "ff_ac": 1,
            "ff_hp": 120,
            "ff_lp": 4800,
            "ff_nf": -27,
            "ff_dynaudnorm_m": 18.0,
            "ff_dynaudnorm_p": 0.97,
            "ff_treble_boost": 1.8,
            "df_hp": 130,
            "df_lp": 5200,
            "df_eq_g": 10,
            "df_comp_th": -30,
            "df_vol": 5.2,
            "none_hp": 120,
            "none_lp": 4200,
            "none_nf": -28,
            "none_vol": 5.5,
            "vad_threshold": 0.48,
            "vad_min_speech": 0.2,
            "vad_min_silence": 1.4,
            "vad_speech_pad": 0.12,
            "vad_post_stt_align_enabled": True,
        },
    },
    {
        "id": "fast_noise_gate",
        "label": "Fast Noise Gate",
        "settings": {
            "selected_audio_ai": "rnnoise",
            "selected_vad": "silero",
            "use_basic_filter": True,
            "ff_ar": 16000,
            "ff_ac": 1,
            "ff_hp": 130,
            "ff_lp": 5000,
            "ff_nf": -28,
            "ff_dynaudnorm_m": 13.0,
            "ff_dynaudnorm_p": 0.96,
            "ff_treble_boost": 2.0,
            "df_hp": 130,
            "df_lp": 5200,
            "df_eq_g": 9,
            "df_comp_th": -28,
            "df_vol": 4.5,
            "vad_threshold": 0.5,
            "vad_min_speech": 0.22,
            "vad_min_silence": 1.3,
            "vad_speech_pad": 0.12,
            "vad_post_stt_align_enabled": True,
        },
    },
    {
        "id": "minimal_hot_signal",
        "label": "Minimal Hot Signal",
        "settings": {
            "selected_audio_ai": "none",
            "selected_vad": "silero",
            "use_basic_filter": True,
            "ff_ar": 16000,
            "ff_ac": 1,
            "ff_hp": 90,
            "ff_lp": 5200,
            "ff_nf": -22,
            "ff_dynaudnorm_m": 8.0,
            "ff_dynaudnorm_p": 0.94,
            "ff_treble_boost": 0.0,
            "none_hp": 90,
            "none_lp": 5200,
            "none_nf": -22,
            "none_vol": 3.6,
            "vad_threshold": 0.48,
            "vad_min_speech": 0.22,
            "vad_min_silence": 1.5,
            "vad_speech_pad": 0.1,
            "vad_post_stt_align_enabled": True,
        },
    },
)


def auto_classify_media_presets(media_path: str, settings: dict | None = None) -> dict:
    settings = dict(settings or {})
    media_path = str(media_path or "").strip()
    if not media_path or not os.path.exists(media_path):
        raise FileNotFoundError("자동 판정을 위한 미디어 파일을 찾을 수 없습니다.")

    with tempfile.TemporaryDirectory(prefix="audio_preset_auto_") as tmpdir:
        scan = prepare_audio_samples(media_path, tmpdir=tmpdir)
        features = aggregate_sample_features(scan.get("samples") or [])
        features["media_duration_sec"] = float(scan.get("media_duration_sec", features.get("media_duration_sec", 0.0)) or 0.0)

    profile = build_audio_profile(features)
    candidate_result = select_audio_candidate(profile, features)
    tune_settings = auto_audio_settings_only(candidate_result.get("settings") or {})
    confidence = _safe_confidence(candidate_result.get("score"), 0.62)
    reason = _decision_reason(profile, candidate_result)
    result = {
        "audio_preset": AUTO_AUDIO_PRESET_NAME,
        "audio_strategy": str(candidate_result.get("id") or "clean_voice"),
        "audio_strategy_label": str(candidate_result.get("label") or ""),
        "stt_quality_preset": normalize_stt_quality_key(settings.get("stt_quality_preset") or "precise"),
        "confidence": confidence,
        "reason": reason,
        "features": features,
        "audio_profile": profile,
        "audio_tune_settings": tune_settings,
        "audio_tune_reason": str(candidate_result.get("reason") or ""),
        "candidate_scores": list(candidate_result.get("candidate_scores") or []),
        "scan": {
            "sample_count": int(features.get("sample_count", 0) or 0),
            "sample_duration_sec": float(features.get("sample_duration_sec", 0.0) or 0.0),
            "total_scanned_sec": float(features.get("total_scanned_sec", 0.0) or 0.0),
            "samples": list(features.get("samples", []) or []),
        },
        "lora_prior_used": bool(candidate_result.get("lora_prior_used", False)),
        "llm_used": False,
    }
    return result


def apply_auto_classified_presets(settings: dict, decision: dict) -> dict:
    updated = dict(settings or {})
    tune_settings = auto_audio_settings_only(decision.get("audio_tune_settings") or {})
    if tune_settings:
        updated.update(tune_settings)
        updated["audio_preset_auto_tune"] = tune_settings
    updated["audio_preset"] = AUTO_AUDIO_PRESET_NAME
    updated["audio_preset_auto_decision"] = {
        "audio_preset": AUTO_AUDIO_PRESET_NAME,
        "audio_strategy": str(decision.get("audio_strategy") or ""),
        "audio_strategy_label": str(decision.get("audio_strategy_label") or ""),
        "suggested_stt_quality_preset": normalize_stt_quality_key(decision.get("stt_quality_preset") or "precise"),
        "stt_quality_preset": updated.get("stt_quality_preset", "precise"),
        "confidence": float(decision.get("confidence", 0.0) or 0.0),
        "reason": str(decision.get("reason") or ""),
        "audio_tune_reason": str(decision.get("audio_tune_reason") or ""),
        "audio_profile": dict(decision.get("audio_profile") or {}),
        "audio_tune_settings": tune_settings,
        "candidate_scores": list(decision.get("candidate_scores") or []),
        "scan": dict(decision.get("scan") or {}),
        "lora_prior_used": bool(decision.get("lora_prior_used", False)),
        "llm_used": bool(decision.get("llm_used", False)),
    }
    return updated


def build_audio_profile(features: dict, **_legacy_kwargs) -> dict:
    low = float(features.get("low_band_ratio", 0.0) or 0.0)
    high = float(features.get("high_band_ratio", 0.0) or 0.0)
    silence = float(features.get("silence_ratio", 1.0) or 1.0)
    rms = float(features.get("rms_mean", 0.0) or 0.0)
    rms_p90 = float(features.get("rms_p90", 0.0) or 0.0)
    zcr = float(features.get("zero_crossing_rate", 0.0) or 0.0)
    centroid = float(features.get("spectral_centroid_hz", 0.0) or 0.0)

    if low >= 0.56:
        environment = "car"
    elif high >= 0.12 or zcr >= 0.16 or centroid >= 2500.0:
        environment = "outdoor"
    else:
        environment = "indoor"

    mic_present = rms >= 0.024 and silence <= 0.68 and high <= 0.20
    if high >= 0.16 or zcr >= 0.20:
        noise_level = "high"
    elif high >= 0.09 or zcr >= 0.13:
        noise_level = "medium"
    else:
        noise_level = "low"
    low_rumble = bool(low >= 0.52 or environment == "car")
    quiet = bool(rms < 0.018 or silence >= 0.76)
    hot_signal = bool(rms_p90 >= 0.22)
    speech_density = max(0.0, min(1.0, 1.0 - silence))
    volume_conf = min(1.0, max(0.0, rms / 0.05))
    noise_penalty = min(0.35, high * 0.9 + max(0.0, low - 0.45) * 0.35 + zcr * 0.18)
    speech_confidence = max(0.05, min(0.98, 0.2 + speech_density * 0.42 + volume_conf * 0.34 - noise_penalty))

    return {
        "environment": environment,
        "mic_present": mic_present,
        "noise_level": noise_level,
        "low_rumble": low_rumble,
        "quiet": quiet,
        "hot_signal": hot_signal,
        "speech_density": round(speech_density, 4),
        "speech_confidence": round(float(speech_confidence), 4),
        "sample_count": int(features.get("sample_count", 0) or 0),
    }


def tune_audio_settings_for_profile(profile: dict, features: dict | None = None) -> tuple[dict, str]:
    result = select_audio_candidate(dict(profile or {}), dict(features or {}), use_lora_prior=False)
    return auto_audio_settings_only(result.get("settings") or {}), str(result.get("reason") or "")


def build_audio_scan_plan(duration_sec: float, *, sample_sec: float = 30.0) -> list[dict]:
    duration = max(0.0, float(duration_sec or 0.0))
    sample_sec = max(5.0, min(float(sample_sec or 30.0), max(5.0, duration or 30.0)))
    if duration <= sample_sec:
        return [{"start_sec": 0.0, "duration_sec": round(duration or sample_sec, 3)}]
    if duration <= 90.0:
        count = 1
    elif duration <= 600.0:
        count = 3
    elif duration <= 1800.0:
        count = 5
    else:
        count = min(9, max(6, int(math.ceil(duration / 600.0)) + 3))
    max_start = max(0.0, duration - sample_sec)
    starts = np.linspace(0.0, max_start, num=count) if count > 1 else np.array([max_start / 2.0])
    return [
        {"start_sec": round(float(start), 3), "duration_sec": round(sample_sec, 3)}
        for start in starts
    ]


def prepare_audio_samples(media_path: str, *, tmpdir: str | None = None, sample_sec: float = 30.0) -> dict:
    info = probe_media(media_path)
    duration = float(info.get("duration", 0.0) or 0.0)
    if duration <= 0.0:
        raise RuntimeError("미디어 길이를 확인하지 못해 자동 판정을 진행할 수 없습니다.")

    tmpdir = str(tmpdir or tempfile.mkdtemp(prefix="audio_preset_auto_"))
    plan = build_audio_scan_plan(duration, sample_sec=sample_sec)
    samples = []
    import subprocess

    for idx, row in enumerate(plan, start=1):
        start = float(row.get("start_sec", 0.0) or 0.0)
        span = float(row.get("duration_sec", sample_sec) or sample_sec)
        wav_path = os.path.join(tmpdir, f"sample_{idx:02d}.wav")
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
        features = analyze_sample_features(wav_path)
        samples.append({
            "index": idx,
            "wav_path": wav_path,
            "start_sec": round(start, 3),
            "duration_sec": round(span, 3),
            "features": features,
            "speech_score": round(_speech_feature_score(features), 6),
        })

    return {
        "media_duration_sec": round(duration, 3),
        "sample_sec": round(sample_sec, 3),
        "plan": plan,
        "samples": samples,
    }


def aggregate_sample_features(samples: list[dict]) -> dict:
    rows = [dict((sample or {}).get("features") or {}) for sample in samples or []]
    if not rows:
        return {
            "rms_mean": 0.0,
            "rms_p90": 0.0,
            "silence_ratio": 1.0,
            "zero_crossing_rate": 0.0,
            "low_band_ratio": 0.0,
            "mid_band_ratio": 0.0,
            "high_band_ratio": 0.0,
            "spectral_centroid_hz": 0.0,
            "sample_count": 0,
            "sample_duration_sec": 0.0,
            "total_scanned_sec": 0.0,
            "samples": [],
        }
    keys = (
        "rms_mean",
        "rms_p90",
        "silence_ratio",
        "zero_crossing_rate",
        "low_band_ratio",
        "mid_band_ratio",
        "high_band_ratio",
        "spectral_centroid_hz",
    )
    aggregate = {
        key: round(float(np.mean([float(row.get(key, 0.0) or 0.0) for row in rows])), 6)
        for key in keys
    }
    duration_values = [float((sample or {}).get("duration_sec", 0.0) or 0.0) for sample in samples or []]
    aggregate.update({
        "media_duration_sec": round(max(float((sample or {}).get("start_sec", 0.0) or 0.0) + float((sample or {}).get("duration_sec", 0.0) or 0.0) for sample in samples or []), 3),
        "sample_count": len(rows),
        "sample_duration_sec": round(float(np.mean(duration_values)) if duration_values else 0.0, 3),
        "total_scanned_sec": round(float(sum(duration_values)), 3),
        "samples": [
            {
                "index": int((sample or {}).get("index", 0) or 0),
                "start_sec": float((sample or {}).get("start_sec", 0.0) or 0.0),
                "duration_sec": float((sample or {}).get("duration_sec", 0.0) or 0.0),
                "speech_score": float((sample or {}).get("speech_score", 0.0) or 0.0),
            }
            for sample in samples or []
        ],
    })
    aggregate["speech_confidence"] = round(_speech_feature_confidence(aggregate), 4)
    return aggregate


def select_audio_candidate(
    profile: dict,
    features: dict,
    *,
    use_lora_prior: bool = True,
) -> dict:
    profile = dict(profile or {})
    features = dict(features or {})
    prior = _audio_lora_prior_scores(profile) if use_lora_prior else {}
    scored = []
    for candidate in _AUTO_AUDIO_CANDIDATES:
        cid = str(candidate.get("id") or "")
        base_score, reasons = _score_audio_candidate(candidate, profile, features)
        prior_boost = float(prior.get(cid, 0.0) or 0.0)
        score = max(0.0, min(0.99, base_score + prior_boost))
        scored.append({
            "id": cid,
            "label": str(candidate.get("label") or cid),
            "score": round(score, 4),
            "base_score": round(base_score, 4),
            "lora_prior": round(prior_boost, 4),
            "reason": ", ".join(dict.fromkeys(reasons)),
        })
    scored.sort(key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)
    best_id = str((scored[0] if scored else {}).get("id") or "clean_voice")
    best = next((candidate for candidate in _AUTO_AUDIO_CANDIDATES if candidate.get("id") == best_id), _AUTO_AUDIO_CANDIDATES[0])
    best_score = float((scored[0] if scored else {}).get("score", 0.62) or 0.62)
    reason = str((scored[0] if scored else {}).get("reason") or "기본 음성 인식 안정성 우선")
    return {
        "id": str(best.get("id") or best_id),
        "label": str(best.get("label") or best_id),
        "score": best_score,
        "settings": auto_audio_settings_only(best.get("settings") or {}),
        "reason": reason,
        "candidate_scores": scored,
        "lora_prior_used": any(float(row.get("lora_prior", 0.0) or 0.0) > 0.0 for row in scored),
    }


def append_audio_lora_record(decision: dict, media_path: str = "", *, path: str | Path | None = None) -> dict:
    decision = dict(decision or {})
    target = Path(path) if path else AUDIO_LORA_CORPUS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schema": "ai_subtitle_studio.audio_preset_lora.v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "media_path": str(media_path or ""),
        "audio_strategy": str(decision.get("audio_strategy") or ""),
        "audio_strategy_label": str(decision.get("audio_strategy_label") or ""),
        "confidence": float(decision.get("confidence", 0.0) or 0.0),
        "reason": str(decision.get("reason") or ""),
        "audio_profile": dict(decision.get("audio_profile") or {}),
        "features": dict(decision.get("features") or {}),
        "audio_tune_settings": auto_audio_settings_only(decision.get("audio_tune_settings") or {}),
        "candidate_scores": list(decision.get("candidate_scores") or []),
        "scan": dict(decision.get("scan") or {}),
    }
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {"path": str(target), "row": row}


def format_auto_audio_decision_log(decision: dict, media_path: str = "") -> str:
    decision = dict(decision or {})
    profile = dict(decision.get("audio_profile") or {})
    settings = dict(decision.get("audio_tune_settings") or {})
    scan = dict(decision.get("scan") or {})
    env = {"indoor": "실내", "outdoor": "실외/개방 공간", "car": "차량/저역 울림"}.get(str(profile.get("environment") or ""), "미확인")
    mic = "외부 마이크 가능성 높음" if bool(profile.get("mic_present")) else "내장/원거리 마이크 가능성"
    noise = {"low": "낮음", "medium": "중간", "high": "높음"}.get(str(profile.get("noise_level") or ""), "미확인")
    speech_conf = int(round(float(profile.get("speech_confidence", decision.get("confidence", 0.0)) or 0.0) * 100))
    sample_count = int(scan.get("sample_count", profile.get("sample_count", 0)) or 0)
    sample_sec = float(scan.get("sample_duration_sec", 0.0) or 0.0)
    total_sec = float(scan.get("total_scanned_sec", 0.0) or 0.0)
    audio_ai = _audio_ai_label(settings.get("selected_audio_ai"))
    vad = _vad_label(settings.get("selected_vad"))
    candidate = str(decision.get("audio_strategy_label") or decision.get("audio_strategy") or "")
    score_lines = []
    for row in list(decision.get("candidate_scores") or [])[:3]:
        score_lines.append(f"{row.get('label')}: {int(round(float(row.get('score', 0.0) or 0.0) * 100))}%")
    score_text = " / ".join(score_lines)
    values = (
        f"ff_hp={settings.get('ff_hp')}, ff_lp={settings.get('ff_lp')}, "
        f"ff_nf={settings.get('ff_nf')}, vad_threshold={settings.get('vad_threshold', settings.get('ten_vad_threshold'))}"
    )
    lora_text = "사용" if bool(decision.get("lora_prior_used")) else "누적 기록"
    return (
        "🎚️ [오토 오디오] 클립별 자동 프리셋 결정\n"
        f"  📂 파일: {os.path.basename(str(media_path or '')) or '-'}\n"
        f"  🔎 스캔: {sample_count}개 구간 × 약 {sample_sec:.0f}초 = {total_sec:.0f}초 검증\n"
        f"  🧭 상황: {env} / {mic} / 노이즈 {noise} / 음성 자신감 {speech_conf}%\n"
        f"  🧪 후보 검증: {score_text or '-'}\n"
        f"  ✅ 선택: {candidate} → 전처리 FFMPEG + 음성필터 {audio_ai} + VAD {vad}\n"
        f"  ⚙️ 적용값: {values}\n"
        f"  🧠 LoRA 학습 데이터: {lora_text}\n"
        f"  💬 근거: {decision.get('audio_tune_reason') or decision.get('reason') or '-'}"
    )


def _score_audio_candidate(candidate: dict, profile: dict, features: dict) -> tuple[float, list[str]]:
    cid = str(candidate.get("id") or "")
    env = str(profile.get("environment") or "indoor")
    noise = str(profile.get("noise_level") or "low")
    low_rumble = bool(profile.get("low_rumble"))
    quiet = bool(profile.get("quiet"))
    hot = bool(profile.get("hot_signal"))
    speech_conf = float(profile.get("speech_confidence", features.get("speech_confidence", 0.55)) or 0.55)
    score = 0.42 + speech_conf * 0.28
    reasons: list[str] = []

    if cid == "low_rumble":
        score += 0.32 if low_rumble or env == "car" else -0.08
        reasons.append("저역 울림/차량성 대응")
    elif cid == "noisy_voice":
        score += 0.3 if noise == "high" or env == "outdoor" else (-0.02 if noise == "medium" else -0.1)
        reasons.append("잡음 많은 음성 보호")
    elif cid == "quiet_boost":
        score += 0.3 if quiet else -0.04
        reasons.append("작은 음량 보강")
    elif cid == "fast_noise_gate":
        score += 0.16 if noise == "medium" and not low_rumble else -0.03
        reasons.append("중간 잡음 빠른 억제")
    elif cid == "minimal_hot_signal":
        score += 0.22 if hot and noise == "low" else -0.12
        reasons.append("과입력 원본 보존")
    else:
        score += 0.2 if noise == "low" and not quiet and not low_rumble else -0.02
        reasons.append("일반 음성 균형")

    if quiet and cid not in {"quiet_boost", "noisy_voice"}:
        score -= 0.08
    if low_rumble and cid not in {"low_rumble", "noisy_voice"}:
        score -= 0.12
    if noise == "high" and cid not in {"noisy_voice", "low_rumble"}:
        score -= 0.13
    if hot and cid in {"quiet_boost", "noisy_voice"}:
        score -= 0.08
    return max(0.0, min(0.98, score)), reasons


def _audio_lora_prior_scores(profile: dict) -> dict[str, float]:
    path = AUDIO_LORA_CORPUS_PATH
    if not path.exists():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-240:]
    except Exception:
        return {}
    counts: dict[str, int] = {}
    env = str(profile.get("environment") or "")
    noise = str(profile.get("noise_level") or "")
    for line in lines:
        try:
            row = json.loads(line)
        except Exception:
            continue
        row_profile = dict(row.get("audio_profile") or {})
        if str(row_profile.get("environment") or "") != env:
            continue
        if str(row_profile.get("noise_level") or "") != noise:
            continue
        strategy = str(row.get("audio_strategy") or "")
        if strategy:
            counts[strategy] = counts.get(strategy, 0) + 1
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {key: min(0.08, 0.02 + 0.06 * (value / total)) for key, value in counts.items()}


def _speech_feature_score(features: dict) -> float:
    return _speech_feature_confidence(features)


def _speech_feature_confidence(features: dict) -> float:
    silence = float(features.get("silence_ratio", 1.0) or 1.0)
    rms = float(features.get("rms_mean", 0.0) or 0.0)
    high = float(features.get("high_band_ratio", 0.0) or 0.0)
    low = float(features.get("low_band_ratio", 0.0) or 0.0)
    zcr = float(features.get("zero_crossing_rate", 0.0) or 0.0)
    speech_density = max(0.0, min(1.0, 1.0 - silence))
    volume_conf = min(1.0, max(0.0, rms / 0.05))
    noise_penalty = min(0.35, high * 0.9 + max(0.0, low - 0.45) * 0.35 + zcr * 0.18)
    return max(0.05, min(0.98, 0.2 + speech_density * 0.42 + volume_conf * 0.34 - noise_penalty))


def _decision_reason(profile: dict, candidate_result: dict) -> str:
    env = {"indoor": "실내", "outdoor": "실외/개방 공간", "car": "차량/저역 울림"}.get(str(profile.get("environment") or ""), "환경 미확인")
    noise = {"low": "낮은 잡음", "medium": "중간 잡음", "high": "높은 잡음"}.get(str(profile.get("noise_level") or ""), "잡음 미확인")
    mic = "외부 마이크 추정" if bool(profile.get("mic_present")) else "내장/원거리 마이크 추정"
    speech = int(round(float(profile.get("speech_confidence", 0.0) or 0.0) * 100))
    return (
        f"{env}, {mic}, {noise}, 음성 자신감 {speech}% 기준으로 "
        f"{candidate_result.get('label', candidate_result.get('id', '자동'))} 선택"
    )


def _audio_ai_label(value: object) -> str:
    return {
        "deepfilter": "DeepFilter",
        "rnnoise": "RNNoise",
        "resemble_enhance": "Resemble Enhance",
        "clearvoice": "ClearVoice",
        "none": "미사용",
    }.get(str(value or "none"), str(value or "미사용"))


def _vad_label(value: object) -> str:
    return {
        "silero": "Silero",
        "ten_vad": "TEN VAD",
        "webrtc": "WebRTC",
        "pyannote": "Pyannote",
        "none": "미사용",
    }.get(str(value or "none"), str(value or "미사용"))


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


def _safe_confidence(value, fallback: float) -> float:
    try:
        conf = float(value)
    except Exception:
        conf = float(fallback)
    return max(0.0, min(1.0, conf))
