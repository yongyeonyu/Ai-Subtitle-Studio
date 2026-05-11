# Version: 03.14.33
# Phase: PHASE2
"""
ui/main/main_runtime_cleanup.py
MainWindow runtime cleanup / fast-exit responsibilities extracted from main_window.py.
"""
import gc
import os
import threading
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from core.runtime import config
from core.runtime.logger import get_logger
from core.settings import load_settings


def _main_window_threading_module():
    try:
        from ui.main import main_window as main_window_module

        module = getattr(main_window_module, "threading", None)
        if module is not None:
            return module
    except Exception:
        pass
    return threading


def _load_main_window_settings():
    try:
        from ui.main import main_window as main_window_module

        loader = getattr(main_window_module, "load_settings", None)
        if callable(loader):
            return loader()
    except Exception:
        pass
    return load_settings()


class MainRuntimeCleanupMixin:
    def _cleanup_runtime_for_navigation(
        self,
        *,
        context: str = "홈 이동",
        timeout_sec: float = 0.5,
        force: bool = False,
        stop_active: bool = False,
    ):
        if getattr(self, "_runtime_cleanup_in_progress", False):
            return False
        editor = getattr(self, "_editor_widget", None)
        editor_busy = self._is_editor_ai_busy(editor)
        backend_busy = self._is_backend_ai_busy()
        if (editor_busy or backend_busy) and not (force or stop_active):
            return False
        cleanup_key = (str(context or ""), id(editor) if editor is not None else 0)
        if (
            not force
            and editor is not None
            and not editor_busy
            and not backend_busy
            and getattr(self, "_last_runtime_cleanup_key", None) == cleanup_key
        ):
            return False
        should_cleanup = bool(force or stop_active or editor is not None or backend_busy)
        if not should_cleanup:
            return False

        self._runtime_cleanup_in_progress = True
        context = str(context or "런타임 정리").strip() or "런타임 정리"
        stopped_any = False
        try:
            try:
                self._stop_post_completion_idle_timer()
            except Exception:
                pass

            if editor is not None:
                try:
                    timer = getattr(editor, "_roughcut_draft_timer", None)
                    if timer is not None:
                        timer.stop()
                    editor._roughcut_draft_pending = False
                    editor._roughcut_draft_generation = int(getattr(editor, "_roughcut_draft_generation", 0) or 0) + 1
                    if hasattr(editor, "_set_roughcut_draft_status"):
                        editor._set_roughcut_draft_status("idle")
                except Exception:
                    pass
                try:
                    state_manager = getattr(editor, "sm", None)
                    is_processing = bool(getattr(editor, "_is_ai_processing", False))
                    if state_manager is not None:
                        is_processing = is_processing or bool(getattr(state_manager, "is_locked", False))
                    if (force or stop_active or is_processing) and hasattr(editor, "_stop_pipeline"):
                        editor._stop_pipeline()
                        stopped_any = True
                except RuntimeError:
                    pass
                except Exception as exc:
                    get_logger().log(f"⚠️ {context} 중 에디터 작업 중단 실패: {exc}")

                try:
                    video_player = getattr(editor, "video_player", None)
                    if video_player is not None:
                        shutdown_backend = getattr(video_player, "shutdown_backend", None)
                        if callable(shutdown_backend):
                            shutdown_backend()
                        timer = getattr(video_player, "_ui_timer", None)
                        if timer is not None:
                            timer.stop()
                        if hasattr(video_player, "pause_video"):
                            video_player.pause_video()
                        for player_name in ("media_player", "vocal_player", "audio_player"):
                            player = getattr(video_player, player_name, None)
                            if player is not None and hasattr(player, "stop"):
                                player.stop()
                except Exception:
                    pass

                try:
                    timeline = getattr(editor, "timeline", None)
                    stop_waveform = getattr(timeline, "stop_waveform_workers", None) if timeline is not None else None
                    if callable(stop_waveform):
                        stop_waveform()
                        stopped_any = True
                except Exception:
                    pass

                if force and hasattr(editor, "_cleanup"):
                    try:
                        editor._cleanup()
                    except Exception:
                        pass

            for backend_name in ("backend", "backend_fast"):
                backend = getattr(self, backend_name, None)
                if backend is None:
                    continue
                backend_instance_busy = self._is_backend_instance_busy(backend)
                try:
                    backend_active = bool(getattr(backend, "_active", False))
                    should_stop_backend = bool(
                        stop_active or backend_instance_busy or (force and backend_active)
                    )
                    if should_stop_backend and hasattr(backend, "stop"):
                        stop_fn = getattr(backend, "stop")
                        try:
                            import inspect

                            if "log_context" in inspect.signature(stop_fn).parameters:
                                stop_fn(log_context=context)
                            else:
                                stop_fn()
                        except (TypeError, ValueError):
                            stop_fn()
                        stopped_any = True
                except Exception as exc:
                    get_logger().log(f"⚠️ {context} 중 {backend_name} 중단 실패: {exc}")

                processor = getattr(backend, "video_processor", None)
                if processor is not None:
                    try:
                        if hasattr(processor, "release_runtime_models"):
                            processor.release_runtime_models()
                        elif hasattr(processor, "stop_transcribe"):
                            processor.stop_transcribe()
                        stopped_any = True
                    except Exception as exc:
                        get_logger().log(f"⚠️ {context} 중 {backend_name} STT 런타임 정리 실패: {exc}")

                for thread_name in ("_pipeline_thread", "_eta_thread"):
                    thread = getattr(backend, thread_name, None)
                    try:
                        if thread is not None and getattr(thread, "is_alive", lambda: False)():
                            thread.join(timeout=max(0.05, float(timeout_sec) / 2.0))
                    except RuntimeError:
                        pass
                    except Exception:
                        pass

            try:
                from core.audio.live_stt import stop_live_stt_worker

                if stop_live_stt_worker():
                    stopped_any = True
            except Exception:
                pass

            skip_external_cleanup = bool(getattr(self, "_skip_external_cleanup_in_navigation", False))
            if not skip_external_cleanup:
                try:
                    from core.platform_compat import cleanup_app_runtime_processes

                    cleanup_result = cleanup_app_runtime_processes(logger=get_logger(), timeout_sec=timeout_sec)
                    if any(int(v or 0) > 0 for v in cleanup_result.values()):
                        stopped_any = True
                except Exception as exc:
                    get_logger().log(f"⚠️ {context} 중 외부 런타임 정리 실패: {exc}")

            try:
                gc.collect()
            except Exception:
                pass

            if stopped_any:
                get_logger().log(f"🧹 {context}: 스레드/AI 런타임/메모리 정리 완료")
            self._last_runtime_cleanup_key = cleanup_key
            return stopped_any
        finally:
            self._runtime_cleanup_in_progress = False

    def _has_active_runtime_work_for_exit(self) -> bool:
        editor = getattr(self, "_editor_widget", None)
        if self._is_editor_ai_busy(editor) or self._is_backend_ai_busy():
            return True
        if bool(getattr(self, "_auto_processing_active", False)):
            return True
        for manager_name in ("_cloud_sync_manager", "_nas_sync_manager"):
            manager = getattr(self, manager_name, None)
            if manager is None:
                continue
            try:
                if bool(getattr(manager, "_in_flight", None)) or bool(getattr(manager, "_folder_jobs", None)):
                    return True
            except Exception:
                pass
        return False

    def _restore_normal_cursor(self, *widgets) -> None:
        app = QApplication.instance()
        if app is not None:
            for _ in range(32):
                try:
                    if QApplication.overrideCursor() is None:
                        break
                    QApplication.restoreOverrideCursor()
                except Exception:
                    break
        for widget in widgets:
            if widget is None:
                continue
            targets = [widget]
            viewport_getter = getattr(widget, "viewport", None)
            if callable(viewport_getter):
                try:
                    viewport = viewport_getter()
                    if viewport is not None:
                        targets.append(viewport)
                except Exception:
                    pass
            for attr_name in ("timeline", "video_player", "text_edit", "canvas", "global_canvas"):
                child = getattr(widget, attr_name, None)
                if child is not None:
                    targets.append(child)
                    child_viewport_getter = getattr(child, "viewport", None)
                    if callable(child_viewport_getter):
                        try:
                            child_viewport = child_viewport_getter()
                            if child_viewport is not None:
                                targets.append(child_viewport)
                        except Exception:
                            pass
                    for nested_name in ("canvas", "global_canvas"):
                        nested_child = getattr(child, nested_name, None)
                        if nested_child is not None:
                            targets.append(nested_child)
            for target in targets:
                if target is None:
                    continue
                try:
                    target.unsetCursor()
                except Exception:
                    pass

    def _clear_runtime_memory_caches(self, *, include_gpu: bool = True) -> None:
        try:
            from core.media_info import clear_media_probe_cache_memory
            from core.personalization.lora_vector_retriever import clear_lora_retrieval_caches
            from core.project.project_io import clear_project_file_cache
            from core.runtime.memory_manager import trim_runtime_memory_caches
            from ui.style import clear_line_icon_cache

            clear_media_probe_cache_memory()
            clear_project_file_cache()
            clear_lora_retrieval_caches()
            clear_line_icon_cache()
            trim_runtime_memory_caches(stage="critical" if include_gpu else "warning", include_gpu=include_gpu)
        except Exception:
            pass
        for owner in (self, getattr(self, "backend", None), getattr(self, "backend_fast", None)):
            if owner is None:
                continue
            try:
                cache = getattr(owner, "_prefetch_cache", None)
                if isinstance(cache, dict):
                    cache.clear()
            except Exception:
                pass
            for attr_name in (
                "_cut_boundary_pipeline_cache",
                "_auto_audio_tune_cache",
                "_runtime_auto_audio_tune",
                "_runtime_auto_audio_decision",
                "_speaker_map",
            ):
                try:
                    payload = getattr(owner, attr_name, None)
                    if isinstance(payload, dict):
                        payload.clear()
                    elif isinstance(payload, list):
                        payload.clear()
                except Exception:
                    pass
        try:
            gc.collect()
        except Exception:
            pass
        if not include_gpu:
            return
        # GPU and MLX cache trimming is already routed through
        # core.runtime.memory_manager.trim_runtime_memory_caches above.

    def _shutdown_runtime_memory_manager(self) -> None:
        try:
            timer = getattr(self, "_runtime_memory_timer", None)
            if timer is not None and hasattr(timer, "stop"):
                timer.stop()
        except Exception:
            pass
        try:
            manager = getattr(self, "_runtime_memory_manager", None)
            if manager is not None and hasattr(manager, "stop"):
                manager.stop()
        except Exception:
            pass

    def _shutdown_runtime_resource_coordinator(self) -> None:
        try:
            timer = getattr(self, "_runtime_resource_timer", None)
            if timer is not None and hasattr(timer, "stop"):
                timer.stop()
        except Exception:
            pass
        try:
            coordinator = getattr(self, "_runtime_resource_coordinator", None)
            if coordinator is not None and hasattr(coordinator, "set_exit_mode"):
                coordinator.set_exit_mode(True)
        except Exception:
            pass

    def _handle_runtime_memory_pressure(self, stage: str, snapshot: dict | None = None):
        stage_text = str(stage or "normal").strip().lower()
        if stage_text == "normal":
            return {"stage": "normal", "actions": []}
        actions: list[str] = []
        include_gpu = stage_text == "critical"
        try:
            self._clear_runtime_memory_caches(include_gpu=include_gpu)
            actions.append("clear_runtime_memory_caches")
        except Exception:
            pass
        if stage_text == "critical":
            try:
                busy = bool(self._is_editor_ai_busy(getattr(self, "_editor_widget", None)) or self._is_backend_ai_busy())
            except Exception:
                busy = True
            if not busy:
                try:
                    self._release_ai_models_for_editor_mode(
                        force=True,
                        preserve_roughcut_status=True,
                        ollama_timeout_sec=1.2,
                    )
                    actions.append("release_ai_models")
                except Exception:
                    pass
        return {"stage": stage_text, "actions": actions}

    def _force_editor_idle_after_generation(self, editor=None, *, reason: str = "generation_complete") -> dict:
        target_editor = editor if editor is not None else getattr(self, "_editor_widget", None)
        widgets = [self, target_editor]
        if target_editor is not None:
            for attr_name in (
                "_is_ai_processing",
                "_live_editor_preview_pending",
            ):
                try:
                    setattr(target_editor, attr_name, False)
                except Exception:
                    pass
            try:
                target_editor._subtitle_generation_completed = True
            except Exception:
                pass
            for timer_name in ("_spinner_timer", "_cut_boundary_scan_timer"):
                try:
                    timer = getattr(target_editor, timer_name, None)
                    if timer is not None and hasattr(timer, "stop"):
                        timer.stop()
                except Exception:
                    pass
            for method_name in ("_clear_processing_indicators", "_safe_enable_start_btn"):
                method = getattr(target_editor, method_name, None)
                if callable(method):
                    try:
                        method()
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
            timeline = getattr(target_editor, "timeline", None)
            if timeline is not None:
                widgets.append(timeline)
                try:
                    timeline.set_playhead_busy(False)
                except Exception:
                    pass
                try:
                    timeline.set_playback_center_lock(False)
                except Exception:
                    pass
            video_player = getattr(target_editor, "video_player", None)
            if video_player is not None:
                widgets.append(video_player)
                try:
                    video_player.set_scan_cut_active(False)
                except Exception:
                    pass
            try:
                manager = getattr(target_editor, "_background_prefetch_manager", None)
                clear = getattr(manager, "clear", None)
                if callable(clear):
                    clear()
                target_editor._last_background_prefetch_request = {}
                target_editor._last_background_prefetch_gate_key = ""
                target_editor._last_background_prefetch_gate_at = 0.0
            except Exception:
                pass
        try:
            self._auto_processing_active = False
        except Exception:
            pass
        self._restore_normal_cursor(*widgets)
        for delay_ms in (0, 80, 240, 700):
            try:
                QTimer.singleShot(delay_ms, lambda saved_widgets=tuple(widgets): self._restore_normal_cursor(*saved_widgets))
            except Exception:
                pass
        return {"idle": True, "reason": reason}

    def _restore_normal_cursor_for_exit(self):
        self._restore_normal_cursor(self, getattr(self, "_editor_widget", None))

    def _is_editor_video_playing(self, editor=None) -> bool:
        editor = editor if editor is not None else getattr(self, "_editor_widget", None)
        try:
            player = getattr(getattr(editor, "video_player", None), "media_player", None)
            return bool(player and player.playbackState() == player.PlaybackState.PlayingState)
        except Exception:
            return False

    def _schedule_post_generation_gc(self, *, editor=None, delay_ms: int = 1600) -> None:
        if bool(getattr(self, "_post_generation_gc_scheduled", False)):
            return
        self._post_generation_gc_scheduled = True

        def _run_gc():
            self._post_generation_gc_scheduled = False
            if self._is_editor_video_playing(editor):
                self._schedule_post_generation_gc(editor=editor, delay_ms=2200)
                return
            try:
                self._clear_runtime_memory_caches(include_gpu=True)
            except Exception:
                pass

        QTimer.singleShot(max(0, int(delay_ms)), _run_gc)

    def _schedule_forced_process_exit(self, *, delay_ms: int = 250):
        if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
            return
        delay_sec = max(0.02, float(max(20, int(delay_ms))) / 1000.0)
        try:
            timer = _main_window_threading_module().Timer(delay_sec, lambda: os._exit(0))
            timer.daemon = True
            timer.start()
        except Exception:
            pass
        try:
            QTimer.singleShot(max(20, int(delay_ms)), lambda: os._exit(0))
        except Exception:
            pass

    def _pause_editor_runtime_for_exit(self, editor) -> bool:
        if editor is None:
            return False
        stopped_any = False
        try:
            abort_pending = getattr(editor, "_abort_pending_editor_processing_ui_work", None)
            if callable(abort_pending):
                abort_pending()
                stopped_any = True
        except Exception:
            pass
        try:
            state_manager = getattr(editor, "sm", None)
            if state_manager is not None and hasattr(state_manager, "stop_processing"):
                state_manager.stop_processing("앱 종료로 작업을 일시 정지했습니다.")
                stopped_any = True
        except Exception:
            pass
        for timer_name in ("_spinner_timer", "_roughcut_draft_timer", "_cut_boundary_scan_timer"):
            try:
                timer = getattr(editor, timer_name, None)
                if timer is not None and hasattr(timer, "stop"):
                    timer.stop()
                    stopped_any = True
            except Exception:
                pass
        try:
            editor._roughcut_draft_pending = False
            editor._roughcut_draft_generation = int(getattr(editor, "_roughcut_draft_generation", 0) or 0) + 1
        except Exception:
            pass
        try:
            video_player = getattr(editor, "video_player", None)
            if video_player is not None:
                shutdown_backend = getattr(video_player, "shutdown_backend", None)
                if callable(shutdown_backend):
                    shutdown_backend()
                timer = getattr(video_player, "_ui_timer", None)
                if timer is not None:
                    timer.stop()
                if hasattr(video_player, "pause_video"):
                    video_player.pause_video()
                for player_name in ("media_player", "vocal_player", "audio_player"):
                    player = getattr(video_player, player_name, None)
                    if player is not None and hasattr(player, "stop"):
                        player.stop()
                stopped_any = True
        except Exception:
            pass
        try:
            timeline = getattr(editor, "timeline", None)
            stop_waveform = getattr(timeline, "stop_waveform_workers", None) if timeline is not None else None
            if callable(stop_waveform):
                stop_waveform()
                stopped_any = True
        except Exception:
            pass
        return stopped_any

    def _pause_backend_runtime_for_exit(self, backend, *, context: str = "앱 종료") -> bool:
        if backend is None:
            return False
        was_busy = self._is_backend_instance_busy(backend)
        stopped_any = bool(was_busy)
        try:
            setattr(backend, "_active", False)
        except Exception:
            pass
        try:
            action_state = getattr(backend, "_action_state", None)
            if isinstance(action_state, list) and action_state:
                action_state[0] = "exit"
                stopped_any = True
        except Exception:
            pass
        for event_name in ("_edit_event", "_start_event"):
            try:
                event_obj = getattr(backend, event_name, None)
                if event_obj is not None and hasattr(event_obj, "set"):
                    event_obj.set()
                    stopped_any = True
            except Exception:
                pass

        stop_fn = getattr(backend, "stop", None)
        if callable(stop_fn) and was_busy:
            def _stop_backend_without_blocking_ui():
                try:
                    import inspect

                    params = inspect.signature(stop_fn).parameters
                    kwargs = {}
                    if "log_context" in params:
                        kwargs["log_context"] = context
                    if "unload_llm" in params:
                        kwargs["unload_llm"] = False
                    stop_fn(**kwargs)
                except TypeError:
                    try:
                        stop_fn()
                    except Exception:
                        pass
                except Exception as exc:
                    try:
                        get_logger().log(f"⚠️ {context} 중 백엔드 일시정지 실패: {exc}")
                    except Exception:
                        pass

            try:
                _main_window_threading_module().Thread(
                    target=_stop_backend_without_blocking_ui,
                    daemon=True,
                    name="fast-exit-backend-stop",
                ).start()
            except Exception:
                pass
        return stopped_any

    def _stop_auto_watchdogs_for_exit(self) -> bool:
        stopped_any = False
        for manager_name in ("_cloud_sync_manager", "_nas_sync_manager"):
            manager = getattr(self, manager_name, None)
            if manager is None:
                continue
            try:
                if bool(getattr(manager, "_running", False)):
                    stopped_any = True
                if hasattr(manager, "stop"):
                    manager.stop()
            except Exception:
                pass
        return stopped_any

    def _pause_all_runtime_work_for_exit(self, *, context: str = "앱 종료") -> bool:
        self._fast_exit_requested = True
        context = str(context or "앱 종료").strip() or "앱 종료"
        stopped_any = False
        try:
            self._shutdown_runtime_memory_manager()
        except Exception:
            pass
        try:
            self._shutdown_runtime_resource_coordinator()
        except Exception:
            pass
        try:
            self._restore_normal_cursor_for_exit()
        except Exception:
            pass
        try:
            self._detach_app_event_filter()
        except Exception:
            pass
        try:
            self._stop_post_completion_idle_timer()
        except Exception:
            pass
        try:
            stopped_any = self._stop_auto_watchdogs_for_exit() or stopped_any
        except Exception:
            pass
        try:
            self._pause_personalization_for_foreground_activity("app_exit", hold_ms=3_600_000)
            self._shutdown_personalization_idle_trainer(timeout_sec=0.0)
            stopped_any = True
        except Exception:
            pass
        try:
            stopped_any = self._pause_editor_runtime_for_exit(getattr(self, "_editor_widget", None)) or stopped_any
        except Exception:
            pass
        backends = [
            getattr(self, backend_name, None)
            for backend_name in ("backend", "backend_fast")
            if getattr(self, backend_name, None) is not None
        ]
        for backend in backends:
            try:
                stopped_any = self._pause_backend_runtime_for_exit(
                    backend,
                    context=context,
                ) or stopped_any
            except Exception:
                pass
        try:
            from core.audio.live_stt import stop_live_stt_worker

            stopped_any = bool(stop_live_stt_worker()) or stopped_any
        except Exception:
            pass
        if stopped_any and not getattr(self, "_fast_exit_pause_logged", False):
            try:
                get_logger().log("⏸️ 앱 종료: 진행 중인 작업을 즉시 일시 정지했습니다.")
            except Exception:
                pass
            self._fast_exit_pause_logged = True
        return stopped_any

    def _cleanup_runtime_for_app_exit(self, *, timeout_sec: float = 0.8) -> bool:
        """Synchronously unload heavy runtimes before the process is allowed to exit."""
        if getattr(self, "_exit_runtime_cleanup_done", False):
            return False
        self._exit_runtime_cleanup_done = True
        stopped_any = False
        try:
            self._skip_external_cleanup_in_navigation = True
            stopped_any = bool(
                self._cleanup_runtime_for_navigation(
                    context="앱 종료",
                    timeout_sec=max(0.1, float(timeout_sec or 0.8)),
                    force=True,
                    stop_active=True,
                )
            ) or stopped_any
        except Exception as exc:
            try:
                get_logger().log(f"⚠️ 앱 종료 런타임 정리 실패: {exc}")
            except Exception:
                pass
        finally:
            self._skip_external_cleanup_in_navigation = False

        try:
            from core.platform_compat import cleanup_app_runtime_processes

            cleanup_result = cleanup_app_runtime_processes(
                logger=get_logger(),
                timeout_sec=max(0.1, float(timeout_sec or 0.8)),
            )
            if any(int(value or 0) > 0 for value in cleanup_result.values()):
                stopped_any = True
        except Exception as exc:
            try:
                get_logger().log(f"⚠️ 앱 종료 외부 런타임 강제 정리 실패: {exc}")
            except Exception:
                pass

        try:
            self._clear_runtime_memory_caches(include_gpu=True)
        except Exception:
            pass
        if stopped_any:
            try:
                get_logger().log("🧹 앱 종료: STT/LLM/Ollama/GPU 런타임 메모리 정리 완료")
            except Exception:
                pass
        return stopped_any

    def _start_runtime_cleanup_for_app_exit_async(self, *, timeout_sec: float = 0.15) -> bool:
        """Kick off exit cleanup without blocking the UI shutdown path."""
        if getattr(self, "_exit_runtime_cleanup_done", False):
            return False
        thread = getattr(self, "_exit_runtime_cleanup_thread", None)
        try:
            if thread is not None and thread.is_alive():
                return False
        except Exception:
            pass

        timeout_value = max(0.05, float(timeout_sec or 0.15))

        def _run_cleanup():
            try:
                self._cleanup_runtime_for_app_exit(timeout_sec=timeout_value)
            finally:
                self._exit_runtime_cleanup_thread = None

        try:
            thread = _main_window_threading_module().Thread(
                target=_run_cleanup,
                daemon=True,
                name="app-exit-runtime-cleanup",
            )
            self._exit_runtime_cleanup_thread = thread
            thread.start()
            return True
        except Exception:
            self._exit_runtime_cleanup_thread = None
            return False

    def _is_editor_ai_busy(self, editor=None) -> bool:
        editor = editor or getattr(self, "_editor_widget", None)
        if editor is None:
            return False
        try:
            if bool(getattr(editor, "_is_ai_processing", False)):
                return True
            state_manager = getattr(editor, "sm", None)
            if state_manager is not None:
                if bool(getattr(state_manager, "is_locked", False)):
                    return True
                if str(getattr(state_manager, "state", "") or "") == "ST_PROC":
                    return True
        except RuntimeError:
            return False
        except Exception:
            pass
        return False

    def _is_backend_ai_busy(self) -> bool:
        for backend_name in ("backend", "backend_fast"):
            backend = getattr(self, backend_name, None)
            if backend is None:
                continue
            if self._is_backend_instance_busy(backend):
                return True
        return False

    def _is_backend_instance_busy(self, backend) -> bool:
        if backend is None:
            return False
        try:
            if bool(getattr(backend, "_active", False)):
                return True
            thread = getattr(backend, "_pipeline_thread", None)
            if thread is not None and getattr(thread, "is_alive", lambda: False)():
                return True
        except RuntimeError:
            return False
        except Exception:
            pass
        return False

    def _release_ai_models_for_editor_mode(
        self,
        *,
        force: bool = False,
        preserve_roughcut_status: bool = False,
        ollama_timeout_sec: float | None = None,
    ):
        if getattr(self, "_editor_ai_release_in_progress", False):
            return
        editor = getattr(self, "_editor_widget", None)
        if not force and (self._is_editor_ai_busy(editor) or self._is_backend_ai_busy()):
            return
        if not force and self._is_editor_actively_editing():
            return
        if not force and self._is_editor_video_playing(editor) and not getattr(self, "_fast_exit_requested", False):
            if not bool(getattr(self, "_editor_ai_release_retry_scheduled", False)):
                self._editor_ai_release_retry_scheduled = True

                def _retry_release():
                    self._editor_ai_release_retry_scheduled = False
                    self._release_ai_models_for_editor_mode(
                        force=force,
                        preserve_roughcut_status=preserve_roughcut_status,
                        ollama_timeout_sec=ollama_timeout_sec,
                    )

                QTimer.singleShot(2200, _retry_release)
            return

        self._editor_ai_release_in_progress = True
        try:
            try:
                if editor is not None and not preserve_roughcut_status:
                    timer = getattr(editor, "_roughcut_draft_timer", None)
                    if timer is not None:
                        timer.stop()
                    editor._roughcut_draft_pending = False
                    editor._roughcut_draft_generation = int(getattr(editor, "_roughcut_draft_generation", 0) or 0) + 1
                    if hasattr(editor, "_set_roughcut_draft_status"):
                        editor._set_roughcut_draft_status("idle")
            except Exception:
                pass

            def _release():
                try:
                    if not force and (self._is_editor_ai_busy(editor) or self._is_backend_ai_busy()):
                        return
                    stopped_runtime = False
                    for backend_name in ("backend", "backend_fast"):
                        backend = getattr(self, backend_name, None)
                        processor = getattr(backend, "video_processor", None) if backend is not None else None
                        if processor is None:
                            continue
                        try:
                            if hasattr(processor, "release_runtime_models"):
                                processor.release_runtime_models()
                                stopped_runtime = True
                            elif hasattr(processor, "stop_transcribe"):
                                processor.stop_transcribe()
                                stopped_runtime = True
                        except Exception as exc:
                            get_logger().log(f"⚠️ 에디터 모드 {backend_name} STT 모델 종료 실패: {exc}")
                    try:
                        from core.audio.live_stt import stop_live_stt_worker

                        if stop_live_stt_worker():
                            stopped_runtime = True
                    except Exception:
                        pass
                    try:
                        settings = _load_main_window_settings()
                        models = [
                            settings.get("selected_model", ""),
                            settings.get("subtitle_llm_model", ""),
                            settings.get("selected_llm_model", ""),
                            settings.get("roughcut_llm_model", ""),
                            settings.get("selected_roughcut_llm_model", ""),
                            settings.get("roughcut_model", ""),
                            getattr(config, "OLLAMA_MODEL", ""),
                        ]
                        from core.llm.ollama_provider import shutdown_local_ollama_runtime

                        shutdown_result = shutdown_local_ollama_runtime(
                            models,
                            logger=get_logger(),
                            log_context="에디터 모드",
                            timeout_sec=(
                                max(0.1, float(ollama_timeout_sec))
                                if ollama_timeout_sec is not None
                                else (1.2 if force else 0.6)
                            ),
                        )
                        if shutdown_result.get("models") or int(shutdown_result.get("processes", 0) or 0) > 0:
                            stopped_runtime = True
                    except Exception as exc:
                        get_logger().log(f"⚠️ 에디터 모드 LLM 모델 종료 실패: {exc}")
                    self._clear_runtime_memory_caches(include_gpu=True)
                    try:
                        if bool(getattr(editor, "_post_generation_models_release_requested", False)):
                            editor._post_generation_models_released = True
                            self._editor_ai_runtime_released_for_editor_mode = True
                    except Exception:
                        pass
                    if stopped_runtime:
                        now = time.monotonic()
                        last_log_at = float(getattr(self, "_editor_ai_release_last_log_at", 0.0) or 0.0)
                        if now - last_log_at >= 3.0:
                            self._editor_ai_release_last_log_at = now
                            get_logger().log("🧹 에디터 모드: AI/STT/LLM 모델을 종료하고 GPU/런타임 메모리를 정리했습니다.")
                finally:
                    self._editor_ai_release_in_progress = False

            _main_window_threading_module().Thread(
                target=_release,
                daemon=True,
                name="editor-release-ai-models",
            ).start()
        except Exception:
            self._editor_ai_release_in_progress = False
