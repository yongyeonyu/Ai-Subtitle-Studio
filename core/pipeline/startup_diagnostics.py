"""Startup media diagnostics for automatic pipeline selection."""
from __future__ import annotations

import copy
import json
import os
import subprocess
from datetime import datetime
from typing import Any

from core.media_info import probe_media
from core.native_swift_startup_diagnostics import (
    attach_expected_processing_time_via_swift,
    build_startup_diagnostic_via_swift,
    format_startup_diagnostic_log_via_swift,
)
from core.platform_compat import ffprobe_binary, hidden_subprocess_kwargs
from core.project.project_io import read_project_file, write_project_file

STARTUP_DIAGNOSTIC_SCHEMA = "ai_subtitle_studio.startup_diagnostic.v1"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        if parsed == parsed:
            return parsed
    except Exception:
        pass
    return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _duration_label(seconds: float) -> str:
    seconds = _to_float(seconds, 0.0)
    if seconds <= 0:
        return "-"
    total = int(round(seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def _processing_label(seconds: float) -> str:
    seconds = _to_float(seconds, 0.0)
    if seconds <= 0:
        return "예상불가"
    total = int(round(seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}시간 {minutes}분 {sec}초"
    if minutes:
        return f"{minutes}분 {sec}초"
    return f"{sec}초"


def _boundary_time(row: Any) -> float:
    if isinstance(row, dict):
        for key in ("timeline_sec", "time", "start", "sec"):
            if key in row:
                return _to_float(row.get(key), 0.0)
        return 0.0
    return _to_float(row, 0.0)


def _first_audio_stream(payload: dict[str, Any]) -> dict[str, Any] | None:
    for stream in list(payload.get("streams", []) or []):
        if isinstance(stream, dict) and stream.get("codec_type") == "audio":
            return stream
    return None


def probe_audio_stream_info(media_path: str, *, timeout_sec: float = 5.0) -> dict[str, Any]:
    """Return lightweight audio metadata used by the start diagnostic."""
    result: dict[str, Any] = {
        "has_audio": False,
        "codec": "",
        "sample_rate": 0,
        "channels": 0,
        "bit_rate": 0,
        "duration_sec": 0.0,
    }
    try:
        cmd = [
            ffprobe_binary(),
            "-v",
            "error",
            "-show_entries",
            "format=duration,bit_rate:stream=index,codec_type,codec_name,sample_rate,channels,bit_rate,duration",
            "-of",
            "json",
            media_path,
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            **hidden_subprocess_kwargs(),
        )
        payload = json.loads(proc.stdout or "{}")
        stream = _first_audio_stream(payload)
        if not stream:
            return result
        fmt = payload.get("format", {}) if isinstance(payload.get("format"), dict) else {}
        result.update(
            {
                "has_audio": True,
                "codec": str(stream.get("codec_name", "") or ""),
                "sample_rate": _to_int(stream.get("sample_rate"), 0),
                "channels": _to_int(stream.get("channels"), 0),
                "bit_rate": _to_int(stream.get("bit_rate"), _to_int(fmt.get("bit_rate"), 0)),
                "duration_sec": _to_float(stream.get("duration"), _to_float(fmt.get("duration"), 0.0)),
            }
        )
    except Exception:
        pass
    return result


def _audio_quality(audio_info: dict[str, Any]) -> dict[str, Any]:
    if not bool(audio_info.get("has_audio")):
        return {
            "score": 0,
            "label": "red",
            "summary": "오디오 없음",
            "noise_estimate": "high",
            "noise_label": "높음",
            "source": "metadata_heuristic",
            "reasons": ["audio_missing"],
        }

    score = 100
    reasons: list[str] = []
    sample_rate = _to_int(audio_info.get("sample_rate"), 0)
    bit_rate = _to_int(audio_info.get("bit_rate"), 0)
    channels = _to_int(audio_info.get("channels"), 0)

    if sample_rate and sample_rate < 16000:
        score -= 35
        reasons.append("low_sample_rate")
    elif sample_rate and sample_rate < 32000:
        score -= 15
        reasons.append("medium_sample_rate")
    elif sample_rate <= 0:
        score -= 20
        reasons.append("unknown_sample_rate")

    if bit_rate and bit_rate < 48000:
        score -= 30
        reasons.append("low_bit_rate")
    elif bit_rate and bit_rate < 96000:
        score -= 12
        reasons.append("medium_bit_rate")
    elif bit_rate <= 0:
        score -= 8
        reasons.append("unknown_bit_rate")

    if channels <= 0:
        score -= 8
        reasons.append("unknown_channels")

    score = max(0, min(100, score))
    if score >= 75:
        label, summary, noise, noise_label = "green", "양호", "low", "낮음"
    elif score >= 45:
        label, summary, noise, noise_label = "yellow", "주의", "medium", "중간"
    else:
        label, summary, noise, noise_label = "red", "복구 필요", "high", "높음"

    return {
        "score": score,
        "label": label,
        "summary": summary,
        "noise_estimate": noise,
        "noise_label": noise_label,
        "source": "metadata_heuristic",
        "reasons": reasons,
    }


def _cut_density_profile(
    cut_boundaries: list[Any] | None,
    provisional_boundaries: list[Any] | None,
    duration_sec: float,
) -> dict[str, Any]:
    cuts = [_boundary_time(row) for row in list(cut_boundaries or [])]
    cuts = [sec for sec in cuts if sec > 0]
    provisional = [_boundary_time(row) for row in list(provisional_boundaries or [])]
    provisional = [sec for sec in provisional if sec > 0]
    minutes = max(_to_float(duration_sec, 0.0) / 60.0, 0.0)
    per_minute = (len(cuts) / minutes) if minutes > 0 else 0.0
    if per_minute >= 4.0:
        level = "high"
        label = "높음"
    elif per_minute >= 1.0:
        level = "medium"
        label = "중간"
    else:
        level = "low"
        label = "낮음"
    return {
        "verified_count": len(cuts),
        "provisional_count": len(provisional),
        "per_minute": round(per_minute, 3),
        "level": level,
        "label": label,
    }


def _speaker_hint(settings: dict[str, Any] | None, speaker_count_hint: int | None) -> dict[str, Any]:
    if speaker_count_hint is not None:
        return {"count": max(1, _to_int(speaker_count_hint, 1)), "source": "runtime"}
    settings = settings if isinstance(settings, dict) else {}
    return {"count": max(1, _to_int(settings.get("max_speakers"), 1)), "source": "settings"}


def _recommend_pipeline(
    *,
    duration_sec: float,
    fps: float,
    audio_quality: dict[str, Any],
    cut_density: dict[str, Any],
    speaker_count: int,
) -> dict[str, Any]:
    if duration_sec <= 0:
        return {
            "mode": "recovery",
            "label": "복구 모드",
            "score": 100,
            "reasons": ["duration_unknown"],
        }
    if int(audio_quality.get("score", 0) or 0) < 35:
        return {
            "mode": "recovery",
            "label": "복구 모드",
            "score": 95,
            "reasons": ["audio_quality_low"],
        }

    score = 0
    reasons: list[str] = []
    if duration_sec >= 20 * 60:
        score += 2
        reasons.append("long_video")
    elif duration_sec <= 5 * 60:
        score -= 1
        reasons.append("short_video")
    if fps >= 50:
        score += 1
        reasons.append("high_fps")
    if str(cut_density.get("level")) == "high":
        score += 2
        reasons.append("dense_cuts")
    elif str(cut_density.get("level")) == "low" and duration_sec <= 8 * 60:
        score -= 1
        reasons.append("simple_cut_structure")
    if speaker_count >= 2:
        score += 1
        reasons.append("multi_speaker")
    if int(audio_quality.get("score", 0) or 0) < 70:
        score += 1
        reasons.append("audio_attention_needed")

    if score <= -2:
        mode, label = "fast", "빠른 모드"
    elif score <= 1:
        mode, label = "balanced", "균형 모드"
    else:
        mode, label = "precise", "정밀 모드"
    return {"mode": mode, "label": label, "score": score, "reasons": reasons}


def build_startup_diagnostic(
    media_path: str,
    *,
    settings: dict[str, Any] | None = None,
    cut_boundaries: list[Any] | None = None,
    provisional_cut_boundaries: list[Any] | None = None,
    expected_time_sec: float | None = None,
    speaker_count_hint: int | None = None,
) -> dict[str, Any]:
    """Build a start-of-run diagnostic profile for a media file."""
    media = probe_media(media_path)
    duration_sec = _to_float(media.get("duration"), 0.0)
    fps = _to_float(media.get("fps"), 0.0)
    audio_info = probe_audio_stream_info(media_path)
    native = build_startup_diagnostic_via_swift(
        media_path,
        media={
            "duration_sec": duration_sec,
            "fps": fps,
            "width": _to_int(media.get("width"), 0),
            "height": _to_int(media.get("height"), 0),
            "info_txt": str(media.get("info_txt", "") or ""),
        },
        audio=audio_info,
        settings=settings,
        cut_boundaries=cut_boundaries,
        provisional_cut_boundaries=provisional_cut_boundaries,
        expected_time_sec=expected_time_sec,
        speaker_count_hint=speaker_count_hint,
    )
    if isinstance(native, dict) and native.get("schema") == STARTUP_DIAGNOSTIC_SCHEMA:
        return native
    audio_quality = _audio_quality(audio_info)
    cut_density = _cut_density_profile(cut_boundaries, provisional_cut_boundaries, duration_sec)
    speakers = _speaker_hint(settings, speaker_count_hint)
    recommendation = _recommend_pipeline(
        duration_sec=duration_sec,
        fps=fps,
        audio_quality=audio_quality,
        cut_density=cut_density,
        speaker_count=int(speakers.get("count", 1) or 1),
    )
    expected = _to_float(expected_time_sec, 0.0)

    return {
        "schema": STARTUP_DIAGNOSTIC_SCHEMA,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "media_path": media_path,
        "media_name": os.path.basename(media_path),
        "media": {
            "duration_sec": round(duration_sec, 3),
            "duration_label": _duration_label(duration_sec),
            "fps": round(fps, 3),
            "width": _to_int(media.get("width"), 0),
            "height": _to_int(media.get("height"), 0),
            "info_txt": str(media.get("info_txt", "") or ""),
        },
        "audio": {**audio_info, "quality": audio_quality},
        "speakers": speakers,
        "cut_density": cut_density,
        "estimated_processing_sec": round(expected, 3) if expected > 0 else 0.0,
        "estimated_processing_label": _processing_label(expected),
        "estimated_processing_source": "history" if expected > 0 else "unknown",
        "recommended_pipeline": recommendation,
    }


def attach_expected_processing_time(
    diagnostic: dict[str, Any],
    expected_time_sec: float,
    *,
    source: str = "history",
) -> dict[str, Any]:
    """Return a diagnostic copy with ETA fields attached."""
    native = attach_expected_processing_time_via_swift(
        diagnostic if isinstance(diagnostic, dict) else {},
        expected_time_sec,
        source=source,
    )
    if isinstance(native, dict):
        return native
    updated = copy.deepcopy(diagnostic if isinstance(diagnostic, dict) else {})
    expected = _to_float(expected_time_sec, 0.0)
    updated["estimated_processing_sec"] = round(expected, 3) if expected > 0 else 0.0
    updated["estimated_processing_label"] = _processing_label(expected)
    updated["estimated_processing_source"] = str(source or "history") if expected > 0 else "unknown"
    return updated


def _reason_label(reason: str) -> str:
    labels = {
        "duration_unknown": "길이 확인 필요",
        "audio_quality_low": "오디오 품질 낮음",
        "long_video": "긴 영상",
        "short_video": "짧은 영상",
        "high_fps": "고FPS",
        "dense_cuts": "컷 많음",
        "simple_cut_structure": "단순 컷",
        "multi_speaker": "복수 화자",
        "audio_attention_needed": "오디오 주의",
    }
    return labels.get(str(reason), str(reason))


def format_startup_diagnostic_log(diagnostic: dict[str, Any]) -> list[str]:
    """Format concise Korean log lines for the terminal/status panel."""
    native = format_startup_diagnostic_log_via_swift(diagnostic if isinstance(diagnostic, dict) else {})
    if isinstance(native, list):
        return native
    if not isinstance(diagnostic, dict):
        return []
    media = diagnostic.get("media", {}) or {}
    audio = diagnostic.get("audio", {}) or {}
    quality = audio.get("quality", {}) or {}
    cut_density = diagnostic.get("cut_density", {}) or {}
    recommendation = diagnostic.get("recommended_pipeline", {}) or {}
    reasons = ", ".join(_reason_label(row) for row in list(recommendation.get("reasons", []) or [])[:4])
    if not reasons:
        reasons = "기본 안정값"
    sample_rate = _to_int(audio.get("sample_rate"), 0)
    channels = _to_int(audio.get("channels"), 0)
    sample_label = f"{sample_rate / 1000:.1f}kHz" if sample_rate else "샘플레이트 미상"
    channel_label = f"{channels}ch" if channels else "채널 미상"
    return [
        (
            "  🩺 [시작 진단] "
            f"{diagnostic.get('media_name', '')} · {media.get('duration_label', '-')} · "
            f"{media.get('fps', 0):.2f}fps · {media.get('width', 0)}x{media.get('height', 0)}"
        ),
        (
            "  🩺 [시작 진단] "
            f"오디오 {quality.get('summary', '미상')} · 노이즈 추정 {quality.get('noise_label', '미상')} · "
            f"{sample_label} · {channel_label}"
        ),
        (
            "  🩺 [시작 진단] "
            f"컷 밀도 {cut_density.get('label', '미상')} · 정식 {cut_density.get('verified_count', 0)}개 · "
            f"임시 {cut_density.get('provisional_count', 0)}개 · {cut_density.get('per_minute', 0.0):.2f}/분"
        ),
        (
            "  🩺 [시작 진단] "
            f"추천 {recommendation.get('label', '균형 모드')} · 예상 {diagnostic.get('estimated_processing_label', '예상불가')} · "
            f"근거: {reasons}"
        ),
    ]


def persist_startup_diagnostic(project_path: str, diagnostic: dict[str, Any]) -> bool:
    """Persist startup diagnostics into both project analysis locations."""
    if not project_path or not os.path.exists(project_path) or not isinstance(diagnostic, dict):
        return False
    try:
        project = read_project_file(project_path)
        analysis = project.setdefault("analysis", {})
        analysis["startup_diagnostic_schema"] = STARTUP_DIAGNOSTIC_SCHEMA
        analysis["startup_diagnostic"] = diagnostic

        editor_state = project.setdefault("editor_state", {})
        editor_analysis = editor_state.setdefault("analysis", {})
        editor_analysis["startup_diagnostic_schema"] = STARTUP_DIAGNOSTIC_SCHEMA
        editor_analysis["startup_diagnostic"] = copy.deepcopy(diagnostic)
        write_project_file(project_path, project)
        return True
    except Exception:
        return False
