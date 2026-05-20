# Version: 03.10.02
# Phase: PHASE2
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QFocusEvent, QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication

from ui.editor.subtitle_text_edit import SubtitleHighlighter, SubtitleTextEdit


class SubtitleTextEditKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _key_event(self, key):
        return QKeyEvent(
            QKeyEvent.Type.KeyPress,
            key,
            Qt.KeyboardModifier.NoModifier,
        )

    def _wheel_down_event(self):
        return QWheelEvent(
            QPointF(20, 20),
            QPointF(20, 20),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )

    def test_fast_left_arrow_does_not_jump_to_block_start(self):
        edit = SubtitleTextEdit()
        try:
            edit.setPlainText("abcdef")
            cursor = edit.textCursor()
            cursor.setPosition(4)
            edit.setTextCursor(cursor)

            edit.keyPressEvent(self._key_event(Qt.Key.Key_Left))
            edit.keyPressEvent(self._key_event(Qt.Key.Key_Left))

            self.assertEqual(edit.textCursor().position(), 2)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_fast_right_arrow_does_not_jump_to_block_end(self):
        edit = SubtitleTextEdit()
        try:
            edit.setPlainText("abcdef")
            cursor = edit.textCursor()
            cursor.setPosition(2)
            edit.setTextCursor(cursor)

            edit.keyPressEvent(self._key_event(Qt.Key.Key_Right))
            edit.keyPressEvent(self._key_event(Qt.Key.Key_Right))

            self.assertEqual(edit.textCursor().position(), 4)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_bare_shift_does_not_start_video_from_text_editor(self):
        edit = SubtitleTextEdit()
        try:
            toggle_play = Mock()
            pause_playback = Mock()
            edit._parent_widget = SimpleNamespace(
                _toggle_video_play=toggle_play,
                _pause_playback_for_keyboard_edit=pause_playback,
                editor_popup=SimpleNamespace(is_visible=lambda: False),
            )

            event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Shift,
                Qt.KeyboardModifier.NoModifier,
            )
            edit.keyPressEvent(event)

            toggle_play.assert_not_called()
            pause_playback.assert_not_called()
            self.assertTrue(event.isAccepted())
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_typing_text_pauses_video_play_from_text_editor(self):
        edit = SubtitleTextEdit()
        try:
            pause_playback = Mock()
            edit._parent_widget = SimpleNamespace(
                _pause_playback_for_keyboard_edit=pause_playback,
                editor_popup=SimpleNamespace(is_visible=lambda: False),
            )

            event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_A,
                Qt.KeyboardModifier.NoModifier,
                "a",
            )
            edit.keyPressEvent(event)

            pause_playback.assert_called_once_with()
            self.assertEqual(edit.toPlainText(), "a")
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_space_key_edits_text_without_starting_video(self):
        edit = SubtitleTextEdit()
        try:
            toggle_play = Mock()
            pause_playback = Mock()
            edit._parent_widget = SimpleNamespace(
                _toggle_video_play=toggle_play,
                _pause_playback_for_keyboard_edit=pause_playback,
                editor_popup=SimpleNamespace(is_visible=lambda: False),
            )
            edit.setPlainText("안녕세계")
            cursor = edit.textCursor()
            cursor.setPosition(2)
            edit.setTextCursor(cursor)

            event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Space,
                Qt.KeyboardModifier.NoModifier,
                " ",
            )
            edit.keyPressEvent(event)

            toggle_play.assert_not_called()
            pause_playback.assert_called_once_with()
            self.assertEqual(edit.toPlainText(), "안녕 세계")
            self.assertTrue(event.isAccepted())
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_selection_lock_blocks_keyboard_cursor_movement(self):
        edit = SubtitleTextEdit()
        try:
            edit.setPlainText("abcdef")
            cursor = edit.textCursor()
            cursor.setPosition(2)
            edit.setTextCursor(cursor)
            edit.set_selection_locked(True)

            edit.keyPressEvent(self._key_event(Qt.Key.Key_Right))

            self.assertEqual(edit.textCursor().position(), 2)
            self.assertTrue(edit.isReadOnly())
            self.assertEqual(edit.focusPolicy(), Qt.FocusPolicy.NoFocus)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_mouse_wheel_scrolls_even_when_selection_locked(self):
        edit = SubtitleTextEdit()
        try:
            edit.resize(360, 120)
            edit.setPlainText("\n".join(f"line {idx}" for idx in range(120)))
            edit.show()
            self.app.processEvents()
            edit.verticalScrollBar().setValue(0)
            edit.set_selection_locked(True)

            event = self._wheel_down_event()
            handled = edit.apply_wheel_scroll_event(event)

            self.assertTrue(handled)
            self.assertTrue(event.isAccepted())
            self.assertGreater(edit.verticalScrollBar().value(), 0)
            self.assertGreater(float(getattr(edit, "_last_user_scroll_at", 0.0)), 0.0)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_timestamp_margin_wheel_scrolls_editor(self):
        edit = SubtitleTextEdit()
        try:
            edit.resize(360, 120)
            edit.setPlainText("\n".join(f"line {idx}" for idx in range(120)))
            edit.show()
            self.app.processEvents()
            edit.verticalScrollBar().setValue(0)

            edit.timestampArea.wheelEvent(self._wheel_down_event())

            self.assertGreater(edit.verticalScrollBar().value(), 0)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_current_line_change_does_not_rehighlight_whole_document(self):
        edit = SubtitleTextEdit()
        try:
            highlighter = SubtitleHighlighter(edit.document())
            with patch.object(highlighter, "rehighlight") as rehighlight:
                highlighter.set_current_line(3)
                highlighter.set_current_line(9)
            self.assertEqual(highlighter._current_line, 9)
            rehighlight.assert_not_called()
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_quality_map_can_rehighlight_visible_blocks_only(self):
        edit = SubtitleTextEdit()
        try:
            edit.setPlainText("\n".join(f"line {idx}" for idx in range(20)))
            highlighter = SubtitleHighlighter(edit.document())
            with patch.object(highlighter, "rehighlight") as rehighlight, \
                 patch.object(highlighter, "rehighlightBlock", wraps=highlighter.rehighlightBlock) as rehighlight_block:
                highlighter.set_quality_map(
                    {5: {"confidence_label": "red"}, 6: {"confidence_label": "green"}},
                    visible_lines=range(4, 8),
                )

            rehighlight.assert_not_called()
            self.assertGreaterEqual(rehighlight_block.call_count, 2)
            self.assertEqual(set(highlighter.quality_by_line), {5, 6})
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_quality_map_rehighlights_only_changed_visible_blocks(self):
        edit = SubtitleTextEdit()
        try:
            edit.setPlainText("\n".join(f"line {idx}" for idx in range(200)))
            highlighter = SubtitleHighlighter(edit.document())
            highlighter.set_quality_map(
                {5: {"confidence_label": "red"}, 6: {"confidence_label": "green"}},
                visible_lines=range(0, 120),
            )

            with patch.object(highlighter, "rehighlight") as rehighlight, \
                 patch.object(highlighter, "rehighlightBlock", wraps=highlighter.rehighlightBlock) as rehighlight_block:
                highlighter.set_quality_map(
                    {5: {"confidence_label": "red"}, 6: {"confidence_label": "yellow"}},
                    visible_lines=range(0, 120),
                )

            rehighlight.assert_not_called()
            self.assertEqual(
                [call.args[0].blockNumber() for call in rehighlight_block.call_args_list],
                [6],
            )
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_quick_layer_marks_qml_segment_overlay_active(self):
        edit = SubtitleTextEdit()
        try:
            edit._quick_layer = object()
            self.assertTrue(edit._quick_layer_overlay_text_active())
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_qml_text_overlay_is_opt_in_even_when_scenegraph_is_available(self):
        with patch.dict(os.environ, {"AI_SUBTITLE_EDITOR_TEXT_QML": ""}, clear=False), \
             patch("ui.editor.subtitle_text_edit.scenegraph_enabled", return_value=True):
            edit = SubtitleTextEdit()
        try:
            self.assertIsNone(edit._quick_layer)
            self.assertFalse(edit._quick_layer_overlay_text_active())
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_focus_in_disables_window_space_shortcut_while_editing(self):
        edit = SubtitleTextEdit()
        shortcut = SimpleNamespace(setEnabled=Mock())
        edit._parent_widget = SimpleNamespace(space_shortcut=shortcut)
        try:
            edit.focusInEvent(QFocusEvent(QEvent.Type.FocusIn))

            shortcut.setEnabled.assert_called_once_with(False)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_focus_out_event_ignores_deleted_space_shortcut(self):
        edit = SubtitleTextEdit()
        deleted_shortcut = SimpleNamespace(
            setEnabled=Mock(side_effect=RuntimeError("wrapped C/C++ object of type QShortcut has been deleted"))
        )
        edit._parent_widget = SimpleNamespace(space_shortcut=deleted_shortcut)
        try:
            edit.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
            deleted_shortcut.setEnabled.assert_called_once_with(True)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()

    def test_overlay_refresh_ignores_deleted_highlighter(self):
        edit = SubtitleTextEdit()
        deleted_highlighter = SimpleNamespace(
            set_gpu_overlay_active=Mock(
                side_effect=RuntimeError("wrapped C/C++ object of type SubtitleHighlighter has been deleted")
            )
        )
        edit._parent_widget = SimpleNamespace(_highlighter=deleted_highlighter)
        edit._quick_layer = object()
        try:
            edit._refresh_gpu_document_overlay_mode()
            self.assertTrue(edit._gpu_document_overlay_active)
            deleted_highlighter.set_gpu_overlay_active.assert_called_once_with(True)
        finally:
            edit.close()
            edit.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
