# Version: 02.02.01
# Phase: PHASE1-B
"""
ui/main/main_signals.py
SignalHandlersMixin — Qt 시그널 핸들러 (세그먼트 전달 · VAD · recog zone · LLM 웜업)
"""
import config
from logger import get_logger


class SignalHandlersMixin:
    """MainWindow 시그널 핸들러 모음."""

    def request_show_home(self):
        self._sig_show_home.emit()

    def append_segments_to_editor(self, segments):
        self._sig_append_segments.emit(segments)

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

    def _do_update_status(self, c_idx, t_total):
        if self._editor_widget:
            if hasattr(self._editor_widget, "update_progress"):
                self._editor_widget.update_progress(c_idx, t_total)

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
                    {"start": v["start"] + offset, "end": v["end"] + offset}
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
