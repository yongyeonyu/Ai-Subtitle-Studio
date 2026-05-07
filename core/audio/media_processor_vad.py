# Version: 03.13.03
# Phase: PHASE2
"""VAD detection and VAD-based chunking helpers for VideoProcessor."""

from __future__ import annotations

import json
import math
import os
import sys
import wave

from core.runtime.logger import get_logger
from core.subtitle_quality.vad_alignment_checker import apply_review_vad_settings, review_vad_config

_CHUNK_DURATION = 30


def _runtime_get_logger():
    owner = sys.modules.get("core.audio.media_processor")
    return getattr(owner, "get_logger", get_logger)()


class VideoProcessorVadMixin:
    def _has_force_split_activity(self, stats: dict, settings: dict | None = None) -> bool:
        settings = settings or {}
        try:
            min_peak = float(settings.get("empty_vad_force_split_min_peak", 0.04))
        except (TypeError, ValueError):
            min_peak = 0.04
        try:
            min_rms = float(settings.get("empty_vad_force_split_min_rms", 0.008))
        except (TypeError, ValueError):
            min_rms = 0.008
        peak = float(stats.get("peak", 0.0) or 0.0)
        rms = float(stats.get("rms", 0.0) or 0.0)
        return peak >= max(0.0, min_peak) or rms >= max(0.0, min_rms)

    def _wav_activity_stats(self, wav_path: str) -> dict:
        stats = {"duration": 0.0, "peak": 0.0, "rms": 0.0}
        try:
            from array import array
            with wave.open(wav_path, "rb") as wf:
                sample_width = wf.getsampwidth()
                frame_rate = max(1, int(wf.getframerate() or 1))
                channels = max(1, int(wf.getnchannels() or 1))
                total_frames = max(0, int(wf.getnframes() or 0))
                stats["duration"] = total_frames / float(frame_rate)
                if total_frames <= 0 or sample_width <= 0:
                    return stats

                max_sample = float((1 << (8 * sample_width - 1)) - 1) if sample_width > 1 else 128.0
                max_sample = max(max_sample, 1.0)
                total_samples = 0
                square_sum = 0.0
                peak = 0.0
                frames_per_read = max(1024, min(frame_rate, 65536))

                while True:
                    raw = wf.readframes(frames_per_read)
                    if not raw:
                        break
                    samples = []
                    if sample_width == 2:
                        usable = len(raw) - (len(raw) % 2)
                        values = array("h")
                        values.frombytes(raw[:usable])
                        if sys.byteorder != "little":
                            values.byteswap()
                        samples = values
                    else:
                        usable = len(raw) - (len(raw) % sample_width)
                        signed = sample_width > 1
                        for offset in range(0, usable, sample_width):
                            value = int.from_bytes(raw[offset:offset + sample_width], "little", signed=signed)
                            if sample_width == 1:
                                value -= 128
                            samples.append(value)
                    if not samples:
                        continue
                    total_samples += len(samples)
                    chunk_peak = max(abs(int(v)) for v in samples) / max_sample
                    peak = max(peak, chunk_peak)
                    square_sum += sum(float(v) * float(v) for v in samples) / (max_sample * max_sample)

                if total_samples > 0:
                    stats["rms"] = math.sqrt(square_sum / total_samples)
                stats["peak"] = peak
                if channels > 1:
                    stats["channels"] = channels
        except Exception as e:
            _runtime_get_logger().log(f"  ⚠️ WAV 활동량 분석 실패: {e}")
        return stats

    def _vad_retry_timestamps_are_usable(self, raw_ts: list, sample_rate: int, total_dur: float) -> bool:
        if not raw_ts:
            return False
        duration = max(0.001, float(total_dur or 0.0))
        spans = []
        for ts in raw_ts:
            try:
                start = max(0.0, float(ts.get("start", 0)) / float(sample_rate))
                end = max(start, float(ts.get("end", 0)) / float(sample_rate))
            except (AttributeError, TypeError, ValueError):
                continue
            if end > start:
                spans.append((start, end))
        if not spans:
            return False

        total_voice = sum(end - start for start, end in spans)
        avg_voice = total_voice / max(1, len(spans))
        coverage = total_voice / duration
        min_total_voice = min(2.0, max(0.35, duration * 0.01))
        too_many_fragments = len(spans) > max(20, int(duration / 1.5))
        mostly_micro_fragments = avg_voice < 0.18

        if total_voice < min_total_voice:
            return False
        if mostly_micro_fragments:
            return False
        if too_many_fragments and avg_voice < 0.45:
            return False
        if coverage > 0.96 and len(spans) > 1:
            return False
        return True

    def _vad_flags_to_segments(
        self,
        flags: list[int],
        *,
        hop_sec: float,
        min_speech_sec: float,
        min_silence_sec: float,
        speech_pad_sec: float,
        source: str,
        for_post_stt_align: bool = False,
    ) -> list[dict]:
        raw: list[tuple[float, float]] = []
        start_idx = None
        for idx, flag in enumerate(flags):
            if flag and start_idx is None:
                start_idx = idx
            elif not flag and start_idx is not None:
                raw.append((start_idx * hop_sec, idx * hop_sec))
                start_idx = None
        if start_idx is not None:
            raw.append((start_idx * hop_sec, len(flags) * hop_sec))

        min_speech = max(0.0, float(min_speech_sec or 0.0))
        min_silence = max(0.0, float(min_silence_sec or 0.0))
        pad = max(0.0, float(speech_pad_sec or 0.0))
        merged: list[list[float]] = []
        for start, end in raw:
            if end - start < min_speech:
                continue
            start = max(0.0, start - pad)
            end = end + pad
            if merged and start - merged[-1][1] <= min_silence:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])

        return [
            {
                "start": round(start, 3),
                "end": round(max(start, end), 3),
                "source": source,
                "post_stt_align": bool(for_post_stt_align),
                "vad_word_filter": not bool(for_post_stt_align),
                "speech_pad_sec": round(pad, 3),
                "min_silence_sec": round(min_silence, 3),
            }
            for start, end in merged
            if end > start
        ]

    def _detect_ten_vad_timestamps(
        self,
        wav_path: str,
        vad_model: str,
        s: dict,
        *,
        for_post_stt_align: bool = False,
    ) -> list[dict]:
        try:
            import numpy as np
            from ten_vad import TenVad

            label = vad_model.upper()
            self._notify_stage(f"⏳ [VAD] {label} 모델 준비 중")
            _runtime_get_logger().log(f"  └ [VAD 후처리] {label} 모델 준비 중...")
            effective_s = apply_review_vad_settings(s)
            hop_size = int(effective_s.get("ten_vad_hop_size", 256) or 256)
            threshold = float(effective_s.get("ten_vad_threshold", effective_s.get("vad_threshold", 0.5)) or 0.5)
            min_speech = float(effective_s.get("vad_min_speech", 0.25) or 0.25)
            min_silence = float(effective_s.get("vad_min_silence", 2.0) or 2.0)
            speech_pad = float(effective_s.get("vad_speech_pad", 0.2) or 0.2)

            self._notify_stage(f"⏳ [VAD] {label} 오디오 로드 중")
            _runtime_get_logger().log(f"  └ [VAD 후처리] {label} 오디오 로드 중...")
            with wave.open(wav_path, "rb") as wav:
                sample_rate = wav.getframerate()
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                frames = wav.readframes(wav.getnframes())
            if sample_rate != 16000 or channels != 1 or sample_width != 2:
                _runtime_get_logger().log(
                    "  ⚠️ TEN VAD는 16kHz mono int16 WAV만 지원합니다. Silero VAD로 계속 진행합니다"
                )
                return []

            audio = np.frombuffer(frames, dtype=np.int16)
            frame_count = len(audio) // hop_size
            if frame_count <= 0:
                return []

            detector = TenVad(hop_size, threshold)
            flags: list[int] = []
            state = getattr(self, "_vad_progress_state", {})
            state.pop(f"{label}:오디오 스캔", None)
            self._vad_progress_state = state
            self._emit_vad_progress(label, "오디오 스캔", 0, force=True)
            for idx in range(frame_count):
                frame = np.ascontiguousarray(audio[idx * hop_size:(idx + 1) * hop_size])
                _probability, flag = detector.process(frame)
                flags.append(int(flag))
                if frame_count >= 10:
                    self._emit_vad_progress(label, "오디오 스캔", int(((idx + 1) / frame_count) * 100), step=10)
            self._emit_vad_progress(label, "오디오 스캔", 100, force=True)
            self._notify_stage(f"⏳ [VAD] {label} 음성 구간 정리 중")
            _runtime_get_logger().log(f"  └ [VAD 후처리] {label} 음성 구간 정리 중...")
            return self._vad_flags_to_segments(
                flags,
                hop_sec=hop_size / 16000.0,
                min_speech_sec=min_speech,
                min_silence_sec=min_silence,
                speech_pad_sec=speech_pad,
                source=vad_model,
                for_post_stt_align=for_post_stt_align,
            )
        except Exception as e:
            _runtime_get_logger().log(f"  ⚠️ TEN VAD 실행 실패 또는 미설치: {e}")
            return []

    @staticmethod
    def _filter_vad_timestamps_for_range(
        timestamps: list[dict],
        target_start_sec=0.0,
        target_end_sec=None,
        is_single_segment=False,
    ) -> list[dict]:
        out = list(timestamps or [])
        if target_start_sec > 0.0 or target_end_sec is not None:
            filtered = []
            end_limit = target_end_sec if target_end_sec is not None else 99999.0
            for item in out:
                t = dict(item)
                if t["start"] >= end_limit:
                    continue
                if t["end"] <= target_start_sec:
                    continue
                if is_single_segment:
                    t["start"] = max(target_start_sec, t["start"])
                    t["end"] = min(end_limit, t["end"])
                else:
                    t["start"] = max(target_start_sec, t["start"])
                if t["end"] > t["start"]:
                    filtered.append(t)
            out = filtered
        if out and out[0]["start"] < 3.0:
            out[0]["start"] = 0.0
        return out

    def _detect_vad_timestamps(
        self,
        wav_path: str,
        vad_model: str,
        s: dict,
        target_start_sec=0.0,
        target_end_sec=None,
        is_single_segment=False,
        *,
        for_post_stt_align: bool = False,
    ) -> list[dict]:
        requested_vad_model = str(vad_model or "none").lower()
        try:
            cached = self._load_vad_timestamps_cache(
                wav_path,
                requested_vad_model,
                s,
                target_start_sec=target_start_sec,
                target_end_sec=target_end_sec,
                is_single_segment=is_single_segment,
                for_post_stt_align=for_post_stt_align,
            )
            if cached is not None:
                label = requested_vad_model.upper()
                self._notify_stage(f"♻️ [VAD] {label} 음성 위치 캐시 재사용")
                _runtime_get_logger().log(f"  └ ♻️ [VAD 캐시] {label} 음성 위치 {len(cached)}개 재사용")
                return cached

            if vad_model == "ten_vad":
                timestamps = self._detect_ten_vad_timestamps(
                    wav_path,
                    vad_model,
                    s,
                    for_post_stt_align=for_post_stt_align,
                )
                if timestamps:
                    filtered = self._filter_vad_timestamps_for_range(
                        timestamps,
                        target_start_sec,
                        target_end_sec,
                        is_single_segment,
                    )
                    self._write_vad_timestamps_cache(
                        wav_path,
                        requested_vad_model,
                        s,
                        filtered,
                        target_start_sec=target_start_sec,
                        target_end_sec=target_end_sec,
                        is_single_segment=is_single_segment,
                        for_post_stt_align=for_post_stt_align,
                    )
                    return filtered
                _runtime_get_logger().log("  ⚠️ TEN VAD 결과가 없어 Silero VAD로 재시도합니다")
                vad_model = "silero"

            import torch

            effective_s = apply_review_vad_settings(s)
            label = vad_model.upper()
            if not self._vad_loaded:
                self._notify_stage(f"⏳ [VAD] {label} 모델 준비 중")
                _runtime_get_logger().log(f"  └ [VAD 후처리] {label} 모델 준비 중...")
                heartbeat = self._start_vad_heartbeat(label, "모델 준비")
                try:
                    self._vad_model, self._vad_utils = torch.hub.load(
                        repo_or_dir="snakers4/silero-vad",
                        model="silero_vad",
                        force_reload=False,
                        onnx=False,
                    )
                finally:
                    self._stop_vad_heartbeat(heartbeat)
                self._vad_loaded = True
                _runtime_get_logger().log(f"  └ [VAD 후처리] {label} 모델 준비 완료")

            model = self._vad_model
            utils = self._vad_utils
            (get_speech_timestamps, _, read_audio, _, _) = utils
            v_thresh = float(effective_s.get("vad_threshold", 0.5))
            v_min_sp = int(float(effective_s.get("vad_min_speech", 0.25)) * 1000)
            v_min_sil = int(float(effective_s.get("vad_min_silence", 2.0)) * 1000)
            v_pad_ms = int(float(effective_s.get("vad_speech_pad", 0.2)) * 1000)
            v_window = int(effective_s.get("vad_window_size", 512) or 512)

            self._notify_stage(f"⏳ [VAD] {label} 오디오 로드 중")
            _runtime_get_logger().log(f"  └ [VAD 후처리] {label} 오디오 로드 중...")
            audio_data = read_audio(wav_path)
            _runtime_get_logger().log(f"  └ [VAD 후처리] {label} 오디오 로드 완료")
            self._notify_stage(f"⏳ [VAD] {label} 오디오 분석 중")
            _runtime_get_logger().log(f"  └ [VAD 후처리] {label} 오디오 분석 중...")
            heartbeat = self._start_vad_heartbeat(label, "오디오 분석")
            try:
                raw_ts = get_speech_timestamps(
                    audio_data,
                    model,
                    sampling_rate=16000,
                    threshold=v_thresh,
                    min_speech_duration_ms=v_min_sp,
                    min_silence_duration_ms=v_min_sil,
                    speech_pad_ms=v_pad_ms,
                    window_size_samples=v_window,
                )
            finally:
                self._stop_vad_heartbeat(heartbeat)
            stats = None
            if not raw_ts:
                stats = self._wav_activity_stats(wav_path)
                if self._has_force_split_activity(stats, s):
                    retry_profiles = [
                        (
                            max(0.30, min(0.40, v_thresh - 0.12 if v_thresh > 0.45 else v_thresh * 0.82)),
                            max(120, min(v_min_sp, 160)),
                            max(450, min(v_min_sil, 600)),
                            max(v_pad_ms, 200),
                        ),
                        (
                            max(0.24, min(0.34, v_thresh * 0.62)),
                            max(100, min(v_min_sp, 130)),
                            max(320, min(v_min_sil, 450)),
                            max(v_pad_ms, 250),
                        ),
                        (
                            max(0.20, min(0.28, v_thresh * 0.50)),
                            max(90, min(v_min_sp, 110)),
                            max(240, min(v_min_sil, 340)),
                            max(v_pad_ms, 300),
                        ),
                    ]
                    for retry_idx, (retry_thresh, retry_min_sp, retry_min_sil, retry_pad_ms) in enumerate(retry_profiles, 1):
                        self._notify_stage(f"⏳ [VAD] {label} 오디오 분석 재시도 {retry_idx}/3")
                        _runtime_get_logger().log(f"  └ [VAD 후처리] {label} 오디오 분석 재시도 {retry_idx}/3")
                        heartbeat = self._start_vad_heartbeat(label, f"재시도 {retry_idx}/3")
                        try:
                            raw_ts = get_speech_timestamps(
                                audio_data,
                                model,
                                sampling_rate=16000,
                                threshold=retry_thresh,
                                min_speech_duration_ms=retry_min_sp,
                                min_silence_duration_ms=retry_min_sil,
                                speech_pad_ms=retry_pad_ms,
                                window_size_samples=v_window,
                            )
                        finally:
                            self._stop_vad_heartbeat(heartbeat)
                        if raw_ts and self._vad_retry_timestamps_are_usable(raw_ts, 16000, stats.get("duration", 0.0)):
                            _runtime_get_logger().log(f"  └ [VAD 후처리] 재시도 {retry_idx}회차로 음성 위치 확보")
                            break
                        raw_ts = []

            self._notify_stage(f"⏳ [VAD] {label} 음성 구간 정리 중")
            _runtime_get_logger().log(f"  └ [VAD 후처리] {label} 음성 구간 정리 중...")
            timestamps = [
                {
                    "start": t["start"] / 16000.0,
                    "end": t["end"] / 16000.0,
                    "source": vad_model,
                    "post_stt_align": bool(for_post_stt_align),
                    "vad_word_filter": not bool(for_post_stt_align),
                    "speech_pad_sec": round(v_pad_ms / 1000.0, 3),
                    "min_silence_sec": round(v_min_sil / 1000.0, 3),
                }
                for t in raw_ts
            ]

            if target_start_sec > 0.0 or target_end_sec is not None:
                filtered = []
                end_limit = target_end_sec if target_end_sec is not None else 99999.0
                for t in timestamps:
                    if t["start"] >= end_limit:
                        continue
                    if t["end"] <= target_start_sec:
                        continue
                    t = dict(t)
                    if is_single_segment:
                        t["start"] = max(target_start_sec, t["start"])
                        t["end"] = min(end_limit, t["end"])
                    else:
                        t["start"] = max(target_start_sec, t["start"])
                    if t["end"] > t["start"]:
                        filtered.append(t)
                timestamps = filtered

            if timestamps and timestamps[0]["start"] < 3.0:
                timestamps[0]["start"] = 0.0
            self._write_vad_timestamps_cache(
                wav_path,
                requested_vad_model,
                s,
                timestamps,
                target_start_sec=target_start_sec,
                target_end_sec=target_end_sec,
                is_single_segment=is_single_segment,
                for_post_stt_align=for_post_stt_align,
            )
            return timestamps
        except Exception as e:
            _runtime_get_logger().log(f"⚠️ VAD 후처리 분석 오류: {e}")
            return []
        finally:
            release = getattr(self, "release_vad_runtime_models", None)
            if callable(release) and requested_vad_model != "none":
                release(log_context="VAD 후처리")

    # 💡 [STEP 3] VAD 분할기 (들여쓰기 및 8개 인자 완벽 교정)
    # [core/media_processor.py] _split_with_vad 함수 전체 교체
    def _split_with_vad(self, wav_path: str, chunk_dir: str, vad_model: str, s: dict, target_start_sec=0.0, target_end_sec=None, is_single_segment=False):
        requested_vad_model = str(vad_model or "none").lower()
        try:
            effective_s = apply_review_vad_settings(s)
            vad_cfg = review_vad_config(s)
            if vad_cfg["review_vad_before_stt_enabled"] and vad_cfg["review_vad_strict_mode"]:
                _runtime_get_logger().log(
                    "  └ 🧪 자막 품질 검수 VAD: "
                    f"pad {vad_cfg['review_vad_speech_pad_sec']:.2f}s / "
                    f"min silence {vad_cfg['review_vad_min_silence_sec']:.2f}s"
                )
            if vad_model == "ten_vad":
                timestamps = self._detect_ten_vad_timestamps(wav_path, vad_model, s)
                if timestamps:
                    timestamps = self._filter_vad_timestamps_for_range(
                        timestamps,
                        target_start_sec,
                        target_end_sec,
                        is_single_segment,
                    )
                    if not timestamps:
                        _runtime_get_logger().log("⚠️ 해당 구간에서 유효한 TEN VAD 음성 신호를 찾지 못했습니다.")
                        return False, []
                    with wave.open(wav_path, "r") as w:
                        total_dur = w.getnframes() / float(w.getframerate())
                    _runtime_get_logger().log("📢 [TEN VAD 선분할] 음성 섹터 분리가 완료되었습니다.")
                    for i, ts in enumerate(timestamps):
                        sm, ss = divmod(ts["start"], 60)
                        _runtime_get_logger().log(f"  [{int(sm):02d}:{ss:05.2f}] 음성섹터{i+1} 확보 완료")
                    grouped = self._build_grouped_chunks(
                        timestamps,
                        total_dur,
                        max_chunk_dur=max(10.0, float(s.get("ff_chunk", _CHUNK_DURATION))),
                        margin=1.0,
                        gap_merge_limit=3.0,
                        settings=s,
                    )
                    grouped = self._split_grouped_chunks_at_hard_cuts(grouped, target_start_sec, target_end_sec)
                    self._write_grouped_chunks_parallel(wav_path, chunk_dir, grouped)
                    try:
                        with open(os.path.join(chunk_dir, "vad_strict.json"), "w", encoding="utf-8") as f:
                            json.dump(timestamps, f)
                    except Exception:
                        pass
                    return True, timestamps
                _runtime_get_logger().log("  ⚠️ TEN VAD 결과가 없어 Silero VAD로 재시도합니다")
                vad_model = "silero"

            import torch
            if not self._vad_loaded:
                self._vad_model, self._vad_utils = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                    onnx=False
                )
                self._vad_loaded = True

            model = self._vad_model
            utils = self._vad_utils
            (get_speech_timestamps, _, read_audio, _, _) = utils

            v_thresh = float(effective_s.get("vad_threshold", 0.5))
            v_min_sp = int(float(effective_s.get("vad_min_speech", 0.25)) * 1000)
            v_min_sil = int(float(effective_s.get("vad_min_silence", 2.0)) * 1000)
            v_pad_ms = int(float(effective_s.get("vad_speech_pad", 0.2)) * 1000)
            v_window = int(effective_s.get("vad_window_size", 512) or 512)

            audio_data = read_audio(wav_path)
            raw_ts = get_speech_timestamps(
                audio_data, model, sampling_rate=16000, threshold=v_thresh,
                min_speech_duration_ms=v_min_sp, min_silence_duration_ms=v_min_sil,
                speech_pad_ms=v_pad_ms, window_size_samples=v_window
            )
            stats = None
            if not raw_ts:
                stats = self._wav_activity_stats(wav_path)
                if self._has_force_split_activity(stats, s):
                    retry_profiles = [
                        (
                            max(0.30, min(0.40, v_thresh - 0.12 if v_thresh > 0.45 else v_thresh * 0.82)),
                            max(120, min(v_min_sp, 160)),
                            max(450, min(v_min_sil, 600)),
                            max(v_pad_ms, 200),
                        ),
                        (
                            max(0.24, min(0.34, v_thresh * 0.62)),
                            max(100, min(v_min_sp, 130)),
                            max(320, min(v_min_sil, 450)),
                            max(v_pad_ms, 250),
                        ),
                        (
                            max(0.20, min(0.28, v_thresh * 0.50)),
                            max(90, min(v_min_sp, 110)),
                            max(240, min(v_min_sil, 340)),
                            max(v_pad_ms, 300),
                        ),
                    ]
                    prev_thresh, prev_min_sp, prev_min_sil = v_thresh, v_min_sp, v_min_sil
                    for retry_idx, (retry_thresh, retry_min_sp, retry_min_sil, retry_pad_ms) in enumerate(retry_profiles, 1):
                        _runtime_get_logger().log(
                            f"  └ 🔁 VAD {retry_idx}차 무검출: 오디오 에너지가 있어 민감도 낮춰 재시도 "
                            f"(threshold {prev_thresh:.2f}→{retry_thresh:.2f}, "
                            f"min speech {prev_min_sp}→{retry_min_sp}ms, "
                            f"min silence {prev_min_sil}→{retry_min_sil}ms, "
                            f"peak {stats['peak']:.4f}, rms {stats['rms']:.4f})"
                        )
                        raw_ts = get_speech_timestamps(
                            audio_data, model, sampling_rate=16000, threshold=retry_thresh,
                            min_speech_duration_ms=retry_min_sp, min_silence_duration_ms=retry_min_sil,
                            speech_pad_ms=retry_pad_ms, window_size_samples=v_window
                        )
                        if raw_ts:
                            if self._vad_retry_timestamps_are_usable(raw_ts, 16000, stats.get("duration", 0.0)):
                                _runtime_get_logger().log(f"  └ ✅ VAD 재시도 {retry_idx}회차로 음성 섹터 {len(raw_ts)}개 확보")
                                break
                            _runtime_get_logger().log(
                                f"  └ ⚠️ VAD 재시도 {retry_idx}회차 결과가 너무 잘게 잡혀 폐기합니다 "
                                f"({len(raw_ts)}개 섹터)"
                            )
                            raw_ts = []
                        prev_thresh, prev_min_sp, prev_min_sil = retry_thresh, retry_min_sp, retry_min_sil
                else:
                    _runtime_get_logger().log(
                        "  └ 🔇 VAD 1차 무검출: 오디오 에너지도 낮아 민감도 재시도를 생략합니다 "
                        f"(threshold {v_thresh:.2f}, peak {stats['peak']:.4f}, rms {stats['rms']:.4f})"
                    )
            timestamps = [
                {
                    "start": t["start"] / 16000.0,
                    "end": t["end"] / 16000.0,
                    "source": vad_model,
                    "review_vad": bool(vad_cfg["review_vad_before_stt_enabled"]),
                    "speech_pad_sec": round(v_pad_ms / 1000.0, 3),
                    "min_silence_sec": round(v_min_sil / 1000.0, 3),
                }
                for t in raw_ts
            ]

            # 구간 필터링 및 단일 세그먼트 보호 로직
            if target_start_sec > 0.0 or target_end_sec is not None:
                end_limit_log = target_end_sec if target_end_sec is not None else 99999.0
                _runtime_get_logger().log(f"\n🎯 [구간 정찰] {target_start_sec:.1f}초 ~ {end_limit_log if end_limit_log < 90000 else '끝'} 구간의 음성을 분석합니다.")

                filtered_timestamps = []
                end_limit = target_end_sec if target_end_sec is not None else 99999.0
                for t in timestamps:
                    if t["start"] >= end_limit: continue
                    if t["end"] <= target_start_sec: continue

                    if is_single_segment:
                        t["start"] = max(target_start_sec, t["start"])
                        t["end"] = min(end_limit, t["end"])
                    else:
                        t["start"] = max(target_start_sec, t["start"])

                    filtered_timestamps.append(t)
                timestamps = filtered_timestamps

            if not timestamps:
                _runtime_get_logger().log("⚠️ 해당 구간에서 유효한 음성 신호를 찾지 못했습니다.")
                return False, []

            with wave.open(wav_path, "r") as w:
                total_dur = w.getnframes() / float(w.getframerate())

            if timestamps and timestamps[0]["start"] < 3.0:
                timestamps[0]["start"] = 0.0

            _runtime_get_logger().log("📢 [VAD 선분할] 음성 섹터 분리가 완료되었습니다.")
            for i, ts in enumerate(timestamps):
                sm, ss = divmod(ts["start"], 60)
                em, es = divmod(ts["end"], 60)
                _runtime_get_logger().log(f"  [{int(sm):02d}:{ss:05.2f}] 음성섹터{i+1} 확보 완료")

            grouped = self._build_grouped_chunks(
                timestamps,
                total_dur,
                max_chunk_dur=max(10.0, float(s.get("ff_chunk", _CHUNK_DURATION))),
                margin=1.0,
                gap_merge_limit=3.0,
                settings=s
            )
            grouped = self._split_grouped_chunks_at_hard_cuts(grouped, target_start_sec, target_end_sec)
            self._write_grouped_chunks_parallel(wav_path, chunk_dir, grouped)

            try:
                with open(os.path.join(chunk_dir, "vad_strict.json"), "w", encoding="utf-8") as f:
                    json.dump(timestamps, f)
            except: pass

            return True, timestamps

        except Exception as e:
            _runtime_get_logger().log(f"⚠️ VAD 오류: {e}")
            return False, []
        finally:
            release = getattr(self, "release_vad_runtime_models", None)
            if callable(release) and requested_vad_model != "none":
                release(log_context="VAD 선분할")
