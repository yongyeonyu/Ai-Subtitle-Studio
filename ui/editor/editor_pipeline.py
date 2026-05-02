# Version: 03.02.15
# Phase: PHASE1-D
"""
ui/editor_pipeline.py
[v01.00.16] 모드/상태 정의 문서 반영
- _on_save: is_locked 체크 제거 (상태 무관 저장)
- _on_prev: 생성 중 중단 + 단일 다이얼로그 (main_window 중복 제거)
- update_progress: 완료 조건 단일화 (EditorPipeline만 완료 판단)
- 기존 기능 100% 유지
"""
import os, time, threading
from PyQt6.QtWidgets import QMessageBox, QMenu
from PyQt6.QtCore import QTimer, QPoint, QObject, pyqtSignal

import config
from logger import get_logger


class PartialSignals(QObject):
    status = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)
    chunk_time = pyqtSignal(float)
    done = pyqtSignal(list)
    finished = pyqtSignal()


class EditorPipelineMixin:
    # ---------------------------------------------------------
    # Backend Signal Hook
    # ---------------------------------------------------------
    def _hook_backend_signals(self):
        main_w = self.window()
        if hasattr(main_w, "backend") and main_w.backend:
            try: main_w.backend.sig_chunk_done.disconnect(self.append_segments)
            except Exception: pass
            try: main_w.backend.sig_progress.disconnect(self.update_progress)
            except Exception: pass
            try: main_w.backend.sig_chunk_done.connect(self.append_segments)
            except Exception: pass
            try: main_w.backend.sig_progress.connect(self.update_progress)
            except Exception: pass
            if getattr(self, 'is_batch_mode', False) and hasattr(main_w.backend, 'sig_batch_finished'):
                try: main_w.backend.sig_batch_finished.disconnect()
                except Exception: pass
                main_w.backend.sig_batch_finished.connect(self._on_batch_finished)

    def _on_batch_finished(self):
        self.sm.set_custom_status("✅ 배치 작업이 모두 완료되었습니다.")
        self._send_ntfy_batch_complete()

    def _send_ntfy_batch_complete(self):
        try:
            main_w = self.window()
            if not getattr(main_w, '_is_auto_pipeline', False):
                return
            from core.notifier import send_ntfy
            send_ntfy(
                title=f"🎉 {config.APP_NAME} 알림",
                message="🎬 모든 파일의 자막 생성이 완료되었습니다!",
                tags="tada,sparkles,clapper"
            )
        except Exception:
            pass

    # ---------------------------------------------------------
    # Pipeline & State Machine Logic
    # ---------------------------------------------------------
    def _trigger_auto_start(self):
        if not hasattr(self, 'btn_start'): return
        from core.state_manager import SubtitleStateManager
        if self.sm.state == SubtitleStateManager.ST_IDLE:
            self._on_start_clicked()

    def _tick_spinner(self):
        try:
            self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
        except RuntimeError: pass

    def _safe_enable_start_btn(self):
        try:
            if hasattr(self, 'btn_start') and self.btn_start:
                self.btn_start.setEnabled(True)
        except RuntimeError: pass

    def _stop_pipeline(self):
        main_w = self.window()
        if hasattr(main_w, "_stop_post_completion_idle_timer"):
            main_w._stop_post_completion_idle_timer()
        self.sm.stop_processing("작업이 중지되었습니다.")
        if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
        if hasattr(main_w, "backend") and main_w.backend:
            main_w.backend.stop()
        QTimer.singleShot(1000, self._safe_enable_start_btn)

    def _start_pipeline(self, is_restart=False):
        main_w = self.window()
        if hasattr(main_w, "_stop_post_completion_idle_timer"):
            main_w._stop_post_completion_idle_timer()
        try:
            from core.settings import load_settings
            latest_settings = load_settings()
            if latest_settings:
                self.settings.update(latest_settings)
                if hasattr(self, "_refresh_speaker_strip"):
                    self._refresh_speaker_strip()
        except Exception:
            pass
        self._completion_handled = False
        if getattr(self, 'is_auto_start', False):
            self.sm.start_auto_mode()
        else:
            self.sm.start_ai_all()
        self._process_start_time = time.time()
        self._backend_finished = False
        self._execute_pipeline_logic(is_restart)

    def _set_process_completed(self):
        if getattr(self, 'is_auto_start', False):
            self.sm.complete_auto_mode()
        else:
            self.sm.complete_ai()
        if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
        get_logger().log("✅ 자막 생성 완료 (EditorPipeline 확정)")
        main_w = self.window()
        if hasattr(main_w, "sync_menu_from_editor"):
            main_w.sync_menu_from_editor(self)
        if hasattr(main_w, "_refresh_saved_status_label"):
            main_w._refresh_saved_status_label(is_dirty=True)
        if hasattr(main_w, "_start_post_completion_idle_timer"):
            main_w._start_post_completion_idle_timer()
        if hasattr(main_w, "_release_ai_models_for_editor_mode"):
            QTimer.singleShot(0, lambda: main_w._release_ai_models_for_editor_mode(force=True))
        elif hasattr(self, "_schedule_post_generation_roughcut_draft"):
            QTimer.singleShot(350, lambda: self._schedule_post_generation_roughcut_draft(force=True))
        # E fix: 자막 생성 완료 후 타임라인/캔버스 재동기화
        QTimer.singleShot(200, self._post_completion_sync)

    def _post_completion_sync(self):
        """E fix: 자막 생성 완료 후 타임라인/글로벌 캔버스 재동기화"""
        try:
            self._redraw_timeline()
        except Exception:
            pass
        try:
            if hasattr(self, "timeline"):
                boxes = list(getattr(self.timeline.canvas, "_multiclip_boxes", []) or [])
                if boxes:
                    self.timeline.fit_to_view()
                    gc = self.timeline.global_canvas
                    gc.total_duration = self.timeline.canvas.total_duration
                    gc.update()
                    self.timeline.canvas.update()
                else:
                    self.timeline.fit_to_view()
        except Exception:
            pass
        try:
            if hasattr(self, "_resolve_active_context") and hasattr(self, "_apply_active_context"):
                ctx = self._resolve_active_context()
                self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
        except Exception:
            pass

    def _execute_pipeline_logic(self, is_restart):
        main_w = self.window()
        # 기존 자막이 사전 로드된 상태면 clear하지 않음
        if not self.text_edit.toPlainText().strip():
            self.text_edit.clear()
        self._segment_queue.clear()

        if is_restart:
            if hasattr(main_w, "backend") and main_w.backend:
                main_w.backend.restart_current_file()
            self._spinner_timer.start()
        else:
            self.sig_start.emit()
            self._spinner_timer.start()

        QTimer.singleShot(50, self._safe_enable_start_btn)
        
    def _on_start_clicked(self):
        from core.state_manager import SubtitleStateManager
        if getattr(self, "_stt_mode_enabled", False):
            if hasattr(self, "_start_stt_vad_detection") and self._start_stt_vad_detection():
                return
        if self.sm.state == SubtitleStateManager.ST_PROC:
            self._stop_pipeline()
        elif self.sm.state in [SubtitleStateManager.ST_COMP, SubtitleStateManager.ST_SAVED]:
            main_w = self.window()
            restarted = False
            if hasattr(main_w, "_restart_current_pipeline_from_beginning"):
                restarted = main_w._restart_current_pipeline_from_beginning(self)
            if restarted:
                self.sm.start_processing()
                if hasattr(self, "_spinner_timer"):
                    self._spinner_timer.start()
                return
            self._start_pipeline(is_restart=True)
        else:
            self._start_pipeline(is_restart=False)

    # ---------------------------------------------------------
    # Partial Recognition
    # ---------------------------------------------------------
    def _show_playhead_menu(self, gpos, sec):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { font-size: 13px; }")
        act_cur = menu.addAction("🎯 현재 자막 세그먼트만 재인식")
        act_end = menu.addAction("🚀 현재부터 끝까지 자막 재인식")
        action = menu.exec(gpos)
        if action == act_cur: self._re_recognize_segment(sec)
        elif action == act_end: self._re_recognize_from(sec)

    def _re_recognize_segment(self, sec):
        segs = self._get_current_segments()
        for s in segs:
            if s["start"] <= sec < s["end"]:
                self._run_partial_backend(s["start"], s["end"], is_single=True)
                break

    def _re_recognize_from(self, sec):
        segs = self._get_current_segments()
        start_sec = sec
        for s in segs:
            if s["start"] <= sec < s["end"]:
                start_sec = s["start"]
                break
        self._run_partial_backend(start_sec, 99999.0, is_single=False)

    def _update_partial_progress(self, sec):
        if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.re_recog_progress = sec
            self.timeline.canvas.update()

    def _run_partial_backend(self, start_sec, end_sec, is_single=False):
        main_w = self.window()
        if not (main_w and main_w.backend): return
        if is_single: self.sm.start_partial_segment()
        else: self.sm.start_partial_from_here()
        if hasattr(self, 'clear_segments_in_range'):
            self.clear_segments_in_range(start_sec, end_sec)
        if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.re_recog_zone = (start_sec, end_sec)
            self.timeline.canvas.re_recog_progress = start_sec
            self.timeline.canvas.update()
        self._partial_signals = PartialSignals()
        self._partial_signals.status.connect(self.update_status)
        self._partial_signals.progress.connect(self.update_progress)
        self._partial_signals.chunk_time.connect(self._update_partial_progress)
        if hasattr(self, 'insert_partial_segments'):
            self._partial_signals.done.connect(self.insert_partial_segments)
        def on_finished():
            if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
            self.sm.complete_ai()
            if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
                self.timeline.canvas.re_recog_zone = None
                self.timeline.canvas.update()
        self._partial_signals.finished.connect(on_finished)
        def _task():
            sig = self._partial_signals
            sig.status.emit("STATUS_PREPARING_AUDIO", "오디오 추출 및 정제 중...")
            chunks = []
            try:
                for chunk, idx, total in main_w.backend.video_processor.process_video(
                    getattr(self, 'media_path', ''), main_w,
                    main_w.backend.min_speakers, main_w.backend.max_speakers,
                    target_start_sec=start_sec, target_end_sec=end_sec,
                    is_single_segment=is_single
                ):
                    if idx == 1: sig.status.emit("STATUS_STT_CHUNKING", f"STT 청크 준비 중 ({start_sec:.1f}s~)")
                    if chunk:
                        sig.status.emit("STATUS_TRANSCRIBING", f"Whisper 자막 인식 중 ({idx}/{total})")
                        sig.chunk_time.emit(chunk[-1]["end"])
                        chunks.extend(chunk)
                    sig.progress.emit(idx, total)
                sig.status.emit("STATUS_INSERTING_SEGS", "자막 정밀 삽입 중...")
                sig.done.emit(chunks)
            except Exception as e:
                get_logger().log(f"⚠️ 재인식 중 치명적 오류: {e}")
            sig.finished.emit()
        threading.Thread(target=_task, daemon=True).start()

    # ---------------------------------------------------------
    # Progress & Status
    # ---------------------------------------------------------
    # ✅ [v01.00.16] 완료 조건 단일화 — EditorPipeline만 완료 판단
    def update_progress(self, c_idx, t_total):
        import threading as _th
        if _th.current_thread() is not _th.main_thread():
            QTimer.singleShot(0, lambda c=c_idx, t=t_total: self.update_progress(c, t))
            return

        total_vid_time = getattr(self.video_player, 'total_time', 0.0) if hasattr(self, 'video_player') else 0.0
        segs = self._get_current_segments()
        current_end = segs[-1].get('end', 0.0) if segs else 0.0

        if total_vid_time > 0 and current_end > 0:
            pct = min(100, int((current_end / total_vid_time) * 100))
        elif t_total > 0:
            pct = min(100, int((c_idx / t_total) * 100))
        else:
            pct = 0

        self.sm.update_progress(c_idx, t_total, pct)

        # ✅ 완료 조건 단일화
        if t_total > 0 and c_idx >= t_total and not getattr(self, '_completion_handled', False):
            self._completion_handled = True
            QTimer.singleShot(0, self._set_process_completed)

    def update_status(self, text, is_final=False, is_raw=False):
        import threading as _th
        if _th.current_thread() is not _th.main_thread():
            QTimer.singleShot(0, lambda t=text, f=is_final, r=is_raw: self.update_status(t, f, r))
            return
        if is_final or "에러" in text or "실패" in text:
            if "완료" in text: self.sm.complete_ai()
            else: self.sm.stop_processing(text)
            if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
        else:
            self.sm.set_custom_status(text)
