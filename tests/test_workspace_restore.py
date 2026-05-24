import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ui.project.workspace_restore import WorkspaceMixin


class _VideoPlayer:
    def __init__(self):
        self.seek_calls = []

    def seek(self, sec):
        self.seek_calls.append(float(sec))


class _Timeline:
    def __init__(self):
        self.canvas = SimpleNamespace(playhead_sec=0.0)
        self.playhead_calls = []
        self.window_centers = []
        self._initial_open_view_token = "stale-fit-token"

    def set_playhead(self, sec):
        self.canvas.playhead_sec = float(sec)
        self.playhead_calls.append(float(sec))

    def preferred_edit_window_seconds(self):
        return 10.0

    def show_time_window_seconds(self, _seconds, *, center_sec=None):
        self.window_centers.append(center_sec)


class _Editor:
    def __init__(self):
        self.timeline = _Timeline()
        self.video_player = _VideoPlayer()
        self.sync_calls = []

    def _sync_after_manual_seek(self, sec):
        self.sync_calls.append(float(sec))


class _FailingTextEdit:
    def document(self):
        raise AssertionError("workspace restore must not trust stale block numbers when a playhead is restored")


class _Owner(WorkspaceMixin):
    pass


class WorkspaceRestoreTests(unittest.TestCase):
    def _schedule_restore(self, editor, workspace):
        callbacks = []
        with (
            patch("ui.project.workspace_restore.load_project", return_value={"workspace": dict(workspace)}),
            patch("ui.project.workspace_restore.QTimer.singleShot", side_effect=lambda _delay, cb: callbacks.append(cb)),
        ):
            _Owner()._restore_workspace(editor, "/tmp/example.aissproj")
        self.assertEqual(len(callbacks), 1)
        return callbacks[0]

    def test_deferred_workspace_restore_applies_saved_playhead_when_untouched(self):
        editor = _Editor()
        callback = self._schedule_restore(editor, {"last_playhead": 1444.226})

        callback()

        self.assertEqual(editor.video_player.seek_calls, [1444.226])
        self.assertEqual(editor.timeline.playhead_calls, [1444.226])
        self.assertEqual(editor.timeline.window_centers, [1444.226])
        self.assertEqual(editor.sync_calls, [1444.226])
        self.assertNotEqual(editor.timeline._initial_open_view_token, "stale-fit-token")

    def test_deferred_workspace_restore_does_not_override_recent_seek(self):
        editor = _Editor()
        callback = self._schedule_restore(editor, {"last_playhead": 1444.226})
        editor.timeline.canvas.playhead_sec = 977.91

        callback()

        self.assertEqual(editor.video_player.seek_calls, [])
        self.assertEqual(editor.timeline.playhead_calls, [])
        self.assertEqual(editor.timeline.window_centers, [977.91])
        self.assertEqual(editor.sync_calls, [977.91])

    def test_deferred_workspace_restore_reapplies_external_seek_after_open_race(self):
        editor = _Editor()
        editor._external_playhead_seek_revision = 1
        editor._external_playhead_seek_sec = 977.91
        editor._external_playhead_seek_sync_video = True
        callback = self._schedule_restore(editor, {"last_playhead": 1444.226})
        editor.timeline.canvas.playhead_sec = 0.0

        callback()

        self.assertEqual(editor.video_player.seek_calls, [977.91])
        self.assertEqual(editor.timeline.playhead_calls, [977.91])
        self.assertEqual(editor.timeline.window_centers, [977.91])
        self.assertEqual(editor.sync_calls, [977.91])

    def test_deferred_workspace_restore_uses_time_sync_not_stale_cursor_block(self):
        editor = _Editor()
        editor.text_edit = _FailingTextEdit()
        callback = self._schedule_restore(
            editor,
            {
                "last_playhead": 170.90406666666667,
                "last_cursor_block": 70,
            },
        )

        callback()

        self.assertEqual(editor.video_player.seek_calls, [170.90406666666667])
        self.assertEqual(editor.timeline.playhead_calls, [170.90406666666667])
        self.assertEqual(editor.sync_calls, [170.90406666666667])


if __name__ == "__main__":
    unittest.main()
