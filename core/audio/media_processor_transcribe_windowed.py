# Version: 03.13.08
# Phase: PHASE2
"""Extracted transcription mixin helpers.

Behavior-preserving split from media_processor_transcribe.py.
"""

from __future__ import annotations

import json
import os
import re
import select
import shutil
import sys
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.audio import stt_rescue
from core.audio.audio_chunk_manifest import audio_chunk_manifest, chunk_dir_signature
from core.audio.runtime_cleanup import clear_audio_model_memory_caches
from core.audio.audio_runtime_services import current_memory_pressure_stage, stage_owned_resource_policy
from core.audio.stt_recheck_service import (
    apply_word_precision_segments as apply_word_precision_segments_via_service,
    apply_recheck_selection_to_tracks as apply_recheck_selection_to_tracks_via_service,
    low_score_recheck_overrides as low_score_recheck_overrides_via_service,
    low_score_recheck_ranges as build_low_score_recheck_ranges,
    normalize_scored_tracks as normalize_scored_tracks_via_service,
    prepare_and_collect_recheck_segments as prepare_and_collect_recheck_segments_via_service,
    precision_pass_overrides as precision_pass_overrides_via_service,
    resolve_precision_model as resolve_precision_model_via_service,
    selective_secondary_recheck_ranges as build_selective_secondary_recheck_ranges,
    selective_secondary_recheck_overrides as selective_secondary_recheck_overrides_via_service,
    word_precision_ranges as build_word_precision_ranges,
)
from core.audio.stt_runtime_policy import (
    ensemble_scheduler_context,
    ensemble_scheduler_suffix,
    resolve_runtime_whisper_model,
    whisper_runtime_accelerator,
)
from core.audio.transcribe_policy_helpers import (
    chunk_sort_key,
    chunk_start_from_path,
    mac_primary_fast_native_model,
    segment_chunk_path,
    segment_has_score,
    segment_needs_word_precision,
    segment_overlaps_range,
    segment_score_100,
    setting_bool,
    setting_float,
    stt_candidate_keep_score,
    stt_persistent_runtime_reuse_enabled,
    stt_selective_ensemble_enabled,
    stt_word_timestamps_for_pass,
    wav_duration,
)
from core.audio.transcribe_worker_io import (
    clone_ensemble_chunk_dir,
    parse_worker_json_line,
    whisper_worker_options,
)
from core.audio.whisperkit_empty_fallback import (
    stop_empty_whisperkit_worker,
    whisperkit_empty_fallback_overrides,
    whisperkit_empty_result_fallback_model,
)
from core.engine.subtitle_text_policy import strip_stt_control_tokens
from core.platform_compat import ffmpeg_binary
from core.runtime import config
from core.runtime.logger import get_logger
from core.runtime.multi_process import runtime_parallel_worker_plan
from core.subtitle_quality.candidate_ranker import rank_overlap_candidates
from core.subtitle_quality.hallucination_detector import annotate_segment_hallucination_risk
from core.subtitle_quality.models import attach_asr_metadata
from core.subtitle_quality.vad_alignment_checker import annotate_segment_vad_alignment
from core.audio.media_processor_transcribe import (
    SttWorkerTimeout,
    _clean_whisper_word_text,
    _join_clean_word_texts,
    _parse_worker_json_line,
    _stt_memory_pressure_stage,
)


def _runtime_parallel_worker_plan(*args, **kwargs):
    owner = sys.modules.get("core.audio.media_processor_transcribe")
    planner = getattr(owner, "runtime_parallel_worker_plan", runtime_parallel_worker_plan)
    return planner(*args, **kwargs)


def _current_stt_memory_pressure_stage(settings: dict | None) -> str:
    owner = sys.modules.get("core.audio.media_processor_transcribe")
    stage = getattr(owner, "_stt_memory_pressure_stage", _stt_memory_pressure_stage)
    return str(stage(settings) or "normal")


class VideoProcessorTranscribeWindowedMixin:
    @staticmethod
    def _windowed_float(settings: dict, key: str, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(settings.get(key, default) or default)
        except (TypeError, ValueError):
            value = float(default)
        return max(float(minimum), min(float(maximum), value))
    def _apply_windowed_chunk_finalize(
        self,
        chunk_segs: list[dict],
        item: dict,
        settings: dict,
        *,
        total_chunks: int,
        vad_segments: list[dict] | None = None,
    ) -> list[dict]:
        if not chunk_segs or total_chunks <= 1 or not bool(settings.get("stt_windowed_finalize_enabled", False)):
            return chunk_segs
        chunk_idx = int(item.get("idx", 0) or 0)
        chunk_start = float(item.get("ov_start_offset", 0.0) or 0.0)
        chunk_duration = max(0.001, float(item.get("duration", 0.001) or 0.001))
        chunk_end = chunk_start + chunk_duration
        overlap_sec = self._windowed_float(
            settings,
            "stt_window_overlap_sec",
            float(settings.get("whisper_chunk_overlap_sec", 0.0) or 0.0),
            0.0,
            min(30.0, chunk_duration / 2.0),
        )
        hysteresis_sec = self._windowed_float(
            settings,
            "stt_window_hysteresis_sec",
            max(0.0, overlap_sec / 2.0),
            0.0,
            max(0.0, overlap_sec / 2.0),
        )
        max_shift = self._windowed_float(settings, "stt_window_max_boundary_shift_sec", 0.12, 0.0, 1.0)
        commit_start = chunk_start + hysteresis_sec if chunk_idx > 0 else None
        commit_end = chunk_end - hysteresis_sec if chunk_idx < total_chunks - 1 else None
        if commit_start is None and commit_end is None:
            return chunk_segs

        finalized: list[dict] = []
        for seg in chunk_segs:
            trimmed = self._trim_segment_to_commit_window(
                seg,
                commit_start=commit_start,
                commit_end=commit_end,
                max_shift=max_shift,
                vad_segments=vad_segments or [],
            )
            if trimmed:
                meta = dict(trimmed.get("asr_metadata") or {})
                meta["windowed_finalize"] = {
                    "enabled": True,
                    "chunk_index": chunk_idx,
                    "total_chunks": int(total_chunks),
                    "chunk_start": round(chunk_start, 3),
                    "chunk_end": round(chunk_end, 3),
                    "commit_start": None if commit_start is None else round(commit_start, 3),
                    "commit_end": None if commit_end is None else round(commit_end, 3),
                    "hysteresis_sec": round(hysteresis_sec, 3),
                    "max_boundary_shift_sec": round(max_shift, 3),
                }
                trimmed["asr_metadata"] = meta
                finalized.append(trimmed)
        return finalized
    def _windowed_span_ranges(self, items: list[dict], settings: dict) -> list[dict]:
        if not items or not bool(settings.get("stt_windowed_finalize_enabled", False)):
            return []
        window_sec = self._windowed_float(settings, "stt_window_sec", 0.0, 0.0, 3600.0)
        if window_sec < 30.0:
            return []
        start = float(items[0].get("ov_start_offset", 0.0) or 0.0)
        end = start
        for item in items:
            item_start = float(item.get("ov_start_offset", 0.0) or 0.0)
            item_duration = max(0.001, float(item.get("duration", 0.001) or 0.001))
            end = max(end, item_start + item_duration)
        if end - start <= window_sec + 1e-3:
            return []
        overlap_default = float(settings.get("whisper_chunk_overlap_sec", 0.0) or 0.0)
        overlap_sec = self._windowed_float(
            settings,
            "stt_window_overlap_sec",
            overlap_default,
            0.0,
            min(60.0, window_sec / 2.0),
        )
        ranges = self._split_range_with_overlap(start, end, window_sec, overlap_sec)
        return ranges if len(ranges) > 1 else []
    @staticmethod
    def _window_items_for_range(items: list[dict], start: float, end: float) -> list[dict]:
        selected: list[dict] = []
        lower = float(start)
        upper = float(end)
        for item in list(items or []):
            item_start = float(item.get("ov_start_offset", 0.0) or 0.0)
            item_duration = max(0.001, float(item.get("duration", 0.001) or 0.001))
            item_end = item_start + item_duration
            if item_end <= lower or item_start >= upper:
                continue
            selected.append(dict(item))
        return selected
    @staticmethod
    def _clip_vad_segments_to_window(vad_segments: list[dict] | None, start: float, end: float) -> list[dict]:
        clipped: list[dict] = []
        lower = float(start)
        upper = float(end)
        for seg in list(vad_segments or []):
            try:
                seg_start = float(seg.get("start", 0.0) or 0.0)
                seg_end = float(seg.get("end", seg_start) or seg_start)
            except (TypeError, ValueError):
                continue
            if seg_end <= lower or seg_start >= upper:
                continue
            clipped_seg = dict(seg)
            clipped_seg["start"] = max(lower, seg_start)
            clipped_seg["end"] = min(upper, seg_end)
            if clipped_seg["end"] > clipped_seg["start"]:
                clipped.append(clipped_seg)
        return clipped
    @staticmethod
    def _write_window_wav_slice(
        source: str,
        dest: str,
        *,
        start_offset_sec: float,
        duration_sec: float,
    ) -> None:
        with wave.open(source, "rb") as reader:
            params = reader.getparams()
            rate = max(1, int(reader.getframerate() or 1))
            start_frame = max(0, int(round(float(start_offset_sec) * rate)))
            frame_count = max(1, int(round(float(duration_sec) * rate)))
            reader.setpos(min(start_frame, max(0, reader.getnframes())))
            frames = reader.readframes(frame_count)
        with wave.open(dest, "wb") as writer:
            writer.setparams(params)
            writer.writeframes(frames)
    def _build_window_chunk_dir(
        self,
        base_chunk_dir: str,
        window_items: list[dict],
        *,
        window_index: int,
        total_windows: int,
        window_range: dict,
        vad_segments: list[dict] | None = None,
    ) -> str:
        base_dir = os.path.dirname(os.path.abspath(base_chunk_dir))
        base_name = os.path.basename(os.path.abspath(base_chunk_dir).rstrip(os.sep))
        window_dir = os.path.join(base_dir, f"{base_name}__stt_window_{window_index + 1:03d}")
        shutil.rmtree(window_dir, ignore_errors=True)
        os.makedirs(window_dir, exist_ok=True)

        window_start = float(window_range.get("start", 0.0) or 0.0)
        window_end = float(window_range.get("end", window_start) or window_start)
        route_outputs_by_source: dict[str, str] = {}
        clipped_count = 0
        for item in list(window_items or []):
            source = os.path.abspath(str(item.get("input_path") or ""))
            if not source or not os.path.exists(source):
                continue
            item_start = float(item.get("ov_start_offset", 0.0) or 0.0)
            item_duration = float(item.get("duration", 0.0) or 0.0)
            if item_duration <= 0.001:
                item_duration = self._wav_duration(source) or 0.001
            item_duration = max(0.001, item_duration)
            item_end = item_start + item_duration
            clip_start = max(window_start, item_start)
            clip_end = min(window_end, item_end)
            if clip_end < clip_start + 0.001:
                continue
            full_chunk = clip_start <= item_start + 0.005 and clip_end >= item_end - 0.005
            if full_chunk:
                link_name = os.path.join(window_dir, os.path.basename(source))
                try:
                    os.symlink(source, link_name)
                except Exception:
                    shutil.copy2(source, link_name)
            else:
                # Window workers must see clipped audio, otherwise quarter windows
                # re-transcribe the whole parent chunk and lose the speed benefit.
                clipped_count += 1
                item_idx = int(item.get("idx", clipped_count - 1) or 0)
                link_name = os.path.join(window_dir, f"vad_{item_idx:03d}_{clip_start:.3f}.wav")
                try:
                    self._write_window_wav_slice(
                        source,
                        link_name,
                        start_offset_sec=clip_start - item_start,
                        duration_sec=clip_end - clip_start,
                    )
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [STT window] WAV slice 실패, 원본 청크를 사용합니다: {exc}")
                    link_name = os.path.join(window_dir, os.path.basename(source))
                    try:
                        os.symlink(source, link_name)
                    except Exception:
                        shutil.copy2(source, link_name)
            route_outputs_by_source[os.path.basename(source)] = link_name

        clipped_vad = list(vad_segments or [])
        if clipped_vad:
            with open(os.path.join(window_dir, "vad_strict.json"), "w", encoding="utf-8") as handle:
                json.dump(clipped_vad, handle, ensure_ascii=False, indent=2)
        route_json = os.path.join(base_chunk_dir, "audio_routes.json")
        if os.path.exists(route_json):
            try:
                with open(route_json, "r", encoding="utf-8") as handle:
                    route_rows = json.load(handle)
                wanted = set(route_outputs_by_source)
                clipped_routes = []
                for row in list(route_rows or []):
                    source_name = os.path.basename(str((row or {}).get("path") or ""))
                    if source_name not in wanted:
                        continue
                    out_row = dict(row)
                    out_row["path"] = route_outputs_by_source.get(source_name, out_row.get("path"))
                    clipped_routes.append(out_row)
                if clipped_routes:
                    with open(os.path.join(window_dir, "audio_routes.json"), "w", encoding="utf-8") as handle:
                        json.dump(clipped_routes, handle, ensure_ascii=False, indent=2)
            except Exception:
                pass
        window_meta = {
            "window_index": int(window_index),
            "total_windows": int(total_windows),
            "start": round(float(window_range.get("start", 0.0) or 0.0), 3),
            "end": round(float(window_range.get("end", 0.0) or 0.0), 3),
            "chunk_count": int(len(window_items or [])),
            "clipped_chunk_count": int(clipped_count),
        }
        with open(os.path.join(window_dir, "window_meta.json"), "w", encoding="utf-8") as handle:
            json.dump(window_meta, handle, ensure_ascii=False, indent=2)
        return window_dir
    def _collect_window_transcribe_segments(
        self,
        window_chunk_dir: str,
        *,
        target_end_sec: float | None,
        is_single: bool,
        model_override: str | None,
        log_label: str,
    ) -> list[dict]:
        collected: list[dict] = []
        for chunk_segs, _idx, _total in self.transcribe(
            window_chunk_dir,
            is_fast_mode=False,
            target_end_sec=target_end_sec,
            is_single=is_single,
            model_override=model_override,
            cleanup_chunk_dir=True,
            log_label=log_label,
            preview_callback=None,
            _allow_window_rolling=False,
        ):
            collected.extend([dict(seg) for seg in (chunk_segs or [])])
        return collected
    def _collect_window_transcribe_segments_isolated(
        self,
        window_chunk_dir: str,
        *,
        settings: dict,
        target_end_sec: float | None,
        is_single: bool,
        model_override: str | None,
        log_label: str,
        use_ensemble: bool = False,
    ) -> list[dict]:
        worker = type(self)()
        worker.language = self.language
        worker._fast_mode_overrides = dict(settings or {})
        for attr in (
            "hard_cut_boundaries",
            "_cut_boundary_provisional_rows",
            "_audio_cut_boundary_rows",
            "_saved_cut_boundaries",
        ):
            if hasattr(self, attr):
                try:
                    setattr(worker, attr, getattr(self, attr))
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [STT window] worker state copy skipped ({attr}): {exc}")
        collected: list[dict] = []
        try:
            if use_ensemble:
                # Long-video hot path: each 3 minute window can preserve STT1/STT2
                # quality policy while outer windows run in parallel.
                iterator = worker.transcribe_ensemble(
                    window_chunk_dir,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    cleanup_chunk_dir=True,
                    _allow_window_rolling=False,
                )
            else:
                iterator = worker.transcribe(
                    window_chunk_dir,
                    is_fast_mode=False,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    model_override=model_override,
                    cleanup_chunk_dir=True,
                    log_label=log_label,
                    preview_callback=None,
                    _allow_window_rolling=False,
                )
            for chunk_segs, _idx, _total in iterator:
                collected.extend([dict(seg) for seg in (chunk_segs or [])])
        finally:
            try:
                worker.release_runtime_models()
            except Exception as exc:
                get_logger().log(f"  ⚠️ [STT window] isolated worker cleanup failed: {exc}")
        return collected
    def _stt_quarter_parallel_window_workers(
        self,
        settings: dict,
        total_windows: int,
        *,
        accelerators: list[str] | None = None,
    ) -> tuple[int, dict]:
        window_parallel_enabled = bool(
            settings.get(
                "stt_window_parallel_enabled",
                settings.get("stt_quarter_parallel_experiment_enabled", True),
            )
        )
        if total_windows < 2 or not window_parallel_enabled:
            return 1, {}
        pressure_stage = _current_stt_memory_pressure_stage(settings)
        if pressure_stage == "critical":
            get_logger().log("  🧵 [STT 창 병렬] 메모리 critical: 병렬 worker만 1개로 회수하고 STT 처리는 계속합니다.")
            return 1, {"memory_pressure_stage": pressure_stage}
        quarter_count = int(settings.get("stt_quarter_parallel_count", 4) or 4)
        window_sec = float(settings.get("stt_window_sec", 180.0) or 180.0)
        aggressive_default = bool(settings.get("stt_window_parallel_aggressive_enabled", True))
        # 3분 window는 X5 품질 gate를 통과한 구조라 normal 상태에서만 worker cap을 넓힙니다.
        if "stt_quarter_parallel_max_workers" in settings:
            default_max = quarter_count
        elif aggressive_default and pressure_stage == "normal" and window_sec >= 180.0:
            default_max = quarter_count
        else:
            default_max = 2
        manual_max = int(settings.get("stt_quarter_parallel_max_workers", default_max) or default_max)
        requested = max(1, min(total_windows, quarter_count, manual_max))
        workers, scheduler_meta = _runtime_parallel_worker_plan(
            settings=settings,
            task="stt_window",
            requested=requested,
            workload=total_windows,
            minimum=1,
            maximum=min(4, total_windows),
            reserve_task="stt",
            accelerators=list(accelerators or []),
        )
        return max(1, int(workers or 1)), dict(scheduler_meta or {})
    def _windowed_span_payloads(
        self,
        items: list[dict],
        window_ranges: list[dict],
        vad_strict: list[dict] | None,
    ) -> list[dict]:
        payloads: list[dict] = []
        for window_index, window_range in enumerate(window_ranges):
            window_start = float(window_range.get("start", 0.0) or 0.0)
            window_end = float(window_range.get("end", 0.0) or 0.0)
            payloads.append(
                {
                    "window_index": window_index,
                    "window_range": window_range,
                    "window_items": self._window_items_for_range(items, window_start, window_end),
                    "clipped_vad": self._clip_vad_segments_to_window(vad_strict, window_start, window_end),
                }
            )
        return payloads
    def _drain_committed_window_results(
        self,
        payloads: list[dict],
        window_results: dict[int, list[dict]],
        settings: dict,
        *,
        next_window_index: int,
        previous_end: float,
        total_windows: int,
        log_label: str,
        preview_callback=None,
    ) -> tuple[list[tuple[list[dict], int, int]], int, float]:
        committed_batches: list[tuple[list[dict], int, int]] = []
        while next_window_index < len(payloads):
            payload = payloads[next_window_index]
            window_index = int(payload["window_index"])
            if window_index not in window_results:
                break
            window_range = dict(payload["window_range"])
            clipped_vad = list(payload["clipped_vad"] or [])
            # 병렬 수집 후에도 확정은 시간 순서로만 수행해야 overlap dedupe 품질이 유지됩니다.
            committed = self._apply_windowed_span_finalize(
                window_results.pop(window_index, []),
                window_range,
                settings,
                window_index=window_index,
                total_windows=total_windows,
                previous_end=previous_end,
                vad_segments=clipped_vad,
            )
            if committed:
                previous_end = float(committed[-1].get("end", previous_end) or previous_end)
                if callable(preview_callback):
                    try:
                        preview_callback(committed, log_label)
                    except Exception as exc:
                        get_logger().log(f"  ⚠️ [{log_label}] window preview callback failed: {exc}")
            get_logger().log(
                f"  💾 [{log_label}] 창 {window_index + 1}/{total_windows} 확정 "
                f"세그먼트 {len(committed)}개"
            )
            committed_batches.append((committed, window_index + 1, total_windows))
            next_window_index += 1
        return committed_batches, next_window_index, previous_end
    def _transcribe_windowed_spans_parallel(
        self,
        chunk_dir: str,
        payloads: list[dict],
        settings: dict,
        *,
        parallel_workers: int,
        total_windows: int,
        target_end_sec: float | None,
        is_single: bool,
        model_override: str | None,
        log_label: str,
        use_ensemble_windows: bool = False,
        preview_callback=None,
    ):
        def _run_window(payload: dict) -> tuple[int, list[dict]]:
            window_index = int(payload["window_index"])
            window_range = dict(payload["window_range"])
            window_items = list(payload["window_items"] or [])
            clipped_vad = list(payload["clipped_vad"] or [])
            if not window_items:
                return window_index, []
            get_logger().log(
                f"  🪟 [{log_label}] 창 {window_index + 1}/{total_windows} "
                f"{float(window_range.get('start', 0.0) or 0.0):.1f}s~"
                f"{float(window_range.get('end', 0.0) or 0.0):.1f}s "
                f"(청크 {len(window_items)}개)"
            )
            window_chunk_dir = self._build_window_chunk_dir(
                chunk_dir,
                window_items,
                window_index=window_index,
                total_windows=total_windows,
                window_range=window_range,
                vad_segments=clipped_vad,
            )
            window_label = f"{log_label}-window-{window_index + 1}/{total_windows}"
            return window_index, self._collect_window_transcribe_segments_isolated(
                window_chunk_dir,
                settings=settings,
                target_end_sec=target_end_sec,
                is_single=is_single,
                model_override=model_override,
                log_label=window_label,
                use_ensemble=use_ensemble_windows,
            )

        window_results: dict[int, list[dict]] = {}
        next_window_index = 0
        previous_end = 0.0
        with ThreadPoolExecutor(max_workers=parallel_workers, thread_name_prefix="stt-window") as executor:
            futures = [executor.submit(_run_window, payload) for payload in payloads]
            for future in as_completed(futures):
                window_index, window_segments = future.result()
                window_results[window_index] = window_segments
                # 앞 창이 끝나는 즉시 확정/하류 최적화로 넘겨 later window STT와 겹치게 한다.
                ready_batches, next_window_index, previous_end = self._drain_committed_window_results(
                    payloads,
                    window_results,
                    settings,
                    next_window_index=next_window_index,
                    previous_end=previous_end,
                    total_windows=total_windows,
                    log_label=log_label,
                    preview_callback=preview_callback,
                )
                for committed, ordinal, total in ready_batches:
                    yield committed, ordinal, total
    def _apply_windowed_span_finalize(
        self,
        window_segments: list[dict],
        window_range: dict,
        settings: dict,
        *,
        window_index: int,
        total_windows: int,
        previous_end: float,
        vad_segments: list[dict] | None = None,
    ) -> list[dict]:
        if not window_segments:
            return []
        window_start = float(window_range.get("start", 0.0) or 0.0)
        window_end = float(window_range.get("end", window_start) or window_start)
        overlap_default = float(settings.get("whisper_chunk_overlap_sec", 0.0) or 0.0)
        overlap_sec = self._windowed_float(
            settings,
            "stt_window_overlap_sec",
            overlap_default,
            0.0,
            min(60.0, max(1.0, window_end - window_start) / 2.0),
        )
        hysteresis_sec = self._windowed_float(
            settings,
            "stt_window_hysteresis_sec",
            max(0.0, overlap_sec / 2.0),
            0.0,
            max(0.0, overlap_sec / 2.0),
        )
        max_shift = self._windowed_float(settings, "stt_window_max_boundary_shift_sec", 0.12, 0.0, 1.0)
        commit_start = window_start + hysteresis_sec if window_index > 0 else None
        commit_end = window_end - hysteresis_sec if window_index < total_windows - 1 else None

        finalized: list[dict] = []
        for seg in list(window_segments or []):
            trimmed = self._trim_segment_to_commit_window(
                seg,
                commit_start=commit_start,
                commit_end=commit_end,
                max_shift=max_shift,
                vad_segments=vad_segments or [],
            )
            if not trimmed:
                continue
            meta = dict(trimmed.get("asr_metadata") or {})
            meta["windowed_span_finalize"] = {
                "enabled": True,
                "window_index": int(window_index),
                "total_windows": int(total_windows),
                "window_start": round(window_start, 3),
                "window_end": round(window_end, 3),
                "commit_start": None if commit_start is None else round(commit_start, 3),
                "commit_end": None if commit_end is None else round(commit_end, 3),
                "hysteresis_sec": round(hysteresis_sec, 3),
                "max_boundary_shift_sec": round(max_shift, 3),
            }
            trimmed["asr_metadata"] = meta
            finalized.append(trimmed)
        return self._dedupe_overlapping_segments(
            finalized,
            previous_end=previous_end,
            dedup_window=float(settings.get("sub_dedup_window", 0.5) or 0.5),
            vad_segments=vad_segments or [],
        )
    def _transcribe_with_windowed_spans(
        self,
        chunk_dir: str,
        items: list[dict],
        settings: dict,
        *,
        vad_strict: list[dict] | None,
        target_end_sec: float | None,
        is_single: bool,
        model_override: str | None,
        log_label: str,
        use_ensemble_windows: bool = False,
        preview_callback=None,
    ):
        window_ranges = self._windowed_span_ranges(items, settings)
        if not window_ranges:
            return
        overlap_default = float(settings.get("whisper_chunk_overlap_sec", 0.0) or 0.0)
        overlap_sec = self._windowed_float(
            settings,
            "stt_window_overlap_sec",
            overlap_default,
            0.0,
            min(60.0, float(settings.get("stt_window_sec", 180.0) or 180.0) / 2.0),
        )
        hysteresis_sec = self._windowed_float(
            settings,
            "stt_window_hysteresis_sec",
            max(0.0, overlap_sec / 2.0),
            0.0,
            max(0.0, overlap_sec / 2.0),
        )
        total_windows = len(window_ranges)
        get_logger().log(
            f"🪟 [{log_label}] 롤링 STT 창 활성화: {total_windows}개 창 · "
            f"window {float(settings.get('stt_window_sec', 180.0) or 180.0):.1f}초 · "
            f"overlap {overlap_sec:.1f}초 · hysteresis {hysteresis_sec:.1f}초"
            + (" · 창별 STT1/STT2 앙상블" if use_ensemble_windows else "")
        )

        window_accelerators: list[str] = []
        if use_ensemble_windows:
            primary_model = str(model_override or settings.get("selected_whisper_model") or self.whisper_model or "")
            secondary_model = str(settings.get("selected_whisper_model_secondary") or "").strip()
            if secondary_model:
                primary_accel, secondary_accel, window_backend_mix = self._ensemble_scheduler_context(
                    primary_model,
                    secondary_model,
                    settings,
                )
                window_accelerators = [primary_accel, secondary_accel]
            else:
                window_backend_mix = self._whisper_runtime_accelerator(primary_model, settings).upper()
                window_accelerators = [window_backend_mix]
        else:
            primary_model = str(model_override or settings.get("selected_whisper_model") or self.whisper_model or "")
            window_backend_mix = self._whisper_runtime_accelerator(primary_model, settings).upper()
            window_accelerators = [window_backend_mix]
        parallel_workers, scheduler_meta = self._stt_quarter_parallel_window_workers(
            settings,
            total_windows,
            accelerators=window_accelerators,
        )
        if parallel_workers > 1:
            suffix = self._ensemble_scheduler_suffix(scheduler_meta, f"windowed {window_backend_mix}")
            get_logger().log(
                f"  🧵 [{log_label}] STT rolling window 병렬 활성화: "
                f"{parallel_workers}개 워커{suffix}"
            )
            try:
                yield from self._transcribe_windowed_spans_parallel(
                    chunk_dir,
                    self._windowed_span_payloads(items, window_ranges, vad_strict),
                    settings,
                    parallel_workers=parallel_workers,
                    total_windows=total_windows,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    model_override=model_override,
                    log_label=log_label,
                    use_ensemble_windows=use_ensemble_windows,
                    preview_callback=preview_callback,
                )
                return
            except Exception as exc:
                # 병렬 worker 실패 시 같은 창/품질 규칙의 serial 경로로 되돌려 생성 실패를 막습니다.
                get_logger().log(f"  ⚠️ [{log_label}] STT rolling window 병렬 실패, serial로 재시도: {exc}")

        previous_end = 0.0
        for window_index, window_range in enumerate(window_ranges):
            window_items = self._window_items_for_range(
                items,
                float(window_range.get("start", 0.0) or 0.0),
                float(window_range.get("end", 0.0) or 0.0),
            )
            clipped_vad = self._clip_vad_segments_to_window(
                vad_strict,
                float(window_range.get("start", 0.0) or 0.0),
                float(window_range.get("end", 0.0) or 0.0),
            )
            if not window_items:
                yield [], window_index + 1, total_windows
                continue
            get_logger().log(
                f"  🪟 [{log_label}] 창 {window_index + 1}/{total_windows} "
                f"{float(window_range.get('start', 0.0) or 0.0):.1f}s~"
                f"{float(window_range.get('end', 0.0) or 0.0):.1f}s "
                f"(청크 {len(window_items)}개)"
            )
            window_chunk_dir = self._build_window_chunk_dir(
                chunk_dir,
                window_items,
                window_index=window_index,
                total_windows=total_windows,
                window_range=window_range,
                vad_segments=clipped_vad,
            )
            window_label = f"{log_label}-window-{window_index + 1}/{total_windows}"
            window_segments = self._collect_window_transcribe_segments(
                window_chunk_dir,
                target_end_sec=target_end_sec,
                is_single=is_single,
                model_override=model_override,
                log_label=window_label,
            )
            committed = self._apply_windowed_span_finalize(
                window_segments,
                window_range,
                settings,
                window_index=window_index,
                total_windows=total_windows,
                previous_end=previous_end,
                vad_segments=clipped_vad,
            )
            if committed:
                previous_end = float(committed[-1].get("end", previous_end) or previous_end)
                if callable(preview_callback):
                    try:
                        preview_callback(committed, log_label)
                    except Exception:
                        pass
            get_logger().log(
                f"  💾 [{log_label}] 창 {window_index + 1}/{total_windows} 확정 "
                f"세그먼트 {len(committed)}개"
            )
            yield committed, window_index + 1, total_windows
    def _trim_segment_to_commit_window(
        self,
        seg: dict,
        *,
        commit_start: float | None,
        commit_end: float | None,
        max_shift: float,
        vad_segments: list[dict],
    ) -> dict | None:
        start = float(seg.get("start", 0.0) or 0.0)
        end = float(seg.get("end", start) or start)
        lower = None if commit_start is None else float(commit_start) - float(max_shift)
        upper = None if commit_end is None else float(commit_end) + float(max_shift)
        if lower is not None and end <= lower:
            return None
        if upper is not None and start >= upper:
            return None

        words = list(seg.get("words") or [])
        if words:
            kept_words = []
            for word in words:
                try:
                    word_start = float(word.get("start", 0.0) or 0.0)
                    word_end = float(word.get("end", word_start) or word_start)
                except (TypeError, ValueError):
                    continue
                midpoint = (word_start + word_end) / 2.0
                if lower is not None and midpoint < lower:
                    continue
                if upper is not None and midpoint > upper:
                    continue
                kept_words.append(dict(word))
            if not kept_words:
                return None
            out = dict(seg)
            out["words"] = kept_words
            out["start"] = max(start, float(kept_words[0].get("start", start) or start))
            out["end"] = min(end, float(kept_words[-1].get("end", end) or end))
            text = _join_clean_word_texts(kept_words)
            if text:
                out["text"] = text
            previous_meta = dict(out.get("asr_metadata") or {})
            out = attach_asr_metadata(out, backend=previous_meta.get("backend"))
            merged_meta = dict(previous_meta)
            merged_meta.update(dict(out.get("asr_metadata") or {}))
            out["asr_metadata"] = merged_meta
            if vad_segments:
                out = annotate_segment_vad_alignment(out, vad_segments)
            return annotate_segment_hallucination_risk(out, vad_segments=vad_segments)

        out = dict(seg)
        if lower is not None:
            out["start"] = max(start, float(commit_start))
        if upper is not None:
            out["end"] = min(end, float(commit_end))
        if float(out.get("end", 0.0) or 0.0) <= float(out.get("start", 0.0) or 0.0) + 0.03:
            return None
        if vad_segments:
            out = annotate_segment_vad_alignment(out, vad_segments)
        return annotate_segment_hallucination_risk(out, vad_segments=vad_segments)
    def _dedupe_overlapping_segments(
        self,
        chunk_segs: list[dict],
        previous_end: float,
        dedup_window: float = 0.5,
        vad_segments: list[dict] | None = None,
    ) -> list[dict]:
        if not chunk_segs or previous_end <= 0.0:
            return chunk_segs

        boundary = max(0.0, float(previous_end) - min(max(float(dedup_window or 0.0), 0.0), 0.15))
        cleaned = []
        for seg in chunk_segs:
            words = [
                dict(w)
                for w in (seg.get("words") or [])
                if float(w.get("end", 0.0) or 0.0) > boundary
            ]
            if seg.get("words"):
                if not words:
                    continue
                trimmed = dict(seg)
                trimmed["words"] = words
                trimmed["start"] = float(words[0].get("start", seg.get("start", previous_end)) or previous_end)
                trimmed["end"] = float(words[-1].get("end", seg.get("end", previous_end)) or previous_end)
                if words and words != seg.get("words"):
                    text = _join_clean_word_texts(words)
                    if text:
                        trimmed["text"] = text
                    trimmed = attach_asr_metadata(trimmed, backend=(trimmed.get("asr_metadata") or {}).get("backend"))
                    if vad_segments:
                        trimmed = annotate_segment_vad_alignment(trimmed, vad_segments)
                    trimmed = annotate_segment_hallucination_risk(trimmed, vad_segments=vad_segments or [])

                ranked = rank_overlap_candidates(
                    [
                        {"candidate_id": "original", "segment": seg},
                        {"candidate_id": "trimmed", "segment": trimmed, "score_bonus": 2.0},
                    ],
                    vad_segments=vad_segments or [],
                    previous_end=previous_end,
                )
                selected_id = str(ranked[0].get("candidate_id") or "trimmed")
                selected_score = ranked[0].get("score")
                selected = dict(ranked[0].get("segment") or trimmed)
                if selected.get("start", 0.0) < previous_end and trimmed.get("end", 0.0) > trimmed.get("start", 0.0):
                    selected = trimmed
                    selected_id = "trimmed"
                    for item in ranked:
                        if item.get("candidate_id") == "trimmed":
                            selected_score = item.get("score")
                            break
                asr_metadata = dict(selected.get("asr_metadata") or {})
                asr_metadata["overlap_candidate"] = {
                    "selected": selected_id,
                    "score": selected_score,
                    "boundary": round(boundary, 6),
                }
                selected["asr_metadata"] = asr_metadata
                cleaned.append(selected)
                continue

            exact_end = float(seg.get("end", 0.0) or 0.0)
            if exact_end <= boundary:
                continue
            new_seg = dict(seg)
            new_seg["start"] = max(float(new_seg.get("start", 0.0) or 0.0), previous_end)
            if new_seg["end"] > new_seg["start"]:
                if vad_segments:
                    new_seg = annotate_segment_vad_alignment(new_seg, vad_segments)
                new_seg = annotate_segment_hallucination_risk(new_seg, vad_segments=vad_segments or [])
                cleaned.append(new_seg)

        return cleaned
