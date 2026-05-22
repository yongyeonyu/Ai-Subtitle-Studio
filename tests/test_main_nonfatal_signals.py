import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import Mock

from ui.main.main_signals import SignalHandlersMixin


class _SignalWindow(SignalHandlersMixin):
    def __init__(self, editor=None):
        self._editor_widget = editor
        self.backend = None
        self._roughcut_widget = None
        self._editor_roughcut_result = None
        self.stack = SimpleNamespace(addWidget=Mock(), currentWidget=Mock(return_value=None))


class _Event:
    def __init__(self):
        self.called = 0

    def set(self):
        self.called += 1


class _BadTimer:
    def isActive(self):
        return True

    def stop(self):
        raise RuntimeError("timer gone")


class MainNonfatalSignalsTests(unittest.TestCase):
    def test_do_append_segments_ready_sets_event_when_flush_fails(self):
        editor = SimpleNamespace(
            append_segments=Mock(),
            _flush_queue=Mock(side_effect=RuntimeError("flush failed")),
        )
        window = _SignalWindow(editor=editor)
        event = _Event()

        window._do_append_segments_ready([{"text": "A"}], event)

        editor.append_segments.assert_called_once()
        self.assertEqual(event.called, 1)

    def test_do_append_segments_flush_defers_repaint_without_reentering_event_loop(self):
        canvas = SimpleNamespace(update=Mock())
        timeline = SimpleNamespace(update=Mock(), canvas=canvas)
        editor = SimpleNamespace(
            append_segments=Mock(),
            _flush_pending_segment_queue_now=Mock(),
            update=Mock(),
            timeline=timeline,
        )
        window = _SignalWindow(editor=editor)

        with mock.patch("ui.main.main_signals.QApplication.processEvents", side_effect=AssertionError("should not run")) as process_events:
            with mock.patch("ui.main.main_signals.QApplication.instance", return_value=object()):
                with mock.patch("ui.main.main_signals.QTimer.singleShot") as single_shot:
                    window._do_append_segments([{"text": "A"}], flush=True)

        editor.append_segments.assert_called_once()
        editor._flush_pending_segment_queue_now.assert_called_once()
        process_events.assert_not_called()
        single_shot.assert_called_once()
        delay, callback = single_shot.call_args.args
        self.assertEqual(delay, 0)

        callback()

        editor.update.assert_called_once()
        timeline.update.assert_called_once()
        canvas.update.assert_called_once()

    def test_do_clear_editor_continues_when_timer_stop_fails(self):
        text_edit = SimpleNamespace(clear=Mock())
        timeline = SimpleNamespace(
            canvas=SimpleNamespace(total_duration=3.0),
            update_segments=Mock(),
            set_playhead=Mock(),
        )
        video_player = SimpleNamespace(
            set_context_segments=Mock(),
            seek=Mock(),
        )
        editor = SimpleNamespace(
            _queue_timer=_BadTimer(),
            _segment_queue=[{"text": "pending"}],
            _live_editor_preview_queue=[{"text": "temp"}],
            _live_editor_preview_segments=[{"text": "temp"}],
            _live_editor_preview_keys={("STT1", 0.0, 1.0, "temp")},
            text_edit=text_edit,
            timeline=timeline,
            video_player=video_player,
            _cached_segs=[{"text": "cached"}],
            _active_seg_start=2.0,
        )
        window = _SignalWindow(editor=editor)

        window._do_clear_editor()

        self.assertEqual(editor._segment_queue, [])
        self.assertEqual(editor._live_editor_preview_queue, [])
        self.assertEqual(editor._live_editor_preview_segments, [])
        self.assertEqual(editor._live_editor_preview_keys, set())
        text_edit.clear.assert_called_once()
        timeline.update_segments.assert_called_once_with([], 0.0, 3.0)
        timeline.set_playhead.assert_called_once_with(0.0)
        video_player.set_context_segments.assert_called_once_with([])
        video_player.seek.assert_called_once_with(0.0)
        self.assertEqual(editor._cached_segs, [])
        self.assertEqual(editor._active_seg_start, 0.0)

    def test_finalize_generation_complete_falls_back_to_current_stack_editor(self):
        finalizer = Mock()
        visible_editor = SimpleNamespace(_finalize_generation_from_backend=finalizer)
        window = _SignalWindow(editor=None)
        window.stack.currentWidget = Mock(return_value=visible_editor)

        window._do_finalize_generation_complete("stt_optimizer_threads_done")

        finalizer.assert_called_once_with(reason="stt_optimizer_threads_done")


if __name__ == "__main__":
    unittest.main()
