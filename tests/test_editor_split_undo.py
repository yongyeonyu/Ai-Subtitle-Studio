import unittest

from PyQt6.QtWidgets import QApplication

from ui.editor.editor_widget import EditorWidget
from ui.editor.subtitle_text_edit import SubtitleBlockData


class EditorSplitUndoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_editor(self) -> EditorWidget:
        editor = EditorWidget(
            video_name="sample.mp4",
            segments=[
                {"start": 1.0, "end": 3.0, "text": "오늘은 여기", "speaker": "00"},
            ],
            media_path="",
            defer_media_load=True,
        )
        editor.resize(1280, 720)
        editor.show()
        self.app.processEvents()
        editor.text_edit.setFocus()
        self.app.processEvents()
        return editor

    def _block_snapshot(self, editor: EditorWidget) -> list[tuple[str, float, str]]:
        doc = editor.text_edit.document()
        rows: list[tuple[str, float, str]] = []
        for idx in range(doc.blockCount()):
            block = doc.findBlockByNumber(idx)
            ud = block.userData()
            self.assertIsInstance(ud, SubtitleBlockData)
            rows.append((block.text(), float(ud.start_sec), str(ud.spk_id)))
        return rows

    def test_text_split_undo_and_redo_follow_snapshot_history_with_text_focus(self):
        editor = self._make_editor()
        try:
            before = self._block_snapshot(editor)
            self.assertEqual(before, [("오늘은 여기", 1.0, "00")])

            editor.split_segment_with_text(0, 2.0, 3)
            self.app.processEvents()

            after_split = self._block_snapshot(editor)
            self.assertEqual(after_split, [("오늘은", 1.0, "00"), ("여기", 2.0, "00")])
            self.assertTrue(editor.text_edit.hasFocus())
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_split")
            self.assertEqual(operation.get("metadata", {}).get("operation_family"), "caption_split")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertLessEqual(int(projection.get("max_active_segments", 1)), 1)

            editor._route_undo()
            self.app.processEvents()
            self.assertEqual(self._block_snapshot(editor), before)

            editor._route_redo()
            self.app.processEvents()
            self.assertEqual(self._block_snapshot(editor), after_split)
        finally:
            editor.close()

    def test_text_split_uses_legacy_fallback_when_live_preview_lane_exists(self):
        editor = self._make_editor()
        try:
            editor._live_stt_preview_segments = [
                {"start": 1.0, "end": 1.5, "text": "preview", "_live_stt_preview": True}
            ]

            editor.split_segment_with_text(0, 2.0, 3)
            self.app.processEvents()

            self.assertEqual(self._block_snapshot(editor), [("오늘은", 1.0, "00"), ("여기", 2.0, "00")])
            self.assertEqual(getattr(editor, "_last_nle_live_editor_operation", {}), {})
            editor._route_undo()
            self.app.processEvents()
            self.assertEqual(self._block_snapshot(editor), [("오늘은 여기", 1.0, "00")])
        finally:
            editor.close()

    def test_smart_split_undo_and_redo_follow_snapshot_history_with_text_focus(self):
        editor = self._make_editor()
        try:
            before = self._block_snapshot(editor)
            self.assertEqual(before, [("오늘은 여기", 1.0, "00")])

            editor._on_smart_split(0, 2.0, False)
            self.app.processEvents()

            after_split = self._block_snapshot(editor)
            self.assertEqual(after_split, [("오늘은 여기", 1.0, "00"), ("새자막", 2.0, "00")])
            self.assertTrue(editor.text_edit.hasFocus())

            editor._route_undo()
            self.app.processEvents()
            self.assertEqual(self._block_snapshot(editor), before)

            editor._route_redo()
            self.app.processEvents()
            self.assertEqual(self._block_snapshot(editor), after_split)
        finally:
            editor.close()
