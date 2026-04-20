# Version: 01.00.00
"""
ui/workspace_mixin.py
MainWindow 프로젝트 저장/복원 Mixin
"""
import os
from PyQt6.QtCore import QTimer

from logger import get_logger
from core.project_manager import load_project


class WorkspaceMixin:

    def _gather_workspace(self, editor):
        """에디터에서 현재 작업 환경 수집"""
        ws = {
            "last_playhead": 0.0,
            "last_cursor_block": 0,
            "zoom_pps": 200.0,
            "scroll_position": 0.0,
            "splitter_sizes": [],
            "terminal_visible": getattr(self, '_log_visible', False)
        }
        try:
            if hasattr(editor, 'video_player'):
                ws["last_playhead"] = getattr(editor.video_player, 'current_time', 0.0)
            if hasattr(editor, 'text_edit'):
                ws["last_cursor_block"] = editor.text_edit.textCursor().blockNumber()
            if hasattr(editor, 'timeline') and hasattr(editor.timeline, 'canvas'):
                ws["zoom_pps"] = editor.timeline.canvas.pps
            if hasattr(editor, 'timeline') and hasattr(editor.timeline, 'scroll'):
                ws["scroll_position"] = float(editor.timeline.scroll.horizontalScrollBar().value())
            if hasattr(editor, 'splitter'):
                ws["splitter_sizes"] = editor.splitter.sizes()
        except Exception:
            pass
        return ws

    def _auto_save_project(self, srt_path, segments):
        """SRT 저장 시 프로젝트 JSON도 자동 저장"""
        try:
            from core.project_manager import save_project, create_project, PROJECTS_DIR

            editor = self._editor_widget
            if not editor:
                return

            media_path = getattr(editor, 'media_path', '')
            if not media_path:
                return

            if self._current_project_path and os.path.exists(self._current_project_path):
                proj_path = self._current_project_path
            else:
                base_name = os.path.splitext(os.path.basename(media_path))[0]
                proj_path = os.path.join(PROJECTS_DIR, f"{base_name}.json")
                if not os.path.exists(proj_path):
                    proj_path = create_project(
                        name=base_name,
                        media_paths=[media_path],
                        srt_path=srt_path
                    )
                self._current_project_path = proj_path

            workspace = self._gather_workspace(editor)

            save_project(
                filepath=proj_path,
                srt_path=srt_path,
                segments=segments,
                workspace=workspace
            )
        except Exception as e:
            get_logger().log(f"⚠️ 프로젝트 자동 저장 실패: {e}")

    def _restore_workspace(self, editor, proj_path):
        """프로젝트 JSON에서 작업 환경 복원"""
        try:
            pd = load_project(proj_path)
            if not pd:
                return
            ws = pd.get("workspace", {})
            if not ws:
                return

            def _apply():
                try:
                    pps = ws.get("zoom_pps", 0)
                    if pps > 0 and hasattr(editor, 'timeline') and hasattr(editor.timeline, 'canvas'):
                        editor.timeline.canvas.pps = pps

                    if hasattr(editor, 'splitter') and ws.get("splitter_sizes"):
                        editor.splitter.setSizes(ws["splitter_sizes"])

                    playhead = ws.get("last_playhead", 0.0)
                    if playhead > 0:
                        if hasattr(editor, 'video_player'):
                            editor.video_player.seek(playhead)
                        if hasattr(editor, 'timeline'):
                            editor.timeline.set_playhead(playhead)
                            editor.timeline.center_to_sec(playhead, smooth=False)

                    block_num = ws.get("last_cursor_block", 0)
                    if block_num > 0 and hasattr(editor, 'text_edit'):
                        from PyQt6.QtGui import QTextCursor
                        block = editor.text_edit.document().findBlockByNumber(block_num)
                        if block.isValid():
                            cur = QTextCursor(block)
                            editor.text_edit.setTextCursor(cur)
                            editor.text_edit.ensureCursorVisible()

                    scroll_pos = ws.get("scroll_position", 0)
                    if scroll_pos > 0 and hasattr(editor, 'timeline') and hasattr(editor.timeline, 'scroll'):
                        editor.timeline.scroll.horizontalScrollBar().setValue(int(scroll_pos))
                        editor.timeline._target_scroll_x = float(scroll_pos)
                        editor.timeline._current_scroll_x = float(scroll_pos)
                except Exception:
                    pass

            QTimer.singleShot(500, _apply)
        except Exception:
            pass