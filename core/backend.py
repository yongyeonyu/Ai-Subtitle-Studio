# Version: 01.00.03
"""
core/backend.py
[추가] STEP 6: iCloud 자동 모드 시 백그라운드에서 투명 MOV 자동 렌더링 및 iCloud 업로드 기능 추가
"""

import os, threading, traceback, queue, json, time, subprocess
import config
from logger import get_logger

from .media_processor import VideoProcessor
from .time_history import get_expected_time, add_history
from .utils import load_subtitle_rules

_SENTINEL = object()
_SETTINGS_PATH = os.path.join(config.DATASET_DIR, "user_settings.json")


class CoreBackend:
    def __init__(self, main_window):
        self.ui = main_window
        self.files_to_process = []; self.current_folder = None
        self.min_speakers = 1; self.max_speakers = 1
        self._active = False; self._speaker_map = []
        get_logger().set_ui_callback(main_window.append_log)
        self.video_processor = VideoProcessor()
        self._pipeline_thread = None

        self.total_expected_time = 0.0
        self.pipeline_start_time = 0.0
        self.is_first_start = True

    # ─────────────────────────────────────────────
    # 설정 로드 중앙화 (필수)
    # ─────────────────────────────────────────────
    def _load_settings(self) -> dict:
        try:
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            get_logger().log(f"⚠️ 설정 로드 실패: {e}")
            return {}

    def start_pipeline(self, files, folder=None, is_icloud=False, is_auto_start=False):
        self._active = True
        self.files_to_process = list(files)
        self.current_folder = folder
        self.is_auto_start = is_auto_start

        self.total_expected_time = 0.0
        self.pipeline_start_time = 0.0
        self.is_first_start = True

        if not self.files_to_process: return
        if hasattr(self.ui, 'init_queue_list'):
            self.ui.init_queue_list(self.files_to_process)

        self._video_durations = {}
        threading.Thread(target=self._precalculate_etas, daemon=True, name="eta-calculator").start()
        get_logger().log(f"🚀 총 {len(self.files_to_process)}개 파일 처리 시작!")
        self._pipeline_thread = threading.Thread(target=self._run_all, daemon=True, name="pipeline-main")
        self._pipeline_thread.start()

    def restart_current_file(self):
        if hasattr(self, '_action_state'): self._action_state[0] = "restart"
        if hasattr(self, '_edit_event'): self._edit_event.set()
        self._speaker_map = []

    def stop(self):
        """백엔드 작업을 안전하게 중단한다 (Phase‑1 최종 버전)"""
        self._active = False

        # ✅ Whisper / ML 프로세스는 VideoProcessor가 책임
        try:
            if hasattr(self, "video_processor"):
                self.video_processor.stop_transcribe()
        except Exception as e:
            get_logger().log(f"⚠️ stop_transcribe 실패: {e}")

        # ✅ 대기 중인 editor / pipeline 이벤트 해제
        if hasattr(self, '_edit_event'):
            self._edit_event.set()
        if hasattr(self, '_start_event'):
            self._start_event.set()
            
    def _precalculate_etas(self):
        total_expected_time = 0.0

        s = self._load_settings()
        max_spk  = int(s.get('max_speakers', 1))
        dia_flag = "O" if max_spk > 1 else "X"
        model_key = f"STT:{s.get('selected_whisper_model','기본')}|LLM:{s.get('selected_model','기본')}|DIA:{dia_flag}"

        for i, target_file in enumerate(self.files_to_process):
            try:
                cmd = [
                    'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height,r_frame_rate:format=duration',
                    '-of', 'json', target_file
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5)
                probe  = json.loads(result.stdout)

                fmt          = probe.get('format', {})
                duration_sec = float(fmt.get('duration', 0)) if fmt.get('duration') else 0.0
                streams      = probe.get('streams', [])

                if streams:
                    strm = streams[0]
                    if duration_sec == 0.0:
                        duration_sec = float(strm.get('duration', 0)) if strm.get('duration') else 0.0
                    w, h    = strm.get('width', 0), strm.get('height', 0)
                    fps_str = strm.get('r_frame_rate', '0/0')
                    if '/' in fps_str:
                        n, d = fps_str.split('/')
                        fps = int(n) / int(d) if int(d) != 0 else 0
                    else:
                        fps = float(fps_str)
                    info_txt = f"{w}x{h} ({fps:.2f}fps)" if w and h else "오디오 파일"
                else:
                    info_txt = "오디오 파일"

                self._video_durations[target_file] = duration_sec

                if duration_sec > 0:
                    m_len, s_len = divmod(int(duration_sec), 60)
                    h_len, m_len = divmod(m_len, 60)
                    len_txt = f"{h_len:02d}:{m_len:02d}:{s_len:02d}" if h_len > 0 else f"{m_len:02d}:{s_len:02d}"
                else:
                    len_txt = "-"

                expected_time = get_expected_time(model_key, duration_sec)
                if expected_time > 0:
                    total_expected_time += expected_time

                if hasattr(self.ui, '_sig_update_queue'):
                    self.ui._sig_update_queue.emit(i, "⏳ 대기 중", str(expected_time), info_txt, len_txt)

            except Exception as e:
                # 너무 조용히 삼키지 말고 최소 로그는 남김
                get_logger().log(f"⚠️ ETA 계산 실패: {os.path.basename(target_file)} / {e}")
                if hasattr(self.ui, '_sig_update_queue'):
                    self.ui._sig_update_queue.emit(i, "⏳ 대기 중", "예상불가", "오류", "-")

        self.total_expected_time = total_expected_time

        if total_expected_time > 0 and hasattr(self.ui, '_sig_update_queue_header'):
            t_mins, t_secs = int(total_expected_time // 60), int(total_expected_time % 60)
            t_hours = t_mins // 60
            if t_hours > 0:
                t_mins = t_mins % 60
                total_str = f"{t_hours}시간 {t_mins}분 {t_secs}초"
            else:
                total_str = f"{t_mins}분 {t_secs}초"
            self.ui._sig_update_queue_header.emit(1, len(self.files_to_process), 0, total_str)

    def _run_all(self):
        try:
            for i, target_file in enumerate(self.files_to_process):
                if not self._active:
                    return
                if hasattr(self.ui, '_sig_update_queue'):
                    self.ui._sig_update_queue.emit(i, "⏳ 오디오 추출 중", "", "", "")
                self._process_one(target_file, i)

        except Exception as e:
            if str(e) not in ("USER_PREV", "USER_EXIT"):
                get_logger().log(f"\n❌ 치명적 에러: {e}")
                get_logger().log(traceback.format_exc())

        finally:
            self._active = False
            try:
                if hasattr(self.ui, 'request_show_home'):
                    self.ui.request_show_home()
            except Exception:
                pass

    def _process_one(self, target_file, queue_index: int):
        # 💡 [신규] 기존 파일 백업 로직 추가
        try:
            from .path_manager import get_srt_path
            import datetime
            import shutil
            
            base_path = os.path.splitext(target_file)[0]
            srt_p = get_srt_path(target_file)
            mov_p = f"{base_path}_자막소스.mov"
            backup_dir = os.path.join(os.path.dirname(target_file), "자막백업")
            
            # 기존 파일이 하나라도 있다면 백업 진행
            if os.path.exists(srt_p) or os.path.exists(mov_p):
                if not os.path.exists(backup_dir):
                    os.makedirs(backup_dir, exist_ok=True)
                
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                
                if os.path.exists(srt_p):
                    shutil.copy2(srt_p, os.path.join(backup_dir, f"{os.path.basename(srt_p)}.{timestamp}.bak"))
                if os.path.exists(mov_p):
                    shutil.copy2(mov_p, os.path.join(backup_dir, f"{os.path.basename(mov_p)}.{timestamp}.bak"))
                
                get_logger().log("📦 기존 자막 파일을 '자막백업' 폴더에 안전하게 복사(백업)했습니다.")
                
        except Exception as e:
            get_logger().log(f"⚠️ 백업 중 오류 발생 (무시하고 진행): {e}")

        edit_event  = threading.Event(); start_event = threading.Event()
        self._edit_event  = edit_event; self._start_event = start_event
        final_segments = []; action_state   = ["wait"]
        self._action_state = action_state

        def on_save(segs):
            nonlocal final_segments
            final_segments  = segs; action_state[0] = "next"
            start_event.set(); edit_event.set()

        def on_start():
            if getattr(self, 'is_first_start', True):
                self.pipeline_start_time = time.time(); self.is_first_start = False
            action_state[0] = "start"; start_event.set()

        def on_prev(): action_state[0] = "prev"; start_event.set(); edit_event.set()

        def on_exit(segs):
            nonlocal final_segments
            final_segments  = segs; action_state[0] = "exit"
            self.stop(); start_event.set(); edit_event.set()

        is_batch = len(self.files_to_process) > 1
        self.ui.open_editor_for_file(target_file, on_save, on_start, on_prev, on_exit, is_batch=is_batch)

        if getattr(self, 'is_auto_start', False):
            threading.Timer(0.5, on_start).start()

        start_event.wait()
        if action_state[0] == "prev": self.ui.request_show_home(); raise Exception("USER_PREV")
        if action_state[0] == "exit": self.ui.request_show_home(); raise Exception("USER_EXIT")
        if action_state[0] == "next": return

        while True:
            self._active = True; self._speaker_map = []; edit_event.clear()
            self._reload_speaker_settings()
            vname = os.path.basename(target_file)
            fsize = os.path.getsize(target_file) / (1024*1024) if os.path.exists(target_file) else 0

            get_logger().log(f"\n{'='*44}\n🎬 [{queue_index+1}/{len(self.files_to_process)}] {vname}\n{'='*44}\n\n{'─'*44}\n  📂 파일: {vname} ({fsize:.1f} MB)\n{'─'*44}")
            
            res = self.video_processor.extract_audio(target_file)
            if not res:
                get_logger().log("❌ 오디오 추출 실패"); edit_event.wait()
                if action_state[0] == "restart":
                    get_logger().log("\n🔄 재시작합니다..."); action_state[0] = "next"; continue
                break

            chunk_dir, vad_segs = res
            if hasattr(self.ui, '_sig_set_vad_segments'): self.ui._sig_set_vad_segments.emit(vad_segs)

            get_logger().log("\n  [STEP 2] 🎤 Whisper 변환 + LLM 최적화 파이프라인 가동...")

            try:
                with open(_SETTINGS_PATH, "r", encoding="utf-8") as f: s = json.load(f)
                max_spk  = int(s.get('max_speakers', 1)); dia_flag = "O" if max_spk > 1 else "X"
                model_key = f"STT:{s.get('selected_whisper_model','기본')}|LLM:{s.get('selected_model','기본')}|DIA:{dia_flag}"

                if target_file in getattr(self, '_video_durations', {}): video_duration_sec = self._video_durations[target_file]
                else: chunks = [f for f in os.listdir(chunk_dir) if f.endswith('.wav')]; video_duration_sec = len(chunks) * 30.0

                expected_time = get_expected_time(model_key, video_duration_sec)
                if hasattr(self.ui, '_sig_update_queue'):
                    if expected_time > 0: self.ui._sig_update_queue.emit(queue_index, "자막 생성 중", str(expected_time), "", "")
                    else: self.ui._sig_update_queue.emit(queue_index, "자막 생성 중", "예상불가 (학습 중)", "", "")
                process_start_time = time.time()
            except Exception:
                process_start_time = time.time(); video_duration_sec = 0.0

            opt_queue = queue.Queue()
            base_name = os.path.splitext(os.path.basename(target_file))[0]
            cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
            audio_for_diarization = cleaned_wav if os.path.exists(cleaned_wav) else target_file

            t_diarize = None
            if self.max_speakers > 1:
                t_diarize = threading.Thread(target=self._prepare_speaker_map, args=(audio_for_diarization,), daemon=True, name="diarizer")
                t_diarize.start()

            auto_collected_segs = []

            def do_transcribe():
                try:
                    for chunk_segs, c_idx, t_total in self.video_processor.transcribe(chunk_dir, is_fast_mode=getattr(self, 'is_auto_start', False)):
                        if not self._active: break
                        opt_queue.put((chunk_segs, c_idx, t_total))
                finally: opt_queue.put(_SENTINEL)
            def do_optimize():
                from .subtitle_engine import optimize_segments
                import json

                total_files = len(self.files_to_process)

                if t_diarize and t_diarize.is_alive():
                    get_logger().log("\n⏳ [안내] 화자 분리 연산 대기 중...")
                    t_diarize.join()

                try:
                    s = self._load_settings()
                    model_name = s.get('selected_model', '기본')
                    api_key = s.get('google_api_key', '')
                    user_prompt = s.get('custom_prompt', '')
                    chunk_time_limit = int(s.get('chunk_time_limit', 60))
                except Exception:
                    model_name = ""
                    api_key = ""
                    user_prompt = ""
                    chunk_time_limit = 60

                is_gemini = "API" in model_name or "Gemini" in model_name

                seg_buffer = []
                last_c_idx = 0
                last_t_total = 1

                def _flush_buffer():
                    nonlocal seg_buffer
                    if not seg_buffer: return

                    chunk_segs = seg_buffer
                    seg_buffer = [] 

                    try:
                        if is_gemini and len(chunk_segs) > 1:
                            from .subtitle_engine import ask_gemini_to_split
                            from .utils import load_subtitle_rules

                            chunk_start = chunk_segs[0]["start"]
                            chunk_end = chunk_segs[-1]["end"]

                            full_text = " ".join([seg["text"] for seg in chunk_segs])
                            rules = load_subtitle_rules()

                            res_chunks = ask_gemini_to_split(full_text, 15, rules, model_name, user_prompt, api_key)

                            if res_chunks and len(res_chunks) > 0:
                                opt = []
                                dur = (chunk_end - chunk_start) / len(res_chunks)
                                for i, txt in enumerate(res_chunks):
                                    opt.append({
                                        "start": round(chunk_start + i * dur, 3),
                                        "end": round(chunk_start + (i + 1) * dur, 3),
                                        "text": txt
                                    })
                            else:
                                opt = optimize_segments(chunk_segs)
                        else:
                            opt = optimize_segments(chunk_segs)

                    except Exception as e:
                        get_logger().log(f"  ❌ 최적화 오류: {e}")
                        opt = chunk_segs

                    for seg in opt:
                        if seg["start"] < 0.0:              seg["start"] = 0.0
                        if seg["end"] <= seg["start"]:      seg["end"]   = seg["start"] + 0.5

                    if self.max_speakers > 1 and self._speaker_map:
                        from .diarize import get_speaker_for_segment
                        for seg in opt:
                            spk_full = get_speaker_for_segment(seg["start"], seg["end"], self._speaker_map)
                            seg["speaker"] = spk_full.replace("SPEAKER_", "")

                        grouped_opt = []
                        for seg in opt:
                            text = seg.get("text", "").strip()
                            if text.startswith("-"): text = text.lstrip("-").strip()
                            spk = seg.get("speaker", "00")

                            if not grouped_opt:
                                seg["text_list"]    = [text]
                                seg["speaker_list"] = [spk]
                                grouped_opt.append(seg)
                            else:
                                prev = grouped_opt[-1]
                                gap  = seg["start"] - prev["end"]
                                if gap < 1.5 and spk != prev["speaker_list"][-1] and len(prev["speaker_list"]) < 2:
                                    prev["text_list"].append(text)
                                    prev["speaker_list"].append(spk)
                                    prev["end"] = max(prev["end"], seg["end"])
                                else:
                                    seg["text_list"]    = [text]
                                    seg["speaker_list"] = [spk]
                                    grouped_opt.append(seg)

                        for seg in grouped_opt:
                            if len(seg.get("text_list", [])) > 1:
                                seg["text"] = f"- {seg['text_list'][0]}\n- {seg['text_list'][1]}"
                            else:
                                seg["text"] = seg["text_list"][0] if "text_list" in seg else seg.get("text", "")
                            if "text_list" in seg: del seg["text_list"]
                        opt = grouped_opt

                    auto_collected_segs.extend(opt)
                    if hasattr(self.ui, "_sig_append_segments"):
                        self.ui._sig_append_segments.emit(opt)

                    if hasattr(self.ui, "_sig_update_editor_status"):
                        self.ui._sig_update_editor_status.emit(last_c_idx, last_t_total)

                while self._active:
                    item = opt_queue.get()
                    if item is _SENTINEL:
                        _flush_buffer() 
                        break

                    chunk_segs, c_idx, t_total = item
                    last_c_idx = c_idx
                    last_t_total = t_total

                    if t_total > 0:
                        overall_pct = int(((queue_index + (c_idx / t_total)) / total_files) * 100)
                    else:
                        overall_pct = int((queue_index / total_files) * 100)

                    if hasattr(self.ui, '_sig_update_queue_header'):
                        self.ui._sig_update_queue_header.emit(queue_index + 1, total_files, overall_pct, "")

                    if not chunk_segs:
                        self.ui.update_editor_status(c_idx, t_total)
                        continue

                    seg_buffer.extend(chunk_segs)

                    buffer_start = seg_buffer[0]["start"]
                    buffer_end = seg_buffer[-1]["end"]
                    current_duration = buffer_end - buffer_start

                    if current_duration >= chunk_time_limit:
                        _flush_buffer()

            t_trans = threading.Thread(target=do_transcribe, daemon=True, name="transcriber")
            t_opt   = threading.Thread(target=do_optimize,   daemon=True, name="optimizer")
            t_trans.start(); t_opt.start()
            t_trans.join();  t_opt.join()

            try:
                with open(_SETTINGS_PATH, "r", encoding="utf-8") as f: s = json.load(f)
                max_spk = int(s.get('max_speakers', 1)); dia_flag = "O" if max_spk > 1 else "X"
                model_key = f"STT:{s.get('selected_whisper_model','기본')}|LLM:{s.get('selected_model','기본')}|DIA:{dia_flag}"
                proc_time = time.time() - process_start_time
                add_history(model_key, video_duration_sec, proc_time)
            except Exception: pass

            if getattr(self, 'is_auto_start', False):
                nonlocal_final = auto_collected_segs[:]
                def _auto_proceed():
                    nonlocal final_segments
                    final_segments = nonlocal_final; action_state[0] = "next"; edit_event.set()
                threading.Timer(2.0, _auto_proceed).start()

            edit_event.wait()
            # 💡 [핵심] 재시작 부분 중복/꼬임 완벽하게 제거됨
            if action_state[0] == "restart":
                get_logger().log("\n🔄 현재 파일의 자막 생성을 처음부터 다시 시작합니다...")

                try:
                    from .path_manager import get_srt_path
                    srt_p = get_srt_path(target_file)
                    if os.path.exists(srt_p):
                        os.remove(srt_p)
                        get_logger().log("    └ 🗑️ 기존 자막 파일을 삭제했습니다. (새로 생성)")

                    if hasattr(self, 'ui') and getattr(self.ui, '_editor_widget', None):
                        ed = self.ui._editor_widget
                        if hasattr(ed, 'text_edit'):
                            ed.text_edit.blockSignals(True)
                            ed.text_edit.clear()
                            ed.text_edit.blockSignals(False)
                        if hasattr(ed, 'timeline') and hasattr(ed.timeline, 'canvas'):
                            ed.timeline.canvas.segments.clear()
                            ed.timeline.canvas.update()
                        ed._is_dirty = False
                except Exception as e:
                    get_logger().log(f"    └ ⚠️ 초기화 중 오류: {e}")

                action_state[0] = "next"; continue

            if not self._active: return
            if action_state[0] == "prev": self.ui.request_show_home(); raise Exception("USER_PREV")
            if action_state[0] == "exit": self.ui.request_show_home(); raise Exception("USER_EXIT")
            break

        # ── STEP 5: SRT 저장 ──────────────────────────────────────
        get_logger().log(f"\n  [STEP 5] 💾 SRT 저장 중...")
        try:
            from .subtitle_engine import save_srt
            from .path_manager    import get_srt_path
            srt_path = get_srt_path(target_file)
            save_srt(final_segments, srt_path, apply_offset=True)
            get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료")

            if hasattr(self.ui, '_sig_update_queue'):
                try: self.ui._sig_update_queue.emit(queue_index, "✅ 자막출력(srt)", "완료", "", "")
                except RuntimeError: pass

            # ── STEP 6: 자막 영상(MOV) 백그라운드 렌더링 ─────────────────
            if getattr(self, 'is_auto_start', False):
                try:
                    try: from ui.export_dialog import _load_es
                    except ImportError: from export_dialog import _load_es
                    s = _load_es()

                    if s.get("icloud", False):
                        get_logger().log(f"\n  [STEP 6] 🎥 투명 자막 영상(MOV) 자동 렌더링 및 iCloud 백업 중...")
                        if hasattr(self.ui, '_sig_update_queue'):
                            self.ui._sig_update_queue.emit(queue_index, "🎥 자막영상출력(mov)", "렌더링 중...", "", "")
                        self._run_background_render(srt_path, target_file, s)
                except Exception as e:
                    get_logger().log(f"❌ MOV 자동 렌더링 오류: {e}")
                    get_logger().log(traceback.format_exc())

            try:
                from .auto_tracker import AutoTracker
                AutoTracker().mark_completed(target_file)
                if hasattr(self.ui, 'mark_cloud_file_done'):
                    self.ui.mark_cloud_file_done(target_file)
            except Exception: pass

            if hasattr(self.ui, '_sig_update_queue'):
                try:
                    if getattr(self, 'is_auto_start', False):
                        self.ui._sig_update_queue.emit(queue_index, "✅ 완료 (다음파일)", "작업 종료", "", "")
                    else:
                        self.ui._sig_update_queue.emit(queue_index, "✅ 자막생성완료", "작업 종료", "", "")
                except RuntimeError: pass

        except Exception as e:
            get_logger().log(f"❌ 처리 실패: {e}")

        if action_state[0] == "exit" or not getattr(self, '_active', True):
            try:
                if hasattr(self, 'ui') and self.ui: self.ui.request_show_home()
            except RuntimeError: pass
            raise Exception("USER_EXIT")

    # ---------------------------------------------------------
    # 💡 [신규] 백그라운드 MOV 렌더링 엔진
    # ---------------------------------------------------------
    def _run_background_render(self, srt_path, target_file, s):
        import tempfile, shutil, re
        from PyQt6.QtGui import QColor, QImage
        from PyQt6.QtCore import Qt
        try: from ui.export_dialog import _parse_srt, _make_png
        except ImportError: from export_dialog import _parse_srt, _make_png

        segs = _parse_srt(srt_path)
        if not segs: return False
        
        res_text = s.get("res", "4K (3840px)")
        width = 3840 if "4K" in res_text else 1920
        fs = int(s.get("size", 60))
        res_scale = 4.0 if width == 3840 else 2.0
        scaled_fs = int(fs * res_scale)
        height = int(scaled_fs * 3.5)
        height += height % 2

        bg_c = QColor(s.get("bg_c", "#000000"))
        bg_rgba = (bg_c.red(), bg_c.green(), bg_c.blue(), int(s.get("bg_op", 50)*2.55)) if s.get("bg", False) else None
        
        bdr_w = int(s.get("bdr_w", 2))
        bdr_w = max(1, int(bdr_w * res_scale)) if bdr_w > 0 and not s.get("no_bdr", False) else 0
        
        txt_c = QColor(s.get("txt_c", "#FFFFFF"))
        bdr_c = QColor(s.get("bdr_c", "#FFFFFF"))
        shd_c = QColor(s.get("shd_c", "#000000"))

        style = dict(
            font_path="", font_family=s.get("font", "Apple SD Gothic Neo"),
            font_size=scaled_fs, res_scale=res_scale, bold=s.get("bold", True),
            align=s.get("align", "가운데"), line_spacing=int(int(s.get("lsp", 6)) * res_scale),
            txt_rgba=(txt_c.red(), txt_c.green(), txt_c.blue(), 255),
            border_w=bdr_w, border_rgba=(bdr_c.red(), bdr_c.green(), bdr_c.blue(), 255),
            shadow_rgba=(shd_c.red(), shd_c.green(), shd_c.blue(), 200) if s.get("shadow", False) else None,
            shadow_x=int(int(s.get("shdx", 3)) * res_scale), shadow_y=int(int(s.get("shdy", 3)) * res_scale),
            bg_rgba=bg_rgba, bg_radius=int(s.get("bg_radius", 10) * res_scale),
            bg_margin=int(s.get("bg_margin", 18) * res_scale), bg_full_width=s.get("bg_full", False)
        )

        total_dur = max(seg["end"] for seg in segs) + 0.5
        wd = tempfile.mkdtemp(prefix="sub_exp_auto_")
        safe_v = re.sub(r'[\\/:*?"<>|]', '_', os.path.basename(target_file))
        out_p = os.path.join(os.path.dirname(target_file), f"{os.path.splitext(safe_v)[0]}_자막소스.mov")

        try:
            pts = sorted({0.0, total_dur} | {sg["start"] for sg in segs} | {sg["end"] for sg in segs})
            events = []
            for i in range(len(pts)-1):
                t0, t1 = pts[i], pts[i+1]
                if t1 - t0 < 0.001: continue
                txt = next((sg["text"] for sg in segs if sg["start"] <= t0 and sg["end"] >= t1), None)
                events.append((t0, t1, txt))

            blank = os.path.join(wd, "blank.png")
            bg_img = QImage(width, height, QImage.Format.Format_ARGB32)
            bg_img.fill(Qt.GlobalColor.transparent)
            bg_img.save(blank, "PNG")

            txt_png = {}
            unique = {e[2] for e in events if e[2]}
            for i, text in enumerate(unique):
                p2 = os.path.join(wd, f"s{i:04d}.png")
                _make_png(p2, text, width, height, style)
                txt_png[text] = p2

            concat = os.path.join(wd, "c.txt")
            with open(concat, "w", encoding="utf-8") as f:
                for t0, t1, txt in events:
                    f.write(f"file '{txt_png.get(txt, blank) if txt else blank}'\nduration {t1-t0:.6f}\n")
                if events: f.write(f"file '{txt_png.get(events[-1][2], blank) if events[-1][2] else blank}'\n")

            enc = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
            if "빠른" in s.get("quality", "빠른"): enc.extend(["-q:v", "15"])
            
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat, "-vf", "format=yuva444p10le"] + enc + [out_p]
            subprocess.run(cmd, capture_output=True)

            if os.path.exists(out_p):
                get_logger().log(f"    └ ✅ MOV 렌더링 완료: {os.path.basename(out_p)}")
                dest_dir = getattr(config, "ICLOUD_DROPZONE", os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT"))
                os.makedirs(dest_dir, exist_ok=True)
                dest_file = os.path.join(dest_dir, os.path.basename(out_p))
                
                if os.path.abspath(out_p) != os.path.abspath(dest_file):
                    get_logger().log("    └ ☁️ iCloud로 자동 복사 중...")
                    shutil.copy2(out_p, dest_file)
                    get_logger().log(f"    └ ✅ iCloud 복사 완료")

                # 💡 [수정됨] 완료 알림 전송
                self._send_ntfy_notification(
                    title=f"{config.APP_NAME} 알림",
                    message=f"✅ [{os.path.basename(target_file)}]\n투명 자막 영상이 iCloud에 준비되었습니다!\n아이패드에서 편집을 시작하세요 🎬",
                    tags="tada,sparkles"
                )
                get_logger().log("    └ 📱 아이패드로 작업 완료 알림 전송 성공!")


                return True
        finally:
            shutil.rmtree(wd, ignore_errors=True)
        return False

    def _reload_speaker_settings(self):
        s = self._load_settings()
        self.min_speakers = int(s.get("min_speakers", 1))
        self.max_speakers = int(s.get("max_speakers", 1))


    def _load_selected_model(self):
        s = self._load_settings()
        return s.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))
    
    def _prepare_speaker_map(self, audio_path):
        try:
            from .diarize import get_speaker_map
            self._speaker_map = get_speaker_map(audio_path, self.min_speakers, self.max_speakers)
        except Exception: self._speaker_map = []

    def _send_ntfy_notification(self, title: str, message: str, tags: str = ""):
        """ntfy 알림 전송 (config.NTFY_TOPIC 기반, 한글 깨짐 방지 Base64 적용)"""
        try:
            import urllib.request
            import base64

            topic = getattr(config, "NTFY_TOPIC", "")
            if not topic:
                return  # 토픽 비어있으면 비활성

            url = f"https://ntfy.sh/{topic}"

            encoded_title = f"=?UTF-8?B?{base64.b64encode(title.encode('utf-8')).decode('utf-8')}?="

            req = urllib.request.Request(url, data=message.encode("utf-8"), method="POST")
            req.add_header("Title", encoded_title)
            if tags:
                req.add_header("Tags", tags)

            urllib.request.urlopen(req, timeout=3)
        except Exception as e:
            get_logger().log(f"    └ ⚠️ 알림 전송 실패: {e}")