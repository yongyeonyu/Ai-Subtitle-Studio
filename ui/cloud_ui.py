# Version: 02.02.01
# Phase: PHASE1-B
"""
ui/cloud_ui.py
iCloud / NAS 자동처리 관련 로직
- main_window.py에서 분리
"""

import os
from PyQt6.QtWidgets import QMessageBox

from logger import get_logger
from core.path_manager import (
    get_icloud_path, get_nas_path, ensure_nas_mounted
)
from ui.dialogs.folder_dialog import FolderDialog


class CloudUIMixin:
    """iCloud / NAS 자동 처리"""

    # ── iCloud ──
    def _on_files_detected(self, files_list):
        get_logger().log(f"🚀 자동 처리 큐 진입: {len(files_list)}개 파일")
        self._sig_auto_start_pipeline.emit(files_list)

    def _do_auto_start_pipeline(self, files_list):
        if self.backend:
            self._is_auto_pipeline = True
            self.backend.start_pipeline(files_list, is_auto_start=True)
            if self._editor_widget and hasattr(self._editor_widget, 'update_status'):
                self._editor_widget.update_status("🚀 AI 엔진이 시작되었습니다. (자동 감지)")

    def _is_app_busy(self):
        if self._editor_widget is not None:
            return True
        if self.backend and getattr(self.backend, '_active', False):
            return True
        return False

    def mark_cloud_file_done(self, filepath):
        if hasattr(self, '_cloud_sync_manager'):
            self._cloud_sync_manager.mark_done(filepath)

    def start_icloud_sync(self):
        self._is_auto_pipeline = True
        self.backend.start_pipeline([], is_icloud=True)

    def _get_icloud_files(self):
        path = get_icloud_path()
        if not path or not os.path.exists(path):
            path = os.path.expanduser(
                "~/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT"
            )
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
                    if ext in v_exts: comp_v_count += 1
                    elif ext in a_exts: comp_a_count += 1
                    continue
                if ext in v_exts:
                    v_count += 1; files.append((f, file_path))
                elif ext in a_exts:
                    a_count += 1; files.append((f, file_path))
                elif ext == '.srt':
                    files.append((f, file_path))

            return (
                sorted(files),
                f"대기 : 영상 {v_count:02d}개 / 음성 {a_count:02d}개",
                f"✅ 작업완료 : 영상 {comp_v_count:02d}개 / 음성 {comp_a_count:02d}개"
            )
        except Exception:
            return [], "오류", ""

    # ── NAS ──
    def _get_nas_folders(self):
        nas_path = get_nas_path()
        if not nas_path:
            return []
        local_path = nas_path
        if nas_path.startswith("smb://"):
            parts = nas_path.replace("smb://", "").split("/")
            local_path = f"/Volumes/{parts[1]}" if len(parts) > 1 else "/Volumes/video"
        if not os.path.exists(local_path):
            return []
        try:
            return sorted([
                (f, os.path.join(local_path, f))
                for f in os.listdir(local_path)
                if not f.startswith('.') and os.path.isdir(os.path.join(local_path, f))
            ])
        except Exception:
            return []

    def _open_nas_root(self):
        nas_url = get_nas_path()
        if not nas_url:
            QMessageBox.warning(self, "오류", "NAS 경로가 설정되지 않았습니다")
            return
        if not ensure_nas_mounted(nas_url):
            QMessageBox.warning(self, "오류", "NAS 마운트에 실패했습니다.")
            return
        local_path = nas_url
        if nas_url.startswith("smb://"):
            parts = nas_url.replace("smb://", "").split("/")
            local_path = f"/Volumes/{parts[1]}" if len(parts) > 1 else "/Volumes/video"
        self._is_auto_pipeline = False
        dlg = FolderDialog(local_path, self)
        if dlg.exec() and dlg.selected_files:
            self._add_recent_folder(local_path)
            if len(dlg.selected_files) == 1 and self.backend:
                self.backend.start_pipeline(dlg.selected_files, folder=local_path)
            elif len(dlg.selected_files) > 1:
                self._show_multiclip_then_batch(dlg.selected_files, folder=local_path, show_multiclip=False)