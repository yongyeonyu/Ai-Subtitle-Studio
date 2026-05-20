#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio.media_processor import VideoProcessor  # noqa: E402
from core.engine.subtitle_accuracy_pipeline import subtitle_completion_report, subtitle_output_variant_score  # noqa: E402
from core.media_info import probe_media  # noqa: E402
from core.performance import current_resource_snapshot  # noqa: E402
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


def _progress(path: Path, *, stage: str, status: str = "running", **extra: Any) -> None:
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "stage": stage,
    }
    payload.update(extra)
    _write_json(path, payload)


def _snapshot_file(src: Path, dst_dir: Path, filename: str) -> dict[str, Any] | None:
    if not src.exists():
        return None
    dst = dst_dir / filename
    try:
        shutil.copy2(src, dst)
        return json.loads(dst.read_text(encoding="utf-8"))
    except Exception:
        return None


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


def _summary_markdown(payload: dict[str, Any]) -> str:
    media = dict(payload.get("media") or {})
    result = dict(payload.get("result") or {})
    completion = dict(payload.get("completion_report") or {})
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
        f"- Readability score: `{readability_score}`",
        f"- Readability max line chars: `{avg_max_line_chars}`",
        f"- Readability orphan lines: `{orphan_line_segments}`",
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
    error = str(payload.get("error") or "").strip()
    if error:
        lines.extend(["", "## Error", "", "```text", error, "```"])
    return "\n".join(lines) + "\n"


def _summary_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload.get("result") or {})
    completion = dict(payload.get("completion_report") or {})
    self_review = dict(payload.get("self_review_summary") or {})
    variant = dict(payload.get("variant_score") or {})
    readability = dict(result.get("readability") or {})
    return {
        "pipeline_elapsed_sec": result.get("elapsed_sec"),
        "raw_segment_count": result.get("raw_segments"),
        "final_segment_count": result.get("final_segments"),
        "avg_stt_score": result.get("avg_stt_score"),
        "self_review_overall_score": self_review.get("overall_score"),
        "completion_avg_quality": completion.get("avg_quality_score"),
        "llm_rollback_count": completion.get("llm_rollback_count"),
        "output_variant_score": variant.get("score"),
        "readability_score": readability.get("readability_score"),
        "peak_rss_bytes": payload.get("peak_rss_bytes"),
        "free_memory_ratio": (payload.get("resource_before") or {}).get("available_memory_ratio"),
        "free_memory_gb": round(
            float(((payload.get("resource_before") or {}).get("available_memory_bytes", 0) or 0) / (1024 ** 3)),
            4,
        ),
    }


def _run_single_verification(
    media_path: Path,
    *,
    mode: str,
    output_root: Path,
    settings_overrides: dict[str, Any] | None = None,
    run_index: int | None = None,
    start_sec: float = 0.0,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    run_dir = output_root
    if run_index is not None and run_index > 0:
        run_dir = output_root / f"run_{run_index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    progress_path = run_dir / "tinyping_full_verify_progress.json"
    result_path = run_dir / "tinyping_full_verify.json"
    summary_path = run_dir / "tinyping_full_verify.md"
    output_prefix = "full_fast" if mode == "fast" else f"full_{mode}"

    media_info = dict(probe_media(str(media_path)) or {})
    duration_total_sec = float(media_info.get("duration", 0.0) or 0.0)
    created_at = datetime.now().isoformat(timespec="seconds")
    base_settings = _base_benchmark_settings("current")
    if settings_overrides:
        base_settings.update(settings_overrides)
    llm_model = str(base_settings.get("selected_model") or "").strip()
    settings = _mode_profile_settings(base_settings, mode, llm_model=llm_model)
    method = _mode_profile_method(settings)
    run_llm = bool(mode == "high" and llm_model and "사용 안함" not in llm_model)
    run_start = max(0.0, float(start_sec or 0.0))
    run_end = None
    if duration_sec and duration_sec > 0.0:
        run_end = min(duration_total_sec, run_start + float(duration_sec))
        if duration_total_sec > 0.0 and run_end < run_start:
            run_end = run_start

    variant = Variant(
        name=output_prefix,
        phase="full_media_verify",
        description=f"Full media verification for {mode} mode",
        method=method,
        overrides=dict(settings),
        run_llm=run_llm,
    )

    sampler = _PeakRSSSampler()
    payload: dict[str, Any] = {
        "schema": "ai_subtitle_studio.full_media_verify.v1",
        "created_at": created_at,
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
        "settings": {
            key: settings.get(key)
            for key in (
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
            )
        },
        "resource_before": current_resource_snapshot({}),
        "pressure_stages": [],
        "runtime_stage": None,
        "process_snapshot_before": _collect_processes(),
    }
    runtime_monitor_before = _snapshot_file(RUNTIME_MONITOR_FILE, run_dir, "runtime_monitor_before.json")
    subtitle_generation_monitor_before = _snapshot_file(
        MEMORY_MONITOR_FILE,
        run_dir,
        "subtitle_generation_monitor_before.json",
    )
    if runtime_monitor_before is not None:
        payload["runtime_monitor_before"] = runtime_monitor_before
        payload["runtime_stage"] = runtime_monitor_before.get("pressure_stage")
    if subtitle_generation_monitor_before is not None:
        payload["subtitle_generation_monitor_before"] = subtitle_generation_monitor_before

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
    chunk_dir = ""
    try:
        sampler.start()
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
        payload["result"] = result

        output_segments_path = run_dir / variant.name / "output_segments.json"
        rows = json.loads(output_segments_path.read_text(encoding="utf-8"))
        self_review = {}
        if rows and isinstance(rows[0], dict):
            self_review = dict(rows[0].get("subtitle_quality_self_review_summary") or {})
        completion = subtitle_completion_report(rows, settings)
        variant_score = subtitle_output_variant_score(rows, settings)
        payload["self_review_summary"] = self_review
        payload["completion_report"] = completion
        payload["variant_score"] = variant_score
        payload["resource_after"] = current_resource_snapshot({})
        payload["process_snapshot_after"] = _collect_processes()
        payload["runtime_monitor_after"] = _snapshot_file(
            RUNTIME_MONITOR_FILE,
            run_dir,
            "runtime_monitor_after.json",
        )
        payload["subtitle_generation_monitor_after"] = _snapshot_file(
            MEMORY_MONITOR_FILE,
            run_dir,
            "subtitle_generation_monitor_after.json",
        )
        payload["pressure_stages"] = [
            payload.get("runtime_stage"),
            payload.get("runtime_monitor_after", {}).get("pressure_stage"),
        ]
        if payload["runtime_monitor_after"] is not None:
            payload["runtime_stage"] = payload["runtime_monitor_after"].get("pressure_stage")
        payload["peak_rss_bytes"] = int(sampler.peak_rss_bytes or 0)
        payload["total_elapsed_sec"] = round(time.perf_counter() - started, 3)
        payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
        payload["summary_metrics"] = _summary_metrics(payload)
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
        payload["error"] = traceback.format_exc()
        payload["process_snapshot_after"] = _collect_processes()
        payload["runtime_monitor_after"] = _snapshot_file(
            RUNTIME_MONITOR_FILE,
            run_dir,
            "runtime_monitor_after_error.json",
        )
        payload["subtitle_generation_monitor_after"] = _snapshot_file(
            MEMORY_MONITOR_FILE,
            run_dir,
            "subtitle_generation_monitor_after_error.json",
        )
        payload["peak_rss_bytes"] = int(sampler.peak_rss_bytes or 0)
        payload["total_elapsed_sec"] = round(time.perf_counter() - started, 3)
        payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
        payload["summary_metrics"] = _summary_metrics(payload)
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


def _build_repeat_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    elapsed = [item.get("summary_metrics", {}).get("pipeline_elapsed_sec") for item in runs]
    elapsed = [float(v) for v in elapsed if isinstance(v, (int, float))]
    final_segments = [item.get("summary_metrics", {}).get("final_segment_count") for item in runs]
    final_segments = [int(v) for v in final_segments if isinstance(v, (int, float))]
    summary = {
        "run_count": len(runs),
        "pipeline_elapsed_sec": {
            "list": elapsed,
            "avg": round(sum(elapsed) / len(elapsed), 3) if elapsed else None,
            "min": min(elapsed) if elapsed else None,
            "max": max(elapsed) if elapsed else None,
        },
        "final_segment_count": {
            "list": final_segments,
            "avg": round(sum(final_segments) / len(final_segments), 3) if final_segments else None,
            "min": min(final_segments) if final_segments else None,
            "max": max(final_segments) if final_segments else None,
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
        "run_index,pipeline_elapsed_sec,total_elapsed_sec,final_segments,raw_segments,avg_stt_score",
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
                        metrics.get("avg_stt_score"),
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
    print(
        json.dumps(
            {
                "ok": True,
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
                "llm_rollback_count": (summary.get("completion_report") or {}).get("llm_rollback_count"),
                "result_path": runs[0].get("result_path") if runs else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
