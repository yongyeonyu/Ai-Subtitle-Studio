import unittest
from types import SimpleNamespace

from ui.editor.editor_lifecycle import EditorLifecycleMixin


class _TextEdit:
    def __init__(self):
        self.margin_updates = 0
        self.timestamp_refreshes = 0

    def update_margins(self):
        self.margin_updates += 1

    def refresh_timestamp_layer(self):
        self.timestamp_refreshes += 1


class _VideoPlayer:
    def __init__(self):
        self.provider = None
        self.display_time = None

    def set_subtitle_provider(self, provider):
        self.provider = provider

    def set_subtitle_display_time(self, sec):
        self.display_time = sec


class _Editor:
    def __init__(self):
        self._cached_segs = [{"start": 9.0, "end": 10.0, "text": "테스트"}]
        self.text_edit = _TextEdit()
        self.video_player = _VideoPlayer()
        self.timeline = SimpleNamespace(canvas=SimpleNamespace(playhead_sec=9.0))
        self.rebuilt_with = None
        self.timestamp_full = None
        self.video_context_refreshed = False

    def _rebuild_subtitle_memory_cache(self, segments=None):
        self.rebuilt_with = list(segments or [])
        return {}

    def _refresh_editor_timestamp_metadata(self, *, full=False):
        self.timestamp_full = full
        return 1

    def _refresh_video_subtitle_context(self):
        self.video_context_refreshed = True

    def _video_subtitle_context_for_player(self):
        return list(self._cached_segs)

    def _global_to_local_sec(self, sec):
        return float(sec)


class _Lifecycle(EditorLifecycleMixin):
    pass


class EditorSrtOpenRefreshTests(unittest.TestCase):
    def test_direct_srt_refresh_restores_timestamp_and_video_context(self):
        editor = _Editor()

        _Lifecycle()._refresh_opened_srt_editor_runtime(editor)

        self.assertEqual(editor.rebuilt_with, editor._cached_segs)
        self.assertTrue(editor.timestamp_full)
        self.assertEqual(editor.text_edit.margin_updates, 1)
        self.assertEqual(editor.text_edit.timestamp_refreshes, 1)
        self.assertTrue(editor.video_context_refreshed)
        self.assertIsNotNone(editor.video_player.provider)
        self.assertEqual(editor.video_player.provider(), editor._cached_segs)
        self.assertEqual(editor.video_player.display_time, 9.0)


if __name__ == "__main__":
    unittest.main()
