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
                    restored_playhead: float | None = None
                    restored_sync_video = True

                    def _local_seek_for(global_sec: float) -> float:
                        local_seek = float(global_sec or 0.0)
                        localizer = getattr(editor, "_global_to_local_sec", None)
                        if callable(localizer):
                            try:
                                local_seek = float(localizer(local_seek) or 0.0)
                            except Exception:
                                local_seek = float(global_sec or 0.0)
                        return local_seek

                    def _sync_restored_playhead(global_sec: float, *, sync_video: bool = True) -> None:
                        # 변경 금지: workspace의 last_cursor_block은 저장 당시 텍스트 블록 번호라
                        # external final.srt 정규화, 중복 제거, 재분할 뒤에는 같은 자막을 가리키지
                        # 않는다. 프로젝트 복원은 블록 번호가 아니라 시간(playhead)을 기준으로
                        # 비디오/타임라인/자막 에디터를 다시 묶어야 마카오처럼 자막 세그먼트가
                        # 음성보다 앞서 보이는 싱크 분리가 재발하지 않는다.
                        try:
                            sec = float(global_sec or 0.0)
                        except Exception:
                            return
                        if sec <= 0:
                            return
                        if sync_video and hasattr(editor, "video_player"):
                            try:
                                editor.video_player.seek(_local_seek_for(sec))
                            except Exception:
                                pass
                        try:
                            if hasattr(editor, "timeline"):
                                current = _current_playhead()
                                if abs(current - sec) > 0.0005:
                                    editor.timeline.set_playhead(sec)
                        except Exception:
                            pass
                        sync_after_seek = getattr(editor, "_sync_after_manual_seek", None)
                        if callable(sync_after_seek):
                            try:
                                sync_after_seek(sec)
                                return
                            except Exception:
                                pass

                    if external_seek is not None:
                        if external_sync_video and hasattr(editor, "video_player"):
                            editor.video_player.seek(_local_seek_for(external_seek))
                        if hasattr(editor, "timeline"):
                            editor.timeline.set_playhead(external_seek)
                        restored_playhead = external_seek
                        restored_sync_video = external_sync_video
                    elif playhead > 0 and not playhead_was_changed:
                        if hasattr(editor, "video_player"):
                            editor.video_player.seek(_local_seek_for(playhead))
                        if hasattr(editor, "timeline"):
                            editor.timeline.set_playhead(playhead)
                        restored_playhead = playhead
                    elif target_center > 0:
                        restored_playhead = target_center
                        restored_sync_video = False

                    if hasattr(editor, "timeline"):
                        try:
                            # 변경 금지: 프로젝트 오픈 직후에는 editor 초기 레이아웃 fit 타이머와
                            # workspace 복원 타이머가 동시에 살아 있다. workspace가 저장된
                            # playhead/8초 창을 복원한 뒤 늦게 도착한 fit 타이머가 전체 보기로
                            # 다시 펼치면 STT1/2 후보가 너무 작아져 "세그먼트가 안 나온다"는
                            # 상태가 재발한다. workspace가 뷰 소유권을 가져가면 이전 초기
                            # open-view 토큰은 반드시 무효화한다.
                            editor.timeline._initial_open_view_token = object()
                        except Exception:
                            pass
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
                    if block_num > 0 and restored_playhead is None and hasattr(editor, "text_edit"):
                        block = editor.text_edit.document().findBlockByNumber(block_num)
                        if block.isValid():
                            cursor = QTextCursor(block)
                            editor.text_edit.setTextCursor(cursor)
                            editor.text_edit.ensureCursorVisible()

                    if restored_playhead is not None and restored_playhead > 0:
                        _sync_restored_playhead(restored_playhead, sync_video=False)
                        for delay in (180, 460, 820):
                            QTimer.singleShot(
                                delay,
                                lambda sec=restored_playhead, sv=restored_sync_video: _sync_restored_playhead(
                                    sec,
                                    sync_video=sv,
                                ),
                            )

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
