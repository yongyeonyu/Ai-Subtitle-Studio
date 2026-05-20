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
from ui.main.main_nonfatal import (
    is_deleted_qt_runtime_error,
)


def _is_deleted_qt_runtime_error(exc: BaseException) -> bool:
    return is_deleted_qt_runtime_error(exc)


def _log_cleanup_step_failure(step: str, exc: BaseException) -> None:
    if _is_deleted_qt_runtime_error(exc):
        return
    try:
        get_logger().log(f"⚠️ 런타임 정리 단계 실패 [{step}]: {exc}")
    except Exception:
        pass


def _run_cleanup_step(step: str, callback, *, default=None, ignore_deleted_qt: bool = True):
    try:
        return callback()
    except RuntimeError as exc:
        if ignore_deleted_qt and _is_deleted_qt_runtime_error(exc):
            return default
        _log_cleanup_step_failure(step, exc)
        return default
    except Exception as exc:
        _log_cleanup_step_failure(step, exc)
        return default


def _main_window_threading_module():
    module = _run_cleanup_step(
        "main_window.threading lookup",
        lambda: __import__("ui.main.main_window", fromlist=["threading"]),
        default=None,
    )
    if module is not None:
        threading_module = getattr(module, "threading", None)
        if threading_module is not None:
            return threading_module
    return threading


def _load_main_window_settings():
    module = _run_cleanup_step(
        "main_window.load_settings lookup",
        lambda: __import__("ui.main.main_window", fromlist=["load_settings"]),
        default=None,
    )
    loader = getattr(module, "load_settings", None) if module is not None else None
    if callable(loader):
        loaded = _run_cleanup_step("main_window.load_settings call", loader, default=None)
        if loaded is not None:
            return loaded
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
            _run_cleanup_step(f"{context} post-completion idle timer stop", self._stop_post_completion_idle_timer)

            if editor is not None:
                def _reset_editor_roughcut_state():
                    timer = getattr(editor, "_roughcut_draft_timer", None)
                    if timer is not None:
                        timer.stop()
                    editor._roughcut_draft_pending = False
                    editor._roughcut_draft_generation = int(getattr(editor, "_roughcut_draft_generation", 0) or 0) + 1
                    if hasattr(editor, "_set_roughcut_draft_status"):
                        editor._set_roughcut_draft_status("idle")
                _run_cleanup_step(f"{context} editor roughcut draft reset", _reset_editor_roughcut_state)
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

                def _shutdown_editor_video_player():
                    video_player = getattr(editor, "video_player", None)
                    if video_player is not None:
                        destructive_video_cleanup = bool(force or stop_active)
                        if destructive_video_cleanup:
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
                            return
                        suspend_for_navigation = getattr(video_player, "suspend_for_navigation", None)
                        if callable(suspend_for_navigation):
                            suspend_for_navigation()
                        elif hasattr(video_player, "pause_video"):
                            video_player.pause_video()
                _run_cleanup_step(f"{context} editor video player shutdown", _shutdown_editor_video_player)

                def _stop_editor_timeline_waveform():
                    nonlocal stopped_any
                    timeline = getattr(editor, "timeline", None)
                    stop_waveform = getattr(timeline, "stop_waveform_workers", None) if timeline is not None else None
                    if callable(stop_waveform):
                        stop_waveform()
                        stopped_any = True
                _run_cleanup_step(f"{context} editor timeline waveform stop", _stop_editor_timeline_waveform)

                if force and hasattr(editor, "_cleanup"):
                    _run_cleanup_step(f"{context} editor cleanup", editor._cleanup)

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

            def _stop_live_stt():
                nonlocal stopped_any
                from core.audio.live_stt import stop_live_stt_worker

                if stop_live_stt_worker():
                    stopped_any = True
            _run_cleanup_step(f"{context} live stt stop", _stop_live_stt)

            skip_external_cleanup = bool(getattr(self, "_skip_external_cleanup_in_navigation", False))
            if not skip_external_cleanup:
                try:
                    from core.platform_compat import cleanup_app_runtime_processes

                    cleanup_result = cleanup_app_runtime_processes(logger=get_logger(), timeout_sec=timeout_sec)
                    if any(int(v or 0) > 0 for v in cleanup_result.values()):
                        stopped_any = True
                except Exception as exc:
                    get_logger().log(f"⚠️ {context} 중 외부 런타임 정리 실패: {exc}")

            _run_cleanup_step(f"{context} gc.collect", gc.collect)

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
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is not None:
            try:
                if bool(getattr(trainer, "is_busy", lambda: False)()) or bool(
                    getattr(trainer, "_current_learning_mode", "")
                ):
                    return True
            except Exception:
                try:
                    if bool(getattr(trainer, "_current_learning_mode", "")):
                        return True
                except Exception:
                    pass
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

    def _schedule_forced_exit_for_busy_about_to_quit(self) -> bool:
        schedule_exit = getattr(self, "_schedule_forced_process_exit", None)
        if not callable(schedule_exit):
            return False
        try:
            should_force = bool(self._has_active_runtime_work_for_exit())
        except Exception:
            should_force = False
        if not should_force:
            return False
        delay_ms = 80 if getattr(config, "IS_MAC", False) else 320
        _run_cleanup_step(
            "app about-to-quit forced process exit",
            lambda: schedule_exit(delay_ms=delay_ms),
            default=None,
        )
        return True

    def _restore_normal_cursor(self, *widgets) -> None:
        app = QApplication.instance()
        if app is not None:
            for _ in range(32):
                try:
                    if QApplication.overrideCursor() is None:
                        break
                    if _run_cleanup_step("restore override cursor", QApplication.restoreOverrideCursor, default=False) is False:
                        break
                except Exception:
                    break
        for widget in widgets:
            if widget is None:
                continue
            targets = [widget]
            viewport_getter = getattr(widget, "viewport", None)
            if callable(viewport_getter):
                viewport = _run_cleanup_step("widget viewport lookup", viewport_getter, default=None)
                if viewport is not None:
                    targets.append(viewport)
            for attr_name in ("timeline", "video_player", "text_edit", "canvas", "global_canvas"):
                child = getattr(widget, attr_name, None)
                if child is not None:
                    targets.append(child)
                    child_viewport_getter = getattr(child, "viewport", None)
                    if callable(child_viewport_getter):
                        child_viewport = _run_cleanup_step("child viewport lookup", child_viewport_getter, default=None)
                        if child_viewport is not None:
                            targets.append(child_viewport)
                    for nested_name in ("canvas", "global_canvas"):
                        nested_child = getattr(child, nested_name, None)
                        if nested_child is not None:
                            targets.append(nested_child)
            for target in targets:
                if target is None:
                    continue
                _run_cleanup_step("cursor unset", target.unsetCursor, default=None)

    def _clear_runtime_memory_caches(self, *, include_gpu: bool = True) -> None:
        def _clear_shared_runtime_caches():
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
        _run_cleanup_step("shared runtime cache trim", _clear_shared_runtime_caches)
        for owner in (self, getattr(self, "backend", None), getattr(self, "backend_fast", None)):
            if owner is None:
                continue
            def _clear_prefetch_cache(target=owner):
                cache = getattr(target, "_prefetch_cache", None)
                if isinstance(cache, dict):
                    cache.clear()
            _run_cleanup_step("prefetch cache clear", _clear_prefetch_cache)
            for attr_name in (
                "_cut_boundary_pipeline_cache",
                "_auto_audio_tune_cache",
                "_runtime_auto_audio_tune",
                "_runtime_auto_audio_decision",
                "_speaker_map",
            ):
                def _clear_owner_payload(target=owner, name=attr_name):
                    payload = getattr(target, name, None)
                    if isinstance(payload, dict):
                        payload.clear()
                    elif isinstance(payload, list):
                        payload.clear()
                _run_cleanup_step(f"{attr_name} clear", _clear_owner_payload)
        _run_cleanup_step("runtime cache gc.collect", gc.collect)
        if not include_gpu:
            return
        # GPU and MLX cache trimming is already routed through
        # core.runtime.memory_manager.trim_runtime_memory_caches above.

    def _shutdown_runtime_memory_manager(self) -> None:
        _run_cleanup_step(
            "runtime memory timer stop",
            lambda: getattr(self, "_runtime_memory_timer", None).stop()
            if getattr(self, "_runtime_memory_timer", None) is not None
            and hasattr(getattr(self, "_runtime_memory_timer", None), "stop")
            else None,
        )
        _run_cleanup_step(
            "runtime memory manager stop",
            lambda: getattr(self, "_runtime_memory_manager", None).stop()
            if getattr(self, "_runtime_memory_manager", None) is not None
            and hasattr(getattr(self, "_runtime_memory_manager", None), "stop")
            else None,
        )

    def _shutdown_runtime_resource_coordinator(self) -> None:
        _run_cleanup_step(
            "runtime resource timer stop",
            lambda: getattr(self, "_runtime_resource_timer", None).stop()
            if getattr(self, "_runtime_resource_timer", None) is not None
            and hasattr(getattr(self, "_runtime_resource_timer", None), "stop")
            else None,
        )
        _run_cleanup_step(
            "runtime resource coordinator exit mode",
            lambda: getattr(self, "_runtime_resource_coordinator", None).set_exit_mode(True)
            if getattr(self, "_runtime_resource_coordinator", None) is not None
            and hasattr(getattr(self, "_runtime_resource_coordinator", None), "set_exit_mode")
            else None,
        )

    def _handle_runtime_memory_pressure(self, stage: str, snapshot: dict | None = None):
        stage_text = str(stage or "normal").strip().lower()
        if stage_text == "normal":
            return {"stage": "normal", "actions": []}
        actions: list[str] = []
        include_gpu = stage_text == "critical"
        if _run_cleanup_step(
            f"runtime memory pressure {stage_text} cache clear",
            lambda: self._clear_runtime_memory_caches(include_gpu=include_gpu),
            default=False,
        ) is not False:
            actions.append("clear_runtime_memory_caches")
        if stage_text == "critical":
            try:
                busy = bool(self._is_editor_ai_busy(getattr(self, "_editor_widget", None)) or self._is_backend_ai_busy())
            except Exception:
                busy = True
            if not busy:
                if _run_cleanup_step(
                    "runtime memory pressure release ai models",
                    lambda: self._release_ai_models_for_editor_mode(
                        force=True,
                        preserve_roughcut_status=True,
                        ollama_timeout_sec=1.2,
                    ),
                    default=False,
                ) is not False:
                    actions.append("release_ai_models")
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
                canvas = getattr(timeline, "canvas", None)
                if canvas is not None:
                    try:
                        canvas._editor_processing_input_locked = False
                        canvas.setProperty("editor_processing_input_locked", False)
                    except Exception:
                        pass
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
        _run_cleanup_step("force editor idle auto processing reset", lambda: setattr(self, "_auto_processing_active", False))
        self._restore_normal_cursor(*widgets)
        for delay_ms in (0, 80, 240, 700):
            _run_cleanup_step(
                f"force editor idle cursor restore timer {delay_ms}ms",
                lambda saved_delay=delay_ms: QTimer.singleShot(
                    saved_delay,
                    lambda saved_widgets=tuple(widgets): self._restore_normal_cursor(*saved_widgets),
                ),
            )
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

    def _post_generation_release_retry_needed(self, editor=None) -> bool:
        target_editor = editor if editor is not None else getattr(self, "_editor_widget", None)
        if target_editor is None:
            return False
        try:
            requested = bool(getattr(target_editor, "_post_generation_models_release_requested", False))
            released = bool(getattr(target_editor, "_post_generation_models_released", False))
            return requested and not released
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
            _run_cleanup_step(
                "post generation runtime cache clear",
                lambda: self._clear_runtime_memory_caches(include_gpu=True),
            )
            if self._post_generation_release_retry_needed(editor):
                # Warm-session slowdown shows up when the first async release
                # request is missed and the next generation starts with stale
                # STT/LLM residency still attached to the finished run.
                _run_cleanup_step(
                    "post generation model release retry",
                    lambda: self._release_ai_models_for_editor_mode(
                        force=True,
                        preserve_roughcut_status=True,
                        ollama_timeout_sec=1.2,
                    ),
                )
                if self._post_generation_release_retry_needed(editor) or bool(
                    getattr(self, "_editor_ai_release_in_progress", False)
                ):
                    self._schedule_post_generation_gc(editor=editor, delay_ms=1600)

        QTimer.singleShot(max(0, int(delay_ms)), _run_gc)

    def _schedule_forced_process_exit(self, *, delay_ms: int = 250):
        if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
            return
        delay_sec = max(0.02, float(max(20, int(delay_ms))) / 1000.0)
        if getattr(config, "IS_MAC", False):
            _run_cleanup_step(
                "native forced process exit watchdog",
                lambda: __import__(
                    "core.native_macos_exit",
                    fromlist=["schedule_native_forced_exit"],
                ).schedule_native_forced_exit(
                    pid=os.getpid(),
                    delay_ms=max(0, int(delay_ms)),
                    term_grace_ms=50,
                ),
                default=False,
            )
        try:
            timer = _main_window_threading_module().Timer(delay_sec, lambda: os._exit(0))
            timer.daemon = True
            timer.start()
        except Exception as exc:
            _log_cleanup_step_failure("forced process exit threading timer", exc)
        _run_cleanup_step(
            "forced process exit qt timer",
            lambda: QTimer.singleShot(max(20, int(delay_ms)), lambda: os._exit(0)),
        )

    def _pause_editor_runtime_for_exit(self, editor) -> bool:
        if editor is None:
            return False
        stopped_any = False
        abort_result = _run_cleanup_step(
            "pause editor abort pending ui work",
            lambda: getattr(editor, "_abort_pending_editor_processing_ui_work", None)()
            if callable(getattr(editor, "_abort_pending_editor_processing_ui_work", None))
            else False,
            default=False,
        )
        if abort_result is not False:
            stopped_any = True
        stop_result = _run_cleanup_step(
            "pause editor state manager stop_processing",
            lambda: getattr(getattr(editor, "sm", None), "stop_processing")("앱 종료로 작업을 일시 정지했습니다.")
            if getattr(editor, "sm", None) is not None
            and hasattr(getattr(editor, "sm", None), "stop_processing")
            else False,
            default=False,
        )
        if stop_result is not False:
            stopped_any = True
        for timer_name in ("_spinner_timer", "_roughcut_draft_timer", "_cut_boundary_scan_timer"):
            timer_result = _run_cleanup_step(
                f"pause editor timer stop {timer_name}",
                lambda name=timer_name: getattr(editor, name, None).stop()
                if getattr(editor, name, None) is not None
                and hasattr(getattr(editor, name, None), "stop")
                else False,
                default=False,
            )
            if timer_result is not False:
                stopped_any = True
        _run_cleanup_step(
            "pause editor roughcut pending reset",
            lambda: (
                setattr(editor, "_roughcut_draft_pending", False),
                setattr(
                    editor,
                    "_roughcut_draft_generation",
                    int(getattr(editor, "_roughcut_draft_generation", 0) or 0) + 1,
                ),
            ),
        )
        def _pause_editor_video():
            nonlocal stopped_any
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
        _run_cleanup_step("pause editor video player", _pause_editor_video)
        def _stop_timeline_waveform():
            nonlocal stopped_any
            timeline = getattr(editor, "timeline", None)
            stop_waveform = getattr(timeline, "stop_waveform_workers", None) if timeline is not None else None
            if callable(stop_waveform):
                stop_waveform()
                stopped_any = True
        _run_cleanup_step("pause editor timeline waveform", _stop_timeline_waveform)
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
            def _stop_manager(target=manager):
                nonlocal stopped_any
                if bool(getattr(target, "_running", False)):
                    stopped_any = True
                if hasattr(target, "stop"):
                    target.stop()
            _run_cleanup_step(f"stop auto watchdog {manager_name}", _stop_manager)
        return stopped_any

    def _pause_all_runtime_work_for_exit(self, *, context: str = "앱 종료") -> bool:
        self._fast_exit_requested = True
        context = str(context or "앱 종료").strip() or "앱 종료"
        stopped_any = False
        _run_cleanup_step("app exit shutdown runtime memory manager", self._shutdown_runtime_memory_manager)
        _run_cleanup_step("app exit shutdown runtime resource coordinator", self._shutdown_runtime_resource_coordinator)
        _run_cleanup_step("app exit restore cursor", self._restore_normal_cursor_for_exit)
        _run_cleanup_step("app exit detach app event filter", self._detach_app_event_filter)
        _run_cleanup_step("app exit stop post completion idle timer", self._stop_post_completion_idle_timer)
        watchdog_result = _run_cleanup_step("app exit stop auto watchdogs", self._stop_auto_watchdogs_for_exit, default=False)
        stopped_any = bool(watchdog_result) or stopped_any
        dialog_stop_result = _run_cleanup_step(
            "app exit stop personalization dialogs",
            lambda: self._request_personalization_stop_for_user_input()
            if hasattr(self, "_request_personalization_stop_for_user_input")
            else None,
            default=None,
        )
        stopped_any = bool(dialog_stop_result) or stopped_any
        def _pause_personalization_trainer():
            nonlocal stopped_any
            trainer = getattr(self, "_personalization_idle_trainer", None)
            self._lora_foreground_busy_until_ms = int(time.time() * 1000) + 3_600_000
            self._lora_foreground_busy_reason = "app_exit"
            if trainer is not None:
                request_stop = getattr(trainer, "request_immediate_stop", None)
                if callable(request_stop):
                    request_stop(
                        reason="app_exit",
                        hold_ms=3_600_000,
                        join_timeout_sec=0.0,
                        cleanup=False,
                    )
                else:
                    try:
                        trainer.suspend_for_foreground_activity(
                            reason="app_exit",
                            hold_ms=3_600_000,
                            cleanup=False,
                        )
                    except TypeError:
                        trainer.suspend_for_foreground_activity(
                            reason="app_exit",
                            hold_ms=3_600_000,
                        )
            self._shutdown_personalization_idle_trainer(
                timeout_sec=0.0,
                cleanup=False,
                recover=False,
            )
            stopped_any = True
        _run_cleanup_step("app exit pause personalization trainer", _pause_personalization_trainer)
        editor_pause_result = _run_cleanup_step(
            "app exit pause editor runtime",
            lambda: self._pause_editor_runtime_for_exit(getattr(self, "_editor_widget", None)),
            default=False,
        )
        stopped_any = bool(editor_pause_result) or stopped_any
        backends = [
            getattr(self, backend_name, None)
            for backend_name in ("backend", "backend_fast")
            if getattr(self, backend_name, None) is not None
        ]
        for backend in backends:
            backend_pause_result = _run_cleanup_step(
                f"app exit pause backend runtime {type(backend).__name__}",
                lambda current_backend=backend: self._pause_backend_runtime_for_exit(
                    current_backend,
                    context=context,
                ),
                default=False,
            )
            stopped_any = bool(backend_pause_result) or stopped_any
        def _stop_live_stt_for_exit():
            nonlocal stopped_any
            from core.audio.live_stt import stop_live_stt_worker

            stopped_any = bool(stop_live_stt_worker()) or stopped_any
        _run_cleanup_step("app exit stop live stt", _stop_live_stt_for_exit)
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

        _run_cleanup_step("app exit clear runtime memory caches", lambda: self._clear_runtime_memory_caches(include_gpu=True))
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
            if editor is not None and not preserve_roughcut_status:
                _run_cleanup_step(
                    "editor ai release roughcut draft reset",
                    lambda: (
                        getattr(editor, "_roughcut_draft_timer", None).stop()
                        if getattr(editor, "_roughcut_draft_timer", None) is not None
                        else None,
                        setattr(editor, "_roughcut_draft_pending", False),
                        setattr(
                            editor,
                            "_roughcut_draft_generation",
                            int(getattr(editor, "_roughcut_draft_generation", 0) or 0) + 1,
                        ),
                        getattr(editor, "_set_roughcut_draft_status", lambda *_args, **_kwargs: None)("idle"),
                    ),
                )

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
                    except Exception as exc:
                        _log_cleanup_step_failure("editor ai release live stt stop", exc)
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
                    _run_cleanup_step(
                        "editor ai release post-generation flags",
                        lambda: (
                            setattr(editor, "_post_generation_models_released", True),
                            setattr(self, "_editor_ai_runtime_released_for_editor_mode", True),
                        )
                        if bool(getattr(editor, "_post_generation_models_release_requested", False))
                        else None,
                    )
                    if stopped_runtime:
                        now = time.monotonic()
                        last_log_at = float(getattr(self, "_editor_ai_release_last_log_at", 0.0) or 0.0)
                        if now - last_log_at >= 600.0:
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
