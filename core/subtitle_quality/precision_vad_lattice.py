"""Precision voice-boundary lattice construction for subtitle refinement."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.runtime.logger import get_logger
from core.subtitle_quality.vad_alignment_checker import normalize_vad_segments


VadDetector = Callable[[str, str, dict[str, Any]], list[dict[str, Any]]]


@dataclass(frozen=True)
class PrecisionVadLatticeResult:
    segments: tuple[dict[str, Any], ...]
    source_counts: dict[str, int]
    audio_paths: dict[str, str]
    report: dict[str, Any]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _speech_like(row: dict[str, Any]) -> bool:
    raw = " ".join(
        str(row.get(key, "") or "").strip().lower()
        for key in ("kind", "type", "label", "category", "vad_type", "source")
    )
    if any(token in raw for token in ("silence", "idle", "gap", "noise", "non_speech", "대기", "무음", "노이즈")):
        return False
    return True


def _prepare_source_rows(rows: Any, *, source: str, weight: float) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for row in normalize_vad_segments(rows or []):
        if not _speech_like(row):
            continue
        item = dict(row)
        item["source"] = str(source or item.get("source") or "unknown")
        item["_precision_source"] = str(source or item.get("source") or "unknown")
        item["_precision_weight"] = max(0.05, min(1.25, _as_float(weight, 0.5)))
        prepared.append(item)
    return prepared


def build_precision_voice_lattice(
    source_groups: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    merge_gap_sec: float = 0.08,
    boundary_pad_sec: float = 0.015,
) -> list[dict[str, Any]]:
    """Merge VAD/voice rows from multiple sources into deterministic speech spans."""
    candidates: list[dict[str, Any]] = []
    for group in list(source_groups or []):
        if not isinstance(group, dict):
            continue
        source = str(group.get("source") or "unknown")
        weight = _as_float(group.get("weight"), 0.5)
        candidates.extend(_prepare_source_rows(group.get("rows"), source=source, weight=weight))
    candidates.sort(key=lambda item: (_as_float(item.get("start")), _as_float(item.get("end"))))
    if not candidates:
        return []

    gap = max(0.0, _as_float(merge_gap_sec, 0.08))
    pad = max(0.0, _as_float(boundary_pad_sec, 0.015))
    clusters: list[list[dict[str, Any]]] = []
    for row in candidates:
        if not clusters:
            clusters.append([row])
            continue
        cluster_end = max(_as_float(item.get("end")) for item in clusters[-1])
        if _as_float(row.get("start")) <= cluster_end + gap:
            clusters[-1].append(row)
        else:
            clusters.append([row])

    lattice: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters):
        weights = [max(0.05, _as_float(item.get("_precision_weight"), 0.5)) for item in cluster]
        total_weight = max(0.001, sum(weights))
        starts = [_as_float(item.get("start")) for item in cluster]
        ends = [_as_float(item.get("end")) for item in cluster]
        weighted_start = sum(start * weight for start, weight in zip(starts, weights)) / total_weight
        weighted_end = sum(end * weight for end, weight in zip(ends, weights)) / total_weight
        coverage_start = min(starts)
        coverage_end = max(ends)
        source_names = sorted({str(item.get("_precision_source") or item.get("source") or "unknown") for item in cluster})
        source_count = len(source_names)
        max_weight = max(weights or [0.0])
        confidence = min(1.0, max_weight * 0.82 + max(0, source_count - 1) * 0.08 + min(total_weight, 3.0) * 0.04)

        if source_count <= 1:
            start = coverage_start
            end = coverage_end
        else:
            start = max(0.0, min(weighted_start, coverage_end))
            end = max(start, max(weighted_end, coverage_start))
            start = max(0.0, min(start, coverage_start + 0.18))
            end = max(end, coverage_end - 0.18)

        start = max(0.0, start - pad)
        end = max(start + 0.03, end + pad)
        lattice.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "source": "precision_voice_lattice",
                "kind": "speech",
                "precision_lattice": True,
                "precision_lattice_index": index,
                "confidence": round(confidence, 4),
                "source_count": source_count,
                "vad_sources": source_names,
                "source_span": {"start": round(coverage_start, 3), "end": round(coverage_end, 3)},
            }
        )
    return lattice


def _existing_path(value: Any) -> str:
    path = os.path.abspath(os.path.expanduser(str(value or "")))
    return path if path and os.path.exists(path) else ""


def _extract_raw_precision_wav(media_path: str, raw_wav: str) -> str:
    media_path = _existing_path(media_path)
    if not media_path or not raw_wav:
        return ""
    if os.path.exists(raw_wav) and os.path.getsize(raw_wav) > 1024:
        return raw_wav
    os.makedirs(os.path.dirname(os.path.abspath(raw_wav)), exist_ok=True)
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
        "-acodec",
        "pcm_s16le",
        raw_wav,
    ]
    subprocess.run(cmd, check=True, timeout=240, **hidden_subprocess_kwargs())
    return raw_wav if os.path.exists(raw_wav) and os.path.getsize(raw_wav) > 1024 else ""


def resolve_precision_audio_paths(
    media_path: str,
    settings: dict[str, Any] | None = None,
    *,
    audio_paths: dict[str, Any] | None = None,
    video_processor: Any = None,
    prepare_audio: bool = True,
) -> dict[str, str]:
    """Find or prepare measured-filter and raw audio paths for precision analysis."""
    paths = dict(audio_paths or {})
    for owner in (video_processor,):
        if owner is None:
            continue
        paths.setdefault("measured_audio_path", getattr(owner, "last_cleaned_wav", ""))
        paths.setdefault("raw_audio_path", getattr(owner, "last_raw_wav", ""))
        last_audio_paths = getattr(owner, "last_audio_paths", None)
        if isinstance(last_audio_paths, dict):
            paths.setdefault("cleaned_wav", last_audio_paths.get("cleaned_wav"))
            paths.setdefault("raw_wav", last_audio_paths.get("raw_wav"))

    measured = _existing_path(paths.get("measured_audio_path") or paths.get("cleaned_wav"))
    raw = _existing_path(paths.get("raw_audio_path") or paths.get("raw_wav"))
    media = _existing_path(media_path)

    processor = video_processor
    if media and (not measured or not raw):
        try:
            from core.audio.media_processor import VideoProcessor

            processor = processor or VideoProcessor()
            work_paths = processor._audio_work_paths(media)
            measured = measured or _existing_path(work_paths.get("cleaned_wav"))
            raw = raw or _existing_path(work_paths.get("raw_wav"))
            paths.setdefault("work_dir", str(work_paths.get("work_dir") or ""))
            paths.setdefault("cleaned_wav", str(work_paths.get("cleaned_wav") or ""))
            paths.setdefault("raw_wav", str(work_paths.get("raw_wav") or ""))
        except Exception:
            processor = video_processor

    if media and prepare_audio and not measured:
        try:
            from core.audio.media_processor import VideoProcessor

            prepare_processor = VideoProcessor()
            prepare_processor.extract_audio(media, prefetch_only=True)
            processor = prepare_processor
            measured = _existing_path(getattr(prepare_processor, "last_cleaned_wav", ""))
            raw = raw or _existing_path(getattr(prepare_processor, "last_raw_wav", ""))
        except Exception as exc:
            get_logger().log(f"⚠️ 정밀 VAD 오디오 준비 실패: {exc}")

    if media and prepare_audio and not raw:
        raw_target = str(paths.get("raw_wav") or "")
        if not raw_target and processor is not None:
            try:
                raw_target = str(processor._audio_work_paths(media).get("raw_wav") or "")
            except Exception:
                raw_target = ""
        if raw_target:
            try:
                raw = _extract_raw_precision_wav(media, raw_target)
            except Exception as exc:
                get_logger().log(f"⚠️ 정밀 VAD raw audio 준비 실패: {exc}")

    out = {
        "measured_audio_path": measured,
        "raw_audio_path": raw,
    }
    for key in ("work_dir", "cleaned_wav", "raw_wav"):
        if paths.get(key):
            out[key] = str(paths.get(key) or "")
    return out


def _default_vad_detector(wav_path: str, provider: str, settings: dict[str, Any]) -> list[dict[str, Any]]:
    from core.audio.media_processor import VideoProcessor

    processor = VideoProcessor()
    return processor._detect_vad_timestamps(
        wav_path,
        provider,
        dict(settings or {}),
        for_post_stt_align=True,
    )


def build_precision_vad_lattice_for_media(
    media_path: str,
    *,
    settings: dict[str, Any] | None = None,
    existing_vad_segments: list[dict[str, Any]] | None = None,
    existing_voice_activity_segments: list[dict[str, Any]] | None = None,
    audio_paths: dict[str, Any] | None = None,
    detector: VadDetector | None = None,
    prepare_audio: bool = True,
    video_processor: Any = None,
) -> PrecisionVadLatticeResult:
    """Build the precision speech lattice from measured audio, raw audio, and existing UI state."""
    effective_settings = dict(settings or {})
    resolved_paths = resolve_precision_audio_paths(
        media_path,
        effective_settings,
        audio_paths=audio_paths,
        video_processor=video_processor,
        prepare_audio=prepare_audio,
    )
    if detector is None:
        try:
            from core.audio.media_processor import VideoProcessor

            detector_processor = VideoProcessor()

            def detector(wav_path: str, provider: str, detector_settings: dict[str, Any]) -> list[dict[str, Any]]:
                return detector_processor._detect_vad_timestamps(
                    wav_path,
                    provider,
                    dict(detector_settings or {}),
                    for_post_stt_align=True,
                )
        except Exception:
            detector = _default_vad_detector
    source_groups: list[dict[str, Any]] = [
        {"source": "existing_vad", "weight": 0.7, "rows": existing_vad_segments or []},
        {"source": "existing_voice_activity", "weight": 0.78, "rows": existing_voice_activity_segments or []},
    ]
    source_counts: dict[str, int] = {
        "existing_vad": len(normalize_vad_segments(existing_vad_segments or [])),
        "existing_voice_activity": len(normalize_vad_segments(existing_voice_activity_segments or [])),
    }

    detection_plan = (
        ("measured_audio", resolved_paths.get("measured_audio_path", ""), 1.0),
        ("raw_audio", resolved_paths.get("raw_audio_path", ""), 0.86),
    )
    providers = ("silero", "ten_vad")
    for audio_label, wav_path, base_weight in detection_plan:
        if not wav_path or not os.path.exists(wav_path):
            continue
        for provider in providers:
            source = f"{audio_label}:{provider}"
            try:
                rows = detector(wav_path, provider, effective_settings)
            except Exception as exc:
                get_logger().log(f"⚠️ 정밀 VAD {source} 실패: {exc}")
                rows = []
            rows = normalize_vad_segments(rows or [])
            source_counts[source] = len(rows)
            if rows:
                weight = base_weight if provider == "silero" else max(0.7, base_weight - 0.05)
                source_groups.append({"source": source, "weight": weight, "rows": rows})

    lattice = build_precision_voice_lattice(
        source_groups,
        merge_gap_sec=_as_float(effective_settings.get("precision_vad_lattice_merge_gap_sec"), 0.08),
        boundary_pad_sec=_as_float(effective_settings.get("precision_vad_lattice_pad_sec"), 0.015),
    )
    report = {
        "lattice_count": len(lattice),
        "source_counts": dict(source_counts),
        "audio_paths": dict(resolved_paths),
        "detectors": providers,
        "schema": "ai_subtitle_studio.precision_vad_lattice.v1",
    }
    return PrecisionVadLatticeResult(
        segments=tuple(lattice),
        source_counts=dict(source_counts),
        audio_paths=dict(resolved_paths),
        report=report,
    )


__all__ = [
    "PrecisionVadLatticeResult",
    "build_precision_vad_lattice_for_media",
    "build_precision_voice_lattice",
    "resolve_precision_audio_paths",
]
