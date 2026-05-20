# Version: 03.08.05
# Phase: PHASE2
"""
ui/main/main_signals.py
SignalHandlersMixin — Qt 시그널 핸들러 (세그먼트 전달 · VAD · recog zone · LLM 웜업)
"""
import os
import threading
import time

from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.runtime import config
from core.runtime.logger import get_logger
from ui.main.main_nonfatal import call_nonfatal_ui_step, run_nonfatal_ui_step
from ui.project.project_session_runtime import set_project_boundary_rows
from ui.queue.queue_dispatch import queue_active_row_index


def _is_preflight_local_ollama_model(model: str) -> bool:
    text = str(model or "").strip()
    if not text or "사용 안함" in text:
        return False
    if "Gemini" in text:
        return False
    try:
        from core.llm.openai_provider import is_openai_model

        if is_openai_model(text):
            return False
    except Exception:
        pass
    return True


class SignalHandlersMixin:
    """MainWindow 시그널 핸들러 모음."""

    def _resolve_active_editor_for_signal(self):
        editor = getattr(self, "_editor_widget", None)
        if editor is not None:
            return editor
        stack = getattr(self, "stack", None)
        current_widget = getattr(stack, "currentWidget", None)
        if callable(current_widget):
            try:
                candidate = current_widget()
            except Exception:
                candidate = None
            if candidate is not None:
                return candidate
        return None

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

    def preview_processing_segments_in_editor(self, stage_label: str, segments, *, stage: str = ""):
        self._sig_preview_processing_segments.emit(
            {
                "stage": str(stage or ""),
                "stage_label": str(stage_label or stage or ""),
                "segments": list(segments or []),
                "active": True,
            }
        )

    def refresh_cut_boundary_placeholder(self):
        self._sig_refresh_cut_boundary_placeholder.emit()

    def preview_cut_boundary_topicless_segments(self, rows):
        self._sig_preview_cut_boundary_topicless_segments.emit(list(rows or []))

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

    def finalize_editor_generation_complete(self, reason: str = "backend_done"):
        self._sig_finalize_generation_complete.emit(str(reason or "backend_done"))

    def append_log(self, msg):
        self.log_text.append(msg)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
        sync_terminal_height = getattr(self, "_sync_sidebar_terminal_panel_height", None)
        if callable(sync_terminal_height):
            QTimer.singleShot(0, sync_terminal_height)
        tracker = getattr(self, "_automation_track_log_line", None)
        if callable(tracker):
            tracker(str(msg or ""))
        if not bool(getattr(self, "_sidebar_engine_refresh_pending", False)):
            self._sidebar_engine_refresh_pending = True

            def _refresh():
                self._sidebar_engine_refresh_pending = False
                refresher = getattr(self, "_refresh_sidebar_engine_info", None)
                if callable(refresher):
                    refresher()

            QTimer.singleShot(80, _refresh)

    def _do_append_segments(self, segments, *, flush: bool = False):
        editor = self._resolve_active_editor_for_signal()
        if editor is None:
            return
        call_nonfatal_ui_step("메인 시그널", editor, "append_segments", segments, step="에디터 세그먼트 append")
        if flush:
            flusher = getattr(editor, "_flush_pending_segment_queue_now", None)
            if callable(flusher):
                run_nonfatal_ui_step("메인 시그널", "에디터 세그먼트 flush", flusher)
            else:
                call_nonfatal_ui_step("메인 시그널", editor, "_flush_queue", step="에디터 세그먼트 fallback flush")
            run_nonfatal_ui_step("메인 시그널", "Qt 이벤트 flush", QApplication.processEvents, default=None)

    def _do_append_segments_ready(self, segments, ready_event):
        try:
            self._do_append_segments(segments, flush=True)
        finally:
            if hasattr(ready_event, "set"):
                run_nonfatal_ui_step("메인 시그널", "append ready event set", ready_event.set, default=None)

    def _do_preview_stt_segments(self, segments):
        editor = self._resolve_active_editor_for_signal()
        if editor is not None and hasattr(editor, "preview_stt_segments"):
            editor.preview_stt_segments(segments)

    def _do_preview_processing_segments(self, payload):
        editor = self._resolve_active_editor_for_signal()
        if editor is None or not hasattr(editor, "preview_processing_segments"):
            return
        try:
            editor.preview_processing_segments(dict(payload or {}))
        except RuntimeError:
            return

    def _do_set_llm_review_segment(self, payload):
        editor = self._resolve_active_editor_for_signal()
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
                flusher = getattr(editor, "_flush_live_editor_preview_queue", None)
                if callable(flusher):
                    flusher()
                focuser = getattr(editor, "_focus_editor_block_for_processing_segment", None)
                if callable(focuser):
                    focuser(data)
        timeline = getattr(editor, "timeline", None) if editor is not None else None
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        setter = getattr(canvas, "set_llm_review_segment", None) if canvas is not None else None
        if callable(setter):
            setter(dict(payload or {}))

    def _do_editor_processing_stage(self, text):
        editor = self._resolve_active_editor_for_signal()
        setter = getattr(editor, "set_live_processing_stage", None) if editor is not None else None
        stage_text = str(text or "")
        if callable(setter):
            if getattr(config, "IS_MAC", False):
                stage_text = stage_text.replace("⏳ ", "", 1)
            setter(stage_text)
        snapshotter = getattr(self, "_automation_capture_processing_stage", None)
        if callable(snapshotter):
            snapshotter(stage_text)

    def _do_clear_editor(self):
        if hasattr(self, "_clear_editor_for_full_restart"):
            call_nonfatal_ui_step("메인 시그널", self, "_clear_editor_for_full_restart", step="풀 리스타트용 에디터 clear")
            return
        ed = self._resolve_active_editor_for_signal()
        if not ed:
            return
        queue_timer = getattr(ed, "_queue_timer", None)
        if queue_timer is not None and getattr(queue_timer, "isActive", lambda: False)():
            call_nonfatal_ui_step("메인 시그널", queue_timer, "stop", step="에디터 queue timer stop")

        def _reset_editor_queues():
            if hasattr(ed, "_segment_queue"):
                ed._segment_queue.clear()
            for attr, value in (
                ("_live_editor_preview_queue", []),
                ("_live_editor_preview_segments", []),
                ("_live_editor_preview_keys", set()),
            ):
                if hasattr(ed, attr):
                    setattr(ed, attr, value.copy() if hasattr(value, "copy") else value)

        run_nonfatal_ui_step("메인 시그널", "에디터 preview/queue reset", _reset_editor_queues, default=None)
        if hasattr(ed, "text_edit"):
            call_nonfatal_ui_step("메인 시그널", ed.text_edit, "clear", step="에디터 텍스트 clear")

        timeline = getattr(ed, "timeline", None)
        if timeline is not None:
            total_duration = getattr(getattr(timeline, "canvas", None), "total_duration", 0.0)
            call_nonfatal_ui_step(
                "메인 시그널",
                timeline,
                "update_segments",
                [],
                0.0,
                total_duration,
                step="타임라인 세그먼트 clear",
            )
            call_nonfatal_ui_step("메인 시그널", timeline, "set_playhead", 0.0, step="타임라인 플레이헤드 초기화")

        vp = getattr(ed, "video_player", None)
        if vp is not None:
            call_nonfatal_ui_step("메인 시그널", vp, "set_context_segments", [], step="비디오 컨텍스트 clear")
            call_nonfatal_ui_step("메인 시그널", vp, "seek", 0.0, step="비디오 seek reset")

        run_nonfatal_ui_step(
            "메인 시그널",
            "에디터 세그먼트 캐시 reset",
            lambda: (setattr(ed, "_cached_segs", []), setattr(ed, "_active_seg_start", 0.0)),
            default=None,
        )

    def _do_update_status(self, c_idx, t_total):
        editor = self._resolve_active_editor_for_signal()
        if editor is not None and hasattr(editor, "update_progress"):
            editor.update_progress(c_idx, t_total)

    def _do_finalize_generation_complete(self, reason: str = "backend_done"):
        editor = self._resolve_active_editor_for_signal()
        if editor is None:
            return
        finalizer = getattr(editor, "_finalize_generation_from_backend", None)
        if callable(finalizer):
            finalizer(reason=str(reason or "backend_done"))
        else:
            fallback = getattr(editor, "_set_process_completed", None)
            if callable(fallback):
                fallback()
        snapshotter = getattr(self, "_automation_finalize_guided_snapshot", None)
        if callable(snapshotter):
            snapshotter(str(reason or "backend_done"))

    def _do_restart_multiclip(self, files, folder=None):
        if not self.backend:
            return
        run_nonfatal_ui_step(
            "메인 시그널",
            "멀티클립 재시작 플래그 설정",
            lambda: (
                setattr(self.backend, "_force_no_reuse_once", True),
                setattr(self.backend, "_force_cut_boundary_rescan_once", True),
            ),
            default=None,
        )
        call_nonfatal_ui_step(
            "메인 시그널",
            self.backend,
            "start_multiclip_pipeline",
            list(files or []),
            folder=folder,
            step="멀티클립 파이프라인 재시작",
        )

    def _do_refresh_cut_boundary_placeholder(self):
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return
        previous_result = getattr(self, "_editor_roughcut_result", None)
        refresh_placeholder = getattr(editor, "_refresh_cut_boundary_placeholder_from_project", None)
        if callable(refresh_placeholder):
            run_nonfatal_ui_step("메인 시그널", "컷 경계 placeholder 프로젝트 반영", refresh_placeholder, default=None)
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
            refreshed = run_nonfatal_ui_step(
                "메인 시그널",
                "컷 경계 placeholder roughcut 갱신",
                lambda: refresh_from_editor(analyze_if_missing=False),
                default=False,
            )
            if refreshed is False:
                return
        fallback_result = (
            getattr(roughcut, "_result", None)
            or getattr(editor, "_roughcut_result", None)
            or getattr(editor, "roughcut_result", None)
            or previous_result
        )
        self._editor_roughcut_result = fallback_result
        call_nonfatal_ui_step("메인 시그널", editor, "_redraw_timeline", step="에디터 타임라인 redraw")

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
        started = time.perf_counter()
        self._on_save_cb = on_save
        self._on_start_cb = on_start
        self._on_prev_cb = on_prev
        self._on_exit_cb = on_exit
        self._target_file = target_file
        self._init_editor(target_file, is_batch)
        get_logger().log_perf(
            "editor.open_request",
            event="ready",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            batch=bool(is_batch),
            file=os.path.basename(str(target_file or "")),
        )

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
            ci = max(0, int(queue_active_row_index(self)))
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

    def _on_cut_boundary_topicless_segments(self, rows):
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return
        handler = getattr(editor, "_apply_cut_boundary_topicless_rows_to_ui", None)
        if callable(handler):
            try:
                handler(list(rows or []), source="stream")
            except Exception as exc:
                get_logger().log(f"⚠️ 컷 경계 split 실시간 반영 실패: {exc}")

    def _on_project_boundary_times_updated(self, times):
        rows = []
        try:
            from core.cut_boundary import sanitize_cut_boundary_rows

            fps = 30.0
            try:
                editor = getattr(self, "_editor_widget", None)
                fps = float(getattr(editor, "video_fps", 30.0) or 30.0) if editor is not None else 30.0
            except Exception:
                fps = 30.0
            rows = sanitize_cut_boundary_rows(list(times or []), primary_fps=fps)
        except Exception:
            rows = []
        set_project_boundary_rows(self, rows, emit_boundary_signal=False)
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return
        try:
            timeline = getattr(editor, "timeline", None)
            if timeline is not None and hasattr(timeline, "set_boundary_times"):
                timeline.set_boundary_times(list(getattr(self, "_project_boundary_times", []) or []))
        except Exception as exc:
            get_logger().log(f"⚠️ 컷 경계 확정선 반영 실패: {exc}")

    def _warmup_local_llm_models(self):
        import threading
        def _scan():
            started = time.perf_counter()
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
            finally:
                get_logger().log_perf(
                    "startup.llm_warmup",
                    event="done",
                    elapsed_ms=(time.perf_counter() - started) * 1000.0,
                    models=len(list(getattr(self, "_local_llm_models", []) or [])),
                )
        threading.Thread(target=_scan, daemon=True, name="llm-warmup").start()

    def _preflight_selected_local_llm_models(self):
        import threading

        def _run():
            started = time.perf_counter()
            probed = 0
            try:
                from core.settings import load_settings
                from core.llm.ollama_provider import ollama_probe_timeout, resolve_ollama_model_for_request

                settings = load_settings()
                candidates = [
                    ("자막 LLM", settings.get("selected_model", "")),
                ]
                if bool(settings.get("roughcut_llm_enabled")):
                    candidates.append(("러프컷 LLM", settings.get("roughcut_llm_model", "")))
                seen = set()
                for context, model in candidates:
                    name = str(model or "").strip()
                    if not _is_preflight_local_ollama_model(name) or name in seen:
                        continue
                    seen.add(name)
                    probe_started = time.perf_counter()
                    resolve_ollama_model_for_request(
                        name,
                        logger=get_logger(),
                        context=context,
                        timeout=ollama_probe_timeout(name, 12.0),
                        allow_fallback=False,
                    )
                    probed += 1
                    get_logger().log_perf(
                        "startup.llm_preflight",
                        event="probe_done",
                        elapsed_ms=(time.perf_counter() - probe_started) * 1000.0,
                        context=context,
                        model=name,
                    )
            except Exception as exc:
                get_logger().log(f"⚠️ 시작 시 Ollama 모델 점검 실패: {exc}")
            finally:
                get_logger().log_perf(
                    "startup.llm_preflight",
                    event="done",
                    elapsed_ms=(time.perf_counter() - started) * 1000.0,
                    probed=probed,
                )

        threading.Thread(target=_run, daemon=True, name="llm-preflight").start()

    def _check_required_models_on_startup(self):
        if getattr(self, "_required_model_check_done", False):
            return
        started = time.perf_counter()
        self._required_model_check_done = True
        try:
            from core.model_manager import get_current_os, get_required_models
            missing = get_required_models()
        except Exception as e:
            get_logger().log(f"⚠️ 필수 AI 모델 확인 실패: {e}")
            get_logger().log_perf(
                "startup.required_models",
                event="failed",
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                error=type(e).__name__,
            )
            return
        if not missing:
            get_logger().log("✅ 필수 AI 모델 확인 완료")
            get_logger().log_perf(
                "startup.required_models",
                event="done",
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                missing=0,
            )
            return

        names = [m.get("name", m.get("id", "unknown")) for m in missing]
        get_logger().log("⚠️ 필수 AI 모델 미설치: " + ", ".join(names))
        get_logger().log_perf(
            "startup.required_models",
            event="done",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            missing=len(names),
        )
        if not self._can_show_startup_required_models_dialog():
            # 시작 직후 경고 모달은 사용자 안내보다 크래시 위험이 더 컸다.
            # 여기서 무조건 QMessageBox로 되돌리지 말고, 창이 안정된 뒤 별도 UX가 필요하면
            # 그때 명시적으로 설계해서 추가한다.
            get_logger().log(
                "ℹ️ 시작 직후 Qt modal 충돌을 피하기 위해 필수 AI 모델 경고 팝업은 생략합니다. 설정 > AI 엔진 설정 > 모델 관리에서 확인하세요."
            )
            return

        QMessageBox.warning(
            self,
            "필수 AI 모델 확인",
            f"현재 OS({get_current_os()})에서 필요한 AI 모델이 아직 준비되지 않았습니다.\n\n"
            + "\n".join(f"- {name}" for name in names)
            + "\n\n설정 > AI 엔진 설정 > 모델 관리에서 설치 상태를 확인하세요."
        )

    def _can_show_startup_required_models_dialog(self) -> bool:
        # 이 체크는 "팝업을 보여줄지"만 판단한다.
        # 임의 UI/UX 변경 지점이 아니라, 시작 안정성을 지키는 안전장치다.
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return False
        app = QApplication.instance()
        if app is None:
            return False
        try:
            if app.thread() != QThread.currentThread():
                return False
        except Exception:
            return False
        try:
            if not self.isVisible():
                return False
            if not self.isActiveWindow():
                return False
        except Exception:
            return False
        try:
            return self.windowHandle() is not None
        except Exception:
            return False
