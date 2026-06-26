# Version: 03.09.23
# Phase: PHASE2
"""
ui/project/project_panel.py
Project UI mixin
"""
import os

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFileDialog, QDialog, QMessageBox, QInputDialog

from core.runtime.logger import get_logger
from core.path_manager import get_last_folder
from core.project.project_manager import (
    PROJECT_FILE_FILTER,
    PROJECTS_DIR,
    add_media_to_project,
    create_project,
    load_project,
    project_stitched_cut_boundaries,
    restore_project_model_settings,
    save_project,
)
from core.project.project_assets import resolve_project_asset_path
from core.project.project_context import (
    project_cut_boundary_provisional_segments,
    project_active_work_mode,
    project_roughcut_state,
    project_segments_to_editor,
)
from core.project.project_runtime_capture import collect_editor_project_aux_state
from core.work_mode import EDITOR_MODE, normalize_work_mode
from ui.editor.editor_project_open_native import (
    open_project_segments_in_editor as native_open_project_segments_in_editor,
)
from ui.project.clip_order_dialog import OrderDialog
from ui.project.project_session_runtime import (
    attach_project_session,
    load_local_project_settings,
    save_local_project_settings,
    set_runtime_multiclip_state,
    sorted_project_media_paths,
)


PROJECT_MEDIA_FILTER = (
    "Media Files (*.mp4 *.mov *.MOV *.MP4 *.m4v *.lrf *.wav *.m4a *.m2a *.mp3 *.aac)"
)


def _safe_open_file_names_for_owner(owner, title: str, folder: str, file_filter: str):
    opener = getattr(owner, "_safe_open_file_names", None)
    if callable(opener):
        return opener(title, folder, file_filter)
    return QFileDialog.getOpenFileNames(owner, title, folder, file_filter)


def _safe_open_file_name_for_owner(owner, title: str, folder: str, file_filter: str):
    opener = getattr(owner, "_safe_open_file_name", None)
    if callable(opener):
        return opener(title, folder, file_filter)
    return QFileDialog.getOpenFileName(owner, title, folder, file_filter)


def _is_placeholder_middle_row(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    title = str(row.get("title", row.get("name", "")) or "")
    tags = row.get("tags", []) or []
    if isinstance(tags, str):
        tags = [tags]
    return bool(
        row.get("is_topicless_placeholder")
        or row.get("is_cut_boundary_placeholder")
        or row.get("source") == "cut_boundary"
        or title == "주제없음"
        or "컷경계" in tags
    )


def _rows_are_placeholder_only(rows) -> bool:
    rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
    return bool(rows) and all(_is_placeholder_middle_row(row) for row in rows)


class ProjectUIMixin:
    def _open_project_file(self, filepath: str) -> bool:
        filepath = str(filepath or "").strip()
        if not filepath:
            return False

        pause_lora = getattr(self, "_pause_personalization_for_foreground_activity", None)
        if callable(pause_lora):
            pause_lora("project_open")

        project = load_project(filepath, hydrate_text_assets=False)
        if not project:
            QMessageBox.warning(self, "오류", "프로젝트 파일을 열 수 없습니다.")
            return False

        attach_project_session(self, filepath, project, auto_pipeline=False, clear_multiclip=True)

        model_settings, saved_settings = restore_project_model_settings(
            self._load_local_settings(),
            project,
        )
        if model_settings:
            self._save_local_settings(saved_settings)
            if hasattr(self, "_refresh_sidebar_engine_info"):
                self._refresh_sidebar_engine_info(settings=saved_settings)
            get_logger().log("🔁 프로젝트 AI 모델 설정 복원 완료")

        media = self._sorted_project_media(project)
        project_segments = project_segments_to_editor(project, include_analysis_candidates=False)

        srt_path = (
            project.get("subtitle", {}).get("path", "")
            or project.get("subtitles", {}).get("srt_path", "")
        )
        source_srt_path = ""
        if srt_path:
            try:
                source_srt_path = resolve_project_asset_path(project, srt_path)
            except Exception:
                source_srt_path = os.path.abspath(str(srt_path or ""))

        get_logger().log(
            f"📂 프로젝트 로드: {project.get('project_name', '')} (미디어 {len(media)}개)"
        )

        if media:
            open_kwargs = {}
            if source_srt_path and os.path.exists(source_srt_path):
                open_kwargs["source_srt_path"] = source_srt_path
            if self._open_project_segments_in_editor(filepath, project, media, project_segments, **open_kwargs):
                if project_active_work_mode(project) == "roughcut" and project_roughcut_state(project):
                    def _open_roughcut_deferred():
                        try:
                            self._open_roughcut_helper()
                        except Exception as e:
                            get_logger().log(f"⚠️ 러프컷 화면 복원 실패: {e}")

                    QTimer.singleShot(180, _open_roughcut_deferred)
                return True

        if source_srt_path and os.path.exists(source_srt_path):
            self._open_srt_in_editor(source_srt_path)
            return True

        if media and self.backend:
            self.backend.start_pipeline(media)
            return True

        QMessageBox.warning(self, "오류", "프로젝트에 유효한 미디어 파일이 없습니다.")
        return False

    def _project_cut_boundary_placeholder_rows(self, project: dict) -> list[dict]:
        analysis = project.get("analysis", {}) or {}
        rows = []
        for key in (
            "cut_boundary_topicless_middle_segments",
            "topicless_middle_segments",
            "roughcut_topicless_segments",
            "middle_segments",
        ):
            raw = analysis.get(key)
            if isinstance(raw, list) and raw:
                rows = raw
                break
        if not rows:
            raw = project.get("middle_segments")
            if isinstance(raw, list):
                rows = raw
        return [
            dict(row)
            for row in list(rows or [])
            if isinstance(row, dict) and _is_placeholder_middle_row(row)
        ]

    def _project_cut_boundary_resume_needed(self, project: dict) -> bool:
        analysis = project.get("analysis", {}) or {}
        cut_rows = analysis.get("cut_boundaries")
        if not isinstance(cut_rows, list):
            cut_rows = []
        provisional_rows = project_cut_boundary_provisional_segments(project)
        if provisional_rows:
            return True
        if cut_rows:
            return False
        middle_rows = analysis.get("middle_segments")
        if isinstance(middle_rows, list) and middle_rows and not _rows_are_placeholder_only(middle_rows):
            return False
        if bool(analysis.get("cut_boundary_topicless_finalized")):
            return False

        has_cut_state = any(
            key in analysis
            for key in (
                "cut_boundary_prescan_done",
                "cut_boundary_cache_path",
                "cut_boundary_cache_type",
                "cut_boundary_resume_required",
                "cut_boundary_provisional_boundaries",
                "cut_boundary_topicless_middle_segments",
                "topicless_middle_segments",
                "roughcut_topicless_segments",
                "middle_segments",
            )
        )
        if not has_cut_state:
            return False
        if bool(analysis.get("cut_boundary_resume_required")):
            return True
        if bool(analysis.get("cut_boundary_prescan_done")):
            return True
        placeholders = self._project_cut_boundary_placeholder_rows(project)
        return bool(placeholders)

    def _resume_cut_boundary_prescan_for_open_project(self, filepath: str, project: dict, media: list[str]) -> bool:
        """Restart background cut-boundary verification when a saved project is stuck.

        A project can be left with `cut_boundary_prescan_done=True` but zero
        confirmed rows if an older empty cache was reused. Treat that as
        unfinished so the pioneer/follower workers run in the background.
        """
        media = [path for path in list(media or []) if path and os.path.exists(path)]
        if not filepath or not os.path.exists(filepath) or not media:
            return False

        try:
            from core.cut_boundary import cut_boundary_enabled
        except Exception:
            cut_boundary_enabled = None

        settings = dict(self._load_local_settings())
        settings.update(dict(project.get("user_settings", {}) or {}))
        try:
            enabled = cut_boundary_enabled(settings) if callable(cut_boundary_enabled) else True
        except Exception:
            enabled = True
        if not enabled:
            return False

        stitched_rows = []
        try:
            stitched_rows = list(project_stitched_cut_boundaries(project) or [])
        except Exception:
            stitched_rows = []
        if stitched_rows:
            try:
                from core.cut_boundary import sync_project_cut_boundaries
                from core.project.project_io import read_project_file, write_project_file

                saved = read_project_file(filepath)
                saved["user_settings"] = dict(settings or {})
                analysis = saved.setdefault("analysis", {})
                analysis["cut_boundaries"] = [dict(row) for row in stitched_rows]
                analysis["cut_boundary_provisional_boundaries"] = []
                for key in (
                    "cut_boundary_prescan_done",
                    "cut_boundary_cache_path",
                    "cut_boundary_cache_type",
                    "cut_boundary_resume_required",
                    "cut_boundary_resume_reason",
                ):
                    analysis.pop(key, None)
                sync_project_cut_boundaries(saved, settings=settings, provisional_boundaries=[])
                write_project_file(filepath, saved)
                get_logger().log(
                    f"🎬 [컷 경계] roughcut exact join 복원: {len(stitched_rows)}개"
                )
            except Exception as exc:
                get_logger().log(f"⚠️ roughcut exact join 컷 경계 복원 실패: {exc}")
            return False

        if not self._project_cut_boundary_resume_needed(project):
            return False

        backend = getattr(self, "backend", None)
        scan = getattr(backend, "_auto_scan_cut_boundaries_for_start", None)
        if not callable(scan):
            return False

        try:
            from core.project.project_io import read_project_file, write_project_file

            saved = read_project_file(filepath)
            saved["user_settings"] = dict(settings or {})
            analysis = saved.setdefault("analysis", {})
            if not list(analysis.get("cut_boundaries", []) or []):
                for key in (
                    "cut_boundary_prescan_done",
                    "cut_boundary_cache_path",
                    "cut_boundary_cache_type",
                    "cut_boundary_resume_required",
                    "cut_boundary_resume_reason",
                ):
                    analysis.pop(key, None)
            write_project_file(filepath, saved)
        except Exception as exc:
            get_logger().log(f"⚠️ 프로젝트 컷 경계 재확인 상태 정리 실패: {exc}")

        try:
            scan(filepath, media)
            get_logger().log("🎬 [컷 경계] 프로젝트 열기 후 백그라운드 중분류 재확인 시작")
            return True
        except Exception as exc:
            get_logger().log(f"⚠️ 프로젝트 컷 경계 백그라운드 재확인 시작 실패: {exc}")
            return False

    def _load_local_settings(self) -> dict:
        return load_local_project_settings()

    def _save_local_settings(self, settings: dict) -> None:
        save_local_project_settings(settings)

    def _sorted_project_media(self, project: dict) -> list:
        return sorted_project_media_paths(project)

    def _open_project_segments_in_editor(
        self,
        filepath: str,
        project: dict,
        media: list[str],
        segments: list[dict],
        **kwargs,
    ):
        return native_open_project_segments_in_editor(self, filepath, project, media, segments, **kwargs)

    def _create_project(self):
        pause_lora = getattr(self, "_pause_personalization_for_foreground_activity", None)
        if callable(pause_lora):
            pause_lora("project_create")
        name, ok = QInputDialog.getText(self, "프로젝트 만들기", "프로젝트 이름:")
        if not ok or not name.strip():
            return

        paths, _ = _safe_open_file_names_for_owner(
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

        project_data = load_project(filepath, hydrate_text_assets=False)
        if project_data:
            attach_project_session(self, filepath, project_data, auto_pipeline=False, clear_multiclip=True)

        get_logger().log(f"📁 프로젝트 생성: {name.strip()} ({len(paths)}개 미디어)")

        if self.backend:
            self.backend.start_pipeline(paths)

    def _open_project(self):
        filepath, _ = _safe_open_file_name_for_owner(
            self,
            "프로젝트 열기",
            PROJECTS_DIR,
            PROJECT_FILE_FILTER,
        )
        if not filepath:
            return
        self._open_project_file(filepath)

    def _save_current_project(self, segments=None):
        filepath = getattr(self, "_current_project_path", None)
        if not filepath:
            return

        aux_state = collect_editor_project_aux_state(getattr(self, "_editor_widget", None))

        save_project(
            filepath,
            segments=segments,
            user_settings=self._load_local_settings(),
            active_work_mode=normalize_work_mode(getattr(self, "_current_work_mode", EDITOR_MODE)),
            stt_preview_segments=aux_state["stt_preview_segments"],
            voice_activity_segments=aux_state["voice_activity_segments"],
            provisional_cut_boundaries=aux_state["provisional_cut_boundaries"],
            persist_analysis_artifacts=False,
            rewrite_stt_reference_tracks=False,
        )
        editor = getattr(self, "_editor_widget", None)
        restorer = getattr(editor, "_restore_editor_time_tags_after_save", None)
        if callable(restorer):
            try:
                restorer()
            except Exception:
                pass
        get_logger().log("💾 프로젝트 저장 완료")

    def _add_video_to_project(self):
        filepath = getattr(self, "_current_project_path", None)
        if not filepath:
            QMessageBox.warning(self, "오류", "열려있는 프로젝트가 없습니다.")
            return

        project = load_project(filepath)
        if not project:
            return

        new_paths, _ = _safe_open_file_names_for_owner(
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
            set_runtime_multiclip_state(
                self,
                ordered,
                new_bounds,
                project_boundary_rows=[b["end"] for b in new_bounds[:-1]] if len(new_bounds) > 1 else [],
                emit_boundary_signal=True,
            )
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
