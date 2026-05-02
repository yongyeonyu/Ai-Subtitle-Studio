# Version: 03.08.05
# Phase: PHASE2
"""
ui/main/main_signals.py
SignalHandlersMixin — Qt 시그널 핸들러 (세그먼트 전달 · VAD · recog zone · LLM 웜업)
"""
import os

from PyQt6.QtWidgets import QMessageBox

import config
from logger import get_logger


class SignalHandlersMixin:
    """MainWindow 시그널 핸들러 모음."""

    def request_show_home(self):
        self._sig_show_home.emit()

    def append_segments_to_editor(self, segments):
        self._sig_append_segments.emit(segments)

    def preview_stt_segments_in_editor(self, segments):
        self._sig_preview_stt_segments.emit(segments)

    def refresh_cut_boundary_placeholder(self):
        self._sig_refresh_cut_boundary_placeholder.emit()

    def set_cut_boundary_scan_active(self, active: bool):
        self._sig_set_cut_boundary_scan_active.emit(bool(active))

    def preview_cut_boundary_scan(self, current_sec: float, next_sec: float = 0.0):
        self._sig_preview_cut_boundary_scan.emit(float(current_sec or 0.0), float(next_sec or 0.0))

    def update_editor_status(self, c_idx, t_total):
        self._sig_update_status.emit(c_idx, t_total)

    def append_log(self, msg):
        self.log_text.append(msg)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def _do_append_segments(self, segments):
        if self._editor_widget:
            self._editor_widget.append_segments(segments)

    def _do_preview_stt_segments(self, segments):
        if self._editor_widget and hasattr(self._editor_widget, "preview_stt_segments"):
            self._editor_widget.preview_stt_segments(segments)

    def _do_clear_editor(self):
        if hasattr(self, "_clear_editor_for_full_restart"):
            self._clear_editor_for_full_restart()
            return
        ed = getattr(self, '_editor_widget', None)
        if not ed:
            return
        try:
            if hasattr(ed, '_queue_timer') and ed._queue_timer.isActive():
                ed._queue_timer.stop()
        except Exception:
            pass
        try:
            if hasattr(ed, '_segment_queue'):
                ed._segment_queue.clear()
        except Exception:
            pass
        try:
            if hasattr(ed, 'text_edit'):
                ed.text_edit.clear()
        except Exception:
            pass
        try:
            if hasattr(ed, 'timeline'):
                ed.timeline.update_segments([], 0.0, getattr(ed.timeline.canvas, 'total_duration', 0.0))
                ed.timeline.set_playhead(0.0)
        except Exception:
            pass
        try:
            vp = getattr(ed, 'video_player', None)
            if vp is not None:
                vp.set_context_segments([])
                vp.seek(0.0)
        except Exception:
            pass
        try:
            ed._cached_segs = []
            ed._active_seg_start = 0.0
        except Exception:
            pass

    def _do_update_status(self, c_idx, t_total):
        if self._editor_widget:
            if hasattr(self._editor_widget, "update_progress"):
                self._editor_widget.update_progress(c_idx, t_total)

    def _do_restart_multiclip(self, files, folder=None):
        if not self.backend:
            return
        try:
            self.backend._force_no_reuse_once = True
        except Exception:
            pass
        self.backend.start_multiclip_pipeline(list(files or []), folder=folder)

    def _do_refresh_cut_boundary_placeholder(self):
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return
        roughcut = getattr(self, "_roughcut_widget", None)
        if roughcut is None:
            try:
                from ui.roughcut.roughcut_widget import RoughcutWidget

                roughcut = RoughcutWidget(owner=self, parent=self)
                self._roughcut_widget = roughcut
                self.stack.addWidget(roughcut)
            except Exception as exc:
                get_logger().log(f"⚠️ 컷 경계 placeholder 위젯 준비 실패: {exc}")
                return
        try:
            roughcut.refresh_from_editor(analyze_if_missing=False)
            self._editor_roughcut_result = getattr(roughcut, "_result", None)
        except Exception as exc:
            get_logger().log(f"⚠️ 컷 경계 placeholder 갱신 실패: {exc}")
            return
        try:
            if hasattr(editor, "_redraw_timeline"):
                editor._redraw_timeline()
        except Exception:
            pass

    def open_editor_for_file(
        self, target_file, on_save, on_start, on_prev, on_exit, is_batch=False
    ):
        self._sig_open_editor.emit(
            target_file, on_save, on_start, on_prev, on_exit, is_batch
        )

    def _do_open_editor(
        self, target_file, on_save, on_start, on_prev, on_exit, is_batch=False
    ):
        self._on_save_cb = on_save
        self._on_start_cb = on_start
        self._on_prev_cb = on_prev
        self._on_exit_cb = on_exit
        self._target_file = target_file
        self._init_editor(target_file, is_batch)

    def _do_load_multiclip_waveform(self, clip_boundaries):
        if self._editor_widget and hasattr(self._editor_widget, "timeline"):
            self._editor_widget.timeline.load_multiclip_waveform(clip_boundaries)

    def _on_vad_segments(self, vad_segs):
        if not self._editor_widget:
            return
        # 멀티클립: VAD 시간을 현재 클립 offset만큼 보정 + 누적
        if hasattr(self, "_multiclip_boundaries") and self._multiclip_boundaries:
            ci = max(0, getattr(self, "_current_file_idx", 1) - 1)
            if ci < len(self._multiclip_boundaries):
                offset = self._multiclip_boundaries[ci]["start"]
                vad_segs = [
                    {**v, "start": v["start"] + offset, "end": v["end"] + offset}
                    for v in vad_segs
                ]
            if not hasattr(self, "_accumulated_vad"):
                self._accumulated_vad = []
            self._accumulated_vad.extend(vad_segs)
            self._editor_widget.set_vad_segments(list(self._accumulated_vad))
        else:
            self._editor_widget.set_vad_segments(vad_segs)

    def _on_recog_zone(self, start_sec, end_sec):
        if not self._editor_widget:
            return
        canvas = getattr(
            getattr(self._editor_widget, "timeline", None), "canvas", None
        )
        if not canvas:
            return
        if start_sec < 0:
            canvas.re_recog_zone = None
            canvas.re_recog_progress = None
        else:
            canvas.re_recog_zone = (start_sec, end_sec)
            canvas.re_recog_progress = start_sec
        canvas.update()

    def _on_recog_progress(self, progress_sec):
        if not self._editor_widget:
            return
        canvas = getattr(
            getattr(self._editor_widget, "timeline", None), "canvas", None
        )
        if not canvas:
            return
        canvas.re_recog_progress = progress_sec
        canvas.update()

    def _on_cut_boundary_scan_active(self, active: bool):
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return
        handler = getattr(editor, "_set_auto_cut_boundary_scan_active", None)
        if callable(handler):
            try:
                handler(bool(active))
            except Exception as exc:
                get_logger().log(f"⚠️ 자동 컷 경계 스캔 상태 반영 실패: {exc}")

    def _on_cut_boundary_scan_preview(self, current_sec: float, next_sec: float):
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return
        handler = getattr(editor, "_preview_auto_cut_boundary_scan", None)
        if callable(handler):
            try:
                handler(float(current_sec or 0.0), float(next_sec or 0.0))
            except Exception as exc:
                get_logger().log(f"⚠️ 자동 컷 경계 스캔 프리뷰 실패: {exc}")

    def _warmup_local_llm_models(self):
        import threading
        def _scan():
            try:
                from core.model_manager import get_local_llm_models
                models = get_local_llm_models()
                if not models:
                    models = [{
                        "name": getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"),
                        "size": 0, "details": {},
                    }]
                self._local_llm_models = models
            except Exception as e:
                self._local_llm_models = [{
                    "name": getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"),
                    "size": 0, "details": {},
                }]
                get_logger().log(f"⚠️ 로컬 LLM 자동 스캔 실패: {e}")
        threading.Thread(target=_scan, daemon=True, name="llm-warmup").start()

    def _check_required_models_on_startup(self):
        if getattr(self, "_required_model_check_done", False):
            return
        self._required_model_check_done = True
        try:
            from core.model_manager import get_current_os, get_required_models
            missing = get_required_models()
        except Exception as e:
            get_logger().log(f"⚠️ 필수 AI 모델 확인 실패: {e}")
            return
        if not missing:
            get_logger().log("✅ 필수 AI 모델 확인 완료")
            return

        names = [m.get("name", m.get("id", "unknown")) for m in missing]
        get_logger().log("⚠️ 필수 AI 모델 미설치: " + ", ".join(names))
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return

        QMessageBox.warning(
            self,
            "필수 AI 모델 확인",
            f"현재 OS({get_current_os()})에서 필요한 AI 모델이 아직 준비되지 않았습니다.\n\n"
            + "\n".join(f"- {name}" for name in names)
            + "\n\n설정 > AI 엔진 설정 > 모델 관리에서 설치 상태를 확인하세요."
        )
