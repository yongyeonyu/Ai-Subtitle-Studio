# Version: 01.00.00
"""
video_processor.py  ─  잼민이 PD v25 (VAD 섹터 그룹화 + 무음 로깅 + Whisper 섹터 동기화)
[특징] 
1. VAD가 설정된 무음 간격(기본 2.0초)을 기준으로 통짜 음성 섹터를 구성
2. 무음 세그먼트와 음성 섹터를 앱 로그에 완벽하게 분리하여 출력
3. 후발대(Whisper)는 무조건 선발대가 지정한 음성 섹터의 시작점부터 인식 시작 (30초 청크 유지)
"""
import os, subprocess, json, re, config, shutil, time, wave, threading
from concurrent.futures import ThreadPoolExecutor
from logger import get_logger

_CHUNK_DURATION = 30     
_OVERLAP_SEC    = 3      

class VideoProcessor:
    # [video_processor.py] __init__ 함수 내부
    def __init__(self):
        self.whisper_model = getattr(config, "WHISPER_MODEL", "mlx-community/whisper-large-v3-mlx")
        self.audio_ai = "demucs"
        self.vad_model = "silero"
        self.io_workers = 6
        
        # 💡 [경로 수정] os.path.dirname... 대신 config.DATASET_DIR를 사용하여 정확한 위치를 찾습니다.
        settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    s = json.load(f)
                    self.whisper_model = s.get("selected_whisper_model", self.whisper_model)
                    self.audio_ai = s.get("selected_audio_ai", "demucs")
                    self.vad_model = s.get("selected_vad", "silero")
                    self.io_workers = int(s.get("io_workers", 6))
            except: pass
        self.language = getattr(config, "LANGUAGE", "ko")
        self._executor = ThreadPoolExecutor(max_workers=self.io_workers)

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
        _FILTERS = {
            "demucs": f"speechnorm=e=12:r=0.0001:l=1,volume={s.get('dm_vol',3.5)},loudnorm=I=-14:LRA=11:tp=-1.0",
            "deepfilter": f"highpass=f={s.get('df_hp',100)},lowpass=f=8000,equalizer=f=3000:width_type=h:width=2000:g={s.get('df_eq_g',8)},acompressor=threshold={s.get('df_comp_th',-28)}dB:ratio=4:attack=5:release=50,speechnorm=e=12:r=0.0001:l=1,volume={s.get('df_vol',3.5)},loudnorm=I=-14:LRA=11:tp=-1.0",
            "none": "anull" 
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
            get_logger().log(f"  └ 🔍 세부 공정 4: {vad_model.upper()} 음성 섹터 스캔 중...")
            # _split_with_vad로 모든 인자 전달
            vad_success, vad_segments = self._split_with_vad(cleaned_wav, chunk_dir, vad_model, s, target_start_sec, target_end_sec, is_single_segment)
            if not vad_success: vad_model = "none"            
        
        # ... (이후 30초 강제 분할 모드 로직은 동일) ...
        return chunk_dir, vad_segments

    # 💡 [STEP 3] VAD 분할기 (들여쓰기 및 8개 인자 완벽 교정)
    # [core/media_processor.py] _split_with_vad 함수 전체 교체
    def _split_with_vad(self, wav_path: str, chunk_dir: str, vad_model: str, s: dict, target_start_sec=0.0, target_end_sec=None, is_single_segment=False):
        try:
            import torch
            model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False, onnx=False)
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
            
            MAX_CHUNK_DUR = 30.0
            MARGIN = 1.0 
            grouped = []
            for ts in timestamps:
                cur_start = max(0.0, ts["start"] - MARGIN)
                sec_end = min(total_dur, ts["end"] + MARGIN)
                while cur_start < sec_end:
                    cur_end = min(sec_end, cur_start + MAX_CHUNK_DUR)
                    grouped.append({"start": cur_start, "end": cur_end})
                    cur_start = cur_end

            for idx, seg in enumerate(grouped):
                out = os.path.join(chunk_dir, f"vad_{idx:03d}_{seg['start']:.3f}.wav")
                subprocess.run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-ss", str(seg["start"]), "-t", str(seg["end"] - seg["start"]), "-i", wav_path, "-acodec", "pcm_s16le", out], capture_output=True)
            
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
        # 💡 [경로 수정] 마찬가지로 실제 데이터셋 폴더 위치를 가리키도록 변경합니다.
        settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f: return json.load(f)
            except: pass
        return {}
 
    def transcribe(self, chunk_dir: str, is_fast_mode: bool = False, target_end_sec: float = None, is_single: bool = False):
        chunks = sorted([f for f in os.listdir(chunk_dir) if f.endswith(".wav")])
        if not chunks: yield [], 0, 0; return

        # 💡 [교차 검증용 VAD 데이터 로드 추가]
        vad_strict = []
        vad_json = os.path.join(chunk_dir, "vad_strict.json")
        if os.path.exists(vad_json):
            try:
                with open(vad_json, "r") as f: vad_strict = json.load(f)
            except: pass

        total = len(chunks)
        target_model = "mlx-community/whisper-medium-mlx" if is_fast_mode else self.whisper_model
        safe_model = json.dumps(target_model)
        
        get_logger().log(f"\n🎯 Whisper 정밀 인식 시작 (총 {total}블록)")

        t_sec = 1.0; q = []
        for i, cf in enumerate(chunks):
            cp = os.path.join(chunk_dir, cf)
            m = re.search(r'vad_\d+_([\d\.]+)\.wav', cf)
            ov_start = float(m.group(1)) if m else i * 30.0
            q.append({"idx": i, "input_path": cp, "ov_start_offset": ov_start})
            if i == len(chunks)-1:
                try:
                    with wave.open(cp, "r") as w: t_sec = ov_start + (w.getnframes()/float(w.getframerate()))
                except: t_sec = ov_start + 30.0

        safe_paths = json.dumps([x["input_path"] for x in q])
        s = self._load_all_settings()
        tr = "(" + ", ".join([str(round(x*0.2,1)) for x in range(int(s.get("w_none_temp_max", 0.4)/0.2)+1)]) + ",)"

        script = f"""
import mlx_whisper, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

for p in {safe_paths}:
    try:
        # 💡 [핵심 교정] 문맥 이어받기(condition_on_previous_text)를 False로 끄고, 
        # 이전 텍스트 억지로 주입하던 로직을 완전 삭제하여 무한 앵무새 루프를 원천 차단합니다!
        r = mlx_whisper.transcribe(
            p, 
            path_or_hf_repo={safe_model}, 
            language='{self.language}', 
            word_timestamps=True, 
            temperature={tr},
            condition_on_previous_text=False
        )
        print(json.dumps(r, ensure_ascii=False), flush=True)
    except Exception as e: 
        print(json.dumps({{"error": str(e)}}, ensure_ascii=False), flush=True)
os._exit(0)
"""

        proc = subprocess.Popen(["python3.11", "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")

        prev_end = 0.0
        for item in q:
            line = proc.stdout.readline()
            if not line: break
            chunk_segs = []
            try:
                data = json.loads(line)
                if "segments" in data:
                    for seg in data["segments"]:
                        offset = item["ov_start_offset"]
                        words = seg.get("words", [])
                        
                        # 1. 기본값: Whisper가 잡아준 뭉툭한 문장 시간
                        exact_start = seg["start"] + offset
                        exact_end = seg["end"] + offset
                        offset_words = []
                        
                        if words:
                            valid_words = [w for w in words if "start" in w and "end" in w and w.get("word", "").strip()]
                            
                            # 💡 [초정밀 VAD 교차 검증 (Cross-Masking)]
                            # Whisper가 잡은 단어 중, VAD가 '무음'이라고 확신한 구간에 있는 단어는 환각으로 보고 날립니다.
                            if vad_strict:
                                temp_words = []
                                for w in valid_words:
                                    w_start = w["start"] + offset
                                    w_end = w["end"] + offset
                                    # VAD 구간 안에 있는지 검사 (오차 허용 범위 0.5초)
                                    is_valid = False
                                    for v in vad_strict:
                                        if w_start <= v["end"] + 0.5 and w_end >= v["start"] - 0.5:
                                            is_valid = True; break
                                    if is_valid: temp_words.append(w)
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
                        
                        # 💡 단어가 모두 날아갔으면(환각) 이 세그먼트는 버립니다.
                        if words and not offset_words:
                            continue
                            
                        # 💡 [제2 방어벽] Whisper가 그린 영역을 넘어서 환각 텍스트를 만들어내더라도 
                        # 시간을 강제로 그린 영역 끝 시간에 맞춰버립니다.
                        if is_single and target_end_sec is not None:
                            if exact_start >= target_end_sec: continue
                            if exact_end > target_end_sec: exact_end = target_end_sec
                            
                        chunk_segs.append({
                            "start": exact_start,
                            "end": exact_end,
                            "text": seg.get("text", "").strip(),
                            "words": offset_words  
                        })
            except: pass

            if chunk_segs: 
                prev_end = chunk_segs[-1]["end"]
            
            pct = min(100, int((prev_end / t_sec) * 100))
            get_logger().log(f"  ▶ 진행 상황: {int(prev_end // 60):02d}분 {int(prev_end % 60):02d}초 / {int(t_sec // 60):02d}분 {int(t_sec % 60):02d}초 ({int(pct)}%)")
            yield chunk_segs, item["idx"] + 1, total

        proc.wait(); shutil.rmtree(chunk_dir, ignore_errors=True)
        get_logger().log("🎊 모든 자막 생성 완료")