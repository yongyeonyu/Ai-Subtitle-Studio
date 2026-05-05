import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ui.editor.editor_actions import EditorActionsMixin


class _Editor(EditorActionsMixin):
    def __init__(self, outputs):
        self._last_saved_srt_outputs = list(outputs)
        self._main = SimpleNamespace(_auto_export_subtitle_video=False)

    def window(self):
        return self._main


class EditorAutoExportTests(unittest.TestCase):
    def test_manual_srt_save_always_exports_subtitle_video(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            srt_path = os.path.join(tmp, "clip.srt")
            media_path = os.path.join(tmp, "clip.mp4")
            with open(srt_path, "w", encoding="utf-8") as handle:
                handle.write("1\n00:00:00,000 --> 00:00:01,000\nhello\n")
            with open(media_path, "wb"):
                pass
            editor = _Editor([(srt_path, media_path)])

            with (
                patch("ui.dialogs.export_dialog._load_es", return_value={"icloud": False}),
                patch(
                    "core.renderer.render_subtitle_mov",
                    side_effect=lambda *args, **_kwargs: calls.append(args) or True,
                ),
            ):
                editor._auto_export_saved_subtitle_videos()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], srt_path)
        self.assertEqual(calls[0][1], media_path)


if __name__ == "__main__":
    unittest.main()
