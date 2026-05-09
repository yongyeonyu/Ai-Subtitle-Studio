import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.editor.editor_widget import EditorWidget
from ui.main.main_window import MainWindow


class _AutoSaveEditor:
    _auto_save_interval_ms = EditorWidget._auto_save_interval_ms
    _editor_auto_save_allowed = EditorWidget._editor_auto_save_allowed
    _on_auto_save = EditorWidget._on_auto_save


class EditorAutosaveCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_auto_save_defaults_to_five_minutes_and_clamps_low_values(self):
        editor = _AutoSaveEditor()
        editor.settings = {}
        self.assertEqual(editor._auto_save_interval_ms(), 300_000)

        editor.settings = {"editor_auto_save_interval_sec": 1}
        self.assertEqual(editor._auto_save_interval_ms(), 120_000)

        editor.settings = {"editor_auto_save_interval_sec": 600}
        self.assertEqual(editor._auto_save_interval_ms(), 600_000)

    def test_auto_save_skips_document_scan_when_nothing_changed(self):
        editor = _AutoSaveEditor()
        editor.sm = SimpleNamespace(
            is_locked=False,
            is_dirty=True,
            state="ST_EDITING",
            start_autosave=Mock(),
        )
        editor._has_unsaved_changes = Mock(return_value=False)
        editor._mark_save_completed = Mock()
        editor._get_current_segments = Mock(side_effect=AssertionError("unchanged autosave should not scan"))
        editor.sig_auto_save = SimpleNamespace(emit=Mock())
        editor._on_save = Mock()

        editor._on_auto_save()

        editor._has_unsaved_changes.assert_called_once()
        editor._mark_save_completed.assert_called_once_with(touch_saved_time=False)
        editor.sm.start_autosave.assert_not_called()
        editor.sig_auto_save.emit.assert_not_called()
        editor._on_save.assert_not_called()

    def test_auto_save_runs_only_while_editor_is_actively_editing(self):
        editor = _AutoSaveEditor()
        editor.sm = SimpleNamespace(is_locked=False, is_dirty=True, state="ST_COMP", start_autosave=Mock())
        editor._has_unsaved_changes = Mock(side_effect=AssertionError("completed generation must not autosave"))
        editor._get_current_segments = Mock(side_effect=AssertionError("completed generation must not scan subtitles"))

        editor._on_auto_save()

        editor.sm.start_autosave.assert_not_called()
        editor._has_unsaved_changes.assert_not_called()

    def test_generation_idle_cleanup_clears_busy_surfaces_and_prefetch_cache(self):
        state_manager = SimpleNamespace(is_locked=True, state="ST_PROC", complete_ai=Mock())
        timeline = SimpleNamespace(set_playhead_busy=Mock(), set_playback_center_lock=Mock())
        video_player = SimpleNamespace(set_scan_cut_active=Mock())
        prefetch_manager = SimpleNamespace(clear=Mock())
        editor = SimpleNamespace(
            sm=state_manager,
            timeline=timeline,
            video_player=video_player,
            _background_prefetch_manager=prefetch_manager,
            _clear_processing_indicators=Mock(),
            _safe_enable_start_btn=Mock(),
        )
        window = SimpleNamespace(_editor_widget=None, _auto_processing_active=True, _restore_normal_cursor=Mock())

        with patch("ui.main.main_window.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            result = MainWindow._force_editor_idle_after_generation(window, editor, reason="test")

        self.assertTrue(result["idle"])
        self.assertFalse(editor._is_ai_processing)
        self.assertTrue(editor._subtitle_generation_completed)
        state_manager.complete_ai.assert_called()
        timeline.set_playhead_busy.assert_called_with(False)
        timeline.set_playback_center_lock.assert_called_with(False)
        video_player.set_scan_cut_active.assert_called_with(False)
        prefetch_manager.clear.assert_called_once()
        self.assertEqual(editor._last_background_prefetch_request, {})
        self.assertFalse(window._auto_processing_active)
        self.assertGreaterEqual(window._restore_normal_cursor.call_count, 1)


if __name__ == "__main__":
    unittest.main()
