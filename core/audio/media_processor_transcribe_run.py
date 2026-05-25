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

class VideoProcessorTranscribeRunMixin:
    def transcribe_ensemble(
        self,
        chunk_dir: str,
        target_end_sec: float = None,
        is_single: bool = False,
        preview_callback=None,
        cleanup_chunk_dir: bool = True,
        _allow_window_rolling: bool = True,
    ):
        chunks, q, _t_sec = self._scan_transcribe_chunks(chunk_dir)
        if not chunks:
            yield [], 0, 0
            return

        vad_strict = []
        vad_json = os.path.join(chunk_dir, "vad_strict.json")
        if os.path.exists(vad_json):
            try:
                with open(vad_json, "r", encoding="utf-8") as handle:
                    vad_strict = json.load(handle)
            except Exception:
                vad_strict = []

        s = self._load_all_settings()
        runtime_overrides = getattr(self, "_fast_mode_overrides", None)
        if isinstance(runtime_overrides, dict) and runtime_overrides:
            s = {**dict(s or {}), **runtime_overrides}
        window_ranges = self._windowed_span_ranges(q, s)
        if _allow_window_rolling and window_ranges:
            self._run_early_stt_preview_burst(
                chunk_dir,
                q,
                s,
                target_end_sec=target_end_sec,
                is_single=is_single,
                model=s.get("selected_whisper_model", self.whisper_model),
                log_label="STT1",
                preview_callback=preview_callback,
                vad_strict=vad_strict,
            )
            had_window_error = False
            try:
                emitted_window_segments = 0
                checked_first_window = False
                for chunk_segs, c_idx, t_total in self._transcribe_with_windowed_spans(
                    chunk_dir,
                    q,
                    s,
                    vad_strict=vad_strict,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    model_override=None,
                    log_label="STT-ENSEMBLE",
                    use_ensemble_windows=self._setting_bool(s, "stt_window_ensemble_enabled", False),
                    preview_callback=preview_callback,
                ):
                    if not checked_first_window:
                        checked_first_window = True
                        head_gap, first_start, head_gap_sec = self._stt_window_head_gap_fallback_needed(
                            q,
                            s,
                            chunk_segs,
                            vad_strict=vad_strict,
                        )
                        if head_gap:
                            first_text = "none" if first_start is None else f"{first_start:.1f}s"
                            get_logger().log(
                                "  ⚠️ [STT-ENSEMBLE] rolling-window 첫 확정 구간이 "
                                f"head {head_gap_sec:.0f}s 밖에서 시작({first_text})해 "
                                "같은 품질 설정의 serial STT fallback으로 전환합니다."
                            )
                            yield from self._transcribe_ensemble_zero_window_fallback(
                                chunk_dir,
                                target_end_sec=target_end_sec,
                                is_single=is_single,
                                preview_callback=preview_callback,
                            )
                            return
                    emitted_window_segments += len(chunk_segs or [])
                    yield chunk_segs, c_idx, t_total
                if emitted_window_segments == 0 and self._stt_window_zero_result_fallback_enabled(s):
                    get_logger().log(
                        "  ⚠️ [STT-ENSEMBLE] rolling-window 결과가 0개라 "
                        "같은 품질 설정으로 serial STT fallback을 1회 실행합니다."
                    )
                    yield from self._transcribe_ensemble_zero_window_fallback(
                        chunk_dir,
                        target_end_sec=target_end_sec,
                        is_single=is_single,
                        preview_callback=preview_callback,
                    )
            except Exception:
                had_window_error = True
                raise
            finally:
                if cleanup_chunk_dir:
                    shutil.rmtree(chunk_dir, ignore_errors=True)
                if had_window_error:
                    get_logger().log("[WARN] STT-ENSEMBLE rolling-window transcription aborted due to worker failure")
                else:
                    get_logger().log("[DONE] STT-ENSEMBLE rolling-window transcription completed")
            return

        from core.audio.npu_acceleration import prefer_npu_whisper_model

        raw_primary_model = s.get("selected_whisper_model", self.whisper_model)
        raw_secondary_model = s.get("selected_whisper_model_secondary", "")
        primary_model = prefer_npu_whisper_model(raw_primary_model, s, purpose="stt", log_label="STT1")
        secondary_model = prefer_npu_whisper_model(raw_secondary_model, s, purpose="stt", log_label="STT2")
        primary_model, primary_runtime_fallback = self._resolve_runtime_whisper_model(primary_model, log_label="STT1")
        secondary_model, secondary_runtime_fallback = self._resolve_runtime_whisper_model(secondary_model, log_label="STT2")
        if (
            secondary_model
            and secondary_model == primary_model
            and str(raw_secondary_model or "").strip()
            and str(raw_secondary_model or "").strip() != str(raw_primary_model or "").strip()
            and not secondary_runtime_fallback
        ):
            secondary_model = str(raw_secondary_model or "").strip()
            get_logger().log("  ↩️ [STT2] NPU 라우팅이 STT1/STT2를 동일 모델로 만들어 STT2는 원래 모델을 유지합니다.")
        if not secondary_model or secondary_model == primary_model:
            yield from self.transcribe(
                chunk_dir,
                is_fast_mode=False,
                target_end_sec=target_end_sec,
                is_single=is_single,
                model_override=primary_model,
                cleanup_chunk_dir=cleanup_chunk_dir,
                log_label="STT1",
                preview_callback=preview_callback,
                _allow_window_rolling=False,
            )
            return
        primary_accel, secondary_accel, backend_mix = self._ensemble_scheduler_context(
            primary_model,
            secondary_model,
            s,
        )

        if self._stt_selective_ensemble_enabled(s):
            yield from self._transcribe_selective_ensemble(
                chunk_dir,
                primary_model,
                secondary_model,
                s,
                target_end_sec=target_end_sec,
                is_single=is_single,
                preview_callback=preview_callback,
                cleanup_chunk_dir=cleanup_chunk_dir,
            )
            return

        get_logger().log(
            "\n🎧 [STT 앙상블] STT1/STT2 병렬 인식 시작 "
            f"(STT1: {primary_model.split(chr(47))[-1]}, STT2: {secondary_model.split(chr(47))[-1]}, {backend_mix})"
        )
        self._notify_stage("⏳ [STT] STT1/STT2 병렬 인식 중")
        results: dict[str, list[dict]] = {"STT1": [], "STT2": []}
        errors: dict[str, BaseException] = {}
        result_lock = threading.Lock()
        error_lock = threading.Lock()
        ensemble_chunk_dirs: dict[str, str] = {}

        def _run(label: str, model: str):
            try:
                local_chunk_dir = ensemble_chunk_dirs.get(label, chunk_dir)
                local_result = self._collect_transcribe_result(
                    local_chunk_dir,
                    model,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    label=label,
                    preview_callback=self._ensemble_preview_callback(label, preview_callback),
                    settings_overrides=s,
                )
                with result_lock:
                    results[label] = local_result
            except BaseException as exc:
                with error_lock:
                    errors[label] = exc

        try:
            stt_workers, scheduler_meta = runtime_parallel_worker_plan(
                settings=s,
                task="stt",
                requested=2,
                workload=2,
                minimum=1,
                maximum=2,
                reserve_task="stt",
                accelerators=[primary_accel, secondary_accel],
            )
            suffix = self._ensemble_scheduler_suffix(scheduler_meta, backend_mix)
            get_logger().log(f"  🧵 [STT 앙상블] 리소스 자동 스케줄러: {stt_workers}개 워커{suffix}")
            for label in ("STT1", "STT2"):
                ensemble_chunk_dirs[label] = self._clone_ensemble_chunk_dir(chunk_dir, label)
            with ThreadPoolExecutor(max_workers=stt_workers, thread_name_prefix="stt-ensemble") as executor:
                futures = [
                    executor.submit(_run, "STT1", primary_model),
                    executor.submit(_run, "STT2", secondary_model),
                ]
                for future in futures:
                    future.result()
            for label, exc in errors.items():
                get_logger().log(f"  ⚠️ [STT 앙상블] {label} 인식 실패: {exc}")
            if not results["STT1"] and not results["STT2"]:
                raise RuntimeError("STT 앙상블 결과가 비어 있습니다")
            vad_strict = []
            vad_json = os.path.join(chunk_dir, "vad_strict.json")
            if os.path.exists(vad_json):
                try:
                    with open(vad_json, "r", encoding="utf-8") as f:
                        vad_strict = json.load(f)
                except Exception:
                    vad_strict = []
            scoring_enabled = True
            if scoring_enabled:
                try:
                    from core.audio.stt_candidate_scorer import (
                        annotate_stt_candidate_tracks,
                        average_stt_score,
                    )

                    scored_tracks = annotate_stt_candidate_tracks(
                        {"STT1": results["STT1"], "STT2": results["STT2"]},
                        vad_segments=vad_strict,
                        settings=s,
                    )
                    results["STT1"] = scored_tracks.get("STT1", results["STT1"])
                    results["STT2"] = scored_tracks.get("STT2", results["STT2"])
                    results = self._normalize_scored_stt_tracks(results, s)
                    get_logger().log(
                        "  📊 [STT 점수] "
                        f"STT1 평균 {average_stt_score(results['STT1']):.1f}점 / "
                        f"STT2 평균 {average_stt_score(results['STT2']):.1f}점"
                    )
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [STT 점수] 후보 점수 계산 실패, 기존 병합 유지: {exc}")

            try:
                if scoring_enabled:
                    results = self._recheck_low_score_stt_ranges(
                        chunk_dir,
                        results,
                        s,
                        vad_strict,
                        primary_model,
                    )
                    from core.audio.stt_candidate_scorer import annotate_stt_candidate_tracks

                    rescored_tracks = annotate_stt_candidate_tracks(
                        {"STT1": results["STT1"], "STT2": results["STT2"]},
                        vad_segments=vad_strict,
                        settings=s,
                    )
                    results["STT1"] = rescored_tracks.get("STT1", results["STT1"])
                    results["STT2"] = rescored_tracks.get("STT2", results["STT2"])
                    results = self._normalize_scored_stt_tracks(results, s)
            except Exception as exc:
                get_logger().log(f"  ⚠️ [STT 재검사] 오류로 기존 STT 후보를 유지합니다: {exc}")

            from core.audio.stt_ensemble import merge_stt_outputs

            merged = merge_stt_outputs(results["STT1"], results["STT2"])
            if vad_strict and bool(s.get("vad_post_stt_align_enabled", True)):
                from core.subtitle_quality.vad_alignment_checker import adjust_segments_to_vad_boundaries

                self._notify_stage("⏳ [VAD] 앙상블 자막 위치 재계산 중")
                merged, adjusted_count = adjust_segments_to_vad_boundaries(
                    merged,
                    vad_strict,
                    max_shift_sec=float(s.get("vad_post_stt_max_shift_sec", 0.7) or 0.7),
                    edge_pad_sec=float(s.get("vad_post_stt_edge_pad_sec", 0.04) or 0.04),
                )
                get_logger().log(f"  🎯 [VAD 후처리] 앙상블 자막 위치 {adjusted_count}개 보정")
            get_logger().log(
                "  ✅ [STT 앙상블] 후보 병합 완료 "
                f"(STT1 {len(results['STT1'])}개 / STT2 {len(results['STT2'])}개 → {len(merged)}개, "
                "단어 단위 ROVER · 저신뢰 STT1 구간 STT2 보강)"
            )
            yield merged, 1, 1
        finally:
            for local_chunk_dir in ensemble_chunk_dirs.values():
                shutil.rmtree(local_chunk_dir, ignore_errors=True)
            if cleanup_chunk_dir:
                shutil.rmtree(chunk_dir, ignore_errors=True)
            self._release_after_transcribe_job("STT 앙상블")
    def _scan_transcribe_chunks(self, chunk_dir: str) -> tuple[list[str], list[dict], float]:
        manifest = self._audio_chunk_manifest(chunk_dir, fallback_step_sec=30.0)
        chunks = [str(row.get("name") or "") for row in manifest if str(row.get("name") or "")]
        t_sec = 1.0
        items: list[dict] = []
        for i, row in enumerate(manifest):
            cp = str(row.get("path") or os.path.join(chunk_dir, str(row.get("name") or "")))
            ov_start = float(row.get("start", i * 30.0) or 0.0)
            chunk_duration = float(row.get("duration", 0.0) or 0.0)
            if chunk_duration <= 0.0:
                chunk_duration = 30.0
            chunk_end = ov_start + chunk_duration
            items.append({
                "idx": i,
                "input_path": cp,
                "ov_start_offset": ov_start,
                "duration": max(0.001, float(chunk_duration or 0.001)),
            })
            t_sec = max(t_sec, chunk_end)
        return chunks, items, t_sec
    def transcribe(
        self,
        chunk_dir: str,
        is_fast_mode: bool = False,
        target_end_sec: float = None,
        is_single: bool = False,
        model_override: str | None = None,
        cleanup_chunk_dir: bool = True,
        log_label: str = "STT",
        preview_callback=None,
        _allow_window_rolling: bool = True,
    ):
        _ = is_fast_mode
        chunks, q, t_sec = self._scan_transcribe_chunks(chunk_dir)
        if not chunks:
            yield [], 0, 0
            return

        vad_strict = []
        vad_json = os.path.join(chunk_dir, "vad_strict.json")
        if os.path.exists(vad_json):
            try:
                with open(vad_json, "r", encoding="utf-8") as f:
                    vad_strict = json.load(f)
            except Exception:
                pass
        route_hints = self._load_audio_route_hints(chunk_dir)

        total = len(chunks)
        _s = self._load_all_settings()
        runtime_overrides = getattr(self, "_fast_mode_overrides", None)
        if isinstance(runtime_overrides, dict) and runtime_overrides:
            _s = {**dict(_s or {}), **runtime_overrides}

        window_ranges = self._windowed_span_ranges(q, _s)
        if _allow_window_rolling and window_ranges:
            self._run_early_stt_preview_burst(
                chunk_dir,
                q,
                _s,
                target_end_sec=target_end_sec,
                is_single=is_single,
                model=model_override or _s.get("selected_whisper_model", self.whisper_model),
                log_label=log_label,
                preview_callback=preview_callback,
                vad_strict=vad_strict,
            )
            had_window_error = False
            try:
                emitted_window_segments = 0
                checked_first_window = False
                for chunk_segs, c_idx, t_total in self._transcribe_with_windowed_spans(
                    chunk_dir,
                    q,
                    _s,
                    vad_strict=vad_strict,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    model_override=model_override,
                    log_label=log_label,
                    preview_callback=preview_callback,
                ):
                    if not checked_first_window:
                        checked_first_window = True
                        head_gap, first_start, head_gap_sec = self._stt_window_head_gap_fallback_needed(
                            q,
                            _s,
                            chunk_segs,
                            vad_strict=vad_strict,
                        )
                        if head_gap:
                            first_text = "none" if first_start is None else f"{first_start:.1f}s"
                            get_logger().log(
                                f"  ⚠️ [{log_label}] rolling-window 첫 확정 구간이 "
                                f"head {head_gap_sec:.0f}s 밖에서 시작({first_text})해 "
                                "같은 품질 설정의 serial STT fallback으로 전환합니다."
                            )
                            yield from self._transcribe_zero_window_fallback(
                                chunk_dir,
                                target_end_sec=target_end_sec,
                                is_single=is_single,
                                model_override=model_override,
                                log_label=log_label,
                                preview_callback=preview_callback,
                            )
                            return
                    emitted_window_segments += len(chunk_segs or [])
                    yield chunk_segs, c_idx, t_total
                if emitted_window_segments == 0 and self._stt_window_zero_result_fallback_enabled(_s):
                    get_logger().log(
                        f"  ⚠️ [{log_label}] rolling-window 결과가 0개라 "
                        "같은 품질 설정으로 serial STT fallback을 1회 실행합니다."
                    )
                    yield from self._transcribe_zero_window_fallback(
                        chunk_dir,
                        target_end_sec=target_end_sec,
                        is_single=is_single,
                        model_override=model_override,
                        log_label=log_label,
                        preview_callback=preview_callback,
                    )
            except Exception:
                had_window_error = True
                raise
            finally:
                if cleanup_chunk_dir:
                    shutil.rmtree(chunk_dir, ignore_errors=True)
                if had_window_error:
                    get_logger().log(f"[WARN] {log_label} rolling-window transcription aborted due to worker failure")
                else:
                    get_logger().log(f"[DONE] {log_label} rolling-window transcription completed")
            return

        if model_override is None and bool(_s.get("stt_ensemble_enabled", False)):
            yield from self.transcribe_ensemble(
                chunk_dir,
                target_end_sec=target_end_sec,
                is_single=is_single,
                preview_callback=preview_callback,
                cleanup_chunk_dir=cleanup_chunk_dir,
                _allow_window_rolling=_allow_window_rolling,
            )
            return
        from core.audio.npu_acceleration import prefer_npu_whisper_model

        target_model = model_override or _s.get("selected_whisper_model", self.whisper_model)
        primary_requested_model = str(target_model or "").strip()
        target_model = self._mac_primary_fast_native_model(target_model, _s, log_label=log_label)
        if str(target_model or "").strip() != primary_requested_model:
            get_logger().log(
                f"  ⚡ [{log_label}] macOS M 최적화: 1차 STT는 native turbo로 실행 "
                f"({primary_requested_model.split(chr(47))[-1]} → {str(target_model).split(chr(47))[-1]}), "
                "저신뢰/단어정밀 구간은 품질 모델로 보강"
            )
        stt_backend_name = ""
        try:
            from core.audio.stt_backend_router import select_stt_backend

            stt_choice = select_stt_backend(target_model, _s)
            stt_backend_name = str(stt_choice.backend or "").strip().lower()
            if stt_choice.model:
                target_model = stt_choice.model
            if stt_choice.reason not in {"auto_selected_model", "selected_model"}:
                get_logger().log(
                    f"  ⚙️ [{log_label}] STT backend={stt_choice.backend} "
                    f"reason={stt_choice.reason}"
                )
        except Exception:
            pass
        target_model = prefer_npu_whisper_model(target_model, _s, purpose="stt", log_label=log_label)
        target_model, _used_runtime_fallback = self._resolve_runtime_whisper_model(target_model, log_label=log_label)
        if self._native_batch_refine_requested(
            _s,
            target_model,
            model_override=model_override,
            total_chunks=total,
        ):
            secondary_model = str(_s.get("selected_whisper_model_secondary") or "").strip()
            get_logger().log(
                "  ⚡ [STT Native Batch] Swift/MLX 1차 인식을 먼저 끝내고 "
                "저신뢰 STT2/단어정밀 보정은 한 번에 배치 처리합니다"
            )
            yield from self._transcribe_selective_ensemble(
                chunk_dir,
                primary_model=target_model,
                secondary_model=secondary_model,
                settings=_s,
                target_end_sec=target_end_sec,
                is_single=is_single,
                preview_callback=preview_callback,
                cleanup_chunk_dir=cleanup_chunk_dir,
            )
            return
        self._notify_stage(f"⏳ [{log_label}] Whisper 인식 중")
        get_logger().log(f"\n🎯 [{log_label}] Whisper 인식 시작 (총 {total}블록, 모델: {target_model.split(chr(47))[-1]})")

        s = _s
        progress_by_audio_duration = bool(s.get("stt_rescue_whisper_mode", False)) or bool(
            s.get("stt_word_timestamp_precision_pass", False)
        )
        if progress_by_audio_duration:
            t_sec = max(0.001, sum(float(item.get("duration", 0.001) or 0.001) for item in q))
        processed_audio_sec = 0.0
        temp_max = float(s.get("w_none_temp_max", 0.4))
        temperature_values = [round(x * 0.2, 1) for x in range(int(temp_max / 0.2) + 1)]
        temperature_tuple = "(" + ", ".join(str(x) for x in temperature_values) + ",)"
        word_timestamps = self._stt_word_timestamps_for_pass(s)
        get_logger().log(
            f"  ⚙️ [{log_label}] word_timestamps={'on' if word_timestamps else 'off'} "
            f"(mode={str(s.get('stt_word_timestamps_mode') or 'always')})"
        )
        worker_silence_timeout_sec = self._stt_worker_silence_timeout_sec(
            s,
            log_label=log_label,
            word_timestamps=word_timestamps,
        )
        if worker_silence_timeout_sec > 0:
            get_logger().log(
                f"  ⏱️ [{log_label}] STT worker silence timeout: {worker_silence_timeout_sec:.0f}s"
            )

        from core.runtime import config as _cfg

        proc = None
        mac_task_id = None
        from core.audio.whisper_coreml import is_coreml_whisper_model
        from core.audio.whisper_cpp import is_whisper_cpp_model
        from core.audio.whisper_transformers import is_transformers_whisper_model
        from core.audio.whisperkit_persistent import is_whisperkit_persistent_model

        use_coreml_whisper = is_coreml_whisper_model(target_model)
        use_whisper_cpp = stt_backend_name == "whisper_cpp" or is_whisper_cpp_model(target_model)
        use_transformers_whisper = is_transformers_whisper_model(target_model)
        use_whisperkit_persistent = is_whisperkit_persistent_model(target_model)
        submitted_q = q
        safe_paths = [x["input_path"] for x in submitted_q]
        if use_whisperkit_persistent:
            from core.audio.whisperkit_persistent import (
                ensure_worker,
                is_supported_whisperkit_model,
                submit_task,
                whisperkit_model_selector,
            )

            try:
                if not is_supported_whisperkit_model(target_model):
                    selector = whisperkit_model_selector(target_model)
                    get_logger().log(
                        f"  ⚠️ [{log_label}] WhisperKit Native 미지원 모델이라 원래 STT 경로로 되돌립니다: {selector}"
                    )
                    target_model = selector or "mlx-community/whisper-large-v3-turbo"
                    use_whisperkit_persistent = False
                    use_coreml_whisper = is_coreml_whisper_model(target_model)
                    use_whisper_cpp = stt_backend_name == "whisper_cpp" or is_whisper_cpp_model(target_model)
                    use_transformers_whisper = is_transformers_whisper_model(target_model)
                else:
                    with self._whisper_lock:
                        current_proc = getattr(self, "_whisperkit_runner_proc", None)
                        self._whisperkit_runner_proc = ensure_worker(current_proc, log_label=log_label)
                        proc = self._whisperkit_runner_proc
                        if proc is not None:
                            if self._duration_first_stt_submission_enabled(s, word_timestamps=word_timestamps):
                                submission_order = self._duration_first_submission_order(q, s)
                                if submission_order != list(range(total)):
                                    submitted_q = [q[idx] for idx in submission_order]
                                    safe_paths = [x["input_path"] for x in submitted_q]
                            whisperkit_workers = self._whisperkit_concurrent_worker_count(
                                s,
                                total_chunks=len(safe_paths),
                                word_timestamps=word_timestamps,
                            )
                            if whisperkit_workers > 1:
                                get_logger().log(
                                    f"  ⚡ [{log_label}] WhisperKit ANE/GPU batch concurrency: "
                                    f"{whisperkit_workers} chunks"
                                )
                            whisperkit_stream_results = self._setting_bool(
                                s,
                                "stt_whisperkit_stream_results_enabled",
                                True,
                            )
                            whisperkit_compute_profile = self._whisperkit_compute_profile(
                                s,
                                word_timestamps=word_timestamps,
                            )
                            mac_task_id = submit_task(
                                proc=proc,
                                chunk_paths=safe_paths,
                                model=target_model,
                                language=self.language,
                                temperature_values=temperature_values,
                                word_timestamps=word_timestamps,
                                concurrent_worker_count=whisperkit_workers,
                                stream_results=whisperkit_stream_results,
                                compute_profile=whisperkit_compute_profile,
                            )
            except Exception as exc:
                get_logger().log(f"  ⚠️ [{log_label}] WhisperKit worker 요청 실패 → MLX fallback: {exc}")
                proc = None
                mac_task_id = None
            if use_whisperkit_persistent and proc is None:
                fallback_model = "mlx-community/whisper-large-v3-turbo"
                get_logger().log(f"  ↩️ [{log_label}] WhisperKit Native 준비 안 됨 → MLX fallback: {fallback_model}")
                target_model = fallback_model
                use_whisperkit_persistent = False
        if use_coreml_whisper:
            from core.audio.whisper_coreml import coreml_model_selector, coreml_selector_is_supported, run_whisper
            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple,
                log_label=log_label,
                options={**self._whisper_worker_options(s), "word_timestamps": word_timestamps},
            )
            if proc is None:
                selector_fallback = str(coreml_model_selector(target_model) or "").strip()
                fallback_model = (
                    selector_fallback
                    if selector_fallback and not coreml_selector_is_supported(selector_fallback)
                    else "mlx-community/whisper-large-v3-turbo"
                )
                get_logger().log(f"  ↩️ [{log_label}] Core ML STT 준비 안 됨 → MLX fallback: {fallback_model}")
                target_model = fallback_model
                use_coreml_whisper = False
                use_whisper_cpp = stt_backend_name == "whisper_cpp" or is_whisper_cpp_model(target_model)
                use_transformers_whisper = is_transformers_whisper_model(target_model)
                use_whisperkit_persistent = is_whisperkit_persistent_model(target_model)
        if use_whisper_cpp:
            from core.audio.whisper_cpp import run_whisper

            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple,
                log_label=log_label,
                word_timestamps=word_timestamps,
                options=self._whisper_worker_options(s),
            )
            if proc is None:
                fallback_model = "mlx-community/whisper-large-v3-turbo" if _cfg.IS_MAC else "large-v3-turbo"
                get_logger().log(f"  ↩️ [{log_label}] whisper.cpp STT 준비 안 됨 → fallback: {fallback_model}")
                target_model = fallback_model
                use_whisper_cpp = False
        if use_transformers_whisper:
            from core.audio.whisper_transformers import run_whisper

            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple,
                log_label=log_label,
            )
            if proc is None:
                get_logger().log("❌ Transformers Whisper 백엔드를 실행할 수 없습니다.")
                return
        elif use_whisper_cpp:
            pass
        elif use_whisperkit_persistent:
            pass
        elif use_coreml_whisper:
            pass
        elif _cfg.IS_MAC:
            from core.audio.whisper_mlx import ensure_worker, submit_task

            with self._whisper_lock:
                self._whisper_runner_proc = ensure_worker(self._whisper_runner_proc)
                proc = self._whisper_runner_proc
                mac_task_id = submit_task(
                    proc=proc,
                    chunk_paths=safe_paths,
                    model=target_model,
                    language=self.language,
                    temperature_values=temperature_values,
                    word_timestamps=word_timestamps,
                )
        else:
            from core.audio.whisper_faster import run_whisper
            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple,
                log_label=log_label,
            )
            if proc is None:
                get_logger().log("❌ Whisper 백엔드를 실행할 수 없습니다.")
                return

        self._whisper_proc = proc
        prev_end = 0.0
        had_error = False
        handled_by_fallback = False
        processed_count = 0
        emitted_segment_count = 0

        try:
            if _cfg.IS_MAC and not use_coreml_whisper and not use_whisper_cpp and not use_transformers_whisper:
                received = 0
                next_emit_idx = 0
                pending_payloads: dict[int, tuple[dict, dict]] = {}
                received_indices: set[int] = set()
                done_seen = False
                wait_started_at = time.monotonic()
                last_wait_log_at = wait_started_at
                precision_pass_active = bool(s.get("stt_word_timestamp_precision_pass", False))
                precision_straggler_skip_enabled = self._setting_bool(
                    s,
                    "stt_word_timestamp_straggler_skip_enabled",
                    True,
                )
                precision_straggler_timeout_sec = self._stt_precision_straggler_timeout_sec(s)
                precision_straggler_max_missing = self._stt_precision_straggler_max_missing_chunks(s)
                precision_straggler_min_received_ratio = self._stt_precision_straggler_min_received_ratio(s)
                recheck_pass_active = bool(s.get("stt_rescue_whisper_mode", False)) and not precision_pass_active
                recheck_straggler_skip_enabled = self._setting_bool(
                    s,
                    "stt_recheck_straggler_skip_enabled",
                    True,
                )
                recheck_straggler_timeout_sec = self._stt_recheck_straggler_timeout_sec(s)
                recheck_straggler_max_missing = self._stt_recheck_straggler_max_missing_chunks(s)
                recheck_straggler_min_received_ratio = self._stt_recheck_straggler_min_received_ratio(s)

                def _missing_worker_indices() -> list[int]:
                    return [
                        idx
                        for idx in range(total)
                        if idx not in received_indices and idx not in pending_payloads
                    ]

                def _precision_straggler_can_skip(missing_count: int) -> bool:
                    if not precision_pass_active or not precision_straggler_skip_enabled:
                        return False
                    if received <= 0 or missing_count <= 0:
                        return False
                    if missing_count <= precision_straggler_max_missing:
                        return True
                    if total <= 0 or precision_straggler_min_received_ratio <= 0.0:
                        return False
                    return (float(received) / float(total)) >= precision_straggler_min_received_ratio

                def _recheck_straggler_can_skip(missing_count: int) -> bool:
                    if not recheck_pass_active or not recheck_straggler_skip_enabled:
                        return False
                    if received <= 0 or missing_count <= 0:
                        return False
                    if missing_count <= recheck_straggler_max_missing:
                        return True
                    if total <= 0 or recheck_straggler_min_received_ratio <= 0.0:
                        return False
                    return (float(received) / float(total)) >= recheck_straggler_min_received_ratio

                def _queue_empty_straggler_payloads(reason: str, kind: str) -> int:
                    missing = _missing_worker_indices()
                    if not missing:
                        return 0
                    backend = "whisperkit-persistent" if use_whisperkit_persistent else "mlx-whisper"
                    for missing_idx in missing:
                        missing_item = q[missing_idx]
                        pending_payloads[missing_idx] = (
                            missing_item,
                            {
                                "backend": backend,
                                "language_probability": None,
                                "chunk_path": missing_item.get("input_path"),
                                "word_timestamps": word_timestamps,
                                "segments": [],
                                "text": "",
                                "stt_precision_straggler_fallback": reason if kind == "precision" else "",
                                "stt_recheck_straggler_fallback": reason if kind == "recheck" else "",
                            },
                        )
                        received_indices.add(missing_idx)
                    return len(missing)

                def _emit_ready_payloads():
                    nonlocal next_emit_idx
                    nonlocal prev_end
                    nonlocal processed_audio_sec
                    nonlocal processed_count
                    nonlocal emitted_segment_count
                    while next_emit_idx in pending_payloads:
                        pending_item, pending_payload = pending_payloads.pop(next_emit_idx)
                        chunk_segs = self._parse_whisper_payload(
                            pending_payload,
                            pending_item,
                            vad_strict,
                            target_end_sec=target_end_sec,
                            is_single=is_single
                        )
                        chunk_segs = self._apply_audio_route_segment_hints(chunk_segs, pending_item, route_hints)
                        chunk_segs = self._apply_windowed_chunk_finalize(
                            chunk_segs,
                            pending_item,
                            s,
                            total_chunks=total,
                            vad_segments=vad_strict,
                        )
                        chunk_segs = self._dedupe_overlapping_segments(
                            chunk_segs,
                            previous_end=prev_end,
                            dedup_window=float(s.get("sub_dedup_window", 0.5) or 0.5),
                            vad_segments=vad_strict,
                        )
                        chunk_segs = self._apply_post_parse_refinements(
                            chunk_dir,
                            chunk_segs,
                            s,
                            vad_strict,
                            target_model,
                            preview_callback=preview_callback,
                        )

                        if chunk_segs:
                            prev_end = chunk_segs[-1]["end"]
                            if callable(preview_callback):
                                try:
                                    preview_callback(chunk_segs, log_label)
                                except Exception:
                                    pass

                        if progress_by_audio_duration:
                            processed_audio_sec += float(pending_item.get("duration", 0.0) or 0.0)
                            progress_sec = min(t_sec, processed_audio_sec)
                        else:
                            progress_sec = prev_end
                        pct = min(100, int((progress_sec / t_sec) * 100))
                        get_logger().log(self._format_transcribe_progress(log_label, progress_sec, t_sec, pct))
                        yield chunk_segs, pending_item["idx"] + 1, total
                        processed_count += 1
                        emitted_segment_count += len(chunk_segs or [])
                        next_emit_idx += 1

                while received < total or (done_seen and next_emit_idx in pending_payloads):
                    effective_timeout_sec = worker_silence_timeout_sec
                    heartbeat_sec = 18.0
                    remaining_count = total - len(received_indices)
                    if (
                        precision_straggler_timeout_sec > 0.0
                        and _precision_straggler_can_skip(remaining_count)
                    ):
                        effective_timeout_sec = (
                            precision_straggler_timeout_sec
                            if effective_timeout_sec <= 0.0
                            else min(effective_timeout_sec, precision_straggler_timeout_sec)
                        )
                        heartbeat_sec = max(2.0, min(5.0, effective_timeout_sec * 0.5))
                    elif (
                        recheck_straggler_timeout_sec > 0.0
                        and _recheck_straggler_can_skip(remaining_count)
                    ):
                        effective_timeout_sec = (
                            recheck_straggler_timeout_sec
                            if effective_timeout_sec <= 0.0
                            else min(effective_timeout_sec, recheck_straggler_timeout_sec)
                        )
                        heartbeat_sec = max(2.0, min(5.0, effective_timeout_sec * 0.5))
                    try:
                        line, last_wait_log_at = self._read_worker_stdout_line(
                            proc,
                            log_label=log_label,
                            received=received,
                            total=total,
                            wait_started_at=wait_started_at,
                            last_wait_log_at=last_wait_log_at,
                            heartbeat_sec=heartbeat_sec,
                            max_silence_sec=effective_timeout_sec,
                        )
                    except SttWorkerTimeout:
                        missing = _missing_worker_indices()
                        if (
                            _precision_straggler_can_skip(len(missing))
                        ):
                            skipped = _queue_empty_straggler_payloads("timeout", "precision")
                            received += skipped
                            get_logger().log(
                                f"  ⚡ [{log_label}] 마지막 {skipped}개 chunk가 "
                                f"{effective_timeout_sec:.0f}s 이상 지연되어 단어정밀 보정만 건너뜁니다. "
                                "기존 STT 자막은 유지합니다."
                            )
                            yield from _emit_ready_payloads()
                            if received >= total:
                                break
                            wait_started_at = time.monotonic()
                            last_wait_log_at = wait_started_at
                            continue
                        if _recheck_straggler_can_skip(len(missing)):
                            skipped = _queue_empty_straggler_payloads("timeout", "recheck")
                            received += skipped
                            get_logger().log(
                                f"  ⚡ [{log_label}] 마지막 {skipped}개 STT2 보강 chunk가 "
                                f"{effective_timeout_sec:.0f}s 이상 지연되어 해당 구간은 STT1 후보를 유지합니다."
                            )
                            yield from _emit_ready_payloads()
                            if received >= total:
                                break
                            wait_started_at = time.monotonic()
                            last_wait_log_at = wait_started_at
                            continue
                        raise
                    if not line:
                        break

                    data = _parse_worker_json_line(line)
                    if data is None:
                        continue

                    task_id = data.get("task_id", data.get("taskId"))
                    if task_id != mac_task_id:
                        continue
                    if data.get("done"):
                        done_seen = True
                        missing = _missing_worker_indices()
                        if (
                            _precision_straggler_can_skip(len(missing))
                        ):
                            skipped = _queue_empty_straggler_payloads("done_missing", "precision")
                            received += skipped
                            get_logger().log(
                                f"  ⚡ [{log_label}] worker 완료 신호 후 누락된 {skipped}개 chunk는 "
                                "단어정밀 보정만 건너뛰고 기존 STT 자막을 유지합니다."
                            )
                            yield from _emit_ready_payloads()
                            break
                        if _recheck_straggler_can_skip(len(missing)):
                            skipped = _queue_empty_straggler_payloads("done_missing", "recheck")
                            received += skipped
                            get_logger().log(
                                f"  ⚡ [{log_label}] worker 완료 신호 후 누락된 {skipped}개 STT2 보강 chunk는 "
                                "해당 구간만 STT1 후보를 유지합니다."
                            )
                            yield from _emit_ready_payloads()
                            break
                        wait_started_at = time.monotonic()
                        last_wait_log_at = wait_started_at
                        if received >= total:
                            break
                        continue

                    if data.get("fatal_error") or data.get("error"):
                        had_error = True
                        msg = data.get("fatal_error") or data.get("error") or "unknown whisper worker error"
                        stage = data.get("stage", "worker")
                        get_logger().log(f"  [FAIL] Whisper worker error ({stage}): {msg}")
                        raise RuntimeError(f"whisper_worker_error[{stage}]: {msg}")

                    submitted_idx = int(data.get("index", received))
                    if submitted_idx < 0 or submitted_idx >= len(submitted_q):
                        continue
                    item = submitted_q[submitted_idx]
                    idx = int(item.get("idx", submitted_idx))
                    payload = data.get("result") if "result" in data else {"error": data.get("error", "")}
                    if isinstance(payload, dict):
                        payload.setdefault("backend", data.get("backend", "mlx-whisper"))
                        payload.setdefault("language_probability", data.get("language_probability"))
                        payload.setdefault("chunk_path", item.get("input_path"))
                        payload.setdefault("word_timestamps", data.get("word_timestamps", word_timestamps))
                    pending_payloads[idx] = (item, payload)
                    received_indices.add(idx)
                    received += 1
                    wait_started_at = time.monotonic()
                    last_wait_log_at = wait_started_at

                    yield from _emit_ready_payloads()

                if total > 0 and processed_count == 0:
                    if use_whisperkit_persistent:
                        fallback_model = whisperkit_empty_result_fallback_model(target_model, s)
                        get_logger().log(
                            f"  ⚠️ [{log_label}] WhisperKit 결과 chunk가 0개라 MLX로 즉시 재시도합니다: "
                            f"{fallback_model.split(chr(47))[-1]}"
                        )
                        handled_by_fallback = True
                        stop_empty_whisperkit_worker(self, proc)
                        previous_overrides = getattr(self, "_fast_mode_overrides", None)
                        fallback_overrides = whisperkit_empty_fallback_overrides(
                            previous_overrides,
                            fallback_model,
                        )
                        self._fast_mode_overrides = fallback_overrides
                        try:
                            yield from self.transcribe(
                                chunk_dir,
                                is_fast_mode=is_fast_mode,
                                target_end_sec=target_end_sec,
                                is_single=is_single,
                                model_override=fallback_model,
                                cleanup_chunk_dir=cleanup_chunk_dir,
                                log_label=log_label,
                                preview_callback=preview_callback,
                                _allow_window_rolling=_allow_window_rolling,
                            )
                        finally:
                            self._fast_mode_overrides = previous_overrides
                        return
                    had_error = True
                    raise RuntimeError("whisper produced 0 chunks")

                if total > 0 and emitted_segment_count == 0 and use_whisperkit_persistent:
                    fallback_model = whisperkit_empty_result_fallback_model(target_model, s)
                    get_logger().log(
                        f"  ⚠️ [{log_label}] WhisperKit 결과 자막이 비어 있어 MLX로 즉시 재시도합니다: "
                        f"{fallback_model.split(chr(47))[-1]}"
                    )
                    handled_by_fallback = True
                    stop_empty_whisperkit_worker(self, proc)
                    previous_overrides = getattr(self, "_fast_mode_overrides", None)
                    fallback_overrides = whisperkit_empty_fallback_overrides(
                        previous_overrides,
                        fallback_model,
                    )
                    self._fast_mode_overrides = fallback_overrides
                    try:
                        yield from self.transcribe(
                            chunk_dir,
                            is_fast_mode=is_fast_mode,
                            target_end_sec=target_end_sec,
                            is_single=is_single,
                            model_override=fallback_model,
                            cleanup_chunk_dir=cleanup_chunk_dir,
                            log_label=log_label,
                            preview_callback=preview_callback,
                            _allow_window_rolling=_allow_window_rolling,
                        )
                    finally:
                        self._fast_mode_overrides = previous_overrides
                    return

            else:
                for item in q:
                    line = proc.stdout.readline()
                    if not line:
                        break

                    data = _parse_worker_json_line(line)
                    if data is None:
                        continue

                    if data.get("fatal_error") or data.get("error"):
                        had_error = True
                        msg = data.get("fatal_error") or data.get("error") or "unknown whisper worker error"
                        stage = data.get("stage", "worker")
                        get_logger().log(f"  [FAIL] Whisper worker error ({stage}): {msg}")
                        raise RuntimeError(f"whisper_worker_error[{stage}]: {msg}")

                    chunk_segs = self._parse_whisper_payload(
                        data,
                        item,
                        vad_strict,
                        target_end_sec=target_end_sec,
                        is_single=is_single
                    )
                    chunk_segs = self._apply_audio_route_segment_hints(chunk_segs, item, route_hints)
                    chunk_segs = self._apply_windowed_chunk_finalize(
                        chunk_segs,
                        item,
                        s,
                        total_chunks=total,
                        vad_segments=vad_strict,
                    )
                    chunk_segs = self._dedupe_overlapping_segments(
                        chunk_segs,
                        previous_end=prev_end,
                        dedup_window=float(s.get("sub_dedup_window", 0.5) or 0.5),
                        vad_segments=vad_strict,
                    )
                    chunk_segs = self._apply_post_parse_refinements(
                        chunk_dir,
                        chunk_segs,
                        s,
                        vad_strict,
                        target_model,
                        preview_callback=preview_callback,
                    )

                    if chunk_segs:
                        prev_end = chunk_segs[-1]["end"]
                        if callable(preview_callback):
                            try:
                                preview_callback(chunk_segs, log_label)
                            except Exception:
                                pass

                    if progress_by_audio_duration:
                        processed_audio_sec += float(item.get("duration", 0.0) or 0.0)
                        progress_sec = min(t_sec, processed_audio_sec)
                    else:
                        progress_sec = prev_end
                    pct = min(100, int((progress_sec / t_sec) * 100))
                    get_logger().log(self._format_transcribe_progress(log_label, progress_sec, t_sec, pct))
                    yield chunk_segs, item["idx"] + 1, total
                    processed_count += 1
                    emitted_segment_count += len(chunk_segs or [])

                proc.wait()
                if proc.returncode not in (0, None):
                    had_error = True
                    raise RuntimeError(f"whisper_worker_exit_code={proc.returncode}")
                if processed_count == 0 and total > 0:
                    had_error = True
                    raise RuntimeError("whisper produced 0 chunks")

        except SttWorkerTimeout as exc:
            had_error = True
            precision_pass = bool(s.get("stt_word_timestamp_precision_pass", False))
            if use_whisperkit_persistent and not precision_pass:
                fallback_model = whisperkit_empty_result_fallback_model(target_model, s)
                get_logger().log(
                    f"  ⚠️ [{log_label}] WhisperKit worker timeout → MLX GPU fallback으로 재시도: "
                    f"{fallback_model.split(chr(47))[-1]}"
                )
                handled_by_fallback = True
                stop_empty_whisperkit_worker(self, proc)
                previous_overrides = getattr(self, "_fast_mode_overrides", None)
                fallback_overrides = whisperkit_empty_fallback_overrides(
                    previous_overrides,
                    fallback_model,
                )
                self._fast_mode_overrides = fallback_overrides
                try:
                    yield from self.transcribe(
                        chunk_dir,
                        is_fast_mode=is_fast_mode,
                        target_end_sec=target_end_sec,
                        is_single=is_single,
                        model_override=fallback_model,
                        cleanup_chunk_dir=cleanup_chunk_dir,
                        log_label=log_label,
                        preview_callback=preview_callback,
                        _allow_window_rolling=_allow_window_rolling,
                    )
                finally:
                    self._fast_mode_overrides = previous_overrides
                return
            raise RuntimeError(str(exc)) from exc
        finally:
            if not handled_by_fallback:
                self._release_after_transcribe_job(log_label, force_stop=had_error)
            if cleanup_chunk_dir and not handled_by_fallback:
                shutil.rmtree(chunk_dir, ignore_errors=True)
            if had_error and not handled_by_fallback:
                get_logger().log(f"[WARN] {log_label} Whisper transcription aborted due to worker failure")
            elif not handled_by_fallback:
                get_logger().log(f"[DONE] {log_label} Whisper transcription completed")
    @staticmethod
    def _format_transcribe_progress(log_label: str, current_sec: float, total_sec: float, pct: int) -> str:
        label = (log_label or "STT").strip() or "STT"
        return (
            f"  ▶ [{label}] 진행 상황: {int(current_sec // 60):02d}분 {int(current_sec % 60):02d}초 / "
            f"{int(total_sec // 60):02d}분 {int(total_sec % 60):02d}초 ({int(pct)}%)"
        )
    def stop_transcribe(self):
        had_runtime = bool(
            getattr(self, "_whisper_proc", None)
            or getattr(self, "_whisper_runner_proc", None)
            or getattr(self, "_whisperkit_runner_proc", None)
        )
        try:
            with getattr(self, "_ensemble_child_lock", threading.Lock()):
                children = list(getattr(self, "_ensemble_child_processors", []) or [])
            for child in children:
                try:
                    child.stop_transcribe()
                except Exception:
                    pass

            from core.runtime import config as _cfg

            if _cfg.IS_MAC:
                from core.audio.whisper_mlx import stop_worker as stop_mlx_worker
                from core.audio.whisperkit_persistent import stop_worker as stop_whisperkit_worker
                with self._whisper_lock:
                    active_proc = getattr(self, "_whisper_proc", None)
                    if self._whisper_runner_proc:
                        stop_mlx_worker(self._whisper_runner_proc)
                        self._whisper_runner_proc = None
                    whisperkit_proc = getattr(self, "_whisperkit_runner_proc", None)
                    if whisperkit_proc:
                        stop_whisperkit_worker(whisperkit_proc)
                        self._whisperkit_runner_proc = None
                    if active_proc and active_proc not in {getattr(self, "_whisper_runner_proc", None), whisperkit_proc}:
                        try:
                            if active_proc.poll() is None:
                                active_proc.terminate()
                                active_proc.wait(timeout=2)
                        except Exception:
                            try:
                                active_proc.kill()
                            except Exception:
                                pass
                    self._whisper_proc = None
                return

            if self._whisper_proc and self._whisper_proc.poll() is None:
                self._whisper_proc.terminate()
                try:
                    self._whisper_proc.wait(timeout=2)
                except Exception:
                    self._whisper_proc.kill()

        except Exception:
            pass
        finally:
            self._whisper_proc = None
            if had_runtime:
                clear_audio_model_memory_caches(include_gpu=True)
    def release_runtime_models(self):
        self.stop_transcribe()
        try:
            with getattr(self, "_ensemble_child_lock", threading.Lock()):
                children = list(getattr(self, "_ensemble_child_processors", []) or [])
            for child in children:
                try:
                    if hasattr(child, "release_runtime_models"):
                        child.release_runtime_models()
                except Exception:
                    pass
            with getattr(self, "_ensemble_child_lock", threading.Lock()):
                self._ensemble_child_processors = []
        except Exception:
            pass
        self.release_vad_runtime_models(log_context="런타임 정리")
        clear_audio_model_memory_caches(include_gpu=True)
