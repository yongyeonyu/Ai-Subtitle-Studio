# Version: 03.01.34
# Phase: PHASE2
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton

from ui.dialogs.export_dialog import ExportDialog, _make_png


class ExportDialogControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_apply_button_is_merged_into_save_and_footer_heights_match(self):
        dialog = ExportDialog([{"start": 0.0, "end": 1.0, "text": "테스트 자막입니다"}], "sample.mp4")
        try:
            button_texts = [button.text() for button in dialog.findChildren(QPushButton)]
            self.assertNotIn("적용", button_texts)

            footer_names = [
                "exportSaveButton",
                "exportSaveDefaultButton",
                "exportLoadDefaultButton",
                "exportCancelButton",
                "exportOkButton",
                "exportRenderButton",
            ]
            heights = [dialog.findChild(QPushButton, name).height() for name in footer_names]
            self.assertEqual(len(set(heights)), 1)
        finally:
            dialog.close()

    def test_subtitle_png_wraps_long_text_to_output_width(self):
        style = {
            "font_family": "Arial",
            "font_size": 36,
            "res_scale": 1.0,
            "bold": True,
            "align": "center",
            "line_spacing": 4,
            "txt_rgba": (255, 255, 255, 255),
            "border_w": 0,
            "border_rgba": (255, 255, 255, 255),
            "shadow_rgba": None,
            "bg_rgba": None,
            "max_text_width_ratio": 0.45,
        }
        image = _make_png(None, "이 문장은 출력 영상 폭에 맞춰 자연스럽게 줄바꿈되어야 합니다", 420, 180, style)
        self.assertEqual(image.width(), 420)
        self.assertEqual(image.height(), 180)

    def test_save_button_applies_live_overlay_style(self):
        class DummyPlayer:
            def __init__(self):
                self.applied = None

            def apply_export_subtitle_style(self, style):
                self.applied = dict(style)

        dialog = ExportDialog([{"start": 0.0, "end": 1.0, "text": "테스트 자막입니다"}], "sample.mp4")
        player = DummyPlayer()
        dialog._video_player_ref = player
        try:
            with patch("ui.dialogs.export_dialog._save_es"):
                dialog._save()
            self.assertIsNotNone(player.applied)
            self.assertIn("res", player.applied)
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
