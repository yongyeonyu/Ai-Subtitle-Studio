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


def _current_stt_memory_pressure_stage(settings: dict | None) -> str:
    owner = sys.modules.get("core.audio.media_processor_transcribe")
    stage = getattr(owner, "_stt_memory_pressure_stage", _stt_memory_pressure_stage)
    return str(stage(settings) or "normal")


class VideoProcessorTranscribePolicyMixin:
    def _whisperkit_concurrent_worker_count(
        self,
        settings: dict | None,
        *,
        total_chunks: int,
        word_timestamps: bool,
    ) -> int:
        chunks = max(1, int(total_chunks or 1))
        self._whisperkit_native_allocation_plan = None
        if chunks <= 1:
            return 1
        pressure_stage = _current_stt_memory_pressure_stage(settings)
        if pressure_stage == "critical":
            return 1
        data = dict(settings or {})
        normal_pressure = pressure_stage not in {"warning", "critical"}
        recheck_pass = (
            bool(data.get("stt_rescue_whisper_mode", False))
            and not bool(data.get("stt_word_timestamp_precision_pass", False))
            and not word_timestamps
        )
        key = (
            "stt_whisperkit_word_timestamp_concurrent_workers"
            if word_timestamps
            else "stt_whisperkit_concurrent_workers"
        )
        try:
            if recheck_pass and "stt_whisperkit_recheck_concurrent_workers" in data:
                configured = int(float(data.get("stt_whisperkit_recheck_concurrent_workers", 0) or 0))
            else:
                configured = int(float(data.get(key, 0) or 0))
        except (TypeError, ValueError):
            configured = 0
        if recheck_pass and "stt_whisperkit_recheck_concurrent_workers" not in data:
            configured = 0
        if configured <= 0:
            if recheck_pass:
                configured = 4 if pressure_stage == "warning" else 8
            elif pressure_stage == "warning":
                configured = 2 if word_timestamps else 3
            else:
                configured = 4 if word_timestamps else 6
        try:
            default_max = 10 if recheck_pass and normal_pressure else (6 if recheck_pass else (8 if normal_pressure else 4))
            max_key = "stt_whisperkit_recheck_concurrent_max_workers" if recheck_pass else "stt_whisperkit_concurrent_max_workers"
            max_workers = int(float(data.get(max_key, data.get("stt_whisperkit_concurrent_max_workers", default_max)) or default_max))
        except (TypeError, ValueError):
            max_workers = 10 if recheck_pass and normal_pressure else (6 if recheck_pass else (8 if normal_pressure else 4))
        if word_timestamps and normal_pressure and self._setting_bool(data, "stt_whisperkit_precision_aggressive_gpu_enabled", True):
            try:
                saturation_workers = int(float(data.get("stt_whisperkit_gpu_saturation_max_workers", 10) or 10))
            except (TypeError, ValueError):
                saturation_workers = 10
            saturation_workers = max(1, min(chunks, saturation_workers))
            configured = max(configured, saturation_workers)
            max_workers = max(max_workers, saturation_workers)
        allocation_workers = 0
        if self._setting_bool(data, "stt_whisperkit_native_allocator_can_raise_workers", True):
            try:
                from core.native_resource_allocator import native_task_allocation

                task = "stt_precision" if word_timestamps else ("stt2" if recheck_pass else "stt1")
                allocator_maximum = max(
                    1,
                    min(
                        chunks,
                        max(
                            max_workers,
                            int(data.get("stt_whisperkit_gpu_saturation_max_workers", 8) or 8),
                        ),
                    ),
                )
                allocator_requested = configured
                if word_timestamps or recheck_pass:
                    # 변경 금지: native allocator가 STT2 재검사/단어 정밀 STT의
                    # ANE/GPU lane을 올릴 수 있어야 한다. 예전 구현은
                    # requested_workers=configured로 묶여 있어서 full-core 설정의
                    # 10-lane 상한을 전달해도 Swift allocator가 worker를 높일
                    # 수 없었고, STT2가 적극적으로 쓰이지 않는 것처럼 보였다.
                    allocator_requested = max(configured, allocator_maximum)
                plan = native_task_allocation(
                    task,
                    settings=data,
                    workload=chunks,
                    requested_workers=allocator_requested,
                    minimum=1,
                    maximum=allocator_maximum,
                    active_labels=[task, "stt"],
                )
                if isinstance(plan, dict):
                    self._whisperkit_native_allocation_plan = {
                        "chunks": chunks,
                        "word_timestamps": bool(word_timestamps),
                        "task": task,
                        "plan": dict(plan),
                    }
                allocation_workers = int((plan or {}).get("workers", 0) or 0)
            except Exception:
                allocation_workers = 0
        if allocation_workers > 0:
            configured = max(configured, allocation_workers)
            max_workers = max(max_workers, allocation_workers)
        return max(1, min(chunks, configured, max(1, max_workers)))
    @staticmethod
    def _whisperkit_compute_profile_from_native_units(
        compute_units: object,
        *,
        fallback: str = "ane_gpu",
    ) -> str:
        try:
            from core.native_swift_transcribe_plan import compute_profile_from_native_units_via_swift

            native_profile = compute_profile_from_native_units_via_swift(compute_units, fallback=fallback)
            if native_profile:
                return native_profile
        except Exception:
            pass

        value = str(compute_units or "").strip()
        if not value:
            return fallback
        key = value.replace("-", "_").replace(" ", "").lower()
        if key in {"all", "full", "allcomputeunits"}:
            return "all"
        if key in {"cpuandgpu", "cpu_gpu", "gpucpu", "gpu", "cpuandgputhenane"}:
            return "gpu"
        if key in {
            "cpuandneuralengine",
            "cpu_neural_engine",
            "cpu_ane",
            "ane",
            "neuralengine",
            "anegpu",
            "ane_gpu",
        }:
            return "ane_gpu"
        if key in {"cpuonly", "cpu"}:
            return "cpu"
        return fallback
    def _whisperkit_compute_profile(
        self,
        settings: dict | None,
        *,
        word_timestamps: bool,
        fallback: str = "ane_gpu",
    ) -> str:
        data = dict(settings or {})
        configured = str(data.get("stt_whisperkit_compute_profile") or "auto").strip()
        if not self._setting_bool(data, "stt_whisperkit_native_compute_profile_enabled", True):
            return configured or fallback
        if configured and configured.lower() not in {"auto", "native", "allocator", "resource_adaptive"}:
            return configured
        record = getattr(self, "_whisperkit_native_allocation_plan", None)
        if not isinstance(record, dict):
            return fallback
        if bool(record.get("word_timestamps", False)) != bool(word_timestamps):
            return fallback
        plan = record.get("plan")
        if not isinstance(plan, dict):
            return fallback
        return self._whisperkit_compute_profile_from_native_units(
            plan.get("compute_units"),
            fallback=fallback,
        )
    def _duration_first_stt_submission_enabled(
        self,
        settings: dict | None,
        *,
        word_timestamps: bool,
    ) -> bool:
        data = dict(settings or {})
        rescue_pass = bool(data.get("stt_rescue_whisper_mode", False))
        precision_pass = bool(data.get("stt_word_timestamp_precision_pass", False))
        enabled_setting = self._setting_bool(data, "stt_duration_first_submission_enabled", True)
        try:
            from core.native_swift_transcribe_plan import duration_first_submission_enabled_via_swift

            native = duration_first_submission_enabled_via_swift(
                rescue_pass=rescue_pass,
                precision_pass=precision_pass,
                word_timestamps=word_timestamps,
                enabled_setting=enabled_setting,
            )
            if native is not None:
                return native
        except Exception:
            pass

        if not (rescue_pass or precision_pass or word_timestamps):
            return False
        return enabled_setting
    def _duration_first_submission_order(self, items: list[dict], settings: dict | None) -> list[int]:
        if len(items or []) <= 1:
            return list(range(len(items or [])))
        try:
            from core.native_swift_transcribe_plan import duration_first_order_via_swift

            swift_order = duration_first_order_via_swift(items)
            if swift_order is not None:
                return swift_order
        except Exception:
            pass

        starts = [float(item.get("ov_start_offset", idx) or idx) for idx, item in enumerate(items)]
        durations = [max(0.001, float(item.get("duration", 0.001) or 0.001)) for item in items]
        native_order = None
        try:
            from core.native_stt_recheck import duration_desc_order_indices

            native_order = duration_desc_order_indices(starts=starts, durations=durations)
        except Exception:
            native_order = None
        if native_order is None:
            native_order = sorted(range(len(items)), key=lambda idx: (-durations[idx], starts[idx]))
        seen: set[int] = set()
        order: list[int] = []
        for idx in native_order:
            if idx in seen or idx < 0 or idx >= len(items):
                continue
            seen.add(idx)
            order.append(idx)
        for idx in range(len(items)):
            if idx not in seen:
                order.append(idx)
        # Avoid remapping overhead on uniform chunks; chronological order is best for live preview.
        if order == list(range(len(items))) or (max(durations) - min(durations)) < 0.05:
            return list(range(len(items)))
        if self._setting_bool(dict(settings or {}), "stt_duration_first_submission_log_enabled", True):
            try:
                get_logger().log(
                    "  ⚡ [STT Native Scheduler] duration-first chunk submission: "
                    f"{order[:8]}{'...' if len(order) > 8 else ''}"
                )
            except Exception:
                pass
        return order
    def _stt_worker_silence_timeout_sec(
        self,
        settings: dict | None,
        *,
        log_label: str,
        word_timestamps: bool,
    ) -> float:
        try:
            from core.native_swift_transcribe_plan import stt_worker_silence_timeout_via_swift

            native = stt_worker_silence_timeout_via_swift(
                settings,
                log_label=log_label,
                word_timestamps=word_timestamps,
            )
            if native is not None:
                return native
        except Exception:
            pass

        data = dict(settings or {})
        precision_pass = bool(data.get("stt_word_timestamp_precision_pass", False))
        label = str(log_label or "").strip()
        if precision_pass or "단어정밀" in label:
            key = "stt_word_timestamp_worker_response_timeout_sec"
            default = 45.0
        elif word_timestamps:
            key = "stt_worker_word_timestamp_response_timeout_sec"
            default = 90.0
        else:
            key = "stt_worker_response_timeout_sec"
            default = 150.0
        try:
            value = float(data.get(key, default) or 0.0)
        except (TypeError, ValueError):
            value = default
        if value <= 0.0:
            return 0.0
        return max(0.05, min(600.0, value))
    def _stt_precision_straggler_timeout_sec(self, settings: dict | None) -> float:
        try:
            from core.native_swift_transcribe_plan import stt_straggler_config_via_swift

            native = stt_straggler_config_via_swift(settings, mode="precision")
            if native is not None:
                return float(native["timeout"])
        except Exception:
            pass

        data = dict(settings or {})
        try:
            value = float(data.get("stt_word_timestamp_worker_straggler_timeout_sec", 12.0) or 0.0)
        except (TypeError, ValueError):
            value = 12.0
        if value <= 0.0:
            return 0.0
        return max(2.0, min(120.0, value))
    def _stt_precision_straggler_max_missing_chunks(self, settings: dict | None) -> int:
        try:
            from core.native_swift_transcribe_plan import stt_straggler_config_via_swift

            native = stt_straggler_config_via_swift(settings, mode="precision")
            if native is not None:
                return int(native["max_missing_chunks"])
        except Exception:
            pass

        data = dict(settings or {})
        try:
            value = int(float(data.get("stt_word_timestamp_worker_straggler_max_missing_chunks", 1) or 1))
        except (TypeError, ValueError):
            value = 1
        return max(1, min(8, value))
    def _stt_precision_straggler_min_received_ratio(self, settings: dict | None) -> float:
        try:
            from core.native_swift_transcribe_plan import stt_straggler_config_via_swift

            native = stt_straggler_config_via_swift(settings, mode="precision")
            if native is not None:
                return float(native["min_received_ratio"])
        except Exception:
            pass

        data = dict(settings or {})
        try:
            value = float(data.get("stt_word_timestamp_worker_straggler_min_received_ratio", 0.90) or 0.0)
        except (TypeError, ValueError):
            value = 0.90
        if value <= 0.0:
            return 0.0
        return max(0.50, min(1.0, value))
    def _stt_recheck_straggler_timeout_sec(self, settings: dict | None) -> float:
        try:
            from core.native_swift_transcribe_plan import stt_straggler_config_via_swift

            native = stt_straggler_config_via_swift(settings, mode="recheck")
            if native is not None:
                return float(native["timeout"])
        except Exception:
            pass

        data = dict(settings or {})
        try:
            value = float(data.get("stt_recheck_worker_straggler_timeout_sec", 18.0) or 0.0)
        except (TypeError, ValueError):
            value = 18.0
        if value <= 0.0:
            return 0.0
        return max(2.0, min(120.0, value))
    def _stt_recheck_straggler_max_missing_chunks(self, settings: dict | None) -> int:
        try:
            from core.native_swift_transcribe_plan import stt_straggler_config_via_swift

            native = stt_straggler_config_via_swift(settings, mode="recheck")
            if native is not None:
                return int(native["max_missing_chunks"])
        except Exception:
            pass

        data = dict(settings or {})
        try:
            value = int(float(data.get("stt_recheck_worker_straggler_max_missing_chunks", 4) or 4))
        except (TypeError, ValueError):
            value = 4
        return max(1, min(4, value))
    def _stt_recheck_straggler_min_received_ratio(self, settings: dict | None) -> float:
        try:
            from core.native_swift_transcribe_plan import stt_straggler_config_via_swift

            native = stt_straggler_config_via_swift(settings, mode="recheck")
            if native is not None:
                return float(native["min_received_ratio"])
        except Exception:
            pass

        data = dict(settings or {})
        try:
            value = float(data.get("stt_recheck_worker_straggler_min_received_ratio", 0.60) or 0.0)
        except (TypeError, ValueError):
            value = 0.60
        if value <= 0.0:
            return 0.0
        return max(0.25, min(1.0, value))
    def _read_worker_stdout_line(
        self,
        proc,
        *,
        log_label: str,
        received: int,
        total: int,
        wait_started_at: float,
        last_wait_log_at: float,
        heartbeat_sec: float = 18.0,
        max_silence_sec: float | None = None,
    ):
        stream = getattr(proc, "stdout", None)
        if stream is None:
            return "", last_wait_log_at
        try:
            fileno = stream.fileno()
        except Exception:
            return stream.readline(), last_wait_log_at

        heartbeat = max(5.0, float(heartbeat_sec or 18.0))
        try:
            timeout_sec = max(0.0, float(max_silence_sec or 0.0))
        except (TypeError, ValueError):
            timeout_sec = 0.0
        while True:
            now = time.monotonic()
            if timeout_sec > 0.0 and now - wait_started_at >= timeout_sec:
                elapsed = max(0.0, now - wait_started_at)
                get_logger().log(
                    f"  ⚠️ [{log_label}] STT worker 응답 타임아웃: "
                    f"{received}/{total} chunks · {elapsed:.0f}s"
                )
                raise SttWorkerTimeout(
                    f"stt_worker_timeout[{log_label}]: {received}/{total} chunks after {elapsed:.1f}s"
                )
            select_timeout = 1.0
            if timeout_sec > 0.0:
                select_timeout = max(0.05, min(1.0, timeout_sec - max(0.0, now - wait_started_at)))
            try:
                ready, _, _ = select.select([fileno], [], [], select_timeout)
            except Exception:
                return stream.readline(), last_wait_log_at
            if ready:
                return stream.readline(), last_wait_log_at
            now = time.monotonic()
            if now - last_wait_log_at >= heartbeat:
                elapsed = max(0.0, now - wait_started_at)
                get_logger().log(
                    f"  ⏳ [{log_label}] STT worker 응답 대기 중... "
                    f"{received}/{total} chunks · {elapsed:.0f}s"
                )
                last_wait_log_at = now
            try:
                if proc.poll() is not None:
                    return stream.readline() or "", last_wait_log_at
            except Exception:
                pass
