from __future__ import annotations

import math
import os
from typing import Any

from core.audio.stt_quality_presets import normalize_stt_quality_key
from core.coerce import safe_float as _safe_float, safe_int as _safe_int, safe_str as _safe_str
from core.json_file import read_json_file, write_json_file_atomic
from core.native_swift_subtitle import request_native_core_task
from core.runtime import config
from core.runtime.setting_utils import setting_bool
from core.settings import load_settings
from core.speaker_profile_settings import automatic_speaker_ceiling, speaker_diarization_auto_enabled


ETA_HISTORY_SCHEMA = "ai_subtitle_studio.runtime_eta_store.v2"
_STORE_OVERRIDE_ENV = "AI_SUBTITLE_STUDIO_TIME_HISTORY_FILE"
_UNKNOWN = "unknown"
_ETA_STORE_CACHE: dict[str, tuple[int, int, dict[str, Any]]] = {}
_RUNTIME_ETA_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "사용", "켜짐"})
_ROUGHCUT_AUTORUN_FALSE_VALUES = frozenset({"0", "false", "off", "no", "사용 안함", "사용안함", "끔"})


def history_store_path(path: str | None = None) -> str:
    override = str(path or os.environ.get(_STORE_OVERRIDE_ENV, "") or "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(config.DATASET_DIR, "time_history.json")


def _history_store_stat(path: str) -> tuple[int, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return int(getattr(stat, "st_mtime_ns", 0) or 0), int(stat.st_size or 0)


def _read_history_store(path: str) -> dict[str, Any]:
    normalized = _safe_str(path)
    if not normalized:
        return {}
    current = _history_store_stat(normalized)
    cached = _ETA_STORE_CACHE.get(normalized)
    if cached is not None and current is not None and cached[0] == current[0] and cached[1] == current[1]:
        return cached[2]
    data = read_json_file(normalized, default={}, expected_type=dict, context="runtime_eta", log_errors=False)
    parsed = data if isinstance(data, dict) else {}
    if current is None:
        _ETA_STORE_CACHE.pop(normalized, None)
    else:
        _ETA_STORE_CACHE[normalized] = (current[0], current[1], parsed)
    return parsed


def _write_history_store(path: str, data: dict[str, Any]) -> None:
    normalized = _safe_str(path)
    if not normalized:
        return
    write_json_file_atomic(normalized, data, indent=2)
    current = _history_store_stat(normalized)
    if current is None:
        _ETA_STORE_CACHE.pop(normalized, None)
    else:
        _ETA_STORE_CACHE[normalized] = (current[0], current[1], data)


def _safe_bool(value: Any, default: bool = False) -> bool:
    return setting_bool(
        value,
        default,
        true_values=_RUNTIME_ETA_TRUE_VALUES,
        true_only_strings=True,
        empty_is_default=False,
    )


def _llm_disabled(model: str, provider: str) -> bool:
    lowered_model = _safe_str(model).lower()
    lowered_provider = _safe_str(provider).lower()
    if lowered_provider in {"", "none", "disabled", "off", "사용 안함", "사용안함"}:
        return True
    return (
        "사용 안함" in lowered_model
        or "사용안함" in lowered_model
        or lowered_model in {"none", "disabled", "off"}
    )


def _normalized_mode(settings: dict[str, Any]) -> str:
    raw = settings.get("stt_quality_preset", settings.get("auto_start_mode", "balanced"))
    return normalize_stt_quality_key(_safe_str(raw, "balanced"))


def _roughcut_llm_eta_details(settings: dict[str, Any], duration_sec: float) -> dict[str, Any]:
    try:
        from core.roughcut.editor_draft import editor_roughcut_draft_enabled
        from core.roughcut.roughcut_llm_config import resolve_roughcut_llm_config
    except Exception:
        return {
            "enabled": False,
            "provider": "none",
            "model": "none",
            "chunk_count": 0,
            "estimated_sec": 0.0,
        }

    llm_config = resolve_roughcut_llm_config(settings, subtitle_rows=[])
    provider = str(getattr(llm_config, "provider", "") or "").strip().lower()
    model = str(getattr(llm_config, "model", "") or "").strip()
    if not (
        bool(getattr(llm_config, "enabled", False))
        and provider not in {"", "none", "disabled", "off"}
        and model
        and "사용 안함" not in model
    ):
        return {
            "enabled": False,
            "provider": provider or "none",
            "model": model or "none",
            "chunk_count": 0,
            "estimated_sec": 0.0,
        }

    raw_autorun = settings.get("roughcut_run_after_subtitle_generation", None)
    if isinstance(raw_autorun, str):
        autorun_enabled: bool | None = raw_autorun.strip().lower() not in _ROUGHCUT_AUTORUN_FALSE_VALUES
    elif raw_autorun is None:
        autorun_enabled = None
    else:
        autorun_enabled = bool(raw_autorun)
    if autorun_enabled is not True:
        autorun_enabled = bool(autorun_enabled) or bool(editor_roughcut_draft_enabled(settings))
    if not autorun_enabled:
        return {
            "enabled": False,
            "provider": provider,
            "model": model,
            "chunk_count": 0,
            "estimated_sec": 0.0,
        }

    max_context_rows = max(1, _safe_int(getattr(llm_config, "max_context_rows", 80), 80))
    chunk_rows = max(1, min(max_context_rows, _safe_int(getattr(llm_config, "chunk_rows", 12), 12)))
    estimated_rows = max(1, int(round(max(0.0, float(duration_sec or 0.0)) / 6.0)))
    if estimated_rows <= max_context_rows:
        chunk_count = 1
    else:
        chunk_count = max(1, math.ceil(estimated_rows / float(chunk_rows)))
    chunk_count = max(1, min(18, int(chunk_count or 1)))

    model_lower = model.lower()
    base_sec = 6.0
    per_chunk_sec = 5.5
    if provider in {"openai", "google", "gemini"}:
        base_sec = 8.0
        per_chunk_sec = 6.5
    if "codex" in model_lower:
        base_sec = max(base_sec, 10.0)
        per_chunk_sec = max(per_chunk_sec, 8.0)
    if provider == "ollama":
        thread_bonus = max(0, _safe_int(getattr(llm_config, "threads", 1), 1) - 1)
        per_chunk_sec = max(4.0, per_chunk_sec - min(1.5, 0.35 * thread_bonus))

    estimated_sec = max(8.0, min(240.0, base_sec + (float(chunk_count) * per_chunk_sec)))
    return {
        "enabled": True,
        "provider": provider,
        "model": model,
        "chunk_count": chunk_count,
        "estimated_sec": round(float(estimated_sec), 3),
    }


def _speaker_count(settings: dict[str, Any], startup_diagnostic: dict[str, Any] | None) -> int:
    if isinstance(startup_diagnostic, dict):
        speakers = dict(startup_diagnostic.get("speakers") or {})
        count = _safe_int(speakers.get("count"), 0)
        if count > 0:
            return max(1, count)
    if speaker_diarization_auto_enabled(settings):
        return max(1, automatic_speaker_ceiling(settings))
    return max(1, _safe_int(settings.get("max_speakers"), 1))


def _startup_media(startup_diagnostic: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(startup_diagnostic, dict):
        return {}
    media = startup_diagnostic.get("media")
    return dict(media) if isinstance(media, dict) else {}


def _startup_audio_quality_score(startup_diagnostic: dict[str, Any] | None) -> float:
    if not isinstance(startup_diagnostic, dict):
        return 70.0
    audio = dict(startup_diagnostic.get("audio") or {})
    quality = dict(audio.get("quality") or {})
    score = _safe_float(quality.get("score"), 70.0)
    return max(0.0, min(100.0, score))


def _startup_cut_density(startup_diagnostic: dict[str, Any] | None) -> float:
    if not isinstance(startup_diagnostic, dict):
        return 0.0
    density = dict(startup_diagnostic.get("cut_density") or {})
    return max(0.0, _safe_float(density.get("per_minute"), 0.0))


def _disk_cache_enabled(settings: dict[str, Any]) -> bool:
    return any(
        (
            _safe_bool(settings.get("cut_boundary_cache_enabled"), True),
            _safe_bool(settings.get("vad_detection_cache_enabled"), True),
            _safe_bool(settings.get("stt_persistent_runtime_reuse_enabled"), True),
            _safe_int(settings.get("prefetch_ahead"), 0) > 0,
        )
    )


def _cut_boundary_cache_state(
    target_file: str,
    settings: dict[str, Any],
    runtime_flags: dict[str, Any],
) -> str:
    explicit = _safe_str(runtime_flags.get("cut_boundary_cache_state"), "")
    if explicit:
        return explicit
    if not _safe_bool(settings.get("cut_boundary_cache_enabled"), True):
        return "disabled"
    if not target_file:
        return "cold"
    try:
        from core.pipeline.cut_boundary_cache import cut_boundary_cache_path_for_start

        cache_path = cut_boundary_cache_path_for_start([target_file], settings)
        return "warm" if cache_path and os.path.exists(cache_path) else "cold"
    except Exception:
        return "cold"


def _vad_cache_state(runtime_flags: dict[str, Any], settings: dict[str, Any]) -> str:
    explicit = _safe_str(runtime_flags.get("vad_cache_state"), "")
    if explicit:
        return explicit
    if not _safe_bool(settings.get("vad_detection_cache_enabled"), True):
        return "disabled"
    return "cold"


def _speaker_cache_state(target_file: str, settings: dict[str, Any]) -> str:
    if not speaker_diarization_auto_enabled(settings):
        return "disabled"
    stem, _ = os.path.splitext(str(target_file or ""))
    return "warm" if stem and os.path.exists(f"{stem}_speaker_cache.json") else "cold"


def _likely_warm_start(
    settings: dict[str, Any],
    queue_index: int,
    runtime_flags: dict[str, Any],
) -> bool:
    if "likely_warm_start" in runtime_flags:
        return _safe_bool(runtime_flags.get("likely_warm_start"))
    if _safe_bool(runtime_flags.get("prefetch_audio_hit")):
        return True
    return bool(
        queue_index > 0
        and (
            _safe_int(settings.get("prefetch_ahead"), 0) > 0
            or _safe_bool(settings.get("stt_persistent_runtime_reuse_enabled"), True)
        )
    )


def _disk_cache_state(
    target_file: str,
    settings: dict[str, Any],
    queue_index: int,
    total_files: int,
    runtime_flags: dict[str, Any],
) -> str:
    explicit = _safe_str(runtime_flags.get("cache_state"), "")
    if explicit:
        return explicit
    if not _disk_cache_enabled(settings):
        return "disabled"
    if _likely_warm_start(settings, queue_index, runtime_flags):
        return "warm"
    cut_state = _cut_boundary_cache_state(target_file, settings, runtime_flags)
    if cut_state == "warm":
        return "warm"
    speaker_state = _speaker_cache_state(target_file, settings)
    if speaker_state == "warm":
        return "warm"
    if total_files > 1 and queue_index > 0:
        return "warm"
    return "cold"


def _cache_score(cache_state: str, runtime_flags: dict[str, Any]) -> float:
    score = {"disabled": 0.0, "cold": 0.45, "warm": 0.85}.get(_safe_str(cache_state, "cold"), 0.45)
    if _safe_bool(runtime_flags.get("prefetch_audio_hit")):
        score += 0.10
    if _safe_bool(runtime_flags.get("likely_warm_start")):
        score += 0.10
    return max(0.0, min(1.0, score))


def _probe_media_if_needed(target_file: str, media_info: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(media_info, dict) and media_info:
        return dict(media_info)
    if not target_file:
        return {}
    try:
        from core.media_info import probe_media

        return dict(probe_media(target_file))
    except Exception:
        return {}


def _variant_key(model_key: str, variant: dict[str, Any], runtime: dict[str, Any]) -> str:
    return "|".join(
        [
            f"mode={_safe_str(variant.get('mode'), 'balanced')}",
            f"preset={_safe_str(variant.get('stt_quality_preset'), 'balanced')}",
            f"model={_safe_str(variant.get('stt_primary'), 'unknown')}",
            f"model2={_safe_str(variant.get('stt_secondary'))}",
            f"ensemble={1 if _safe_bool(variant.get('stt_ensemble_enabled')) else 0}",
            f"llmProvider={_safe_str(variant.get('llm_provider'), 'none')}",
            f"llmModel={_safe_str(variant.get('llm_model'), 'none')}",
            f"vad={_safe_str(variant.get('selected_vad'), 'none')}",
            f"audio={_safe_str(variant.get('selected_audio_ai'), 'none')}",
            f"dia={1 if _safe_bool(variant.get('diarization_enabled')) else 0}",
            f"cache={_safe_str(runtime.get('cache_state'), 'cold')}",
            f"modelKey={_safe_str(model_key)}",
        ]
    )


def build_runtime_eta_payload(
    model_key: str,
    video_duration_sec: float,
    *,
    settings: dict[str, Any] | None = None,
    media_info: dict[str, Any] | None = None,
    startup_diagnostic: dict[str, Any] | None = None,
    target_file: str | None = None,
    queue_index: int = 0,
    total_files: int = 1,
    runtime_flags: dict[str, Any] | None = None,
    processing_time_sec: float | None = None,
    store_path: str | None = None,
) -> dict[str, Any]:
    runtime_flags = dict(runtime_flags or {})
    s = dict(settings or load_settings())
    media = _probe_media_if_needed(str(target_file or ""), media_info)
    startup_media = _startup_media(startup_diagnostic)
    duration_sec = max(
        0.0,
        _safe_float(video_duration_sec, 0.0),
        _safe_float(startup_media.get("duration_sec"), 0.0),
        _safe_float(media.get("duration"), 0.0),
    )
    fps = max(_safe_float(startup_media.get("fps"), 0.0), _safe_float(media.get("fps"), 0.0))
    width = max(_safe_int(startup_media.get("width"), 0), _safe_int(media.get("width"), 0))
    height = max(_safe_int(startup_media.get("height"), 0), _safe_int(media.get("height"), 0))
    mode = _normalized_mode(s)
    llm_provider = _safe_str(s.get("selected_llm_provider"), "ollama")
    llm_model = _safe_str(s.get("selected_model"), "기본")
    stt_secondary = _safe_str(s.get("selected_whisper_model_secondary")) if _safe_bool(s.get("stt_ensemble_enabled")) else ""
    target_file = os.path.abspath(str(target_file or "")) if target_file else ""
    cache_state = _disk_cache_state(target_file, s, queue_index, total_files, runtime_flags)
    cut_boundary_state = _cut_boundary_cache_state(target_file, s, runtime_flags)
    vad_state = _vad_cache_state(runtime_flags, s)
    likely_warm_start = _likely_warm_start(s, queue_index, runtime_flags)
    roughcut_eta = _roughcut_llm_eta_details(s, duration_sec)
    payload: dict[str, Any] = {
        "store_path": history_store_path(store_path),
        "schema": ETA_HISTORY_SCHEMA,
        "model_key": _safe_str(model_key),
        "target_file": target_file,
        "variant": {
            "mode": mode,
            "stt_quality_preset": mode,
            "stt_primary": _safe_str(s.get("selected_whisper_model"), "기본"),
            "stt_secondary": stt_secondary,
            "stt_ensemble_enabled": _safe_bool(s.get("stt_ensemble_enabled")),
            "llm_provider": "none" if _llm_disabled(llm_model, llm_provider) else llm_provider,
            "llm_model": "none" if _llm_disabled(llm_model, llm_provider) else llm_model,
            "diarization_enabled": speaker_diarization_auto_enabled(s),
            "max_speakers": automatic_speaker_ceiling(s) if speaker_diarization_auto_enabled(s) else max(1, _safe_int(s.get("max_speakers"), 1)),
            "selected_vad": _safe_str(s.get("selected_vad"), "none"),
            "selected_audio_ai": _safe_str(s.get("selected_audio_ai"), "none"),
        },
        "media": {
            "duration_sec": duration_sec,
            "fps": fps,
            "width": width,
            "height": height,
            "pixel_count": max(0, width) * max(0, height),
            "audio_quality_score": _startup_audio_quality_score(startup_diagnostic),
            "cut_density_per_min": _startup_cut_density(startup_diagnostic),
            "speaker_hint": _speaker_count(s, startup_diagnostic),
            "is_audio_only": width <= 0 or height <= 0,
        },
        "runtime": {
            "queue_index": max(0, _safe_int(queue_index, 0)),
            "total_files": max(1, _safe_int(total_files, 1)),
            "prefetch_audio_hit": _safe_bool(runtime_flags.get("prefetch_audio_hit")),
            "cut_boundary_cache_enabled": _safe_bool(s.get("cut_boundary_cache_enabled"), True),
            "vad_cache_enabled": _safe_bool(s.get("vad_detection_cache_enabled"), True),
            "stt_runtime_reuse_enabled": _safe_bool(s.get("stt_persistent_runtime_reuse_enabled"), True),
            "prefetch_ahead": max(0, _safe_int(s.get("prefetch_ahead"), 0)),
            "auto_audio_tune_enabled": not _safe_bool(s.get("audio_preset_auto_disabled"), False),
            "cache_state": cache_state,
            "cut_boundary_cache_state": cut_boundary_state,
            "vad_cache_state": vad_state,
            "speaker_cache_state": _speaker_cache_state(target_file, s),
            "likely_warm_start": likely_warm_start,
            "cache_score": _cache_score(cache_state, runtime_flags),
            "roughcut_post_generation_enabled": bool(roughcut_eta.get("enabled", False)),
            "roughcut_estimated_sec": max(0.0, _safe_float(roughcut_eta.get("estimated_sec"), 0.0)),
            "roughcut_chunk_count": max(0, _safe_int(roughcut_eta.get("chunk_count"), 0)),
        },
    }
    if roughcut_eta.get("enabled"):
        payload["variant"]["roughcut_llm_provider"] = _safe_str(roughcut_eta.get("provider"), "none")
        payload["variant"]["roughcut_llm_model"] = _safe_str(roughcut_eta.get("model"), "none")
    if processing_time_sec is not None:
        payload["processing_time_sec"] = max(0.0, _safe_float(processing_time_sec, 0.0))
    return payload


def _fallback_predict(payload: dict[str, Any]) -> float:
    path = _safe_str(payload.get("store_path"))
    data = _read_history_store(path)
    duration_sec = max(0.0, _safe_float((payload.get("media") or {}).get("duration_sec"), 0.0))
    if duration_sec <= 0:
        return -1.0
    variant = dict(payload.get("variant") or {})
    runtime = dict(payload.get("runtime") or {})
    variant_key = _variant_key(_safe_str(payload.get("model_key")), variant, runtime)
    if isinstance(data, dict):
        if data.get("schema") == ETA_HISTORY_SCHEMA:
            variants = dict(data.get("variants") or {})
            summary = dict(variants.get(variant_key) or {})
            ratio = _safe_float(summary.get("weighted_speed_ratio"), 0.0)
            if ratio > 0.0:
                return max(1.0, duration_sec * ratio + _safe_float((data.get("weights") or {}).get("fixed_overhead_sec"), 10.0))
            runs = list(data.get("runs") or [])
            ratios = [
                _safe_float(((row or {}).get("metrics") or {}).get("speed_ratio"), 0.0)
                for row in runs
                if isinstance(row, dict)
            ]
            ratios = [row for row in ratios if row > 0.0]
            if ratios:
                ratio = sum(ratios[-12:]) / float(len(ratios[-12:]))
                return max(1.0, duration_sec * ratio + 10.0)
        legacy = dict(data.get(_safe_str(payload.get("model_key"))) or {})
        total_vid = _safe_float(legacy.get("total_video_duration"), 0.0)
        total_proc = _safe_float(legacy.get("total_processing_time"), 0.0)
        if total_vid > 0.0 and total_proc > 0.0:
            return duration_sec * (total_proc / total_vid)
    return -1.0


def _fallback_record(payload: dict[str, Any]) -> None:
    path = _safe_str(payload.get("store_path"))
    if not path:
        return
    data = _read_history_store(path)
    if not isinstance(data, dict) or data.get("schema") != ETA_HISTORY_SCHEMA:
        data = {
            "schema": ETA_HISTORY_SCHEMA,
            "weights": {"fixed_overhead_sec": 10.0},
            "variants": {},
            "runs": [],
        }
    variant = dict(payload.get("variant") or {})
    runtime = dict(payload.get("runtime") or {})
    metrics = {
        "processing_sec": max(0.0, _safe_float(payload.get("processing_time_sec"), 0.0)),
        "speed_ratio": 0.0,
    }
    media = dict(payload.get("media") or {})
    duration_sec = max(0.0, _safe_float(media.get("duration_sec"), 0.0))
    if duration_sec > 0.0:
        metrics["speed_ratio"] = metrics["processing_sec"] / duration_sec
    variant_key = _variant_key(_safe_str(payload.get("model_key")), variant, runtime)
    runs = list(data.get("runs") or [])
    runs.append(
        {
            "variant_key": variant_key,
            "model_key": _safe_str(payload.get("model_key")),
            "variant": variant,
            "media": media,
            "runtime": runtime,
            "metrics": metrics,
        }
    )
    data["runs"] = runs[-240:]
    variants = dict(data.get("variants") or {})
    summary = dict(variants.get(variant_key) or {})
    count = max(0, _safe_int(summary.get("count"), 0)) + 1
    last_ratio = metrics["speed_ratio"]
    ema = _safe_float(summary.get("ema_speed_ratio"), 0.0)
    ema = last_ratio if count <= 1 or ema <= 0.0 else (0.35 * last_ratio + 0.65 * ema)
    variants[variant_key] = {
        "count": count,
        "weighted_speed_ratio": (ema * 0.6) + (last_ratio * 0.4),
        "ema_speed_ratio": ema,
        "recent_speed_ratio": last_ratio,
        "last_processing_sec": metrics["processing_sec"],
    }
    data["variants"] = variants
    _write_history_store(path, data)


def _native_predict(payload: dict[str, Any]) -> float:
    decoded = request_native_core_task("runtime_eta_predict", payload)
    if isinstance(decoded, dict):
        predicted = _safe_float(decoded.get("predicted_processing_sec"), -1.0)
        if predicted > 0.0:
            return predicted
    return -1.0


def _native_record(payload: dict[str, Any]) -> bool:
    decoded = request_native_core_task("runtime_eta_record", payload)
    return isinstance(decoded, dict) and not decoded.get("error")


def get_expected_time(
    model_key: str,
    video_duration_sec: float,
    *,
    settings: dict[str, Any] | None = None,
    media_info: dict[str, Any] | None = None,
    startup_diagnostic: dict[str, Any] | None = None,
    target_file: str | None = None,
    queue_index: int = 0,
    total_files: int = 1,
    runtime_flags: dict[str, Any] | None = None,
    store_path: str | None = None,
) -> float:
    payload = build_runtime_eta_payload(
        model_key,
        video_duration_sec,
        settings=settings,
        media_info=media_info,
        startup_diagnostic=startup_diagnostic,
        target_file=target_file,
        queue_index=queue_index,
        total_files=total_files,
        runtime_flags=runtime_flags,
        store_path=store_path,
    )
    roughcut_estimated_sec = max(0.0, _safe_float((payload.get("runtime") or {}).get("roughcut_estimated_sec"), 0.0))
    predicted = _native_predict(payload)
    if predicted > 0.0:
        return predicted + roughcut_estimated_sec
    predicted = _fallback_predict(payload)
    if predicted > 0.0:
        return predicted + roughcut_estimated_sec
    return predicted


def add_history(
    model_key: str,
    video_duration_sec: float,
    processing_time_sec: float,
    *,
    settings: dict[str, Any] | None = None,
    media_info: dict[str, Any] | None = None,
    startup_diagnostic: dict[str, Any] | None = None,
    target_file: str | None = None,
    queue_index: int = 0,
    total_files: int = 1,
    runtime_flags: dict[str, Any] | None = None,
    store_path: str | None = None,
) -> None:
    if _safe_float(video_duration_sec, 0.0) <= 0.0 or _safe_float(processing_time_sec, 0.0) <= 0.0:
        return
    payload = build_runtime_eta_payload(
        model_key,
        video_duration_sec,
        settings=settings,
        media_info=media_info,
        startup_diagnostic=startup_diagnostic,
        target_file=target_file,
        queue_index=queue_index,
        total_files=total_files,
        runtime_flags=runtime_flags,
        processing_time_sec=processing_time_sec,
        store_path=store_path,
    )
    if _native_record(payload):
        return
    _fallback_record(payload)


__all__ = [
    "ETA_HISTORY_SCHEMA",
    "add_history",
    "build_runtime_eta_payload",
    "get_expected_time",
    "history_store_path",
]
