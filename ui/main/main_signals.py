# Version: 03.08.05
# Phase: PHASE2
"""
ui/main/main_signals.py
SignalHandlersMixin — Qt 시그널 핸들러 (세그먼트 전달 · VAD · recog zone · LLM 웜업)
"""
import os
import threading

from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.runtime import config
from core.runtime.logger import get_logger


class SignalHandlersMixin:
    """MainWindow 시그널 핸들러 모음."""

    def request_show_home(self):
        self._sig_show_home.emit()

    def append_segments_to_editor(self, segments):
        self._sig_append_segments.emit(segments)

    def append_segments_to_editor_and_wait(self, segments, timeout_sec: float = 2.0):
        app = QApplication.instance()
        if app is not None and QThread.currentThread() == app.thread():
            self._do_append_segments(segments, flush=True)
            return True
        ready_event = threading.Event()
        self._sig_append_segments_ready.emit(list(segments or []), ready_event)
        try:
            timeout = max(0.1, float(timeout_sec or 2.0))
        except Exception:
            timeout = 2.0
        return bool(ready_event.wait(timeout))

    def preview_stt_segments_in_editor(self, segments):
        self._sig_preview_stt_segments.emit(segments)

    def refresh_cut_boundary_placeholder(self):
        self._sig_refresh_cut_boundary_placeholder.emit()

    def set_cut_boundary_scan_active(self, active: bool):
        self._sig_set_cut_boundary_scan_active.emit(bool(active))

    def preview_cut_boundary_scan(self, current_sec: float, next_sec: float = 0.0):
        self._sig_preview_cut_boundary_scan.emit(float(current_sec or 0.0), float(next_sec or 0.0))

    def preview_cut_boundary_scan_lines(self, times):
        self._sig_preview_cut_boundary_scan_lines.emit(list(times or []))

    def update_project_boundary_times(self, times):
        self._sig_update_project_boundary_times.emit(list(times or []))

    def update_editor_status(self, c_idx, t_total):
        self._sig_update_status.emit(c_idx, t_total)

    def append_log(self, msg):
        self.log_text.append(msg)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
        if not bool(getattr(self, "_sidebar_engine_refresh_pending", False)):
            self._sidebar_engine_refresh_pending = True

            def _refresh():
                self._sidebar_engine_refresh_pending = False
                refresher = getattr(self, "_refresh_sidebar_engine_info", None)
                if callable(refresher):
                    refresher()

            QTimer.singleShot(80, _refresh)

    def _do_append_segments(self, segments, *, flush: bool = False):
        if self._editor_widget:
            self._editor_widget.append_segments(segments)
            if flush:
                flusher = getattr(self._editor_widget, "_flush_pending_segment_queue_now", None)
                if callable(flusher):
                    flusher()
                elif hasattr(self._editor_widget, "_flush_queue"):
                    try:
                        self._editor_widget._flush_queue()
                    except Exception:
                        pass
                QApplication.processEvents()

    def _do_append_segments_ready(self, segments, ready_event):
        try:
            self._do_append_segments(segments, flush=True)
        finally:
            if hasattr(ready_event, "set"):
                try:
                    ready_event.set()
                except Exception:
                    pass

    def _do_preview_stt_segments(self, segments):
        if self._editor_widget and hasattr(self._editor_widget, "preview_stt_segments"):
            self._editor_widget.preview_stt_segments(segments)

    def _do_set_llm_review_segment(self, payload):
        editor = getattr(self, "_editor_widget", None)
        if editor is not None and hasattr(editor, "set_live_processing_stage"):
            data = dict(payload or {})
            if data.get("active"):
                idx = int(data.get("idx", 0) or 0) + 1
                total = max(1, int(data.get("total", 1) or 1))
                sample = str(data.get("text", "") or "").strip().replace("\n", " ")
                if len(sample) > 34:
                    sample = sample[:34] + "..."
                suffix = f" · {sample}" if sample else ""
                editor.set_live_processing_stage(f"자막 LLM 검수 중 ({idx}/{total}){suffix}")
        timeline = getattr(editor, "timeline", None) if editor is not None else None
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        setter = getattr(canvas, "set_llm_review_segment", None) if canvas is not None else None
        if callable(setter):
            setter(dict(payload or {}))

    def _do_editor_processing_stage(self, text):
        editor = getattr(self, "_editor_widget", None)
        setter = getattr(editor, "set_live_processing_stage", None) if editor is not None else None
        if callable(setter):
            setter(str(text or ""))

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
            for attr, value in (
                ("_live_editor_preview_queue", []),
                ("_live_editor_preview_segments", []),
                ("_live_editor_preview_keys", set()),
            ):
                if hasattr(ed, attr):
                    setattr(ed, attr, value.copy() if hasattr(value, "copy") else value)
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
        refresh_from_editor = getattr(roughcut, "refresh_from_editor", None)
        if callable(refresh_from_editor):
            try:
                refresh_from_editor(analyze_if_missing=False)
            except Exception as exc:
                get_logger().log(f"⚠️ 컷 경계 placeholder 갱신 실패: {exc}")
                return
        self._editor_roughcut_result = getattr(roughcut, "_result", None)
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

    def open_editor_for_file_and_wait(
        self,
        target_file,
        on_save,
        on_start,
        on_prev,
        on_exit,
        is_batch=False,
        timeout_sec: float = 5.0,
    ) -> bool:
        target = str(target_file or "")
        if not target:
            return False
        app = QApplication.instance()
        if app is not None and QThread.currentThread() == app.thread():
            self._do_open_editor(target, on_save, on_start, on_prev, on_exit, is_batch)
            return True
        ready_event = threading.Event()
        self._sig_open_editor_ready.emit(
            target, on_save, on_start, on_prev, on_exit, is_batch, ready_event
        )
        try:
            timeout = max(0.1, float(timeout_sec or 5.0))
        except Exception:
            timeout = 5.0
        return bool(ready_event.wait(timeout))

    def ensure_processing_editor(self, target_file, timeout_sec: float = 5.0) -> bool:
        target = str(target_file or "")
        if not target:
            return False
        app = QApplication.instance()
        if app is not None and QThread.currentThread() == app.thread():
            self._do_prepare_processing_editor(target)
            return True
        ready_event = threading.Event()
        self._sig_prepare_processing_editor.emit(target, ready_event)
        try:
            timeout = max(0.1, float(timeout_sec or 5.0))
        except Exception:
            timeout = 5.0
        return bool(ready_event.wait(timeout))

    def _do_open_editor(
        self, target_file, on_save, on_start, on_prev, on_exit, is_batch=False
    ):
        self._on_save_cb = on_save
        self._on_start_cb = on_start
        self._on_prev_cb = on_prev
        self._on_exit_cb = on_exit
        self._target_file = target_file
        self._init_editor(target_file, is_batch)

    def _do_open_editor_ready(
        self, target_file, on_save, on_start, on_prev, on_exit, is_batch=False, ready_event=None
    ):
        try:
            self._do_open_editor(target_file, on_save, on_start, on_prev, on_exit, is_batch)
        finally:
            if hasattr(ready_event, "set"):
                try:
                    ready_event.set()
                except Exception:
                    pass

    def _do_prepare_processing_editor(self, target_file, ready_event=None):
        target = str(target_file or "")

        def _noop(*_args, **_kwargs):
            return None

        editor = getattr(self, "_editor_widget", None)
        same_target = bool(
            editor is not None
            and str(getattr(editor, "media_path", "") or "") == target
        )

        if not same_target:
            self._do_open_editor(target, _noop, _noop, _noop, _noop, False)
            editor = getattr(self, "_editor_widget", None)

        if editor is not None:
            try:
                editor.is_auto_start = True
            except Exception:
                pass
            state_manager = getattr(editor, "sm", None)
            if state_manager is not None:
                try:
                    if str(getattr(state_manager, "state", "") or "") != "ST_PROC":
                        state_manager.start_auto_mode()
                except Exception:
                    pass
            activator = getattr(self, "_activate_editor_for_main_action", None)
            if callable(activator):
                try:
                    activator()
                except Exception:
                    pass

        if hasattr(ready_event, "set"):
            try:
                ready_event.set()
            except Exception:
                pass

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

    def _on_cut_boundary_scan_lines(self, times):
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return
        handler = getattr(editor, "_set_auto_cut_boundary_scan_lines", None)
        if callable(handler):
            try:
                handler(list(times or []))
            except Exception as exc:
                get_logger().log(f"⚠️ 자동 컷 경계 임시선 반영 실패: {exc}")

    def _on_project_boundary_times_updated(self, times):
        try:
            self._project_boundary_times = list(times or [])
        except Exception:
            self._project_boundary_times = []
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return
        try:
            timeline = getattr(editor, "timeline", None)
            if timeline is not None and hasattr(timeline, "set_boundary_times"):
                timeline.set_boundary_times(list(self._project_boundary_times or []))
        except Exception as exc:
            get_logger().log(f"⚠️ 컷 경계 확정선 반영 실패: {exc}")

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

    def _preflight_selected_local_llm_models(self):
        import threading

        def _run():
            try:
                from core.settings import load_settings
                from core.llm.ollama_provider import ollama_probe_timeout, resolve_ollama_model_for_request

                settings = load_settings()
                candidates = [
                    ("자막 LLM", settings.get("selected_model", "")),
                    ("러프컷 LLM", settings.get("roughcut_llm_model", "")),
                ]
                seen = set()
                for context, model in candidates:
                    name = str(model or "").strip()
                    if not name or name in seen or "사용 안함" in name:
                        continue
                    seen.add(name)
                    resolve_ollama_model_for_request(
                        name,
                        logger=get_logger(),
                        context=context,
                        timeout=ollama_probe_timeout(name, 12.0),
                        allow_fallback=False,
                    )
            except Exception as exc:
                get_logger().log(f"⚠️ 시작 시 Ollama 모델 점검 실패: {exc}")

        threading.Thread(target=_run, daemon=True, name="llm-preflight").start()

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
