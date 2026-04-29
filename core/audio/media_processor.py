# Version: 03.00.19
# Phase: PHASE2
"""
media_processor.py  ─  잼민이 PD v25 (VAD 섹터 그룹화 + 무음 로깅 + Whisper 섹터 동기화)
[특징] 
1. VAD가 설정된 무음 간격(기본 2.0초)을 기준으로 통짜 음성 섹터를 구성
2. 무음 세그먼트와 음성 섹터를 앱 로그에 완벽하게 분리하여 출력
3. 후발대(Whisper)는 무조건 선발대가 지정한 음성 섹터의 시작점부터 인식 시작 (30초 청크 유지)
"""
import sys
import os, subprocess, json, re, config, shutil, time, wave, threading
from concurrent.futures import ThreadPoolExecutor
from logger import get_logger

_CHUNK_DURATION = 30
_OVERLAP_SEC = 3.0


def _parse_worker_json_line(line: str):
    line = (line or "").strip()
    if not line or not line.startswith("{"):
        return None
    try:
        return json.loads(line)
    except Exception as e:
        get_logger().log(f"  ⚠️ JSON 파싱 오류: {e}")
        get_logger().log(f"  ⚠️ raw line: {line[:200] if line else 'empty'}")
        return None


class VideoProcessor:
    # [media_processor.py] __init__ 함수 내부
    
    def __init__(self):
        self.whisper_model = getattr(config, "WHISPER_MODEL", "mlx-community/whisper-large-v3-mlx")
        self.audio_ai = "demucs"
        self.vad_model = "silero"
        self.io_workers = max(6, min(12, (os.cpu_count() or 8)))

        settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    s = json.load(f)
                    self.whisper_model = s.get("selected_whisper_model", self.whisper_model)
                    self.audio_ai = s.get("selected_audio_ai", "demucs")
                    self.vad_model = s.get("selected_vad", "silero")
                    self.io_workers = max(1, int(s.get("io_workers", self.io_workers)))
            except Exception:
                pass

        self.language = getattr(config, "LANGUAGE", "ko")
        self._executor = ThreadPoolExecutor(max_workers=self.io_workers)

        # 런타임 핸들
        self._whisper_proc = None
        self._whisper_runner_proc = None
        self._whisper_lock = threading.Lock()

        self._vad_loaded = False
        self._vad_model = None
        self._vad_utils = None

    # 💡 파라미터에 target_start_sec와 target_end_sec 추가
    # 💡 1. 메인 파이프라인 (불필요한 중복 로직 싹 걷어내고 아주 깔끔해졌습니다)
    # 💡 [STEP 1] 메인 파이프라인 (is_single_segment 파라미터 추가)
    def process_video(self, media_path, ui_callback, min_spk=1, max_spk=1, target_start_sec=0.0, target_end_sec=None, is_single_segment=False):
        import time

        # 오디오 추출 단계로 is_single_segment 전달
        chunk_dir, vad_segments = self.extract_audio(media_path, target_start_sec, target_end_sec, is_single_segment)
        
        if not os.path.exists(chunk_dir) or not os.listdir(chunk_dir):
            yield [], 1, 1; return

        # Whisper 단계로 is_single_segment 및 target_end_sec 전달
        for chunk_segs, idx, total in self.transcribe(chunk_dir, is_fast_mode=False, target_end_sec=target_end_sec, is_single=is_single_segment):
            yield chunk_segs, idx, total

    # 💡 [STEP 2] 오디오 추출 엔진 (is_single_segment 파라미터 추가)
    def extract_audio(self, video_path: str, target_start_sec=0.0, target_end_sec=None, is_single_segment=False):
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        s = self._load_all_settings()
        audio_ai = s.get("selected_audio_ai", "demucs")
        use_basic = s.get("use_basic_filter", True)
        vad_model = s.get("selected_vad", "silero")

        master_filter = f"highpass=f={s.get('none_hp',200)},lowpass=f={s.get('none_lp',3000)},afftdn=nf={s.get('none_nf',-25)},loudnorm=I={s.get('none_target',-14)}"

        dm_vol = s.get("dm_vol", s.get("none_vol", 3.5))
        df_vol = s.get("df_vol", 3.5)

        _FILTERS = {
            "demucs": (
                f"speechnorm=e=12:r=0.0001:l=1,"
                f"volume={dm_vol},"
                f"loudnorm=I=-14:LRA=11:tp=-1.0"
            ),
            "deepfilter": (
                f"highpass=f={s.get('df_hp',100)},lowpass=f=8000,"
                f"equalizer=f=3000:width_type=h:width=2000:g={s.get('df_eq_g',8)},"
                f"acompressor=threshold={s.get('df_comp_th',-28)}dB:ratio=4:attack=5:release=50,"
                f"speechnorm=e=12:r=0.0001:l=1,"
                f"volume={df_vol},"
                f"loudnorm=I=-14:LRA=11:tp=-1.0"
            ),
            "none": "anull",
        }
        active_filter = _FILTERS.get(audio_ai, "anull")

        base_name = os.path.splitext(os.path.basename(video_path))[0]
        chunk_dir = os.path.join(config.OUTPUT_DIR, f"{base_name}_chunks")
        raw_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_raw.wav")
        cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
        
        is_partial = target_start_sec > 0.0 or target_end_sec is not None
        
        shutil.rmtree(chunk_dir, ignore_errors=True)
        os.makedirs(chunk_dir, exist_ok=True)

        is_valid_cache = False
        if os.path.exists(cleaned_wav) and os.path.getsize(cleaned_wav) > 1024 * 100:
            is_valid_cache = True

        if is_partial and is_valid_cache:
            get_logger().log("  └ ♻️ [초고속 모드] 정상적으로 분리된 오디오 캐시를 발견하여 추출을 건너뜜")
        else:
            get_logger().log("  └ 📥 세부 공정 1: 오디오 추출 및 필터 적용 중...")
            subprocess.run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", video_path, "-vn", "-ac", "1", "-ar", "48000", "-af", master_filter, "-acodec", "pcm_s16le", raw_wav] if use_basic else ["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", video_path, "-vn", "-ac", "1", "-ar", "48000", "-acodec", "pcm_s16le", raw_wav], capture_output=True)
                
            ai_wav = raw_wav
            if audio_ai == "demucs":
                get_logger().log("  └ 🤖 세부 공정 2: Demucs 보컬 정밀 분리 중...")
                subprocess.run(["demucs", "--two-stems=vocals", raw_wav, "-o", config.OUTPUT_DIR], capture_output=True)
                demucs_out = os.path.join(config.OUTPUT_DIR, "htdemucs", f"{base_name}_raw", "vocals.wav")
                if os.path.exists(demucs_out): ai_wav = demucs_out

            get_logger().log("  └ 🔊 세부 공정 3: 음량 평탄화 및 포맷 변환 중...")
            subprocess.run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", ai_wav, "-ac", "1", "-ar", "16000", "-af", active_filter, "-acodec", "pcm_s16le", cleaned_wav], capture_output=True)
            if os.path.exists(raw_wav): os.remove(raw_wav)

        vad_segments = []
        if vad_model != "none":
            import hashlib

            # ✅ VAD 캐시 경로
            vad_cache_path = os.path.join(
                config.OUTPUT_DIR,
                f"{base_name}_vad_cache.json"
            )

            # ✅ cleaned_wav의 수정 시간 + 크기로 캐시 유효성 판단
            cache_valid = False
            if os.path.exists(vad_cache_path) and os.path.exists(cleaned_wav):
                try:
                    with open(vad_cache_path, "r") as f:
                        cache_data = json.load(f)
                    wav_stat = os.stat(cleaned_wav)
                    if (cache_data.get("wav_mtime") == wav_stat.st_mtime
                            and cache_data.get("wav_size") == wav_stat.st_size
                            and cache_data.get("vad_model") == vad_model
                            and not is_partial):
                        cache_valid = True
                except Exception:
                    pass

            if cache_valid:
                get_logger().log(f"  └ ♻️ [VAD 캐시] 이전 분석 결과를 재사용합니다.")
                vad_segments = cache_data.get("timestamps", [])

                import wave
                with wave.open(cleaned_wav, "r") as w:
                    total_dur = w.getnframes() / float(w.getframerate())

                grouped = self._build_grouped_chunks(vad_segments, total_dur, settings=s)
                self._write_grouped_chunks_parallel(cleaned_wav, chunk_dir, grouped)

                try:
                    with open(os.path.join(chunk_dir, "vad_strict.json"), "w") as f:
                        json.dump(vad_segments, f)
                except Exception:
                    pass

                vad_success = True
                
            else:
                # ✅ VAD 새로 실행
                get_logger().log(f"  └ 🔍 세부 공정 4: {vad_model.upper()} 음성 섹터 스캔 중...")
                vad_success, vad_segments = self._split_with_vad(
                    cleaned_wav, chunk_dir, vad_model, s,
                    target_start_sec, target_end_sec, is_single_segment
                )

                # ✅ 캐시 저장
                if vad_success and not is_partial:
                    try:
                        wav_stat = os.stat(cleaned_wav)
                        cache_obj = {
                            "wav_mtime": wav_stat.st_mtime,
                            "wav_size": wav_stat.st_size,
                            "vad_model": vad_model,
                            "timestamps": vad_segments
                        }
                        with open(vad_cache_path, "w") as f:
                            json.dump(cache_obj, f)
                    except Exception:
                        pass

            if not vad_success:
                vad_model = "none"

        # VAD=none 또는 VAD 실패 시: 30초 단위 강제 분할
        if vad_model == "none":
            import wave
            existing_chunks = [f for f in os.listdir(chunk_dir) if f.endswith('.wav')]
            if not existing_chunks and os.path.exists(cleaned_wav):
                get_logger().log("  └ 🔪 VAD 없음: 30초 단위 강제 분할...")
                try:
                    with wave.open(cleaned_wav, 'r') as wf:
                        total_dur = wf.getnframes() / float(wf.getframerate())
                    chunk_sec = max(10.0, float(s.get("ff_chunk", _CHUNK_DURATION)))
                    overlap_sec = self._chunk_overlap_sec(s)
                    grouped = self._split_range_with_overlap(0.0, total_dur, chunk_sec, overlap_sec)
                    self._write_grouped_chunks_parallel(cleaned_wav, chunk_dir, grouped)
                    get_logger().log(f"    → {len(grouped)}개 청크 병렬 생성 완료 (overlap {overlap_sec:.1f}초, 총 {total_dur:.1f}초)")
                except Exception as e:
                    get_logger().log(f"  ⚠️ 강제 분할 실패: {e}")

        return chunk_dir, vad_segments

    # 💡 [STEP 3] VAD 분할기 (들여쓰기 및 8개 인자 완벽 교정)
    # [core/media_processor.py] _split_with_vad 함수 전체 교체
    def _split_with_vad(self, wav_path: str, chunk_dir: str, vad_model: str, s: dict, target_start_sec=0.0, target_end_sec=None, is_single_segment=False):
        try:
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
            
            v_thresh = float(s.get("vad_threshold", 0.5))
            v_min_sp = int(float(s.get("vad_min_speech", 0.25)) * 1000)
            v_min_sil = int(float(s.get("vad_min_silence", 2.0)) * 1000)
            v_pad_ms = int(float(s.get("vad_speech_pad", 0.2)) * 1000) 
            
            audio_data = read_audio(wav_path)
            raw_ts = get_speech_timestamps(
                audio_data, model, sampling_rate=16000, threshold=v_thresh, 
                min_speech_duration_ms=v_min_sp, min_silence_duration_ms=v_min_sil,
                speech_pad_ms=v_pad_ms, window_size_samples=512
            )
            timestamps = [{"start": t["start"]/16000.0, "end": t["end"]/16000.0} for t in raw_ts]
            
            # 구간 필터링 및 단일 세그먼트 보호 로직
            if target_start_sec > 0.0 or target_end_sec is not None:
                end_limit_log = target_end_sec if target_end_sec is not None else 99999.0
                get_logger().log(f"\n🎯 [구간 정찰] {target_start_sec:.1f}초 ~ {end_limit_log if end_limit_log < 90000 else '끝'} 구간의 음성을 분석합니다.")
                
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
                get_logger().log("⚠️ 해당 구간에서 유효한 음성 신호를 찾지 못했습니다.")
                return False, []

            with wave.open(wav_path, "r") as w: 
                total_dur = w.getnframes() / float(w.getframerate())
                
            if timestamps and timestamps[0]["start"] < 3.0: 
                timestamps[0]["start"] = 0.0

            get_logger().log("📢 선발대가 요청하신 구간의 음성 섹터를 완벽하게 분리했습니다!")
            for i, ts in enumerate(timestamps):
                sm, ss = divmod(ts["start"], 60)
                em, es = divmod(ts["end"], 60)
                get_logger().log(f"  [{int(sm):02d}:{ss:05.2f}] 음성섹터{i+1} 확보 완료")
            
            grouped = self._build_grouped_chunks(
                timestamps,
                total_dur,
                max_chunk_dur=max(10.0, float(s.get("ff_chunk", _CHUNK_DURATION))),
                margin=1.0,
                gap_merge_limit=3.0,
                settings=s
            )
            self._write_grouped_chunks_parallel(wav_path, chunk_dir, grouped)

            try:
                with open(os.path.join(chunk_dir, "vad_strict.json"), "w") as f:
                    json.dump(timestamps, f)
            except: pass

            return True, timestamps

        except Exception as e:
            get_logger().log(f"⚠️ VAD 오류: {e}")
            return False, []

    def __del__(self):
        try: self._executor.shutdown(wait=False)
        except: pass

    def _load_all_settings(self):
        """user_settings.json 로드 (오류 시 로그 남김). fast-mode override 지원."""
        settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")

        if not os.path.exists(settings_path):
            data = {}
        else:
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    get_logger().log("⚠️ user_settings.json 형식 오류: dict 아님")
                    data = {}
            except Exception as e:
                get_logger().log(f"⚠️ user_settings.json 로드 실패: {e}")
                data = {}

        # 빠른모드 오버라이드: _fast_mode_overrides가 있으면 적용
        overrides = getattr(self, '_fast_mode_overrides', None)
        if overrides and isinstance(overrides, dict):
            data.update(overrides)
        return data

    def clear_fast_mode_overrides(self):
        """빠른모드 오버라이드 제거 — 품질모드/멀티클립 진입 시 호출"""
        self._fast_mode_overrides = None

    def transcribe(self, chunk_dir: str, is_fast_mode: bool = False, target_end_sec: float = None, is_single: bool = False):
        chunks = sorted([f for f in os.listdir(chunk_dir) if f.endswith(".wav")])
        if not chunks:
            yield [], 0, 0
            return

        vad_strict = []
        vad_json = os.path.join(chunk_dir, "vad_strict.json")
        if os.path.exists(vad_json):
            try:
                with open(vad_json, "r") as f:
                    vad_strict = json.load(f)
            except Exception:
                pass

        total = len(chunks)
        _s = self._load_all_settings()
        target_model = _s.get("selected_whisper_model", self.whisper_model)
        get_logger().log(f"\n🎯 Whisper 인식 시작 (총 {total}블록, 모델: {target_model.split(chr(47))[-1]})")

        t_sec = 1.0
        q = []
        for i, cf in enumerate(chunks):
            cp = os.path.join(chunk_dir, cf)
            m = re.search(r'vad_\d+_([\d\.]+)\.wav', cf)
            ov_start = float(m.group(1)) if m else i * 30.0
            q.append({
                "idx": i,
                "input_path": cp,
                "ov_start_offset": ov_start
            })
            if i == len(chunks) - 1:
                try:
                    with wave.open(cp, "r") as w:
                        t_sec = ov_start + (w.getnframes() / float(w.getframerate()))
                except Exception:
                    t_sec = ov_start + 30.0

        safe_paths = [x["input_path"] for x in q]
        s = self._load_all_settings()
        temp_max = float(s.get("w_none_temp_max", 0.4))
        temperature_values = [round(x * 0.2, 1) for x in range(int(temp_max / 0.2) + 1)]
        temperature_tuple = "(" + ", ".join(str(x) for x in temperature_values) + ",)"

        import config as _cfg

        mac_task_id = None
        if _cfg.IS_MAC:
            from core.audio.whisper_mlx import ensure_worker, submit_task

            with self._whisper_lock:
                self._whisper_runner_proc = ensure_worker(self._whisper_runner_proc)
                proc = self._whisper_runner_proc
                mac_task_id = submit_task(
                    proc=proc,
                    chunk_paths=safe_paths,
                    model=target_model,
                    language=self.language,
                    temperature_values=temperature_values
                )
        else:
            from core.audio.whisper_faster import run_whisper
            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple
            )
            if proc is None:
                get_logger().log("❌ Whisper 백엔드를 실행할 수 없습니다.")
                return

        self._whisper_proc = proc
        prev_end = 0.0
        had_error = False
        processed_count = 0

        try:
            if _cfg.IS_MAC:
                received = 0
                while received < total:
                    line = proc.stdout.readline()
                    if not line:
                        break

                    data = _parse_worker_json_line(line)
                    if data is None:
                        continue

                    if data.get("task_id") != mac_task_id:
                        continue
                    if data.get("done"):
                        break

                    if data.get("fatal_error") or data.get("error"):
                        had_error = True
                        msg = data.get("fatal_error") or data.get("error") or "unknown whisper worker error"
                        stage = data.get("stage", "worker")
                        get_logger().log(f"  [FAIL] Whisper worker error ({stage}): {msg}")
                        raise RuntimeError(f"whisper_worker_error[{stage}]: {msg}")

                    idx = int(data.get("index", received))
                    item = q[idx]
                    payload = data.get("result") if "result" in data else {"error": data.get("error", "")}
                    chunk_segs = self._parse_whisper_payload(
                        payload,
                        item,
                        vad_strict,
                        target_end_sec=target_end_sec,
                        is_single=is_single
                    )
                    chunk_segs = self._dedupe_overlapping_segments(
                        chunk_segs,
                        previous_end=prev_end,
                        dedup_window=float(s.get("sub_dedup_window", 0.5) or 0.5),
                    )

                    if chunk_segs:
                        prev_end = chunk_segs[-1]["end"]

                    pct = min(100, int((prev_end / t_sec) * 100))
                    get_logger().log(
                        f"  ▶ 진행 상황: {int(prev_end // 60):02d}분 {int(prev_end % 60):02d}초 / "
                        f"{int(t_sec // 60):02d}분 {int(t_sec % 60):02d}초 ({int(pct)}%)"
                    )

                    yield chunk_segs, item["idx"] + 1, total
                    processed_count += 1
                    received += 1

            else:
                for item in q:
                    line = proc.stdout.readline()
                    if not line:
                        break

                    data = _parse_worker_json_line(line)
                    if data is None:
                        continue

                    chunk_segs = self._parse_whisper_payload(
                        data,
                        item,
                        vad_strict,
                        target_end_sec=target_end_sec,
                        is_single=is_single
                    )
                    chunk_segs = self._dedupe_overlapping_segments(
                        chunk_segs,
                        previous_end=prev_end,
                        dedup_window=float(s.get("sub_dedup_window", 0.5) or 0.5),
                    )

                    if chunk_segs:
                        prev_end = chunk_segs[-1]["end"]

                    pct = min(100, int((prev_end / t_sec) * 100))
                    get_logger().log(
                        f"  ▶ 진행 상황: {int(prev_end // 60):02d}분 {int(prev_end % 60):02d}초 / "
                        f"{int(t_sec // 60):02d}분 {int(t_sec % 60):02d}초 ({int(pct)}%)"
                    )
                    yield chunk_segs, item["idx"] + 1, total
                    processed_count += 1

                proc.wait()
                if proc.returncode not in (0, None):
                    had_error = True
                    raise RuntimeError(f"whisper_worker_exit_code={proc.returncode}")
                if processed_count == 0 and total > 0:
                    had_error = True
                    raise RuntimeError("whisper produced 0 chunks")

        finally:
            self._whisper_proc = None
            shutil.rmtree(chunk_dir, ignore_errors=True)
            if had_error:
                get_logger().log("[WARN] Whisper transcription aborted due to worker failure")
            else:
                get_logger().log("[DONE] Whisper transcription completed")

    def stop_transcribe(self):
        try:
            import config as _cfg

            if _cfg.IS_MAC:
                from core.audio.whisper_mlx import stop_worker
                with self._whisper_lock:
                    if self._whisper_runner_proc:
                        stop_worker(self._whisper_runner_proc)
                        self._whisper_runner_proc = None
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


    def _ffmpeg_trim_to_wav(self, src_wav: str, out_wav: str, start_sec: float, duration_sec: float) -> bool:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                "-ss", str(start_sec),
                "-t", str(duration_sec),
                "-i", src_wav,
                "-acodec", "pcm_s16le",
                out_wav,
            ],
            capture_output=True
        )
        return result.returncode == 0 and os.path.exists(out_wav) and os.path.getsize(out_wav) > 0
    
    def _chunk_overlap_sec(self, settings: dict | None = None) -> float:
        settings = settings or {}
        try:
            overlap = float(settings.get("whisper_chunk_overlap_sec", _OVERLAP_SEC))
        except (TypeError, ValueError):
            overlap = _OVERLAP_SEC
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

        max_workers = max(1, min(self.io_workers, len(grouped)))

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

            if words:
                valid_words = [
                    w for w in words
                    if "start" in w and "end" in w and w.get("word", "").strip()
                ]

                if vad_strict:
                    temp_words = []
                    for w in valid_words:
                        w_start = w["start"] + offset
                        w_end = w["end"] + offset
                        is_valid = False
                        for v in vad_strict:
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
                        offset_words.append({
                            "word": w.get("word", ""),
                            "start": w["start"] + offset,
                            "end": w["end"] + offset
                        })

            if words and not offset_words:
                continue

            if is_single and target_end_sec is not None:
                if exact_start >= target_end_sec:
                    continue
                if exact_end > target_end_sec:
                    exact_end = target_end_sec

            chunk_segs.append({
                "start": exact_start,
                "end": exact_end,
                "text": seg.get("text", "").strip(),
                "words": offset_words,
            })

        return chunk_segs

    def _dedupe_overlapping_segments(self, chunk_segs: list[dict], previous_end: float, dedup_window: float = 0.5) -> list[dict]:
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
                new_seg = dict(seg)
                new_seg["words"] = words
                new_seg["start"] = float(words[0].get("start", seg.get("start", previous_end)) or previous_end)
                new_seg["end"] = float(words[-1].get("end", seg.get("end", previous_end)) or previous_end)
                if words and words != seg.get("words"):
                    text = " ".join(str(w.get("word", "") or "").strip() for w in words).strip()
                    if text:
                        new_seg["text"] = text
                cleaned.append(new_seg)
                continue

            exact_end = float(seg.get("end", 0.0) or 0.0)
            if exact_end <= boundary:
                continue
            new_seg = dict(seg)
            new_seg["start"] = max(float(new_seg.get("start", 0.0) or 0.0), previous_end)
            if new_seg["end"] > new_seg["start"]:
                cleaned.append(new_seg)

        return cleaned
    
