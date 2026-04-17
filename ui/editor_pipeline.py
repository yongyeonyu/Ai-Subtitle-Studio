# Version: 01.00.12
"""
ui/editor_pipeline.py
[v01.00.12 수정사항]
- _on_prev: 저장 여부 확인 다이얼로그(예/아니요/취소) 추가 — 종료 기능 마이그레이션
- _on_next: "개발중입니다" 알림창 표시
- _on_exit: 내부 참조용으로 유지 (window closeEvent에서 사용)
"""
import os, time, threading
from PyQt6.QtWidgets import QMessageBox, QMenu
from PyQt6.QtCore import QTimer, QPoint, QObject, pyqtSignal

import config
from logger import get_logger
from core.data_manager import save_settings as _dm_save_settings
from core.subtitle_engine import save_srt
from core.path_manager import get_srt_path

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
        import config, urllib.request, base64
        topic = getattr(config, "NTFY_TOPIC", "")
        if not topic: return
        url = f"https://ntfy.sh/{topic}"
        msg = "🎉🎬 모든 파일의 자막 생성이 완료되었습니다! 작업 완료!"
        title = f"{config.APP_NAME} 알림"
        data = base64.b64encode(msg.encode("utf-8")).decode("utf-8")
        req = urllib.request.Request(url, data=data.encode("utf-8"), method="POST")
        req.add_header("Title", base64.b64encode(title.encode("utf-8")).decode("utf-8"))
        req.add_header("Encoding", "base64")
        req.add_header("Tags", "tada,sparkles,clapper")
        urllib.request.urlopen(req, timeout=5)
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
        self.sm.stop_processing("작업이 중지되었습니다.")
        if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
        main_w = self.window()
        if hasattr(main_w, "backend") and main_w.backend:
            main_w.backend.stop()
        QTimer.singleShot(1000, self._safe_enable_start_btn)
    
    def _start_pipeline(self, is_restart=False):
        if getattr(self, 'is_auto_start', False):
            self.sm.start_auto_mode()
        else:
            self.sm.start_ai_all()
            
        self._process_start_time = time.time()
        self._backend_finished = False 
        QTimer.singleShot(50, lambda: self._execute_pipeline_logic(is_restart))

    def _set_process_completed(self):
        if getattr(self, 'is_auto_start', False):
            self.sm.complete_auto_mode()
        else:
            self.sm.complete_ai()
            
        if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
    
    def _execute_pipeline_logic(self, is_restart):
        main_w = self.window()
        self.text_edit.clear()
        self._segment_queue.clear()
        if is_restart:
            if hasattr(main_w, "backend") and main_w.backend:
                main_w.backend.restart_current_file()
            self._spinner_timer.start()
        else:
            self.sig_start.emit()
            self._spinner_timer.start()
        QTimer.singleShot(500, self._safe_enable_start_btn)

    def _on_start_clicked(self):
        from core.state_manager import SubtitleStateManager
        if self.sm.state == SubtitleStateManager.ST_PROC:
            self._stop_pipeline()
        elif self.sm.state in [SubtitleStateManager.ST_COMP, SubtitleStateManager.ST_SAVED]:
            self._start_pipeline(is_restart=True)
        else:
            self._start_pipeline(is_restart=False)

    # ---------------------------------------------------------
    # Main Button Actions & Dialogs
    # ---------------------------------------------------------
    def _show_confirm_dialog(self, title: str, text: str) -> QMessageBox.StandardButton:
        """예/아니요/취소 다이얼로그 공통 헬퍼"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No  |
            QMessageBox.StandardButton.Cancel
        )
        msg_box.button(QMessageBox.StandardButton.Yes).setText("예")
        msg_box.button(QMessageBox.StandardButton.No).setText("아니요")
        msg_box.button(QMessageBox.StandardButton.Cancel).setText("취소")
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
        return msg_box.exec()

    def _on_prev(self):
        """[v01.00.12] 종료 기능 마이그레이션: 저장 여부 확인 후 메인 화면으로 복귀"""
        from core.state_manager import SubtitleStateManager
        if self.sm.state == SubtitleStateManager.ST_PROC:
            QMessageBox.warning(self, "작업 중", "AI 작업 중에는 이동할 수 없습니다.")
            return

        if not self.sm.is_dirty:
            # 변경사항 없으면 바로 복귀
            self.sig_prev.emit()
            if hasattr(self.window(), 'show_home'):
                self.window().show_home()
            return

        reply = self._show_confirm_dialog(
            "메인 화면으로 이동",
            "수정된 내용을 저장하시겠습니까?"
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._on_save()
            self.sig_prev.emit()
            if hasattr(self.window(), 'show_home'):
                self.window().show_home()
        elif reply == QMessageBox.StandardButton.No:
            self.sig_prev.emit()
            if hasattr(self.window(), 'show_home'):
                self.window().show_home()
        # Cancel: 아무것도 안 함

    def _on_save(self, *args, skip_auto_next=False):
        if self.sm.is_locked: return
        segs = self._get_current_segments()
        if getattr(self, 'media_path', None):
            srt_path = get_srt_path(self.media_path)
            save_srt(segs, srt_path)
            self.sm.complete_save()
            self.sig_save.emit(segs)

    def _on_exit(self):
        """내부용: window closeEvent 에서 호출. 예/아니요/취소 다이얼로그."""
        if not self.sm.is_dirty:
            if hasattr(self.window(), 'show_home'):
                self.window().show_home()
            return

        reply = self._show_confirm_dialog(
            "편집 종료",
            "수정된 내용을 저장하시겠습니까?"
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._on_save()
            if hasattr(self.window(), 'show_home'):
                self.window().show_home()
        elif reply == QMessageBox.StandardButton.No:
            if hasattr(self.window(), 'show_home'):
                self.window().show_home()
        # Cancel: 아무것도 안 함

    def _on_next(self):
        """[v01.00.12] 개발 중 알림"""
        # 💡 [고스트 클릭 방어] 자동 모드일 때는 포커스 튐 현상으로 인한 클릭을 무시합니다.
        #if getattr(self, 'is_batch_mode', False):
        #    return
            
        QMessageBox.information(self, "알림", "개발중입니다.")

    def _show_export_dialog(self):
        from ui.export_dialog import ExportDialog
        segs = self._get_current_segments()
        if segs:
            dlg = ExportDialog(segs, getattr(self, 'video_name', ''), self)
            if hasattr(self, 'video_player'):
                dlg._video_player_ref = self.video_player
            dlg.exec()

    def _show_settings(self):
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings = dlg.result_settings
            _dm_save_settings(self.settings)
            if hasattr(self, '_update_engine_label_text'): self._update_engine_label_text()

    def _show_adv_settings(self):
        from ui.settings_dialog import AdvancedSettingsDialog
        dlg = AdvancedSettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings.update(dlg.result)
            _dm_save_settings(self.settings)

    def _show_speaker_settings(self):
        from ui.settings_dialog import SpeakerDialog
        dlg = SpeakerDialog(self.settings, self)
        if dlg.exec():
            self.settings.update(dlg.result)
            _dm_save_settings(self.settings)
            if hasattr(self, '_update_highlighter_colors'): self._update_highlighter_colors()

    def _show_gap_settings(self):
        from ui.settings_dialog import GapSettingsDialog
        dlg = GapSettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings.update(dlg.result)
            _dm_save_settings(self.settings)

    # ---------------------------------------------------------
    # Partial Recognition (부분 재인식 로직)
    # ---------------------------------------------------------
    def _show_playhead_menu(self, gpos: QPoint, sec: float):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { font-size: 13px; }")
        act_cur = menu.addAction("🎯 현재 자막 세그먼트만 재인식")
        act_end = menu.addAction("🚀 현재부터 끝까지 자막 재인식")
        action = menu.exec(gpos)
        if action == act_cur: self._re_recognize_segment(sec)
        elif action == act_end: self._re_recognize_from(sec)

    def _re_recognize_segment(self, sec: float):
        segs = self._get_current_segments()
        for s in segs:
            if s["start"] <= sec < s["end"]:
                self._run_partial_backend(s["start"], s["end"], is_single=True)
                break

    def _re_recognize_from(self, sec: float):
        segs = self._get_current_segments()
        start_sec = sec
        for s in segs:
            if s["start"] <= sec < s["end"]:
                start_sec = s["start"] 
                break
        self._run_partial_backend(start_sec, 99999.0, is_single=False)

    def _update_partial_progress(self, sec: float):
        if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.re_recog_progress = sec
            self.timeline.canvas.update()

    def _run_partial_backend(self, start_sec: float, end_sec: float, is_single: bool = False):
        main_w = self.window()
        if not (main_w and main_w.backend): return
        
        if is_single:
            self.sm.start_partial_segment()
        else:
            self.sm.start_partial_from_here()
        
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
                    if idx == 1: 
                        sig.status.emit("STATUS_VAD_SCANNING", f"선발대 탐색 중 ({start_sec:.1f}s~)")
                    if chunk:
                        sig.status.emit("STATUS_TRANSCRIBING", f"후발대 자막 생성 중 ({idx}/{total})")
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
    # Progress & Status (상태 머신 연동)
    # ---------------------------------------------------------
    def update_progress(self, c_idx: int, t_total: int):
        import threading
        if threading.current_thread() is not threading.main_thread():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda c=c_idx, t=t_total: self.update_progress(c, t))
            return
            
        if c_idx >= t_total and t_total > 0:
            self._backend_finished = True

        total_vid_time = self.video_player.total_time if hasattr(self, 'video_player') else 1.0
        segs = self._get_current_segments()
        current_end = segs[-1].get('end', 0.0) if segs else 0.0
        pct = min(100, int((current_end / total_vid_time) * 100))
        
        self.sm.update_progress(c_idx, t_total, pct)

    def update_status(self, text: str, is_final: bool = False, is_raw: bool = False):
        import threading
        if threading.current_thread() is not threading.main_thread():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda t=text, f=is_final, r=is_raw: self.update_status(t, f, r))
            return
            
        if is_final or "에러" in text or "실패" in text:
            if "완료" in text:
                self.sm.complete_ai()
            else:
                self.sm.stop_processing(text)
            if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
        else:
            self.sm.set_custom_status(text)
