# Version: 02.01.00
# Phase: PHASE1-B
"""
ui/project_ui.py
프로젝트 만들기 / 열기 / 저장 / 영상 추가
- main_window.py에서 분리
"""

import os
from PyQt6.QtWidgets import QFileDialog, QDialog, QMessageBox

from logger import get_logger
from core.project_manager import (
    create_project, save_project, load_project,
    add_media_to_project, get_boundary_times, PROJECTS_DIR
)
from core.path_manager import get_last_folder
from ui.order_dialog import OrderDialog


class ProjectUIMixin:
    """프로젝트 만들기 / 열기 / 저장 / 영상 추가"""

    def _create_project(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "프로젝트 만들기", "프로젝트 이름:")
        if not ok or not name.strip():
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self, "영상/음성 파일 선택",
            get_last_folder() or os.path.expanduser("~"),
            "영상/음성 파일 (*.mp4 *.mov *.MOV *.MP4 *.m4v *.lrf *.wav *.m4a *.m2a *.mp3 *.aac)"
        )
        if not paths:
            return

        if len(paths) > 1:
            dlg = OrderDialog(paths, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            paths = dlg.ordered_files

        if not paths:
            return

        filepath = create_project(
            name.strip(),
            media_paths=paths,
            user_settings=self._load_local_settings()
        )
        self._current_project_path = filepath
        self._is_auto_pipeline = False

        project_data = load_project(filepath)
        if project_data:
            self._project_boundary_times = get_boundary_times(project_data)

        get_logger().log(f"📝 프로젝트 생성: {name.strip()} ({len(paths)}개 미디어)")

        if self.backend:
            self.backend.start_pipeline(paths)

    def _open_project(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "프로젝트 열기", PROJECTS_DIR, "Project Files (*.json)"
        )
        if not filepath:
            return

        project = load_project(filepath)
        if not project:
            QMessageBox.warning(self, "오류", "프로젝트 파일을 읽을 수 없습니다.")
            return

        self._current_project_path = filepath
        self._is_auto_pipeline = False
        self._project_boundary_times = get_boundary_times(project)

        saved = project.get("user_settings", {})
        if saved:
            self._save_local_settings(saved)
            get_logger().log("⚙️ 프로젝트 설정 복원 완료")

        media = [
            m["path"] for m in sorted(
                project.get("media", []),
                key=lambda x: x.get("order", 0)
            ) if os.path.exists(m["path"])
        ]

        srt_path = (
            project.get("subtitle", {}).get("path", "")
            or project.get("subtitles", {}).get("srt_path", "")
        )

        get_logger().log(
            f"📦 프로젝트 로드: {project.get('project_name', '')} (미디어 {len(media)}개)"
        )

        if srt_path and os.path.exists(srt_path):
            self._open_srt_in_editor(srt_path)
        elif media and self.backend:
            self.backend.start_pipeline(media)
        else:
            QMessageBox.warning(self, "오류", "프로젝트에 유효한 미디어 파일이 없습니다.")

    def _save_current_project(self, segments=None):
        fp = getattr(self, '_current_project_path', None)
        if not fp:
            return
        save_project(fp, segments=segments, user_settings=self._load_local_settings())
        get_logger().log("💾 프로젝트 저장 완료")

    def _add_video_to_project(self):
        fp = getattr(self, '_current_project_path', None)
        if not fp:
            QMessageBox.warning(self, "오류", "열려있는 프로젝트가 없습니다.")
            return

        project = load_project(fp)
        if not project:
            return

        new_paths, _ = QFileDialog.getOpenFileNames(
            self, "추가할 영상/음성 선택",
            get_last_folder() or os.path.expanduser("~"),
            "Media Files (*.mp4 *.mov *.MOV *.MP4 *.wav *.m4a *.m2a *.mp3 *.aac *.lrf)"
        )
        if not new_paths:
            return

        existing = [
            m["path"] for m in sorted(
                project.get("media", []),
                key=lambda x: x.get("order", 0)
            )
        ]

        dlg = OrderDialog(
            existing + new_paths, self,
            title="영상 순서 편집 (기존 + 추가)"
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if not dlg.ordered_files:
            return

        add_media_to_project(fp, new_paths)

        new_only = [p for p in dlg.ordered_files if p not in set(existing)]
        if new_only and self.backend:
            get_logger().log(f"➕ 프로젝트에 {len(new_only)}개 영상 추가")
            self.backend.start_pipeline(new_only)
        else:
            self.show_home()