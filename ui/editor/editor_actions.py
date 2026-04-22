# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/editor_actions.py
에디터 UI 버튼 액션 (저장/이전/종료/내보내기/설정)
- editor_pipeline.py에서 분리
"""

import os
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt

from logger import get_logger
from core.data_manager import save_settings as _dm_save_settings
from core.subtitle_engine import save_srt
from core.path_manager import get_srt_path


class EditorActionsMixin:
    """저장 / 이전 / 종료 / 내보내기 / 설정 다이얼로그"""

    # ---------------------------------------------------------
    # 공통 유틸
    # ---------------------------------------------------------
    def _go_home(self):
        try:
            self._cleanup()
        except Exception:
            pass
        try:
            self.sig_prev.emit()
        except Exception:
            pass
        try:
            main_w = self.window()
            for name in ("handle_prev", "show_home", "go_home", "_show_home", "show_main"):
                if hasattr(main_w, name) and callable(getattr(main_w, name)):
                    getattr(main_w, name)()
                    break
        except Exception:
            pass

    def _show_confirm_dialog(self, title, text):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No |
            QMessageBox.StandardButton.Cancel
        )
        msg_box.setStyleSheet("""
            QMessageBox { background-color: #1a1a1a; color: #FFFFFF; }
            QPushButton { background-color: #333333; color: #FFFFFF; border: 2px solid #FFFFFF; padding: 6px 16px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #555555; }
        """)
        msg_box.button(QMessageBox.StandardButton.Yes).setText("예")
        msg_box.button(QMessageBox.StandardButton.No).setText("아니요")
        msg_box.button(QMessageBox.StandardButton.Cancel).setText("취소")
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
        return msg_box.exec()

    # ---------------------------------------------------------
    # 저장
    # ---------------------------------------------------------
    def _on_save(self, *args, skip_auto_next=False):
        segs = self._get_current_segments()
        if not segs:
            return

        try:
            if getattr(self, 'media_path', None):
                srt_path = get_srt_path(self.media_path)
                save_srt(segs, srt_path)
                get_logger().log(f"💾 저장 완료: {os.path.basename(srt_path)}")
        except Exception as e:
            get_logger().log(f"⚠️ 저장 실패: {e}")
            return

        try:
            self.sig_save.emit(segs)
        except Exception:
            pass

        try:
            if hasattr(self, "sm"):
                if getattr(self.sm, "is_locked", False):
                    self.sm.is_dirty = False
                else:
                    self.sm.complete_save()
        except Exception:
            pass

        self._skip_prev_confirm_once = True

        try:
            self._auto_save_project(segs)
        except Exception as e:
            get_logger().log(f"⚠️ 프로젝트 자동 저장 실패: {e}")

    # ---------------------------------------------------------
    # 프로젝트 자동 저장
    # ---------------------------------------------------------
    def _auto_save_project(self, segs: list = None):
        from core.project_manager import (
            save_project, create_project, load_project,
            ensure_projects_dir, PROJECTS_DIR
        )

        media_path = getattr(self, 'media_path', None)
        if not media_path:
            return

        main_w = self.window()
        project_path = getattr(main_w, '_current_project_path', None)

        if not project_path:
            base_name = os.path.splitext(os.path.basename(media_path))[0]
            project_path = create_project(
                name=base_name,
                media_paths=[media_path],
                srt_path=get_srt_path(media_path)
            )
            main_w._current_project_path = project_path
            get_logger().log(f"📝 프로젝트 자동 생성: {os.path.basename(project_path)}")

        workspace = {}
        if hasattr(self, 'video_player'):
            workspace["last_playhead"] = getattr(self.video_player, 'current_time', 0.0)
        if hasattr(self, 'text_edit'):
            workspace["last_cursor_block"] = self.text_edit.textCursor().blockNumber()
        if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            workspace["zoom_pps"] = self.timeline.canvas.pps
        if hasattr(self, 'splitter'):
            workspace["splitter_sizes"] = self.splitter.sizes()
        try:
            workspace["terminal_visible"] = main_w._log_visible
        except Exception:
            pass

        save_project(
            filepath=project_path,
            srt_path=get_srt_path(media_path),
            segments=segs,
            workspace=workspace
        )
        get_logger().log(f"📦 프로젝트 저장 완료: {os.path.basename(project_path)}")

    # ---------------------------------------------------------
    # 이전
    # ---------------------------------------------------------
    def _on_prev(self):
        from core.state_manager import SubtitleStateManager

        if self.sm.state == SubtitleStateManager.ST_PROC:
            self._stop_pipeline()

        if getattr(self, "_skip_prev_confirm_once", False):
            self._skip_prev_confirm_once = False
            self._go_home()
            return

        is_dirty = False
        try:
            is_dirty = bool(getattr(self.sm, "is_dirty", False))
        except Exception:
            pass

        if not is_dirty:
            self._go_home()
            return

        reply = self._show_confirm_dialog(
            "이전으로 이동",
            "저장되지 않은 변경사항이 있습니다.\n저장하시겠습니까?"
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return
        if reply == QMessageBox.StandardButton.Yes:
            self._on_save()

        self._go_home()

    # ---------------------------------------------------------
    # 종료
    # ---------------------------------------------------------
    def _on_exit(self):
        from core.state_manager import SubtitleStateManager

        if self.sm.state == SubtitleStateManager.ST_PROC:
            self._stop_pipeline()

        if getattr(self, "_skip_prev_confirm_once", False):
            self._skip_prev_confirm_once = False
            self.sig_exit.emit()
            return

        is_dirty = False
        try:
            is_dirty = bool(getattr(self.sm, "is_dirty", False))
        except Exception:
            pass

        if not is_dirty:
            self.sig_exit.emit()
            return

        reply = self._show_confirm_dialog(
            "종료",
            "저장되지 않은 변경사항이 있습니다.\n저장하시겠습니까?"
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return
        if reply == QMessageBox.StandardButton.Yes:
            self._on_save()

        self.sig_exit.emit()

    # ---------------------------------------------------------
    # 다음
    # ---------------------------------------------------------
    def _on_next(self):
        QMessageBox.information(self, "알림", "개발중입니다.")

    # ---------------------------------------------------------
    # 내보내기
    # ---------------------------------------------------------
    def _show_export_dialog(self):
        is_dirty = False
        try:
            if hasattr(self, "sm"):
                is_dirty = bool(getattr(self.sm, "is_dirty", False))
        except Exception:
            pass

        if is_dirty:
            reply = self._show_confirm_dialog(
                "자막 출력",
                "변경된 자막이 저장되지 않았습니다.\n저장 후 출력하시겠습니까?"
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._on_save()

        from ui.export_dialog import ExportDialog
        segs = self._get_current_segments()
        if segs:
            dlg = ExportDialog(segs, getattr(self, 'video_name', ''), self)
            if hasattr(self, 'video_player'):
                dlg._video_player_ref = self.video_player
            dlg.exec()

    # ---------------------------------------------------------
    # 설정 다이얼로그
    # ---------------------------------------------------------
    def _show_settings(self):
        from ui.settings.settings_dialog import SettingsDialog
        self.setCursor(Qt.CursorShape.WaitCursor)
        dlg = SettingsDialog(self.settings, self)
        self.unsetCursor()
        if dlg.exec():
            self.settings = dlg.result_settings
            _dm_save_settings(self.settings)
            if hasattr(self, '_update_engine_label_text'):
                self._update_engine_label_text()
    def _show_adv_settings(self):
        from ui.settings.settings_dialog import AdvancedSettingsDialog
        dlg = AdvancedSettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings.update(dlg.result)
            _dm_save_settings(self.settings)

    def _show_speaker_settings(self):
        from ui.settings.settings_dialog import SpeakerDialog
        dlg = SpeakerDialog(self.settings, self)
        if dlg.exec():
            self.settings.update(dlg.result)
            _dm_save_settings(self.settings)
            if hasattr(self, '_update_highlighter_colors'):
                self._update_highlighter_colors()

    def _show_gap_settings(self):
        from ui.settings.settings_dialog import GapSettingsDialog
        dlg = GapSettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings.update(dlg.result)
            _dm_save_settings(self.settings)