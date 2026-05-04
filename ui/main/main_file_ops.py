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
from core.settings import load_settings, save_settings
from core.work_mode import EDITOR_MODE, ROUGHCUT_MODE, SHORTFORM_MODE, normalize_work_mode


class FileOpsMixin:
    """파일/폴더 선택 및 배치·멀티클립 모드 진입 관련 메서드."""

    def _prepare_dialog_state(self):
        try:
            fw = QApplication.focusWidget()
            if fw is not None:
                fw.clearFocus()
        except Exception:
            pass
        try:
            self.unsetCursor()
            self.update()
        except Exception:
            pass
        QApplication.processEvents()

    def _safe_open_file_names(self, title, folder, flt):
        self._prepare_dialog_state()
        return QFileDialog.getOpenFileNames(self, title, folder, flt)

    def _safe_open_file_name(self, title, folder, flt):
        self._prepare_dialog_state()
        return QFileDialog.getOpenFileName(self, title, folder, flt)

    def _safe_open_directory(self, title, folder):
        self._prepare_dialog_state()
        return QFileDialog.getExistingDirectory(self, title, folder)

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
        if hasattr(self, "_sig_update_queue_header"):
            self._sig_update_queue_header.emit(1, len(files), 0, "")

    def _clear_multiclip_runtime_state(self):
        self._multiclip_files = []
        self._multiclip_boundaries = []
        self._accumulated_vad = []
        self._reuse_existing_multiclip_subtitles = False

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
        self._is_auto_pipeline = False
        self._auto_export_subtitle_video = False
        self._auto_audio_tune_per_file = True
        if hasattr(self, "_clear_runtime_quality_override"):
            self._clear_runtime_quality_override()
        self._current_project_path = None
        self._project_boundary_times = []
        self._clear_multiclip_runtime_state()
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

        if getattr(self, "_queue_mode_starting", False):
            return
        self._queue_mode_starting = True

        try:
            self._is_auto_pipeline = True
            self._is_queue_mode = True
            self._auto_audio_tune_per_file = True
            self._current_project_path = None
            self._project_boundary_times = []
            self._clear_multiclip_runtime_state()
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
        self._is_auto_pipeline = False
        self._auto_export_subtitle_video = False
        self._auto_audio_tune_per_file = True
        if hasattr(self, "_clear_runtime_quality_override"):
            self._clear_runtime_quality_override()
        self._current_project_path = None
        self._project_boundary_times = []
        self._clear_multiclip_runtime_state()
        from ui.dialogs.folder_dialog import FolderDialog

        dlg = FolderDialog(folder, self)
        if dlg.exec() and getattr(dlg, "saved_only", False):
            return
        if dlg.result() and dlg.selected_files:
            self._auto_export_subtitle_video = bool(getattr(dlg, "export_subtitle_video", False))
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
        self._is_auto_pipeline = False
        self._auto_export_subtitle_video = False
        self._auto_audio_tune_per_file = True
        if hasattr(self, "_clear_runtime_quality_override"):
            self._clear_runtime_quality_override()
        self._current_project_path = None
        self._project_boundary_times = []
        self._clear_multiclip_runtime_state()
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

        dlg = MultiClipEditor(files, self, show_multiclip=show_multiclip)
        if dlg.exec():
            self._multiclip_files = list(dlg.sorted_files)
            if self.backend:
                self.backend.start_multiclip_pipeline(
                    dlg.sorted_files, folder=folder
                )

    def _clear_cache(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("캐쉬 삭제")
        msg.setText("output 폴더 내의 임시 파일들을 모두 삭제하시겠습니까?")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.setStyleSheet("""
            QMessageBox { background-color: #1a1a1a; color: #FFFFFF; }
            QPushButton { background-color: #333333; color: #FFFFFF; border: 2px solid #FFFFFF; padding: 6px 16px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #555555; }
        """)
        if msg.exec() == QMessageBox.StandardButton.Yes:
            import shutil

            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "output",
            )
            try:
                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                    os.makedirs(output_dir, exist_ok=True)
                from core.auto_tracker import TRACKER_FILE

                if os.path.exists(TRACKER_FILE):
                    os.remove(TRACKER_FILE)
                if hasattr(self, "_cloud_sync_manager"):
                    mgr = self._cloud_sync_manager
                    mgr._size_cache.clear()
                    mgr._in_flight.clear()
                QMessageBox.information(self, "완료", "캐쉬 삭제 완료")
                self._restore_current_work_mode()
            except Exception as e:
                QMessageBox.warning(self, "오류", f"삭제 중 오류: {e}")

    def _quick_exit(self):
        self._backup_before_quick_exit()
        if self.backend:
            try:
                self.backend.stop(log_context="앱 종료")
            except TypeError:
                self.backend.stop()
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

    def _backup_before_quick_exit(self):
        import datetime
        import shutil

        editor = getattr(self, "_editor_widget", None)
        if editor is not None:
            try:
                if hasattr(editor, "_on_save"):
                    editor._on_save(skip_auto_next=True)
            except Exception as exc:
                try:
                    from core.runtime.logger import get_logger
                    get_logger().log(f"⚠️ 종료 전 자막 저장 실패: {exc}")
                except Exception:
                    pass

        project_path = str(getattr(self, "_current_project_path", "") or "")
        if project_path and os.path.exists(project_path):
            try:
                backup_dir = os.path.join(os.path.dirname(project_path), "프로젝트백업")
                os.makedirs(backup_dir, exist_ok=True)
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                base, ext = os.path.splitext(os.path.basename(project_path))
                shutil.copy2(project_path, os.path.join(backup_dir, f"{base}_{stamp}{ext or '.json'}"))
            except Exception as exc:
                try:
                    from core.runtime.logger import get_logger
                    get_logger().log(f"⚠️ 종료 전 프로젝트 백업 실패: {exc}")
                except Exception:
                    pass
