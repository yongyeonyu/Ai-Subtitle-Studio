#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


def _copy_chunk_dir(source: Path, target: Path) -> Path:
    if not source.exists():
        if target.exists():
            return target
        raise FileNotFoundError(source)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target, copy_function=_copy_benchmark_chunk_file)
    return target


def _copy_benchmark_chunk_file(src: str, dst: str) -> str:
    if Path(src).suffix.lower() == ".wav":
        try:
            os.link(src, dst)
            return dst
        except OSError:
            pass
    return shutil.copy2(src, dst)


_CHUNK_EXACT_KEYS = {
    "subtitle_mode",
    "simple_operation_mode",
    "mode",
    "user_facing_mode",
    "auto_start_mode",
    "stt_quality_preset",
    "selected_audio_ai",
    "selected_vad",
    "use_basic_filter",
    "ff_chunk",
    "whisper_chunk_overlap_sec",
    "direct_ffmpeg_chunk_extract",
    "direct_ffmpeg_chunk_batch_extract",
    "wav_pcm_fast_chunk_extract",
    "vad_pre_split_enabled",
    "vad_post_stt_align_enabled",
    "vad_post_stt_edge_pad_sec",
    "vad_backend_policy",
    "audio_chunk_routing_enabled",
    "audio_chunk_route_vad_enabled",
    "audio_chunk_routing_benchmark_locked",
    "audio_chunk_routing_disabled",
    "audio_chunk_profile_sec",
}
_CHUNK_PREFIXES = (
    "ff_",
    "df_",
    "none_",
    "vad_",
    "ten_vad_",
    "audio_chunk_route_",
    "direct_ffmpeg_",
    "wav_pcm_",
    "scan_cut_",
    "cut_boundary_",
    "review_vad_",
)


def _chunk_extraction_signature(settings: dict[str, Any]) -> str:
    subset: dict[str, Any] = {}
    for key, value in dict(settings or {}).items():
        if key in _CHUNK_EXACT_KEYS or key.startswith(_CHUNK_PREFIXES):
            subset[key] = value
    return json.dumps(subset, ensure_ascii=False, sort_keys=True, default=str)


def _variant_chunk_settings(base_settings: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(base_settings or {})
    if overrides:
        merged.update(dict(overrides))
    return merged


def _collect_transcribe(generator) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk_rows, _idx, _total in generator:
        for row in chunk_rows or []:
            if isinstance(row, dict) and str(row.get("text", "") or "").strip():
                rows.append(dict(row))
    rows.sort(key=lambda row: (float(row.get("start", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0)))
    return rows


def _slim_segments_for_artifact(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slim: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        words = item.pop("words", None)
        if words:
            item["word_count"] = len(words)
        slim.append(item)
    return slim


def _chunk_wav_count(chunk_dir: Path) -> int:
    try:
        return sum(1 for path in chunk_dir.iterdir() if path.is_file() and path.suffix.lower() == ".wav")
    except Exception:
        return 0


def _load_vad(chunk_dir: Path) -> list[dict[str, Any]]:
    path = chunk_dir / "vad_strict.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [dict(row) for row in data if isinstance(row, dict)]
    except Exception:
        return []


def _load_cached_raw_segments(settings: dict[str, Any]) -> list[dict[str, Any]]:
    path_text = str(settings.get("_benchmark_cached_raw_segments_path") or "").strip()
    if not path_text:
        raise RuntimeError("cached_raw variant requires --cached-raw-segments")
    path = Path(path_text).expanduser()
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("segments") or data.get("rows") or data.get("raw_segments") or []
    rows = [dict(row) for row in data if isinstance(row, dict) and str(row.get("text", "") or "").strip()]
    rows.sort(key=lambda row: (float(row.get("start", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0)))
    return rows
