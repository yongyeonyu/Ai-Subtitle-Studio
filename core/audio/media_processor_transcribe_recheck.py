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
    selective_secondary_recheck_plan as selective_secondary_recheck_plan_via_service,
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
class VideoProcessorTranscribeRecheckMixin:
    def _precision_low_vad_nondigit_collect_padding(
        self,
        item: stt_rescue.SttRecheckRange,
        settings: dict,
        default_pad: float,
    ) -> float:
        if not bool(settings.get("stt_word_timestamp_low_vad_nondigit_collect_padding_enabled", False)):
            return default_pad

        primary_text = str(getattr(item, "primary_text", "") or "").strip()
        if not primary_text or re.search(r"\d", primary_text):
            return default_pad
        if str(getattr(item, "secondary_text", "") or "").strip():
            return default_pad

        primary = getattr(item, "primary", {}) or {}
        flags = {str(flag) for flag in (primary.get("stt_score_flags") or ())}
        if not flags or not flags.issubset({"no_speech_prob_missing", "avg_logprob_missing", "word_confidence_missing", "low_language_char_ratio"}):
            return default_pad

        quality = dict(primary.get("quality") or {})
        vad_score = quality.get("vad_alignment_score")
        try:
            vad_score_value = float(vad_score if vad_score is not None else 100.0)
        except Exception:
            vad_score_value = 100.0
        max_vad_score = max(
            0.0,
            min(
                100.0,
                float(settings.get("stt_word_timestamp_low_vad_nondigit_collect_padding_max_vad_score", 60.0) or 60.0),
            ),
        )
        if vad_score_value > max_vad_score:
            return default_pad

        duration_sec = max(0.0, float(item.end or 0.0) - float(item.start or 0.0))
        max_duration_sec = max(
            0.1,
            float(settings.get("stt_word_timestamp_low_vad_nondigit_collect_padding_max_duration_sec", 3.5) or 3.5),
        )
        if duration_sec > max_duration_sec:
            return default_pad

        target_pad = max(
            0.0,
            float(settings.get("stt_word_timestamp_low_vad_nondigit_collect_padding_sec", 0.0) or 0.0),
        )
        return min(default_pad, target_pad)

    def _precision_short_digit_phrase_collect_padding(
        self,
        item: stt_rescue.SttRecheckRange,
        settings: dict,
        default_pad: float,
    ) -> float:
        if not bool(settings.get("stt_word_timestamp_short_digit_phrase_collect_padding_enabled", False)):
            return default_pad

        primary_text = str(getattr(item, "primary_text", "") or "").strip()
        if not primary_text or not re.search(r"\d", primary_text):
            return default_pad
        if str(getattr(item, "secondary_text", "") or "").strip():
            return default_pad
        if not re.search(r"[가-힣]", primary_text):
            return default_pad

        normalized_text = re.sub(r"[\s.,]", "", primary_text)
        if normalized_text.isdigit():
            return default_pad

        primary = getattr(item, "primary", {}) or {}
        flags = {str(flag) for flag in (primary.get("stt_score_flags") or ())}
        if not flags or not flags.issubset({"no_speech_prob_missing", "avg_logprob_missing", "word_confidence_missing", "low_language_char_ratio"}):
            return default_pad

        duration_sec = max(0.0, float(item.end or 0.0) - float(item.start or 0.0))
        max_duration_sec = max(
            0.1,
            float(settings.get("stt_word_timestamp_short_digit_phrase_collect_padding_max_duration_sec", 2.5) or 2.5),
        )
        if duration_sec > max_duration_sec:
            return default_pad

        quality = dict(primary.get("quality") or {})
        vad_score = quality.get("vad_alignment_score")
        try:
            vad_score_value = float(vad_score if vad_score is not None else 0.0)
        except Exception:
            vad_score_value = 0.0
        min_vad_score = max(
            0.0,
            min(
                100.0,
                float(settings.get("stt_word_timestamp_short_digit_phrase_collect_padding_min_vad_score", 95.0) or 95.0),
            ),
        )
        if vad_score_value < min_vad_score:
            return default_pad

        target_pad = max(
            0.0,
            float(settings.get("stt_word_timestamp_short_digit_phrase_collect_padding_sec", 0.0) or 0.0),
        )
        return min(default_pad, target_pad)

    def _transcribe_zero_window_fallback(
        self,
        chunk_dir: str,
        *,
        target_end_sec: float | None,
        is_single: bool,
        model_override: str | None,
        log_label: str,
        preview_callback,
    ):
        yield from self.transcribe(
            chunk_dir,
            is_fast_mode=False,
            target_end_sec=target_end_sec,
            is_single=is_single,
            model_override=model_override,
            cleanup_chunk_dir=False,
            log_label=log_label,
            preview_callback=preview_callback,
            _allow_window_rolling=False,
        )
    def _transcribe_ensemble_zero_window_fallback(
        self,
        chunk_dir: str,
        *,
        target_end_sec: float | None,
        is_single: bool,
        preview_callback,
    ):
        yield from self.transcribe_ensemble(
            chunk_dir,
            target_end_sec=target_end_sec,
            is_single=is_single,
            preview_callback=preview_callback,
            cleanup_chunk_dir=False,
            _allow_window_rolling=False,
        )
    def _ffmpeg_trim_recheck_clip(self, src_wav: str, out_wav: str, start_sec: float, duration_sec: float, settings: dict | None = None) -> bool:
        filter_chain = stt_rescue.rescue_audio_filter(settings)
        cmd = [
            ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
            "-ss", f"{max(0.0, float(start_sec or 0.0)):.3f}",
            "-t", f"{max(0.05, float(duration_sec or 0.05)):.3f}",
            "-i", src_wav,
            "-ac", "1", "-ar", "16000",
            "-af", filter_chain,
            "-acodec", "pcm_s16le",
            out_wav,
        ]
        ok = self._run_media_command_no_progress(cmd, label="STT 재검사 오디오 보정")
        if ok and os.path.exists(out_wav) and os.path.getsize(out_wav) > 0:
            return True
        return self._ffmpeg_trim_to_wav(src_wav, out_wav, start_sec, duration_sec)
    def _prepare_recheck_clip(self, item: stt_rescue.SttRecheckRange, out_dir: str, idx: int, settings: dict) -> dict | None:
        source_path = self._segment_chunk_path(item.primary) or self._segment_chunk_path(item.secondary)
        if not source_path or not os.path.exists(source_path):
            return None

        pad = stt_rescue.recheck_padding(settings)
        pad = self._precision_low_vad_nondigit_collect_padding(item, settings, pad)
        pad = self._precision_short_digit_phrase_collect_padding(item, settings, pad)
        chunk_start = self._chunk_start_from_path(source_path)
        chunk_duration = self._wav_duration(source_path)
        abs_start = max(0.0, item.start - pad)
        abs_end = max(abs_start + 0.05, item.end + pad)
        local_start = max(0.0, abs_start - chunk_start)
        local_end = abs_end - chunk_start
        if chunk_duration > 0:
            local_end = min(chunk_duration, local_end)
        duration = max(0.05, local_end - local_start)
        if duration <= 0.05:
            return None

        actual_abs_start = chunk_start + local_start
        out_path = os.path.join(out_dir, f"vad_{900 + idx:03d}_{actual_abs_start:.3f}.wav")
        if not self._ffmpeg_trim_recheck_clip(source_path, out_path, local_start, duration, settings):
            return None
        return {
            "range": item,
            "path": out_path,
            "source_path": source_path,
            "source_chunk_start": round(chunk_start, 3),
            "source_chunk_duration_sec": round(max(0.0, chunk_duration), 3),
            "local_start": round(local_start, 3),
            "local_end": round(local_end, 3),
            "padding_sec": round(max(0.0, pad), 3),
            "start": round(actual_abs_start, 3),
            "end": round(actual_abs_start + duration, 3),
        }
    def _chunk_path_covering_time(self, chunk_dir: str, target_sec: float) -> str:
        target = float(target_sec or 0.0)
        for row in self._audio_chunk_manifest(chunk_dir):
            path = str(row.get("path") or "")
            start = float(row.get("start", 0.0) or 0.0)
            duration = float(row.get("duration", 0.0) or 0.0)
            if duration <= 0.0:
                continue
            if (start - 0.25) <= target <= (start + duration + 0.25):
                return path
        return ""
    def _word_precision_ranges(
        self,
        segments: list[dict],
        settings: dict,
    ) -> list[stt_rescue.SttRecheckRange]:
        return build_word_precision_ranges(
            segments,
            settings,
            needs_precision_fn=self._segment_needs_word_precision,
            score_fn=self._segment_score_100,
            has_score_fn=self._segment_has_score,
        )
    def _apply_word_precision_segments(
        self,
        base_segments: list[dict],
        precision_segments: list[dict],
        ranges: list[stt_rescue.SttRecheckRange],
        settings: dict,
    ) -> tuple[list[dict], int]:
        try:
            from core.audio.stt_ensemble import text_similarity
        except Exception:
            text_similarity = None
        return apply_word_precision_segments_via_service(
            base_segments=base_segments,
            precision_segments=precision_segments,
            ranges=ranges,
            settings=settings,
            score_fn=self._segment_score_100,
            text_similarity_fn=text_similarity,
        )
    def _apply_post_parse_refinements(
        self,
        chunk_dir: str,
        segments: list[dict],
        settings: dict,
        vad_strict: list[dict],
        primary_model: str,
        preview_callback=None,
    ) -> list[dict]:
        refined = self._recheck_primary_low_score_with_secondary(
            chunk_dir,
            segments,
            settings,
            vad_strict,
            primary_model,
            preview_callback=preview_callback,
        )
        return self._recheck_word_timestamps_for_precision(
            chunk_dir,
            refined,
            settings,
            vad_strict,
            primary_model,
        )
    def _recheck_word_timestamps_for_precision(
        self,
        chunk_dir: str,
        segments: list[dict],
        settings: dict,
        vad_strict: list[dict],
        primary_model: str,
    ) -> list[dict]:
        if not segments:
            return segments
        if not self._setting_bool(settings, "stt_word_timestamps_precision_enabled", True):
            return segments
        if bool(settings.get("stt_word_timestamp_precision_pass", False)):
            return segments
        if self._stt_word_timestamps_for_pass(settings):
            return segments

        trace_callback = getattr(self, "_benchmark_word_precision_trace_callback", None)
        trace_rows: list[dict] = []

        def _record_trace(extra: dict | None = None) -> None:
            if not callable(trace_callback):
                return
            payload = dict(extra or {})
            payload["elapsed_ms"] = round(float(payload.get("elapsed_ms", 0.0) or 0.0), 3)
            trace_rows.append(payload)

        phase_started = time.perf_counter()
        ranges = self._word_precision_ranges(segments, settings)
        _record_trace(
            {
                "phase": "range_select",
                "elapsed_ms": (time.perf_counter() - phase_started) * 1000.0,
                "segment_count": len(list(segments or [])),
                "range_count": len(list(ranges or [])),
            }
        )
        if not ranges:
            if callable(trace_callback):
                try:
                    trace_callback([dict(item) for item in trace_rows])
                except Exception:
                    pass
            return segments

        get_logger().log(
            f"  🔬 [단어 타임태그] 저신뢰/정밀 구간 {len(ranges)}개만 word timestamp 재인식"
        )
        self._notify_stage(f"⏳ [STT] 단어 타임태그 {len(ranges)}개 정밀 보정 중")
        precision_dir = os.path.join(chunk_dir, "_stt_word_precision")
        shutil.rmtree(precision_dir, ignore_errors=True)
        os.makedirs(precision_dir, exist_ok=True)
        batch = prepare_and_collect_recheck_segments_via_service(
            ranges=ranges,
            out_dir=precision_dir,
            settings=settings,
            prepare_clip_fn=self._prepare_recheck_clip,
            collect_fn=self._collect_transcribe_result,
            model=resolve_precision_model_via_service(settings, primary_model=primary_model),
            label="STT-단어정밀",
            settings_overrides=precision_pass_overrides_via_service(settings),
            annotate_fn=self._annotate_stt_candidates,
            annotate_source="WORD_PRECISION",
            vad_segments=vad_strict,
            peer_segments=segments,
            is_single=False,
            trace_callback=_record_trace,
        )
        if not batch.prepared_clips:
            if callable(trace_callback):
                try:
                    trace_callback([dict(item) for item in trace_rows])
                except Exception:
                    pass
            return segments
        if not batch.collected_segments:
            if callable(trace_callback):
                try:
                    trace_callback([dict(item) for item in trace_rows])
                except Exception:
                    pass
            return segments
        if batch.annotate_error:
            get_logger().log(f"  ⚠️ [단어 타임태그] 정밀 구간 점수 계산 실패: {batch.annotate_error}")

        phase_started = time.perf_counter()
        updated, applied = self._apply_word_precision_segments(
            segments,
            batch.collected_segments,
            ranges,
            settings,
        )
        _record_trace(
            {
                "phase": "apply_precision",
                "elapsed_ms": (time.perf_counter() - phase_started) * 1000.0,
                "range_count": len(list(ranges or [])),
                "collected_segment_count": len(list(batch.collected_segments or [])),
                "applied_count": int(applied or 0),
                "result_segment_count": len(list(updated or [])),
            }
        )
        if applied > 0:
            get_logger().log(f"  ✅ [단어 타임태그] {applied}개 자막 타이밍을 단어 기준으로 보정했습니다.")
        if callable(trace_callback):
            try:
                trace_callback([dict(item) for item in trace_rows])
            except Exception:
                pass
        return updated
    def _recheck_low_score_stt_ranges(
        self,
        chunk_dir: str,
        results: dict[str, list[dict]],
        settings: dict,
        vad_strict: list[dict],
        primary_model: str,
    ) -> dict[str, list[dict]]:
        if not stt_rescue.enabled(settings):
            return results

        ranges = build_low_score_recheck_ranges(
            results.get("STT1", []),
            results.get("STT2", []),
            settings,
            score_fn=self._segment_score_100,
        )
        if not ranges:
            return results

        threshold = stt_rescue.threshold(settings)
        get_logger().log(
            f"  🔁 [STT 재검사] STT1/STT2 모두 {threshold:.0f}점 이하인 구간 {len(ranges)}개 재인식 시작"
        )
        self._notify_stage(f"⏳ [STT] 저점 구간 {len(ranges)}개 재검사 중")

        rescue_dir = os.path.join(chunk_dir, "_stt_recheck")
        os.makedirs(rescue_dir, exist_ok=True)
        batch = prepare_and_collect_recheck_segments_via_service(
            ranges=ranges,
            out_dir=rescue_dir,
            settings=settings,
            prepare_clip_fn=self._prepare_recheck_clip,
            collect_fn=self._collect_transcribe_result,
            model=str(settings.get("stt_low_score_recheck_model") or primary_model or "").strip() or primary_model,
            label="STT-재검사",
            settings_overrides=low_score_recheck_overrides_via_service(settings),
            annotate_fn=self._annotate_stt_candidates,
            annotate_source="RECHECK",
            vad_segments=vad_strict,
            is_single=False,
        )
        if not batch.prepared_clips:
            get_logger().log("  ⚠️ [STT 재검사] 재검사용 WAV 생성 실패로 기존 후보를 유지합니다.")
            return results
        if not batch.collected_segments:
            get_logger().log("  ⚠️ [STT 재검사] 재인식 결과가 비어 있어 기존 후보를 유지합니다.")
            return results
        if batch.annotate_error:
            get_logger().log(f"  ⚠️ [STT 재검사] 재검사 점수 계산 실패: {batch.annotate_error}")

        applied = apply_recheck_selection_to_tracks_via_service(
            prepared_clips=batch.prepared_clips,
            rescue_segments=batch.collected_segments,
            settings=settings,
            replacement_is_better_fn=stt_rescue.replacement_is_better,
            mark_segments_fn=stt_rescue.mark_rescue_segments,
            base_tracks={
                "STT1": results.get("STT1", []),
                "STT2": results.get("STT2", []),
            },
            decorate_segment_fn=lambda seg: {
                **seg,
                "stt_selected_source": "RECHECK",
                "stt_ensemble_source": "RECHECK",
            },
        )
        for item in applied.selection.skipped_ranges:
            get_logger().log(
                "  ↩️ [STT 재검사] 개선 부족으로 기존 후보 유지 "
                f"({item.start:.2f}-{item.end:.2f}s, STT1 {item.primary_score:.1f}, STT2 {item.secondary_score:.1f})"
            )

        if not applied.selection.applied_segments:
            get_logger().log("  ↩️ [STT 재검사] 교체할 만큼 좋아진 구간이 없어 기존 후보를 유지합니다.")
            return results

        updated = dict(applied.merged_tracks or {})
        get_logger().log(f"  ✅ [STT 재검사] {len(applied.selection.applied_ranges)}개 저점 구간을 재인식 결과로 교체했습니다.")
        return {"STT1": list(updated.get("STT1", [])), "STT2": list(updated.get("STT2", []))}
    def _selective_secondary_recheck_enabled(self, settings: dict, primary_model: str) -> bool:
        if not stt_rescue.enabled(settings):
            return False
        if bool(settings.get("stt_ensemble_enabled", False)) and not self._stt_selective_ensemble_enabled(settings):
            return False
        enabled_value = settings.get("stt_selective_secondary_recheck_enabled")
        if enabled_value is None:
            if self._stt_selective_ensemble_enabled(settings):
                enabled_value = True
            else:
                try:
                    from core.mode_policy import selected_mode_from_settings

                    enabled_value = selected_mode_from_settings(settings) == "fast"
                except Exception:
                    enabled_value = False
        if not bool(enabled_value):
            return False
        secondary_model = str(settings.get("selected_whisper_model_secondary") or "").strip()
        if not secondary_model or secondary_model == str(primary_model or "").strip():
            return False
        return True
    def _recheck_primary_low_score_with_secondary(
        self,
        chunk_dir: str,
        chunk_segs: list[dict],
        settings: dict,
        vad_strict: list[dict],
        primary_model: str,
        target_end_sec: float = None,
        preview_callback=None,
    ) -> list[dict]:
        self._last_secondary_low_score_recheck_info = {
            "collect_runtime_info_found": False,
            "collect_runtime_info": None,
            "recheck_plan_source_counts": None,
            "raw_range_count": 0,
            "range_count": 0,
            "prepared_clip_count": 0,
            "collected_segment_count": 0,
            "applied_range_count": 0,
            "skipped_range_count": 0,
            "applied_segment_count": 0,
            "retained_primary_segment_count": len(list(chunk_segs or [])),
            "annotate_error": "",
        }
        if not chunk_segs or not self._selective_secondary_recheck_enabled(settings, primary_model):
            return chunk_segs
        secondary_model = str(settings.get("selected_whisper_model_secondary") or "").strip()
        context_label = "선택 STT2 재검사" if self._stt_selective_ensemble_enabled(settings) else "Fast STT2 재검사"
        try:
            scored_primary = self._annotate_stt_candidates(
                [dict(seg) for seg in chunk_segs if isinstance(seg, dict)],
                source="STT1",
                vad_segments=vad_strict,
                settings=settings,
            )
        except Exception as exc:
            get_logger().log(f"  ⚠️ [{context_label}] STT1 점수 계산 실패: {exc}")
            return chunk_segs

        range_settings = dict(settings)
        if target_end_sec is not None:
            range_settings["_stt_recheck_target_end_sec"] = float(target_end_sec)

        recheck_plan = selective_secondary_recheck_plan_via_service(
            primary_segments=scored_primary,
            vad_segments=vad_strict,
            settings=range_settings,
            score_fn=self._segment_score_100,
            chunk_path_for_time=lambda target_sec: self._chunk_path_covering_time(chunk_dir, target_sec),
        )
        source_counts = {
            "low_score": len(recheck_plan.get("low_score") or ()),
            "missing_voice": len(recheck_plan.get("missing_voice") or ()),
            "route_hint": len(recheck_plan.get("route_hint") or ()),
            "merged": len(recheck_plan.get("merged") or ()),
        }
        ranges = list(recheck_plan.get("ranges") or ())
        raw_range_count = int(recheck_plan.get("raw_count") or 0)
        self._last_secondary_low_score_recheck_info = {
            "collect_runtime_info_found": False,
            "collect_runtime_info": None,
            "recheck_plan_source_counts": dict(source_counts),
            "raw_range_count": raw_range_count,
            "range_count": len(ranges),
            "prepared_clip_count": 0,
            "collected_segment_count": 0,
            "applied_range_count": 0,
            "skipped_range_count": 0,
            "applied_segment_count": 0,
            "retained_primary_segment_count": len(list(scored_primary or [])),
            "annotate_error": "",
        }
        if raw_range_count > len(ranges):
            get_logger().log(
                f"  ⚡ [{context_label}] STT2 재검사 예산 적용: {raw_range_count}개 → {len(ranges)}개"
            )
        if source_counts:
            get_logger().log(
                "  🧭 "
                f"[{context_label}] 후보 source "
                f"low_score={int(source_counts.get('low_score', 0) or 0)} "
                f"missing_voice={int(source_counts.get('missing_voice', 0) or 0)} "
                f"route_hint={int(source_counts.get('route_hint', 0) or 0)} "
                f"merged={int(source_counts.get('merged', 0) or 0)}"
            )
        if not ranges:
            return scored_primary

        threshold = stt_rescue.threshold(settings)
        get_logger().log(
            f"  🔁 [{context_label}] STT1 {threshold:.0f}점 이하/누락/경계 후보 {len(ranges)}개를 STT2로 확인"
        )
        self._notify_stage(f"⏳ [STT] 저점 구간 {len(ranges)}개 STT2 확인 중")

        rescue_dir = os.path.join(chunk_dir, "_fast_stt2_recheck")
        shutil.rmtree(rescue_dir, ignore_errors=True)
        os.makedirs(rescue_dir, exist_ok=True)
        collect_fn = self._collect_transcribe_result
        if callable(preview_callback):
            stt2_preview_callback = self._ensemble_preview_callback("STT2", preview_callback)

            def collect_fn(*args, **kwargs):
                kwargs["preview_callback"] = stt2_preview_callback
                return self._collect_transcribe_result(*args, **kwargs)

            setattr(collect_fn, "_collect_owner", self)

        batch = prepare_and_collect_recheck_segments_via_service(
            ranges=ranges,
            out_dir=rescue_dir,
            settings=settings,
            prepare_clip_fn=self._prepare_recheck_clip,
            collect_fn=collect_fn,
            model=secondary_model,
            label="Fast-STT2",
            settings_overrides=selective_secondary_recheck_overrides_via_service(settings),
            annotate_fn=self._annotate_stt_candidates,
            annotate_source="STT2",
            vad_segments=vad_strict,
            peer_segments=scored_primary,
            is_single=False,
        )
        collect_runtime_info = dict(getattr(self, "_last_collect_runtime_info", {}) or {})
        self._last_secondary_low_score_recheck_info = {
            **dict(getattr(self, "_last_secondary_low_score_recheck_info", {}) or {}),
            "collect_runtime_info_found": bool(collect_runtime_info),
            "collect_runtime_info": collect_runtime_info if collect_runtime_info else None,
            "prepared_clip_count": len(list(batch.prepared_clips or [])),
            "collected_segment_count": len(list(batch.collected_segments or [])),
            "annotate_error": str(batch.annotate_error or "").strip(),
        }
        if not batch.prepared_clips:
            return scored_primary
        if not batch.collected_segments:
            return scored_primary
        if batch.annotate_error:
            get_logger().log(f"  ⚠️ [{context_label}] STT2 점수 계산 실패: {batch.annotate_error}")

        applied = apply_recheck_selection_to_tracks_via_service(
            prepared_clips=batch.prepared_clips,
            rescue_segments=batch.collected_segments,
            settings=settings,
            replacement_is_better_fn=stt_rescue.replacement_is_better,
            mark_segments_fn=stt_rescue.mark_rescue_segments,
            base_tracks={"primary": scored_primary},
            decorate_segment_fn=lambda seg: {
                **seg,
                "stt_selected_source": "STT2",
                "stt_ensemble_source": "STT2_SELECTIVE_RECHECK",
                "stt_preview_source": "STT2",
                "stt_source": "STT2",
            },
            retention_ratios={"primary": float(settings.get("stt_selective_recheck_min_segment_retention_ratio", 0.9) or 0.9)},
        )

        if not applied.selection.applied_segments:
            get_logger().log(f"  ↩️ [{context_label}] 개선된 저점 구간이 없어 STT1 결과를 유지합니다.")
            self._last_secondary_low_score_recheck_info = {
                **dict(getattr(self, "_last_secondary_low_score_recheck_info", {}) or {}),
                "applied_range_count": 0,
                "skipped_range_count": len(list(applied.selection.skipped_ranges or [])),
                "applied_segment_count": 0,
                "retained_primary_segment_count": len(list(scored_primary or [])),
            }
            return scored_primary

        if applied.merged_tracks is None:
            candidate_updated = list(applied.preview_tracks.get("primary", []))
            get_logger().log(
                f"  ↩️ [{context_label}] STT2 보강 결과가 원본 세그먼트를 과도하게 줄여 "
                f"STT1 유지 ({len(scored_primary)}개 → {len(candidate_updated)}개)"
            )
            self._last_secondary_low_score_recheck_info = {
                **dict(getattr(self, "_last_secondary_low_score_recheck_info", {}) or {}),
                "applied_range_count": len(list(applied.selection.applied_ranges or [])),
                "skipped_range_count": len(list(applied.selection.skipped_ranges or [])),
                "applied_segment_count": len(list(applied.selection.applied_segments or [])),
                "retained_primary_segment_count": len(list(scored_primary or [])),
            }
            return scored_primary
        updated = list((applied.merged_tracks or {}).get("primary", []))
        get_logger().log(f"  ✅ [{context_label}] 저점 구간 {len(applied.selection.applied_ranges)}개를 STT2 결과로 보강했습니다.")
        self._last_secondary_low_score_recheck_info = {
            **dict(getattr(self, "_last_secondary_low_score_recheck_info", {}) or {}),
            "applied_range_count": len(list(applied.selection.applied_ranges or [])),
            "skipped_range_count": len(list(applied.selection.skipped_ranges or [])),
            "applied_segment_count": len(list(applied.selection.applied_segments or [])),
            "retained_primary_segment_count": len(updated),
        }
        return updated
