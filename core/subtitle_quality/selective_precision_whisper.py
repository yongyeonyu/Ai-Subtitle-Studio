"""Selective precision Whisper pass guarded by deterministic evidence checks."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Callable

from core.engine.subtitle_stt_candidate_helpers import _stt_candidate_similarity
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.runtime.logger import get_logger
from core.subtitle_quality.hallucination_detector import HALLUCINATION_PHRASES
from core.subtitle_quality.recheck_engine import RECHECK_FLAGS
from core.subtitle_quality.vad_alignment_checker import normalize_vad_segments, vad_alignment_info


PrecisionTranscriber = Callable[..., Any]


@dataclass(frozen=True)
class SelectivePrecisionWhisperResult:
    segments: tuple[dict[str, Any], ...]
    report: dict[str, Any]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _compact(text: Any) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _quality_flags(segment: dict[str, Any]) -> set[str]:
    quality = dict(segment.get("quality") or {})
    flags = set(str(flag) for flag in list(quality.get("flags") or ()))
    for key in ("_uncertainty_bucket", "score_color", "stt_score_color"):
        value = str(segment.get(key, "") or "").strip().lower()
        if value in {"red", "yellow", "gray", "grey"}:
            flags.add(f"{key}:{value}")
    return flags


def _overlapping_lattice(start: float, end: float, lattice: list[dict[str, Any]], *, pad_sec: float = 0.18) -> list[dict[str, Any]]:
    lower = max(0.0, start - max(0.0, pad_sec))
    upper = end + max(0.0, pad_sec)
    return [
        row
        for row in lattice
        if _as_float(row.get("end")) > lower and _as_float(row.get("start")) < upper
    ]


def _target_span_from_lattice(segment: dict[str, Any], lattice: list[dict[str, Any]], *, pad_sec: float) -> tuple[float, float, list[dict[str, Any]]]:
    start = max(0.0, _as_float(segment.get("start")))
    end = max(start, _as_float(segment.get("end"), start))
    rows = _overlapping_lattice(start, end, lattice, pad_sec=pad_sec)
    if not rows:
        return max(0.0, start - pad_sec), end + pad_sec, []
    lattice_start = min(_as_float(row.get("start")) for row in rows)
    lattice_end = max(_as_float(row.get("end")) for row in rows)
    return max(0.0, min(start, lattice_start) - pad_sec), max(end, lattice_end) + pad_sec, rows


def _edge_uncertain_against_lattice(segment: dict[str, Any], rows: list[dict[str, Any]], *, max_edge_delta_sec: float) -> bool:
    if not rows:
        return True
    if len(rows) > 1:
        return True
    row = rows[0]
    start = max(0.0, _as_float(segment.get("start")))
    end = max(start, _as_float(segment.get("end"), start))
    return bool(
        abs(start - _as_float(row.get("start"))) > max_edge_delta_sec
        or abs(end - _as_float(row.get("end"))) > max_edge_delta_sec
    )


def select_precision_whisper_targets(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    lattice_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    settings = dict(settings or {})
    lattice = normalize_vad_segments(lattice_segments or [])
    if not lattice:
        return []
    max_targets = max(0, _as_int(settings.get("precision_whisper_max_segments"), 12))
    max_total_audio = max(0.0, _as_float(settings.get("precision_whisper_max_audio_sec"), 90.0))
    pad = max(0.05, _as_float(settings.get("precision_whisper_context_pad_sec"), 0.22))
    min_vad_ratio = max(0.0, min(1.0, _as_float(settings.get("precision_whisper_uncertain_vad_ratio"), 0.48)))
    max_edge_delta = max(0.03, _as_float(settings.get("precision_whisper_edge_uncertain_sec"), 0.22))
    targets: list[dict[str, Any]] = []
    total_audio = 0.0

    for list_index, segment in enumerate(segments or []):
        if not isinstance(segment, dict) or segment.get("is_gap"):
            continue
        text = str(segment.get("text", "") or "").strip()
        if not text:
            continue
        info = vad_alignment_info(segment, lattice)
        ratio = info.get("vad_overlap_ratio")
        flags = _quality_flags(segment)
        has_timing_words = bool(segment.get("words"))
        low_quality = bool(flags.intersection(RECHECK_FLAGS)) or any(flag.endswith(":red") or flag.endswith(":gray") for flag in flags)
        ratio_uncertain = ratio is None or float(ratio) < min_vad_ratio
        recheck_start, recheck_end, rows = _target_span_from_lattice(segment, lattice, pad_sec=pad)
        edge_uncertain = _edge_uncertain_against_lattice(segment, rows, max_edge_delta_sec=max_edge_delta)
        no_word_timing = not has_timing_words and edge_uncertain and len(_compact(text)) >= 3
        if not (ratio_uncertain or low_quality or no_word_timing):
            continue

        if recheck_end <= recheck_start:
            continue
        span = recheck_end - recheck_start
        if max_total_audio and total_audio + span > max_total_audio:
            continue
        item = dict(segment)
        item["_list_index"] = list_index
        item["segment_index"] = int(segment.get("line", list_index) if segment.get("line") is not None else list_index)
        item["recheck_start"] = round(recheck_start, 3)
        item["recheck_end"] = round(recheck_end, 3)
        item["recheck_reason"] = "precision_uncertain_vad" if ratio_uncertain else "precision_quality_flag"
        item["vad_overlap_ratio"] = ratio
        item["precision_lattice_refs"] = [
            {
                "start": row.get("start"),
                "end": row.get("end"),
                "confidence": row.get("confidence"),
                "vad_sources": list(row.get("vad_sources") or []),
            }
            for row in rows
        ]
        targets.append(item)
        total_audio += span
        if max_targets and len(targets) >= max_targets:
            break
    return targets


def _candidate_text(candidate: Any) -> str:
    if isinstance(candidate, dict):
        return str(candidate.get("text") or candidate.get("output") or "").strip()
    return str(getattr(candidate, "text", candidate) or "").strip()


def _reference_texts(segment: dict[str, Any]) -> list[str]:
    refs = [str(segment.get("text", "") or "").strip()]
    for candidate in list(segment.get("stt_candidates") or []):
        if isinstance(candidate, dict):
            text = str(candidate.get("text") or candidate.get("output") or "").strip()
            if text:
                refs.append(text)
    return [text for text in refs if text]


def precision_whisper_deterministic_judge(
    segment: dict[str, Any],
    candidate: dict[str, Any],
    lattice_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    text = _candidate_text(candidate)
    compact = _compact(text)
    if not compact:
        return {"accepted": False, "reason": "empty_precision_whisper"}
    lowered = text.lower()
    if any(str(phrase).lower() in lowered for phrase in HALLUCINATION_PHRASES):
        return {"accepted": False, "reason": "known_hallucination_phrase", "text": text}

    refs = _reference_texts(segment)
    best_similarity = max((_stt_candidate_similarity(text, ref) for ref in refs), default=0.0)
    min_similarity = max(0.0, min(1.0, _as_float(settings.get("precision_whisper_min_similarity"), 0.74)))
    if len(compact) <= 8:
        min_similarity = min(min_similarity, max(0.62, _as_float(settings.get("precision_whisper_short_min_similarity"), 0.66)))
    if best_similarity < min_similarity:
        return {
            "accepted": False,
            "reason": "text_too_far_from_existing_or_stt",
            "similarity": round(best_similarity, 4),
            "min_similarity": round(min_similarity, 4),
            "text": text,
        }

    ref_len = max(1, len(_compact(refs[0] if refs else "")))
    length_ratio = len(compact) / ref_len
    min_ratio = max(0.1, _as_float(settings.get("precision_whisper_min_length_ratio"), 0.45))
    max_ratio = max(min_ratio, _as_float(settings.get("precision_whisper_max_length_ratio"), 1.85))
    if length_ratio < min_ratio or length_ratio > max_ratio:
        return {
            "accepted": False,
            "reason": "length_ratio_out_of_range",
            "length_ratio": round(length_ratio, 4),
            "text": text,
        }

    start = _as_float(candidate.get("start"), _as_float(segment.get("start")))
    end = max(start, _as_float(candidate.get("end"), _as_float(segment.get("end"), start)))
    info = vad_alignment_info({"start": start, "end": end}, lattice_segments)
    ratio = info.get("vad_overlap_ratio")
    min_vad_ratio = max(0.0, min(1.0, _as_float(settings.get("precision_whisper_min_vad_overlap"), 0.35)))
    if ratio is None or float(ratio) < min_vad_ratio:
        return {
            "accepted": False,
            "reason": "candidate_outside_precision_vad",
            "vad_overlap_ratio": ratio,
            "min_vad_overlap": round(min_vad_ratio, 4),
            "text": text,
        }
    return {
        "accepted": True,
        "reason": "deterministic_precision_whisper_judge",
        "similarity": round(best_similarity, 4),
        "vad_overlap_ratio": round(float(ratio), 4),
        "text": text,
    }


def _extract_precision_clip(source_path: str, start_sec: float, end_sec: float, out_wav: str) -> str:
    if not source_path or not os.path.exists(source_path):
        return ""
    duration = max(0.05, end_sec - start_sec)
    os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
    cmd = [
        ffmpeg_binary(),
        "-y",
        "-nostdin",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, start_sec):.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        source_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        out_wav,
    ]
    subprocess.run(cmd, check=True, timeout=120, **hidden_subprocess_kwargs())
    return out_wav if os.path.exists(out_wav) and os.path.getsize(out_wav) > 1024 else ""


def _default_precision_transcriber(clip_path: str, target: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    from core.audio.live_stt import transcribe_wav_file

    result = transcribe_wav_file(clip_path, profile="quality", settings=settings)
    return {
        "text": getattr(result, "text", ""),
        "engine": getattr(result, "engine", "local-whisper"),
        "model": getattr(result, "model", ""),
        "elapsed": getattr(result, "elapsed", 0.0),
    }


def _call_transcriber(transcriber: PrecisionTranscriber, clip_path: str, target: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    try:
        result = transcriber(clip_path, target, settings)
    except TypeError:
        result = transcriber(clip_path)
    if isinstance(result, dict):
        return dict(result)
    return {
        "text": getattr(result, "text", result),
        "engine": getattr(result, "engine", ""),
        "model": getattr(result, "model", ""),
    }


def _apply_precision_candidate(segment: dict[str, Any], candidate: dict[str, Any], judge: dict[str, Any]) -> dict[str, Any]:
    out = dict(segment)
    old_text = str(out.get("text", "") or "").strip()
    new_text = _candidate_text(candidate)
    if new_text:
        out["text"] = new_text
    out["start"] = round(_as_float(candidate.get("start"), _as_float(out.get("start"))), 3)
    out["end"] = round(max(_as_float(out.get("start")), _as_float(candidate.get("end"), _as_float(out.get("end")))), 3)
    stt_candidates = [dict(row) for row in list(out.get("stt_candidates") or []) if isinstance(row, dict)]
    stt_candidates.append(
        {
            "source": "PRECISION_WHISPER",
            "label": "precision_whisper",
            "text": new_text,
            "start": out["start"],
            "end": out["end"],
            "score": 100.0 * float(judge.get("similarity", 0.0) or 0.0),
            "vad_overlap_ratio": judge.get("vad_overlap_ratio"),
        }
    )
    out["stt_candidates"] = stt_candidates
    metadata = dict(out.get("asr_metadata") or {})
    metadata["precision_whisper"] = {
        "accepted": True,
        "old_text": old_text,
        "new_text": new_text,
        "judge": dict(judge),
        "engine": candidate.get("engine"),
        "model": candidate.get("model"),
    }
    out["asr_metadata"] = metadata
    quality_history = list(out.get("quality_history") or [])
    quality_history.append({"stage": "precision_whisper", "judge": dict(judge)})
    out["quality_history"] = quality_history
    return out


def run_selective_precision_whisper(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    media_path: str = "",
    audio_path: str = "",
    lattice_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    settings: dict[str, Any] | None = None,
    transcriber: PrecisionTranscriber | None = None,
    clip_extractor: Callable[[str, float, float, str], str] | None = None,
) -> SelectivePrecisionWhisperResult:
    settings = dict(settings or {})
    current = [dict(segment) for segment in list(segments or []) if isinstance(segment, dict)]
    lattice = normalize_vad_segments(lattice_segments or [])
    targets = select_precision_whisper_targets(current, lattice, settings=settings)
    source_audio = str(audio_path or media_path or "").strip()
    if not targets or not source_audio or not os.path.exists(source_audio):
        return SelectivePrecisionWhisperResult(
            segments=tuple(current),
            report={
                "target_count": len(targets),
                "accepted_count": 0,
                "rejected_count": 0,
                "skipped": not bool(source_audio and os.path.exists(source_audio)),
                "schema": "ai_subtitle_studio.selective_precision_whisper.v1",
            },
        )

    transcriber = transcriber or _default_precision_transcriber
    clip_extractor = clip_extractor or _extract_precision_clip
    accepted = 0
    rejected = 0
    decisions: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ai_subtitle_precision_whisper_") as tmp_dir:
        for target_index, target in enumerate(targets):
            list_index = _as_int(target.get("_list_index"), -1)
            if list_index < 0 or list_index >= len(current):
                continue
            start = _as_float(target.get("recheck_start"))
            end = max(start, _as_float(target.get("recheck_end"), start))
            clip_path = os.path.join(tmp_dir, f"precision_{target_index:03d}.wav")
            try:
                clip = clip_extractor(source_audio, start, end, clip_path)
            except Exception as exc:
                get_logger().log(f"⚠️ 정밀 Whisper 클립 추출 실패: {exc}")
                clip = ""
            if not clip:
                decisions.append({"segment_index": target.get("segment_index"), "accepted": False, "reason": "clip_extract_failed"})
                rejected += 1
                continue
            try:
                raw_candidate = _call_transcriber(transcriber, clip, target, settings)
            except Exception as exc:
                get_logger().log(f"⚠️ 정밀 Whisper 재인식 실패: {exc}")
                decisions.append({"segment_index": target.get("segment_index"), "accepted": False, "reason": "transcriber_failed"})
                rejected += 1
                continue

            target_rows = target.get("precision_lattice_refs") or []
            snap_start = min((_as_float(row.get("start"), start) for row in target_rows), default=_as_float(current[list_index].get("start")))
            snap_end = max((_as_float(row.get("end"), end) for row in target_rows), default=_as_float(current[list_index].get("end")))
            candidate = {
                **raw_candidate,
                "start": round(snap_start, 3),
                "end": round(max(snap_start + 0.05, snap_end), 3),
            }
            judge = precision_whisper_deterministic_judge(
                current[list_index],
                candidate,
                lattice,
                settings=settings,
            )
            decisions.append({"segment_index": target.get("segment_index"), **judge})
            if not judge.get("accepted"):
                rejected += 1
                continue
            current[list_index] = _apply_precision_candidate(current[list_index], candidate, judge)
            accepted += 1

    return SelectivePrecisionWhisperResult(
        segments=tuple(current),
        report={
            "target_count": len(targets),
            "accepted_count": accepted,
            "rejected_count": rejected,
            "decisions": decisions,
            "schema": "ai_subtitle_studio.selective_precision_whisper.v1",
        },
    )


__all__ = [
    "SelectivePrecisionWhisperResult",
    "precision_whisper_deterministic_judge",
    "run_selective_precision_whisper",
    "select_precision_whisper_targets",
]
