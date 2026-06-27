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

class VideoProcessorTranscribeRecheckMixin:
    @staticmethod
    def _recheck_range_duration_stats(ranges) -> tuple[float, float]:
        durations: list[float] = []
        for item in list(ranges or []):
            try:
                start = float(getattr(item, "start", 0.0) or 0.0)
                end = float(getattr(item, "end", start) or start)
            except Exception:
                continue
            durations.append(round(max(0.0, end - start), 6))
        if not durations:
            return 0.0, 0.0
        return round(sum(durations), 6), round(max(durations), 6)

    @staticmethod
    def _prepared_clip_duration_stats(prepared_clips) -> tuple[float, float]:
        durations: list[float] = []
        for clip in list(prepared_clips or []):
            if not isinstance(clip, dict):
                continue
            try:
                start = float(clip.get("start", 0.0) or 0.0)
                end = float(clip.get("end", start) or start)
            except Exception:
                continue
            durations.append(round(max(0.0, end - start), 6))
        if not durations:
            return 0.0, 0.0
        return round(sum(durations), 6), round(max(durations), 6)

    @staticmethod
    def _word_precision_range_reason_stats(ranges) -> dict[str, int]:
        stats = {
            "selected_range_count": 0,
            "precision_review_range_count": 0,
            "needs_review_range_count": 0,
            "red_range_count": 0,
            "yellow_range_count": 0,
            "risk_range_count": 0,
            "missing_word_range_count": 0,
        }
        for item in list(ranges or []):
            primary = getattr(item, "primary", {}) if item is not None else {}
            if not isinstance(primary, dict):
                primary = {}
            if any(bool(primary.get(key)) for key in ("editor_selected", "selected")):
                stats["selected_range_count"] += 1
            if bool(primary.get("precision_review")):
                stats["precision_review_range_count"] += 1
            if bool(primary.get("needs_review")):
                stats["needs_review_range_count"] += 1
            quality = primary.get("quality") if isinstance(primary.get("quality"), dict) else {}
            label = str(quality.get("confidence_label") or "").strip().lower()
            if label == "red":
                stats["red_range_count"] += 1
            elif label == "yellow":
                stats["yellow_range_count"] += 1
            flags = {str(flag) for flag in (quality.get("flags") or ())}
            if flags.intersection({"outside_vad_speech", "high_cps", "short_duration_long_text"}):
                stats["risk_range_count"] += 1
            if flags.intersection({"word_timestamps_missing"}):
                stats["missing_word_range_count"] += 1
        return stats

    @staticmethod
    def _secondary_recheck_range_reason_stats(ranges, *, threshold: float) -> dict[str, int]:
        stats = {
            "missing_voice_range_count": 0,
            "route_hint_range_count": 0,
            "low_score_range_count": 0,
            "empty_text_range_count": 0,
        }
        for item in list(ranges or []):
            primary = getattr(item, "primary", {}) if item is not None else {}
            if not isinstance(primary, dict):
                primary = {}
            meta = primary.get("asr_metadata") if isinstance(primary.get("asr_metadata"), dict) else {}
            primary_text = str(getattr(item, "primary_text", "") or primary.get("text") or "").strip()
            if bool(meta.get("missing_voice_candidate")):
                stats["missing_voice_range_count"] += 1
            if bool(primary.get("stt_route_secondary_recheck_hint")):
                stats["route_hint_range_count"] += 1
            try:
                score = float(getattr(item, "primary_score", 0.0) or 0.0)
            except Exception:
                score = 0.0
            if primary_text and score <= float(threshold):
                stats["low_score_range_count"] += 1
            if not primary_text:
                stats["empty_text_range_count"] += 1
        return stats

    def _reset_stt_stage_wall_clock_spans(self) -> None:
        self._stt_stage_wall_clock_spans = []

    def _record_stt_stage_wall_clock_span(self, stage: str, started: float, **metadata) -> None:
        try:
            elapsed = max(0.0, time.perf_counter() - float(started))
        except Exception:
            elapsed = 0.0
        spans = getattr(self, "_stt_stage_wall_clock_spans", None)
        if not isinstance(spans, list):
            spans = []
            self._stt_stage_wall_clock_spans = spans
        row = {
            "stage": str(stage or "unknown"),
            "elapsed_sec": round(elapsed, 6),
        }
        for key, value in dict(metadata or {}).items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                row[str(key)] = value
        spans.append(row)

    def _merge_stt_stage_wall_clock_spans(self, rows: list[dict] | tuple[dict, ...]) -> None:
        spans = getattr(self, "_stt_stage_wall_clock_spans", None)
        if not isinstance(spans, list):
            spans = []
            self._stt_stage_wall_clock_spans = spans
        for item in list(rows or []):
            if not isinstance(item, dict):
                continue
            row = {str(key): value for key, value in item.items() if isinstance(value, (str, int, float, bool))}
            if row.get("stage"):
                spans.append(row)

    def _stt_stage_wall_clock_spans_snapshot(self) -> list[dict]:
        spans = getattr(self, "_stt_stage_wall_clock_spans", None)
        if not isinstance(spans, list):
            return []
        return [dict(item) for item in spans if isinstance(item, dict)]

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
        started = time.perf_counter()
        input_count = len(segments or [])
        range_count = 0
        prepared_count = 0
        collected_count = 0
        applied_count = 0
        range_audio_sec = 0.0
        max_range_duration_sec = 0.0
        prepared_audio_sec = 0.0
        max_prepared_clip_duration_sec = 0.0
        result_count = input_count
        prepare_elapsed = 0.0
        collect_elapsed = 0.0
        annotate_elapsed = 0.0
        batch_elapsed = 0.0
        collect_cache_enabled = False
        collect_cache_hit = False
        collect_cache_write = False
        collect_provider_called = False
        reason_stats: dict[str, int] = {}
        status = "not_started"
        try:
            if not segments:
                status = "empty_input"
                return segments
            if not self._setting_bool(settings, "stt_word_timestamps_precision_enabled", True):
                status = "disabled"
                return segments
            if bool(settings.get("stt_word_timestamp_precision_pass", False)):
                status = "already_precision_pass"
                return segments
            if self._stt_word_timestamps_for_pass(settings):
                status = "word_timestamps_already_enabled"
                return segments

            ranges = self._word_precision_ranges(segments, settings)
            range_count = len(ranges)
            range_audio_sec, max_range_duration_sec = self._recheck_range_duration_stats(ranges)
            reason_stats = self._word_precision_range_reason_stats(ranges)
            if not ranges:
                status = "no_ranges"
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
                settings_overrides=precision_pass_overrides_via_service(),
                annotate_fn=self._annotate_stt_candidates,
                annotate_source="WORD_PRECISION",
                vad_segments=vad_strict,
                peer_segments=segments,
                is_single=False,
            )
            prepared_count = len(batch.prepared_clips or [])
            collected_count = len(batch.collected_segments or [])
            prepared_audio_sec, max_prepared_clip_duration_sec = self._prepared_clip_duration_stats(batch.prepared_clips)
            prepare_elapsed = float(batch.prepare_elapsed_sec or 0.0)
            collect_elapsed = float(batch.collect_elapsed_sec or 0.0)
            annotate_elapsed = float(batch.annotate_elapsed_sec or 0.0)
            batch_elapsed = float(batch.total_elapsed_sec or 0.0)
            collect_cache_enabled = bool(batch.collect_cache_enabled)
            collect_cache_hit = bool(batch.collect_cache_hit)
            collect_cache_write = bool(batch.collect_cache_write)
            collect_provider_called = bool(batch.collect_provider_called)
            if not batch.prepared_clips:
                status = "prepare_empty"
                return segments
            if not batch.collected_segments:
                status = "collect_empty"
                return segments
            if batch.annotate_error:
                get_logger().log(f"  ⚠️ [단어 타임태그] 정밀 구간 점수 계산 실패: {batch.annotate_error}")

            updated, applied = self._apply_word_precision_segments(
                segments,
                batch.collected_segments,
                ranges,
                settings,
            )
            applied_count = int(applied or 0)
            result_count = len(updated or [])
            status = "applied" if applied_count > 0 else "no_applied_segments"
            if applied > 0:
                get_logger().log(f"  ✅ [단어 타임태그] {applied}개 자막 타이밍을 단어 기준으로 보정했습니다.")
            return updated
        finally:
            self._record_stt_stage_wall_clock_span(
                "word_precision",
                started,
                status=status,
                input_segments=input_count,
                range_count=range_count,
                prepared_clip_count=prepared_count,
                collected_segment_count=collected_count,
                applied_count=applied_count,
                result_segments=result_count,
                range_audio_sec=round(range_audio_sec, 6),
                max_range_duration_sec=round(max_range_duration_sec, 6),
                prepared_audio_sec=round(prepared_audio_sec, 6),
                max_prepared_clip_duration_sec=round(max_prepared_clip_duration_sec, 6),
                prepare_elapsed_sec=round(prepare_elapsed, 6),
                collect_elapsed_sec=round(collect_elapsed, 6),
                annotate_elapsed_sec=round(annotate_elapsed, 6),
                batch_elapsed_sec=round(batch_elapsed, 6),
                collect_cache_enabled=collect_cache_enabled,
                collect_cache_hit=collect_cache_hit,
                collect_cache_write=collect_cache_write,
                collect_provider_called=collect_provider_called,
                **reason_stats,
            )
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
            settings_overrides=low_score_recheck_overrides_via_service(),
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
        started = time.perf_counter()
        input_count = len(chunk_segs or [])
        range_count = 0
        raw_range_count = 0
        prepared_count = 0
        collected_count = 0
        applied_count = 0
        applied_segment_count = 0
        range_audio_sec = 0.0
        max_range_duration_sec = 0.0
        prepared_audio_sec = 0.0
        max_prepared_clip_duration_sec = 0.0
        result_count = input_count
        prepare_elapsed = 0.0
        collect_elapsed = 0.0
        annotate_elapsed = 0.0
        batch_elapsed = 0.0
        collect_cache_enabled = False
        collect_cache_hit = False
        collect_cache_write = False
        collect_provider_called = False
        reason_stats: dict[str, int] = {}
        status = "not_started"
        try:
            if not chunk_segs:
                status = "empty_input"
                return chunk_segs
            if not self._selective_secondary_recheck_enabled(settings, primary_model):
                status = "disabled"
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
                status = "score_failed"
                get_logger().log(f"  ⚠️ [{context_label}] STT1 점수 계산 실패: {exc}")
                return chunk_segs
            result_count = len(scored_primary or [])

            range_settings = dict(settings)
            if target_end_sec is not None:
                range_settings["_stt_recheck_target_end_sec"] = float(target_end_sec)

            ranges, raw_range_count = build_selective_secondary_recheck_ranges(
                primary_segments=scored_primary,
                vad_segments=vad_strict,
                settings=range_settings,
                score_fn=self._segment_score_100,
                chunk_path_for_time=lambda target_sec: self._chunk_path_covering_time(chunk_dir, target_sec),
            )
            range_count = len(ranges)
            range_audio_sec, max_range_duration_sec = self._recheck_range_duration_stats(ranges)
            threshold = stt_rescue.threshold(settings)
            reason_stats = self._secondary_recheck_range_reason_stats(ranges, threshold=threshold)
            if raw_range_count > len(ranges):
                get_logger().log(
                    f"  ⚡ [{context_label}] STT2 재검사 예산 적용: {raw_range_count}개 → {len(ranges)}개"
                )
            if not ranges:
                status = "no_ranges"
                return scored_primary

            get_logger().log(
                f"  🔁 [{context_label}] STT1 {threshold:.0f}점 이하/누락/경계 후보 {len(ranges)}개를 STT2로 확인"
            )
            self._notify_stage(f"⏳ [STT] 저점 구간 {len(ranges)}개 STT2 확인 중")

            collect_fn = self._collect_transcribe_result
            batch_settings = settings
            if callable(preview_callback):
                if bool(settings.get("stt_recheck_collect_cache_enabled", False)):
                    batch_settings = {**dict(settings), "stt_recheck_collect_cache_enabled": False}
                stt2_preview_callback = self._ensemble_preview_callback("STT2", preview_callback)

                def collect_fn(*args, **kwargs):
                    kwargs["preview_callback"] = stt2_preview_callback
                    return self._collect_transcribe_result(*args, **kwargs)

            rescue_dir = os.path.join(chunk_dir, "_fast_stt2_recheck")
            shutil.rmtree(rescue_dir, ignore_errors=True)
            os.makedirs(rescue_dir, exist_ok=True)

            batch = prepare_and_collect_recheck_segments_via_service(
                ranges=ranges,
                out_dir=rescue_dir,
                settings=batch_settings,
                prepare_clip_fn=self._prepare_recheck_clip,
                collect_fn=collect_fn,
                model=secondary_model,
                label="Fast-STT2",
                settings_overrides=selective_secondary_recheck_overrides_via_service(),
                annotate_fn=self._annotate_stt_candidates,
                annotate_source="STT2",
                vad_segments=vad_strict,
                peer_segments=scored_primary,
                is_single=False,
            )
            prepared_count = len(batch.prepared_clips or [])
            collected_count = len(batch.collected_segments or [])
            prepared_audio_sec, max_prepared_clip_duration_sec = self._prepared_clip_duration_stats(batch.prepared_clips)
            prepare_elapsed = float(batch.prepare_elapsed_sec or 0.0)
            collect_elapsed = float(batch.collect_elapsed_sec or 0.0)
            annotate_elapsed = float(batch.annotate_elapsed_sec or 0.0)
            batch_elapsed = float(batch.total_elapsed_sec or 0.0)
            collect_cache_enabled = bool(batch.collect_cache_enabled)
            collect_cache_hit = bool(batch.collect_cache_hit)
            collect_cache_write = bool(batch.collect_cache_write)
            collect_provider_called = bool(batch.collect_provider_called)
            if not batch.prepared_clips:
                status = "prepare_empty"
                return scored_primary
            if not batch.collected_segments:
                status = "collect_empty"
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
            applied_count = len(applied.selection.applied_ranges or [])
            applied_segment_count = len(applied.selection.applied_segments or [])

            if not applied.selection.applied_segments:
                status = "no_improvement"
                get_logger().log(f"  ↩️ [{context_label}] 개선된 저점 구간이 없어 STT1 결과를 유지합니다.")
                return scored_primary

            if applied.merged_tracks is None:
                candidate_updated = list(applied.preview_tracks.get("primary", []))
                status = "retention_rejected"
                get_logger().log(
                    f"  ↩️ [{context_label}] STT2 보강 결과가 원본 세그먼트를 과도하게 줄여 "
                    f"STT1 유지 ({len(scored_primary)}개 → {len(candidate_updated)}개)"
                )
                return scored_primary
            updated = list((applied.merged_tracks or {}).get("primary", []))
            result_count = len(updated)
            status = "applied"
            get_logger().log(f"  ✅ [{context_label}] 저점 구간 {len(applied.selection.applied_ranges)}개를 STT2 결과로 보강했습니다.")
            return updated
        finally:
            self._record_stt_stage_wall_clock_span(
                "stt2_selective_recheck",
                started,
                status=status,
                input_segments=input_count,
                raw_range_count=raw_range_count,
                range_count=range_count,
                prepared_clip_count=prepared_count,
                collected_segment_count=collected_count,
                applied_count=applied_count,
                applied_segment_count=applied_segment_count,
                result_segments=result_count,
                range_audio_sec=round(range_audio_sec, 6),
                max_range_duration_sec=round(max_range_duration_sec, 6),
                prepared_audio_sec=round(prepared_audio_sec, 6),
                max_prepared_clip_duration_sec=round(max_prepared_clip_duration_sec, 6),
                prepare_elapsed_sec=round(prepare_elapsed, 6),
                collect_elapsed_sec=round(collect_elapsed, 6),
                annotate_elapsed_sec=round(annotate_elapsed, 6),
                batch_elapsed_sec=round(batch_elapsed, 6),
                collect_cache_enabled=collect_cache_enabled,
                collect_cache_hit=collect_cache_hit,
                collect_cache_write=collect_cache_write,
                collect_provider_called=collect_provider_called,
                **reason_stats,
            )
