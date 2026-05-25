# Version: 03.14.33
# Phase: PHASE2
"""Personalization idle and post-generation cleanup helpers for MainWindow."""

from __future__ import annotations

from PyQt6.QtCore import QDateTime, QEvent
from PyQt6.QtWidgets import QApplication

from core.personalization.idle_trainer import FOREGROUND_ACTIVITY_HOLD_MS
from core.runtime.logger import get_logger


class MainPersonalizationMixin:
    def _attach_app_event_filter(self):
        if getattr(self, "_app_event_filter_installed", False):
            return
        app = QApplication.instance()
        if app is None:
            return
        try:
            app.installEventFilter(self)
            self._app_event_filter_installed = True
        except RuntimeError:
            self._app_event_filter_installed = False

    def _detach_app_event_filter(self):
        if not getattr(self, "_app_event_filter_installed", False):
            return
        app = QApplication.instance()
        if app is None:
            self._app_event_filter_installed = False
            return
        try:
            app.removeEventFilter(self)
        except RuntimeError:
            pass
        self._app_event_filter_installed = False

    def eventFilter(self, obj, event):
        try:
            if self._is_general_user_activity_event(event):
                immediate_stop = self._is_immediate_personalization_stop_event(event)
                trainer = getattr(self, "_personalization_idle_trainer", None)
                if trainer is not None:
                    try:
                        if immediate_stop:
                            request_stop = getattr(trainer, "request_immediate_stop", None)
                            if callable(request_stop):
                                request_stop(
                                    reason="user_input_interrupt",
                                    hold_ms=0,
                                    join_timeout_sec=0.03,
                                )
                            else:
                                trainer.note_user_activity()
                                trainer.suspend_for_foreground_activity(
                                    reason="user_input_interrupt",
                                    hold_ms=0,
                                )
                        else:
                            trainer.note_user_activity()
                    except Exception:
                        pass
                if immediate_stop:
                    self._request_personalization_stop_for_user_input()
                if getattr(self, "_post_completion_idle_enabled", False):
                    self._reset_post_completion_idle_timer()
        except Exception:
            pass
        return False

    def _is_general_user_activity_event(self, event) -> bool:
        return event.type() in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.MouseMove,
            QEvent.Type.Wheel,
            QEvent.Type.KeyPress,
            QEvent.Type.KeyRelease,
            QEvent.Type.TouchBegin,
            QEvent.Type.TouchUpdate,
            QEvent.Type.TouchEnd,
        }

    def _is_immediate_personalization_stop_event(self, event) -> bool:
        return event.type() in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.MouseMove,
            QEvent.Type.Wheel,
            QEvent.Type.KeyPress,
            QEvent.Type.KeyRelease,
            QEvent.Type.TouchBegin,
            QEvent.Type.TouchUpdate,
            QEvent.Type.TouchEnd,
        }

    def _register_personalization_learning_dialog(self, dialog) -> None:
        dialogs = [
            item
            for item in list(getattr(self, "_personalization_learning_dialogs", []) or [])
            if item is not None
        ]
        if dialog not in dialogs:
            dialogs.append(dialog)
        self._personalization_learning_dialogs = dialogs

    def _unregister_personalization_learning_dialog(self, dialog) -> None:
        self._personalization_learning_dialogs = [
            item
            for item in list(getattr(self, "_personalization_learning_dialogs", []) or [])
            if item is not None and item is not dialog
        ]

    def _request_personalization_stop_for_user_input(self) -> bool:
        stopped_any = False
        for widget in list(getattr(self, "_personalization_learning_dialogs", []) or []):
            request_stop = getattr(widget, "_request_stop_for_user_input", None)
            if not callable(request_stop):
                continue
            try:
                stopped_any = bool(request_stop()) or stopped_any
            except Exception:
                continue
        return stopped_any

    def _run_personalization_idle_jobs_now(self):
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {"started": False, "reason": "trainer_unavailable"}
        return trainer.run_pending_now()

    def _pause_personalization_for_foreground_activity(
        self,
        reason: str = "foreground_activity",
        *,
        hold_ms: int = FOREGROUND_ACTIVITY_HOLD_MS,
    ):
        """Stop launching LoRA learning while the user/app starts foreground work."""
        now = QDateTime.currentMSecsSinceEpoch()
        try:
            hold = max(0, int(hold_ms))
        except Exception:
            hold = FOREGROUND_ACTIVITY_HOLD_MS
        self._lora_foreground_busy_until_ms = max(
            int(getattr(self, "_lora_foreground_busy_until_ms", 0) or 0),
            now + hold,
        )
        self._lora_foreground_busy_reason = str(reason or "foreground_activity")
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {"suspended": False, "reason": "trainer_unavailable"}
        try:
            return trainer.suspend_for_foreground_activity(
                reason=self._lora_foreground_busy_reason,
                hold_ms=hold,
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 개인화 학습 일시중지 실패: {exc}")
            return {"suspended": False, "reason": str(exc)}

    def _pause_personalization_idle_jobs(self):
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {}
        return trainer.pause_pending_jobs()

    def _resume_personalization_idle_jobs(self):
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {}
        return trainer.resume_pending_jobs()

    def _clear_personalization_idle_jobs(self, *, keep_completed: bool = True):
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {}
        return trainer.clear_pending_jobs(keep_completed=keep_completed)

    def _post_generation_resource_cleanup(self, *, reason: str = "generation_complete", editor=None):
        """Return the UI to an interactive state and detach clip-owned work."""
        for backend_name in ("backend", "backend_fast"):
            backend = getattr(self, backend_name, None)
            if backend is None:
                continue
            try:
                lock = getattr(backend, "_prefetch_lock", None)
                if lock is not None:
                    with lock:
                        backend._prefetch_generation = int(getattr(backend, "_prefetch_generation", 0) or 0) + 1
                        getattr(backend, "_prefetch_cache", {}).clear()
                        getattr(backend, "_prefetch_threads", {}).clear()
            except Exception:
                pass
            vp = getattr(backend, "video_processor", None)
            if vp is not None:
                for method_name in ("clear_fast_mode_overrides", "clear_auto_audio_tune_overrides"):
                    method = getattr(vp, method_name, None)
                    if callable(method):
                        try:
                            method()
                        except Exception:
                            pass
                try:
                    vp.stage_callback = None
                except Exception:
                    pass
        target_editor = editor if editor is not None else getattr(self, "_editor_widget", None)
        if target_editor is not None:
            for method_name in ("_abort_pending_editor_processing_ui_work", "_clear_processing_indicators", "_safe_enable_start_btn"):
                method = getattr(target_editor, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
            try:
                target_editor._subtitle_generation_completed = True
            except Exception:
                pass
            try:
                target_editor._is_ai_processing = False
            except Exception:
                pass
            try:
                target_editor._post_generation_models_release_requested = True
                target_editor._post_generation_models_released = False
            except Exception:
                pass
            try:
                state_manager = getattr(target_editor, "sm", None)
                if state_manager is not None and (
                    bool(getattr(state_manager, "is_locked", False))
                    or str(getattr(state_manager, "state", "") or "") == "ST_PROC"
                ):
                    state_manager.complete_ai()
            except Exception:
                pass
            for attr_name, empty_value in (
                ("_live_editor_preview_queue", []),
                ("_live_editor_preview_segments", []),
                ("_subtitle_context_window_index_cache", {}),
            ):
                try:
                    current = getattr(target_editor, attr_name, None)
                    if isinstance(current, list):
                        current.clear()
                    elif isinstance(current, dict):
                        current.clear()
                    else:
                        setattr(target_editor, attr_name, empty_value.copy() if hasattr(empty_value, "copy") else empty_value)
                except Exception:
                    pass
            try:
                target_editor._segment_cache_valid = False
            except Exception:
                pass
        for backend_name in ("backend", "backend_fast"):
            backend = getattr(self, backend_name, None)
            if backend is None:
                continue
            for thread_name in ("_pipeline_thread", "_eta_thread", "_cut_boundary_prescan_thread", "_cut_boundary_follower_thread"):
                thread = getattr(backend, thread_name, None)
                try:
                    if thread is not None and getattr(thread, "is_alive", lambda: False)():
                        thread.join(timeout=0.05)
                    if thread is not None and not getattr(thread, "is_alive", lambda: False)():
                        setattr(backend, thread_name, None)
                except Exception:
                    pass
        try:
            self._auto_processing_active = False
        except Exception:
            pass
        try:
            self._force_editor_idle_after_generation(target_editor, reason=reason)
        except Exception:
            self._restore_normal_cursor(self, target_editor)
        try:
            self._editor_ai_runtime_release_requested_for_editor_mode = True
        except Exception as exc:
            get_logger().log(f"⚠️ 생성 완료 모델 정리 예약 실패: {exc}")
        reserve_playback = getattr(self, "_reserve_video_playback_runtime", None)
        if callable(reserve_playback):
            try:
                reserve_playback(hold_sec=10.0)
            except Exception:
                pass
        self._schedule_post_generation_gc(editor=target_editor, delay_ms=1200)
        get_logger().log(f"🧹 후처리 정리 완료: {reason}")
        if hasattr(self, "_refresh_saved_status_label"):
            self._refresh_saved_status_label()
        return {"cleaned": True, "reason": reason}

    def _is_user_activity_event(self, event) -> bool:
        if not getattr(self, "_post_completion_idle_enabled", False):
            return False
        return self._is_general_user_activity_event(event)

    def _start_post_completion_idle_timer(self):
        self._post_completion_idle_enabled = True
        self._attach_app_event_filter()
        self._post_completion_idle_deadline_ms = QDateTime.currentMSecsSinceEpoch() + int(self._post_completion_idle_ms)
        self._post_completion_idle_timer.start(self._post_completion_idle_ms)
        self._post_completion_idle_countdown_timer.start()
        self._refresh_post_completion_idle_status()

    def _reset_post_completion_idle_timer(self):
        if getattr(self, "_post_completion_idle_enabled", False):
            self._post_completion_idle_deadline_ms = QDateTime.currentMSecsSinceEpoch() + int(self._post_completion_idle_ms)
            self._post_completion_idle_timer.start(self._post_completion_idle_ms)
            self._refresh_post_completion_idle_status()

    def _stop_post_completion_idle_timer(self):
        self._post_completion_idle_enabled = False
        self._post_completion_idle_deadline_ms = 0
        try:
            self._post_completion_idle_timer.stop()
        except Exception:
            pass
        try:
            self._post_completion_idle_countdown_timer.stop()
        except Exception:
            pass
        self._refresh_post_completion_idle_status()

    def _post_completion_idle_remaining_ms(self) -> int:
        if not getattr(self, "_post_completion_idle_enabled", False):
            return 0
        deadline = int(getattr(self, "_post_completion_idle_deadline_ms", 0) or 0)
        if deadline <= 0:
            return 0
        return max(0, deadline - QDateTime.currentMSecsSinceEpoch())

    def _refresh_post_completion_idle_status(self):
        if hasattr(self, "_refresh_saved_status_label"):
            self._refresh_saved_status_label()

    def _is_editor_actively_editing(self) -> bool:
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return False
        state_manager = getattr(editor, "sm", None)
        if state_manager is not None:
            state = str(getattr(state_manager, "state", "") or "")
            if state in {"ST_EDITING", "ST_AUTOSAVE"}:
                return True
        timeline = getattr(editor, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        if canvas is not None:
            if bool(getattr(canvas, "_edit_active", False)):
                return True
            if getattr(canvas, "_drag_seg", None) is not None:
                return True
        return False

    def _on_post_completion_idle_timeout(self):
        if self._is_editor_actively_editing():
            self._reset_post_completion_idle_timer()
            return
        self._post_completion_idle_enabled = False
        self._post_completion_idle_deadline_ms = 0
        try:
            self._post_completion_idle_countdown_timer.stop()
        except Exception:
            pass
        backend = getattr(self, "backend", None)
        if backend is not None and hasattr(backend, "_action_state") and hasattr(backend, "_edit_event"):
            try:
                backend._action_state[0] = "exit"
                backend._edit_event.set()
                return
            except Exception:
                pass
        self.show_home(allow_home_idle_learning=True)
