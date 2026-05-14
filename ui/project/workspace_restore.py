# Version: 03.09.28
# Phase: PHASE1-C
"""
ui/workspace_mixin.py
Workspace restore mixin
"""
import os

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor

from core.runtime.logger import get_logger
from core.project.project_manager import load_project
from ui.project.project_session_runtime import attach_project_session


class WorkspaceMixin:
    def _gather_workspace(self, editor):
        ws = {
            "last_playhead": 0.0,
            "last_cursor_block": 0,
            "splitter_sizes": [],
            "terminal_visible": getattr(self, "_log_visible", False),
            "dashboard_mode": getattr(self, "_dashboard_mode", "dashboard"),
            "project_panel_visible": bool(getattr(self, "_project_panel_visible", True)),
        }

        try:
            if hasattr(editor, "video_player"):
                ws["last_playhead"] = getattr(editor.video_player, "current_time", 0.0)

            if hasattr(editor, "text_edit"):
                ws["last_cursor_block"] = editor.text_edit.textCursor().blockNumber()

            if hasattr(editor, "splitter"):
                ws["splitter_sizes"] = editor.splitter.sizes()
        except Exception:
            pass

        return ws

    def _auto_save_project(self, srt_path, segments):
        try:
            from core.project.project_manager import PROJECTS_DIR, create_project, save_project

            editor = self._editor_widget
            if not editor:
                return

            media_path = getattr(editor, "media_path", "")
            if not media_path:
                return

            if self._current_project_path and os.path.exists(self._current_project_path):
                project_path = self._current_project_path
            else:
                base_name = os.path.splitext(os.path.basename(media_path))[0]
                project_path = os.path.join(PROJECTS_DIR, f"{base_name}.json")

                if not os.path.exists(project_path):
                    project_path = create_project(
                        name=base_name,
                        media_paths=[media_path],
                        srt_path=srt_path,
                        user_settings=dict(getattr(editor, "settings", {}) or {}),
                    )
                attach_project_session(
                    self,
                    project_path,
                    None,
                    auto_pipeline=False,
                    clear_multiclip=False,
                    emit_boundary_signal=False,
                )

            workspace = self._gather_workspace(editor)

            save_project(
                filepath=project_path,
                srt_path=srt_path,
                segments=segments,
                user_settings=dict(getattr(editor, "settings", {}) or {}),
                workspace=workspace,
            )
        except Exception as e:
            get_logger().log(f"Auto project save failed: {e}")

    def _restore_workspace(self, editor, proj_path):
        try:
            project_data = load_project(proj_path, hydrate_text_assets=False)
            if not project_data:
                return

            workspace = project_data.get("workspace", {})
            if not workspace:
                self._fit_timeline_on_start(editor)
                return

            def _apply():
                try:
                    splitter_sizes = workspace.get("splitter_sizes", [])
                    if splitter_sizes and hasattr(editor, "splitter"):
                        editor.splitter.setSizes(splitter_sizes)

                    if hasattr(self, "_dashboard_mode"):
                        self._dashboard_mode = workspace.get("dashboard_mode", "dashboard") or "dashboard"
                    if hasattr(self, "_project_panel_visible"):
                        self._project_panel_visible = bool(workspace.get("project_panel_visible", True))
                    if hasattr(self, "_apply_log_visible"):
                        self._apply_log_visible(bool(workspace.get("terminal_visible", False)))

                    playhead = workspace.get("last_playhead", 0.0)
                    if playhead > 0:
                        if hasattr(editor, "video_player"):
                            editor.video_player.seek(playhead)
                        if hasattr(editor, "timeline"):
                            editor.timeline.set_playhead(playhead)

                    if hasattr(editor, "timeline"):
                        if hasattr(editor.timeline, "show_time_window_seconds"):
                            editor.timeline.show_time_window_seconds(
                                15.0,
                                center_sec=playhead if playhead > 0 else None,
                            )
                        elif hasattr(editor.timeline, "fit_to_view"):
                            editor.timeline.fit_to_view()
                            if playhead > 0:
                                editor.timeline.center_to_sec(playhead, smooth=False)

                    block_num = workspace.get("last_cursor_block", 0)
                    if block_num > 0 and hasattr(editor, "text_edit"):
                        block = editor.text_edit.document().findBlockByNumber(block_num)
                        if block.isValid():
                            cursor = QTextCursor(block)
                            editor.text_edit.setTextCursor(cursor)
                            editor.text_edit.ensureCursorVisible()

                except Exception:
                    pass

            QTimer.singleShot(500, _apply)
        except Exception:
            pass

    def _fit_timeline_on_start(self, editor):
        timeline = getattr(editor, "timeline", None)
        if timeline is not None and hasattr(timeline, "schedule_time_window_seconds"):
            timeline.schedule_time_window_seconds(15.0, delays=(500,))
        elif timeline is not None and hasattr(timeline, "fit_to_view"):
            QTimer.singleShot(500, timeline.fit_to_view)

    def _fit_timeline_if_missing_zoom(self, editor):
        self._fit_timeline_on_start(editor)
