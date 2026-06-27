#!/usr/bin/env python3
from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import re
import shutil
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from io import StringIO
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio.media_processor import VideoProcessor  # noqa: E402
from core.engine.subtitle_accuracy_pipeline import subtitle_completion_report, subtitle_output_variant_score  # noqa: E402
from core.media_info import probe_media  # noqa: E402
from core.performance import current_resource_snapshot  # noqa: E402
from core.runtime.multi_process import apply_apple_m_subtitle_pipeline_plan  # noqa: E402
from core.runtime.memory_manager import process_rss_bytes  # noqa: E402
from tools.benchmark_subtitle_pipeline_variants import (  # noqa: E402
    Variant,
    _base_benchmark_settings,
    _bind_processor_settings,
    _chunk_wav_count,
    _load_vad,
    _mode_profile_method,
    _mode_profile_settings,
    _run_variant,
)

LATEST_DIR = ROOT / "output" / "manual_verification" / "latest"
DEFAULT_MEDIA = Path("/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4")
RUNTIME_MONITOR_FILE = ROOT / "output" / "runtime_monitor" / "latest.json"
MEMORY_MONITOR_FILE = ROOT / "output" / "memory_monitor" / "subtitle_generation_latest.json"
PROC_PATTERNS = [re.compile(r"\bwhisperkit\b", re.I), re.compile(r"\bmlx\b", re.I), re.compile(r"\bollama\b", re.I)]
CUT_BOUNDARY_PROFILE_FILE_MARKERS = (
    "cut_boundary_",
    "cut_boundary/",
    "roughcut/",
    "subtitle_boundary_alignment.py",
    "timeline_cut_boundary",
)
CUT_BOUNDARY_PROFILE_FUNCTION_MARKERS = (
    "cut_boundary",
    "cutboundar",
    "confirmed_cut",
    "pioneer",
    "follower",
    "source_fps",
    "packet_scout",
    "pipe_scout",
    "ffmpeg_scene",
    "roughcut",
)
CUT_BOUNDARY_PROFILE_STAGE_ORDER = (
    "pioneer_scout",
    "source_fps_pipe_scout",
    "follower_verification",
    "ffmpeg_scene_prepass",
    "fusion",
    "confirmed_cut_split_snap",
    "roughcut_boundary",
    "cut_boundary_other",
)
GENERATION_PROFILE_STAGE_ORDER = (
    "stt_primary_transcribe",
    "stt2_selective_recheck",
    "word_precision",
    "llm_refinement",
    "vad_stt_consensus",
    "subtitle_postprocess",
    "cleanup_trim",
    "generation_other",
)
VERIFICATION_SETTING_KEYS = (
    "subtitle_mode",
    "selected_model",
    "selected_llm_provider",
    "selected_whisper_model",
    "selected_whisper_model_secondary",
    "stt_ensemble_enabled",
    "stt_ensemble_parallel_enabled",
    "stt_ensemble_selective_enabled",
    "stt_word_timestamps_mode",
    "stt_word_timestamps_precision_enabled",
    "selected_audio_ai",
    "selected_vad",
    "runtime_quality_self_review_enabled",
    "runtime_memory_warning_ratio",
    "runtime_memory_critical_ratio",
    "runtime_memory_warning_trim_cooldown_sec",
    "runtime_memory_critical_trim_cooldown_sec",
    "runtime_memory_warning_disk_trim_ratio",
    "runtime_memory_critical_disk_trim_ratio",
    "benchmark_runtime_profile",
    "apple_m_full_core_aggressive_enabled",
    "apple_m_aggressive_full_parallel_stt_enabled",
    "stt_window_ensemble_enabled",
    "stt_window_parallel_enabled",
    "stt_quarter_parallel_count",
    "stt_quarter_parallel_max_workers",
    "runtime_scheduler_reserve_cores",
    "runtime_native_threads",
    "io_workers",
    "audio_chunk_route_max_workers",
    "llm_threads_resource_max",
)


class _PeakRSSSampler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.peak_rss_bytes = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="full-media-rss-sampler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        try:
            import psutil  # type: ignore
        except Exception:
            while not self._stop.wait(1.0):
                self.peak_rss_bytes = max(self.peak_rss_bytes, int(process_rss_bytes() or 0))
            return

        proc = psutil.Process(os.getpid())
        while not self._stop.wait(1.0):
            total = 0
            try:
                total += int(proc.memory_info().rss or 0)
            except Exception:
                total += int(process_rss_bytes() or 0)
            try:
                for child in proc.children(recursive=True):
                    try:
                        total += int(child.memory_info().rss or 0)
                    except Exception:
                        continue
            except Exception:
                pass
            self.peak_rss_bytes = max(self.peak_rss_bytes, total)


def _parse_value_text(value_text: str) -> Any:
    text = str(value_text).strip()
    if text.lower() in {"true", "false", "null", "none", ""}:
        return {"true": True, "false": False, "null": None, "none": None}.get(text.lower(), text)
    try:
        return json.loads(text)
    except Exception:
        return text


def _parse_setting_overrides(raw_values: list[str] | None) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for raw in raw_values or []:
        if "=" not in raw:
            raise ValueError(f"Invalid --setting value: {raw!r}; expected key=value")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid --setting key in {raw!r}")
        overrides[key] = _parse_value_text(value)
    return overrides


def _load_settings_json(path_text: str | None) -> dict[str, Any]:
    if not path_text:
        return {}
    settings_path = Path(path_text)
    if not settings_path.exists():
        raise FileNotFoundError(settings_path)
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"settings-json should be an object: {settings_path}")
    return dict(payload)


def _readable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_readable_json(payload) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _profile_stats_rows(profile: cProfile.Profile, *, limit: int = 80) -> list[dict[str, Any]]:
    stats = pstats.Stats(profile)
    rows: list[dict[str, Any]] = []
    for (filename, line_no, func_name), values in stats.stats.items():
        primitive_calls, total_calls, total_time, cumulative_time, _callers = values
        rows.append(
            {
                "file": filename,
                "line": int(line_no),
                "function": func_name,
                "primitive_calls": int(primitive_calls),
                "total_calls": int(total_calls),
                "total_time_sec": round(float(total_time), 6),
                "cumulative_time_sec": round(float(cumulative_time), 6),
            }
        )
    rows.sort(key=lambda item: (float(item["cumulative_time_sec"]), float(item["total_time_sec"])), reverse=True)
    if limit is None or int(limit) <= 0:
        return rows
    return rows[: max(1, int(limit or 80))]


def _is_cut_boundary_profile_row(row: dict[str, Any]) -> bool:
    file_text = str(row.get("file") or "").replace("\\", "/").lower()
    function_text = str(row.get("function") or "").lower()
    return any(marker in file_text for marker in CUT_BOUNDARY_PROFILE_FILE_MARKERS) or any(
        marker in function_text for marker in CUT_BOUNDARY_PROFILE_FUNCTION_MARKERS
    )


def _cut_boundary_profile_stage(row: dict[str, Any]) -> str:
    text = f"{row.get('file') or ''} {row.get('function') or ''}".replace("\\", "/").lower()
    if "ffmpeg_scene" in text or "scene_prepass" in text:
        return "ffmpeg_scene_prepass"
    if "cut_boundary_fusion" in text or "fusion" in text:
        return "fusion"
    if "source_fps" in text or "packet_scout" in text or "pipe_scout" in text:
        return "source_fps_pipe_scout"
    if "verify_media_cut_boundary" in text or "follower" in text:
        return "follower_verification"
    if "pioneer" in text or "scan_media_cut_boundary" in text:
        return "pioneer_scout"
    if "roughcut" in text:
        return "roughcut_boundary"
    if "split" in text or "snap" in text or "confirmed_cut" in text or "subtitle_boundary_alignment.py" in text:
        return "confirmed_cut_split_snap"
    return "cut_boundary_other"


def _profile_time(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _compact_profile_row(row: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "stage": row.get("stage") or _cut_boundary_profile_stage(row),
        "file": row.get("file"),
        "line": row.get("line"),
        "function": row.get("function"),
        "primitive_calls": row.get("primitive_calls"),
        "total_calls": row.get("total_calls"),
        "total_time_sec": row.get("total_time_sec"),
        "cumulative_time_sec": row.get("cumulative_time_sec"),
    }
    return compact


def _compact_generation_profile_row(row: dict[str, Any]) -> dict[str, Any]:
    compact = _compact_profile_row(row)
    compact["stage"] = row.get("stage") or _generation_profile_stage(row)
    return compact


def _generation_profile_stage(row: dict[str, Any]) -> str:
    text = f"{row.get('file') or ''} {row.get('function') or ''}".replace("\\", "/").lower()
    if "word_timestamp" in text or "word_timestamps" in text or "word_precision" in text:
        return "word_precision"
    if "stt_recheck_service" in text or "transcribe_recheck" in text or "recheck_primary_low_score" in text:
        return "stt2_selective_recheck"
    if "transcribe" in text or "whisperkit" in text or "stt_worker" in text or "collect_transcribe" in text:
        return "stt_primary_transcribe"
    if "ollama" in text or "/llm/" in text or "llm_" in text or "subtitle_context_refiner" in text:
        return "llm_refinement"
    if "vad" in text or "consensus" in text or "subtitle_final_integrity" in text or "subtitle_stt_candidate" in text:
        return "vad_stt_consensus"
    if "subtitle_engine" in text or "subtitle_quality" in text or "common_split" in text or "output_variant" in text:
        return "subtitle_postprocess"
    if "runtime_cleanup" in text or "clear_cache" in text or "stage_trim" in text or "gc.collect" in text:
        return "cleanup_trim"
    return "generation_other"


def _is_generation_profile_row(row: dict[str, Any]) -> bool:
    return _generation_profile_stage(row) != "generation_other"


def _summarize_cut_boundary_profile(rows: list[dict[str, Any]], *, top_limit: int = 20) -> dict[str, Any]:
    matching_rows = []
    for row in rows:
        if not _is_cut_boundary_profile_row(row):
            continue
        staged = dict(row)
        staged["stage"] = _cut_boundary_profile_stage(row)
        matching_rows.append(staged)

    stage_summaries: dict[str, dict[str, Any]] = {}
    ordered_stages = list(CUT_BOUNDARY_PROFILE_STAGE_ORDER)
    ordered_stages.extend(
        sorted({str(row.get("stage") or "cut_boundary_other") for row in matching_rows} - set(ordered_stages))
    )
    for stage in ordered_stages:
        stage_rows = [row for row in matching_rows if row.get("stage") == stage]
        if not stage_rows:
            continue
        stage_rows.sort(key=lambda item: (_profile_time(item, "cumulative_time_sec"), _profile_time(item, "total_time_sec")), reverse=True)
        stage_summaries[stage] = {
            "row_count": len(stage_rows),
            "max_cumulative_time_sec": round(max(_profile_time(row, "cumulative_time_sec") for row in stage_rows), 6),
            "max_total_time_sec": round(max(_profile_time(row, "total_time_sec") for row in stage_rows), 6),
            "top_rows": [_compact_profile_row(row) for row in stage_rows[:5]],
        }

    top_stage = None
    top_cumulative = None
    if stage_summaries:
        top_stage, top_data = max(
            stage_summaries.items(),
            key=lambda item: float(item[1].get("max_cumulative_time_sec") or 0.0),
        )
        top_cumulative = top_data.get("max_cumulative_time_sec")

    return {
        "schema": "ai_subtitle_studio.cut_boundary_profile_summary.v1",
        "note": "cProfile cumulative times are diagnostic and non-additive; use non-profile repeat runs for elapsed-time truth.",
        "source_row_count": len(rows),
        "matching_row_count": len(matching_rows),
        "top_stage": top_stage,
        "top_cumulative_time_sec": top_cumulative,
        "stage_summaries": stage_summaries,
        "top_rows": [_compact_profile_row(row) for row in matching_rows[: max(1, int(top_limit or 20))]],
    }


def _summarize_generation_profile(rows: list[dict[str, Any]], *, top_limit: int = 20) -> dict[str, Any]:
    matching_rows = []
    for row in rows:
        if not _is_generation_profile_row(row):
            continue
        staged = dict(row)
        staged["stage"] = _generation_profile_stage(row)
        matching_rows.append(staged)

    stage_summaries: dict[str, dict[str, Any]] = {}
    ordered_stages = list(GENERATION_PROFILE_STAGE_ORDER)
    ordered_stages.extend(
        sorted({str(row.get("stage") or "generation_other") for row in matching_rows} - set(ordered_stages))
    )
    for stage in ordered_stages:
        stage_rows = [row for row in matching_rows if row.get("stage") == stage]
        if not stage_rows:
            continue
        stage_rows.sort(key=lambda item: (_profile_time(item, "cumulative_time_sec"), _profile_time(item, "total_time_sec")), reverse=True)
        stage_summaries[stage] = {
            "row_count": len(stage_rows),
            "max_cumulative_time_sec": round(max(_profile_time(row, "cumulative_time_sec") for row in stage_rows), 6),
            "max_total_time_sec": round(max(_profile_time(row, "total_time_sec") for row in stage_rows), 6),
            "top_rows": [_compact_generation_profile_row(row) for row in stage_rows[:5]],
        }

    top_stage = None
    top_cumulative = None
    if stage_summaries:
        top_stage, top_data = max(
            stage_summaries.items(),
            key=lambda item: float(item[1].get("max_cumulative_time_sec") or 0.0),
        )
        top_cumulative = top_data.get("max_cumulative_time_sec")

    return {
        "schema": "ai_subtitle_studio.generation_profile_summary.v1",
        "note": "cProfile cumulative times are diagnostic and non-additive; use non-profile repeat runs for elapsed-time truth.",
        "source_row_count": len(rows),
        "matching_row_count": len(matching_rows),
        "top_stage": top_stage,
        "top_cumulative_time_sec": top_cumulative,
        "stage_summaries": stage_summaries,
        "top_rows": [_compact_generation_profile_row(row) for row in matching_rows[: max(1, int(top_limit or 20))]],
    }


def _cut_boundary_profile_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Cut Boundary Function Profile",
        "",
        f"- Matching rows: `{summary.get('matching_row_count')}` / `{summary.get('source_row_count')}`",
        f"- Top stage: `{summary.get('top_stage')}`",
        f"- Top cumulative time: `{summary.get('top_cumulative_time_sec')}` sec",
        f"- Note: {summary.get('note')}",
        "",
        "## Stage Maxima",
        "",
    ]
    stage_summaries = dict(summary.get("stage_summaries") or {})
    if not stage_summaries:
        lines.append("- No cut-boundary owner rows were present in the captured profile.")
    for stage in CUT_BOUNDARY_PROFILE_STAGE_ORDER:
        data = dict(stage_summaries.get(stage) or {})
        if not data:
            continue
        lines.append(
            f"- `{stage}`: rows `{data.get('row_count')}`, "
            f"max cumulative `{data.get('max_cumulative_time_sec')}` sec, "
            f"max total `{data.get('max_total_time_sec')}` sec"
        )
    return "\n".join(lines) + "\n"


def _generation_profile_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Generation Function Profile",
        "",
        f"- Matching rows: `{summary.get('matching_row_count')}` / `{summary.get('source_row_count')}`",
        f"- Top stage: `{summary.get('top_stage')}`",
        f"- Top cumulative time: `{summary.get('top_cumulative_time_sec')}` sec",
        f"- Note: {summary.get('note')}",
        "",
        "## Stage Maxima",
        "",
    ]
    stage_summaries = dict(summary.get("stage_summaries") or {})
    if not stage_summaries:
        lines.append("- No generation owner rows were present in the captured profile.")
    for stage in GENERATION_PROFILE_STAGE_ORDER:
        data = dict(stage_summaries.get(stage) or {})
        if not data:
            continue
        lines.append(
            f"- `{stage}`: rows `{data.get('row_count')}`, "
            f"max cumulative `{data.get('max_cumulative_time_sec')}` sec, "
            f"max total `{data.get('max_total_time_sec')}` sec"
        )
    return "\n".join(lines) + "\n"


def _write_profile_artifacts(run_dir: Path, profile: cProfile.Profile, *, limit: int = 80) -> dict[str, Any]:
    profile_path = run_dir / "function_profile.pstats"
    top_json_path = run_dir / "function_profile_top.json"
    top_txt_path = run_dir / "function_profile_top.txt"
    cut_summary_json_path = run_dir / "function_profile_cut_boundary_summary.json"
    cut_summary_md_path = run_dir / "function_profile_cut_boundary_summary.md"
    generation_summary_json_path = run_dir / "function_profile_generation_summary.json"
    generation_summary_md_path = run_dir / "function_profile_generation_summary.md"
    profile.dump_stats(str(profile_path))
    all_rows = _profile_stats_rows(profile, limit=0)
    rows = all_rows[: max(1, int(limit or 80))]
    cut_summary = _summarize_cut_boundary_profile(all_rows, top_limit=max(20, int(limit or 80)))
    generation_summary = _summarize_generation_profile(all_rows, top_limit=max(20, int(limit or 80)))
    _write_json(
        top_json_path,
        {
            "schema": "ai_subtitle_studio.function_profile.v1",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "sort": "cumulative_time_sec",
            "limit": max(1, int(limit or 80)),
            "rows": rows,
        },
    )
    _write_json(cut_summary_json_path, cut_summary)
    _write_text(cut_summary_md_path, _cut_boundary_profile_markdown(cut_summary))
    _write_json(generation_summary_json_path, generation_summary)
    _write_text(generation_summary_md_path, _generation_profile_markdown(generation_summary))
    stream = StringIO()
    pstats.Stats(profile, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(max(1, int(limit or 80)))
    _write_text(top_txt_path, stream.getvalue())
    return {
        "pstats_path": str(profile_path),
        "top_json_path": str(top_json_path),
        "top_txt_path": str(top_txt_path),
        "cut_boundary_summary_path": str(cut_summary_json_path),
        "cut_boundary_summary_md_path": str(cut_summary_md_path),
        "cut_boundary_summary": cut_summary,
        "generation_summary_path": str(generation_summary_json_path),
        "generation_summary_md_path": str(generation_summary_md_path),
        "generation_summary": generation_summary,
        "top_rows": rows[:10],
    }


def _progress(path: Path, *, stage: str, status: str = "running", **extra: Any) -> None:
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "stage": stage,
    }
    payload.update(extra)
    _write_json(path, payload)


def _snapshot_process_pid(payload: dict[str, Any] | None) -> int | None:
    data = dict(payload or {})
    resource = data.get("resource")
    if not isinstance(resource, dict):
        resource = data
    native = resource.get("native_memory") if isinstance(resource, dict) else None
    if isinstance(native, dict):
        try:
            pid = int(native.get("pid") or 0)
            if pid > 0:
                return pid
        except (TypeError, ValueError):
            pass
    return None


def _resource_pressure_stage(payload: dict[str, Any] | None) -> str | None:
    data = dict(payload or {})
    stage = str(data.get("pressure_stage") or data.get("memory_pressure_stage") or "").strip().lower()
    if stage in {"normal", "warning", "critical"}:
        return stage
    native = data.get("native_memory")
    if isinstance(native, dict):
        stage = str(native.get("pressure_stage") or native.get("memory_pressure_stage") or "").strip().lower()
        if stage in {"normal", "warning", "critical"}:
            return stage
    return None


def _ignored_snapshot_record(src: Path, filename: str, reason: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": filename,
        "source_path": str(src),
        "reason": reason,
        "source_pid": _snapshot_process_pid(payload),
        "source_stage": payload.get("pressure_stage") or payload.get("memory_pressure_stage"),
        "source_subtitle_stage": payload.get("subtitle_generation_stage"),
    }


def _snapshot_file(
    src: Path,
    dst_dir: Path,
    filename: str,
    *,
    expected_pid: int | None = None,
    ignored_snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not src.exists():
        return None
    dst = dst_dir / filename
    try:
        payload = json.loads(src.read_text(encoding="utf-8"))
    except Exception:
        return None
    if expected_pid is not None:
        source_pid = _snapshot_process_pid(payload)
        if source_pid is not None and source_pid != expected_pid:
            reason = f"pid_mismatch:{source_pid}!={expected_pid}"
            ignored = _ignored_snapshot_record(src, filename, reason, payload)
            if ignored_snapshots is not None:
                ignored_snapshots.append(ignored)
            ignored_dst = dst.with_name(f"{dst.stem}_ignored.json")
            try:
                _write_json(ignored_dst, {"ignored": True, **ignored, "snapshot": payload})
            except Exception:
                pass
            return None
    try:
        shutil.copy2(src, dst)
    except Exception:
        try:
            _write_json(dst, payload)
        except Exception:
            pass
    return payload


def _collect_processes() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "psutil_available": False,
        "matched_processes": [],
        "total_matched": 0,
    }
    try:
        import psutil  # type: ignore
    except Exception:
        return payload
    payload["psutil_available"] = True
    rows: list[dict[str, Any]] = []
    total_matched = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
        try:
            info = proc.info or {}
            name = str(info.get("name") or "").lower()
            cmd = " ".join(str(item) for item in (info.get("cmdline") or []))
            cmdline = cmd.lower()
            if not any(pat.search(name) or pat.search(cmdline) for pat in PROC_PATTERNS):
                continue
            total_matched += 1
            rss = 0
            try:
                rss = int((info.get("memory_info") or {}).rss or 0)
            except Exception:
                rss = 0
            rows.append(
                {
                    "pid": int(info.get("pid") or 0),
                    "name": info.get("name"),
                    "cmdline": cmd,
                    "rss_bytes": rss,
                }
            )
        except Exception:
            continue
    payload["matched_processes"] = rows
    payload["total_matched"] = total_matched
    return payload


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _dict_payload(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _final_segment_summary(result: dict[str, Any]) -> dict[str, Any]:
    for key in ("native_segments_summary", "native_final_segments_summary", "output_segments_summary"):
        summary = _dict_payload(result.get(key))
        if summary:
            return summary
    return {}


def _summary_markdown(payload: dict[str, Any]) -> str:
    media = dict(payload.get("media") or {})
    result = dict(payload.get("result") or {})
    completion = dict(payload.get("completion_report") or {})
    final_summary = _final_segment_summary(result)
    stt_summary = _dict_payload(result.get("native_stt_segments_summary"))
    global_summary = _dict_payload(result.get("native_global_canvas_summary"))
    quality = _dict_payload(result.get("quality"))
    readability = dict(result.get("readability") or {})
    self_review = dict(payload.get("self_review_summary") or {})
    variant_score = dict(payload.get("variant_score") or {})
    readability_score = readability.get("readability_score")
    avg_max_line_chars = readability.get("avg_max_line_chars")
    orphan_line_segments = readability.get("orphan_line_segments")
    lines = [
        "# Full Media Verification",
        "",
        f"- Created: `{payload.get('created_at')}`",
        f"- Verification ok: `{payload.get('ok')}`",
        f"- Verification failure: `{payload.get('verification_failure_reason') or ''}`",
        f"- Media: `{media.get('path')}`",
        f"- Duration: `{media.get('duration_sec')}` sec (`{media.get('len_txt')}`)",
        f"- Mode: `{payload.get('mode')}`",
        f"- Method: `{payload.get('method')}`",
        f"- Run LLM: `{payload.get('run_llm')}`",
        f"- Run index: `{payload.get('run_index') or 'single'}`",
        f"- Start sec: `{media.get('start_sec')}`",
        f"- Duration sec: `{media.get('duration_target_sec')}`",
        f"- Pipeline elapsed: `{result.get('elapsed_sec')}` sec",
        f"- Total elapsed: `{payload.get('total_elapsed_sec')}` sec",
        f"- Peak RSS bytes: `{payload.get('peak_rss_bytes')}`",
        f"- Final segments: `{result.get('final_segments')}`",
        f"- Raw segments: `{result.get('raw_segments')}`",
        f"- Avg STT score: `{result.get('avg_stt_score')}`",
        f"- Self review overall score: `{self_review.get('overall_score')}`",
        f"- Completion avg quality: `{completion.get('avg_quality_score')}`",
        f"- Variant score: `{variant_score.get('score')}`",
        f"- Reference quality score: `{quality.get('quality_score')}`",
        f"- Reference timing MAE: `{quality.get('timing_mae_sec')}` sec",
        f"- Readability score: `{readability_score}`",
        f"- Readability max line chars: `{avg_max_line_chars}`",
        f"- Readability orphan lines: `{orphan_line_segments}`",
        f"- Final invalid/non-monotonic/overlap: `{final_summary.get('invalid_duration_count')}` / `{final_summary.get('non_monotonic_count')}` / `{final_summary.get('overlap_count')}`",
        f"- Final stable for save/reopen: `{final_summary.get('stable_for_save_reopen')}`",
        f"- Global canvas max active: `{global_summary.get('max_active_segments')}`",
        f"- STT1/STT2 selected: `{stt_summary.get('stt1_selected_count')}` / `{stt_summary.get('stt2_selected_count')}`",
        f"- STT2 recheck / word precision: `{stt_summary.get('recheck_applied_count')}` / `{stt_summary.get('word_precision_count')}`",
        f"- STT pressure stage transitions: `{payload.get('pressure_stages')}`",
        f"- Runtime monitor stage: `{payload.get('runtime_stage')}`",
    ]
    runtime_monitor = dict(payload.get("runtime_monitor_after") or {})
    if runtime_monitor:
        runtime_pressure = runtime_monitor.get("memory_pressure_stage")
        runtime_warning = runtime_monitor.get("resource", {}).get("memory_pressure_stage")
        lines.extend(
            [
                f"- Runtime memory stage: `{runtime_pressure}`",
                f"- Native memory pressure: `{runtime_warning}`",
            ]
        )
    ignored_monitors = list(payload.get("ignored_monitor_snapshots") or [])
    if ignored_monitors:
        lines.append(f"- Ignored stale monitor snapshots: `{len(ignored_monitors)}`")
    stage_wall_clock_summary = dict(result.get("stage_wall_clock_summary") or {})
    if stage_wall_clock_summary:
        stage_summaries = dict(stage_wall_clock_summary.get("stage_summaries") or {})

        def _wall_total(stage: str) -> Any:
            return dict(stage_summaries.get(stage) or {}).get("total_elapsed_sec")

        lines.extend(
            [
                f"- Stage wall-clock spans: `{stage_wall_clock_summary.get('span_count')}`",
                f"- Stage wall-clock top: `{stage_wall_clock_summary.get('top_stage')}` / `{stage_wall_clock_summary.get('top_elapsed_sec')}` sec",
                f"- Stage wall-clock STT1/STT2/word/postprocess: `{_wall_total('stt_primary_transcribe')}` / `{_wall_total('stt2_selective_recheck')}` / `{_wall_total('word_precision')}` / `{_wall_total('subtitle_postprocess')}` sec",
                f"- Stage wall-clock VAD consensus: `{_wall_total('vad_stt_consensus')}` sec",
            ]
        )
    trim_summary = dict(((payload.get("subtitle_generation_monitor_after") or {}).get("stage_trim_summary")) or {})
    if trim_summary:
        lines.extend(
            [
                f"- Stage trim executed: `{trim_summary.get('executed_count')}`",
                f"- Stage trim total elapsed: `{trim_summary.get('total_elapsed_ms')}` ms",
                f"- Stage trim slowest stage: `{trim_summary.get('slowest_stage_key')}`",
                f"- Stage trim slowest elapsed: `{trim_summary.get('slowest_stage_elapsed_ms')}` ms",
            ]
        )
    cut_summary = dict(((payload.get("function_profile") or {}).get("cut_boundary_summary")) or {})
    if cut_summary:
        lines.extend(
            [
                f"- Cut-boundary profile rows: `{cut_summary.get('matching_row_count')}`",
                f"- Cut-boundary profile top stage: `{cut_summary.get('top_stage')}`",
                f"- Cut-boundary profile top cumulative: `{cut_summary.get('top_cumulative_time_sec')}` sec",
            ]
        )
    generation_summary = dict(((payload.get("function_profile") or {}).get("generation_summary")) or {})
    if generation_summary:
        lines.extend(
            [
                f"- Generation profile rows: `{generation_summary.get('matching_row_count')}`",
                f"- Generation profile top stage: `{generation_summary.get('top_stage')}`",
                f"- Generation profile top cumulative: `{generation_summary.get('top_cumulative_time_sec')}` sec",
            ]
        )
    error = str(payload.get("error") or "").strip()
    if error:
        lines.extend(["", "## Error", "", "```text", error, "```"])
    return "\n".join(lines) + "\n"


def verification_failure_reason(payload: dict[str, Any]) -> str:
    result = dict(payload.get("result") or {})
    error = str(payload.get("error") or result.get("error") or "").strip()
    if error:
        return f"pipeline_error:{error.splitlines()[-1][:180]}"

    media = dict(payload.get("media") or {})
    try:
        target_duration = float(media.get("duration_target_sec") or media.get("duration_sec") or 0.0)
    except (TypeError, ValueError):
        target_duration = 0.0
    try:
        raw_segments = int(result.get("raw_segments") or 0)
    except (TypeError, ValueError):
        raw_segments = 0
    try:
        final_segments = int(result.get("final_segments") or 0)
    except (TypeError, ValueError):
        final_segments = 0
    try:
        vad_segments = int(payload.get("vad_segments") or 0)
    except (TypeError, ValueError):
        vad_segments = 0
    try:
        audio_chunk_wavs = int(payload.get("audio_chunk_wavs") or 0)
    except (TypeError, ValueError):
        audio_chunk_wavs = 0

    # QA hot path: a non-trivial verification slice must not pass with zero
    # subtitles, otherwise missing audio streams or STT early-exits look like
    # speed wins.
    if target_duration >= 5.0:
        if raw_segments <= 0:
            return "empty_subtitle_output:raw_segments_zero"
        if final_segments <= 0:
            return "empty_subtitle_output:final_segments_zero"
        final_summary = _final_segment_summary(result)
        if final_summary:
            invalid_count = _safe_int(final_summary.get("invalid_duration_count"))
            non_monotonic_count = _safe_int(final_summary.get("non_monotonic_count"))
            overlap_count = _safe_int(final_summary.get("overlap_count"))
            if invalid_count > 0:
                return f"final_stability:invalid_duration_count={invalid_count}"
            if non_monotonic_count > 0:
                return f"final_stability:non_monotonic_count={non_monotonic_count}"
            if overlap_count > 0:
                return f"final_stability:overlap_count={overlap_count}"
            if final_summary.get("stable_for_save_reopen") is False:
                return "final_stability:stable_for_save_reopen_false"
    return ""


def summary_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload.get("result") or {})
    completion = dict(payload.get("completion_report") or {})
    self_review = dict(payload.get("self_review_summary") or {})
    variant = dict(payload.get("variant_score") or {})
    variant_metrics = dict(variant.get("metrics") or {})
    final_summary = _final_segment_summary(result)
    global_summary = _dict_payload(result.get("native_global_canvas_summary"))
    stt_summary = _dict_payload(result.get("native_stt_segments_summary"))
    quality = _dict_payload(result.get("quality"))
    readability = dict(result.get("readability") or {})
    subtitle_monitor_after = _dict_payload(payload.get("subtitle_generation_monitor_after"))
    stage_wall_clock_summary = dict(result.get("stage_wall_clock_summary") or {})
    metrics = {
        "pipeline_elapsed_sec": result.get("elapsed_sec"),
        "raw_segment_count": result.get("raw_segments"),
        "final_segment_count": result.get("final_segments"),
        "avg_stt_score": result.get("avg_stt_score"),
        "quality_score": quality.get("quality_score"),
        "text_score": quality.get("text_score"),
        "timing_mae_sec": quality.get("timing_mae_sec"),
        "cer": quality.get("cer"),
        "segment_count_delta": quality.get("segment_count_delta"),
        "self_review_overall_score": self_review.get("overall_score"),
        "completion_avg_quality": completion.get("avg_quality_score"),
        "llm_rollback_count": completion.get("llm_rollback_count"),
        "output_variant_score": variant.get("score"),
        "readability_score": readability.get("readability_score"),
        "final_invalid_duration_count": final_summary.get("invalid_duration_count"),
        "final_non_monotonic_count": final_summary.get("non_monotonic_count"),
        "final_overlap_count": final_summary.get("overlap_count"),
        "final_stable_for_save_reopen": _safe_bool_or_none(final_summary.get("stable_for_save_reopen")),
        "final_max_overlap": final_summary.get("max_overlap"),
        "global_canvas_max_active_segments": global_summary.get("max_active_segments"),
        "global_canvas_stable": _safe_bool_or_none(global_summary.get("stable_for_global_canvas")),
        "stt1_selected_count": stt_summary.get("stt1_selected_count"),
        "stt2_selected_count": stt_summary.get("stt2_selected_count"),
        "stt_recheck_applied_count": stt_summary.get("recheck_applied_count"),
        "word_precision_count": stt_summary.get("word_precision_count"),
        "stt2_coverage_ratio": stt_summary.get("stt2_coverage_ratio"),
        "selective_recheck_active": _safe_bool_or_none(stt_summary.get("selective_recheck_active")),
        "llm_gate_skipped_segments": variant_metrics.get("llm_gate_skipped_segments"),
        "llm_verifier_rollbacks": variant_metrics.get("llm_verifier_rollbacks"),
        "lora_applied_segments": variant_metrics.get("lora_applied_segments"),
        "deep_policy_segments": variant_metrics.get("deep_policy_segments"),
        "subtitle_memory_pressure_stage": subtitle_monitor_after.get("pressure_stage"),
        "peak_rss_bytes": payload.get("peak_rss_bytes"),
        "free_memory_ratio": (payload.get("resource_before") or {}).get("available_memory_ratio"),
        "free_memory_gb": round(
            float(((payload.get("resource_before") or {}).get("available_memory_bytes", 0) or 0) / (1024 ** 3)),
            4,
        ),
    }
    if stage_wall_clock_summary:
        metrics.update({
            "stage_wall_clock_span_count": stage_wall_clock_summary.get("span_count"),
            "stage_wall_clock_top_stage": stage_wall_clock_summary.get("top_stage"),
            "stage_wall_clock_top_elapsed_sec": stage_wall_clock_summary.get("top_elapsed_sec"),
        })
        wall_stage_summaries = dict(stage_wall_clock_summary.get("stage_summaries") or {})
        for stage in (
            "stt_primary_transcribe",
            "stt_primary_collect_transcribe",
            "stt2_selective_recheck",
            "stt2_collect_transcribe",
            "stt2_full_fallback_transcribe",
            "stt_collect_whisperkit_fallback",
            "word_precision",
            "word_precision_collect_transcribe",
            "vad_stt_consensus",
            "subtitle_postprocess",
            "subtitle_postprocess_detail",
        ):
            stage_summary = dict(wall_stage_summaries.get(stage) or {})
            if not stage_summary:
                continue
            metrics[f"stage_wall_clock_{stage}_count"] = stage_summary.get("count")
            metrics[f"stage_wall_clock_{stage}_total_elapsed_sec"] = stage_summary.get("total_elapsed_sec")
            metrics[f"stage_wall_clock_{stage}_max_elapsed_sec"] = stage_summary.get("max_elapsed_sec")
            for substage in ("setup", "prepare", "collect", "annotate", "batch", "detail"):
                key = f"total_{substage}_elapsed_sec"
                if key in stage_summary:
                    metric_key = f"stage_wall_clock_{stage}_{substage}_elapsed_sec"
                    if stage == "subtitle_postprocess_detail" and substage == "detail":
                        metric_key = "stage_wall_clock_subtitle_postprocess_detail_elapsed_sec"
                    metrics[metric_key] = stage_summary.get(key)
        spans = list(stage_wall_clock_summary.get("spans") or [])
        for span in reversed(spans):
            if not isinstance(span, dict) or str(span.get("stage") or "") != "subtitle_postprocess":
                continue
            if span.get("detail_top_stage") is not None:
                metrics["stage_wall_clock_subtitle_postprocess_detail_top_stage"] = span.get("detail_top_stage")
            if span.get("detail_top_elapsed_sec") is not None:
                metrics["stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec"] = span.get("detail_top_elapsed_sec")
            if span.get("detail_stage_count") is not None:
                metrics["stage_wall_clock_subtitle_postprocess_detail_stage_count"] = span.get("detail_stage_count")
            break
        for span in reversed(spans):
            if (
                not isinstance(span, dict)
                or str(span.get("stage") or "") != "subtitle_postprocess_detail"
                or str(span.get("detail_stage") or "") != "high_context_boundary"
            ):
                continue
            for key in (
                "high_context_boundary_candidate_pair_count",
                "high_context_boundary_skipped_pair_count",
                "high_context_boundary_llm_call_count",
                "high_context_boundary_failed_call_count",
                "high_context_boundary_changed_pair_count",
                "high_context_boundary_max_pairs",
                "high_context_boundary_keep_decision_count",
                "high_context_boundary_move_boundary_decision_count",
                "high_context_boundary_merge_decision_count",
                "high_context_boundary_invalid_decision_count",
                "high_context_boundary_correction_request_count",
                "high_context_boundary_applied_correction_count",
                "high_context_boundary_keep_cache_hit_count",
                "high_context_boundary_keep_cache_miss_count",
                "high_context_boundary_keep_cache_write_count",
                "high_context_boundary_elapsed_sec",
                "high_context_boundary_enabled",
                "high_context_boundary_keep_cache_enabled",
                "high_context_boundary_reason",
            ):
                if key in span:
                    metrics[key] = span.get(key)
            break
        diagnostic_fields = (
            "raw_range_count",
            "range_count",
            "prepared_clip_count",
            "collected_segment_count",
            "applied_count",
            "applied_segment_count",
            "range_audio_sec",
            "max_range_duration_sec",
            "prepared_audio_sec",
            "max_prepared_clip_duration_sec",
            "missing_voice_range_count",
            "route_hint_range_count",
            "low_score_range_count",
            "empty_text_range_count",
            "selected_range_count",
            "precision_review_range_count",
            "needs_review_range_count",
            "red_range_count",
            "yellow_range_count",
            "risk_range_count",
            "missing_word_range_count",
            "collect_cache_enabled",
            "collect_cache_hit",
            "collect_cache_write",
            "collect_provider_called",
        )
        for stage in ("stt2_selective_recheck", "word_precision"):
            for span in reversed(spans):
                if not isinstance(span, dict) or str(span.get("stage") or "") != stage:
                    continue
                for key in diagnostic_fields:
                    if key in span:
                        metrics[f"stage_wall_clock_{stage}_{key}"] = span.get(key)
                break
        collect_diagnostic_fields = (
            "label",
            "status",
            "backend",
            "router_backend",
            "resolved_model",
            "chunk_count",
            "submitted_chunk_count",
            "chunk_audio_sec",
            "target_end_sec",
            "word_timestamps",
            "progress_by_audio_duration",
            "worker_silence_timeout_sec",
            "whisperkit_worker_count",
            "whisperkit_stream_results",
            "whisperkit_compute_profile",
            "submission_reordered",
            "received_chunks",
            "processed_chunks",
            "emitted_segment_count",
            "done_seen",
            "setup_elapsed_sec",
            "collect_elapsed_sec",
            "worker_reuse_enabled",
            "worker_cache_hit",
            "worker_cache_busy",
            "worker_transient",
            "resource_pressure_stage",
            "resource_allows_worker_reuse",
            "collect_cache_enabled",
            "collect_cache_hit",
            "collect_cache_write",
            "collect_provider_called",
            "collect_cache_path",
            "source_collect_label",
        )
        for stage in (
            "stt_primary_transcribe",
            "stt_primary_collect_transcribe",
            "stt2_collect_transcribe",
            "word_precision_collect_transcribe",
            "stt_collect_transcribe",
        ):
            for span in reversed(spans):
                if not isinstance(span, dict) or str(span.get("stage") or "") != stage:
                    continue
                for key in collect_diagnostic_fields:
                    if key in span:
                        metrics[f"stage_wall_clock_{stage}_{key}"] = span.get(key)
                break
    trim_summary = dict(((payload.get("subtitle_generation_monitor_after") or {}).get("stage_trim_summary")) or {})
    if trim_summary:
        metrics.update({
            "stage_trim_requested_count": trim_summary.get("requested_count"),
            "stage_trim_executed_count": trim_summary.get("executed_count"),
            "stage_trim_skipped_count": trim_summary.get("skipped_count"),
            "stage_trim_total_elapsed_ms": trim_summary.get("total_elapsed_ms"),
            "stage_trim_total_failure_count": trim_summary.get("total_failure_count"),
            "stage_trim_slowest_stage": trim_summary.get("slowest_stage_key"),
            "stage_trim_slowest_stage_elapsed_ms": trim_summary.get("slowest_stage_elapsed_ms"),
        })
    cut_summary = dict(((payload.get("function_profile") or {}).get("cut_boundary_summary")) or {})
    if cut_summary:
        metrics.update({
            "cut_boundary_profile_matching_rows": cut_summary.get("matching_row_count"),
            "cut_boundary_profile_top_stage": cut_summary.get("top_stage"),
            "cut_boundary_profile_top_cumulative_time_sec": cut_summary.get("top_cumulative_time_sec"),
        })
    generation_summary = dict(((payload.get("function_profile") or {}).get("generation_summary")) or {})
    if generation_summary:
        metrics.update({
            "generation_profile_matching_rows": generation_summary.get("matching_row_count"),
            "generation_profile_top_stage": generation_summary.get("top_stage"),
            "generation_profile_top_cumulative_time_sec": generation_summary.get("top_cumulative_time_sec"),
        })
        stage_summaries = dict(generation_summary.get("stage_summaries") or {})
        for stage in GENERATION_PROFILE_STAGE_ORDER:
            stage_summary = dict(stage_summaries.get(stage) or {})
            if not stage_summary:
                continue
            metrics[f"generation_profile_{stage}_max_cumulative_time_sec"] = stage_summary.get("max_cumulative_time_sec")
    return metrics


def _build_single_verification_context(
    media_path: Path,
    *,
    mode: str,
    run_dir: Path,
    settings_overrides: dict[str, Any] | None,
    run_index: int | None,
    start_sec: float,
    duration_sec: float | None,
) -> tuple[dict[str, Any], dict[str, Any], Variant, float, float | None]:
    output_prefix = "full_fast" if mode == "fast" else f"full_{mode}"
    media_info = dict(probe_media(str(media_path)) or {})
    duration_total_sec = float(media_info.get("duration", 0.0) or 0.0)
    base_settings = _base_benchmark_settings("current")
    if settings_overrides:
        base_settings.update(settings_overrides)
    llm_model = str(base_settings.get("selected_model") or "").strip()
    settings = _mode_profile_settings(base_settings, mode, llm_model=llm_model)
    settings = apply_apple_m_subtitle_pipeline_plan(settings)
    method = _mode_profile_method(settings)
    run_llm = bool(mode == "high" and llm_model and "사용 안함" not in llm_model)
    run_start = max(0.0, float(start_sec or 0.0))
    run_end = None
    if duration_sec and duration_sec > 0.0:
        run_end = min(duration_total_sec, run_start + float(duration_sec))
        if duration_total_sec > 0.0 and run_end < run_start:
            run_end = run_start
    payload: dict[str, Any] = {
        "schema": "ai_subtitle_studio.full_media_verify.v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_index": run_index,
        "media": {
            "path": str(media_path),
            "duration_sec": round(duration_total_sec, 3),
            "duration_target_sec": None if duration_sec is None else round(float(duration_sec), 3),
            "start_sec": round(run_start, 3),
            "width": media_info.get("width"),
            "height": media_info.get("height"),
            "fps": media_info.get("fps"),
            "info_txt": media_info.get("info_txt"),
            "len_txt": media_info.get("len_txt"),
        },
        "mode": mode,
        "method": method,
        "run_llm": run_llm,
        "settings_overrides": settings_overrides,
        "settings": {key: settings.get(key) for key in VERIFICATION_SETTING_KEYS},
        "resource_before": current_resource_snapshot({}),
        "pressure_stages": [],
        "runtime_stage": None,
        "process_snapshot_before": _collect_processes(),
        "ignored_monitor_snapshots": [],
    }
    expected_pid = _snapshot_process_pid(payload.get("resource_before"))
    ignored_snapshots = payload["ignored_monitor_snapshots"]
    runtime_monitor_before = _snapshot_file(
        RUNTIME_MONITOR_FILE,
        run_dir,
        "runtime_monitor_before.json",
        expected_pid=expected_pid,
        ignored_snapshots=ignored_snapshots,
    )
    subtitle_generation_monitor_before = _snapshot_file(
        MEMORY_MONITOR_FILE,
        run_dir,
        "subtitle_generation_monitor_before.json",
        expected_pid=expected_pid,
        ignored_snapshots=ignored_snapshots,
    )
    if runtime_monitor_before is not None:
        payload["runtime_monitor_before"] = runtime_monitor_before
        payload["runtime_stage"] = runtime_monitor_before.get("pressure_stage")
    else:
        payload["runtime_stage"] = _resource_pressure_stage(payload.get("resource_before"))
    if subtitle_generation_monitor_before is not None:
        payload["subtitle_generation_monitor_before"] = subtitle_generation_monitor_before
    variant = Variant(
        name=output_prefix,
        phase="full_media_verify",
        description=f"Full media verification for {mode} mode",
        method=method,
        overrides=dict(settings),
        run_llm=run_llm,
    )
    return payload, settings, variant, run_start, run_end


def _finalize_successful_verification_payload(
    payload: dict[str, Any],
    *,
    run_dir: Path,
    variant: Variant,
    settings: dict[str, Any],
    sampler: _PeakRSSSampler,
    started: float,
) -> dict[str, Any]:
    output_segments_path = run_dir / variant.name / "output_segments.json"
    rows = json.loads(output_segments_path.read_text(encoding="utf-8"))
    self_review = dict(rows[0].get("subtitle_quality_self_review_summary") or {}) if rows and isinstance(rows[0], dict) else {}
    payload["self_review_summary"] = self_review
    payload["completion_report"] = subtitle_completion_report(rows, settings)
    payload["variant_score"] = subtitle_output_variant_score(rows, settings)
    payload["resource_after"] = current_resource_snapshot({})
    payload["process_snapshot_after"] = _collect_processes()
    expected_pid = _snapshot_process_pid(payload.get("resource_after")) or _snapshot_process_pid(payload.get("resource_before"))
    ignored_snapshots = payload.setdefault("ignored_monitor_snapshots", [])
    payload["runtime_monitor_after"] = _snapshot_file(
        RUNTIME_MONITOR_FILE,
        run_dir,
        "runtime_monitor_after.json",
        expected_pid=expected_pid,
        ignored_snapshots=ignored_snapshots,
    )
    payload["subtitle_generation_monitor_after"] = _snapshot_file(
        MEMORY_MONITOR_FILE,
        run_dir,
        "subtitle_generation_monitor_after.json",
        expected_pid=expected_pid,
        ignored_snapshots=ignored_snapshots,
    )
    runtime_after = dict(payload.get("runtime_monitor_after") or {})
    after_stage = runtime_after.get("pressure_stage") or _resource_pressure_stage(payload.get("resource_after"))
    payload["pressure_stages"] = [payload.get("runtime_stage"), after_stage]
    if runtime_after:
        payload["runtime_stage"] = runtime_after.get("pressure_stage")
    elif after_stage:
        payload["runtime_stage"] = after_stage
    payload["peak_rss_bytes"] = int(sampler.peak_rss_bytes or 0)
    payload["total_elapsed_sec"] = round(time.perf_counter() - started, 3)
    payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
    payload["summary_metrics"] = summary_metrics(payload)
    payload["verification_failure_reason"] = verification_failure_reason(payload)
    payload["ok"] = not bool(payload["verification_failure_reason"])
    return payload


def _finalize_failed_verification_payload(
    payload: dict[str, Any],
    *,
    run_dir: Path,
    sampler: _PeakRSSSampler,
    started: float,
) -> dict[str, Any]:
    payload["error"] = traceback.format_exc()
    payload["process_snapshot_after"] = _collect_processes()
    expected_pid = _snapshot_process_pid(payload.get("resource_before"))
    ignored_snapshots = payload.setdefault("ignored_monitor_snapshots", [])
    payload["runtime_monitor_after"] = _snapshot_file(
        RUNTIME_MONITOR_FILE,
        run_dir,
        "runtime_monitor_after_error.json",
        expected_pid=expected_pid,
        ignored_snapshots=ignored_snapshots,
    )
    payload["subtitle_generation_monitor_after"] = _snapshot_file(
        MEMORY_MONITOR_FILE,
        run_dir,
        "subtitle_generation_monitor_after_error.json",
        expected_pid=expected_pid,
        ignored_snapshots=ignored_snapshots,
    )
    payload["peak_rss_bytes"] = int(sampler.peak_rss_bytes or 0)
    payload["total_elapsed_sec"] = round(time.perf_counter() - started, 3)
    payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
    payload["summary_metrics"] = summary_metrics(payload)
    payload["verification_failure_reason"] = verification_failure_reason(payload) or "pipeline_exception"
    payload["ok"] = False
    return payload


def _run_single_verification(
    media_path: Path,
    *,
    mode: str,
    output_root: Path,
    settings_overrides: dict[str, Any] | None = None,
    run_index: int | None = None,
    start_sec: float = 0.0,
    duration_sec: float | None = None,
    profile_functions: bool = False,
    profile_top: int = 80,
) -> dict[str, Any]:
    run_dir = output_root
    if run_index is not None and run_index > 0:
        run_dir = output_root / f"run_{run_index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    progress_path = run_dir / "tinyping_full_verify_progress.json"
    result_path = run_dir / "tinyping_full_verify.json"
    summary_path = run_dir / "tinyping_full_verify.md"
    payload, settings, variant, run_start, run_end = _build_single_verification_context(
        media_path,
        mode=mode,
        run_dir=run_dir,
        settings_overrides=settings_overrides,
        run_index=run_index,
        start_sec=start_sec,
        duration_sec=duration_sec,
    )
    sampler = _PeakRSSSampler()
    profiler = cProfile.Profile() if profile_functions else None
    _progress(
        progress_path,
        stage="starting",
        media=str(media_path),
        mode=mode,
        run_index=run_index,
        start_sec=payload["media"]["start_sec"],
        target_duration_sec=payload["media"]["duration_target_sec"],
    )
    started = time.perf_counter()
    try:
        sampler.start()
        if profiler is not None:
            profiler.enable()
        extractor = VideoProcessor()
        _bind_processor_settings(extractor, settings)
        _progress(progress_path, stage="audio_extract", media=str(media_path), mode=mode, run_index=run_index)
        extract_started = time.perf_counter()
        chunk_dir, _ = extractor.extract_audio(
            str(media_path),
            target_start_sec=run_start,
            target_end_sec=run_end,
            is_single_segment=False,
        )
        audio_extract_elapsed = time.perf_counter() - extract_started
        extractor.release_runtime_models()

        chunk_path = Path(chunk_dir)
        if not chunk_path.exists():
            raise RuntimeError(f"audio chunk extraction failed: {chunk_path}")
        vad_rows = _load_vad(chunk_path)
        payload["audio_extract_elapsed_sec"] = round(audio_extract_elapsed, 3)
        payload["audio_chunk_dir"] = str(chunk_path)
        payload["audio_chunk_wavs"] = _chunk_wav_count(chunk_path)
        payload["vad_segments"] = len(vad_rows)

        _progress(
            progress_path,
            stage="subtitle_pipeline",
            mode=mode,
            run_index=run_index,
            audio_extract_elapsed_sec=round(audio_extract_elapsed, 3),
            audio_chunk_wavs=payload["audio_chunk_wavs"],
            vad_segments=payload["vad_segments"],
        )
        result = _run_variant(
            variant,
            chunk_source=chunk_path,
            work_dir=run_dir,
            base_settings=settings,
            reference=[],
        )
        if profiler is not None:
            profiler.disable()
            payload["function_profile"] = _write_profile_artifacts(
                run_dir,
                profiler,
                limit=profile_top,
            )
        payload["result"] = result
        payload = _finalize_successful_verification_payload(
            payload,
            run_dir=run_dir,
            variant=variant,
            settings=settings,
            sampler=sampler,
            started=started,
        )
        _write_json(result_path, payload)
        _write_text(summary_path, _summary_markdown(payload))
        _progress(
            progress_path,
            status="completed",
            stage="completed",
            run_index=run_index,
            total_elapsed_sec=payload["total_elapsed_sec"],
            peak_rss_bytes=payload["peak_rss_bytes"],
            self_review_overall_score=payload.get("self_review_overall_score"),
            completion_avg_quality=payload.get("completion_avg_quality"),
            result_path=str(result_path),
        )
        return payload
    except Exception:
        if profiler is not None:
            try:
                profiler.disable()
                payload["function_profile"] = _write_profile_artifacts(
                    run_dir,
                    profiler,
                    limit=profile_top,
                )
            except Exception:
                pass
        payload = _finalize_failed_verification_payload(payload, run_dir=run_dir, sampler=sampler, started=started)
        _write_json(result_path, payload)
        _write_text(summary_path, _summary_markdown(payload))
        _progress(
            progress_path,
            status="failed",
            stage="failed",
            run_index=run_index,
            total_elapsed_sec=payload["total_elapsed_sec"],
            result_path=str(result_path),
            error=str(payload.get("error") or "").splitlines()[-1] if payload.get("error") else "unknown_error",
        )
        raise
    finally:
        sampler.stop()


def run_full_verification(
    media_path: str | Path,
    *,
    mode: str = "high",
    output_dir: str | Path = LATEST_DIR,
    settings_overrides: dict[str, Any] | None = None,
    start_sec: float = 0.0,
    duration_sec: float | None = None,
    profile_functions: bool = False,
    profile_top: int = 80,
) -> dict[str, Any]:
    output_root = Path(output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)
    payload = _run_single_verification(
        Path(media_path).expanduser(),
        mode=str(mode or "high").strip().lower(),
        output_root=output_root,
        settings_overrides=settings_overrides,
        run_index=None,
        start_sec=max(0.0, float(start_sec or 0.0)),
        duration_sec=float(duration_sec) if duration_sec and duration_sec > 0.0 else None,
        profile_functions=bool(profile_functions),
        profile_top=max(1, int(profile_top or 80)),
    )
    payload["result_path"] = str((output_root / "tinyping_full_verify.json").resolve())
    return payload


def _build_repeat_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    def metric_values(key: str, *, cast: type = float) -> list[Any]:
        values: list[Any] = []
        for item in runs:
            value = (item.get("summary_metrics") or {}).get(key)
            if cast is bool:
                if isinstance(value, bool):
                    values.append(value)
                continue
            if not isinstance(value, (int, float)):
                continue
            try:
                values.append(cast(value))
            except (TypeError, ValueError):
                continue
        return values

    def numeric_summary(key: str, *, cast: type = float, decimals: int = 3) -> dict[str, Any]:
        values = metric_values(key, cast=cast)
        if not values:
            return {"list": [], "avg": None, "min": None, "max": None}
        avg = sum(values) / len(values)
        return {
            "list": values,
            "avg": round(avg, decimals) if cast is float else round(avg, 3),
            "min": min(values),
            "max": max(values),
        }

    elapsed = metric_values("pipeline_elapsed_sec", cast=float)
    final_stability = metric_values("final_stable_for_save_reopen", cast=bool)
    cut_profile_stages = [
        str(item.get("summary_metrics", {}).get("cut_boundary_profile_top_stage") or "")
        for item in runs
        if item.get("summary_metrics", {}).get("cut_boundary_profile_top_stage")
    ]
    cut_profile_top_times = metric_values("cut_boundary_profile_top_cumulative_time_sec", cast=float)
    generation_profile_stages = [
        str(item.get("summary_metrics", {}).get("generation_profile_top_stage") or "")
        for item in runs
        if item.get("summary_metrics", {}).get("generation_profile_top_stage")
    ]
    generation_profile_top_times = metric_values("generation_profile_top_cumulative_time_sec", cast=float)
    stage_wall_clock_top_stages = [
        str((item.get("summary_metrics") or {}).get("stage_wall_clock_top_stage") or "")
        for item in runs
        if (item.get("summary_metrics") or {}).get("stage_wall_clock_top_stage")
    ]
    subtitle_postprocess_detail_top_stages = [
        str((item.get("summary_metrics") or {}).get("stage_wall_clock_subtitle_postprocess_detail_top_stage") or "")
        for item in runs
        if (item.get("summary_metrics") or {}).get("stage_wall_clock_subtitle_postprocess_detail_top_stage")
    ]
    high_context_boundary_reasons = [
        str((item.get("summary_metrics") or {}).get("high_context_boundary_reason") or "")
        for item in runs
        if (item.get("summary_metrics") or {}).get("high_context_boundary_reason")
    ]
    high_context_boundary_enabled = [
        bool((item.get("summary_metrics") or {}).get("high_context_boundary_enabled"))
        for item in runs
        if (item.get("summary_metrics") or {}).get("high_context_boundary_enabled") is not None
    ]
    high_context_boundary_keep_cache_enabled = [
        bool((item.get("summary_metrics") or {}).get("high_context_boundary_keep_cache_enabled"))
        for item in runs
        if (item.get("summary_metrics") or {}).get("high_context_boundary_keep_cache_enabled") is not None
    ]
    subtitle_pressure_stages = [
        str((item.get("summary_metrics") or {}).get("subtitle_memory_pressure_stage") or "")
        for item in runs
        if (item.get("summary_metrics") or {}).get("subtitle_memory_pressure_stage")
    ]
    summary = {
        "run_count": len(runs),
        "pipeline_elapsed_sec": {
            "list": elapsed,
            "avg": round(sum(elapsed) / len(elapsed), 3) if elapsed else None,
            "min": min(elapsed) if elapsed else None,
            "max": max(elapsed) if elapsed else None,
        },
        "raw_segment_count": numeric_summary("raw_segment_count", cast=int),
        "final_segment_count": numeric_summary("final_segment_count", cast=int),
        "quality_score": numeric_summary("quality_score", cast=float),
        "timing_mae_sec": numeric_summary("timing_mae_sec", cast=float, decimals=4),
        "final_invalid_duration_count": numeric_summary("final_invalid_duration_count", cast=int),
        "final_non_monotonic_count": numeric_summary("final_non_monotonic_count", cast=int),
        "final_overlap_count": numeric_summary("final_overlap_count", cast=int),
        "final_stable_for_save_reopen": {
            "list": final_stability,
            "all": all(final_stability) if final_stability else None,
            "latest": final_stability[-1] if final_stability else None,
        },
        "global_canvas_max_active_segments": numeric_summary("global_canvas_max_active_segments", cast=int),
        "stt1_selected_count": numeric_summary("stt1_selected_count", cast=int),
        "stt2_selected_count": numeric_summary("stt2_selected_count", cast=int),
        "stt_recheck_applied_count": numeric_summary("stt_recheck_applied_count", cast=int),
        "word_precision_count": numeric_summary("word_precision_count", cast=int),
        "stt2_coverage_ratio": numeric_summary("stt2_coverage_ratio", cast=float, decimals=6),
        "llm_gate_skipped_segments": numeric_summary("llm_gate_skipped_segments", cast=int),
        "stage_trim_total_elapsed_ms": numeric_summary("stage_trim_total_elapsed_ms", cast=float),
        "stage_trim_executed_count": numeric_summary("stage_trim_executed_count", cast=int),
        "stage_wall_clock_top_stage": {
            "list": stage_wall_clock_top_stages,
            "latest": stage_wall_clock_top_stages[-1] if stage_wall_clock_top_stages else None,
        },
        "stage_wall_clock_top_elapsed_sec": numeric_summary("stage_wall_clock_top_elapsed_sec", cast=float),
        "stage_wall_clock_stt_primary_transcribe_total_elapsed_sec": numeric_summary(
            "stage_wall_clock_stt_primary_transcribe_total_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_stt_collect_whisperkit_fallback_count": numeric_summary(
            "stage_wall_clock_stt_collect_whisperkit_fallback_count",
            cast=int,
        ),
        "stage_wall_clock_stt_collect_whisperkit_fallback_total_elapsed_sec": numeric_summary(
            "stage_wall_clock_stt_collect_whisperkit_fallback_total_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_stt_collect_whisperkit_fallback_max_elapsed_sec": numeric_summary(
            "stage_wall_clock_stt_collect_whisperkit_fallback_max_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_stt2_selective_recheck_total_elapsed_sec": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_total_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_stt2_selective_recheck_prepare_elapsed_sec": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_prepare_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_stt2_selective_recheck_collect_elapsed_sec": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_collect_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_stt2_selective_recheck_annotate_elapsed_sec": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_annotate_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_stt2_selective_recheck_batch_elapsed_sec": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_batch_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_stt2_selective_recheck_raw_range_count": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_raw_range_count",
            cast=int,
        ),
        "stage_wall_clock_stt2_selective_recheck_range_count": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_range_count",
            cast=int,
        ),
        "stage_wall_clock_stt2_selective_recheck_range_audio_sec": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_range_audio_sec",
            cast=float,
        ),
        "stage_wall_clock_stt2_selective_recheck_max_range_duration_sec": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_max_range_duration_sec",
            cast=float,
        ),
        "stage_wall_clock_stt2_selective_recheck_prepared_audio_sec": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_prepared_audio_sec",
            cast=float,
        ),
        "stage_wall_clock_stt2_selective_recheck_max_prepared_clip_duration_sec": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_max_prepared_clip_duration_sec",
            cast=float,
        ),
        "stage_wall_clock_stt2_selective_recheck_applied_segment_count": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_applied_segment_count",
            cast=int,
        ),
        "stage_wall_clock_stt2_selective_recheck_missing_voice_range_count": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_missing_voice_range_count",
            cast=int,
        ),
        "stage_wall_clock_stt2_selective_recheck_route_hint_range_count": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_route_hint_range_count",
            cast=int,
        ),
        "stage_wall_clock_stt2_selective_recheck_low_score_range_count": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_low_score_range_count",
            cast=int,
        ),
        "stage_wall_clock_stt2_selective_recheck_empty_text_range_count": numeric_summary(
            "stage_wall_clock_stt2_selective_recheck_empty_text_range_count",
            cast=int,
        ),
        "stage_wall_clock_word_precision_total_elapsed_sec": numeric_summary(
            "stage_wall_clock_word_precision_total_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_word_precision_prepare_elapsed_sec": numeric_summary(
            "stage_wall_clock_word_precision_prepare_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_word_precision_collect_elapsed_sec": numeric_summary(
            "stage_wall_clock_word_precision_collect_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_word_precision_annotate_elapsed_sec": numeric_summary(
            "stage_wall_clock_word_precision_annotate_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_word_precision_batch_elapsed_sec": numeric_summary(
            "stage_wall_clock_word_precision_batch_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_word_precision_range_count": numeric_summary(
            "stage_wall_clock_word_precision_range_count",
            cast=int,
        ),
        "stage_wall_clock_word_precision_range_audio_sec": numeric_summary(
            "stage_wall_clock_word_precision_range_audio_sec",
            cast=float,
        ),
        "stage_wall_clock_word_precision_max_range_duration_sec": numeric_summary(
            "stage_wall_clock_word_precision_max_range_duration_sec",
            cast=float,
        ),
        "stage_wall_clock_word_precision_prepared_audio_sec": numeric_summary(
            "stage_wall_clock_word_precision_prepared_audio_sec",
            cast=float,
        ),
        "stage_wall_clock_word_precision_max_prepared_clip_duration_sec": numeric_summary(
            "stage_wall_clock_word_precision_max_prepared_clip_duration_sec",
            cast=float,
        ),
        "stage_wall_clock_word_precision_selected_range_count": numeric_summary(
            "stage_wall_clock_word_precision_selected_range_count",
            cast=int,
        ),
        "stage_wall_clock_word_precision_precision_review_range_count": numeric_summary(
            "stage_wall_clock_word_precision_precision_review_range_count",
            cast=int,
        ),
        "stage_wall_clock_word_precision_needs_review_range_count": numeric_summary(
            "stage_wall_clock_word_precision_needs_review_range_count",
            cast=int,
        ),
        "stage_wall_clock_word_precision_red_range_count": numeric_summary(
            "stage_wall_clock_word_precision_red_range_count",
            cast=int,
        ),
        "stage_wall_clock_word_precision_yellow_range_count": numeric_summary(
            "stage_wall_clock_word_precision_yellow_range_count",
            cast=int,
        ),
        "stage_wall_clock_word_precision_risk_range_count": numeric_summary(
            "stage_wall_clock_word_precision_risk_range_count",
            cast=int,
        ),
        "stage_wall_clock_word_precision_missing_word_range_count": numeric_summary(
            "stage_wall_clock_word_precision_missing_word_range_count",
            cast=int,
        ),
        "stage_wall_clock_vad_stt_consensus_total_elapsed_sec": numeric_summary(
            "stage_wall_clock_vad_stt_consensus_total_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_subtitle_postprocess_total_elapsed_sec": numeric_summary(
            "stage_wall_clock_subtitle_postprocess_total_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_subtitle_postprocess_detail_top_stage": {
            "list": subtitle_postprocess_detail_top_stages,
            "latest": subtitle_postprocess_detail_top_stages[-1] if subtitle_postprocess_detail_top_stages else None,
        },
        "stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec": numeric_summary(
            "stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec",
            cast=float,
        ),
        "stage_wall_clock_subtitle_postprocess_detail_stage_count": numeric_summary(
            "stage_wall_clock_subtitle_postprocess_detail_stage_count",
            cast=int,
        ),
        "stage_wall_clock_subtitle_postprocess_detail_total_elapsed_sec": numeric_summary(
            "stage_wall_clock_subtitle_postprocess_detail_total_elapsed_sec",
            cast=float,
        ),
        "high_context_boundary_enabled": {
            "list": high_context_boundary_enabled,
            "all": all(high_context_boundary_enabled) if high_context_boundary_enabled else None,
            "latest": high_context_boundary_enabled[-1] if high_context_boundary_enabled else None,
        },
        "high_context_boundary_reason": {
            "list": high_context_boundary_reasons,
            "latest": high_context_boundary_reasons[-1] if high_context_boundary_reasons else None,
        },
        "high_context_boundary_keep_cache_enabled": {
            "list": high_context_boundary_keep_cache_enabled,
            "all": all(high_context_boundary_keep_cache_enabled) if high_context_boundary_keep_cache_enabled else None,
            "latest": high_context_boundary_keep_cache_enabled[-1] if high_context_boundary_keep_cache_enabled else None,
        },
        "high_context_boundary_candidate_pair_count": numeric_summary(
            "high_context_boundary_candidate_pair_count",
            cast=int,
        ),
        "high_context_boundary_skipped_pair_count": numeric_summary(
            "high_context_boundary_skipped_pair_count",
            cast=int,
        ),
        "high_context_boundary_llm_call_count": numeric_summary(
            "high_context_boundary_llm_call_count",
            cast=int,
        ),
        "high_context_boundary_failed_call_count": numeric_summary(
            "high_context_boundary_failed_call_count",
            cast=int,
        ),
        "high_context_boundary_changed_pair_count": numeric_summary(
            "high_context_boundary_changed_pair_count",
            cast=int,
        ),
        "high_context_boundary_max_pairs": numeric_summary(
            "high_context_boundary_max_pairs",
            cast=int,
        ),
        "high_context_boundary_keep_decision_count": numeric_summary(
            "high_context_boundary_keep_decision_count",
            cast=int,
        ),
        "high_context_boundary_move_boundary_decision_count": numeric_summary(
            "high_context_boundary_move_boundary_decision_count",
            cast=int,
        ),
        "high_context_boundary_merge_decision_count": numeric_summary(
            "high_context_boundary_merge_decision_count",
            cast=int,
        ),
        "high_context_boundary_invalid_decision_count": numeric_summary(
            "high_context_boundary_invalid_decision_count",
            cast=int,
        ),
        "high_context_boundary_correction_request_count": numeric_summary(
            "high_context_boundary_correction_request_count",
            cast=int,
        ),
        "high_context_boundary_applied_correction_count": numeric_summary(
            "high_context_boundary_applied_correction_count",
            cast=int,
        ),
        "high_context_boundary_keep_cache_hit_count": numeric_summary(
            "high_context_boundary_keep_cache_hit_count",
            cast=int,
        ),
        "high_context_boundary_keep_cache_miss_count": numeric_summary(
            "high_context_boundary_keep_cache_miss_count",
            cast=int,
        ),
        "high_context_boundary_keep_cache_write_count": numeric_summary(
            "high_context_boundary_keep_cache_write_count",
            cast=int,
        ),
        "high_context_boundary_elapsed_sec": numeric_summary(
            "high_context_boundary_elapsed_sec",
            cast=float,
        ),
        "subtitle_memory_pressure_stage": {
            "list": subtitle_pressure_stages,
            "latest": subtitle_pressure_stages[-1] if subtitle_pressure_stages else None,
        },
        "cut_boundary_profile_top_stage": {
            "list": cut_profile_stages,
            "latest": cut_profile_stages[-1] if cut_profile_stages else None,
        },
        "cut_boundary_profile_top_cumulative_time_sec": {
            "list": cut_profile_top_times,
            "avg": round(sum(cut_profile_top_times) / len(cut_profile_top_times), 3) if cut_profile_top_times else None,
            "min": min(cut_profile_top_times) if cut_profile_top_times else None,
            "max": max(cut_profile_top_times) if cut_profile_top_times else None,
        },
        "generation_profile_top_stage": {
            "list": generation_profile_stages,
            "latest": generation_profile_stages[-1] if generation_profile_stages else None,
        },
        "generation_profile_top_cumulative_time_sec": {
            "list": generation_profile_top_times,
            "avg": round(sum(generation_profile_top_times) / len(generation_profile_top_times), 3) if generation_profile_top_times else None,
            "min": min(generation_profile_top_times) if generation_profile_top_times else None,
            "max": max(generation_profile_top_times) if generation_profile_top_times else None,
        },
        "run_paths": [item.get("result_path") for item in runs],
    }
    return summary


def _emit_repeat_summary(output_root: Path, runs: list[dict[str, Any]]) -> None:
    summary = _build_repeat_summary(runs)
    summary["result_paths"] = [str(item.get("result_path") or "") for item in runs]
    _write_json(output_root / "repeat_summary.json", {
        "schema": "ai_subtitle_studio.full_media_verify_repeat.v1",
        **summary,
    })
    lines = [
        "run_index,pipeline_elapsed_sec,total_elapsed_sec,final_segments,raw_segments,quality_score,timing_mae_sec,final_invalid_duration_count,final_non_monotonic_count,final_overlap_count,final_stable_for_save_reopen,global_canvas_max_active_segments,stt1_selected_count,stt2_selected_count,stt_recheck_applied_count,word_precision_count,stt2_coverage_ratio,llm_gate_skipped_segments,avg_stt_score,stage_trim_total_elapsed_ms,stage_trim_executed_count,stage_trim_slowest_stage,stage_wall_clock_top_stage,stage_wall_clock_top_elapsed_sec,stage_wall_clock_stt_primary_transcribe_total_elapsed_sec,stage_wall_clock_stt_collect_whisperkit_fallback_count,stage_wall_clock_stt_collect_whisperkit_fallback_total_elapsed_sec,stage_wall_clock_stt_collect_whisperkit_fallback_max_elapsed_sec,stage_wall_clock_stt2_selective_recheck_total_elapsed_sec,stage_wall_clock_stt2_selective_recheck_prepare_elapsed_sec,stage_wall_clock_stt2_selective_recheck_collect_elapsed_sec,stage_wall_clock_stt2_selective_recheck_annotate_elapsed_sec,stage_wall_clock_stt2_selective_recheck_batch_elapsed_sec,stage_wall_clock_stt2_selective_recheck_range_audio_sec,stage_wall_clock_stt2_selective_recheck_max_range_duration_sec,stage_wall_clock_stt2_selective_recheck_prepared_audio_sec,stage_wall_clock_stt2_selective_recheck_max_prepared_clip_duration_sec,stage_wall_clock_stt2_selective_recheck_applied_segment_count,stage_wall_clock_stt2_selective_recheck_missing_voice_range_count,stage_wall_clock_stt2_selective_recheck_route_hint_range_count,stage_wall_clock_stt2_selective_recheck_low_score_range_count,stage_wall_clock_stt2_selective_recheck_empty_text_range_count,stage_wall_clock_word_precision_total_elapsed_sec,stage_wall_clock_word_precision_prepare_elapsed_sec,stage_wall_clock_word_precision_collect_elapsed_sec,stage_wall_clock_word_precision_annotate_elapsed_sec,stage_wall_clock_word_precision_batch_elapsed_sec,stage_wall_clock_word_precision_range_audio_sec,stage_wall_clock_word_precision_max_range_duration_sec,stage_wall_clock_word_precision_prepared_audio_sec,stage_wall_clock_word_precision_max_prepared_clip_duration_sec,stage_wall_clock_word_precision_selected_range_count,stage_wall_clock_word_precision_precision_review_range_count,stage_wall_clock_word_precision_needs_review_range_count,stage_wall_clock_word_precision_red_range_count,stage_wall_clock_word_precision_yellow_range_count,stage_wall_clock_word_precision_risk_range_count,stage_wall_clock_word_precision_missing_word_range_count,stage_wall_clock_vad_stt_consensus_total_elapsed_sec,stage_wall_clock_subtitle_postprocess_total_elapsed_sec,stage_wall_clock_subtitle_postprocess_detail_top_stage,stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec,stage_wall_clock_subtitle_postprocess_detail_stage_count,stage_wall_clock_subtitle_postprocess_detail_total_elapsed_sec,high_context_boundary_enabled,high_context_boundary_reason,high_context_boundary_candidate_pair_count,high_context_boundary_skipped_pair_count,high_context_boundary_llm_call_count,high_context_boundary_failed_call_count,high_context_boundary_changed_pair_count,high_context_boundary_max_pairs,high_context_boundary_keep_decision_count,high_context_boundary_move_boundary_decision_count,high_context_boundary_merge_decision_count,high_context_boundary_invalid_decision_count,high_context_boundary_correction_request_count,high_context_boundary_applied_correction_count,high_context_boundary_keep_cache_enabled,high_context_boundary_keep_cache_hit_count,high_context_boundary_keep_cache_miss_count,high_context_boundary_keep_cache_write_count,high_context_boundary_elapsed_sec,subtitle_memory_pressure_stage,generation_profile_top_stage,generation_profile_top_cumulative_time_sec,cut_boundary_profile_top_stage,cut_boundary_profile_top_cumulative_time_sec",
    ]
    for item in runs:
        metrics = item.get("summary_metrics") or {}
        lines.append(
            ",".join(
                map(
                    str,
                    [
                        item.get("run_index"),
                        metrics.get("pipeline_elapsed_sec"),
                        item.get("total_elapsed_sec"),
                        metrics.get("final_segment_count"),
                        metrics.get("raw_segment_count"),
                        metrics.get("quality_score"),
                        metrics.get("timing_mae_sec"),
                        metrics.get("final_invalid_duration_count"),
                        metrics.get("final_non_monotonic_count"),
                        metrics.get("final_overlap_count"),
                        metrics.get("final_stable_for_save_reopen"),
                        metrics.get("global_canvas_max_active_segments"),
                        metrics.get("stt1_selected_count"),
                        metrics.get("stt2_selected_count"),
                        metrics.get("stt_recheck_applied_count"),
                        metrics.get("word_precision_count"),
                        metrics.get("stt2_coverage_ratio"),
                        metrics.get("llm_gate_skipped_segments"),
                        metrics.get("avg_stt_score"),
                        metrics.get("stage_trim_total_elapsed_ms"),
                        metrics.get("stage_trim_executed_count"),
                        metrics.get("stage_trim_slowest_stage"),
                        metrics.get("stage_wall_clock_top_stage"),
                        metrics.get("stage_wall_clock_top_elapsed_sec"),
                        metrics.get("stage_wall_clock_stt_primary_transcribe_total_elapsed_sec"),
                        metrics.get("stage_wall_clock_stt_collect_whisperkit_fallback_count"),
                        metrics.get("stage_wall_clock_stt_collect_whisperkit_fallback_total_elapsed_sec"),
                        metrics.get("stage_wall_clock_stt_collect_whisperkit_fallback_max_elapsed_sec"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_total_elapsed_sec"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_prepare_elapsed_sec"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_collect_elapsed_sec"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_annotate_elapsed_sec"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_batch_elapsed_sec"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_range_audio_sec"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_max_range_duration_sec"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_prepared_audio_sec"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_max_prepared_clip_duration_sec"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_applied_segment_count"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_missing_voice_range_count"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_route_hint_range_count"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_low_score_range_count"),
                        metrics.get("stage_wall_clock_stt2_selective_recheck_empty_text_range_count"),
                        metrics.get("stage_wall_clock_word_precision_total_elapsed_sec"),
                        metrics.get("stage_wall_clock_word_precision_prepare_elapsed_sec"),
                        metrics.get("stage_wall_clock_word_precision_collect_elapsed_sec"),
                        metrics.get("stage_wall_clock_word_precision_annotate_elapsed_sec"),
                        metrics.get("stage_wall_clock_word_precision_batch_elapsed_sec"),
                        metrics.get("stage_wall_clock_word_precision_range_audio_sec"),
                        metrics.get("stage_wall_clock_word_precision_max_range_duration_sec"),
                        metrics.get("stage_wall_clock_word_precision_prepared_audio_sec"),
                        metrics.get("stage_wall_clock_word_precision_max_prepared_clip_duration_sec"),
                        metrics.get("stage_wall_clock_word_precision_selected_range_count"),
                        metrics.get("stage_wall_clock_word_precision_precision_review_range_count"),
                        metrics.get("stage_wall_clock_word_precision_needs_review_range_count"),
                        metrics.get("stage_wall_clock_word_precision_red_range_count"),
                        metrics.get("stage_wall_clock_word_precision_yellow_range_count"),
                        metrics.get("stage_wall_clock_word_precision_risk_range_count"),
                        metrics.get("stage_wall_clock_word_precision_missing_word_range_count"),
                        metrics.get("stage_wall_clock_vad_stt_consensus_total_elapsed_sec"),
                        metrics.get("stage_wall_clock_subtitle_postprocess_total_elapsed_sec"),
                        metrics.get("stage_wall_clock_subtitle_postprocess_detail_top_stage"),
                        metrics.get("stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec"),
                        metrics.get("stage_wall_clock_subtitle_postprocess_detail_stage_count"),
                        metrics.get("stage_wall_clock_subtitle_postprocess_detail_total_elapsed_sec"),
                        metrics.get("high_context_boundary_enabled"),
                        metrics.get("high_context_boundary_reason"),
                        metrics.get("high_context_boundary_candidate_pair_count"),
                        metrics.get("high_context_boundary_skipped_pair_count"),
                        metrics.get("high_context_boundary_llm_call_count"),
                        metrics.get("high_context_boundary_failed_call_count"),
                        metrics.get("high_context_boundary_changed_pair_count"),
                        metrics.get("high_context_boundary_max_pairs"),
                        metrics.get("high_context_boundary_keep_decision_count"),
                        metrics.get("high_context_boundary_move_boundary_decision_count"),
                        metrics.get("high_context_boundary_merge_decision_count"),
                        metrics.get("high_context_boundary_invalid_decision_count"),
                        metrics.get("high_context_boundary_correction_request_count"),
                        metrics.get("high_context_boundary_applied_correction_count"),
                        metrics.get("high_context_boundary_keep_cache_enabled"),
                        metrics.get("high_context_boundary_keep_cache_hit_count"),
                        metrics.get("high_context_boundary_keep_cache_miss_count"),
                        metrics.get("high_context_boundary_keep_cache_write_count"),
                        metrics.get("high_context_boundary_elapsed_sec"),
                        metrics.get("subtitle_memory_pressure_stage"),
                        metrics.get("generation_profile_top_stage"),
                        metrics.get("generation_profile_top_cumulative_time_sec"),
                        metrics.get("cut_boundary_profile_top_stage"),
                        metrics.get("cut_boundary_profile_top_cumulative_time_sec"),
                    ],
                )
            )
        )
    _write_text(output_root / "repeat_summary.csv", "\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full-media subtitle verification and save compact artifacts.")
    parser.add_argument("--media", default=str(DEFAULT_MEDIA))
    parser.add_argument("--mode", default="high", choices=["fast", "auto", "high", "stt"])
    parser.add_argument("--output-dir", default=str(LATEST_DIR))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--start-sec", type=float, default=0.0)
    parser.add_argument("--duration-sec", type=float, default=0.0)
    parser.add_argument("--settings-json", default=None, help="Path to JSON file with benchmark setting overrides.")
    parser.add_argument("--setting", action="append", default=[], help="Additional setting override in key=value format.")
    parser.add_argument("--run-prefix", default="")
    parser.add_argument("--profile-functions", action="store_true", help="Write cProfile function hot-path artifacts for this real-media run.")
    parser.add_argument("--profile-top", type=int, default=80, help="Number of function profiler rows to keep.")
    args = parser.parse_args()

    media = Path(args.media).expanduser()
    if not media.exists():
        raise FileNotFoundError(media)
    repeat_count = max(1, int(args.repeat or 1))
    start_sec = max(0.0, float(args.start_sec or 0.0))
    duration_sec = None
    if args.duration_sec and args.duration_sec > 0.0:
        duration_sec = float(args.duration_sec)
    settings_overrides = _load_settings_json(args.settings_json)
    settings_overrides.update(_parse_setting_overrides(args.setting))

    output_dir = Path(args.output_dir).expanduser()
    run_root = output_dir
    if args.run_prefix:
        run_root = output_dir / str(args.run_prefix).strip()
    run_root.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, Any]] = []
    for index in range(1, repeat_count + 1):
        run_payload = _run_single_verification(
            media,
            mode=str(args.mode or "high").strip().lower(),
            output_root=run_root if repeat_count == 1 else run_root,
            settings_overrides=settings_overrides,
            run_index=index if repeat_count > 1 else None,
            start_sec=start_sec,
            duration_sec=duration_sec,
            profile_functions=bool(args.profile_functions),
            profile_top=max(1, int(args.profile_top or 80)),
        )
        run_payload["result_path"] = str(
            (
                run_root / (f"run_{index:02d}" if repeat_count > 1 else ".") / "tinyping_full_verify.json"
            )
            .resolve()
        )
        runs.append(run_payload)

    _emit_repeat_summary(run_root, runs)
    summary = runs[-1]
    failed_reasons = [
        str(item.get("verification_failure_reason") or "").strip()
        for item in runs
        if not bool(item.get("ok", False)) or str(item.get("verification_failure_reason") or "").strip()
    ]
    ok = not failed_reasons
    print(
        json.dumps(
            {
                "ok": ok,
                "mode": summary.get("mode"),
                "run_count": len(runs),
                "run_index": summary.get("run_index"),
                "total_elapsed_sec": summary.get("total_elapsed_sec"),
                "pipeline_elapsed_sec": (summary.get("summary_metrics") or {}).get("pipeline_elapsed_sec"),
                "peak_rss_bytes": summary.get("peak_rss_bytes"),
                "self_review_overall_score": (summary.get("self_review_summary") or {}).get("overall_score"),
                "completion_avg_quality": (summary.get("completion_report") or {}).get("avg_quality_score"),
                "final_segment_count": (summary.get("summary_metrics") or {}).get("final_segment_count"),
                "raw_segment_count": (summary.get("summary_metrics") or {}).get("raw_segment_count"),
                "quality_score": (summary.get("summary_metrics") or {}).get("quality_score"),
                "timing_mae_sec": (summary.get("summary_metrics") or {}).get("timing_mae_sec"),
                "final_overlap_count": (summary.get("summary_metrics") or {}).get("final_overlap_count"),
                "final_stable_for_save_reopen": (summary.get("summary_metrics") or {}).get("final_stable_for_save_reopen"),
                "global_canvas_max_active_segments": (summary.get("summary_metrics") or {}).get("global_canvas_max_active_segments"),
                "stt2_selected_count": (summary.get("summary_metrics") or {}).get("stt2_selected_count"),
                "word_precision_count": (summary.get("summary_metrics") or {}).get("word_precision_count"),
                "llm_rollback_count": (summary.get("completion_report") or {}).get("llm_rollback_count"),
                "llm_gate_skipped_segments": (summary.get("summary_metrics") or {}).get("llm_gate_skipped_segments"),
                "subtitle_memory_pressure_stage": (summary.get("summary_metrics") or {}).get("subtitle_memory_pressure_stage"),
                "stage_wall_clock_top_stage": (summary.get("summary_metrics") or {}).get("stage_wall_clock_top_stage"),
                "stage_wall_clock_top_elapsed_sec": (summary.get("summary_metrics") or {}).get("stage_wall_clock_top_elapsed_sec"),
                "stage_wall_clock_stt_primary_transcribe_total_elapsed_sec": (summary.get("summary_metrics") or {}).get("stage_wall_clock_stt_primary_transcribe_total_elapsed_sec"),
                "stage_wall_clock_stt_collect_whisperkit_fallback_count": (summary.get("summary_metrics") or {}).get("stage_wall_clock_stt_collect_whisperkit_fallback_count"),
                "stage_wall_clock_stt_collect_whisperkit_fallback_total_elapsed_sec": (summary.get("summary_metrics") or {}).get("stage_wall_clock_stt_collect_whisperkit_fallback_total_elapsed_sec"),
                "stage_wall_clock_stt_collect_whisperkit_fallback_max_elapsed_sec": (summary.get("summary_metrics") or {}).get("stage_wall_clock_stt_collect_whisperkit_fallback_max_elapsed_sec"),
                "stage_wall_clock_stt2_selective_recheck_total_elapsed_sec": (summary.get("summary_metrics") or {}).get("stage_wall_clock_stt2_selective_recheck_total_elapsed_sec"),
                "stage_wall_clock_word_precision_total_elapsed_sec": (summary.get("summary_metrics") or {}).get("stage_wall_clock_word_precision_total_elapsed_sec"),
                "stage_wall_clock_vad_stt_consensus_total_elapsed_sec": (summary.get("summary_metrics") or {}).get("stage_wall_clock_vad_stt_consensus_total_elapsed_sec"),
                "stage_wall_clock_subtitle_postprocess_total_elapsed_sec": (summary.get("summary_metrics") or {}).get("stage_wall_clock_subtitle_postprocess_total_elapsed_sec"),
                "stage_wall_clock_subtitle_postprocess_detail_top_stage": (summary.get("summary_metrics") or {}).get("stage_wall_clock_subtitle_postprocess_detail_top_stage"),
                "stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec": (summary.get("summary_metrics") or {}).get("stage_wall_clock_subtitle_postprocess_detail_top_elapsed_sec"),
                "stage_wall_clock_subtitle_postprocess_detail_stage_count": (summary.get("summary_metrics") or {}).get("stage_wall_clock_subtitle_postprocess_detail_stage_count"),
                "stage_wall_clock_subtitle_postprocess_detail_total_elapsed_sec": (summary.get("summary_metrics") or {}).get("stage_wall_clock_subtitle_postprocess_detail_total_elapsed_sec"),
                "high_context_boundary_enabled": (summary.get("summary_metrics") or {}).get("high_context_boundary_enabled"),
                "high_context_boundary_reason": (summary.get("summary_metrics") or {}).get("high_context_boundary_reason"),
                "high_context_boundary_candidate_pair_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_candidate_pair_count"),
                "high_context_boundary_skipped_pair_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_skipped_pair_count"),
                "high_context_boundary_llm_call_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_llm_call_count"),
                "high_context_boundary_failed_call_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_failed_call_count"),
                "high_context_boundary_changed_pair_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_changed_pair_count"),
                "high_context_boundary_max_pairs": (summary.get("summary_metrics") or {}).get("high_context_boundary_max_pairs"),
                "high_context_boundary_keep_decision_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_keep_decision_count"),
                "high_context_boundary_move_boundary_decision_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_move_boundary_decision_count"),
                "high_context_boundary_merge_decision_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_merge_decision_count"),
                "high_context_boundary_invalid_decision_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_invalid_decision_count"),
                "high_context_boundary_correction_request_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_correction_request_count"),
                "high_context_boundary_applied_correction_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_applied_correction_count"),
                "high_context_boundary_keep_cache_enabled": (summary.get("summary_metrics") or {}).get("high_context_boundary_keep_cache_enabled"),
                "high_context_boundary_keep_cache_hit_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_keep_cache_hit_count"),
                "high_context_boundary_keep_cache_miss_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_keep_cache_miss_count"),
                "high_context_boundary_keep_cache_write_count": (summary.get("summary_metrics") or {}).get("high_context_boundary_keep_cache_write_count"),
                "high_context_boundary_elapsed_sec": (summary.get("summary_metrics") or {}).get("high_context_boundary_elapsed_sec"),
                "generation_profile_top_stage": (summary.get("summary_metrics") or {}).get("generation_profile_top_stage"),
                "generation_profile_top_cumulative_time_sec": (summary.get("summary_metrics") or {}).get("generation_profile_top_cumulative_time_sec"),
                "cut_boundary_profile_top_stage": (summary.get("summary_metrics") or {}).get("cut_boundary_profile_top_stage"),
                "cut_boundary_profile_top_cumulative_time_sec": (summary.get("summary_metrics") or {}).get("cut_boundary_profile_top_cumulative_time_sec"),
                "failure_reason": failed_reasons[0] if failed_reasons else "",
                "result_path": runs[0].get("result_path") if runs else None,
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
