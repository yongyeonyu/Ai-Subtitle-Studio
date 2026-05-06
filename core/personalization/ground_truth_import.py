from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from core.media_info import probe_media
from core.personalization.lora_context_classifier import classify_lora_context
from core.personalization.lora_models import (
    ExcludedParentheticalRow,
    TruthTableRow,
    line_break_pattern_for_text,
    stable_hash,
)
from core.personalization.subtitle_style_profile import build_subtitle_style_profile
from core.personalization.lora_storage import (
    append_excluded_parentheticals,
    append_multimodal_lora_context_rows,
    append_truth_table_rows,
    append_voice_lora_bridge_rows,
)
from core.platform_compat import ffprobe_binary, hidden_subprocess_kwargs
from core.srt_parser import parse_srt
from core.utils import load_rules


MEDIA_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
    ".mp4", ".mov", ".mkv", ".avi", ".wmv", ".mxf",
}
SUBTITLE_EXTENSIONS = {".srt"}
OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}", "（": "）", "【": "】"}
CLOSE_TO_OPEN = {value: key for key, value in OPEN_TO_CLOSE.items()}
VOICE_BRIDGE_DEFAULT_FPS = 30.0


def _normalize_basename(value: str) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").casefold())


def _clean_line_spaces(text: str) -> str:
    lines = []
    for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        collapsed = re.sub(r"\s+", " ", line).strip()
        if collapsed:
            lines.append(collapsed)
    return "\n".join(lines)


def _contains_spoken_chars(text: str) -> bool:
    return bool(re.search(r"[0-9A-Za-z가-힣]", str(text or "")))


def extract_parenthetical_segments(text: str) -> dict[str, Any]:
    raw = str(text or "")
    kept_chars: list[str] = []
    excluded_blocks: list[str] = []
    stack: list[tuple[str, list[str]]] = []

    for char in raw:
        if char in OPEN_TO_CLOSE:
            stack.append((OPEN_TO_CLOSE[char], []))
            continue
        if stack:
            expected_close, buffer = stack[-1]
            if char == expected_close:
                excluded_text = "".join(buffer).strip()
                if excluded_text:
                    excluded_blocks.append(excluded_text)
                stack.pop()
                continue
            buffer.append(char)
            stack[-1] = (expected_close, buffer)
            continue
        kept_chars.append(char)

    for expected_close, buffer in stack:
        kept_chars.append(CLOSE_TO_OPEN.get(expected_close, "("))
        kept_chars.extend(buffer)

    kept_text = _clean_line_spaces("".join(kept_chars))
    excluded_text = " | ".join(block for block in excluded_blocks if block)
    return {
        "raw_text": raw.strip(),
        "speech_training_text": kept_text,
        "excluded_parenthetical_text": excluded_text,
        "had_parenthetical": bool(excluded_blocks),
    }


def _detect_split_rule(text: str) -> str:
    split_rules, _, _ = load_rules()
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    for line in lines[:-1]:
        last_token = re.split(r"\s+", line)[-1].strip(".,!?~")
        if 1 <= len(last_token) <= 12:
            return last_token
        for rule in sorted(split_rules, key=len, reverse=True):
            if line.endswith(str(rule or "").strip()):
                return str(rule).strip()
    return ""


def _punctuation_pattern(text: str) -> str:
    return "".join(ch for ch in str(text or "") if ch in ".,!?~")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _round_float(value: Any, digits: int = 3) -> float:
    return round(_safe_float(value), int(digits))


def _fraction_to_float(value: Any) -> float:
    text = str(value or "").strip()
    if "/" in text:
        left, right = text.split("/", 1)
        numerator = _safe_float(left)
        denominator = _safe_float(right)
        return numerator / denominator if denominator else 0.0
    return _safe_float(text)


def _file_fingerprint(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    info = {
        "path": str(target),
        "name": target.name,
        "stem": target.stem,
        "extension": target.suffix.lower(),
        "exists": target.exists(),
        "size_bytes": 0,
        "modified_epoch": 0.0,
    }
    try:
        stat = target.stat()
        info["size_bytes"] = int(stat.st_size)
        info["modified_epoch"] = round(float(stat.st_mtime), 3)
    except OSError:
        pass
    return info


def _probe_streams_for_lora(media_path: str | Path) -> dict[str, Any]:
    target = str(media_path)
    try:
        cmd = [
            ffprobe_binary(),
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate,format_name:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,sample_rate,channels,channel_layout,bit_rate,duration",
            "-of",
            "json",
            target,
        ]
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
            **hidden_subprocess_kwargs(),
        )
        if completed.returncode != 0:
            return {"available": False, "error": _clean_line_spaces(completed.stderr)[:180]}
        payload = json.loads(completed.stdout or "{}")
    except Exception as exc:
        return {"available": False, "error": str(exc)[:180]}

    format_info = dict(payload.get("format") or {})
    video_streams: list[dict[str, Any]] = []
    audio_streams: list[dict[str, Any]] = []
    for stream in list(payload.get("streams") or []):
        if not isinstance(stream, dict):
            continue
        stream_type = str(stream.get("codec_type") or "")
        if stream_type == "video":
            fps = _fraction_to_float(stream.get("avg_frame_rate")) or _fraction_to_float(stream.get("r_frame_rate"))
            video_streams.append(
                {
                    "index": _safe_int(stream.get("index")),
                    "codec": str(stream.get("codec_name") or ""),
                    "width": _safe_int(stream.get("width")),
                    "height": _safe_int(stream.get("height")),
                    "fps": round(fps, 3),
                    "bit_rate": _safe_int(stream.get("bit_rate")),
                    "duration_sec": _round_float(stream.get("duration")),
                }
            )
        elif stream_type == "audio":
            audio_streams.append(
                {
                    "index": _safe_int(stream.get("index")),
                    "codec": str(stream.get("codec_name") or ""),
                    "sample_rate": _safe_int(stream.get("sample_rate")),
                    "channels": _safe_int(stream.get("channels")),
                    "channel_layout": str(stream.get("channel_layout") or ""),
                    "bit_rate": _safe_int(stream.get("bit_rate")),
                    "duration_sec": _round_float(stream.get("duration")),
                }
            )

    return {
        "available": True,
        "format": {
            "format_name": str(format_info.get("format_name") or ""),
            "duration_sec": _round_float(format_info.get("duration")),
            "size_bytes": _safe_int(format_info.get("size")),
            "bit_rate": _safe_int(format_info.get("bit_rate")),
        },
        "video_streams": video_streams,
        "audio_streams": audio_streams,
    }


def _media_profile_for_lora(media_path: str | Path) -> dict[str, Any]:
    basic = probe_media(str(media_path))
    streams = _probe_streams_for_lora(media_path)
    first_video = dict((streams.get("video_streams") or [{}])[0] or {})
    first_audio = dict((streams.get("audio_streams") or [{}])[0] or {})
    duration = _safe_float(basic.get("duration")) or _safe_float(dict(streams.get("format") or {}).get("duration_sec"))
    width = _safe_int(first_video.get("width")) or _safe_int(basic.get("width"))
    height = _safe_int(first_video.get("height")) or _safe_int(basic.get("height"))
    fps = _safe_float(first_video.get("fps")) or _safe_float(basic.get("fps"))
    return {
        "file": _file_fingerprint(media_path),
        "duration_sec": round(duration, 3),
        "duration_label": str(basic.get("len_txt") or ""),
        "has_video": width > 0 and height > 0,
        "has_audio": bool(streams.get("audio_streams")),
        "video": {
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "codec": str(first_video.get("codec") or ""),
            "pixel_count": int(width * height) if width and height else 0,
            "aspect_ratio": round(width / height, 4) if width and height else 0.0,
        },
        "audio": {
            "codec": str(first_audio.get("codec") or ""),
            "sample_rate": _safe_int(first_audio.get("sample_rate")),
            "channels": _safe_int(first_audio.get("channels")),
            "channel_layout": str(first_audio.get("channel_layout") or ""),
            "bit_rate": _safe_int(first_audio.get("bit_rate")),
        },
        "streams": streams,
    }


def _mean(values: list[float]) -> float:
    cleaned = [float(value) for value in values if value is not None]
    return round(sum(cleaned) / len(cleaned), 3) if cleaned else 0.0


def _max_or_zero(values: list[float]) -> float:
    return round(max(values), 3) if values else 0.0


def _language_mix(texts: list[str]) -> dict[str, Any]:
    joined = "\n".join(str(text or "") for text in texts)
    counts = {
        "hangul": len(re.findall(r"[가-힣]", joined)),
        "latin": len(re.findall(r"[A-Za-z]", joined)),
        "digit": len(re.findall(r"\d", joined)),
        "punctuation": len(re.findall(r"[.,!?~]", joined)),
    }
    total = max(1, sum(counts.values()))
    return {
        **counts,
        "hangul_ratio": round(counts["hangul"] / total, 4),
        "latin_ratio": round(counts["latin"] / total, 4),
        "digit_ratio": round(counts["digit"] / total, 4),
    }


def _top_counter(counter: Counter, limit: int = 12) -> list[dict[str, Any]]:
    return [{"value": str(value), "count": int(count)} for value, count in counter.most_common(limit)]


def _subtitle_profile_for_lora(
    segments: list[dict[str, Any]],
    truth_rows: list[dict[str, Any]],
    excluded_rows: list[dict[str, Any]],
    *,
    media_duration_sec: float = 0.0,
) -> dict[str, Any]:
    speech_texts = [str(row.get("speech_training_text") or "") for row in truth_rows]
    raw_texts = [str(row.get("raw_ground_truth_text") or "") for row in truth_rows]
    durations = [_safe_float(row.get("duration_sec")) for row in truth_rows]
    cps_values = [_safe_float(row.get("cps")) for row in truth_rows]
    starts = [_safe_float(row.get("start_sec")) for row in truth_rows]
    ends = [_safe_float(row.get("end_sec")) for row in truth_rows]
    gaps = [max(0.0, round(starts[idx] - ends[idx - 1], 3)) for idx in range(1, min(len(starts), len(ends)))]
    line_counts = [max(1, len([line for line in text.splitlines() if line.strip()])) for text in speech_texts]
    char_counts = [len(text.replace("\n", "")) for text in speech_texts]
    line_breaks = Counter(str(row.get("line_break_pattern") or "") for row in truth_rows if str(row.get("line_break_pattern") or ""))
    split_rules = Counter(str(row.get("detected_split_rule") or "") for row in truth_rows if str(row.get("detected_split_rule") or ""))
    punctuation = Counter("".join(str(row.get("punctuation_pattern") or "") for row in truth_rows))
    covered_duration = sum(durations)
    media_duration = max(0.0, float(media_duration_sec or 0.0))
    return {
        "segments_total": len(segments),
        "speech_segments": len(truth_rows),
        "excluded_parenthetical_segments": len(excluded_rows),
        "excluded_parenthetical_ratio": round(len(excluded_rows) / max(1, len(segments)), 4),
        "subtitle_coverage_ratio": round(covered_duration / media_duration, 4) if media_duration else 0.0,
        "timing": {
            "first_start_sec": round(min(starts), 3) if starts else 0.0,
            "last_end_sec": round(max(ends), 3) if ends else 0.0,
            "total_speech_duration_sec": round(covered_duration, 3),
            "avg_segment_duration_sec": _mean(durations),
            "max_segment_duration_sec": _max_or_zero(durations),
            "avg_gap_sec": _mean(gaps),
            "max_gap_sec": _max_or_zero(gaps),
        },
        "reading_speed": {
            "avg_cps": _mean(cps_values),
            "max_cps": _max_or_zero(cps_values),
            "avg_chars": _mean([float(value) for value in char_counts]),
            "max_chars": int(max(char_counts)) if char_counts else 0,
            "avg_lines": _mean([float(value) for value in line_counts]),
            "max_lines": int(max(line_counts)) if line_counts else 0,
        },
        "style": {
            "language_mix": _language_mix(speech_texts),
            "line_break_patterns": _top_counter(line_breaks),
            "split_rules": _top_counter(split_rules),
            "punctuation": _top_counter(punctuation),
            "latin_tokens": _top_counter(Counter(re.findall(r"[A-Za-z][A-Za-z0-9_+-]*", "\n".join(raw_texts)))),
            "number_tokens": _top_counter(Counter(re.findall(r"\d+(?:[.,]\d+)*", "\n".join(raw_texts)))),
        },
    }


def _build_multimodal_lora_context_rows(
    *,
    media_id: str,
    media_path: str,
    subtitle_path: str,
    media_profile: dict[str, Any],
    subtitle_profile: dict[str, Any],
    classification: dict[str, Any],
    pair_match_type: str = "",
) -> list[dict[str, Any]]:
    payload = {
        "schema": "ai_subtitle_studio.multimodal_lora_context.v1",
        "task": "subtitle_generation_context",
        "source": "ground_truth_pair",
        "media_id": media_id,
        "media_path": media_path,
        "subtitle_path": subtitle_path,
        "pair_match_type": pair_match_type,
        "media_profile": media_profile,
        "subtitle_profile": subtitle_profile,
        "context_classification": classification,
        "generation_targets": {
            "goal": "improve_first_pass_subtitle_generation_quality",
            "learn_from": [
                "media_duration_resolution_fps_audio_stream",
                "subtitle_timing_density_cps_gap_line_breaks",
                "punctuation_and_language_mix",
                "parenthetical_editorial_exclusion_policy",
                "voice_text_alignment_ranges",
            ],
            "do_not_learn_as_spoken_text": ["()", "[]", "{}"],
        },
    }
    payload["dedupe_hash"] = stable_hash(
        {
            "media_id": media_id,
            "media_path": media_path,
            "subtitle_path": subtitle_path,
            "task": payload["task"],
            "subtitle_segments": subtitle_profile.get("speech_segments"),
            "media_mtime": dict(media_profile.get("file") or {}).get("modified_epoch"),
        }
    )
    return [payload]


def build_truth_table_records_from_srt(
    media_path: str | Path,
    subtitle_path: str | Path,
    *,
    media_id: str | None = None,
    speaker_or_voice_hint: str = "",
    pair_match_type: str = "",
) -> dict[str, Any]:
    media_path = str(media_path)
    subtitle_path = str(subtitle_path)
    media_id = str(media_id or stable_hash({"media_path": media_path})[:16])
    truth_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    voice_bridge_rows: list[dict[str, Any]] = []
    media_profile = _media_profile_for_lora(media_path)
    subtitle_segments = list(parse_srt(subtitle_path))
    media_duration_sec = _safe_float(media_profile.get("duration_sec"))
    media_fps = _safe_float(dict(media_profile.get("video") or {}).get("fps")) or VOICE_BRIDGE_DEFAULT_FPS
    stats = {
        "segments_total": 0,
        "truth_rows": 0,
        "excluded_parenthetical_rows": 0,
        "skipped_empty_text": 0,
        "skipped_pure_symbols": 0,
    }

    for index, segment in enumerate(subtitle_segments, start=1):
        stats["segments_total"] += 1
        raw_text = str(segment.get("text") or "").strip()
        if not raw_text:
            stats["skipped_empty_text"] += 1
            continue

        extracted = extract_parenthetical_segments(raw_text)
        speech_text = str(extracted["speech_training_text"] or "")
        excluded_text = str(extracted["excluded_parenthetical_text"] or "")
        segment_id = f"{Path(subtitle_path).stem}:{index}"

        if excluded_text:
            excluded_rows.append(
                ExcludedParentheticalRow(
                    media_id=media_id,
                    media_path=media_path,
                    subtitle_path=subtitle_path,
                    segment_id=segment_id,
                    original_text=raw_text,
                    excluded_text=excluded_text,
                    kept_text=speech_text,
                ).to_record()
            )
            stats["excluded_parenthetical_rows"] += 1

        if not speech_text:
            stats["skipped_empty_text"] += 1
            continue
        if not _contains_spoken_chars(speech_text):
            stats["skipped_pure_symbols"] += 1
            continue

        start_sec = float(segment.get("start", 0.0) or 0.0)
        end_sec = float(segment.get("end", 0.0) or 0.0)
        previous_end = _safe_float(subtitle_segments[index - 2].get("end")) if index > 1 else 0.0
        next_start = _safe_float(subtitle_segments[index].get("start")) if index < len(subtitle_segments) else 0.0
        position_ratio = round(start_sec / media_duration_sec, 4) if media_duration_sec > 0 else 0.0
        style_profile = build_subtitle_style_profile(
            raw_text=raw_text,
            speech_text=speech_text,
            start_sec=start_sec,
            end_sec=end_sec,
            previous_end_sec=previous_end if index > 1 else None,
            next_start_sec=next_start if index < len(subtitle_segments) else None,
        )
        truth_rows.append(
            TruthTableRow(
                media_id=media_id,
                media_path=media_path,
                subtitle_path=subtitle_path,
                segment_id=segment_id,
                start_sec=start_sec,
                end_sec=end_sec,
                raw_ground_truth_text=raw_text,
                speech_training_text=speech_text,
                excluded_parenthetical_text=excluded_text,
                line_break_pattern=line_break_pattern_for_text(speech_text),
                punctuation_pattern=_punctuation_pattern(raw_text),
                detected_split_rule=_detect_split_rule(speech_text),
                speaker_or_voice_hint=speaker_or_voice_hint,
                extra={
                    "source": "ground_truth_pair",
                    "subtitle_index": index,
                    "pair_match_type": pair_match_type,
                    "media_duration_sec": round(media_duration_sec, 3),
                    "media_fps": round(media_fps, 3),
                    "media_video_width": _safe_int(dict(media_profile.get("video") or {}).get("width")),
                    "media_video_height": _safe_int(dict(media_profile.get("video") or {}).get("height")),
                    "media_audio_sample_rate": _safe_int(dict(media_profile.get("audio") or {}).get("sample_rate")),
                    "media_audio_channels": _safe_int(dict(media_profile.get("audio") or {}).get("channels")),
                    "segment_position_ratio": position_ratio,
                    "gap_before_sec": round(max(0.0, start_sec - previous_end), 3) if index > 1 else 0.0,
                    "gap_after_sec": round(max(0.0, next_start - end_sec), 3) if index < len(subtitle_segments) else 0.0,
                    "style_profile": style_profile,
                },
            ).to_record()
        )
        duration_sec = max(0.0, end_sec - start_sec)
        start_frame = int(round(start_sec * media_fps))
        end_frame = int(round(end_sec * media_fps))
        voice_bridge_rows.append(
            {
                "schema": "ai_subtitle_studio.voice_lora_bridge.v1",
                "task": "voice_text_alignment_seed",
                "source": "ground_truth_pair",
                "project_path": subtitle_path,
                "project_name": Path(subtitle_path).stem,
                "media_id": media_id,
                "segment_index": index,
                "segment_id": segment_id,
                "text": speech_text,
                "speaker": str(speaker_or_voice_hint or "unknown"),
                "clip_path": media_path,
                "clip_idx": None,
                "start_sec": round(start_sec, 3),
                "end_sec": round(end_sec, 3),
                "duration_sec": round(duration_sec, 3),
                "start_frame": start_frame,
                "end_frame": end_frame,
                "fps": round(media_fps, 3),
                "media_fps": round(media_fps, 3),
                "video_width": _safe_int(dict(media_profile.get("video") or {}).get("width")),
                "video_height": _safe_int(dict(media_profile.get("video") or {}).get("height")),
                "audio_sample_rate": _safe_int(dict(media_profile.get("audio") or {}).get("sample_rate")),
                "audio_channels": _safe_int(dict(media_profile.get("audio") or {}).get("channels")),
                "duration_frames": max(0, end_frame - start_frame),
                "selected_source": "ground_truth_srt",
                "input_text": speech_text,
                "dedupe_hash": stable_hash(
                    {
                        "media_id": media_id,
                        "segment_id": segment_id,
                        "start_sec": round(start_sec, 3),
                        "end_sec": round(end_sec, 3),
                        "text": speech_text,
                        "source": "ground_truth_pair",
                    }
                ),
            }
        )
        stats["truth_rows"] += 1

    subtitle_profile = _subtitle_profile_for_lora(
        subtitle_segments,
        truth_rows,
        excluded_rows,
        media_duration_sec=media_duration_sec,
    )
    classification = classify_lora_context(
        media_profile=media_profile,
        subtitle_profile=subtitle_profile,
        texts=[
            *(row.get("speech_training_text") for row in truth_rows),
        ],
        file_hints=[media_path, subtitle_path],
    )
    multimodal_context_rows = _build_multimodal_lora_context_rows(
        media_id=media_id,
        media_path=media_path,
        subtitle_path=subtitle_path,
        media_profile=media_profile,
        subtitle_profile=subtitle_profile,
        classification=classification,
        pair_match_type=pair_match_type,
    )

    return {
        "media_id": media_id,
        "media_path": media_path,
        "subtitle_path": subtitle_path,
        "truth_rows": truth_rows,
        "excluded_rows": excluded_rows,
        "voice_bridge_rows": voice_bridge_rows,
        "multimodal_context_rows": multimodal_context_rows,
        "media_profile": media_profile,
        "subtitle_profile": subtitle_profile,
        "classification": classification,
        "stats": stats,
    }


def is_media_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in MEDIA_EXTENSIONS


def is_subtitle_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUBTITLE_EXTENSIONS


def discover_ground_truth_assets(inputs: list[str | Path]) -> dict[str, list[str]]:
    media_paths: list[str] = []
    subtitle_paths: list[str] = []
    for item in inputs or []:
        target = Path(item)
        candidates = [target]
        if target.is_dir():
            candidates = [path for path in target.rglob("*") if path.is_file()]
        for candidate in candidates:
            suffix = candidate.suffix.lower()
            if suffix in MEDIA_EXTENSIONS:
                media_paths.append(str(candidate))
            elif suffix in SUBTITLE_EXTENSIONS:
                subtitle_paths.append(str(candidate))
    return {
        "media_paths": sorted(set(media_paths)),
        "subtitle_paths": sorted(set(subtitle_paths)),
    }


def pair_media_and_subtitle_paths(
    media_paths: list[str | Path],
    subtitle_paths: list[str | Path],
) -> dict[str, Any]:
    subtitle_candidates = [str(Path(path)) for path in subtitle_paths or []]
    remaining_subtitles = set(subtitle_candidates)
    exact_index: dict[str, list[str]] = {}
    normalized_index: dict[str, list[str]] = {}
    for subtitle_path in subtitle_candidates:
        stem = Path(subtitle_path).stem
        exact_index.setdefault(stem, []).append(subtitle_path)
        normalized_index.setdefault(_normalize_basename(stem), []).append(subtitle_path)

    pairs: list[dict[str, str]] = []
    unmatched_media: list[str] = []
    ambiguous_matches: list[dict[str, Any]] = []

    for media_path in sorted(str(Path(path)) for path in media_paths or []):
        stem = Path(media_path).stem
        exact_matches = [path for path in exact_index.get(stem, []) if path in remaining_subtitles]
        if len(exact_matches) == 1:
            subtitle_path = exact_matches[0]
            remaining_subtitles.remove(subtitle_path)
            pairs.append({"media_path": media_path, "subtitle_path": subtitle_path, "match_type": "exact"})
            continue
        if len(exact_matches) > 1:
            ambiguous_matches.append(
                {"media_path": media_path, "subtitle_candidates": exact_matches, "match_type": "exact"}
            )
            continue

        normalized_matches = [
            path for path in normalized_index.get(_normalize_basename(stem), []) if path in remaining_subtitles
        ]
        if len(normalized_matches) == 1:
            subtitle_path = normalized_matches[0]
            remaining_subtitles.remove(subtitle_path)
            pairs.append({"media_path": media_path, "subtitle_path": subtitle_path, "match_type": "normalized"})
            continue
        if len(normalized_matches) > 1:
            ambiguous_matches.append(
                {"media_path": media_path, "subtitle_candidates": normalized_matches, "match_type": "normalized"}
            )
            continue
        unmatched_media.append(media_path)

    return {
        "pairs": pairs,
        "unmatched_media_paths": unmatched_media,
        "unmatched_subtitle_paths": sorted(remaining_subtitles),
        "ambiguous_matches": ambiguous_matches,
    }


def pair_ground_truth_assets(inputs: list[str | Path]) -> dict[str, Any]:
    assets = discover_ground_truth_assets(inputs)
    return {
        **assets,
        **pair_media_and_subtitle_paths(assets["media_paths"], assets["subtitle_paths"]),
    }


def resolve_ambiguous_matches(
    ambiguous_matches: list[dict[str, Any]],
    chooser,
) -> dict[str, Any]:
    resolved_pairs: list[dict[str, str]] = []
    unresolved: list[dict[str, Any]] = []

    for item in list(ambiguous_matches or []):
        media_path = str(item.get("media_path") or "")
        match_type = str(item.get("match_type") or "ambiguous")
        candidates = [str(Path(path)) for path in list(item.get("subtitle_candidates") or []) if str(path or "").strip()]
        if not media_path or not candidates:
            unresolved.append(dict(item))
            continue

        selected = chooser(media_path, candidates, match_type) if callable(chooser) else None
        selected_key = str(Path(str(selected))) if selected else ""
        selected_path = next((candidate for candidate in candidates if str(Path(candidate)) == selected_key), "")
        if selected_path:
            resolved_pairs.append(
                {
                    "media_path": media_path,
                    "subtitle_path": selected_path,
                    "match_type": f"user_confirmed_{match_type}",
                }
            )
            continue
        unresolved.append(dict(item))

    return {
        "pairs": resolved_pairs,
        "unresolved": unresolved,
    }


def import_ground_truth_pairs(
    pairs: list[dict[str, Any]],
    *,
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    imported_pairs = 0
    truth_total = 0
    excluded_total = 0
    voice_bridge_total = 0
    multimodal_context_total = 0
    skipped_total = 0

    for pair in pairs or []:
        result = build_truth_table_records_from_srt(
            pair.get("media_path", ""),
            pair.get("subtitle_path", ""),
            media_id=str(pair.get("media_id") or ""),
            speaker_or_voice_hint=str(pair.get("speaker_or_voice_hint") or ""),
            pair_match_type=str(pair.get("match_type") or ""),
        )
        append_truth_table_rows(result["truth_rows"], store_dir)
        append_excluded_parentheticals(result["excluded_rows"], store_dir)
        append_voice_lora_bridge_rows(result["voice_bridge_rows"], store_dir)
        append_multimodal_lora_context_rows(result["multimodal_context_rows"], store_dir)
        imported_pairs += 1
        truth_total += int(result["stats"]["truth_rows"])
        excluded_total += int(result["stats"]["excluded_parenthetical_rows"])
        voice_bridge_total += len(list(result.get("voice_bridge_rows") or []))
        multimodal_context_total += len(list(result.get("multimodal_context_rows") or []))
        skipped_total += int(result["stats"]["skipped_empty_text"]) + int(result["stats"]["skipped_pure_symbols"])

    return {
        "imported_pairs": imported_pairs,
        "truth_rows": truth_total,
        "excluded_rows": excluded_total,
        "voice_bridge_rows": voice_bridge_total,
        "multimodal_context_rows": multimodal_context_total,
        "skipped_rows": skipped_total,
    }


__all__ = [
    "MEDIA_EXTENSIONS",
    "SUBTITLE_EXTENSIONS",
    "build_truth_table_records_from_srt",
    "discover_ground_truth_assets",
    "extract_parenthetical_segments",
    "import_ground_truth_pairs",
    "is_media_path",
    "is_subtitle_path",
    "pair_ground_truth_assets",
    "pair_media_and_subtitle_paths",
    "resolve_ambiguous_matches",
]
