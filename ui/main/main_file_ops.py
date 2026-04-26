# Version: 02.03.03
# Phase: PHASE1-B
"""
ui/main/main_file_ops.py
FileOpsMixin — 파일/폴더 선택 · 배치 시작 · 멀티클립 진입 · 캐시 삭제 · 종료
"""
import os
import sys

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QApplication
from PyQt6.QtCore import QTimer

from core.path_manager import (
    get_srt_path, get_last_folder, set_last_folder,
    ensure_nas_mounted, get_recent_folders, add_recent_folder,
)
from core.settings import load_settings, save_settings


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
        self._current_project_path = None
        self._project_boundary_times = []
        self._multiclip_boundaries = []
        self._accumulated_vad = []
        srt = [p for p in paths if p.lower().endswith(".srt")]
        vid = [p for p in paths if not p.lower().endswith(".srt")]
        if vid and len(vid) > 1:
            self._show_multiclip_then_batch(vid, show_multiclip=True)
        elif vid and len(vid) == 1 and self.backend:
            self.backend.start_pipeline(vid)
        elif srt:
            self._open_srt_in_editor(srt[0])

    def _start_batch(self, files, folder=None):
        """멀티 파일 → backend_fast 배치 모드 (중복 호출 방지)"""
        if not files:
            return

        if getattr(self, "_batch_starting", False):
            return
        self._batch_starting = True

        try:
            from core.backend_fast import CoreBackendFast

            self._is_auto_pipeline = True
            if not getattr(self, "backend_fast", None):
                self.backend_fast = CoreBackendFast(self)

            if getattr(self.backend_fast, "_active", False):
                return

            self.backend_fast.start_batch(files, folder=folder)
        finally:
            QTimer.singleShot(500, lambda: setattr(self, "_batch_starting", False))

    def select_folder(self):
        folder = self._safe_open_directory(
            "폴더 선택", get_last_folder() or os.path.expanduser("~")
        )
        if not folder or not ensure_nas_mounted(folder):
            return
        set_last_folder(folder)
        self._add_recent_folder(folder)
        self._is_auto_pipeline = False
        self._current_project_path = None
        self._project_boundary_times = []
        from ui.dialogs.folder_dialog import FolderDialog

        dlg = FolderDialog(folder, self)
        if dlg.exec() and getattr(dlg, "saved_only", False):
            return
        if dlg.result() and dlg.selected_files:
            if len(dlg.selected_files) == 1 and self.backend:
                self.backend.start_pipeline(dlg.selected_files, folder=folder)
            elif len(dlg.selected_files) > 1:
                self._show_multiclip_then_batch(
                    dlg.selected_files, folder=folder, show_multiclip=False
                )

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
        self._current_project_path = None
        self._project_boundary_times = []
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
            self._open_srt_in_editor(srt[0])
        elif vid and len(vid) == 1 and self.backend:
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
            if dlg.selected_mode == "fast":
                self._start_batch(dlg.sorted_files, folder=folder)
            elif dlg.selected_mode == "quality":
                if self.backend:
                    self.backend.start_pipeline(
                        dlg.sorted_files, folder=folder, is_auto_start=True
                    )
            elif dlg.selected_mode == "multiclip":
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
                self.show_home()
            except Exception as e:
                QMessageBox.warning(self, "오류", f"삭제 중 오류: {e}")

    def _quick_exit(self):
        if self.backend:
            self.backend.stop()
        QApplication.quit()
