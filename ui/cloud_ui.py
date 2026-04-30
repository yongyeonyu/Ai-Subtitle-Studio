# Version: 03.01.00
# Phase: PHASE1-B
"""
ui/cloud_ui.py
iCloud / NAS automatic processing UI helpers.
"""

import os
from PyQt6.QtWidgets import QMessageBox

from logger import get_logger
from core.path_manager import (
    get_icloud_path, get_nas_path, ensure_nas_mounted, get_local_path,
    get_nas_excluded_folders, set_nas_excluded_folders
)
from core.settings import load_settings
from ui.dialogs.folder_dialog import FolderDialog


class CloudUIMixin:
    """iCloud / NAS 자동 처리"""

    def _on_files_detected(self, files_list):
        if not files_list:
            return
        parent = os.path.basename(os.path.dirname(files_list[0])) if files_list else ""
        get_logger().log(f"🚀 자동 처리 큐 진입: {parent} / {len(files_list)}개 파일")
        self._auto_processing_active = True
        try:
            self._tick_home_watchdog_labels()
        except Exception:
            pass
        self._sig_auto_start_pipeline.emit(files_list)

    def _do_auto_start_pipeline(self, files_list):
        if not files_list:
            return
        settings = load_settings()
        mode = settings.get("auto_start_mode", "quality")
        folder = os.path.dirname(files_list[0]) if files_list else None
        self._is_auto_pipeline = True
        if mode == "fast" and hasattr(self, "_start_batch"):
            self._start_batch(files_list, folder=folder)
        elif self.backend:
            self.backend.start_pipeline(files_list, folder=folder, is_auto_start=True)
            if self._editor_widget and hasattr(self._editor_widget, 'update_status'):
                self._editor_widget.update_status("🚀 AI 엔진이 시작되었습니다. (자동 감지)")

    def _is_app_busy(self):
        if getattr(self, "_auto_processing_active", False):
            return True
        if self._editor_widget is not None:
            return True
        if self.backend and getattr(self.backend, '_active', False):
            return True
        if getattr(self, "backend_fast", None) and getattr(self.backend_fast, '_active', False):
            return True
        return False

    def mark_cloud_file_done(self, filepath):
        if hasattr(self, '_cloud_sync_manager'):
            self._cloud_sync_manager.mark_done(filepath)
        if hasattr(self, '_nas_sync_manager'):
            self._nas_sync_manager.mark_done(filepath)
        managers = [
            getattr(self, "_cloud_sync_manager", None),
            getattr(self, "_nas_sync_manager", None),
        ]
        still_running = False
        for mgr in managers:
            try:
                still_running = still_running or bool(getattr(mgr, "_in_flight", None))
                still_running = still_running or bool(getattr(mgr, "_folder_jobs", None))
            except Exception:
                pass
        if not still_running:
            self._auto_processing_active = False
            try:
                self._tick_home_watchdog_labels()
            except Exception:
                pass

    def start_icloud_sync(self):
        self._is_auto_pipeline = True
        self._auto_processing_active = True
        self.backend.start_pipeline([], is_icloud=True)

    def _get_icloud_files(self):
        path = get_icloud_path()
        if not path or not os.path.exists(path):
            path = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT")
            if not os.path.exists(path):
                return [], "경로 없음", ""
        v_exts = {'.mov', '.mp4', '.m4v', '.MOV', '.MP4', '.M4V', '.lrf', '.LRF'}
        a_exts = {'.wav', '.m4a', '.mp3', '.aac', '.m2a'}
        v_count = a_count = comp_v_count = comp_a_count = 0
        files = []
        try:
            from core.auto_tracker import AutoTracker
            tracker = AutoTracker()
        except ImportError:
            tracker = None
        try:
            for f in os.listdir(path):
                if f.startswith('.') or "_자막소스.mov" in f:
                    continue
                ext = os.path.splitext(f)[1].lower()
                file_path = os.path.join(path, f)
                status = tracker.get_status(file_path) if tracker else None
                if status == "완료":
                    if ext in v_exts:
                        comp_v_count += 1
                    elif ext in a_exts:
                        comp_a_count += 1
                    continue
                if ext in v_exts:
                    v_count += 1
                    files.append((f, file_path))
                elif ext in a_exts:
                    a_count += 1
                    files.append((f, file_path))
                elif ext == '.srt':
                    files.append((f, file_path))
            return sorted(files), f"대기 : 영상 {v_count:02d}개 / 음성 {a_count:02d}개", f"✅ 작업완료 : 영상 {comp_v_count:02d}개 / 음성 {comp_a_count:02d}개"
        except Exception:
            return [], "오류", ""

    def _get_nas_folders(self):
        nas_path = get_nas_path()
        if not nas_path:
            return [], "경로 없음", ""
        local_path = get_local_path(nas_path)
        if not os.path.exists(local_path):
            return [], "경로 없음", ""
        folders = []
        pending = completed = excluded_count = 0
        excluded = {os.path.normpath(p) for p in get_nas_excluded_folders()}
        try:
            from core.auto_tracker import AutoTracker
            tracker = AutoTracker()
        except ImportError:
            tracker = None
        try:
            for current, dirs, files in os.walk(local_path):
                dirs[:] = sorted([d for d in dirs if not d.startswith('.')])
                norm = os.path.normpath(current)
                if any(norm == ex or norm.startswith(ex + os.sep) for ex in excluded):
                    excluded_count += 1
                    dirs[:] = []
                    continue
                if current == local_path:
                    continue
                has_media = any((not f.startswith('.')) and os.path.splitext(f)[1].lower() in {'.mov', '.mp4', '.m4a', '.wav', '.mp3', '.aac', '.m2a'} for f in files)
                if has_media:
                    status = tracker.get_status(current) if tracker else None
                    if status == "완료":
                        completed += 1
                    else:
                        pending += 1
                folders.append((os.path.relpath(current, local_path), current))
            return sorted(folders, key=lambda x: x[0].lower()), f"대기 : 폴더 {pending:02d}개", f"✅ 작업완료 : 폴더 {completed:02d}개 / 제외 {excluded_count:02d}개"
        except Exception:
            return [], "오류", ""

    def _open_nas_root(self):
        nas_url = get_nas_path()
        if not nas_url:
            QMessageBox.warning(self, "오류", "NAS 경로가 설정되지 않았습니다")
            return
        if not ensure_nas_mounted(nas_url):
            QMessageBox.warning(self, "오류", "NAS 마운트에 실패했습니다.")
            return
        local_path = get_local_path(nas_url)
        self._is_auto_pipeline = False
        dlg = FolderDialog(local_path, self, excluded_folders=get_nas_excluded_folders())
        if dlg.exec():
            set_nas_excluded_folders(sorted(dlg.excluded_folders))
            self._add_recent_folder(local_path)
            if getattr(dlg, "saved_only", False):
                if hasattr(self, "_restore_current_work_mode"):
                    self._restore_current_work_mode()
                else:
                    self.show_home()
                return
            if dlg.selected_files:
                if len(dlg.selected_files) == 1 and self.backend:
                    self.backend.start_pipeline(dlg.selected_files, folder=local_path)
                elif len(dlg.selected_files) > 1:
                    self._show_multiclip_then_batch(dlg.selected_files, folder=local_path, show_multiclip=False)
            elif hasattr(self, "_restore_current_work_mode"):
                self._restore_current_work_mode()
            else:
                self.show_home()
