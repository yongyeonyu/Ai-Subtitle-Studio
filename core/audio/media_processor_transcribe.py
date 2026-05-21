# Version: 03.13.08
# Phase: PHASE2
"""Whisper transcription, ensemble, and STT rescue helpers for VideoProcessor."""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.audio import stt_rescue
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


_parse_worker_json_line = parse_worker_json_line


def _stt_memory_pressure_stage(settings: dict | None) -> str:
    """Return the current memory pressure stage for STT reuse decisions."""

    return current_memory_pressure_stage(settings)


def _clean_whisper_word_text(text: str) -> str:
    cleaned = strip_stt_control_tokens(str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned, flags=re.UNICODE).strip()
    return cleaned


def _join_clean_word_texts(words: list[dict]) -> str:
    parts = []
    for word in list(words or []):
        if not isinstance(word, dict):
            continue
        cleaned = _clean_whisper_word_text(str(word.get("word", "") or ""))
        if cleaned:
            parts.append(cleaned)
    return " ".join(parts).strip()


class VideoProcessorTranscribeMixin:
    _chunk_sort_key = staticmethod(chunk_sort_key)
    _chunk_start_from_path = staticmethod(chunk_start_from_path)
    _mac_primary_fast_native_model = staticmethod(mac_primary_fast_native_model)
    _segment_chunk_path = staticmethod(segment_chunk_path)
    _segment_has_score = staticmethod(segment_has_score)
    _segment_needs_word_precision = staticmethod(segment_needs_word_precision)
    _segment_overlaps_range = staticmethod(segment_overlaps_range)
    _segment_score_100 = staticmethod(segment_score_100)
    _setting_bool = staticmethod(setting_bool)
    _setting_float = staticmethod(setting_float)
    _stt_candidate_keep_score = staticmethod(stt_candidate_keep_score)
    _stt_persistent_runtime_reuse_enabled = staticmethod(stt_persistent_runtime_reuse_enabled)
    _stt_selective_ensemble_enabled = staticmethod(stt_selective_ensemble_enabled)
    _stt_word_timestamps_for_pass = staticmethod(stt_word_timestamps_for_pass)
    _wav_duration = staticmethod(wav_duration)
    _resolve_runtime_whisper_model = staticmethod(resolve_runtime_whisper_model)
    _whisper_runtime_accelerator = staticmethod(whisper_runtime_accelerator)
    _ensemble_scheduler_context = staticmethod(ensemble_scheduler_context)
    _ensemble_scheduler_suffix = staticmethod(ensemble_scheduler_suffix)
    _clone_ensemble_chunk_dir = staticmethod(clone_ensemble_chunk_dir)
    _whisper_worker_options = staticmethod(whisper_worker_options)

    @staticmethod
    def _annotate_stt_candidates(segments, **kwargs):
        from core.audio.stt_candidate_scorer import annotate_stt_candidates

        return annotate_stt_candidates(segments, **kwargs)

    def _load_audio_route_hints(self, chunk_dir: str) -> dict[str, dict]:
        route_json = os.path.join(str(chunk_dir or ""), "audio_routes.json")
        if not route_json or not os.path.exists(route_json):
            return {}
        try:
            with open(route_json, "r", encoding="utf-8") as handle:
                rows = json.load(handle)
        except Exception:
            return {}
        hints: dict[str, dict] = {}
        for row in list(rows or []):
            if not isinstance(row, dict):
                continue
            name = os.path.basename(str(row.get("path") or ""))
            if name:
                hints[name] = dict(row)
        return hints

    def _apply_audio_route_segment_hints(
        self,
        segments: list[dict],
        chunk_item: dict,
        route_hints: dict[str, dict] | None,
    ) -> list[dict]:
        if not segments or not route_hints:
            return segments
        chunk_name = os.path.basename(str((chunk_item or {}).get("input_path") or ""))
        route = dict((route_hints or {}).get(chunk_name) or {})
        if not route:
            return segments
        confidence = float(route.get("confidence", route.get("self_score", route.get("feature_confidence", 0.0))) or 0.0)
        risk_level = str(route.get("risk_level") or "low").strip().lower()
        precision_review = bool(route.get("precision_review"))
        secondary_hint = bool(route.get("secondary_recheck_hint"))
        strategy = str(route.get("audio_strategy") or "")
        updated: list[dict] = []
        for seg in list(segments or []):
            out = dict(seg)
            meta = dict(out.get("asr_metadata") or {})
            meta["adaptive_audio_route"] = {
                "strategy": strategy,
                "confidence": round(confidence, 4),
                "risk_level": risk_level,
                "hysteresis_applied": bool(route.get("hysteresis_applied")),
                "precision_review": precision_review,
                "secondary_recheck_hint": secondary_hint,
            }
            out["asr_metadata"] = meta
            if precision_review:
                out["precision_review"] = True
            if risk_level == "high":
                out["needs_review"] = True
            if secondary_hint:
                out["stt_route_secondary_recheck_hint"] = True
            updated.append(out)
        return updated

    def _collect_transcribe_result(
        self,
        chunk_dir: str,
        model: str,
        target_end_sec: float = None,
        is_single: bool = False,
        label: str = "STT",
        preview_callback=None,
        settings_overrides: dict | None = None,
    ) -> list[dict]:
        try:
            effective_settings = self._load_all_settings()
        except Exception:
            effective_settings = {}
        if settings_overrides:
            effective_settings.update(dict(settings_overrides))
        reuse_worker = self._stt_persistent_runtime_reuse_enabled(effective_settings)
        pressure_stage = _stt_memory_pressure_stage(effective_settings)
        resource_policy = stage_owned_resource_policy(effective_settings, pressure_stage=pressure_stage)
        if reuse_worker and not resource_policy.allow_stt_collect_worker_reuse:
            # Stage-owned resource policy keeps STT reuse fast only while macOS
            # has enough memory headroom for persistent WhisperKit/MLX workers.
            reuse_worker = False
        cache_key = f"{self.language}|{str(model or '').strip()}"
        worker = None
        transient_worker = True
        worker_id = 0

        with self._ensemble_child_lock:
            children = getattr(self, "_ensemble_child_processors", None)
            if not isinstance(children, list):
                children = []
                self._ensemble_child_processors = children
            if reuse_worker:
                cache = getattr(self, "_stt_collect_worker_cache", None)
                if not isinstance(cache, dict):
                    cache = {}
                    self._stt_collect_worker_cache = cache
                busy = getattr(self, "_stt_collect_worker_busy", None)
                if not isinstance(busy, set):
                    busy = set()
                    self._stt_collect_worker_busy = busy
                cached = cache.get(cache_key)
                if cached is not None and id(cached) not in busy:
                    worker = cached
                    transient_worker = False
                    if worker not in children:
                        children.append(worker)
                else:
                    worker = type(self)()
                    if cached is None:
                        cache[cache_key] = worker
                        transient_worker = False
                    if worker not in children:
                        children.append(worker)
                worker_id = id(worker)
                busy.add(worker_id)
            else:
                worker = type(self)()
                children.append(worker)

        worker.language = self.language
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
        worker._fast_mode_overrides = dict(effective_settings or {}) if effective_settings else None
        result: list[dict] = []
        try:
            try:
                for chunk_segs, _idx, _total in worker.transcribe(
                    chunk_dir,
                    is_fast_mode=False,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    model_override=model,
                    cleanup_chunk_dir=False,
                    log_label=label,
                    preview_callback=preview_callback,
                    _allow_window_rolling=False,
                ):
                    result.extend(chunk_segs or [])
            except RuntimeError as exc:
                get_logger().log(f"  ⚠️ [{label}] 보조 STT 재검사 실패, 기존 STT 결과를 유지합니다: {exc}")
                result = []
        finally:
            if reuse_worker:
                with self._ensemble_child_lock:
                    busy = getattr(self, "_stt_collect_worker_busy", set())
                    try:
                        busy.discard(worker_id)
                    except Exception:
                        pass
            if transient_worker:
                worker.stop_transcribe()
            with self._ensemble_child_lock:
                if transient_worker:
                    try:
                        self._ensemble_child_processors.remove(worker)
                    except (AttributeError, ValueError):
                        pass
        return result

    def _release_after_transcribe_job(self, log_label: str = "STT", *, force_stop: bool = False) -> None:
        try:
            settings = self._load_all_settings()
        except Exception:
            settings = {}
        keep_warm = (not force_stop) and self._stt_persistent_runtime_reuse_enabled(settings)
        pressure_stage = _stt_memory_pressure_stage(settings)
        resource_policy = stage_owned_resource_policy(settings, pressure_stage=pressure_stage)
        if keep_warm and not resource_policy.keep_stt_worker_warm:
            # Do not preserve STT worker UI/runtime behavior here. This is a
            # performance guard: a warm worker that saves startup time can make
            # later subtitles slower when system memory is already critical.
            keep_warm = False

        def _alive(proc) -> bool:
            try:
                return proc is not None and proc.poll() is None
            except Exception:
                return False

        own_alive = _alive(getattr(self, "_whisper_runner_proc", None)) or _alive(
            getattr(self, "_whisperkit_runner_proc", None)
        )
        child_alive = False
        if keep_warm:
            try:
                with getattr(self, "_ensemble_child_lock", threading.Lock()):
                    children = list(getattr(self, "_ensemble_child_processors", []) or [])
                for child in children:
                    if _alive(getattr(child, "_whisper_runner_proc", None)) or _alive(
                        getattr(child, "_whisperkit_runner_proc", None)
                    ):
                        child_alive = True
                        break
            except Exception:
                child_alive = False

        if keep_warm and (own_alive or child_alive):
            self._whisper_proc = None
            try:
                get_logger().log(f"🔥 [{log_label}] macOS STT persistent worker 유지: 다음 STT 재사용")
            except Exception:
                pass
            return

        if pressure_stage == "critical" and (own_alive or child_alive):
            try:
                get_logger().log(f"🧹 [{log_label}] 메모리 critical: STT persistent worker 재사용 중단")
            except Exception:
                pass

        self.stop_transcribe()
        # Only the expensive GPU cache clear is needed under hard pressure.
        # Keeping this warning stage lightweight reduces per-run overhead while
        # preserving steady-state latency under normal/mild memory pressure.
        clear_audio_model_memory_caches(include_gpu=resource_policy.include_gpu_on_release)
        try:
            get_logger().log(f"🧹 [{log_label}] 음성인식 모델/가속기 메모리 정리 완료")
        except Exception:
            pass

    def release_vad_runtime_models(self, *, log_context: str = "VAD") -> None:
        released = bool(getattr(self, "_vad_loaded", False) or getattr(self, "_vad_model", None) is not None)
        try:
            model = getattr(self, "_vad_model", None)
            if model is not None and hasattr(model, "to"):
                try:
                    model.to("cpu")
                except Exception:
                    pass
            self._vad_model = None
            self._vad_utils = None
            self._vad_loaded = False
        except Exception:
            pass
        if released:
            clear_audio_model_memory_caches(include_gpu=True)
            try:
                get_logger().log(f"🧹 [{log_context}] VAD 모델/가속기 메모리 정리 완료")
            except Exception:
                pass

    def _normalize_scored_stt_tracks(
        self,
        tracks: dict[str, list[dict]],
        settings: dict | None,
    ) -> dict[str, list[dict]]:
        from core.audio.stt_candidate_scorer import filter_scored_stt_candidates

        keep_score = self._stt_candidate_keep_score(settings)
        normalized, dropped_counts = normalize_scored_tracks_via_service(
            tracks,
            keep_score=keep_score,
            filter_fn=lambda items, min_score: filter_scored_stt_candidates(items, min_score=min_score),
        )
        for label, filtered in normalized.items():
            dropped = int(dropped_counts.get(label, 0))
            if dropped > 0:
                get_logger().log(
                    f"  🧹 [STT 정리] {label} 저품질 후보 {dropped}개 제외 "
                    f"(유지 기준 {keep_score:.0f}점)"
                )
        return normalized
    def _ensemble_preview_callback(self, label: str, preview_callback):
        if not callable(preview_callback):
            return None
        source_label = str(label or "STT").strip() or "STT"

        def _callback(chunk_segs, _worker_label=None):
            preview = [dict(seg) for seg in (chunk_segs or [])]
            if not preview:
                return
            try:
                preview_callback(preview, source_label)
            except Exception:
                pass

        return _callback
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
        try:
            names = sorted(name for name in os.listdir(chunk_dir) if name.endswith(".wav"))
        except Exception:
            return ""
        for name in names:
            path = os.path.join(chunk_dir, name)
            start = self._chunk_start_from_path(path)
            duration = self._wav_duration(path)
            if duration <= 0.0:
                continue
            if (start - 0.25) <= float(target_sec or 0.0) <= (start + duration + 0.25):
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
    ) -> list[dict]:
        refined = self._recheck_primary_low_score_with_secondary(
            chunk_dir,
            segments,
            settings,
            vad_strict,
            primary_model,
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

        ranges = self._word_precision_ranges(segments, settings)
        if not ranges:
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
        if not batch.prepared_clips:
            return segments
        if not batch.collected_segments:
            return segments
        if batch.annotate_error:
            get_logger().log(f"  ⚠️ [단어 타임태그] 정밀 구간 점수 계산 실패: {batch.annotate_error}")

        updated, applied = self._apply_word_precision_segments(
            segments,
            batch.collected_segments,
            ranges,
            settings,
        )
        if applied > 0:
            get_logger().log(f"  ✅ [단어 타임태그] {applied}개 자막 타이밍을 단어 기준으로 보정했습니다.")
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
    ) -> list[dict]:
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

        ranges, raw_range_count = build_selective_secondary_recheck_ranges(
            primary_segments=scored_primary,
            vad_segments=vad_strict,
            settings=settings,
            score_fn=self._segment_score_100,
            chunk_path_for_time=lambda target_sec: self._chunk_path_covering_time(chunk_dir, target_sec),
        )
        if raw_range_count > len(ranges):
            get_logger().log(
                f"  ⚡ [{context_label}] STT2 재검사 예산 적용: {raw_range_count}개 → {len(ranges)}개"
            )
        if not ranges:
            return scored_primary

        threshold = stt_rescue.threshold(settings)
        get_logger().log(
            f"  🔁 [{context_label}] STT1 {threshold:.0f}점 이하/누락 후보 {len(ranges)}개만 STT2로 확인"
        )
        self._notify_stage(f"⏳ [STT] 저점 구간 {len(ranges)}개 STT2 확인 중")

        rescue_dir = os.path.join(chunk_dir, "_fast_stt2_recheck")
        shutil.rmtree(rescue_dir, ignore_errors=True)
        os.makedirs(rescue_dir, exist_ok=True)
        batch = prepare_and_collect_recheck_segments_via_service(
            ranges=ranges,
            out_dir=rescue_dir,
            settings=settings,
            prepare_clip_fn=self._prepare_recheck_clip,
            collect_fn=self._collect_transcribe_result,
            model=secondary_model,
            label="Fast-STT2",
            settings_overrides=selective_secondary_recheck_overrides_via_service(),
            annotate_fn=self._annotate_stt_candidates,
            annotate_source="STT2",
            vad_segments=vad_strict,
            peer_segments=scored_primary,
            is_single=False,
        )
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
            return scored_primary

        if applied.merged_tracks is None:
            candidate_updated = list(applied.preview_tracks.get("primary", []))
            get_logger().log(
                f"  ↩️ [{context_label}] STT2 보강 결과가 원본 세그먼트를 과도하게 줄여 "
                f"STT1 유지 ({len(scored_primary)}개 → {len(candidate_updated)}개)"
            )
            return scored_primary
        updated = list((applied.merged_tracks or {}).get("primary", []))
        get_logger().log(f"  ✅ [{context_label}] 저점 구간 {len(applied.selection.applied_ranges)}개를 STT2 결과로 보강했습니다.")
        return updated

    def _transcribe_selective_ensemble(
        self,
        chunk_dir: str,
        primary_model: str,
        secondary_model: str,
        settings: dict,
        target_end_sec: float = None,
        is_single: bool = False,
        preview_callback=None,
        cleanup_chunk_dir: bool = True,
    ):
        get_logger().log(
            "\n🎧 [STT 선택 앙상블] STT1 빠른 1차 인식 → 저신뢰 구간만 STT2/단어 타임태그 정밀 보강 "
            f"(STT1: {primary_model.split(chr(47))[-1]}, STT2: {secondary_model.split(chr(47))[-1]})"
        )
        self._notify_stage("⏳ [STT] STT1 우선 인식 중")
        vad_strict = []
        vad_json = os.path.join(chunk_dir, "vad_strict.json")
        if os.path.exists(vad_json):
            try:
                with open(vad_json, "r", encoding="utf-8") as f:
                    vad_strict = json.load(f)
            except Exception:
                vad_strict = []

        try:
            primary_overrides = {
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_candidate_scoring_enabled": True,
                "stt_word_timestamp_precision_pass": False,
                "stt_word_timestamps_precision_enabled": False,
            }
            primary_segments = self._collect_transcribe_result(
                chunk_dir,
                primary_model,
                target_end_sec=target_end_sec,
                is_single=is_single,
                label="STT1",
                preview_callback=self._ensemble_preview_callback("STT1", preview_callback),
                settings_overrides=primary_overrides,
            )
            if not primary_segments:
                get_logger().log("  ⚠️ [STT 선택 앙상블] STT1 결과가 비어 있어 STT2 전체 인식으로 대체합니다.")
                fallback_overrides = {
                    "stt_ensemble_enabled": False,
                    "stt_selective_secondary_recheck_enabled": False,
                    "stt_candidate_scoring_enabled": True,
                    "stt_word_timestamp_precision_pass": False,
                    "stt_word_timestamps_precision_enabled": False,
                }
                primary_segments = self._collect_transcribe_result(
                    chunk_dir,
                    secondary_model,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    label="STT2",
                    preview_callback=self._ensemble_preview_callback("STT2", preview_callback),
                    settings_overrides=fallback_overrides,
                )
                for seg in primary_segments:
                    seg["stt_selected_source"] = "STT2"
                    seg["stt_ensemble_source"] = "STT2_FALLBACK"
            else:
                primary_segments = self._recheck_primary_low_score_with_secondary(
                    chunk_dir,
                    primary_segments,
                    settings,
                    vad_strict,
                    primary_model,
                )

            primary_segments = self._recheck_word_timestamps_for_precision(
                chunk_dir,
                primary_segments,
                settings,
                vad_strict,
                primary_model,
            )
            try:
                primary_segments = self._annotate_stt_candidates(
                    primary_segments,
                    source="STT1_SELECTIVE",
                    vad_segments=vad_strict,
                    settings=settings,
                )
            except Exception as exc:
                get_logger().log(f"  ⚠️ [STT 선택 앙상블] 최종 점수 계산 실패: {exc}")

            for seg in primary_segments:
                seg.setdefault("stt_selected_source", "STT1")
                seg.setdefault("stt_ensemble_source", "STT1_SELECTIVE")

            if vad_strict and bool(settings.get("vad_post_stt_align_enabled", True)):
                from core.subtitle_quality.vad_alignment_checker import adjust_segments_to_vad_boundaries

                self._notify_stage("⏳ [VAD] 선택 앙상블 자막 위치 재계산 중")
                primary_segments, adjusted_count = adjust_segments_to_vad_boundaries(
                    primary_segments,
                    vad_strict,
                    max_shift_sec=float(settings.get("vad_post_stt_max_shift_sec", 0.7) or 0.7),
                    edge_pad_sec=float(settings.get("vad_post_stt_edge_pad_sec", 0.04) or 0.04),
                )
                get_logger().log(f"  🎯 [VAD 후처리] 선택 앙상블 자막 위치 {adjusted_count}개 보정")

            if callable(preview_callback):
                try:
                    preview_callback([dict(seg) for seg in primary_segments], "STT-SELECTIVE")
                except Exception:
                    pass
            get_logger().log(
                "  ✅ [STT 선택 앙상블] 최종 후보 완료 "
                f"({len(primary_segments)}개, STT2는 저신뢰/누락 후보에만 사용)"
            )
            yield primary_segments, 1, 1
        finally:
            if cleanup_chunk_dir:
                shutil.rmtree(chunk_dir, ignore_errors=True)
            self._release_after_transcribe_job("STT 선택 앙상블")

    def _native_batch_refine_requested(
        self,
        settings: dict,
        primary_model: str,
        *,
        model_override: str | None,
        total_chunks: int,
    ) -> bool:
        """Finish native STT1 first, then batch expensive rechecks once.

        Running low-score STT2 rescue or word-timestamp precision inside every
        chunk callback repeatedly hops from Swift/MLX back into Python.  On
        macOS the faster path is one native STT1 pass followed by a single
        batched refinement over only the uncertain ranges.
        """
        if model_override is not None:
            return False
        if not bool(getattr(config, "IS_MAC", False)):
            return False
        if total_chunks <= 1:
            return False
        if not self._setting_bool(settings, "stt_native_batch_refine_enabled", True):
            return False
        if bool(settings.get("stt_ensemble_enabled", False)):
            return False
        if bool(settings.get("stt_word_timestamp_precision_pass", False)):
            return False
        if bool(settings.get("stt_rescue_whisper_mode", False)):
            return False

        word_precision = (
            self._setting_bool(settings, "stt_word_timestamps_precision_enabled", True)
            and not self._stt_word_timestamps_for_pass(settings)
        )
        secondary_recheck = self._selective_secondary_recheck_enabled(settings, primary_model)
        return bool(word_precision or secondary_recheck)

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
        if _allow_window_rolling and self._windowed_span_ranges(q, s):
            had_window_error = False
            try:
                yield from self._transcribe_with_windowed_spans(
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
        chunks = sorted(
            [f for f in os.listdir(chunk_dir) if f.endswith(".wav")],
            key=self._chunk_sort_key,
        )
        t_sec = 1.0
        items: list[dict] = []
        for i, cf in enumerate(chunks):
            cp = os.path.join(chunk_dir, cf)
            m = re.search(r'vad_\d+_([\d\.]+)\.wav', cf)
            ov_start = float(m.group(1)) if m else i * 30.0
            try:
                with wave.open(cp, "r") as w:
                    chunk_duration = w.getnframes() / float(w.getframerate())
                    chunk_end = ov_start + chunk_duration
            except Exception:
                chunk_duration = 30.0
                chunk_end = ov_start + 30.0
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

        if _allow_window_rolling and self._windowed_span_ranges(q, _s):
            had_window_error = False
            try:
                yield from self._transcribe_with_windowed_spans(
                    chunk_dir,
                    q,
                    _s,
                    vad_strict=vad_strict,
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

        safe_paths = [x["input_path"] for x in q]
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
                            mac_task_id = submit_task(
                                proc=proc,
                                chunk_paths=safe_paths,
                                model=target_model,
                                language=self.language,
                                temperature_values=temperature_values,
                                word_timestamps=word_timestamps,
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
                done_seen = False
                while received < total or (done_seen and next_emit_idx in pending_payloads):
                    line = proc.stdout.readline()
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
                        if received >= total:
                            break
                        continue

                    if data.get("fatal_error") or data.get("error"):
                        had_error = True
                        msg = data.get("fatal_error") or data.get("error") or "unknown whisper worker error"
                        stage = data.get("stage", "worker")
                        get_logger().log(f"  [FAIL] Whisper worker error ({stage}): {msg}")
                        raise RuntimeError(f"whisper_worker_error[{stage}]: {msg}")

                    idx = int(data.get("index", received))
                    item = q[idx]
                    payload = data.get("result") if "result" in data else {"error": data.get("error", "")}
                    if isinstance(payload, dict):
                        payload.setdefault("backend", data.get("backend", "mlx-whisper"))
                        payload.setdefault("language_probability", data.get("language_probability"))
                        payload.setdefault("chunk_path", item.get("input_path"))
                        payload.setdefault("word_timestamps", data.get("word_timestamps", word_timestamps))
                    pending_payloads[idx] = (item, payload)
                    received += 1

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
    def _parse_whisper_payload(self, data: dict, item: dict, vad_strict: list,
                           target_end_sec: float = None, is_single: bool = False) -> list[dict]:
        chunk_segs = []
        if "segments" not in data:
            if data.get("error"):
                get_logger().log(f"  ⚠️ Whisper 오류: {data.get('error')}")
            return chunk_segs

        offset = item["ov_start_offset"]

        for seg in data["segments"]:
            words = seg.get("words", [])
            exact_start = seg["start"] + offset
            exact_end = seg["end"] + offset
            offset_words = []
            cleaned_segment_text = _clean_whisper_word_text(seg.get("text", ""))

            if words:
                valid_words = [
                    {**w, "word": _clean_whisper_word_text(w.get("word", ""))}
                    for w in words
                    if "start" in w and "end" in w and _clean_whisper_word_text(w.get("word", ""))
                ]

                word_filter_vad = [v for v in vad_strict if v.get("vad_word_filter", True)]
                if word_filter_vad:
                    temp_words = []
                    for w in valid_words:
                        w_start = w["start"] + offset
                        w_end = w["end"] + offset
                        is_valid = False
                        for v in word_filter_vad:
                            if w_start <= v["end"] + 0.5 and w_end >= v["start"] - 0.5:
                                is_valid = True
                                break
                        if is_valid:
                            temp_words.append(w)
                    valid_words = temp_words

                if valid_words:
                    exact_start = valid_words[0]["start"] + offset
                    exact_end = valid_words[-1]["end"] + offset
                    for w in valid_words:
                        word_item = {
                            "word": _clean_whisper_word_text(w.get("word", "")),
                            "start": w["start"] + offset,
                            "end": w["end"] + offset
                        }
                        for conf_key in ("confidence", "probability", "score"):
                            if conf_key in w:
                                word_item[conf_key] = w.get(conf_key)
                        if word_item["word"]:
                            offset_words.append(word_item)

            if words and not offset_words:
                continue
            if offset_words:
                rebuilt_text = _join_clean_word_texts(offset_words)
                if rebuilt_text:
                    cleaned_segment_text = rebuilt_text

            if is_single and target_end_sec is not None:
                if exact_start >= target_end_sec:
                    continue
                if exact_end > target_end_sec:
                    exact_end = target_end_sec
            if not cleaned_segment_text:
                continue

            segment = {
                "start": exact_start,
                "end": exact_end,
                "text": cleaned_segment_text,
                "words": offset_words,
            }
            for key in (
                "avg_logprob",
                "compression_ratio",
                "no_speech_prob",
                "temperature",
                "tokens",
                "word_confidence",
            ):
                if key in seg:
                    segment[key] = seg.get(key)
            segment = attach_asr_metadata(
                segment,
                backend=data.get("backend"),
                language_probability=data.get("language_probability"),
                chunk_path=data.get("chunk_path") or item.get("input_path"),
            )
            asr_metadata = dict(segment.get("asr_metadata") or {})
            if data.get("word_timestamps") is not None:
                asr_metadata["word_timestamps_requested"] = bool(data.get("word_timestamps"))
            asr_metadata["word_timestamps_available"] = bool(offset_words)
            asr_metadata["chunk_start"] = round(float(offset), 6)
            asr_metadata["chunk_end"] = round(float(offset) + float(item.get("duration", 0.0) or 0.0), 6)
            asr_metadata["chunk_duration"] = round(float(item.get("duration", 0.0) or 0.0), 6)
            segment["asr_metadata"] = asr_metadata
            if vad_strict:
                segment = annotate_segment_vad_alignment(segment, vad_strict)
            segment = annotate_segment_hallucination_risk(segment, vad_segments=vad_strict)
            chunk_segs.append(segment)

        return chunk_segs

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

    def _stt_quarter_parallel_window_workers(self, settings: dict, total_windows: int) -> tuple[int, dict]:
        window_parallel_enabled = bool(
            settings.get(
                "stt_window_parallel_enabled",
                settings.get("stt_quarter_parallel_experiment_enabled", True),
            )
        )
        if total_windows < 2 or not window_parallel_enabled:
            return 1, {}
        pressure_stage = _stt_memory_pressure_stage(settings)
        if pressure_stage == "critical":
            get_logger().log("  🧵 [STT 1/4 병렬] 메모리 critical 상태라 병렬 창 처리를 건너뜁니다.")
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
        workers, scheduler_meta = runtime_parallel_worker_plan(
            settings=settings,
            task="stt_window",
            requested=requested,
            workload=total_windows,
            minimum=1,
            maximum=min(4, total_windows),
            reserve_task="stt",
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

        parallel_workers, scheduler_meta = self._stt_quarter_parallel_window_workers(settings, total_windows)
        if parallel_workers > 1:
            suffix = self._ensemble_scheduler_suffix(scheduler_meta, "windowed")
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
