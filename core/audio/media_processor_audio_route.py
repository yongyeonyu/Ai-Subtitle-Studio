# Version: 03.14.33
# Phase: PHASE2
"""Adaptive audio route helpers for VideoProcessor.

Behavior-preserving split from media_processor_audio.py.
"""

from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from core.audio.audio_presets import auto_audio_settings_only
from core.audio.audio_runtime_services import plan_audio_route_workers
from core.platform_compat import ffmpeg_binary
from core.runtime.logger import get_logger


def _runtime_get_logger():
    import sys

    owner = sys.modules.get("core.audio.media_processor")
    return getattr(owner, "get_logger", get_logger)()


def _audio_route_settings_bool(settings: dict | None, key: str, default: bool = False) -> bool:
    value = dict(settings or {}).get(key, default)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    if text in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", "disable", "끄기", "끔"}:
        return False
    return bool(default)


class VideoProcessorAudioRouteMixin:
    @staticmethod
    def _adaptive_audio_routing_enabled(settings: dict | None) -> bool:
        data = dict(settings or {})
        if _audio_route_settings_bool(data, "audio_chunk_routing_benchmark_locked", False):
            return False
        if _audio_route_settings_bool(data, "audio_chunk_routing_disabled", False):
            return False
        return _audio_route_settings_bool(data, "audio_chunk_routing_enabled", True)

    def _audio_route_sample_span(self, start: float, end: float, settings: dict | None = None) -> tuple[float, float]:
        try:
            from core.native_swift_audio_filter import audio_route_sample_span_via_swift

            native = audio_route_sample_span_via_swift(start, end, settings)
            if native is not None:
                return native
        except Exception:
            pass

        start = max(0.0, float(start or 0.0))
        end = max(start, float(end or start))
        duration = max(0.0, end - start)
        if duration <= 0.0:
            return start, 0.0
        try:
            max_sample = float((settings or {}).get("audio_chunk_profile_sec", 30.0) or 30.0)
        except Exception:
            max_sample = 30.0
        sample_dur = min(duration, max(8.0, min(30.0, max_sample)))
        sample_start = start + max(0.0, (duration - sample_dur) / 2.0)
        return round(sample_start, 3), round(sample_dur, 3)

    def _extract_audio_route_sample(
        self,
        media_path: str,
        sample_path: str,
        *,
        start: float,
        duration: float,
        settings: dict,
    ) -> bool:
        if duration <= 0.0:
            return False
        cmd = [
            ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
            *self._ffmpeg_parallel_args(settings),
            "-ss", f"{max(0.0, float(start or 0.0)):.3f}",
            "-t", f"{max(0.05, float(duration or 0.05)):.3f}",
            "-i", media_path,
            *self._ffmpeg_audio_stream_args(),
            "-ac", "1", "-ar", "16000",
            "-sample_fmt", "s16",
            sample_path,
        ]
        return self._run_media_command_no_progress(cmd, label="오디오 라우팅 샘플 추출")

    def _fallback_chunk_audio_route(self, settings: dict, *, reason: str = "clip-level auto preset fallback") -> dict:
        from core.audio.audio_presets import auto_audio_settings_only

        tune = auto_audio_settings_only(settings)
        return {
            "audio_strategy": "clip_fallback",
            "audio_strategy_label": "클립 기준 유지",
            "audio_tune_reason": reason,
            "confidence": 0.5,
            "settings": tune,
            "audio_profile": {},
            "features": {},
            "candidate_scores": [],
        }

    @staticmethod
    def _audio_route_int_setting(settings: dict | None, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(float(dict(settings or {}).get(key, default)))
        except Exception:
            value = int(default)
        return max(int(minimum), min(int(maximum), value))

    def _audio_route_profile_sample_count(self, settings: dict | None = None) -> int:
        return self._audio_route_int_setting(settings, "audio_chunk_route_profile_samples", 3, 1, 5)

    def _audio_route_profile_window_sec(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_profile_window_sec", 8.0, 2.0, 20.0)

    def _audio_route_candidate_limit(self, settings: dict | None = None) -> int:
        return self._audio_route_int_setting(settings, "audio_chunk_route_candidate_limit", 3, 1, 4)

    def _audio_route_preview_enabled(self, settings: dict | None = None) -> bool:
        return self._settings_bool(settings, "audio_chunk_route_preview_enabled", True)

    def _audio_route_preview_min_confidence(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_preview_min_confidence", 0.76, 0.0, 1.0)

    def _audio_route_preview_gap_max(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_preview_gap_max", 0.08, 0.0, 0.5)

    def _audio_route_hysteresis_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_hysteresis_margin", 0.05, 0.0, 0.5)

    def _audio_route_profile_memory_enabled(self, settings: dict | None = None) -> bool:
        return self._settings_bool(settings, "audio_chunk_route_profile_memory_enabled", True)

    def _audio_route_profile_memory_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_profile_memory_margin", 0.04, 0.0, 0.5)

    def _audio_route_profile_memory_min_confidence(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_profile_memory_min_confidence", 0.64, 0.0, 1.0)

    def _audio_route_switch_confirmation_enabled(self, settings: dict | None = None) -> bool:
        return self._settings_bool(settings, "audio_chunk_route_switch_confirmation_enabled", True)

    def _audio_route_switch_confirmation_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_switch_confirmation_margin", 0.04, 0.0, 0.5)

    def _audio_route_switch_confirmation_strong_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_switch_confirmation_strong_margin", 0.11, 0.0, 0.5)

    def _audio_route_switch_confirmation_min_streak(self, settings: dict | None = None) -> int:
        return self._audio_route_int_setting(settings, "audio_chunk_route_switch_confirmation_min_streak", 2, 1, 4)

    def _audio_route_precision_threshold(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_precision_threshold", 0.74, 0.0, 1.0)

    def _audio_route_secondary_recheck_threshold(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_secondary_recheck_threshold", 0.68, 0.0, 1.0)

    def _audio_route_secondary_recheck_high_risk_max_confidence(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_secondary_recheck_high_risk_max_confidence", 0.74, 0.0, 1.0)

    def _audio_route_vad_preserve_base_min_confidence(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_vad_preserve_base_min_confidence", 0.78, 0.0, 1.0)

    def _audio_route_secondary_recheck_hint(self, confidence: float, risk_level: str, settings: dict | None = None) -> bool:
        confidence = max(0.0, min(1.0, float(confidence or 0.0)))
        risk = str(risk_level or "").strip().lower()
        if confidence <= self._audio_route_secondary_recheck_threshold(settings):
            return True
        # 변경 금지: high-noise 판정만으로 STT2 재검사를 켜면 X5처럼 STT1이
        # 정확한 구간도 넓은 재검사 범위에 묶여 타이밍/문장이 흔들린다.
        # high-risk는 confidence가 별도 캡 이하일 때만 STT2 rescue 힌트로 쓴다.
        return risk == "high" and confidence <= self._audio_route_secondary_recheck_high_risk_max_confidence(settings)

    def _audio_route_preserve_base_vad_for_confident_route(
        self,
        confidence: float,
        settings: dict | None = None,
    ) -> bool:
        data = dict(settings or {})
        base_vad = str(data.get("selected_vad") or "").strip().lower()
        if not base_vad or base_vad == "none":
            return False
        if not self._settings_bool(
            data,
            "audio_chunk_route_vad_enabled",
            self._settings_bool(data, "vad_post_stt_align_enabled", True),
        ):
            return False
        return float(confidence or 0.0) >= self._audio_route_vad_preserve_base_min_confidence(data)

    def _audio_route_with_base_vad_settings(self, tune: dict, settings: dict | None = None) -> dict:
        out = dict(tune or {})
        data = dict(settings or {})
        for key in self._AUDIO_ROUTE_VAD_SETTING_KEYS:
            if key in data:
                out[key] = deepcopy(data[key])
        return out

    def _audio_route_low_confidence_threshold(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_low_confidence_threshold", 0.58, 0.0, 1.0)

    def _audio_route_baseline_guard_enabled(self, settings: dict | None = None) -> bool:
        return self._settings_bool(settings, "audio_chunk_route_baseline_guard_enabled", True)

    def _audio_route_baseline_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_baseline_margin", 0.04, 0.0, 0.5)

    def _audio_route_baseline_non_none_extra_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_baseline_non_none_extra_margin", 0.03, 0.0, 0.5)

    def _audio_route_baseline_noisy_voice_extra_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_baseline_noisy_voice_extra_margin", 0.05, 0.0, 0.5)

    @staticmethod
    def _audio_route_is_specialist_strategy(strategy: str | None) -> bool:
        return str(strategy or "").strip().lower() in {"noisy_voice", "low_rumble", "fast_noise_gate"}

    @staticmethod
    def _audio_route_is_challenging_profile(profile: dict | None) -> bool:
        data = dict(profile or {})
        noise = str(data.get("noise_level") or "low").strip().lower()
        environment = str(data.get("environment") or "").strip().lower()
        clean_dialog = bool(data.get("clean_dialog"))
        roomy_dialog = bool(data.get("roomy_dialog"))
        driving_noise = bool(data.get("driving_noise"))
        volatile_scene = bool(data.get("volatile_scene"))
        mic_present = bool(data.get("mic_present", True))
        if driving_noise or roomy_dialog:
            return True
        if noise == "high":
            return True
        if noise == "medium" and not clean_dialog and (volatile_scene or not mic_present or environment == "outdoor"):
            return True
        return bool(volatile_scene and not clean_dialog)

    def _audio_route_split_enabled(self, settings: dict | None = None) -> bool:
        return self._settings_bool(settings, "audio_chunk_route_split_enabled", False)

    def _audio_route_max_span_sec(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_max_span_sec", 0.0, 0.0, 240.0)

    def _audio_route_split_confidence_threshold(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_split_confidence_threshold", 0.8, 0.0, 1.0)

    def _audio_route_split_candidate_gap_max(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_split_candidate_gap_max", 0.06, 0.0, 0.5)

    def _audio_route_split_preview_divergence_min(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_split_preview_divergence_min", 0.08, 0.0, 0.5)

    @staticmethod
    def _audio_route_score_gap(rows: list[dict] | None) -> float:
        scores = []
        for row in list(rows or []):
            try:
                scores.append(float(row.get("score", 0.0) or 0.0))
            except Exception:
                continue
        if not scores:
            return 0.0
        scores.sort(reverse=True)
        if len(scores) == 1:
            return max(0.0, scores[0])
        return max(0.0, scores[0] - scores[1])

    def _audio_route_preview_divergence(self, route: dict) -> float:
        try:
            from core.native_swift_audio_filter import audio_route_preview_divergence_via_swift

            native = audio_route_preview_divergence_via_swift(route)
            if native is not None:
                return native
        except Exception:
            pass

        feature_conf = None
        self_score = None
        try:
            feature_conf = float(route.get("feature_confidence", 0.0) or 0.0)
        except Exception:
            feature_conf = None
        try:
            self_score = float(route.get("self_score", 0.0) or 0.0)
        except Exception:
            self_score = None
        if feature_conf is not None and self_score is not None:
            return abs(self_score - feature_conf)
        preview_gap = self._audio_route_score_gap(route.get("preview_scores"))
        feature_gap = self._audio_route_score_gap(route.get("candidate_scores"))
        return abs(preview_gap - feature_gap)

    def _maybe_expand_grouped_chunks_for_audio_route(self, grouped: list[dict], settings: dict | None = None) -> list[dict]:
        items = [dict(item) for item in list(grouped or []) if isinstance(item, dict)]
        if not items or not self._audio_route_split_enabled(settings):
            return items
        max_span = self._audio_route_max_span_sec(settings)
        if max_span <= 0.0:
            return items

        overlap_sec = max(0.0, min(self._chunk_overlap_sec(settings), max_span / 2.0))
        expanded: list[dict] = []
        changed = False
        for item in items:
            start = max(0.0, float(item.get("start", 0.0) or 0.0))
            end = max(start, float(item.get("end", start) or start))
            if end - start <= max_span + 0.001:
                expanded.append({"start": round(start, 3), "end": round(end, 3)})
                continue
            sub_ranges = self._split_range_with_overlap(start, end, max_span, overlap_sec)
            if len(sub_ranges) > 1:
                changed = True
                expanded.extend(sub_ranges)
            else:
                expanded.append({"start": round(start, 3), "end": round(end, 3)})

        if changed:
            try:
                _runtime_get_logger().log(
                    f"  ✂️ [오디오 라우팅] adaptive route 청크 {len(items)}개 → {len(expanded)}개 세분화 "
                    f"(max {max_span:.1f}s, overlap {overlap_sec:.1f}s)"
                )
            except Exception:
                pass
        return expanded

    def _should_split_audio_route_segment(self, seg: dict, route: dict, settings: dict | None = None) -> bool:
        if not self._audio_route_split_enabled(settings):
            return False
        start = max(0.0, float(seg.get("start", 0.0) or 0.0))
        end = max(start, float(seg.get("end", start) or start))
        duration = end - start
        max_span = self._audio_route_max_span_sec(settings)
        if max_span <= 0.0 or duration <= max_span + 0.001:
            return False

        profile = dict(route.get("audio_profile") or {})
        strategy = str(route.get("audio_strategy") or "").strip().lower()
        score = self._route_effective_score(route)
        threshold = self._audio_route_split_confidence_threshold(settings)
        challenging = self._audio_route_is_challenging_profile(profile)
        specialist = self._audio_route_is_specialist_strategy(strategy)
        volatile = bool(profile.get("volatile_scene"))
        noise = str(profile.get("noise_level") or "low").strip().lower()
        fallback_like = strategy in {"benchmark_locked_baseline", "clip_fallback"}
        candidate_gap = self._audio_route_score_gap(route.get("candidate_scores"))
        preview_gap = self._audio_route_score_gap(route.get("preview_scores"))
        gap_limit = self._audio_route_split_candidate_gap_max(settings)
        preview_divergence = self._audio_route_preview_divergence(route)
        preview_switch = bool(route.get("preview_route_switched"))
        baseline_guard = bool(route.get("baseline_guard_applied"))
        low_confidence = score < threshold
        preview_divergence_min = self._audio_route_split_preview_divergence_min(settings)
        try:
            from core.native_swift_audio_filter import audio_route_split_decision_via_swift

            native = audio_route_split_decision_via_swift(
                fallback_like=fallback_like,
                challenging=challenging,
                low_confidence=low_confidence,
                baseline_guard=baseline_guard,
                preview_switch=preview_switch,
                specialist=specialist,
                volatile=volatile,
                noise=noise,
                candidate_gap=candidate_gap,
                preview_gap=preview_gap,
                gap_limit=gap_limit,
                preview_divergence=preview_divergence,
                preview_divergence_min=preview_divergence_min,
            )
            if native is not None:
                return native
        except Exception:
            pass

        # Split only when the long chunk is both difficult and route selection
        # looks ambiguous enough that a finer-grained probe may legitimately win.
        if fallback_like and challenging and (low_confidence or candidate_gap <= gap_limit + 0.03):
            return True
        if baseline_guard and (
            preview_switch
            or preview_divergence >= preview_divergence_min
            or candidate_gap <= gap_limit + 0.02
        ):
            return True
        if preview_switch and preview_divergence >= preview_divergence_min:
            return True
        if challenging and volatile and low_confidence and (
            candidate_gap <= gap_limit or preview_gap <= gap_limit
        ):
            return True
        if specialist and volatile and low_confidence and preview_divergence >= max(0.04, gap_limit):
            return True
        if noise == "high" and volatile and low_confidence and candidate_gap <= gap_limit:
            return True
        return False

    def _selective_expand_grouped_chunks_for_audio_route(
        self,
        grouped: list[dict],
        route_logs: dict[int, dict],
        settings: dict | None = None,
    ) -> list[dict]:
        items = [dict(item) for item in list(grouped or []) if isinstance(item, dict)]
        if not items or not route_logs or not self._audio_route_split_enabled(settings):
            return items

        max_span = self._audio_route_max_span_sec(settings)
        if max_span <= 0.0:
            return items

        overlap_sec = max(0.0, min(self._chunk_overlap_sec(settings), max_span / 2.0))
        expanded: list[dict] = []
        changed = False
        split_count = 0
        for idx, item in enumerate(items):
            route = dict(route_logs.get(idx) or {})
            start = max(0.0, float(item.get("start", 0.0) or 0.0))
            end = max(start, float(item.get("end", start) or start))
            if not self._should_split_audio_route_segment(item, route, settings):
                expanded.append({"start": round(start, 3), "end": round(end, 3)})
                continue
            sub_ranges = self._split_range_with_overlap(start, end, max_span, overlap_sec)
            if len(sub_ranges) > 1:
                changed = True
                split_count += 1
                expanded.extend(sub_ranges)
            else:
                expanded.append({"start": round(start, 3), "end": round(end, 3)})

        if changed:
            try:
                _runtime_get_logger().log(
                    f"  ✂️ [오디오 라우팅] 변화 큰 청크 {split_count}개만 {len(items)}→{len(expanded)} 세분화 "
                    f"(max {max_span:.1f}s, overlap {overlap_sec:.1f}s)"
                )
            except Exception:
                pass
        return expanded

    @staticmethod
    def _audio_route_settings_signature(settings: dict | None = None) -> tuple:
        data = dict(settings or {})

        def _norm(key: str, default: str = "") -> str:
            return str(data.get(key, default) or default).strip().lower()

        def _flt(key: str) -> float | None:
            try:
                return round(float(data.get(key)), 4)
            except Exception:
                return None

        return (
            _norm("selected_audio_ai", "none"),
            _norm("selected_vad", "none"),
            _audio_route_settings_bool(data, "use_basic_filter", True),
            _flt("ff_hp"),
            _flt("ff_lp"),
            _flt("ff_nf"),
            _flt("ff_dynaudnorm_m"),
            _flt("ff_dynaudnorm_p"),
            _flt("ff_treble_boost"),
            _flt("vad_threshold"),
            _flt("ten_vad_threshold"),
        )

    def _audio_route_candidate_row_for_settings(
        self,
        candidate_scores: list[dict],
        route_settings: dict,
        *,
        fallback_id: str,
        fallback_label: str,
        fallback_score: float,
    ) -> dict:
        from core.audio.preset_auto_classifier import candidate_settings_for_id

        target_signature = self._audio_route_settings_signature(route_settings)
        for row in list(candidate_scores or []):
            candidate_id = str(row.get("id") or "")
            candidate_signature = self._audio_route_settings_signature(candidate_settings_for_id(candidate_id))
            if candidate_signature == target_signature:
                matched = dict(row)
                matched["signature"] = target_signature
                return matched
        return {
            "id": fallback_id,
            "label": fallback_label,
            "score": round(float(fallback_score or 0.0), 4),
            "signature": target_signature,
        }

    def _audio_route_baseline_settings(self, settings: dict | None = None) -> dict:
        from core.audio.audio_presets import auto_audio_settings_only

        data = dict(settings or {})
        baseline = auto_audio_settings_only(data)
        for key in (
            "selected_vad",
            "vad_threshold",
            "ten_vad_threshold",
            "vad_min_speech",
            "vad_min_silence",
            "vad_speech_pad",
            "vad_window_size",
            "vad_post_stt_align_enabled",
        ):
            if key in data:
                baseline[key] = deepcopy(data[key])
        return baseline

    def _audio_route_tune_settings(self, candidate_settings: dict | None, runtime_settings: dict | None = None) -> dict:
        from core.audio.audio_presets import auto_audio_settings_only

        source = dict(candidate_settings or {})
        tune = auto_audio_settings_only(source)
        route_vad_enabled = self._settings_bool(
            runtime_settings,
            "audio_chunk_route_vad_enabled",
            self._settings_bool(runtime_settings, "vad_post_stt_align_enabled", True),
        )
        if route_vad_enabled:
            # 변경 금지: 청크별 오디오 라우팅에서는 후보가 고른 VAD까지 같이 보존해야
            # 마카오처럼 잡음이 큰 구간이 clearvoice/ten_vad 경로로 실제 렌더링됩니다.
            for key in self._AUDIO_ROUTE_VAD_SETTING_KEYS:
                if key in source:
                    tune[key] = deepcopy(source[key])
        return tune

    def _score_audio_route_preview_candidate(
        self,
        *,
        candidate_row: dict,
        candidate_settings: dict,
        raw_features: dict,
        raw_profile: dict,
        preview_features: dict,
        preview_profile: dict,
    ) -> tuple[float, dict]:
        base = max(0.0, min(1.0, float(candidate_row.get("score", 0.0) or 0.0)))
        raw_speech = max(0.0, min(1.0, float(raw_profile.get("speech_confidence", 0.0) or 0.0)))
        speech = max(0.0, min(1.0, float(preview_profile.get("speech_confidence", 0.0) or 0.0)))
        speech_drop = max(0.0, raw_speech - speech)
        raw_noise = float(raw_features.get("high_band_ratio", 0.0) or 0.0) + max(
            0.0, float(raw_features.get("low_band_ratio", 0.0) or 0.0) - 0.45
        )
        preview_noise = float(preview_features.get("high_band_ratio", 0.0) or 0.0) + max(
            0.0, float(preview_features.get("low_band_ratio", 0.0) or 0.0) - 0.45
        )
        noise_gain = max(-0.3, min(0.3, raw_noise - preview_noise))
        silence_drift = abs(
            float(preview_features.get("silence_ratio", 0.0) or 0.0)
            - float(raw_features.get("silence_ratio", 0.0) or 0.0)
        )
        rms_drift = abs(
            float(preview_features.get("rms_mean", 0.0) or 0.0)
            - float(raw_features.get("rms_mean", 0.0) or 0.0)
        )
        stability = max(0.0, min(1.0, 1.0 - (silence_drift * 1.4) - (rms_drift * 8.0)))
        vad = str(candidate_settings.get("selected_vad", "none") or "none").strip().lower()
        noise_level = str(raw_profile.get("noise_level") or "low").strip().lower()
        volatile = bool(raw_profile.get("volatile_scene"))
        vad_bonus = 0.0
        if vad == "ten_vad" and noise_level == "high":
            vad_bonus += 0.04
        elif vad == "silero" and noise_level == "low":
            vad_bonus += 0.02
        if volatile and str(candidate_settings.get("selected_audio_ai", "none") or "none").strip().lower() != "none":
            vad_bonus += 0.02
        preview_quiet = bool(preview_profile.get("quiet"))
        quiet_penalty = 0.0
        if preview_quiet and not bool(raw_profile.get("quiet")):
            quiet_penalty += 0.06
        if speech_drop >= 0.16 and str(candidate_settings.get("selected_audio_ai", "none") or "none").strip().lower() != "none":
            quiet_penalty += 0.04
        speech_penalty = min(0.22, speech_drop * 0.42)

        total = (
            (base * 0.34)
            + (speech * 0.30)
            + ((0.5 + noise_gain) * 0.16)
            + (stability * 0.20)
            + vad_bonus
            - speech_penalty
            - quiet_penalty
        )
        total = max(0.0, min(0.99, total))
        details = {
            "base_score": round(base, 4),
            "raw_speech_score": round(raw_speech, 4),
            "speech_score": round(speech, 4),
            "speech_drop": round(speech_drop, 4),
            "noise_gain": round(noise_gain, 4),
            "stability_score": round(stability, 4),
            "vad_bonus": round(vad_bonus, 4),
            "speech_penalty": round(speech_penalty, 4),
            "quiet_penalty": round(quiet_penalty, 4),
            "preview_quiet": preview_quiet,
            "volatile_scene": volatile,
        }
        return total, details

    def _write_adaptive_preview_sample(
        self,
        sample_path: str,
        out_path: str,
        settings: dict,
        *,
        tmpdir: str,
        label: str,
    ) -> bool:
        audio_ai = str(settings.get("selected_audio_ai", "none") or "none").lower()
        use_basic = bool(settings.get("use_basic_filter", True))
        master_filter = self._build_ffmpeg_preprocess_filter(settings)
        active_filter = self._build_audio_cleanup_filter(audio_ai, settings)

        if self._can_fuse_ffmpeg_preprocess(audio_ai, settings):
            fused_filter = self._build_fused_ffmpeg_filter(audio_ai, settings, use_basic=use_basic)
            cmd = [
                ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
                *self._ffmpeg_parallel_args(settings),
                "-i", sample_path,
                "-ac", "1", "-ar", "16000",
                "-af", fused_filter,
                "-acodec", "pcm_s16le",
                out_path,
            ]
            return (
                self._run_media_command_no_progress(cmd, label=label)
                and os.path.exists(out_path)
                and os.path.getsize(out_path) > 0
            )

        raw_wav = os.path.join(tmpdir, f"{os.path.basename(out_path)}.raw.wav")
        base_cmd = [
            ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
            *self._ffmpeg_parallel_args(settings),
            "-i", sample_path,
            "-ac", "1", "-ar", str(self._audio_processing_sample_rate(audio_ai, settings)),
        ]
        if use_basic:
            base_cmd.extend(["-af", master_filter])
        base_cmd.extend(["-acodec", "pcm_s16le", raw_wav])
        if not self._run_media_command_no_progress(base_cmd, label=f"{label}-base"):
            return False

        ai_wav = raw_wav
        if audio_ai == "rnnoise":
            routed_wav = os.path.join(tmpdir, f"{os.path.basename(out_path)}.rnnoise.wav")
            if self._apply_rnnoise(raw_wav, routed_wav) and os.path.exists(routed_wav):
                ai_wav = routed_wav
        elif audio_ai == "resemble_enhance":
            routed_wav = os.path.join(tmpdir, f"{os.path.basename(out_path)}.resemble.wav")
            if self._apply_resemble_enhance(raw_wav, routed_wav) and os.path.exists(routed_wav):
                ai_wav = routed_wav
        elif audio_ai == "clearvoice":
            routed_wav = os.path.join(tmpdir, f"{os.path.basename(out_path)}.clearvoice.wav")
            prev_clearvoice_settings = getattr(self, "_clearvoice_runtime_settings", None)
            self._clearvoice_runtime_settings = dict(settings)
            try:
                if self._apply_clearvoice(raw_wav, routed_wav) and os.path.exists(routed_wav):
                    ai_wav = routed_wav
            finally:
                self._clearvoice_runtime_settings = prev_clearvoice_settings

        final_cmd = [
            ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
            *self._ffmpeg_parallel_args(settings),
            "-i", ai_wav,
            "-ac", "1", "-ar", "16000",
            "-af", active_filter,
            "-acodec", "pcm_s16le",
            out_path,
        ]
        return (
            self._run_media_command_no_progress(final_cmd, label=f"{label}-final")
            and os.path.exists(out_path)
            and os.path.getsize(out_path) > 0
        )

    def _preview_chunk_audio_route(
        self,
        sample_path: str,
        *,
        route_features: dict,
        route_profile: dict,
        candidate_scores: list[dict],
        settings: dict,
        tmpdir: str,
        force: bool = False,
    ) -> tuple[dict | None, list[dict]]:
        from core.audio.preset_auto_classifier import (
            build_audio_profile,
            build_chunk_route_features,
            candidate_settings_for_id,
        )

        if not candidate_scores or not self._audio_route_preview_enabled(settings):
            return None, []

        top_score = float(candidate_scores[0].get("score", 0.0) or 0.0)
        second_score = float(candidate_scores[1].get("score", 0.0) or 0.0) if len(candidate_scores) > 1 else -1.0
        gap = top_score - second_score if second_score >= 0.0 else top_score
        if (
            not force
            and
            top_score >= self._audio_route_preview_min_confidence(settings)
            and gap >= self._audio_route_preview_gap_max(settings)
            and not bool(route_profile.get("volatile_scene"))
        ):
            return None, []

        preview_rows: list[dict] = []
        best: dict | None = None
        profile_sample_count = self._audio_route_profile_sample_count(settings)
        profile_window_sec = self._audio_route_profile_window_sec(settings)
        for idx, candidate_row in enumerate(candidate_scores[: self._audio_route_candidate_limit(settings)], start=1):
            candidate_id = str(candidate_row.get("id") or "")
            candidate_settings = dict(settings)
            candidate_settings.update(candidate_settings_for_id(candidate_id))
            preview_path = os.path.join(tmpdir, f"preview_{idx:02d}_{candidate_id}.wav")
            if not self._write_adaptive_preview_sample(
                sample_path,
                preview_path,
                candidate_settings,
                tmpdir=tmpdir,
                label=f"오디오 라우팅 프리뷰 {candidate_id}",
            ):
                preview_rows.append(
                    {
                        "id": candidate_id,
                        "label": str(candidate_row.get("label") or candidate_id),
                        "preview_ok": False,
                        "score": 0.0,
                    }
                )
                continue

            preview_features = build_chunk_route_features(
                preview_path,
                sample_count=profile_sample_count,
                window_sec=profile_window_sec,
            )
            preview_profile = build_audio_profile(preview_features)
            preview_score, details = self._score_audio_route_preview_candidate(
                candidate_row=candidate_row,
                candidate_settings=candidate_settings,
                raw_features=route_features,
                raw_profile=route_profile,
                preview_features=preview_features,
                preview_profile=preview_profile,
            )
            row = {
                "id": candidate_id,
                "label": str(candidate_row.get("label") or candidate_id),
                "preview_ok": True,
                "score": round(preview_score, 4),
                "signature": candidate_row.get("signature"),
                "settings": candidate_settings,
                "details": details,
                "preview_profile": preview_profile,
            }
            preview_rows.append(row)
            if best is None or float(row.get("score", 0.0) or 0.0) > float(best.get("score", 0.0) or 0.0):
                best = row
        preview_rows.sort(key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)
        return best, preview_rows

    def _maybe_apply_audio_route_baseline_guard(
        self,
        sample_path: str,
        *,
        route_features: dict,
        route_profile: dict,
        candidate_scores: list[dict],
        selected_strategy: str,
        selected_label: str,
        selected_confidence: float,
        selected_settings: dict,
        preview_self_score: float | None,
        settings: dict,
        tmpdir: str,
    ) -> dict | None:
        from core.audio.audio_presets import auto_audio_settings_only

        if not self._audio_route_baseline_guard_enabled(settings):
            return None

        baseline_settings = self._audio_route_baseline_settings(settings)
        baseline_signature = self._audio_route_settings_signature(baseline_settings)
        selected_signature = self._audio_route_settings_signature(selected_settings)
        if baseline_signature == selected_signature:
            return None

        baseline_seed = max(
            0.42,
            min(
                0.82,
                float(route_profile.get("speech_confidence", 0.0) or 0.0)
                + (0.06 if str(baseline_settings.get("selected_audio_ai", "none") or "none").strip().lower() == "none" else 0.02),
            ),
        )
        selected_seed = max(0.35, min(0.95, float(selected_confidence or 0.0)))
        selected_candidate = self._audio_route_candidate_row_for_settings(
            candidate_scores,
            selected_settings,
            fallback_id=str(selected_strategy or "adaptive_selected"),
            fallback_label=str(selected_label or selected_strategy or "Adaptive Selected"),
            fallback_score=selected_seed,
        )
        baseline_candidate = self._audio_route_candidate_row_for_settings(
            candidate_scores,
            baseline_settings,
            fallback_id="benchmark_locked_baseline",
            fallback_label="기본 High 유지",
            fallback_score=baseline_seed,
        )
        compare_candidates = [selected_candidate]
        if dict(baseline_candidate) != dict(selected_candidate):
            compare_candidates.append(baseline_candidate)

        _best, compare_scores = self._preview_chunk_audio_route(
            sample_path,
            route_features=route_features,
            route_profile=route_profile,
            candidate_scores=compare_candidates,
            settings=settings,
            tmpdir=tmpdir,
            force=True,
        )
        if not compare_scores:
            return None

        def _find_row(target: dict) -> dict | None:
            target_signature = target.get("signature")
            target_id = str(target.get("id") or "")
            for row in compare_scores:
                if row.get("signature") == target_signature:
                    return row
            for row in compare_scores:
                if str(row.get("id") or "") == target_id:
                    return row
            return None

        selected_preview = _find_row(selected_candidate)
        baseline_preview = _find_row(baseline_candidate)
        if not baseline_preview or not baseline_preview.get("preview_ok"):
            return None

        selected_guard_score = float(preview_self_score if preview_self_score is not None else selected_confidence or 0.0)
        if selected_preview and selected_preview.get("preview_ok"):
            selected_guard_score = float(selected_preview.get("score", selected_guard_score) or selected_guard_score)

        margin = self._audio_route_baseline_margin(settings)
        if str(selected_settings.get("selected_audio_ai", "none") or "none").strip().lower() != "none":
            margin += self._audio_route_baseline_non_none_extra_margin(settings)
        if str(selected_strategy or "").strip().lower() == "noisy_voice":
            margin += self._audio_route_baseline_noisy_voice_extra_margin(settings)
        if bool(route_profile.get("volatile_scene")):
            margin += 0.02

        baseline_score = float(baseline_preview.get("score", 0.0) or 0.0)
        adaptive_gain = selected_guard_score - baseline_score
        challenging_profile = self._audio_route_is_challenging_profile(route_profile)
        specialist_strategy = self._audio_route_is_specialist_strategy(selected_strategy)
        if challenging_profile and specialist_strategy:
            margin = max(self._audio_route_baseline_margin(settings), margin - 0.05)
            if adaptive_gain >= max(0.08, margin + 0.01):
                return {
                    "applied": False,
                    "margin": round(margin, 4),
                    "selected_preview_score": round(selected_guard_score, 4),
                    "baseline_preview_score": round(baseline_score, 4),
                    "compare_scores": compare_scores,
                    "reason": (
                        f"도전적 오디오 프로파일에서 {selected_strategy} self-score 우위 "
                        f"{adaptive_gain:.2f}가 커 adaptive route 유지"
                    ),
                }
        if baseline_score + margin < selected_guard_score:
            return {
                "applied": False,
                "margin": round(margin, 4),
                "selected_preview_score": round(selected_guard_score, 4),
                "baseline_preview_score": round(baseline_score, 4),
                "compare_scores": compare_scores,
            }

        return {
            "applied": True,
            "margin": round(margin, 4),
            "selected_preview_score": round(selected_guard_score, 4),
            "baseline_preview_score": round(baseline_score, 4),
            "compare_scores": compare_scores,
            "settings": baseline_settings,
            "audio_strategy": "benchmark_locked_baseline",
            "audio_strategy_label": "기본 High 유지",
            "confidence": round(baseline_score, 4),
            "reason": (
                f"adaptive 후보 self-score {selected_guard_score:.2f} 대비 "
                f"기본 High self-score {baseline_score:.2f}가 margin {margin:.2f} 안이라 기본값 유지"
            ),
        }

    def _route_risk_level(self, confidence: float, profile: dict, settings: dict | None = None) -> str:
        volatile = bool((profile or {}).get("volatile_scene"))
        noise = str((profile or {}).get("noise_level") or "low").strip().lower()
        low_threshold = self._audio_route_low_confidence_threshold(settings)
        secondary_threshold = self._audio_route_secondary_recheck_threshold(settings)
        if confidence <= low_threshold or (volatile and confidence <= secondary_threshold) or noise == "high":
            return "high"
        if confidence <= self._audio_route_precision_threshold(settings) or volatile:
            return "medium"
        return "low"

    def _classify_chunk_audio_route(
        self,
        media_path: str,
        seg: dict,
        settings: dict,
        *,
        index: int,
        tmpdir: str,
    ) -> dict:
        from core.audio.preset_auto_classifier import (
            build_audio_profile,
            build_chunk_route_features,
            candidate_settings_for_id,
            rank_audio_candidates,
            select_audio_candidate,
        )

        start = max(0.0, float(seg.get("start", 0.0) or 0.0))
        end = max(start, float(seg.get("end", start) or start))
        sample_start, sample_dur = self._audio_route_sample_span(start, end, settings)
        sample_path = os.path.join(tmpdir, f"route_{index:03d}_{sample_start:.3f}.wav")
        if not self._extract_audio_route_sample(
            media_path,
            sample_path,
            start=sample_start,
            duration=sample_dur,
            settings=settings,
        ):
            return self._fallback_chunk_audio_route(settings, reason="샘플 추출 실패")

        try:
            features = build_chunk_route_features(
                sample_path,
                sample_count=self._audio_route_profile_sample_count(settings),
                window_sec=self._audio_route_profile_window_sec(settings),
            )
            features.update({
                "sample_duration_sec": sample_dur,
                "total_scanned_sec": sample_dur,
                "media_duration_sec": max(0.0, end - start),
            })
            profile = build_audio_profile(features)
            result = select_audio_candidate(profile, features, use_lora_prior=True)
            candidate_scores = rank_audio_candidates(profile, features, use_lora_prior=True)
            feature_strategy = str(result.get("id") or "clean_voice")
            feature_label = str(result.get("label") or "")
            feature_confidence = float(result.get("score", 0.0) or 0.0)
            selected_strategy = feature_strategy
            selected_label = feature_label
            selected_confidence = feature_confidence
            tune = self._audio_route_tune_settings(candidate_settings_for_id(feature_strategy), settings)
            preview_best, preview_scores = self._preview_chunk_audio_route(
                sample_path,
                route_features=features,
                route_profile=profile,
                candidate_scores=candidate_scores,
                settings=settings,
                tmpdir=tmpdir,
            )
            decision_source = "feature_classifier"
            preview_self_score = None
            preview_strategy = feature_strategy
            preview_route_switched = False
            route_reason = str(result.get("reason") or "")
            if preview_best and preview_best.get("preview_ok"):
                decision_source = "feature_plus_preview"
                preview_strategy = str(preview_best.get("id") or selected_strategy)
                preview_route_switched = preview_strategy != feature_strategy
                selected_strategy = preview_strategy
                selected_label = str(preview_best.get("label") or selected_label)
                selected_confidence = float(preview_best.get("score", selected_confidence) or selected_confidence)
                preview_self_score = float(preview_best.get("score", 0.0) or 0.0)
                tune = self._audio_route_tune_settings(preview_best.get("settings") or tune, settings)
                route_reason = (
                    f"{route_reason}; 프리뷰 self-score {preview_self_score:.2f}로 "
                    f"{selected_label or selected_strategy} 유지/선택"
                ).strip("; ")
            baseline_guard = self._maybe_apply_audio_route_baseline_guard(
                sample_path,
                route_features=features,
                route_profile=profile,
                candidate_scores=candidate_scores,
                selected_strategy=selected_strategy,
                selected_label=selected_label,
                selected_confidence=selected_confidence,
                selected_settings=tune,
                preview_self_score=preview_self_score,
                settings=settings,
                tmpdir=tmpdir,
            )
            if baseline_guard and baseline_guard.get("applied"):
                decision_source = f"{decision_source}_baseline_guard"
                selected_strategy = str(baseline_guard.get("audio_strategy") or selected_strategy)
                selected_label = str(baseline_guard.get("audio_strategy_label") or selected_label)
                selected_confidence = float(baseline_guard.get("confidence", selected_confidence) or selected_confidence)
                tune = self._audio_route_tune_settings(baseline_guard.get("settings") or tune, settings)
                preview_self_score = float(baseline_guard.get("baseline_preview_score", selected_confidence) or selected_confidence)
                route_reason = (
                    f"{route_reason}; {str(baseline_guard.get('reason') or '').strip()}"
                ).strip("; ")
            risk_level = self._route_risk_level(selected_confidence, profile, settings)
            if self._audio_route_preserve_base_vad_for_confident_route(selected_confidence, settings):
                before_vad = str(tune.get("selected_vad") or "")
                tune = self._audio_route_with_base_vad_settings(tune, settings)
                after_vad = str(tune.get("selected_vad") or before_vad)
                if before_vad and after_vad and before_vad != after_vad:
                    # 변경 금지: 오디오 필터 선택과 VAD 선택은 분리한다. X5에서는
                    # ClearVoice가 유효해도 ten_vad가 긴 VAD 덩어리를 만들어 STT2
                    # 예산을 소모했다. confidence가 충분하면 기준 VAD(silero)를 유지한다.
                    route_reason = (
                        f"{route_reason}; confident route라 VAD는 기준값 {after_vad} 유지"
                    ).strip("; ")
            return {
                "audio_strategy": selected_strategy,
                "audio_strategy_label": selected_label,
                "audio_tune_reason": route_reason,
                "confidence": selected_confidence,
                "feature_confidence": feature_confidence,
                "feature_audio_strategy": feature_strategy,
                "preview_audio_strategy": preview_strategy,
                "preview_route_switched": preview_route_switched,
                "self_score": preview_self_score,
                "settings": tune,
                "audio_profile": profile,
                "features": features,
                "candidate_scores": list(candidate_scores or result.get("candidate_scores") or []),
                "preview_scores": preview_scores,
                "decision_source": decision_source,
                "risk_level": risk_level,
                "precision_review": selected_confidence <= self._audio_route_precision_threshold(settings) or risk_level != "low",
                "secondary_recheck_hint": self._audio_route_secondary_recheck_hint(selected_confidence, risk_level, settings),
                "baseline_guard_applied": bool(baseline_guard and baseline_guard.get("applied")),
                "baseline_guard_margin": None if not baseline_guard else baseline_guard.get("margin"),
                "baseline_guard_scores": [] if not baseline_guard else list(baseline_guard.get("compare_scores") or []),
                "sample_start": sample_start,
                "sample_duration": sample_dur,
            }
        except Exception as exc:
            return self._fallback_chunk_audio_route(settings, reason=f"프로파일링 실패: {exc}")

    def _route_log_line(self, idx: int, seg: dict, route: dict) -> str:
        settings = dict(route.get("settings") or {})
        profile = dict(route.get("audio_profile") or {})
        start = float(seg.get("start", 0.0) or 0.0)
        end = float(seg.get("end", start) or start)
        audio_ai = self._audio_cleanup_label(str(settings.get("selected_audio_ai", "none") or "none"), True)
        vad = str(settings.get("selected_vad", "none") or "none")
        confidence = int(round(float(route.get("confidence", 0.0) or 0.0) * 100))
        env = str(profile.get("environment") or "-")
        noise = str(profile.get("noise_level") or "-")
        return (
            f"    · 청크 {idx + 1:02d} {start:.1f}s~{end:.1f}s: "
            f"{audio_ai} / VAD {vad} / {env} / noise {noise} / confidence {confidence}%"
        )

    def _apply_audio_route_hysteresis(self, grouped: list[dict], routes: list[dict], settings: dict) -> list[dict]:
        if not routes:
            return routes
        if not self._settings_bool(settings, "audio_chunk_route_hysteresis_enabled", True):
            return routes

        margin = self._audio_route_hysteresis_margin(settings)
        stabilized: list[dict] = []
        previous: dict | None = None
        for idx, route in enumerate(routes):
            current = dict(route or {})
            current_settings = dict(current.get("settings") or current.get("audio_tune_settings") or {})
            current_strategy = str(current.get("audio_strategy") or "")
            current_conf = float(
                current.get("self_score", current.get("confidence", current.get("feature_confidence", 0.0))) or 0.0
            )
            profile = dict(current.get("audio_profile") or {})
            dynamic_margin = margin + (0.03 if bool(profile.get("volatile_scene")) else 0.0)
            if previous is not None:
                prev_strategy = str(previous.get("audio_strategy") or "")
                prev_conf = float(
                    previous.get("self_score", previous.get("confidence", previous.get("feature_confidence", 0.0))) or 0.0
                )
                if current_strategy and prev_strategy and current_strategy != prev_strategy:
                    baseline_guard_locked = bool(current.get("baseline_guard_applied")) and current_strategy == "benchmark_locked_baseline"
                    if baseline_guard_locked:
                        stabilized.append(current)
                        previous = current
                        continue
                    if current_conf < prev_conf + dynamic_margin:
                        current["hysteresis_applied"] = True
                        current["hysteresis_margin"] = round(dynamic_margin, 4)
                        current["hysteresis_original_strategy"] = current_strategy
                        current["hysteresis_original_settings"] = current_settings
                        current["audio_strategy"] = prev_strategy
                        current["audio_strategy_label"] = str(previous.get("audio_strategy_label") or prev_strategy)
                        kept_settings = dict(previous.get("settings") or previous.get("audio_tune_settings") or {})
                        current["settings"] = kept_settings
                        current["audio_tune_settings"] = kept_settings
                        current["selected_vad"] = str(
                            kept_settings.get("selected_vad", current_settings.get("selected_vad", ""))
                        )
                        current["confidence"] = round(max(current_conf, prev_conf - (dynamic_margin / 2.0)), 4)
                        current["precision_review"] = bool(previous.get("precision_review") or current.get("precision_review"))
                        current["secondary_recheck_hint"] = bool(
                            previous.get("secondary_recheck_hint") or current.get("secondary_recheck_hint")
                        )
            stabilized.append(current)
            previous = current
        return stabilized

    @staticmethod
    def _route_effective_score(route: dict | None) -> float:
        row = dict(route or {})
        return float(
            row.get("self_score", row.get("confidence", row.get("feature_confidence", 0.0))) or 0.0
        )

    def _apply_audio_route_profile_memory(self, grouped: list[dict], routes: list[dict], settings: dict) -> list[dict]:
        _ = grouped
        if not routes:
            return routes
        if not self._audio_route_profile_memory_enabled(settings):
            return routes

        from core.audio.preset_auto_classifier import build_audio_route_bucket

        margin = self._audio_route_profile_memory_margin(settings)
        min_confidence = self._audio_route_profile_memory_min_confidence(settings)
        stabilized: list[dict] = []
        bucket_memory: dict[str, dict] = {}

        for idx, route in enumerate(routes):
            current = dict(route or {})
            current_settings = dict(current.get("settings") or current.get("audio_tune_settings") or {})
            current_strategy = str(current.get("audio_strategy") or "")
            current_score = self._route_effective_score(current)
            profile = dict(current.get("audio_profile") or {})
            bucket = build_audio_route_bucket(profile)
            current["profile_bucket"] = bucket

            remembered = bucket_memory.get(bucket)
            baseline_guard_locked = bool(current.get("baseline_guard_applied")) and current_strategy == "benchmark_locked_baseline"
            current_is_fallback = current_strategy == "clip_fallback"

            if remembered and not baseline_guard_locked:
                remembered_strategy = str(remembered.get("audio_strategy") or "")
                remembered_score = float(remembered.get("score", 0.0) or 0.0)
                remembered_settings = dict(remembered.get("settings") or {})
                remembered_label = str(remembered.get("audio_strategy_label") or remembered_strategy)
                remembered_reusable = (
                    remembered_strategy
                    and remembered_strategy != "clip_fallback"
                    and remembered_score >= min_confidence
                )
                confidence_gap_small = current_score < remembered_score + margin
                current_is_ambiguous = current_score < min_confidence
                if (
                    remembered_reusable
                    and remembered_strategy != current_strategy
                    and (current_is_fallback or current_is_ambiguous or confidence_gap_small)
                ):
                    adopted_score = round(max(current_score, remembered_score - (margin / 2.0)), 4)
                    current["profile_memory_applied"] = True
                    current["profile_memory_bucket"] = bucket
                    current["profile_memory_margin"] = round(margin, 4)
                    current["profile_memory_original_strategy"] = current_strategy
                    current["profile_memory_original_settings"] = current_settings
                    current["profile_memory_reason"] = (
                        f"유사 오디오 프로파일({bucket})에서 직전 안정 route {remembered_strategy} 재사용"
                    )
                    current["audio_strategy"] = remembered_strategy
                    current["audio_strategy_label"] = remembered_label
                    current["settings"] = remembered_settings
                    current["audio_tune_settings"] = remembered_settings
                    current["confidence"] = adopted_score
                    current["self_score"] = adopted_score
                    current_strategy = remembered_strategy
                    current_settings = remembered_settings
                    current_score = adopted_score

            stabilized.append(current)

            final_strategy = str(current.get("audio_strategy") or "")
            final_score = self._route_effective_score(current)
            final_settings = dict(current.get("settings") or current.get("audio_tune_settings") or {})
            if final_strategy and final_strategy != "clip_fallback" and final_score >= min_confidence:
                existing = bucket_memory.get(bucket)
                existing_score = float((existing or {}).get("score", 0.0) or 0.0)
                existing_strategy = str((existing or {}).get("audio_strategy") or "")
                if existing is None or existing_strategy == final_strategy or final_score > existing_score + margin:
                    bucket_memory[bucket] = {
                        "index": idx,
                        "audio_strategy": final_strategy,
                        "audio_strategy_label": str(current.get("audio_strategy_label") or final_strategy),
                        "settings": final_settings,
                        "score": round(final_score, 4),
                    }

        return stabilized

    def _apply_audio_route_switch_confirmation(self, grouped: list[dict], routes: list[dict], settings: dict) -> list[dict]:
        _ = grouped
        if not routes:
            return routes
        if not self._audio_route_switch_confirmation_enabled(settings):
            return routes

        min_streak = self._audio_route_switch_confirmation_min_streak(settings)
        margin = self._audio_route_switch_confirmation_margin(settings)
        strong_margin = max(margin, self._audio_route_switch_confirmation_strong_margin(settings))
        stabilized: list[dict] = []
        stable_route: dict | None = None
        pending_strategy = ""
        pending_bucket = ""
        pending_streak = 0
        pending_best_score = 0.0

        for current_idx, route in enumerate(routes):
            current = dict(route or {})
            current_settings = dict(current.get("settings") or current.get("audio_tune_settings") or {})
            current_strategy = str(current.get("audio_strategy") or "")
            current_score = self._route_effective_score(current)
            profile = dict(current.get("audio_profile") or {})
            bucket = str(current.get("profile_bucket") or profile.get("profile_bucket") or "").strip()
            if not bucket:
                from core.audio.preset_auto_classifier import build_audio_route_bucket

                bucket = build_audio_route_bucket(profile)
                current["profile_bucket"] = bucket
            baseline_guard_locked = bool(current.get("baseline_guard_applied")) and current_strategy == "benchmark_locked_baseline"

            if stable_route is None or not current_strategy:
                stabilized.append(current)
                stable_route = current
                pending_strategy = ""
                pending_bucket = ""
                pending_streak = 0
                pending_best_score = 0.0
                continue

            stable_strategy = str(stable_route.get("audio_strategy") or "")
            stable_score = self._route_effective_score(stable_route)
            stable_settings = dict(stable_route.get("settings") or stable_route.get("audio_tune_settings") or {})
            stable_label = str(stable_route.get("audio_strategy_label") or stable_strategy)

            if baseline_guard_locked or current_strategy == stable_strategy:
                stabilized.append(current)
                stable_route = current
                pending_strategy = ""
                pending_bucket = ""
                pending_streak = 0
                pending_best_score = 0.0
                continue

            dynamic_margin = margin + (0.02 if bool(profile.get("volatile_scene")) else 0.0)
            dynamic_strong_margin = strong_margin + (0.03 if bool(profile.get("volatile_scene")) else 0.0)

            if current_score >= stable_score + dynamic_strong_margin:
                current["switch_confirmation_bypassed"] = True
                current["switch_confirmation_margin"] = round(dynamic_strong_margin, 4)
                current["switch_confirmation_reason"] = (
                    f"새 route {current_strategy} self-score {current_score:.2f}가 "
                    f"이전 안정 route {stable_strategy} {stable_score:.2f}보다 충분히 높아 즉시 전환"
                )
                stabilized.append(current)
                stable_route = current
                pending_strategy = ""
                pending_bucket = ""
                pending_streak = 0
                pending_best_score = 0.0
                continue

            if pending_strategy == current_strategy and pending_bucket == bucket:
                pending_streak += 1
                pending_best_score = max(pending_best_score, current_score)
            else:
                pending_strategy = current_strategy
                pending_bucket = bucket
                pending_streak = 1
                pending_best_score = current_score

            if pending_streak >= min_streak and pending_best_score >= stable_score + dynamic_margin:
                current["switch_confirmation_approved"] = True
                current["switch_confirmation_margin"] = round(dynamic_margin, 4)
                current["switch_confirmation_streak"] = pending_streak
                current["switch_confirmation_reason"] = (
                    f"새 route {current_strategy}가 유사 구간 {pending_streak}개 연속 확인되어 전환"
                )
                stabilized.append(current)
                stable_route = current
                pending_strategy = ""
                pending_bucket = ""
                pending_streak = 0
                pending_best_score = 0.0
                continue

            adopted_score = round(max(current_score, stable_score - (dynamic_margin / 2.0)), 4)
            current["switch_confirmation_applied"] = True
            current["switch_confirmation_original_strategy"] = current_strategy
            current["switch_confirmation_original_settings"] = current_settings
            current["switch_confirmation_margin"] = round(dynamic_margin, 4)
            current["switch_confirmation_streak"] = pending_streak
            current["switch_confirmation_reason"] = (
                f"새 route {current_strategy} 전환 전 확인 중({pending_streak}/{min_streak})이라 "
                f"이전 안정 route {stable_strategy} 유지"
            )
            current["audio_strategy"] = stable_strategy
            current["audio_strategy_label"] = stable_label
            current["settings"] = stable_settings
            current["audio_tune_settings"] = stable_settings
            current["confidence"] = adopted_score
            current["self_score"] = adopted_score
            current["precision_review"] = bool(
                stable_route.get("precision_review") or current.get("precision_review")
            )
            current["secondary_recheck_hint"] = bool(
                stable_route.get("secondary_recheck_hint") or current.get("secondary_recheck_hint")
            )
            stabilized.append(current)

        return stabilized
