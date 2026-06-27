# Version: 03.13.08
# Phase: PHASE2
"""Whisper transcription, ensemble, and STT rescue helpers for VideoProcessor."""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shutil
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

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


_parse_worker_json_line = parse_worker_json_line


class SttWorkerTimeout(RuntimeError):
    """Raised when a persistent STT worker stops producing chunk responses."""


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


STT_PRIMARY_COLLECT_CACHE_SCHEMA = "ai_subtitle_studio.stt_primary_collect_cache.v1"
_STT_PRIMARY_COLLECT_CACHE_BY_PATH: dict[str, dict] = {}
_STT_PRIMARY_COLLECT_CACHE_LOCK = threading.Lock()
_STT_PRIMARY_COLLECT_CACHE_IGNORED_SETTING_KEYS = {
    "stt_primary_collect_cache_enabled",
    "stt_primary_collect_cache_path",
    "stt_primary_collect_cache_max_entries",
    "stt_recheck_collect_cache_enabled",
    "stt_recheck_collect_cache_path",
    "stt_recheck_collect_cache_max_entries",
    "subtitle_llm_context_keep_cache_enabled",
    "subtitle_llm_context_keep_cache_path",
    "subtitle_llm_context_keep_cache_max_entries",
    "subtitle_llm_macro_response_cache_enabled",
    "subtitle_llm_macro_response_cache_path",
    "subtitle_llm_macro_response_cache_max_entries",
}


def _stt_primary_collect_cache_enabled(settings: dict | None) -> bool:
    value = dict(settings or {}).get("stt_primary_collect_cache_enabled", False)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "사용 안함", "끔"}
    return bool(value)


def _stt_primary_collect_cache_path(settings: dict | None) -> Path:
    override = str(dict(settings or {}).get("stt_primary_collect_cache_path") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path(config.OUTPUT_DIR) / "stt_primary_collect_cache" / "primary_collect_v1.json"


def _stt_primary_collect_cache_max_entries(settings: dict | None) -> int:
    try:
        return max(1, int(dict(settings or {}).get("stt_primary_collect_cache_max_entries", 64) or 64))
    except Exception:
        return 64


def _stt_primary_collect_label(label: str) -> bool:
    normalized = str(label or "").strip().upper().replace("_", "-")
    return normalized == "STT1" or normalized.startswith("STT1-") or normalized.startswith("BENCH-STT1")


def _stt_primary_collect_cache_safe_payload(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {
            str(key): _stt_primary_collect_cache_safe_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _STT_PRIMARY_COLLECT_CACHE_IGNORED_SETTING_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_stt_primary_collect_cache_safe_payload(item) for item in value]
    return str(value)


def _stt_primary_file_sha256(path: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with open(path, "rb") as handle:
            while True:
                data = handle.read(1024 * 1024)
                if not data:
                    break
                size += len(data)
                digest.update(data)
        return digest.hexdigest(), size
    except Exception:
        return "", 0


def _stt_primary_chunk_fingerprints(chunk_dir: str) -> list[dict]:
    root = os.path.abspath(str(chunk_dir or ""))
    if not root or not os.path.isdir(root):
        return []
    try:
        names = sorted(
            [name for name in os.listdir(root) if str(name).lower().endswith(".wav")],
            key=chunk_sort_key,
        )
    except Exception:
        names = []
    fingerprints: list[dict] = []
    for name in names:
        path = os.path.join(root, name)
        sha256, size_bytes = _stt_primary_file_sha256(path)
        fingerprints.append(
            {
                "name": str(name),
                "audio_sha256": sha256,
                "size_bytes": int(size_bytes),
            }
        )
    return fingerprints


def _stt_primary_collect_cache_key(
    *,
    chunk_dir: str,
    settings: dict | None,
    model: str,
    language: str,
    label: str,
    target_end_sec: float | None,
    is_single: bool,
    settings_overrides: dict | None,
) -> str:
    payload = {
        "schema": STT_PRIMARY_COLLECT_CACHE_SCHEMA,
        "model": str(model or ""),
        "language": str(language or ""),
        "label": str(label or ""),
        "target_end_sec": round(float(target_end_sec), 6) if target_end_sec is not None else None,
        "is_single": bool(is_single),
        "settings": _stt_primary_collect_cache_safe_payload(dict(settings or {})),
        "settings_overrides": _stt_primary_collect_cache_safe_payload(dict(settings_overrides or {})),
        "chunks": _stt_primary_chunk_fingerprints(chunk_dir),
    }
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _load_stt_primary_collect_cache_unlocked(path: Path) -> dict:
    cache_path = str(path)
    if cache_path in _STT_PRIMARY_COLLECT_CACHE_BY_PATH:
        return _STT_PRIMARY_COLLECT_CACHE_BY_PATH[cache_path]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != STT_PRIMARY_COLLECT_CACHE_SCHEMA:
            raise ValueError("unsupported cache schema")
        entries = payload.get("entries")
        cache = dict(entries) if isinstance(entries, dict) else {}
    except Exception:
        cache = {}
    _STT_PRIMARY_COLLECT_CACHE_BY_PATH[cache_path] = cache
    return cache


def _cached_stt_primary_collect_segments(path: Path, key: str) -> tuple[list[dict], dict] | None:
    with _STT_PRIMARY_COLLECT_CACHE_LOCK:
        cache = _load_stt_primary_collect_cache_unlocked(path)
        entry = cache.get(key)
        if not isinstance(entry, dict):
            return None
        segments = entry.get("segments")
        if not isinstance(segments, list):
            return None
        clean = [dict(seg) for seg in segments if isinstance(seg, dict)]
        if segments != [] and not clean:
            return None
        diagnostics = entry.get("diagnostics")
        return clean, dict(diagnostics) if isinstance(diagnostics, dict) else {}


def _store_stt_primary_collect_segments(
    path: Path,
    key: str,
    segments: list[dict],
    *,
    max_entries: int,
    diagnostics: dict | None = None,
) -> bool:
    clean_segments = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    if not clean_segments:
        return False
    try:
        with _STT_PRIMARY_COLLECT_CACHE_LOCK:
            cache = _load_stt_primary_collect_cache_unlocked(path)
            clean_diagnostics = {
                str(diag_key): value
                for diag_key, value in dict(diagnostics or {}).items()
                if isinstance(value, (str, int, float, bool)) or value is None
            }
            cache[key] = {
                "schema": STT_PRIMARY_COLLECT_CACHE_SCHEMA,
                "created_epoch": round(time.time(), 3),
                "segments": clean_segments,
                "diagnostics": clean_diagnostics,
            }
            entries = dict(list(cache.items())[-max(1, int(max_entries)) :])
            payload = {
                "schema": STT_PRIMARY_COLLECT_CACHE_SCHEMA,
                "updated_epoch": round(time.time(), 3),
                "entries": entries,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
            tmp.replace(path)
            _STT_PRIMARY_COLLECT_CACHE_BY_PATH[str(path)] = entries
        return True
    except Exception:
        return False

from core.audio.media_processor_transcribe_policy import VideoProcessorTranscribePolicyMixin
from core.audio.media_processor_transcribe_recheck import VideoProcessorTranscribeRecheckMixin
from core.audio.media_processor_transcribe_run import VideoProcessorTranscribeRunMixin
from core.audio.media_processor_transcribe_windowed import VideoProcessorTranscribeWindowedMixin


class VideoProcessorTranscribeMixin(
    VideoProcessorTranscribeRunMixin,
    VideoProcessorTranscribePolicyMixin,
    VideoProcessorTranscribeRecheckMixin,
    VideoProcessorTranscribeWindowedMixin,
):
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

    def _audio_chunk_manifest(
        self,
        chunk_dir: str,
        *,
        fallback_step_sec: float = 0.0,
        require_vad_start: bool = False,
    ) -> list[dict]:
        root = os.path.abspath(str(chunk_dir or ""))
        if not root:
            return []
        signature = chunk_dir_signature(root)
        key = (
            signature if signature is not None else root,
            round(float(fallback_step_sec or 0.0), 6),
            bool(require_vad_start),
        )
        cache = getattr(self, "_audio_chunk_manifest_cache", None)
        if not isinstance(cache, dict):
            cache = {}
        if key in cache:
            return [dict(row) for row in cache[key]]
        rows = audio_chunk_manifest(
            root,
            fallback_step_sec=fallback_step_sec,
            require_vad_start=require_vad_start,
            signature=signature,
        )
        if len(cache) >= 4:
            cache.clear()
        cache[key] = [dict(row) for row in rows]
        self._audio_chunk_manifest_cache = cache
        return [dict(row) for row in rows]

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
        self._last_collect_transcribe_diagnostics = {}
        if reuse_worker and not resource_policy.allow_stt_collect_worker_reuse:
            # Stage-owned resource policy keeps STT reuse fast only while macOS
            # has enough memory headroom for persistent WhisperKit/MLX workers.
            reuse_worker = False
        primary_collect_label = _stt_primary_collect_label(label)
        primary_cache_enabled = _stt_primary_collect_cache_enabled(effective_settings)
        primary_cache_allowed = primary_collect_label and primary_cache_enabled and not callable(preview_callback)
        primary_cache_path: Path | None = None
        primary_cache_key = ""
        primary_cache_hit = False
        primary_cache_write = False
        primary_provider_called = primary_collect_label
        if primary_cache_allowed:
            primary_cache_path = _stt_primary_collect_cache_path(effective_settings)
            primary_cache_key = _stt_primary_collect_cache_key(
                chunk_dir=chunk_dir,
                settings=effective_settings,
                model=model,
                language=getattr(self, "language", ""),
                label=label,
                target_end_sec=target_end_sec,
                is_single=is_single,
                settings_overrides=settings_overrides,
            )
            cached_payload = _cached_stt_primary_collect_segments(primary_cache_path, primary_cache_key)
            if cached_payload is not None:
                cached_segments, cached_diagnostics = cached_payload
                primary_cache_hit = True
                primary_provider_called = False
                diagnostics = {
                    key: value
                    for key, value in dict(cached_diagnostics or {}).items()
                    if isinstance(value, (str, int, float, bool)) or value is None
                }
                diagnostics.update({
                    "label": str(label or ""),
                    "status": "cache_hit",
                    "resolved_model": str(diagnostics.get("resolved_model") or model or ""),
                    "target_end_sec": float(target_end_sec) if target_end_sec is not None else None,
                    "collect_elapsed_sec": 0.0,
                    "worker_reuse_enabled": bool(reuse_worker),
                    "worker_cache_hit": False,
                    "worker_cache_busy": False,
                    "worker_transient": False,
                    "resource_pressure_stage": str(pressure_stage or ""),
                    "resource_allows_worker_reuse": bool(resource_policy.allow_stt_collect_worker_reuse),
                    "collect_cache_enabled": True,
                    "collect_cache_hit": True,
                    "collect_cache_write": False,
                    "collect_provider_called": False,
                    "collect_cache_path": str(primary_cache_path),
                    "emitted_segment_count": len(cached_segments),
                })
                self._last_collect_transcribe_diagnostics = {
                    key: value
                    for key, value in diagnostics.items()
                    if isinstance(value, (str, int, float, bool)) or value is None
                }
                if hasattr(self, "_record_stt_stage_wall_clock_span"):
                    self._record_stt_stage_wall_clock_span(
                        "stt_primary_collect_transcribe",
                        time.perf_counter(),
                        source_collect_label=label,
                        **{
                            key: value
                            for key, value in diagnostics.items()
                            if isinstance(value, (str, int, float, bool)) or value is None
                        },
                    )
                return [dict(seg) for seg in cached_segments]
        cache_key = f"{self.language}|{str(model or '').strip()}"
        worker = None
        transient_worker = True
        worker_id = 0
        worker_cache_hit = False
        worker_cache_busy = False

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
                    worker_cache_hit = True
                    if worker not in children:
                        children.append(worker)
                else:
                    worker_cache_busy = cached is not None
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
        child_span_start = 0
        if hasattr(worker, "_stt_stage_wall_clock_spans_snapshot"):
            try:
                child_span_start = len(worker._stt_stage_wall_clock_spans_snapshot())
            except Exception:
                child_span_start = 0
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
                if primary_cache_allowed and primary_cache_path is not None and primary_cache_key and result:
                    primary_cache_write = _store_stt_primary_collect_segments(
                        primary_cache_path,
                        primary_cache_key,
                        result,
                        max_entries=_stt_primary_collect_cache_max_entries(effective_settings),
                    )
            except RuntimeError as exc:
                get_logger().log(f"  ⚠️ [{label}] 보조 STT 재검사 실패, 기존 STT 결과를 유지합니다: {exc}")
                result = []
        finally:
            if hasattr(worker, "_stt_stage_wall_clock_spans_snapshot"):
                try:
                    child_spans = worker._stt_stage_wall_clock_spans_snapshot()[child_span_start:]
                except Exception:
                    child_spans = []
                collect_spans = [
                    {
                        **dict(span),
                        "source_collect_label": label,
                        **(
                            {
                                "collect_cache_enabled": bool(primary_cache_enabled),
                                "collect_cache_hit": bool(primary_cache_hit),
                                "collect_cache_write": bool(primary_cache_write),
                                "collect_provider_called": bool(primary_provider_called),
                                "collect_cache_path": str(primary_cache_path or ""),
                            }
                            if primary_collect_label
                            else {}
                        ),
                    }
                    for span in child_spans
                    if str((span or {}).get("stage") or "").startswith("stt_collect_")
                    or str((span or {}).get("stage") or "").endswith("_collect_transcribe")
                ]
                if collect_spans:
                    if hasattr(self, "_merge_stt_stage_wall_clock_spans"):
                        self._merge_stt_stage_wall_clock_spans(collect_spans)
                    else:
                        spans = getattr(self, "_stt_stage_wall_clock_spans", None)
                        if not isinstance(spans, list):
                            spans = []
                            self._stt_stage_wall_clock_spans = spans
                        spans.extend(collect_spans)
            run_diagnostics = getattr(worker, "_last_transcribe_run_diagnostics", None)
            if isinstance(run_diagnostics, dict):
                collect_diagnostics = {
                    key: value
                    for key, value in run_diagnostics.items()
                    if isinstance(value, (str, int, float, bool))
                }
                collect_diagnostics.update(
                    {
                        "worker_reuse_enabled": bool(reuse_worker),
                        "worker_cache_hit": bool(worker_cache_hit),
                        "worker_cache_busy": bool(worker_cache_busy),
                        "worker_transient": bool(transient_worker),
                        "resource_pressure_stage": str(pressure_stage or ""),
                        "resource_allows_worker_reuse": bool(resource_policy.allow_stt_collect_worker_reuse),
                    }
                )
                if primary_collect_label:
                    if primary_cache_allowed and primary_cache_path is not None and primary_cache_key and result:
                        primary_cache_write = _store_stt_primary_collect_segments(
                            primary_cache_path,
                            primary_cache_key,
                            result,
                            max_entries=_stt_primary_collect_cache_max_entries(effective_settings),
                            diagnostics=collect_diagnostics,
                        ) or primary_cache_write
                    collect_diagnostics.update(
                        {
                            "collect_cache_enabled": bool(primary_cache_enabled),
                            "collect_cache_hit": bool(primary_cache_hit),
                            "collect_cache_write": bool(primary_cache_write),
                            "collect_provider_called": bool(primary_provider_called),
                            "collect_cache_path": str(primary_cache_path or ""),
                        }
                    )
                self._last_collect_transcribe_diagnostics = collect_diagnostics
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

    def _early_stt_preview_burst_sec(self, settings: dict | None, target_end_sec: float | None) -> float:
        burst_sec = self._setting_float(settings, "stt_early_preview_burst_sec", 30.0)
        burst_sec = max(5.0, min(60.0, float(burst_sec or 30.0)))
        if target_end_sec is not None:
            try:
                burst_sec = min(burst_sec, max(0.0, float(target_end_sec)))
            except Exception:
                pass
        return burst_sec

    def _run_early_stt_preview_burst(
        self,
        chunk_dir: str,
        items: list[dict],
        settings: dict,
        *,
        target_end_sec: float | None,
        is_single: bool,
        model: str | None,
        log_label: str,
        preview_callback,
        vad_strict: list[dict] | None = None,
    ) -> None:
        if not callable(preview_callback):
            return
        if not self._setting_bool(settings, "stt_early_preview_burst_enabled", True):
            return
        if _stt_memory_pressure_stage(settings) == "critical":
            get_logger().log("  ⚡ [STT Preview] 메모리 critical 상태라 early preview burst를 건너뜁니다.")
            return

        burst_sec = self._early_stt_preview_burst_sec(settings, target_end_sec)
        if burst_sec <= 0.01:
            return
        root = os.path.abspath(str(chunk_dir or ""))
        key = (root, str(model or "").strip(), str(log_label or "STT").strip(), round(burst_sec, 3))
        seen = getattr(self, "_stt_early_preview_burst_keys", None)
        if not isinstance(seen, set):
            seen = set()
        if key in seen:
            return
        seen.add(key)
        self._stt_early_preview_burst_keys = seen

        window_range = {"start": 0.0, "end": burst_sec}
        window_items: list[dict] = []
        for item in list(items or []):
            item_start = float((item or {}).get("ov_start_offset", 0.0) or 0.0)
            item_duration = float((item or {}).get("duration", 0.0) or 0.0)
            if item_duration <= 0.001:
                source = str((item or {}).get("input_path") or "")
                item_duration = self._wav_duration(source) if source else 0.0
            item_end = item_start + max(0.001, float(item_duration or 0.001))
            if item_start < burst_sec and item_end > 0.0:
                window_items.append(dict(item))
        if not window_items:
            get_logger().log(f"  ⚡ [STT Preview] 0~{burst_sec:.0f}초에 STT preview용 음성 청크가 없어 건너뜁니다.")
            return

        burst_dir = ""
        emitted_count = 0

        def _preview(chunk_segs, _worker_label=None):
            nonlocal emitted_count
            preview = []
            for seg in list(chunk_segs or []):
                if not isinstance(seg, dict):
                    continue
                try:
                    if float(seg.get("start", 0.0) or 0.0) >= burst_sec + 0.05:
                        continue
                except Exception:
                    pass
                row = dict(seg)
                meta = dict(row.get("asr_metadata") or {})
                meta["early_preview_burst"] = {
                    "enabled": True,
                    "burst_sec": round(burst_sec, 3),
                    "final_quality_path": "unchanged_rolling_window",
                }
                row["asr_metadata"] = meta
                row.setdefault("stt_preview_source", "STT1_EARLY_PREVIEW")
                row.setdefault("stt_ensemble_source", "STT1_EARLY_PREVIEW")
                preview.append(row)
            if not preview:
                return
            emitted_count += len(preview)
            try:
                preview_callback(preview, "STT1-EARLY")
            except Exception:
                pass

        overrides = dict(settings or {})
        overrides.update({
            "stt_ensemble_enabled": False,
            "stt_ensemble_selective_enabled": False,
            "stt_selective_secondary_recheck_enabled": False,
            "stt_word_timestamps_default_enabled": False,
            "stt_word_timestamps_mode": "off",
            "stt_word_timestamps_precision_enabled": False,
            "stt_word_timestamp_precision_pass": False,
        })
        try:
            get_logger().log(f"  ⚡ [STT Preview] 0~{burst_sec:.0f}초 early STT preview burst 시작")
            burst_dir = self._build_window_chunk_dir(
                chunk_dir,
                window_items,
                window_index=0,
                total_windows=1,
                window_range=window_range,
                vad_segments=self._clip_vad_segments_to_window(vad_strict or [], 0.0, burst_sec),
            )
            self._collect_transcribe_result(
                burst_dir,
                str(model or "").strip() or str((settings or {}).get("selected_whisper_model") or self.whisper_model),
                target_end_sec=burst_sec,
                is_single=True,
                label="STT1-EARLY",
                preview_callback=_preview,
                settings_overrides=overrides,
            )
            get_logger().log(f"  ⚡ [STT Preview] early STT preview 표시 완료: {emitted_count}개")
        except Exception as exc:
            get_logger().log(f"  ⚠️ [STT Preview] early preview burst 실패, 본 STT는 계속 진행합니다: {exc}")
        finally:
            if burst_dir:
                shutil.rmtree(burst_dir, ignore_errors=True)

    def _stt_window_zero_result_fallback_enabled(self, settings: dict | None) -> bool:
        return self._setting_bool(settings, "stt_window_zero_result_fallback_enabled", True)

    def _stt_window_head_gap_fallback_enabled(self, settings: dict | None) -> bool:
        return self._setting_bool(settings, "stt_window_head_gap_fallback_enabled", True)

    @staticmethod
    def _min_segment_start(segments: list[dict] | None) -> float | None:
        starts: list[float] = []
        for seg in list(segments or []):
            try:
                starts.append(float(seg.get("start", 0.0) or 0.0))
            except (TypeError, ValueError, AttributeError):
                continue
        return min(starts) if starts else None

    @staticmethod
    def _min_item_start(items: list[dict] | None) -> float | None:
        starts: list[float] = []
        for item in list(items or []):
            try:
                starts.append(float(item.get("ov_start_offset", 0.0) or 0.0))
            except (TypeError, ValueError, AttributeError):
                continue
        return min(starts) if starts else None

    def _stt_window_head_gap_fallback_needed(
        self,
        items: list[dict],
        settings: dict,
        first_window_segments: list[dict] | None,
        *,
        vad_strict: list[dict] | None = None,
    ) -> tuple[bool, float | None, float]:
        if not self._stt_window_head_gap_fallback_enabled(settings):
            return False, self._min_segment_start(first_window_segments), 0.0
        source_start = self._min_item_start(items)
        if source_start is None or source_start > 5.0:
            return False, self._min_segment_start(first_window_segments), 0.0
        head_gap_sec = self._windowed_float(
            settings,
            "stt_window_head_gap_fallback_sec",
            45.0,
            5.0,
            180.0,
        )
        if not vad_strict and self._setting_bool(settings, "stt_window_head_gap_requires_vad", True):
            return False, self._min_segment_start(first_window_segments), head_gap_sec
        # If VAD exists and proves the head is silent, keep the faster window result.
        if vad_strict:
            has_head_voice = False
            cutoff = source_start + head_gap_sec
            for row in list(vad_strict or []):
                try:
                    vad_start = float(row.get("start", 0.0) or 0.0)
                    vad_end = float(row.get("end", vad_start) or vad_start)
                except (TypeError, ValueError, AttributeError):
                    continue
                if vad_end > source_start + 0.25 and vad_start <= cutoff:
                    has_head_voice = True
                    break
            if not has_head_voice:
                return False, self._min_segment_start(first_window_segments), head_gap_sec
        first_start = self._min_segment_start(first_window_segments)
        if first_start is None:
            return True, None, head_gap_sec
        return first_start > source_start + head_gap_sec, first_start, head_gap_sec






















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
        self._reset_stt_stage_wall_clock_spans()
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
            primary_started = time.perf_counter()
            primary_status = "ok"
            try:
                primary_segments = self._collect_transcribe_result(
                    chunk_dir,
                    primary_model,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    label="STT1",
                    preview_callback=self._ensemble_preview_callback("STT1", preview_callback),
                    settings_overrides=primary_overrides,
                )
            except Exception:
                primary_status = "failed"
                raise
            finally:
                primary_diagnostics = getattr(self, "_last_collect_transcribe_diagnostics", None)
                primary_metadata = {
                    "status": primary_status,
                    "label": "STT1",
                    "result_segments": len(primary_segments or []) if "primary_segments" in locals() else 0,
                }
                if isinstance(primary_diagnostics, dict):
                    for key in (
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
                    ):
                        if key in primary_diagnostics:
                            primary_metadata[key] = primary_diagnostics.get(key)
                self._record_stt_stage_wall_clock_span(
                    "stt_primary_transcribe",
                    primary_started,
                    **primary_metadata,
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
                fallback_started = time.perf_counter()
                fallback_status = "ok"
                try:
                    primary_segments = self._collect_transcribe_result(
                        chunk_dir,
                        secondary_model,
                        target_end_sec=target_end_sec,
                        is_single=is_single,
                        label="STT2",
                        preview_callback=self._ensemble_preview_callback("STT2", preview_callback),
                        settings_overrides=fallback_overrides,
                    )
                except Exception:
                    fallback_status = "failed"
                    raise
                finally:
                    self._record_stt_stage_wall_clock_span(
                        "stt2_full_fallback_transcribe",
                        fallback_started,
                        status=fallback_status,
                        label="STT2",
                        result_segments=len(primary_segments or []),
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
                    target_end_sec=target_end_sec,
                    preview_callback=preview_callback,
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
                vad_align_started = time.perf_counter()
                vad_input_count = len(primary_segments or [])
                primary_segments, adjusted_count = adjust_segments_to_vad_boundaries(
                    primary_segments,
                    vad_strict,
                    max_shift_sec=float(settings.get("vad_post_stt_max_shift_sec", 0.7) or 0.7),
                    edge_pad_sec=float(settings.get("vad_post_stt_edge_pad_sec", 0.04) or 0.04),
                )
                self._record_stt_stage_wall_clock_span(
                    "vad_stt_consensus",
                    vad_align_started,
                    status="applied",
                    input_segments=vad_input_count,
                    adjusted_count=int(adjusted_count or 0),
                    result_segments=len(primary_segments or []),
                )
                get_logger().log(f"  🎯 [VAD 후처리] 선택 앙상블 자막 위치 {adjusted_count}개 보정")

            if callable(preview_callback):
                try:
                    preview_callback([dict(seg) for seg in primary_segments], "STT-SELECTIVE")
                except Exception:
                    pass
            get_logger().log(
                "  ✅ [STT 선택 앙상블] 최종 후보 완료 "
                f"({len(primary_segments)}개, STT2는 저신뢰/누락/경계 후보에 사용)"
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
