#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        f"- Audio extract elapsed: `{payload.get('audio_extract_elapsed_sec')}` sec",
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
    ]
    error = str(payload.get("error") or "").strip()
    if error:
        lines.extend(["", "## Error", "", "```text", error, "```"])
    return "\n".join(lines) + "\n"


def summary_metrics(payload: dict[str, Any]) -> dict[str, Any]:
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
    }


def _attach_summary_metrics(payload: dict[str, Any]) -> None:
    payload.update(summary_metrics(payload))


def run_full_verification(media_path: Path, *, mode: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "tinyping_full_verify_progress.json"
    result_path = output_dir / "tinyping_full_verify.json"
    summary_path = output_dir / "tinyping_full_verify.md"

    media_info = dict(probe_media(str(media_path)) or {})
    duration_sec = float(media_info.get("duration", 0.0) or 0.0)
    created_at = datetime.now().isoformat(timespec="seconds")
    base_settings = _base_benchmark_settings("current")
    llm_model = str(base_settings.get("selected_model") or "").strip()
    settings = _mode_profile_settings(base_settings, mode, llm_model=llm_model)
    method = _mode_profile_method(settings)
    run_llm = bool(mode == "high" and llm_model and "사용 안함" not in llm_model)
    variant = Variant(
        name=f"full_{mode}",
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
        "media": {
            "path": str(media_path),
            "duration_sec": round(duration_sec, 3),
            "width": media_info.get("width"),
            "height": media_info.get("height"),
            "fps": media_info.get("fps"),
            "info_txt": media_info.get("info_txt"),
            "len_txt": media_info.get("len_txt"),
        },
        "mode": mode,
        "method": method,
        "run_llm": run_llm,
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
            )
        },
        "resource_before": current_resource_snapshot({}),
    }
    _progress(progress_path, stage="starting", media=str(media_path), mode=mode)
    started = time.perf_counter()
    chunk_dir = ""
    try:
        sampler.start()
        extractor = VideoProcessor()
        _bind_processor_settings(extractor, settings)
        _progress(progress_path, stage="audio_extract", media=str(media_path), mode=mode)
        extract_started = time.perf_counter()
        chunk_dir, _ = extractor.extract_audio(
            str(media_path),
            target_start_sec=0.0,
            target_end_sec=duration_sec if duration_sec > 0.0 else None,
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
            audio_extract_elapsed_sec=round(audio_extract_elapsed, 3),
            audio_chunk_wavs=payload["audio_chunk_wavs"],
            vad_segments=payload["vad_segments"],
        )
        result = _run_variant(
            variant,
            chunk_source=chunk_path,
            work_dir=output_dir,
            base_settings=settings,
            reference=[],
        )
        payload["result"] = result

        output_segments_path = output_dir / variant.name / "output_segments.json"
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
        payload["peak_rss_bytes"] = int(sampler.peak_rss_bytes or 0)
        payload["total_elapsed_sec"] = round(time.perf_counter() - started, 3)
        payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _attach_summary_metrics(payload)
        _write_json(result_path, payload)
        _write_text(summary_path, _summary_markdown(payload))
        _progress(
            progress_path,
            status="completed",
            stage="completed",
            total_elapsed_sec=payload["total_elapsed_sec"],
            peak_rss_bytes=payload["peak_rss_bytes"],
            self_review_overall_score=payload.get("self_review_overall_score"),
            completion_avg_quality=payload.get("completion_avg_quality"),
            result_path=str(result_path),
        )
        return payload
    except Exception:
        payload["error"] = traceback.format_exc()
        payload["peak_rss_bytes"] = int(sampler.peak_rss_bytes or 0)
        payload["total_elapsed_sec"] = round(time.perf_counter() - started, 3)
        payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _attach_summary_metrics(payload)
        _write_json(result_path, payload)
        _write_text(summary_path, _summary_markdown(payload))
        _progress(
            progress_path,
            status="failed",
            stage="failed",
            total_elapsed_sec=payload["total_elapsed_sec"],
            result_path=str(result_path),
            error=str(payload.get("error") or "").splitlines()[-1] if payload.get("error") else "unknown_error",
        )
        raise
    finally:
        sampler.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full-media subtitle verification and save compact artifacts.")
    parser.add_argument("--media", default=str(DEFAULT_MEDIA))
    parser.add_argument("--mode", default="high", choices=["fast", "auto", "high", "stt"])
    parser.add_argument("--output-dir", default=str(LATEST_DIR))
    args = parser.parse_args()
    media = Path(args.media).expanduser()
    if not media.exists():
        raise FileNotFoundError(media)
    payload = run_full_verification(
        media,
        mode=str(args.mode or "high").strip().lower(),
        output_dir=Path(args.output_dir).expanduser(),
    )
    print(
        json.dumps(
            {
                "ok": True,
                "mode": payload.get("mode"),
                "total_elapsed_sec": payload.get("total_elapsed_sec"),
                "peak_rss_bytes": payload.get("peak_rss_bytes"),
                "self_review_overall_score": payload.get("self_review_overall_score"),
                "completion_avg_quality": payload.get("completion_avg_quality"),
                "final_segment_count": payload.get("final_segment_count"),
                "raw_segment_count": payload.get("raw_segment_count"),
                "llm_rollback_count": payload.get("llm_rollback_count"),
                "result_path": str(Path(args.output_dir).expanduser() / "tinyping_full_verify.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
