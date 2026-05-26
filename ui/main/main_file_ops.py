# Version: 03.14.23
# Phase: PHASE1-B
"""
ui/main/main_file_ops.py
FileOpsMixin — 파일/폴더 선택 · 배치 시작 · 멀티클립 진입 · 캐시 삭제 · 종료
"""
import os

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QApplication
from PyQt6.QtCore import QTimer

from core.path_manager import (
    get_last_folder, set_last_folder,
    ensure_nas_mounted, get_recent_folders, add_recent_folder,
)
from core.runtime import config
from core.settings import load_settings, save_settings
from core.work_mode import EDITOR_MODE, ROUGHCUT_MODE, SHORTFORM_MODE, normalize_work_mode
from ui.editor.editor_save_manager import (
    backup_project_file_copy,
    clear_reusable_caches,
    reusable_cache_paths as _editor_reusable_cache_paths,
)
from ui.dialogs.message_box import ask_yes_no, confirm_save_changes, show_message
from ui.main.main_nonfatal import call_nonfatal_ui_step, run_nonfatal_ui_step
from ui.queue.queue_formatting import build_queue_header_payload
from ui.project.project_session_runtime import (
    clear_multiclip_runtime_state,
    detach_project_session,
    set_runtime_multiclip_state,
)

FILE_DIALOG_SELECTED_PRIORITY_HOLD_MS = 4500
FILE_DIALOG_CANCEL_PRIORITY_HOLD_MS = 500


def _reusable_cache_paths() -> list[str]:
    return _editor_reusable_cache_paths()


class FileOpsMixin:
    """파일/폴더 선택 및 배치·멀티클립 모드 진입 관련 메서드."""

    def _file_ops_log_failure(self, step: str, exc: BaseException) -> None:
        try:
            from core.runtime.logger import get_logger

            get_logger().log(f"⚠️ 파일 작업 실패 [{step}]: {exc}")
        except Exception:
            pass

    def _confirm_save_dirty_editor_before_exit(self) -> bool:
        self._editor_exit_save_completed = False
        self._editor_exit_save_skipped = False
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return True
        helper = getattr(editor, "_confirm_close_before_exit", None)
        if callable(helper):
            before_dirty = bool(getattr(editor, "_is_dirty", False))
            ok = bool(helper("종료 확인"))
            after_dirty = bool(getattr(editor, "_is_dirty", False))
            if ok and before_dirty and not after_dirty:
                self._editor_exit_save_completed = True
            elif ok and before_dirty and after_dirty:
                self._editor_exit_save_skipped = True
            return ok
        try:
            dirty_checker = getattr(editor, "_has_unsaved_changes", None)
            if callable(dirty_checker):
                is_dirty = bool(dirty_checker())
            elif hasattr(editor, "sm"):
                is_dirty = bool(getattr(editor.sm, "is_dirty", False))
            else:
                is_dirty = bool(getattr(editor, "_is_dirty", False))
        except Exception:
            is_dirty = bool(getattr(editor, "_is_dirty", False))
        if not is_dirty:
            return True

        reply = confirm_save_changes(self, title="종료 확인")
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.No:
            self._editor_exit_save_skipped = True
            return True

        fast_exit_save = getattr(editor, "_on_save_for_exit", None)
        save = fast_exit_save if callable(fast_exit_save) else getattr(editor, "_on_save", None)
        if not callable(save):
            return True
        try:
            if callable(fast_exit_save) and save is fast_exit_save:
                saved = bool(save())
            else:
                saved = bool(save(skip_auto_next=True))
        except TypeError:
            saved = bool(save())
        except Exception as exc:
            show_message(
                self,
                "저장 실패",
                f"종료 전 저장을 완료하지 못했습니다.\n{exc}",
                icon=QMessageBox.Icon.Warning,
                buttons=QMessageBox.StandardButton.Ok,
                default=QMessageBox.StandardButton.Ok,
            )
            return False
        if not saved:
            show_message(
                self,
                "저장 확인",
                "저장할 자막 세그먼트를 찾지 못했거나 저장이 완료되지 않았습니다.\n종료를 취소하고 상태를 확인해 주세요.",
                icon=QMessageBox.Icon.Warning,
                buttons=QMessageBox.StandardButton.Ok,
                default=QMessageBox.StandardButton.Ok,
            )
            return False
        self._editor_exit_save_completed = True
        return True

    def _prepare_dialog_state(self):
        pause_lora = getattr(self, "_pause_personalization_for_foreground_activity", None)
        if callable(pause_lora):
            run_nonfatal_ui_step("파일 작업", "file dialog foreground pause", lambda: pause_lora("file_dialog"), default=None)
        call_nonfatal_ui_step("파일 작업", self, "raise_", step="dialog owner raise", default=None)
        call_nonfatal_ui_step("파일 작업", self, "activateWindow", step="dialog owner activate", default=None)
        fw = run_nonfatal_ui_step("파일 작업", "focus widget lookup", QApplication.focusWidget, default=None)
        if fw is not None:
            call_nonfatal_ui_step("파일 작업", fw, "clearFocus", step="focus clear", default=None)
        call_nonfatal_ui_step("파일 작업", self, "unsetCursor", step="dialog state cursor unset", default=None)
        call_nonfatal_ui_step("파일 작업", self, "update", step="dialog state update", default=None)
        run_nonfatal_ui_step("파일 작업", "dialog state processEvents", QApplication.processEvents, default=None)

    def _dialog_start_folder(self, folder):
        path = str(folder or "").strip() or os.path.expanduser("~")
        if os.path.isfile(path):
            path = os.path.dirname(path)
        if not os.path.isdir(path):
            path = os.path.expanduser("~")
        return path

    def _dialog_result_has_selection(self, result) -> bool:
        selected = result[0] if isinstance(result, tuple) and result else result
        if isinstance(selected, (list, tuple, set)):
            return bool(selected)
        return bool(str(selected or "").strip())

    def _finish_file_dialog_foreground(self, result=None):
        self._file_dialog_active = False
        self._schedule_foreground_file_open_priority_clear(result)
        if self._dialog_result_has_selection(result):
            self._pending_home_auto_source_rebuild = False
            return
        if not bool(getattr(self, "_pending_home_auto_source_rebuild", False)):
            return
        self._pending_home_auto_source_rebuild = False

        def _rebuild_if_home():
            stack = getattr(self, "stack", None)
            if stack is not None:
                try:
                    if int(stack.currentIndex()) != 0:
                        return
                except Exception:
                    return
            rebuild = getattr(self, "_build_home_content", None)
            if callable(rebuild):
                rebuild()

        QTimer.singleShot(0, _rebuild_if_home)

    def _schedule_foreground_file_open_priority_clear(self, result=None):
        delay_ms = (
            FILE_DIALOG_SELECTED_PRIORITY_HOLD_MS
            if self._dialog_result_has_selection(result)
            else FILE_DIALOG_CANCEL_PRIORITY_HOLD_MS
        )

        def _clear_priority():
            self._foreground_file_open_requested = False
            resume_release = getattr(self, "_resume_deferred_editor_ai_release_after_file_open", None)
            if callable(resume_release):
                resume_release()

        QTimer.singleShot(delay_ms, _clear_priority)

    def _run_foreground_file_dialog(self, opener):
        self._foreground_file_open_requested = True
        suspend_startup = getattr(self, "_suspend_startup_background_for_foreground_action", None)
        if callable(suspend_startup):
            suspend_startup("file_dialog", hold_ms=FILE_DIALOG_SELECTED_PRIORITY_HOLD_MS)
        self._file_dialog_active = True
        result = None
        try:
            self._prepare_dialog_state()
            result = opener()
            return result
        finally:
            self._finish_file_dialog_foreground(result)

    def _safe_open_file_names(self, title, folder, flt):
        folder = self._dialog_start_folder(folder)
        return self._run_foreground_file_dialog(
            lambda: QFileDialog.getOpenFileNames(self, title, folder, flt)
        )

    def _safe_open_file_name(self, title, folder, flt):
        folder = self._dialog_start_folder(folder)
        return self._run_foreground_file_dialog(
            lambda: QFileDialog.getOpenFileName(self, title, folder, flt)
        )

    def _safe_open_directory(self, title, folder):
        folder = self._dialog_start_folder(folder)
        return self._run_foreground_file_dialog(
            lambda: QFileDialog.getExistingDirectory(self, title, folder)
        )

    def _add_recent_folder(self, folder_path):
        if not folder_path or not str(folder_path).strip():
            return
        add_recent_folder(folder_path)
        self.recent_folders = get_recent_folders()
        settings = load_settings()
        recent = settings.get("recent_folders", [])
        if folder_path in recent:
            recent.remove(folder_path)
        recent.insert(0, folder_path)
        self.recent_folders = recent[:10]
        settings["recent_folders"] = self.recent_folders
        save_settings(settings)
        if self.add_recent_folder_callback:
            self.add_recent_folder_callback(folder_path)

    def _prepare_single_file_queue(self, files):
        files = list(files or [])
        if not files:
            return
        if hasattr(self, "init_queue_list"):
            self.init_queue_list(files)
        if hasattr(self, "_sig_update_queue_header_payload"):
            self._sig_update_queue_header_payload.emit(
                build_queue_header_payload(1, len(files), 0, "")
            )

    def _clear_multiclip_runtime_state(self):
        clear_multiclip_runtime_state(self)

    def select_files(self):
        paths, _ = self._safe_open_file_names(
            "파일 선택",
            get_last_folder() or os.path.expanduser("~"),
            "Media/SRT Files (*.mp4 *.mov *.MOV *.MP4 *.wav *.m4a *.m2a *.mp3 *.aac *.srt)",
        )
        if not paths:
            return
        set_last_folder(os.path.dirname(paths[0]))
        self._add_recent_folder(os.path.dirname(paths[0]))
        self._auto_export_subtitle_video = True
        self._auto_audio_tune_per_file = True
        if hasattr(self, "_clear_runtime_quality_override"):
            self._clear_runtime_quality_override()
        detach_project_session(self, auto_pipeline=False)
        srt = [p for p in paths if p.lower().endswith(".srt")]
        vid = [p for p in paths if not p.lower().endswith(".srt")]
        if vid and len(vid) > 1:
            self._show_multiclip_then_batch(vid, show_multiclip=True)
        elif vid and len(vid) == 1 and self.backend:
            if hasattr(self, "clear_queue_list"):
                self.clear_queue_list()
            self.backend.start_pipeline(vid)
        elif srt:
            if hasattr(self, "clear_queue_list"):
                self.clear_queue_list()
            self._open_srt_in_editor(srt[0])

    def _start_queue_mode(self, files, folder=None, source="queue"):
        """폴더/NAS/iCloud 공용 큐 모드: 클립을 하나씩 열고 시작 버튼 흐름으로 자동 처리."""
        if not files:
            return

        pause_lora = getattr(self, "_pause_personalization_for_foreground_activity", None)
        if callable(pause_lora):
            pause_lora(f"{source}_queue_start")

        if getattr(self, "_queue_mode_starting", False):
            return
        self._queue_mode_starting = True

        try:
            self._is_queue_mode = True
            self._auto_export_subtitle_video = True
            self._auto_audio_tune_per_file = True
            detach_project_session(self, auto_pipeline=True)
            if not self.backend:
                return
            if getattr(self.backend, "_active", False):
                return
            if hasattr(self, "_prepare_single_file_queue"):
                self._prepare_single_file_queue(files)
            self.backend.start_pipeline(files, folder=folder, is_auto_start=True)
        finally:
            QTimer.singleShot(500, lambda: setattr(self, "_queue_mode_starting", False))

    def _start_batch(self, files, folder=None):
        """기존 호출부 호환용 별칭 — 내부적으로 공용 큐 모드를 사용한다."""
        return self._start_queue_mode(files, folder=folder, source="batch")

    def select_folder(self):
        folder = self._safe_open_directory(
            "폴더 선택", get_last_folder() or os.path.expanduser("~")
        )
        if not folder:
            return
        set_last_folder(folder)
        self._add_recent_folder(folder)
        self._auto_export_subtitle_video = True
        self._auto_audio_tune_per_file = True
        if hasattr(self, "_clear_runtime_quality_override"):
            self._clear_runtime_quality_override()
        detach_project_session(self, auto_pipeline=False)
        from ui.dialogs.folder_dialog import FolderDialog

        dlg = FolderDialog(folder, self)
        if dlg.exec() and getattr(dlg, "saved_only", False):
            return
        if dlg.result() and dlg.selected_files:
            self._auto_export_subtitle_video = True
            self._start_queue_mode(dlg.selected_files, folder=folder, source="folder")

    def _open_recent(self, folder):
        if not os.path.exists(folder):
            if not ensure_nas_mounted(folder):
                QMessageBox.warning(
                    self, "오류", f"폴더를 찾을 수 없습니다:\n{folder}"
                )
                return
        set_last_folder(folder)
        self._add_recent_folder(folder)
        self._auto_export_subtitle_video = True
        self._auto_audio_tune_per_file = True
        if hasattr(self, "_clear_runtime_quality_override"):
            self._clear_runtime_quality_override()
        detach_project_session(self, auto_pipeline=False)
        paths, _ = self._safe_open_file_names(
            "파일 선택",
            folder,
            "Media/SRT Files (*.mp4 *.mov *.MOV *.MP4 *.wav *.m4a *.m2a *.mp3 *.aac *.srt)",
        )
        if not paths:
            return
        srt = [p for p in paths if p.lower().endswith(".srt")]
        vid = [p for p in paths if not p.lower().endswith(".srt")]
        if srt:
            if hasattr(self, "clear_queue_list"):
                self.clear_queue_list()
            self._open_srt_in_editor(srt[0])
        elif vid and len(vid) == 1 and self.backend:
            if hasattr(self, "clear_queue_list"):
                self.clear_queue_list()
            self.backend.start_pipeline(vid)
        elif vid and len(vid) > 1:
            self._show_multiclip_then_batch(vid, show_multiclip=False)

    def open_editor_directly(self):
        path, _ = self._safe_open_file_name(
            "SRT 파일 선택",
            get_last_folder() or os.path.expanduser("~"),
            "SRT Files (*.srt)",
        )
        if path:
            set_last_folder(os.path.dirname(path))
            self._add_recent_folder(os.path.dirname(path))
            self._open_srt_in_editor(path)

    def _show_multiclip_then_batch(self, files, folder=None, show_multiclip=True):
        from ui.project.multiclip_panel import MultiClipEditor

        pause_lora = getattr(self, "_pause_personalization_for_foreground_activity", None)
        if callable(pause_lora):
            run_nonfatal_ui_step("파일 작업", "multiclip foreground pause", lambda: pause_lora("multiclip_open"), default=None)

        dlg = MultiClipEditor(files, self, show_multiclip=show_multiclip)
        if dlg.exec():
            set_runtime_multiclip_state(
                self,
                list(dlg.sorted_files),
                [],
                project_boundary_rows=None,
                emit_boundary_signal=False,
            )
            if self.backend:
                self.backend.start_multiclip_pipeline(
                    dlg.sorted_files, folder=folder
                )

    def _clear_cache(self):
        if ask_yes_no(
            self,
            "캐쉬 삭제",
            "컷경계, VAD, 음성필터/전처리, 파형 등 재사용 캐쉬 파일을 모두 삭제하시겠습니까?",
            default_no=True,
        ):
            try:
                removed_count = int(clear_reusable_caches(main_window=self) or 0)
                show_message(
                    self,
                    "완료",
                    f"컷경계/VAD/음성필터/파형 등 재사용 캐쉬 {removed_count}개 삭제 완료",
                    icon=QMessageBox.Icon.Information,
                    buttons=QMessageBox.StandardButton.Ok,
                    default=QMessageBox.StandardButton.Ok,
                )
                self._restore_current_work_mode()
            except Exception as e:
                show_message(
                    self,
                    "오류",
                    f"삭제 중 오류: {e}",
                    icon=QMessageBox.Icon.Warning,
                    buttons=QMessageBox.StandardButton.Ok,
                    default=QMessageBox.StandardButton.Ok,
                )

    def _quick_exit(self):
        confirm_exit = getattr(self, "_confirm_save_dirty_editor_before_exit", None)
        if callable(confirm_exit) and not confirm_exit():
            return
        self._quick_exit_requested = True
        exit_delay_ms = 20 if getattr(config, "IS_MAC", False) else 60
        schedule_exit = getattr(self, "_schedule_forced_process_exit", None)
        if callable(schedule_exit):
            run_nonfatal_ui_step(
                "파일 작업",
                "강제 종료 예약",
                lambda: schedule_exit(delay_ms=exit_delay_ms),
                default=None,
            )
        busy_before_exit = bool(
            run_nonfatal_ui_step(
                "파일 작업",
                "종료 전 활성 런타임 확인",
                self._has_active_runtime_work_for_exit,
                default=False,
            )
        )

        pause_runtime = getattr(self, "_pause_all_runtime_work_for_exit", None)
        try:
            if callable(pause_runtime):
                pause_runtime(context="앱 종료")
            elif self.backend:
                try:
                    self.backend.stop(log_context="앱 종료", unload_llm=False)
                except TypeError:
                    self.backend.stop()
        except Exception as exc:
            self._file_ops_log_failure("종료 중 작업 일시정지", exc)

        cleanup_runtime_async = getattr(self, "_start_runtime_cleanup_for_app_exit_async", None)
        exit_cleanup_timeout = 0.08 if getattr(config, "IS_MAC", False) else 0.15
        try:
            if callable(cleanup_runtime_async):
                cleanup_runtime_async(timeout_sec=exit_cleanup_timeout)
            else:
                cleanup_runtime_sync = getattr(self, "_cleanup_runtime_for_app_exit", None)
                if callable(cleanup_runtime_sync):
                    cleanup_runtime_sync(timeout_sec=exit_cleanup_timeout)
        except Exception as exc:
            self._file_ops_log_failure("종료 중 런타임 정리 시작", exc)

        if not busy_before_exit:
            run_nonfatal_ui_step(
                "파일 작업",
                "종료 전 백업",
                lambda: self._backup_before_quick_exit(include_project_backup=False),
                default=None,
            )
        else:
            run_nonfatal_ui_step(
                "파일 작업",
                "종료 전 백업 생략 로그",
                lambda: __import__("core.runtime.logger", fromlist=["get_logger"]).get_logger().log(
                    "⏸️ 종료 전 백업은 생략하고, 진행 중 작업 일시 정지를 우선했습니다."
                ),
                default=None,
            )
        call_nonfatal_ui_step("파일 작업", self, "close", step="빠른 종료 close", default=None)
        QApplication.quit()

    def _restore_current_work_mode(self):
        mode = normalize_work_mode(getattr(self, "_current_work_mode", EDITOR_MODE))
        self._current_work_mode = mode
        if mode == ROUGHCUT_MODE and hasattr(self, "_open_roughcut_helper"):
            self._open_roughcut_helper()
        elif mode == SHORTFORM_MODE and hasattr(self, "_open_shortform_maker"):
            self._open_shortform_maker()
        elif mode == EDITOR_MODE and hasattr(self, "_open_editor_screen") and getattr(self, "_editor_widget", None) is not None:
            self._open_editor_screen()

    def _backup_before_quick_exit(self, *, include_project_backup: bool = True):
        project_path = str(getattr(self, "_current_project_path", "") or "")
        if include_project_backup and project_path and os.path.exists(project_path):
            try:
                backup_project_file_copy(project_path)
            except Exception as exc:
                self._file_ops_log_failure("종료 전 프로젝트 백업", exc)
