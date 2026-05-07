# Version: 03.14.17
# Phase: PHASE2
"""
media_processor.py  ─  잼민이 PD v25 (VAD 섹터 그룹화 + 무음 로깅 + Whisper 섹터 동기화)
[특징] 
1. VAD가 설정된 무음 간격(기본 2.0초)을 기준으로 통짜 음성 섹터를 구성
2. 무음 세그먼트와 음성 섹터를 앱 로그에 완벽하게 분리하여 출력
3. Whisper는 기본적으로 고정 오버랩 청크를 인식하고, VAD는 검수/선택 선분할 신호로만 사용
"""
import json
import hashlib
import os
import shutil
import subprocess
import sys  # noqa: F401 - compatibility hook for runtime/test patching
import threading
import time  # noqa: F401 - compatibility hook for heartbeat tests/runtime patching
from concurrent.futures import ThreadPoolExecutor
from core.audio.audio_presets import apply_audio_preset, auto_audio_settings_only
from core.accuracy_policy import apply_accuracy_first_runtime_settings
from core.settings_profiles import materialize_user_settings
from core.audio.media_processor_audio import VideoProcessorAudioHelpersMixin
from core.audio.media_processor_transcribe import VideoProcessorTranscribeMixin
from core.audio.media_processor_vad import VideoProcessorVadMixin
from core.llm.secure_keys import get_api_key  # noqa: F401 - patched by audio helper tests/runtime hooks
from core.performance import (
    bounded_worker_count,
)
from core.media_fingerprint import media_fingerprint_digest
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.runtime import config
from core.runtime.logger import get_logger
from core.runtime.multi_process import runtime_parallel_worker_plan
from core.subtitle_quality.vad_alignment_checker import (
    review_vad_config,
    review_vad_enabled,
)

_CHUNK_DURATION = 30
_OVERLAP_SEC = 3.0
_VAD_CACHE_VERSION = 3
_AUDIO_CACHE_VERSION = 3


class VideoProcessor(VideoProcessorTranscribeMixin, VideoProcessorAudioHelpersMixin, VideoProcessorVadMixin):
    # [media_processor.py] __init__ 함수 내부
    
    def __init__(self):
        self.whisper_model = getattr(config, "WHISPER_MODEL", "mlx-community/whisper-large-v3-mlx")
        self.audio_ai = "deepfilter"
        self.vad_model = "silero"
        self.io_workers = bounded_worker_count(kind="io")

        settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    s = json.load(f)
                    self.whisper_model = s.get("selected_whisper_model", self.whisper_model)
                    self.audio_ai = s.get("selected_audio_ai", "deepfilter")
                    self.vad_model = s.get("selected_vad", "silero")
                    self.io_workers = bounded_worker_count(s.get("io_workers", self.io_workers), kind="io")
            except Exception:
                pass

        self.language = getattr(config, "LANGUAGE", "ko")
        self._executor = ThreadPoolExecutor(max_workers=self.io_workers)

        # 런타임 핸들
        self._whisper_proc = None
        self._whisper_runner_proc = None
        self._whisper_lock = threading.Lock()
        self._ensemble_child_lock = threading.Lock()

        self._vad_loaded = False
        self._vad_model = None
        self._vad_utils = None
        self.stage_callback = None

    def process_video(
        self,
        media_path,
        ui_callback=None,
        min_spk=1,
        max_spk=1,
        target_start_sec=0.0,
        target_end_sec=None,
        is_single_segment=False,
    ):
        _ = (ui_callback, min_spk, max_spk)

        try:
            # 오디오 추출 단계로 is_single_segment 전달
            chunk_dir, vad_segments = self.extract_audio(media_path, target_start_sec, target_end_sec, is_single_segment)

            if not os.path.exists(chunk_dir) or not os.listdir(chunk_dir):
                yield [], 1, 1; return

            # Whisper 단계로 is_single_segment 및 target_end_sec 전달
            for chunk_segs, idx, total in self.transcribe(chunk_dir, is_fast_mode=False, target_end_sec=target_end_sec, is_single=is_single_segment):
                yield chunk_segs, idx, total
        finally:
            self.release_runtime_models()

    # 💡 오디오 추출/정제 엔진 (is_single_segment 파라미터 추가)
    def extract_audio(
        self,
        video_path: str,
        target_start_sec=0.0,
        target_end_sec=None,
        is_single_segment=False,
        *,
        prefetch_only: bool = False,
    ):
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        s = self._load_all_settings()
        audio_ai = s.get("selected_audio_ai", "deepfilter")
        use_basic = s.get("use_basic_filter", True)
        vad_model = s.get("selected_vad", "silero")

        master_filter = self._build_ffmpeg_preprocess_filter(s)
        active_filter = self._build_audio_cleanup_filter(audio_ai, s)

        audio_paths = self._audio_work_paths(
            video_path,
            target_start_sec=target_start_sec,
            target_end_sec=target_end_sec,
            is_single_segment=is_single_segment,
        )
        base_name = audio_paths["base_name"]
        work_dir = audio_paths["work_dir"]
        chunk_dir = audio_paths["chunk_dir"]
        raw_wav = audio_paths["raw_wav"]
        cleaned_wav = audio_paths["cleaned_wav"]
        cleaned_meta = f"{cleaned_wav}.meta.json"
        os.makedirs(work_dir, exist_ok=True)
        self.last_audio_work_dir = work_dir
        self.last_chunk_dir = chunk_dir
        self.last_raw_wav = raw_wav
        self.last_cleaned_wav = cleaned_wav
        self.last_audio_paths = dict(audio_paths)
        
        is_partial = target_start_sec > 0.0 or target_end_sec is not None
        cache_config = self._audio_cache_config(
            video_path,
            s,
            audio_ai=audio_ai,
            use_basic=use_basic,
            master_filter=master_filter,
            active_filter=active_filter,
        )
        
        shutil.rmtree(chunk_dir, ignore_errors=True)
        os.makedirs(chunk_dir, exist_ok=True)

        vad_pre_split_enabled = bool(s.get("vad_pre_split_enabled", False))
        vad_post_align_enabled = bool(s.get("vad_post_stt_align_enabled", True))
        direct_start, direct_end = self._direct_chunk_span(video_path, target_start_sec, target_end_sec)
        direct_span = max(0.0, direct_end - direct_start)
        if not prefetch_only and self._can_direct_extract_stt_chunks(
            s,
            audio_ai=audio_ai,
            vad_model=vad_model,
            vad_pre_split_enabled=vad_pre_split_enabled,
            vad_post_align_enabled=vad_post_align_enabled,
            span_sec=direct_span,
            is_partial=is_partial,
        ):
            chunk_sec = max(10.0, float(s.get("ff_chunk", _CHUNK_DURATION)))
            overlap_sec = self._chunk_overlap_sec(s)
            grouped = self._split_range_with_overlap(direct_start, direct_end, chunk_sec, overlap_sec)
            grouped = self._split_grouped_chunks_at_hard_cuts(grouped, direct_start, direct_end)
            fused_filter = self._combine_audio_filters(master_filter if use_basic else "anull", active_filter)
            self._notify_stage("⏳ [전처리] FFMPEG 직접 청크 추출 중")
            get_logger().log(
                "  └ [전처리] 전체 WAV 생성을 건너뛰고 원본에서 STT 청크를 직접 추출합니다 "
                f"(청크 {len(grouped)}개, {direct_span:.1f}초)"
            )
            ok = False
            if self._adaptive_audio_routing_enabled(s):
                ok = self._write_adaptive_grouped_chunks_from_media(
                    video_path,
                    chunk_dir,
                    grouped,
                    s,
                    precomputed_vad_segments=None,
                )
            if not ok:
                ok = self._write_grouped_chunks_from_media_parallel(video_path, chunk_dir, grouped, fused_filter, s)
            if ok:
                get_logger().log(f"    → Whisper 청크 {len(grouped)}개 직접 생성 완료 (overlap {overlap_sec:.1f}초)")
                return chunk_dir, []
            get_logger().log("  ⚠️ 직접 청크 추출 실패: 기존 cleaned.wav 전처리 경로로 재시도합니다")
            shutil.rmtree(chunk_dir, ignore_errors=True)
            os.makedirs(chunk_dir, exist_ok=True)

        reuse_audio_cache = bool(s.get("reuse_preprocessed_audio_cache", True))
        is_valid_cache = reuse_audio_cache and self._cleaned_audio_cache_valid(cleaned_wav, cleaned_meta, cache_config)

        if is_valid_cache:
            self._notify_stage("♻️ [전처리] FFMPEG 오디오 캐시 재사용")
            get_logger().log("  └ ♻️ [전처리] 원본/설정이 같은 오디오 캐시를 재사용합니다")
        else:
            self._notify_stage("⏳ [전처리] FFMPEG 오디오 추출 및 기본 필터 적용 중")
            get_logger().log("  └ [전처리] FFMPEG 오디오 추출 및 기본 필터 적용 중...")
            ffmpeg = ffmpeg_binary()

            if self._can_fuse_ffmpeg_preprocess(audio_ai):
                fused_filter = self._combine_audio_filters(master_filter if use_basic else "anull", active_filter)
                self._notify_stage("⏳ [전처리] FFMPEG 단일 패스 오디오 추출/정제 중")
                get_logger().log("  └ [전처리] FFMPEG 단일 패스로 오디오 추출/정제를 처리합니다")
                extract_cmd = [
                    ffmpeg, "-y", "-nostdin", "-loglevel", "error",
                    *self._ffmpeg_parallel_args(s),
                    "-i", video_path,
                    *self._ffmpeg_audio_stream_args(),
                    "-ac", "1", "-ar", "16000",
                    "-af", fused_filter,
                    "-acodec", "pcm_s16le",
                    cleaned_wav,
                ]
                if not self._run_media_command(extract_cmd, label="ffmpeg 음량 평탄화"):
                    return chunk_dir, []
                self._write_cleaned_audio_cache_meta(cleaned_meta, cache_config)
                if os.path.exists(raw_wav):
                    try:
                        os.remove(raw_wav)
                    except Exception:
                        pass
                ai_wav = cleaned_wav
                audio_filter_applied = False
            else:
                extract_cmd = [
                    ffmpeg, "-y", "-nostdin", "-loglevel", "error",
                    *self._ffmpeg_parallel_args(s),
                    "-i", video_path,
                    *self._ffmpeg_audio_stream_args(),
                    "-ac", "1", "-ar", "48000",
                ]
                if use_basic:
                    extract_cmd.extend(["-af", master_filter])
                extract_cmd.extend(["-acodec", "pcm_s16le", raw_wav])
                if not self._run_media_command(extract_cmd, label="ffmpeg 오디오 추출"):
                    return chunk_dir, []

                ai_wav = raw_wav
                audio_filter_applied = False
                if audio_ai == "rnnoise":
                    self._notify_stage("⏳ [음성] RNNoise 빠른 노이즈 제거 중")
                    get_logger().log("  └ [음성] RNNoise 빠른 노이즈 제거 중...")
                    rnnoise_wav = os.path.join(work_dir, f"{base_name}_rnnoise.wav")
                    if self._apply_rnnoise(raw_wav, rnnoise_wav) and os.path.exists(rnnoise_wav):
                        ai_wav = rnnoise_wav
                        audio_filter_applied = True
                elif audio_ai == "resemble_enhance":
                    self._notify_stage("⏳ [음성] Resemble Enhance 음성 향상 중")
                    get_logger().log("  └ [음성] Resemble Enhance 음성 향상 중...")
                    resemble_wav = os.path.join(work_dir, f"{base_name}_resemble.wav")
                    if self._apply_resemble_enhance(raw_wav, resemble_wav) and os.path.exists(resemble_wav):
                        ai_wav = resemble_wav
                        audio_filter_applied = True
                elif audio_ai == "clearvoice":
                    self._notify_stage("⏳ [음성] ClearVoice 음성 향상 중")
                    get_logger().log("  └ [음성] ClearVoice 음성 향상 중...")
                    clearvoice_wav = os.path.join(work_dir, f"{base_name}_clearvoice.wav")
                    if self._apply_clearvoice(raw_wav, clearvoice_wav) and os.path.exists(clearvoice_wav):
                        ai_wav = clearvoice_wav
                        audio_filter_applied = True

                audio_label = self._audio_cleanup_label(audio_ai, audio_filter_applied)
                if audio_ai == "none":
                    self._notify_stage("⏳ [음성] 미사용: FFMPEG 16k 포맷 변환 중")
                    get_logger().log("  └ [음성] 미사용: FFMPEG 16k 포맷 변환 중...")
                else:
                    self._notify_stage(f"⏳ [음성] {audio_label} 정제 및 FFMPEG 16k 변환 중")
                    get_logger().log(f"  └ [음성] {audio_label} 정제 및 FFMPEG 16k 변환 중...")
                if not self._run_media_command(
                    [
                        ffmpeg, "-y", "-nostdin", "-loglevel", "error",
                        *self._ffmpeg_parallel_args(s),
                        "-i", ai_wav,
                        "-ac", "1", "-ar", "16000",
                        "-af", active_filter,
                        "-acodec", "pcm_s16le",
                        cleaned_wav,
                    ],
                    label="ffmpeg 음량 평탄화",
                ):
                    return chunk_dir, []
                self._write_cleaned_audio_cache_meta(cleaned_meta, cache_config)
                if os.path.exists(raw_wav): os.remove(raw_wav)

        if prefetch_only:
            get_logger().log("  └ ♻️ [전처리] 오디오 선추출은 cleaned cache까지만 준비하고 STT 청크는 실제 처리에서 분할합니다")
            return "", []

        vad_segments = []
        vad_requested = vad_model != "none" and vad_pre_split_enabled
        vad_empty_or_failed = False
        if vad_model != "none" and not vad_pre_split_enabled:
            if vad_post_align_enabled and os.path.exists(cleaned_wav):
                self._notify_stage(f"⏳ [VAD] {vad_model.upper()} 음성 위치 재계산 준비 중")
                get_logger().log(
                    f"  └ [VAD 후처리] {vad_model.upper()} 음성 위치 재계산 중 "
                    "(STT 선분할에는 사용하지 않음)"
                )
                vad_segments = self._detect_vad_timestamps(
                    cleaned_wav,
                    vad_model,
                    s,
                    target_start_sec=target_start_sec,
                    target_end_sec=target_end_sec,
                    is_single_segment=is_single_segment,
                    for_post_stt_align=True,
                )
                if vad_segments:
                    try:
                        with open(os.path.join(chunk_dir, "vad_strict.json"), "w", encoding="utf-8") as f:
                            json.dump(vad_segments, f)
                    except Exception:
                        pass
                    get_logger().log(f"  └ [VAD 후처리] 음성 위치 {len(vad_segments)}개 확보")
                else:
                    get_logger().log("  └ [VAD 후처리] 유효한 음성 위치를 찾지 못해 타이밍 보정을 건너뜁니다")
            else:
                get_logger().log(
                    f"  └ [VAD] {vad_model.upper()} 후처리 비활성: STT 선분할에는 사용하지 않습니다"
                )
            vad_model = "none"

        if vad_model != "none":
            # ✅ VAD 캐시 경로
            vad_cache_path = os.path.join(
                work_dir,
                f"{base_name}_vad_cache.json"
            )

            # ✅ cleaned_wav의 수정 시간 + 크기로 캐시 유효성 판단
            cache_valid = False
            if os.path.exists(vad_cache_path) and os.path.exists(cleaned_wav):
                try:
                    with open(vad_cache_path, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                    wav_stat = os.stat(cleaned_wav)
                    cache_config = self._vad_cache_config(s)
                    if (cache_data.get("wav_mtime") == wav_stat.st_mtime
                            and cache_data.get("wav_size") == wav_stat.st_size
                            and cache_data.get("vad_model") == vad_model
                            and cache_data.get("vad_cache_config") == cache_config
                            and not is_partial):
                        cache_valid = True
                except Exception:
                    pass

            if cache_valid:
                self._notify_stage(f"♻️ [VAD] {vad_model.upper()} 캐시 재사용")
                get_logger().log("  └ ♻️ [VAD 캐시] 이전 분석 결과를 재사용합니다.")
                vad_segments = cache_data.get("timestamps", [])

                import wave
                with wave.open(cleaned_wav, "r") as w:
                    total_dur = w.getnframes() / float(w.getframerate())

                grouped = self._build_grouped_chunks(vad_segments, total_dur, settings=s)
                grouped = self._split_grouped_chunks_at_hard_cuts(grouped, target_start_sec, target_end_sec)
                if not self._adaptive_audio_routing_enabled(s) or not self._write_adaptive_grouped_chunks_from_media(
                    video_path,
                    chunk_dir,
                    grouped,
                    s,
                    precomputed_vad_segments=vad_segments,
                ):
                    self._write_grouped_chunks_parallel(cleaned_wav, chunk_dir, grouped)

                try:
                    with open(os.path.join(chunk_dir, "vad_strict.json"), "w", encoding="utf-8") as f:
                        json.dump(vad_segments, f)
                except Exception:
                    pass

                vad_success = True
                
            else:
                # ✅ VAD 새로 실행
                self._notify_stage(f"⏳ [VAD] {vad_model.upper()} 음성 섹터 스캔 중")
                get_logger().log(f"  └ [VAD 선분할] {vad_model.upper()} 음성 섹터 스캔 중...")
                vad_success, vad_segments = self._split_with_vad(
                    cleaned_wav, chunk_dir, vad_model, s,
                    target_start_sec, target_end_sec, is_single_segment
                )
                if vad_success and self._adaptive_audio_routing_enabled(s):
                    routed_grouped = self._grouped_chunks_from_existing_wavs(chunk_dir)
                    if routed_grouped:
                        self._write_adaptive_grouped_chunks_from_media(
                            video_path,
                            chunk_dir,
                            routed_grouped,
                            s,
                            precomputed_vad_segments=vad_segments,
                        )

                # ✅ 캐시 저장
                if vad_success and not is_partial:
                    try:
                        wav_stat = os.stat(cleaned_wav)
                        cache_obj = {
                            "wav_mtime": wav_stat.st_mtime,
                            "wav_size": wav_stat.st_size,
                            "vad_model": vad_model,
                            "vad_cache_config": self._vad_cache_config(s),
                            "timestamps": vad_segments
                        }
                        with open(vad_cache_path, "w", encoding="utf-8") as f:
                            json.dump(cache_obj, f)
                    except Exception:
                        pass

            if not vad_success:
                vad_empty_or_failed = True
                vad_model = "none"

        # VAD=none 또는 VAD 실패 시: 30초 단위 강제 분할
        if vad_model == "none":
            import wave
            existing_chunks = [f for f in os.listdir(chunk_dir) if f.endswith('.wav')]
            if not existing_chunks and os.path.exists(cleaned_wav):
                if vad_requested and vad_empty_or_failed and not s.get("allow_force_split_on_empty_vad", False):
                    stats = self._wav_activity_stats(cleaned_wav)
                    if not self._has_force_split_activity(stats, s):
                        get_logger().log(
                            "  └ [STT 준비] VAD 선분할 결과가 없고 오디오 에너지도 낮아 Whisper 청크 생성을 건너뜁니다 "
                            f"(peak {stats['peak']:.4f}, rms {stats['rms']:.4f}, 총 {stats['duration']:.1f}초)"
                        )
                        return chunk_dir, []
                    get_logger().log(
                        "  └ [STT 준비] VAD 선분할 결과는 없지만 오디오 에너지가 있어 고정 오버랩 청크를 생성합니다 "
                        f"(peak {stats['peak']:.4f}, rms {stats['rms']:.4f}, 총 {stats['duration']:.1f}초)"
                    )
                self._notify_stage("⏳ [STT 준비] Whisper 고정 오버랩 청크 분할 중")
                get_logger().log("  └ [STT 준비] Whisper 고정 오버랩 청크 분할 중...")
                try:
                    with wave.open(cleaned_wav, 'r') as wf:
                        total_dur = wf.getnframes() / float(wf.getframerate())
                    chunk_sec = max(10.0, float(s.get("ff_chunk", _CHUNK_DURATION)))
                    overlap_sec = self._chunk_overlap_sec(s)
                    range_start = max(0.0, float(target_start_sec or 0.0))
                    range_end = float(total_dur or 0.0)
                    if target_end_sec is not None:
                        range_end = min(range_end, max(range_start, float(target_end_sec or range_start)))
                    grouped = self._split_range_with_overlap(range_start, range_end, chunk_sec, overlap_sec)
                    grouped = self._split_grouped_chunks_at_hard_cuts(grouped, range_start, range_end)
                    if not self._adaptive_audio_routing_enabled(s) or not self._write_adaptive_grouped_chunks_from_media(
                        video_path,
                        chunk_dir,
                        grouped,
                        s,
                        precomputed_vad_segments=vad_segments,
                    ):
                        self._write_grouped_chunks_parallel(cleaned_wav, chunk_dir, grouped)
                    get_logger().log(
                        f"    → Whisper 청크 {len(grouped)}개 생성 완료 "
                        f"(overlap {overlap_sec:.1f}초, 범위 {range_start:.1f}s~{range_end:.1f}s)"
                    )
                except Exception as e:
                    get_logger().log(f"  ⚠️ STT 청크 분할 실패: {e}")

        return chunk_dir, vad_segments

    def __del__(self):
        try: self._executor.shutdown(wait=False)
        except: pass

    def _load_all_settings(self):
        """user_settings.json 로드 (오류 시 로그 남김). Legacy override hook 지원."""
        settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")

        data = materialize_user_settings({})
        if not os.path.exists(settings_path):
            pass
        else:
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    get_logger().log("⚠️ user_settings.json 형식 오류: dict 아님")
                    loaded = {}
                data.update(loaded)
            except Exception as e:
                get_logger().log(f"⚠️ user_settings.json 로드 실패: {e}")

        data = apply_accuracy_first_runtime_settings(data)

        preset_name = str(data.get("audio_preset", "") or "")
        if preset_name:
            try:
                data = apply_audio_preset(data, preset_name)
            except Exception as e:
                get_logger().log(f"⚠️ 오디오 프리셋 적용 실패({preset_name}): {e}")
        auto_tune = data.get("audio_preset_auto_tune")
        if isinstance(auto_tune, dict):
            data.update(auto_audio_settings_only(auto_tune))
        runtime_tune = getattr(self, "_auto_audio_tune_overrides", None)
        if isinstance(runtime_tune, dict) and runtime_tune:
            data.update(auto_audio_settings_only(runtime_tune))
        # Legacy override hook kept for compatibility with older batch callers.
        overrides = getattr(self, '_fast_mode_overrides', None)
        if overrides and isinstance(overrides, dict):
            data.update(overrides)
        return data

    def clear_fast_mode_overrides(self):
        """Legacy batch override 제거."""
        self._fast_mode_overrides = None

    def clear_auto_audio_tune_overrides(self):
        self._auto_audio_tune_overrides = None

    def set_auto_audio_tune_overrides(self, overrides: dict | None):
        self._auto_audio_tune_overrides = dict(overrides or {}) if overrides else None

    def _safe_audio_base_name(self, video_path: str) -> str:
        base_name = os.path.splitext(os.path.basename(str(video_path or "")))[0]
        safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in base_name).strip(" ._")
        return (safe or "media")[:96]

    def _audio_work_paths(
        self,
        video_path: str,
        *,
        target_start_sec=0.0,
        target_end_sec=None,
        is_single_segment=False,
    ) -> dict:
        """Return collision-safe audio artifact paths for one concrete media fingerprint."""
        base_name = self._safe_audio_base_name(video_path)
        try:
            source_digest = media_fingerprint_digest(video_path, sample_bytes=512 * 1024, include_samples=True)[:20]
        except Exception:
            source_digest = hashlib.sha1(os.path.abspath(str(video_path or "")).encode("utf-8", errors="ignore")).hexdigest()[:20]

        hard_cuts = []
        for item in list(getattr(self, "hard_cut_boundaries", []) or []):
            try:
                if isinstance(item, dict):
                    sec = float(item.get("timeline_sec", item.get("time", item.get("start", 0.0))) or 0.0)
                else:
                    sec = float(item)
                if sec > 0.0:
                    hard_cuts.append(round(sec, 3))
            except Exception:
                continue

        chunk_payload = {
            "start": round(float(target_start_sec or 0.0), 3),
            "end": None if target_end_sec is None else round(float(target_end_sec or 0.0), 3),
            "single": bool(is_single_segment),
            "hard_cuts": sorted(set(hard_cuts)),
        }
        chunk_digest = hashlib.sha1(
            json.dumps(chunk_payload, ensure_ascii=False, sort_keys=True).encode("utf-8", errors="ignore")
        ).hexdigest()[:12]
        work_dir = os.path.join(config.OUTPUT_DIR, "_audio_fingerprint", f"{base_name}_{source_digest}")
        return {
            "base_name": base_name,
            "source_digest": source_digest,
            "chunk_digest": chunk_digest,
            "work_dir": work_dir,
            "chunk_dir": os.path.join(work_dir, f"{base_name}_{chunk_digest}_chunks"),
            "raw_wav": os.path.join(work_dir, f"{base_name}_raw.wav"),
            "cleaned_wav": os.path.join(work_dir, f"{base_name}_cleaned.wav"),
        }

    def _ffmpeg_trim_to_wav(self, src_wav: str, out_wav: str, start_sec: float, duration_sec: float) -> bool:
        result = subprocess.run(
            [
                ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
                "-ss", str(start_sec),
                "-t", str(duration_sec),
                "-i", src_wav,
                "-acodec", "pcm_s16le",
                out_wav,
            ],
            capture_output=True,
            **hidden_subprocess_kwargs(),
        )
        return result.returncode == 0 and os.path.exists(out_wav) and os.path.getsize(out_wav) > 0
    
    def _chunk_overlap_sec(self, settings: dict | None = None) -> float:
        settings = settings or {}
        try:
            overlap = float(settings.get("whisper_chunk_overlap_sec", _OVERLAP_SEC))
        except (TypeError, ValueError):
            overlap = _OVERLAP_SEC
        try:
            from core.mode_policy import selected_mode_from_settings

            mode = selected_mode_from_settings(settings)
        except Exception:
            mode = str(settings.get("subtitle_mode") or settings.get("simple_operation_mode") or "").strip().lower()
        quality_review_enabled = bool(
            settings.get("subtitle_quality_enabled")
            or settings.get("subtitle_quality_auto_check_after_generate")
        )
        long_quality_overlap = bool(settings.get("subtitle_quality_long_overlap_enabled", mode != "fast"))
        if quality_review_enabled and long_quality_overlap:
            overlap = max(overlap, 3.0)
        return max(0.0, min(8.0, overlap))

    def _split_range_with_overlap(self, start: float, end: float, max_chunk_dur: float, overlap_sec: float) -> list[dict]:
        start = max(0.0, float(start or 0.0))
        end = max(start, float(end or start))
        max_chunk_dur = max(1.0, float(max_chunk_dur or _CHUNK_DURATION))
        overlap_sec = max(0.0, min(float(overlap_sec or 0.0), max_chunk_dur / 2.0))
        if end <= start:
            return []
        if end - start <= max_chunk_dur:
            return [{"start": start, "end": end}]

        grouped = []
        cursor = start
        step = max(0.5, max_chunk_dur - overlap_sec)
        while cursor < end:
            chunk_end = min(end, cursor + max_chunk_dur)
            grouped.append({"start": round(cursor, 3), "end": round(chunk_end, 3)})
            if chunk_end >= end:
                break
            cursor = min(end, cursor + step)
        return grouped

    def _build_grouped_chunks(self, timestamps: list[dict], total_dur: float,
                          max_chunk_dur: float = 30.0, margin: float = 1.0,
                          gap_merge_limit: float = 3.0, settings: dict | None = None) -> list[dict]:
        overlap_sec = self._chunk_overlap_sec(settings)
        if review_vad_enabled(settings):
            cfg = review_vad_config(settings)
            margin = min(float(margin), max(0.0, float(cfg["review_vad_speech_pad_sec"])))
            gap_merge_limit = min(float(gap_merge_limit), max(0.1, float(cfg["review_vad_min_silence_sec"])))
        merged_sectors = []
        for ts in timestamps:
            s = max(0.0, ts["start"] - margin)
            e = min(total_dur, ts["end"] + margin)
            if merged_sectors and (s - merged_sectors[-1]["end"]) <= gap_merge_limit:
                merged_sectors[-1]["end"] = e
            else:
                merged_sectors.append({"start": s, "end": e})

        grouped = []
        for seg in merged_sectors:
            grouped.extend(self._split_range_with_overlap(seg["start"], seg["end"], max_chunk_dur, overlap_sec))

        return grouped
    
    def _write_grouped_chunks_parallel(self, wav_path: str, chunk_dir: str, grouped: list[dict]):
        if not grouped:
            return

        settings = self._load_all_settings()
        workload = len(grouped)
        max_workers, scheduler = runtime_parallel_worker_plan(
            settings=settings,
            task="io",
            workload=workload,
            requested=self.io_workers,
            minimum=1,
            maximum=workload,
            reserve_task="io",
        )
        if scheduler.get("ramp", {}).get("enabled"):
            get_logger().log(f"  🐢 [전처리] 청크 생성 램프업: {max_workers}개 워커")

        def _one(idx_seg):
            idx, seg = idx_seg
            out = os.path.join(chunk_dir, f"vad_{idx:03d}_{seg['start']:.3f}.wav")
            ok = self._ffmpeg_trim_to_wav(
                wav_path,
                out,
                seg["start"],
                seg["end"] - seg["start"]
            )
            return ok, out

        if max_workers == 1:
            for idx, seg in enumerate(grouped):
                _one((idx, seg))
            return

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="chunk-writer") as ex:
            futures = [ex.submit(_one, (idx, seg)) for idx, seg in enumerate(grouped)]
            for fut in futures:
                try:
                    fut.result()
                except Exception as e:
                    get_logger().log(f"⚠️ 청크 생성 실패: {e}")

    def _write_grouped_chunks_from_media_parallel(
        self,
        media_path: str,
        chunk_dir: str,
        grouped: list[dict],
        audio_filter: str,
        settings: dict,
    ) -> bool:
        if not grouped:
            return False

        ffmpeg = ffmpeg_binary()
        workload = len(grouped)
        max_workers, scheduler = runtime_parallel_worker_plan(
            settings=settings,
            task="io",
            workload=workload,
            requested=self.io_workers,
            minimum=1,
            maximum=workload,
            reserve_task="io",
        )
        if scheduler.get("ramp", {}).get("enabled"):
            get_logger().log(f"  🐢 [전처리] 직접 청크 추출 램프업: {max_workers}개 워커")
        progress_lock = threading.Lock()
        done_count = 0
        next_log_pct = 0

        def _one(idx_seg):
            idx, seg = idx_seg
            start = max(0.0, float(seg.get("start", 0.0) or 0.0))
            end = max(start, float(seg.get("end", start) or start))
            out = os.path.join(chunk_dir, f"vad_{idx:03d}_{start:.3f}.wav")
            cmd = [
                ffmpeg, "-y", "-nostdin", "-loglevel", "error",
                *self._ffmpeg_parallel_args(settings),
                "-ss", str(start),
                "-t", str(max(0.001, end - start)),
                "-i", media_path,
                *self._ffmpeg_audio_stream_args(),
                "-ac", "1", "-ar", "16000",
                "-af", audio_filter or "anull",
                "-acodec", "pcm_s16le",
                out,
            ]
            ok = self._run_media_command_no_progress(cmd, label="ffmpeg 직접 청크 추출")
            return ok and os.path.exists(out) and os.path.getsize(out) > 0

        def _mark_progress():
            nonlocal done_count, next_log_pct
            with progress_lock:
                done_count += 1
                pct = min(100, int(round((done_count / len(grouped)) * 100)))
                if pct >= next_log_pct or done_count == len(grouped):
                    next_log_pct = min(100, pct + 10)
                    msg = f"⏳ [전처리] FFMPEG 직접 청크 추출 중 {pct}%"
                    self._notify_stage(msg)
                    get_logger().log(f"  └ [전처리] 직접 청크 추출 진행률 {pct}% ({done_count}/{len(grouped)})")

        failures = 0
        if max_workers == 1:
            for item in enumerate(grouped):
                if not _one(item):
                    failures += 1
                _mark_progress()
        else:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="direct-chunk-writer") as ex:
                futures = [ex.submit(_one, item) for item in enumerate(grouped)]
                for fut in futures:
                    try:
                        if not fut.result():
                            failures += 1
                    except Exception as e:
                        failures += 1
                        get_logger().log(f"⚠️ 직접 청크 생성 실패: {e}")
                    finally:
                        _mark_progress()
        return failures == 0
