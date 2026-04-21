# Version: 01.00.07
"""
core/backend.py
[v01.00.07] 모드/상태 정의 문서 반영
- do_optimize 종료 시 완료 숫자 전달 (EditorPipeline이 완료 판단)
- ntfy: _is_auto_pipeline 체크 (iCloud/NAS 자동모드에서만)
- start_event.wait timeout 추가
- ffmpeg returncode 체크
- 기존 기능 100% 유지
"""

import os, threading, traceback, queue, time
import config
from logger import get_logger

from .media_processor import VideoProcessor
from .time_history import get_expected_time, add_history
from .settings import load_settings, get_model_key
from .media_info import probe_media

_SENTINEL = object()


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
        self._eta_thread = threading.Thread(target=self._precalculate_etas, daemon=True, name="eta-calculator")
        self._eta_thread.start()
        get_logger().log(f"🚀 총 {len(self.files_to_process)}개 파일 처리 시작!")
        self._pipeline_thread = threading.Thread(target=self._run_all, daemon=True, name="pipeline-main")
        self._pipeline_thread.start()

    def restart_current_file(self):
        if hasattr(self, '_action_state'): self._action_state[0] = "restart"
        if hasattr(self, '_edit_event'): self._edit_event.set()
        self._speaker_map = []

    def stop(self):
        self._active = False
        try:
            if hasattr(self, "video_processor"):
                self.video_processor.stop_transcribe()
        except Exception as e:
            get_logger().log(f"⚠️ stop_transcribe 실패: {e}")
        if hasattr(self, '_edit_event'): self._edit_event.set()
        if hasattr(self, '_start_event'): self._start_event.set()

    def _precalculate_etas(self):
        total_expected_time = 0.0
        s = load_settings()
        model_key = get_model_key(s)

        for i, target_file in enumerate(self.files_to_process):
            try:
                info = probe_media(target_file)
                duration_sec = info["duration"]
                info_txt = info["info_txt"]
                len_txt = info["len_txt"]

                self._video_durations[target_file] = duration_sec

                expected_time = get_expected_time(model_key, duration_sec)
                if expected_time > 0:
                    total_expected_time += expected_time

                if hasattr(self.ui, '_sig_update_queue'):
                    self.ui._sig_update_queue.emit(
                        i, "⏳ 대기 중", str(expected_time), info_txt, len_txt
                    )
            except Exception as e:
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
        eta_thread = getattr(self, '_eta_thread', None)
        if eta_thread and eta_thread.is_alive():
            eta_thread.join(timeout=30)

        try:
            total_files = len(self.files_to_process)
            for i, target_file in enumerate(self.files_to_process):
                if not self._active:
                    return
                if hasattr(self.ui, '_sig_update_queue'):
                    self.ui._sig_update_queue.emit(i, "⏳ 오디오 추출 중", "", "", "")
                if hasattr(self.ui, '_sig_update_queue_header'):
                    self.ui._sig_update_queue_header.emit(i + 1, total_files, 0, "")
                self._process_one(target_file, i)

            if getattr(self.ui, '_is_auto_pipeline', False):
                self._send_ntfy_notification(
                    title=f"🏆 {config.APP_NAME} 작업 종료",
                    message=f"🎉 {total_files}개 파일 처리 완료!\n아이패드에서 확인해 보세요, 대표님.",
                    tags="checkered_flag,tada"
                )

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
    
    def _backup_existing(self, target_file):
        """기존 자막/MOV 파일 백업"""
        try:
            from .path_manager import get_srt_path
            import datetime, shutil
            base_path = os.path.splitext(target_file)[0]
            srt_p = get_srt_path(target_file)
            mov_p = f"{base_path}_자막소스.mov"
            backup_dir = os.path.join(os.path.dirname(target_file), "자막백업")
            if os.path.exists(srt_p) or os.path.exists(mov_p):
                os.makedirs(backup_dir, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                if os.path.exists(srt_p):
                    shutil.copy2(srt_p, os.path.join(backup_dir, f"{os.path.basename(srt_p)}.{timestamp}.bak"))
                if os.path.exists(mov_p):
                    shutil.copy2(mov_p, os.path.join(backup_dir, f"{os.path.basename(mov_p)}.{timestamp}.bak"))
                get_logger().log("📦 기존 자막 파일을 '자막백업' 폴더에 안전하게 복사(백업)했습니다.")
        except Exception as e:
            get_logger().log(f"⚠️ 백업 중 오류 발생 (무시하고 진행): {e}")

    def _handle_restart(self, target_file):
        """재시작 시 에디터/SRT 초기화"""
        get_logger().log("\n🔄 현재 파일의 자막 생성을 처음부터 다시 시작합니다...")
        try:
            from .path_manager import get_srt_path
            srt_p = get_srt_path(target_file)
            if os.path.exists(srt_p):
                os.remove(srt_p)
                get_logger().log("    └ 🗑️ 기존 자막 파일을 삭제했습니다. (새로 생성)")

            def _clear_editor_main():
                ed = getattr(self.ui, '_editor_widget', None)
                if ed is None: return
                try:
                    if hasattr(ed, 'text_edit'):
                        ed.text_edit.blockSignals(True)
                        ed.text_edit.clear()
                        ed.text_edit.blockSignals(False)
                    if hasattr(ed, 'timeline') and hasattr(ed.timeline, 'canvas'):
                        ed.timeline.canvas.segments.clear()
                        ed.timeline.canvas.update()
                    ed._is_dirty = False
                except Exception as ex:
                    get_logger().log(f"    └ ⚠️ 에디터 초기화 중 오류: {ex}")

            from PyQt6.QtCore import QTimer as _QT
            _QT.singleShot(0, _clear_editor_main)
        except Exception as e:
            get_logger().log(f"    └ ⚠️ 초기화 중 오류: {e}")

    def _save_and_export(self, target_file, queue_index, final_segments, is_auto_mode):
        """SRT 저장 + MOV 렌더링 + 완료 처리"""
        get_logger().log(f"\n  [STEP 5] 💾 SRT 저장 중...")
        try:
            from .subtitle_engine import save_srt
            from .path_manager import get_srt_path
            srt_path = get_srt_path(target_file)
            save_srt(final_segments, srt_path, apply_offset=True)
            get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료")

            is_video_export = False
            export_settings = {}
            try:
                try: from ui.export_dialog import _load_es
                except ImportError: from export_dialog import _load_es
                export_settings = _load_es()
                is_video_export = export_settings.get("icloud", False)
            except Exception: pass

            base_name = os.path.splitext(os.path.basename(target_file))[0]
            current_idx = queue_index + 1
            total_cnt = len(self.files_to_process)

            if not is_video_export and getattr(self.ui, '_is_auto_pipeline', False):
                self._send_ntfy_notification(
                    title=f"📝 {config.APP_NAME} 알림",
                    message=f"[{current_idx}/{total_cnt}] {base_name}.srt 생성 완료!\n🎯 다음 작업으로 넘어갑니다.",
                    tags="memo,sparkles"
                )

            if hasattr(self.ui, '_sig_update_queue'):
                try: 
                    self.ui._sig_update_queue.emit(queue_index, "✅ 자막출력(srt)", "", "", "")
                except RuntimeError: pass

            # ── STEP 6: MOV 렌더링 ──
            if is_video_export:
                try:
                    get_logger().log(f"\n  [STEP 6] 🎥 투명 자막 영상(MOV) 백그라운드 렌더링 및 iCloud 백업 중...")
                    if hasattr(self.ui, '_sig_update_queue'):
                        self.ui._sig_update_queue.emit(queue_index, "🎥 자막영상출력(mov)", "", "", "")
                    self._run_background_render(srt_path, target_file, export_settings, current_idx, total_cnt)
                except Exception as e:
                    get_logger().log(f"❌ MOV 렌더링 오류: {e}")
                    get_logger().log(traceback.format_exc())

            try:
                from .auto_tracker import AutoTracker
                AutoTracker().mark_completed(target_file)
                if hasattr(self.ui, 'mark_cloud_file_done'):
                    self.ui.mark_cloud_file_done(target_file)
            except Exception: pass

            if hasattr(self.ui, '_sig_update_queue'):
                try:
                    if is_auto_mode:
                        self.ui._sig_update_queue.emit(queue_index, "✅ 완료 (다음파일)", "", "", "")
                    else:
                        self.ui._sig_update_queue.emit(queue_index, "✅ 자막생성완료", "", "", "")
                except RuntimeError:
                    pass

        except Exception as e:
            get_logger().log(f"❌ 처리 실패: {e}")

    def _process_one(self, target_file, queue_index):
        # ── STEP 0: 백업 ──
        self._backup_existing(target_file)

        # ── 이벤트/콜백 ──
        edit_event = threading.Event(); start_event = threading.Event()
        self._edit_event = edit_event; self._start_event = start_event
        final_segments = []; action_state = ["wait"]; self._action_state = action_state

        def on_save(segs):
            nonlocal final_segments
            final_segments = segs; action_state[0] = "next"
            start_event.set(); edit_event.set()

        def on_start():
            if getattr(self, 'is_first_start', True):
                self.pipeline_start_time = time.time(); self.is_first_start = False
            action_state[0] = "start"; start_event.set()

        def on_prev():
            action_state[0] = "prev"; start_event.set(); edit_event.set()

        def on_exit(segs):
            nonlocal final_segments
            final_segments = segs; action_state[0] = "exit"
            self.stop(); start_event.set(); edit_event.set()

        # 변경: 첫 파일은 수동, 이후 파일은 자동 진행
        is_auto_mode = getattr(self, 'is_auto_start', False) or (queue_index > 0 and len(self.files_to_process) > 1)

        self.ui.open_editor_for_file(target_file, on_save, on_start, on_prev, on_exit, is_batch=is_auto_mode)

        if is_auto_mode:
            threading.Timer(0.5, on_start).start()

        if not start_event.wait(timeout=600):
            get_logger().log("❌ 시작 이벤트 타임아웃 (600초)")
            return
        if action_state[0] == "prev": self.ui.request_show_home(); raise Exception("USER_PREV")
        if action_state[0] == "exit": self.ui.request_show_home(); raise Exception("USER_EXIT")
        if action_state[0] == "next": return

        # ── STT 파이프라인 루프 ──
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
            if hasattr(self.ui, '_sig_set_vad_segments'):
                self.ui._sig_set_vad_segments.emit(vad_segs)

            get_logger().log("\n  [STEP 2] 🎤 Whisper 변환 + LLM 최적화 파이프라인 가동...")

            try:
                s = load_settings()
                model_key = get_model_key(s)

                if target_file in getattr(self, '_video_durations', {}):
                    video_duration_sec = self._video_durations[target_file]
                else:
                    chunks = [f for f in os.listdir(chunk_dir) if f.endswith('.wav')]
                    video_duration_sec = len(chunks) * 30.0

                expected_time = get_expected_time(model_key, video_duration_sec)
                if hasattr(self.ui, '_sig_update_queue'):
                    if expected_time > 0:
                        self.ui._sig_update_queue.emit(queue_index, "자막 생성 중", str(expected_time), "", "")
                    else:
                        self.ui._sig_update_queue.emit(queue_index, "자막 생성 중", "예상불가 (학습 중)", "", "")
                process_start_time = time.time()
            except Exception:
                process_start_time = time.time(); video_duration_sec = 0.0

            opt_queue = queue.Queue()
            base_name = os.path.splitext(os.path.basename(target_file))[0]

            # 교체 (m4a 안전 fallback)
            cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
            raw_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}.wav")
            if os.path.exists(cleaned_wav):
                audio_for_diarization = cleaned_wav
            elif os.path.exists(raw_wav):
                audio_for_diarization = raw_wav
            else:
                wav_in_chunks = sorted([os.path.join(chunk_dir, f) for f in os.listdir(chunk_dir) if f.endswith('.wav')])
                audio_for_diarization = wav_in_chunks[0] if wav_in_chunks else target_file


            t_diarize = None
            if self.max_speakers > 1:
                t_diarize = threading.Thread(target=self._prepare_speaker_map, args=(audio_for_diarization,), daemon=True, name="diarizer")
                t_diarize.start()

            auto_collected_segs = []

            def do_transcribe():
                try:
                    for chunk_segs, c_idx, t_total in self.video_processor.transcribe(chunk_dir, is_fast_mode=is_auto_mode):
                        if not self._active: break
                        opt_queue.put((chunk_segs, c_idx, t_total))
                finally:
                    opt_queue.put(_SENTINEL)

            def do_optimize():
                from .subtitle_engine import optimize_segments
                total_files = len(self.files_to_process)

                if t_diarize and t_diarize.is_alive():
                    get_logger().log("\n⏳ [안내] 화자 분리 연산 대기 중...")
                    t_diarize.join()

                try:
                    s = load_settings()
                    model_name = s.get('selected_model', '기본')
                    api_key = s.get('google_api_key', '')
                    user_prompt = s.get('custom_prompt', '')
                    chunk_time_limit = int(s.get('chunk_time_limit', 60))
                except Exception:
                    model_name = ""; api_key = ""; user_prompt = ""; chunk_time_limit = 60

                is_gemini = "API" in model_name or "Gemini" in model_name
                seg_buffer = []
                last_c_idx = 0
                last_t_total = 1

                def _flush_buffer():
                    nonlocal seg_buffer
                    if not seg_buffer: return
                    chunk_segs = seg_buffer; seg_buffer = []

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
                        if seg["start"] < 0.0: seg["start"] = 0.0
                        if seg["end"] <= seg["start"]: seg["end"] = seg["start"] + 0.5

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
                                seg["text_list"] = [text]; seg["speaker_list"] = [spk]
                                grouped_opt.append(seg)
                            else:
                                prev = grouped_opt[-1]
                                gap = seg["start"] - prev["end"]
                                if gap < 1.5 and spk != prev["speaker_list"][-1] and len(prev["speaker_list"]) < 2:
                                    prev["text_list"].append(text); prev["speaker_list"].append(spk)
                                    prev["end"] = max(prev["end"], seg["end"])
                                else:
                                    seg["text_list"] = [text]; seg["speaker_list"] = [spk]
                                    grouped_opt.append(seg)

                        for seg in grouped_opt:
                            if len(seg.get("text_list", [])) > 1:
                                seg["text"] = f"- {seg['text_list'][0]}\n- {seg['text_list'][1]}"
                            else:
                                seg["text"] = seg["text_list"][0] if "text_list" in seg else seg.get("text", "")
                            if "text_list" in seg: del seg["text_list"]
                        opt = grouped_opt

                    auto_collected_segs.extend(opt)

                    try:
                        if hasattr(self.ui, "_sig_append_segments"):
                            self.ui._sig_append_segments.emit(opt)
                        if hasattr(self.ui, "_sig_update_status"):
                            self.ui._sig_update_status.emit(last_c_idx, last_t_total)
                    except RuntimeError:
                        pass

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

 
                    if hasattr(self.ui, '_sig_update_status'):
                        self.ui._sig_update_status.emit(c_idx, t_total)

                    # 교체: try/except 감싸기
                    try:
                        if hasattr(self.ui, '_sig_update_queue_header'):
                            self.ui._sig_update_queue_header.emit(queue_index + 1, total_files, overall_pct, "")
                    except RuntimeError:
                        pass

                    if not chunk_segs:
                        try:
                            if hasattr(self.ui, '_sig_update_status'):
                                self.ui._sig_update_status.emit(c_idx, t_total)
                        except RuntimeError:
                            pass
                        continue

                    seg_buffer.extend(chunk_segs)
                    buffer_start = seg_buffer[0]["start"]
                    buffer_end = seg_buffer[-1]["end"]
                    current_duration = buffer_end - buffer_start

                    if current_duration >= chunk_time_limit:
                        _flush_buffer()

                if hasattr(self.ui, '_sig_update_status'):
                    self.ui._sig_update_status.emit(last_t_total, last_t_total)

            t_trans = threading.Thread(target=do_transcribe, daemon=True, name="transcriber")
            t_opt = threading.Thread(target=do_optimize, daemon=True, name="optimizer")
            t_trans.start(); t_opt.start()
            t_trans.join(); t_opt.join()

            # ✅ STT 완료 → 큐 즉시 업데이트
            if hasattr(self.ui, '_sig_update_queue'):
                try:
                    self.ui._sig_update_queue.emit(queue_index, "✅ 자막 생성 완료", "", "", "")
                except RuntimeError:
                    pass

            try:
                s = load_settings()
                model_key = get_model_key(s)
                proc_time = time.time() - process_start_time
                add_history(model_key, video_duration_sec, proc_time)
            except Exception: pass

            if is_auto_mode:
                nonlocal_final = auto_collected_segs[:]
                def _auto_proceed():
                    nonlocal final_segments
                    final_segments = nonlocal_final; action_state[0] = "next"; edit_event.set()
                threading.Timer(2.0, _auto_proceed).start()

            edit_event.wait()

            if action_state[0] == "restart":
                self._handle_restart(target_file)
                action_state[0] = "next"; continue

            if not self._active: return
            if action_state[0] == "prev": self.ui.request_show_home(); raise Exception("USER_PREV")
            if action_state[0] == "exit": self.ui.request_show_home(); raise Exception("USER_EXIT")
            break

        # ── STEP 5~6: 저장 + 내보내기 ──
        self._save_and_export(target_file, queue_index, final_segments, is_auto_mode)

        if action_state[0] == "exit" or not getattr(self, '_active', True):
            try:
                if hasattr(self, 'ui') and self.ui: self.ui.request_show_home()
            except RuntimeError: pass
            raise Exception("USER_EXIT")    

    def _run_background_render(self, srt_path, target_file, s, current_idx=1, total_cnt=1):
        """MOV 렌더링 → renderer.py에 위임"""
        from .renderer import render_subtitle_mov

        success = render_subtitle_mov(srt_path, target_file, s, current_idx, total_cnt)

        if success:
            base_name = os.path.splitext(os.path.basename(target_file))[0]
            if getattr(self.ui, '_is_auto_pipeline', False):
                self._send_ntfy_notification(
                    title=f"🎞️ {config.APP_NAME} 알림",
                    message=f"[{current_idx}/{total_cnt}] {base_name}.srt / {base_name}.mov 생성 완료!",
                    tags="film_projector,rocket"
                )

        return success

    def _reload_speaker_settings(self):
        s = load_settings()
        self.min_speakers = int(s.get("min_speakers", 1))
        self.max_speakers = int(s.get("max_speakers", 1))

    def _load_selected_model(self):
        s = load_settings()
        return s.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))

    def _prepare_speaker_map(self, audio_path):
        try:
            from .diarize import get_speaker_map
            self._speaker_map = get_speaker_map(audio_path, self.min_speakers, self.max_speakers)
        except Exception:
            self._speaker_map = []

    def _send_ntfy_notification(self, title, message, tags=""):
        from .notifier import send_ntfy
        send_ntfy(title, message, tags)

    def start_multiclip_pipeline(self, files, folder=None):
        """멀티클립 품질모드: 모든 클립 순차 STT → 하나의 에디터에서 편집"""
        self._active = True
        self.files_to_process = list(files)
        self.current_folder = folder
        self.is_auto_start = False
        self.is_first_start = True
        self.total_expected_time = 0.0
        self.pipeline_start_time = 0.0

        if not self.files_to_process:
            return
        if hasattr(self.ui, 'init_queue_list'):
            self.ui.init_queue_list(self.files_to_process)

        get_logger().log(f"🎬 멀티클립 품질모드: {len(self.files_to_process)}개 클립 순차 처리")
        self._pipeline_thread = threading.Thread(
            target=self._run_multiclip, daemon=True, name="multiclip-main"
        )
        self._pipeline_thread.start()

    def _run_multiclip(self):
        try:
            total_files = len(self.files_to_process)
            first_file = self.files_to_process[0]

            # ── STEP 0: 클립 길이 사전 계산 ──
            get_logger().log(f"🎬 멀티클립: {total_files}개 클립 정보 수집 중...")

            if hasattr(self.ui, 'init_queue_list'):
                self.ui.init_queue_list(self.files_to_process)

            clip_boundaries = []
            cumulative = 0.0
            s = load_settings()
            model_key = get_model_key(s)
            total_expected = 0.0

            for i, target_file in enumerate(self.files_to_process):
                vname = os.path.basename(target_file)
                try:
                    info = probe_media(target_file)
                    clip_dur = info["duration"]
                    info_txt = info["info_txt"]
                    len_txt = info["len_txt"]

                    expected = get_expected_time(model_key, clip_dur)
                    if expected > 0:
                        total_expected += expected

                    if hasattr(self.ui, '_sig_update_queue'):
                        self.ui._sig_update_queue.emit(
                            i, "⏳ 대기 중", str(expected), info_txt, len_txt
                        )
                except Exception:
                    clip_dur = 30.0
                    info_txt = ""
                    len_txt = ""

                clip_boundaries.append({
                    "start": cumulative,
                    "end": cumulative + clip_dur,
                    "file": target_file,
                    "name": vname
                })
                cumulative += clip_dur
                get_logger().log(f"  📂 [{i+1}/{total_files}] {vname}: {clip_dur:.1f}초")

            self.total_expected_time = total_expected
            if total_expected > 0 and hasattr(self.ui, '_sig_update_queue_header'):
                t_mins, t_secs = int(total_expected // 60), int(total_expected % 60)
                t_hours = t_mins // 60
                if t_hours > 0:
                    t_mins = t_mins % 60
                    total_str = f"{t_hours}시간 {t_mins}분 {t_secs}초"
                else:
                    total_str = f"{t_mins}분 {t_secs}초"
                    self.ui._sig_update_queue_header.emit(1, total_files, 0, total_str)

            # 멀티클립 경계 정보를 UI에 전달 (에디터 열기 전)
            self.ui._multiclip_boundaries = clip_boundaries

            # ── STEP 1: 에디터 열기 (클립 박스만 표시, 파형 아직 없음) ──
            edit_event = threading.Event()
            start_event = threading.Event()
            self._edit_event = edit_event
            self._start_event = start_event
            final_segments = []
            action_state = ["wait"]
            self._action_state = action_state

            def on_save(segs):
                nonlocal final_segments
                final_segments = segs
                action_state[0] = "next"
                edit_event.set()

            def on_start():
                if getattr(self, 'is_first_start', True):
                    self.pipeline_start_time = time.time()
                    self.is_first_start = False
                action_state[0] = "start"
                start_event.set()

            def on_prev():
                action_state[0] = "prev"
                start_event.set()
                edit_event.set()

            def on_exit(segs):
                nonlocal final_segments
                final_segments = segs
                action_state[0] = "exit"
                self.stop()
                start_event.set()
                edit_event.set()

            self.ui.open_editor_for_file(
                first_file, on_save, on_start, on_prev, on_exit, is_batch=False
            )

            # 시작 버튼 대기
            if not start_event.wait(timeout=600):
                get_logger().log("❌ 시작 이벤트 타임아웃")
                return
            if action_state[0] in ("prev", "exit"):
                self.ui.request_show_home()
                return

            if action_state[0] in ("prev", "exit"):
                self.ui.request_show_home()
                return

            # ── 멀티클립 파형 로드 시작 (병렬) ──
            if hasattr(self.ui, '_sig_load_multiclip_waveform'):
                self.ui._sig_load_multiclip_waveform.emit(clip_boundaries)

            # ── STEP 2: 클립별 오디오 추출 + Whisper (순차) ──
            get_logger().log(f"\n🎤 멀티클립 STT 시작...")

            for i, target_file in enumerate(self.files_to_process):
                if not self._active:
                    return

                vname = os.path.basename(target_file)
                bd = clip_boundaries[i]
                offset = bd["start"]

                get_logger().log(f"\n{'='*44}\n🎬 [{i+1}/{total_files}] {vname}\n{'='*44}")

                if hasattr(self.ui, '_sig_update_queue'):
                    self.ui._sig_update_queue.emit(i, "⏳ 오디오 추출 중", "", "", "")

                self._backup_existing(target_file)
                res = self.video_processor.extract_audio(target_file)
                if not res:
                    get_logger().log(f"  ❌ 오디오 추출 실패: {vname}")
                    if hasattr(self.ui, '_sig_update_queue'):
                        self.ui._sig_update_queue.emit(i, "❌ 오류", "", "", "")
                    continue

                chunk_dir, vad_segs = res

                if hasattr(self.ui, '_sig_update_queue'):
                    self.ui._sig_update_queue.emit(i, "⏳ 자막 생성 중", "", "", "")

                get_logger().log(f"  🎤 Whisper 변환 중...")

                clip_segments = []
                for chunk_segs, c_idx, t_total in self.video_processor.transcribe(chunk_dir):
                    if not self._active:
                        return
                    clip_segments.extend(chunk_segs)
                get_logger().log(f"    📊 총 {len(clip_segments)}개 세그먼트")

                # 시간 오프셋 적용
                for seg in clip_segments:
                    seg["start"] += offset
                    seg["end"] += offset
                    seg["_clip_idx"] = i
                    if "words" in seg:
                        for w in seg["words"]:
                            w["start"] += offset
                            w["end"] += offset

                # 최적화
                from .subtitle_engine import optimize_segments
                opt = optimize_segments(clip_segments)
                for seg in opt:
                    if seg["start"] < 0.0:
                        seg["start"] = 0.0
                    if seg["end"] <= seg["start"]:
                        seg["end"] = seg["start"] + 0.5
                    seg["_clip_idx"] = i

                # 에디터에 즉시 전달 (클립 완료될 때마다)
                if hasattr(self.ui, '_sig_append_segments'):
                    self.ui._sig_append_segments.emit(opt)

                if hasattr(self.ui, '_sig_update_queue'):
                    self.ui._sig_update_queue.emit(i, "✅ 완료", "", "", "")

                get_logger().log(f"  ✅ 클립 {i+1} 자막 완료 ({len(opt)}개 세그먼트)")

            get_logger().log(f"\n🎊 전체 {total_files}개 클립 처리 완료! 에디터에서 편집 후 저장하세요.")

            if hasattr(self.ui, '_sig_update_status'):
                self.ui._sig_update_status.emit(total_files, total_files)

            # ── 편집 대기 ──
            edit_event.wait()

            if action_state[0] == "exit" or not self._active:
                self.ui.request_show_home()
                return

            # ── 통합 SRT 저장 ──
            if final_segments:
                from .subtitle_engine import save_srt
                from .path_manager import get_srt_path
                srt_path = get_srt_path(first_file)
                save_srt(final_segments, srt_path, apply_offset=True)
                get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료 (멀티클립 통합)")

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
