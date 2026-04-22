# Version: 02.02.00
# Phase: PHASE1-B
"""
core/pipeline/single_pipeline.py
SinglePipelineMixin — 단일 파일 / 배치 파이프라인 (_run_all, _process_one)
"""
import os
import threading
import traceback
import queue
import time

import config
from logger import get_logger
from core.settings import load_settings, get_model_key
from core.time_history import get_expected_time, add_history

_SENTINEL = object()


class SinglePipelineMixin:
    """단일 / 배치 품질모드 파이프라인."""

    def _run_all(self):
        total_files = len(self.files_to_process)

        try:
            for i, target_file in enumerate(self.files_to_process):
                if not self._active:
                    return

                if hasattr(self.ui, "_sig_update_queue"):
                    self.ui._sig_update_queue.emit(i, "⏳ 오디오 추출 중", "", "", "")
                if hasattr(self.ui, "_sig_update_queue_header"):
                    self.ui._sig_update_queue_header.emit(i + 1, total_files, 0, "")

                self._process_one(target_file, i)

            if getattr(self.ui, "_is_auto_pipeline", False):
                self._send_ntfy_notification(
                    title=f"🏆 {config.APP_NAME} 작업 종료",
                    message=f"🎉 {total_files}개 파일 처리 완료!\n아이패드에서 확인해 보세요, 대표님.",
                    tags="checkered_flag,tada",
                )

        except Exception as e:
            if str(e) not in ("USER_PREV", "USER_EXIT"):
                get_logger().log(f"\n❌ 치명적 에러: {e}")
                get_logger().log(traceback.format_exc())

        finally:
            self._active = False
            try:
                if hasattr(self.ui, "request_show_home"):
                    self.ui.request_show_home()
            except Exception:
                pass

    def _process_one(self, target_file, queue_index):
        # ── STEP 0: 백업 ──
        self._backup_existing(target_file)

        # ── 이벤트/콜백 ──
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
            start_event.set()
            edit_event.set()

        def on_start():
            if getattr(self, "is_first_start", True):
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

        # 변경: 첫 파일은 수동, 이후 파일은 자동 진행
        is_auto_mode = getattr(self, "is_auto_start", False) or (
            queue_index > 0 and len(self.files_to_process) > 1
        )

        self.ui.open_editor_for_file(
            target_file, on_save, on_start, on_prev, on_exit, is_batch=is_auto_mode
        )

        if is_auto_mode:
            threading.Timer(0.05, on_start).start()

        if not start_event.wait(timeout=600):
            get_logger().log("❌ 시작 이벤트 타임아웃 (600초)")
            return
        if action_state[0] == "prev":
            self.ui.request_show_home()
            raise Exception("USER_PREV")
        if action_state[0] == "exit":
            self.ui.request_show_home()
            raise Exception("USER_EXIT")
        if action_state[0] == "next":
            return

        # ── STT 파이프라인 루프 ──
        while True:
            self._active = True
            self._speaker_map = []
            edit_event.clear()
            self._reload_speaker_settings()
            vname = os.path.basename(target_file)
            fsize = (
                os.path.getsize(target_file) / (1024 * 1024)
                if os.path.exists(target_file)
                else 0
            )

            get_logger().log(
                f"\n{'=' * 44}\n🎬 [{queue_index + 1}/{len(self.files_to_process)}] {vname}"
                f"\n{'=' * 44}\n\n{'─' * 44}\n  📂 파일: {vname} ({fsize:.1f} MB)\n{'─' * 44}"
            )

            res = self._get_audio_extract_result(target_file)

            next_file = (
                self.files_to_process[queue_index + 1]
                if (queue_index + 1) < len(self.files_to_process)
                else None
            )
            if next_file:
                self._prefetch_audio_for_file(next_file)

            if not res:
                get_logger().log("❌ 오디오 추출 실패")
                if hasattr(self.ui, "_sig_update_queue"):
                    try:
                        self.ui._sig_update_queue.emit(queue_index, "❌ 오류", "", "", "")
                    except RuntimeError:
                        pass

                if action_state[0] == "restart":
                    get_logger().log("\n🔄 재시작합니다...")
                    action_state[0] = "next"
                    continue

                return

            chunk_dir, vad_segs = res
            if hasattr(self.ui, "_sig_set_vad_segments"):
                self.ui._sig_set_vad_segments.emit(vad_segs)

            get_logger().log("\n  [STEP 2] 🎤 Whisper 변환 + LLM 최적화 파이프라인 가동...")

            try:
                s = load_settings()
                model_key = "QUALITY:" + get_model_key(s)

                if target_file in getattr(self, "_video_durations", {}):
                    video_duration_sec = self._video_durations[target_file]
                else:
                    chunks = [f for f in os.listdir(chunk_dir) if f.endswith(".wav")]
                    video_duration_sec = len(chunks) * 30.0

                expected_time = get_expected_time(model_key, video_duration_sec)
                if hasattr(self.ui, "_sig_update_queue"):
                    if expected_time > 0:
                        self.ui._sig_update_queue.emit(
                            queue_index, "자막 생성 중", str(expected_time), "", ""
                        )
                    else:
                        self.ui._sig_update_queue.emit(
                            queue_index, "자막 생성 중", "예상불가 (학습 중)", "", ""
                        )
                process_start_time = time.time()
            except Exception:
                process_start_time = time.time()
                video_duration_sec = 0.0

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
                wav_in_chunks = sorted(
                    [
                        os.path.join(chunk_dir, f)
                        for f in os.listdir(chunk_dir)
                        if f.endswith(".wav")
                    ]
                )
                audio_for_diarization = (
                    wav_in_chunks[0] if wav_in_chunks else target_file
                )

            t_diarize = None
            if self.max_speakers > 1:
                t_diarize = threading.Thread(
                    target=self._prepare_speaker_map,
                    args=(audio_for_diarization,),
                    daemon=True,
                    name="diarizer",
                )
                t_diarize.start()

            auto_collected_segs = []

            def do_transcribe():
                try:
                    for chunk_segs, c_idx, t_total in self.video_processor.transcribe(
                        chunk_dir, is_fast_mode=False
                    ):
                        if not self._active:
                            break
                        opt_queue.put((chunk_segs, c_idx, t_total))
                finally:
                    opt_queue.put(_SENTINEL)

            def do_optimize():
                from core.subtitle_engine import optimize_segments

                total_files = len(self.files_to_process)

                if t_diarize and t_diarize.is_alive():
                    get_logger().log("\n⏳ [안내] 화자 분리 연산 대기 중...")
                    t_diarize.join()

                try:
                    s = load_settings()
                    model_name = s.get("selected_model", "기본")
                    api_key = s.get("google_api_key", "")
                    user_prompt = s.get("custom_prompt", "")
                    chunk_time_limit = int(s.get("chunk_time_limit", 60))
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
                    if not seg_buffer:
                        return
                    chunk_segs = seg_buffer
                    seg_buffer = []

                    try:
                        if is_gemini and len(chunk_segs) > 1:
                            from core.subtitle_engine import ask_gemini_to_split
                            from core.utils import load_subtitle_rules

                            chunk_start = chunk_segs[0]["start"]
                            chunk_end = chunk_segs[-1]["end"]
                            full_text = " ".join([seg["text"] for seg in chunk_segs])
                            rules = load_subtitle_rules()
                            res_chunks = ask_gemini_to_split(
                                full_text, 15, rules, model_name, user_prompt, api_key
                            )
                            if res_chunks and len(res_chunks) > 0:
                                opt = []
                                dur = (chunk_end - chunk_start) / len(res_chunks)
                                for i, txt in enumerate(res_chunks):
                                    opt.append(
                                        {
                                            "start": round(chunk_start + i * dur, 3),
                                            "end": round(
                                                chunk_start + (i + 1) * dur, 3
                                            ),
                                            "text": txt,
                                        }
                                    )
                            else:
                                opt = optimize_segments(chunk_segs)
                        else:
                            opt = optimize_segments(chunk_segs)
                    except Exception as e:
                        get_logger().log(f"  ❌ 최적화 오류: {e}")
                        opt = chunk_segs

                    for seg in opt:
                        if seg["start"] < 0.0:
                            seg["start"] = 0.0
                        if seg["end"] <= seg["start"]:
                            seg["end"] = seg["start"] + 0.5

                    if self.max_speakers > 1 and self._speaker_map:
                        from core.audio.diarize import get_speaker_for_segment

                        for seg in opt:
                            spk_full = get_speaker_for_segment(
                                seg["start"], seg["end"], self._speaker_map
                            )
                            seg["speaker"] = spk_full.replace("SPEAKER_", "")

                        grouped_opt = []
                        for seg in opt:
                            text = seg.get("text", "").strip()
                            if text.startswith("-"):
                                text = text.lstrip("-").strip()
                            spk = seg.get("speaker", "00")
                            if not grouped_opt:
                                seg["text_list"] = [text]
                                seg["speaker_list"] = [spk]
                                grouped_opt.append(seg)
                            else:
                                prev = grouped_opt[-1]
                                gap = seg["start"] - prev["end"]
                                if (
                                    gap < 1.5
                                    and spk != prev["speaker_list"][-1]
                                    and len(prev["speaker_list"]) < 2
                                ):
                                    prev["text_list"].append(text)
                                    prev["speaker_list"].append(spk)
                                    prev["end"] = max(prev["end"], seg["end"])
                                else:
                                    seg["text_list"] = [text]
                                    seg["speaker_list"] = [spk]
                                    grouped_opt.append(seg)

                        for seg in grouped_opt:
                            if len(seg.get("text_list", [])) > 1:
                                seg["text"] = (
                                    f"- {seg['text_list'][0]}\n- {seg['text_list'][1]}"
                                )
                            else:
                                seg["text"] = (
                                    seg["text_list"][0]
                                    if "text_list" in seg
                                    else seg.get("text", "")
                                )
                            if "text_list" in seg:
                                del seg["text_list"]
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
                        overall_pct = int(
                            ((queue_index + (c_idx / t_total)) / total_files) * 100
                        )
                    else:
                        overall_pct = int((queue_index / total_files) * 100)

                    if hasattr(self.ui, "_sig_update_status"):
                        self.ui._sig_update_status.emit(c_idx, t_total)

                    try:
                        if hasattr(self.ui, "_sig_update_queue_header"):
                            self.ui._sig_update_queue_header.emit(
                                queue_index + 1, total_files, overall_pct, ""
                            )
                    except RuntimeError:
                        pass

                    if not chunk_segs:
                        try:
                            if hasattr(self.ui, "_sig_update_status"):
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

                if hasattr(self.ui, "_sig_update_status"):
                    self.ui._sig_update_status.emit(last_t_total, last_t_total)

            t_trans = threading.Thread(
                target=do_transcribe, daemon=True, name="transcriber"
            )
            t_opt = threading.Thread(target=do_optimize, daemon=True, name="optimizer")
            t_trans.start()
            t_opt.start()
            t_trans.join()
            t_opt.join()

            # ✅ STT 완료 → 큐 즉시 업데이트
            if hasattr(self.ui, "_sig_update_queue"):
                try:
                    self.ui._sig_update_queue.emit(
                        queue_index, "✅ 자막 생성 완료", "", "", ""
                    )
                except RuntimeError:
                    pass

            try:
                s = load_settings()
                model_key = "QUALITY:" + get_model_key(s)
                proc_time = time.time() - process_start_time
                add_history(model_key, video_duration_sec, proc_time)
            except Exception:
                pass

            if is_auto_mode:
                nonlocal_final = auto_collected_segs[:]

                def _auto_proceed():
                    nonlocal final_segments
                    final_segments = nonlocal_final
                    action_state[0] = "next"
                    edit_event.set()

                threading.Timer(0.05, _auto_proceed).start()

            edit_event.wait()

            if action_state[0] == "restart":
                self._handle_restart(target_file)
                action_state[0] = "next"
                continue

            if not self._active:
                return
            if action_state[0] == "prev":
                self.ui.request_show_home()
                raise Exception("USER_PREV")
            if action_state[0] == "exit":
                self.ui.request_show_home()
                raise Exception("USER_EXIT")
            break

        # ── STEP 5~6: 저장 + 내보내기 ──
        self._save_and_export(target_file, queue_index, final_segments, is_auto_mode)

        if action_state[0] == "exit" or not getattr(self, "_active", True):
            try:
                if hasattr(self, "ui") and self.ui:
                    self.ui.request_show_home()
            except RuntimeError:
                pass
            raise Exception("USER_EXIT")
