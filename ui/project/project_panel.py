# Version: 03.09.23
# Phase: PHASE2
"""
ui/project/project_panel.py
Project UI mixin
"""
import os

from PyQt6.QtWidgets import QFileDialog, QDialog, QMessageBox, QInputDialog

from logger import get_logger
from core.path_manager import get_last_folder
from core.project.project_manager import (
    PROJECTS_DIR,
    add_media_to_project,
    create_project,
    extract_model_settings,
    get_boundary_times,
    load_project,
    merge_project_model_settings,
    save_project,
)
from core.project.project_context import (
    project_clip_boundaries,
    project_voice_activity_segments,
    project_active_work_mode,
    project_media_files,
    project_roughcut_state,
    project_segments_to_editor,
    project_stt_preview_segments,
)
from core.work_mode import EDITOR_MODE, normalize_work_mode
from ui.project.clip_order_dialog import OrderDialog


PROJECT_MEDIA_FILTER = (
    "Media Files (*.mp4 *.mov *.MOV *.MP4 *.m4v *.lrf *.wav *.m4a *.m2a *.mp3 *.aac)"
)
PROJECT_FILE_FILTER = "Project Files (*.json)"


class ProjectUIMixin:
    def _load_local_settings(self) -> dict:
        try:
            from core.project.data_manager import load_settings
            return dict(load_settings() or {})
        except Exception:
            try:
                from core.settings import load_settings
                return dict(load_settings() or {})
            except Exception:
                return {}

    def _save_local_settings(self, settings: dict) -> None:
        if not isinstance(settings, dict):
            return
        try:
            from core.project.data_manager import save_settings
            save_settings(settings)
            return
        except Exception:
            pass
        try:
            from core.settings import save_settings
            save_settings(settings)
        except Exception:
            pass

    def _sorted_project_media(self, project: dict) -> list:
        media_files = project_media_files(project)
        if media_files:
            return [path for path in media_files if os.path.exists(path)]
        return [
            item["path"]
            for item in sorted(project.get("media", []), key=lambda x: x.get("order", 0))
            if os.path.exists(item["path"])
        ]

    def _open_project_segments_in_editor(self, filepath: str, project: dict, media: list[str], segments: list[dict]):
        if not media:
            return False

        boundaries = project_clip_boundaries(project)
        if len(media) > 1:
            self._multiclip_files = list(media)
            self._multiclip_boundaries = boundaries
            self._project_boundary_times = [b["end"] for b in boundaries[:-1]] if len(boundaries) > 1 else []
        else:
            self._multiclip_files = []
            self._multiclip_boundaries = []
            self._project_boundary_times = []

        self._current_project_path = filepath
        self._is_auto_pipeline = False
        self._on_save_cb = None
        self._on_start_cb = None
        self._on_prev_cb = None
        self._on_exit_cb = None
        self._init_editor(media[0], is_batch=False)

        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return False
        try:
            if hasattr(editor, "_reload_segments_from_list"):
                editor._reload_segments_from_list(segments)
            else:
                editor.append_segments(segments)
            if len(media) > 1 and hasattr(editor, "_apply_multiclip_state_from_owner"):
                editor._apply_multiclip_state_from_owner()
            if hasattr(editor, "_set_process_completed"):
                editor._set_process_completed()
            stt_preview = project_stt_preview_segments(project)
            if stt_preview:
                editor._live_stt_preview_segments = stt_preview
            if hasattr(editor, "_redraw_timeline"):
                editor._redraw_timeline()
            voice_activity = project_voice_activity_segments(project)
            if voice_activity and hasattr(editor, "set_voice_activity_segments"):
                editor.set_voice_activity_segments(voice_activity)
        except Exception as e:
            get_logger().log(f"⚠️ 프로젝트 자막 복원 실패: {e}")
        return True

    def _create_project(self):
        name, ok = QInputDialog.getText(self, "프로젝트 만들기", "프로젝트 이름:")
        if not ok or not name.strip():
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "영상/음성 파일 선택",
            get_last_folder() or os.path.expanduser("~"),
            PROJECT_MEDIA_FILTER,
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
            name=name.strip(),
            media_paths=paths,
            user_settings=self._load_local_settings(),
        )

        self._current_project_path = filepath
        self._is_auto_pipeline = False

        project_data = load_project(filepath)
        if project_data:
            self._project_boundary_times = get_boundary_times(project_data)

        get_logger().log(f"📁 프로젝트 생성: {name.strip()} ({len(paths)}개 미디어)")

        if self.backend:
            self.backend.start_pipeline(paths)

    def _open_project(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "프로젝트 열기",
            PROJECTS_DIR,
            PROJECT_FILE_FILTER,
        )
        if not filepath:
            return

        project = load_project(filepath)
        if not project:
            QMessageBox.warning(self, "오류", "프로젝트 파일을 열 수 없습니다.")
            return

        self._current_project_path = filepath
        self._is_auto_pipeline = False
        self._project_boundary_times = get_boundary_times(project)

        model_settings = extract_model_settings(project)
        saved_settings = merge_project_model_settings(
            self._load_local_settings(),
            project,
        )
        if model_settings:
            self._save_local_settings(saved_settings)
            if hasattr(self, "_refresh_sidebar_engine_info"):
                self._refresh_sidebar_engine_info(settings=saved_settings)
            get_logger().log("🔁 프로젝트 AI 모델 설정 복원 완료")

        media = self._sorted_project_media(project)
        project_segments = project_segments_to_editor(project)

        srt_path = (
            project.get("subtitle", {}).get("path", "")
            or project.get("subtitles", {}).get("srt_path", "")
        )

        get_logger().log(
            f"📂 프로젝트 로드: {project.get('project_name', '')} (미디어 {len(media)}개)"
        )

        if media:
            if self._open_project_segments_in_editor(filepath, project, media, project_segments):
                if project_active_work_mode(project) == "roughcut" and project_roughcut_state(project):
                    try:
                        self._open_roughcut_helper()
                    except Exception as e:
                        get_logger().log(f"⚠️ 러프컷 화면 복원 실패: {e}")
                return

        if srt_path and os.path.exists(srt_path):
            self._open_srt_in_editor(srt_path)
            return

        if media and self.backend:
            self.backend.start_pipeline(media)
            return

        QMessageBox.warning(self, "오류", "프로젝트에 유효한 미디어 파일이 없습니다.")

    def _save_current_project(self, segments=None):
        filepath = getattr(self, "_current_project_path", None)
        if not filepath:
            return

        editor = getattr(self, "_editor_widget", None)
        stt_preview_segments = []
        if editor is not None:
            stt_preview_segments = list(getattr(editor, "_live_stt_preview_segments", []) or [])

        save_project(
            filepath,
            segments=segments,
            user_settings=self._load_local_settings(),
            active_work_mode=normalize_work_mode(getattr(self, "_current_work_mode", EDITOR_MODE)),
            stt_preview_segments=stt_preview_segments,
        )
        get_logger().log("💾 프로젝트 저장 완료")

    def _add_video_to_project(self):
        filepath = getattr(self, "_current_project_path", None)
        if not filepath:
            QMessageBox.warning(self, "오류", "열려있는 프로젝트가 없습니다.")
            return

        project = load_project(filepath)
        if not project:
            return

        new_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "추가할 영상/음성 선택",
            get_last_folder() or os.path.expanduser("~"),
            PROJECT_MEDIA_FILTER,
        )
        if not new_paths:
            return

        existing = [
            item["path"]
            for item in sorted(project.get("media", []), key=lambda x: x.get("order", 0))
        ]

        dlg = OrderDialog(
            existing + new_paths,
            self,
            title="영상 순서 편집 (기존 + 추가)",
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if not dlg.ordered_files:
            return

        add_media_to_project(filepath, new_paths)

        editor = getattr(self, "_editor_widget", None)
        if editor is not None and hasattr(editor, "_remap_segments_for_multiclip_files"):
            ordered = list(dlg.ordered_files)
            remapped, new_bounds = editor._remap_segments_for_multiclip_files(ordered)
            self._multiclip_files = ordered
            self._multiclip_boundaries = new_bounds
            self._project_boundary_times = [b["end"] for b in new_bounds[:-1]] if len(new_bounds) > 1 else []
            editor._reload_segments_from_list(remapped)
            editor._apply_multiclip_state_from_owner()
            try:
                editor._auto_save_project(editor._get_current_segments())
            except Exception:
                pass
            get_logger().log(f"➕ 단일클립 프로젝트를 멀티클립으로 전환: {len(ordered)}개")
            return

        new_only = [path for path in dlg.ordered_files if path not in set(existing)]
        if new_only and self.backend:
            get_logger().log(f"➕ 프로젝트에 {len(new_only)}개 영상 추가")
            self.backend.start_pipeline(new_only)
        else:
            self.show_home()
