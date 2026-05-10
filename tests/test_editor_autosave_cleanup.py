import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.editor.editor_widget import EditorWidget
from ui.editor.editor_pipeline import EditorPipelineMixin
from ui.main.main_window import MainWindow


class _AutoSaveEditor:
    _auto_save_interval_ms = EditorWidget._auto_save_interval_ms
    _editor_auto_save_allowed = EditorWidget._editor_auto_save_allowed
    _on_auto_save = EditorWidget._on_auto_save


class _CompletionEditor(EditorPipelineMixin):
    def __init__(self):
        self.sm = SimpleNamespace(
            complete_ai=Mock(),
            complete_auto_mode=Mock(),
        )
        self._flush_pending_segment_queue_now = Mock()
        self._clear_processing_indicators = Mock()
        self._post_completion_sync = Mock()
        self._on_save = Mock(return_value=True)
        self._get_current_segments = Mock(return_value=[{"start": 0.0, "end": 1.0, "text": "ok"}])
        self.settings = {}
        self.is_auto_start = False
        self._segment_queue = []
        self._window = SimpleNamespace(
            _force_editor_idle_after_generation=Mock(),
            sync_menu_from_editor=Mock(),
            _refresh_saved_status_label=Mock(),
            _start_post_completion_idle_timer=Mock(),
        )

    def window(self):
        return self._window


class EditorAutosaveCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_auto_save_is_fixed_to_five_minutes(self):
        editor = _AutoSaveEditor()
        editor.settings = {}
        self.assertEqual(editor._auto_save_interval_ms(), 300_000)

        editor.settings = {"editor_auto_save_interval_sec": 1}
        self.assertEqual(editor._auto_save_interval_ms(), 300_000)

        editor.settings = {"editor_auto_save_interval_sec": 600}
        self.assertEqual(editor._auto_save_interval_ms(), 300_000)

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

    def test_auto_save_is_blocked_until_manual_save_for_manual_confirm_operations(self):
        editor = _AutoSaveEditor()
        editor._autosave_requires_manual_save = True
        editor.sm = SimpleNamespace(is_locked=False, is_dirty=True, state="ST_EDITING", start_autosave=Mock())
        editor._has_unsaved_changes = Mock(side_effect=AssertionError("manual-save-required state must not autosave"))
        editor._get_current_segments = Mock(side_effect=AssertionError("manual-save-required state must not scan"))

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

    def test_backend_generation_finalizer_marks_complete_and_auto_saves_once(self):
        editor = _CompletionEditor()

        with patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._finalize_generation_from_backend(reason="test")
            editor._finalize_generation_from_backend(reason="duplicate")

        editor.sm.complete_ai.assert_called_once()
        editor._flush_pending_segment_queue_now.assert_called_once()
        editor._on_save.assert_called_once_with(skip_auto_next=True)
        self.assertTrue(editor._process_completed_finalized)
        self.assertTrue(editor._generation_completion_autosave_done)

    def test_stt_progress_complete_does_not_finalize_before_backend_finalizer(self):
        editor = _CompletionEditor()
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor._completion_handled = False
        editor._process_completed_finalized = False
        editor.sm = SimpleNamespace(
            update_progress=Mock(),
            complete_ai=Mock(),
            _is_stage_status_active=Mock(return_value=False),
        )

        with patch("ui.editor.editor_pipeline.QTimer.singleShot") as single_shot:
            editor.update_progress(10, 10)

        editor.sm.complete_ai.assert_not_called()
        self.assertFalse(editor._completion_handled)
        self.assertFalse(editor._process_completed_finalized)
        self.assertEqual(editor.sm.update_progress.call_args_list[-1].args[3], "⏳ 자막 최적화/검수 중...")
        single_shot.assert_not_called()

    def test_backend_generation_finalizer_waits_until_segments_exist(self):
        editor = _CompletionEditor()
        editor._get_current_segments = Mock(return_value=[])
        editor.sm.update_progress = Mock()

        with patch("ui.editor.editor_pipeline.QTimer.singleShot") as single_shot:
            editor._finalize_generation_from_backend(reason="test")

        editor.sm.complete_ai.assert_not_called()
        self.assertFalse(getattr(editor, "_process_completed_finalized", False))
        self.assertEqual(editor.sm.update_progress.call_args_list[-1].args[3], "⏳ 최종 자막 반영 중...")
        single_shot.assert_called_once()

    def test_generation_completion_autosave_waits_until_segments_exist(self):
        editor = _CompletionEditor()
        editor._get_current_segments = Mock(return_value=[])
        editor._segment_queue = []
        editor._generation_completion_autosave_done = False

        with patch("ui.editor.editor_pipeline.QTimer.singleShot") as single_shot:
            editor._run_generation_completion_autosave(attempt=0)

        editor._on_save.assert_not_called()
        single_shot.assert_called_once()


if __name__ == "__main__":
    unittest.main()
