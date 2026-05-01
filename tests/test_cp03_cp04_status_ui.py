# Version: 03.02.13
# Phase: PHASE2
import os
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QLabel

import config
from core.state_manager import SubtitleStateManager
from core.work_mode import EDITOR_MODE
from ui.home_ui import HomeUIMixin
from ui.menu_bar import StatusRail
from ui.queue_widget import QueueMixin


class _DummyHome(QObject, HomeUIMixin):
    def __init__(self, editor):
        super().__init__()
        self._editor = editor
        self.saved_status_label = QLabel("")
        self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)

    def _active_editor(self):
        return self._editor


class Cp03Cp04StatusUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_saved_status_is_dot_and_version_only_with_generation_blink(self):
        state_manager = SimpleNamespace(state="ST_SAVED", is_locked=False, is_dirty=False)
        editor = SimpleNamespace(sm=state_manager, _is_ai_processing=False)
        home = _DummyHome(editor)

        home._refresh_saved_status_label(is_dirty=False)
        text = home.saved_status_label.text()
        self.assertIn(f"v{config.APP_VERSION}", text)
        self.assertIn("#34C759", text)
        for forbidden in ("상태 / 설정", "현재 설정", "저장됨:", "버전:"):
            self.assertNotIn(forbidden, text)

        state_manager.state = "ST_PROC"
        state_manager.is_locked = True
        state_manager.is_dirty = True
        home._refresh_saved_status_label(is_dirty=True)
        self.assertTrue(home._saved_status_blink_timer.isActive())
        self.assertEqual(home._saved_status_blink_timer.interval(), 1000)
        self.assertIn("#FF453A", home.saved_status_label.text())

        home._tick_saved_status_blink()
        self.assertIn("#5A1F24", home.saved_status_label.text())

        state_manager.state = "ST_SAVED"
        state_manager.is_locked = False
        state_manager.is_dirty = False
        home._refresh_saved_status_label(is_dirty=False)
        self.assertFalse(home._saved_status_blink_timer.isActive())
        self.assertIn("#34C759", home.saved_status_label.text())

    def test_status_rail_uses_green_flash_and_short_korean_stages(self):
        rail = StatusRail()
        try:
            flash_style = rail._state_style(True)
            self.assertIn("#34C759", flash_style)
            self.assertNotIn("#007AFF", flash_style)

            def editor_for(status, *, dirty=True, processing=True):
                label = QLabel(status)
                return SimpleNamespace(
                    status_lbl=label,
                    current_state="ST_PROC" if processing else "ST_COMP",
                    current_mode="MODE_AI_ALL",
                    _is_ai_processing=processing,
                    _is_dirty=dirty,
                    _stt_mode_enabled=False,
                    _get_current_segments=lambda: [{"start": 0.0, "end": 1.0, "text": "테스트"}],
                )

            cases = {
                "오디오 추출 중": "VAD",
                "Whisper 중": "인식",
                "LLM 최적화 중": "보정",
                "💾 자동 저장 중...": "저장",
                "✨ 자막 생성 완료": "완료",
            }
            for status, expected in cases.items():
                self.assertEqual(rail._stage_text(EDITOR_MODE, editor_for(status)), expected)
            stale_label = QLabel("자막 생성 중")
            completed_editor = SimpleNamespace(
                status_lbl=stale_label,
                current_state="ST_COMP",
                current_mode="MODE_AI_ALL",
                _is_ai_processing=False,
                _is_dirty=True,
                _stt_mode_enabled=False,
                _get_current_segments=lambda: [{"start": 0.0, "end": 1.0, "text": "테스트"}],
            )
            self.assertEqual(rail._stage_text(EDITOR_MODE, completed_editor), "완료")
        finally:
            rail.close()

    def test_progress_ticks_do_not_overwrite_active_stage_status(self):
        state_manager = SubtitleStateManager()
        state_manager.start_ai_all()
        state_manager.set_custom_status("⏳ LLM 최적화 중")
        state_manager.update_progress(1, 3, 33)
        self.assertIn("LLM", state_manager._status_msg)

    def test_queue_completion_status_completes_editor_state(self):
        class DummyQueue(QueueMixin):
            def __init__(self):
                self.synced = False
                self.refreshed_dirty = None
                self.editor = SimpleNamespace(sm=SubtitleStateManager(), is_auto_start=False)
                self.editor.sm.start_ai_all()
                self.editor._set_process_completed = self._complete_editor
                self.editor._has_unsaved_changes = lambda: True
                self._editor_widget = self.editor

            def _complete_editor(self):
                self.editor.sm.complete_ai()

            def sync_menu_from_editor(self, editor=None):
                self.synced = editor is self.editor

            def _refresh_saved_status_label(self, is_dirty=None, touch_saved_time=False):
                self.refreshed_dirty = is_dirty

        queue = DummyQueue()
        queue._sync_editor_stage_from_queue_status("✅ 자막 생성 완료")
        self.assertEqual(queue.editor.sm.state, SubtitleStateManager.ST_COMP)
        self.assertIn("완료", queue.editor.sm._status_msg)
        self.assertTrue(queue.synced)
        self.assertIs(queue.refreshed_dirty, True)

    def test_save_clears_dirty_until_real_subtitle_edit(self):
        from ui.editor.editor_widget import EditorWidget

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sample.m4a")
            open(media_path, "wb").close()
            editor = EditorWidget(
                "sample.m4a",
                [{"start": 0.0, "end": 1.0, "text": "첫 자막", "speaker": "00"}],
                media_path=media_path,
            )
            try:
                editor._flush_queue()
                editor._mark_initial_segments_saved()
                self.assertFalse(editor._has_unsaved_changes())
                self.assertFalse(editor.sm.is_dirty)

                cur = editor.text_edit.textCursor()
                cur.movePosition(QTextCursor.MoveOperation.End)
                cur.insertText(" 수정")
                editor.text_edit.setTextCursor(cur)
                editor._app_start_time = 0
                editor._on_text_edited()
                self.assertTrue(editor._has_unsaved_changes())
                self.assertTrue(editor.sm.is_dirty)

                editor._auto_save_project = lambda segs=None: None
                self.assertTrue(editor._on_save(skip_auto_next=True))
                self.assertFalse(editor._has_unsaved_changes())
                self.assertFalse(editor.sm.is_dirty)

                editor._on_text_edited()
                self.assertFalse(editor._has_unsaved_changes())
                self.assertFalse(editor.sm.is_dirty)

                class SavedQueue(QueueMixin):
                    def __init__(self, target):
                        self._editor_widget = target
                        self.refreshed_dirty = None

                    def sync_menu_from_editor(self, editor=None):
                        pass

                    def _refresh_saved_status_label(self, is_dirty=None, touch_saved_time=False):
                        self.refreshed_dirty = is_dirty

                saved_queue = SavedQueue(editor)
                saved_queue._sync_editor_stage_from_queue_status("✅ 자막생성완료")
                self.assertIs(saved_queue.refreshed_dirty, False)
                self.assertFalse(editor.sm.is_dirty)

                prompted = []
                editor._show_confirm_dialog = lambda *args, **kwargs: prompted.append(True)
                exited = []
                editor.sig_exit.connect(lambda *args: exited.append(True))
                editor._on_exit()
                self.assertFalse(prompted)
                self.assertTrue(exited)
            finally:
                editor.close()


if __name__ == "__main__":
    unittest.main()
