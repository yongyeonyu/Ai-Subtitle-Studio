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
            from core.project.project_manager import create_project, project_file_path_for_name, save_project

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
                project_path = project_file_path_for_name(base_name)

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
                persist_analysis_artifacts=False,
                rewrite_stt_reference_tracks=False,
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

            def _current_playhead() -> float:
                try:
                    canvas = getattr(getattr(editor, "timeline", None), "canvas", None)
                    return float(getattr(canvas, "playhead_sec", 0.0) or 0.0)
                except Exception:
                    return 0.0

            scheduled_playhead = _current_playhead()

            def _external_seek_override() -> tuple[float | None, bool]:
                try:
                    if int(getattr(editor, "_external_playhead_seek_revision", 0) or 0) <= 0:
                        return None, True
                    return (
                        float(getattr(editor, "_external_playhead_seek_sec", 0.0) or 0.0),
                        bool(getattr(editor, "_external_playhead_seek_sync_video", True)),
                    )
                except Exception:
                    return None, True

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

                    try:
                        playhead = float(workspace.get("last_playhead", 0.0) or 0.0)
                    except Exception:
                        playhead = 0.0
                    current_playhead = _current_playhead()
                    external_seek, external_sync_video = _external_seek_override()
                    # Deferred open restore must not undo a user/automation seek that landed before this timer fires.
                    playhead_was_changed = abs(current_playhead - scheduled_playhead) > 0.05
                    target_center = external_seek if external_seek is not None else (current_playhead if playhead_was_changed else playhead)
                    if external_seek is not None:
                        local_seek = external_seek
                        localizer = getattr(editor, "_global_to_local_sec", None)
                        if callable(localizer):
                            try:
                                local_seek = float(localizer(external_seek) or 0.0)
                            except Exception:
                                local_seek = external_seek
                        if external_sync_video and hasattr(editor, "video_player"):
                            editor.video_player.seek(local_seek)
                        if hasattr(editor, "timeline"):
                            editor.timeline.set_playhead(external_seek)
                    elif playhead > 0 and not playhead_was_changed:
                        if hasattr(editor, "video_player"):
                            editor.video_player.seek(playhead)
                        if hasattr(editor, "timeline"):
                            editor.timeline.set_playhead(playhead)

                    if hasattr(editor, "timeline"):
                        preferred_seconds = (
                            editor.timeline.preferred_edit_window_seconds()
                            if hasattr(editor.timeline, "preferred_edit_window_seconds")
                            else float(getattr(editor.timeline, "_preferred_edit_window_seconds", 10.0) or 10.0)
                        )
                        if hasattr(editor.timeline, "show_time_window_seconds"):
                            editor.timeline.show_time_window_seconds(
                                preferred_seconds,
                                center_sec=target_center if target_center > 0 else None,
                            )
                        elif hasattr(editor.timeline, "fit_to_view"):
                            editor.timeline.fit_to_view()
                            if target_center > 0:
                                editor.timeline.center_to_sec(target_center, smooth=False)

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
            preferred_seconds = (
                timeline.preferred_edit_window_seconds()
                if hasattr(timeline, "preferred_edit_window_seconds")
                else float(getattr(timeline, "_preferred_edit_window_seconds", 10.0) or 10.0)
            )
            timeline.schedule_time_window_seconds(preferred_seconds, delays=(500,))
        elif timeline is not None and hasattr(timeline, "fit_to_view"):
            QTimer.singleShot(500, timeline.fit_to_view)

    def _fit_timeline_if_missing_zoom(self, editor):
        self._fit_timeline_on_start(editor)
