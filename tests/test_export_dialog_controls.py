# Version: 03.01.34
# Phase: PHASE2
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton, QRadioButton, QWidget

from ui.dialogs.export_dialog import (
    ExportDialog,
    OUTPUT_MODE_SUBTITLE_ONLY,
    OUTPUT_MODE_SUBTITLE_WITH_VIDEO,
    _make_png,
)


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

    def test_output_mode_radios_default_to_subtitle_only_and_are_exclusive(self):
        dialog = ExportDialog([{"start": 0.0, "end": 1.0, "text": "테스트 자막입니다"}], "sample.mp4")
        try:
            subtitle_only = dialog.findChild(QRadioButton, "exportSubtitleOnlyRadio")
            subtitle_video = dialog.findChild(QRadioButton, "exportSubtitleWithVideoRadio")

            self.assertTrue(subtitle_only.isChecked())
            self.assertFalse(subtitle_video.isChecked())
            self.assertEqual(dialog.output_mode(), OUTPUT_MODE_SUBTITLE_ONLY)

            subtitle_video.setChecked(True)
            self.assertFalse(subtitle_only.isChecked())
            self.assertTrue(subtitle_video.isChecked())
            self.assertEqual(dialog.output_mode(), OUTPUT_MODE_SUBTITLE_WITH_VIDEO)
        finally:
            dialog.close()

    def test_output_mode_is_collected_and_restored(self):
        dialog = ExportDialog([{"start": 0.0, "end": 1.0, "text": "테스트 자막입니다"}], "sample.mp4")
        try:
            dialog.set_output_mode(OUTPUT_MODE_SUBTITLE_WITH_VIDEO)
            collected = dialog._collect()
            self.assertEqual(collected["output_mode"], OUTPUT_MODE_SUBTITLE_WITH_VIDEO)

            dialog.set_output_mode(OUTPUT_MODE_SUBTITLE_ONLY)
            self.assertTrue(dialog._apply_settings({"output_mode": OUTPUT_MODE_SUBTITLE_WITH_VIDEO}))
            self.assertEqual(dialog.output_mode(), OUTPUT_MODE_SUBTITLE_WITH_VIDEO)
        finally:
            dialog.close()

    def test_text_height_control_is_collected_and_restored(self):
        dialog = ExportDialog([{"start": 0.0, "end": 1.0, "text": "테스트 자막입니다"}], "sample.mp4")
        try:
            text_height = dialog.findChild(QComboBox, "exportTextHeightCombo")
            self.assertIsNotNone(text_height)

            text_height.setCurrentText("20")
            collected = dialog._collect()
            self.assertEqual(collected["text_height"], "20")
            self.assertEqual(dialog._style(effect_scale=2.0)["vertical_offset"], 40)

            self.assertTrue(dialog._apply_settings({"text_height": "-15"}))
            self.assertEqual(text_height.currentText(), "-15")
        finally:
            dialog.close()

    def test_text_height_menu_entry_opens_text_tab(self):
        dialog = ExportDialog(
            [{"start": 0.0, "end": 1.0, "text": "테스트 자막입니다"}],
            "sample.mp4",
            initial_tab="text_height",
        )
        try:
            self.assertEqual(dialog.tabs.tabText(dialog.tabs.currentIndex()), "텍스트")
        finally:
            dialog.close()

    def test_render_uses_overlay_worker_when_video_mode_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sample.mp4")
            with open(media_path, "wb") as handle:
                handle.write(b"")
            parent = QWidget()
            parent.media_path = media_path
            dialog = ExportDialog([{"start": 0.0, "end": 1.0, "text": "테스트 자막입니다"}], os.path.basename(media_path), parent)
            dialog.set_output_mode(OUTPUT_MODE_SUBTITLE_WITH_VIDEO)

            class DummyWorker:
                def __init__(self, payload):
                    self.payload = payload
                    self.done = SimpleNamespace(connect=lambda *_args, **_kwargs: None)
                    self.started = False

                def start(self):
                    self.started = True

            workers = []

            def make_worker(payload):
                worker = DummyWorker(payload)
                workers.append(worker)
                return worker

            try:
                with patch("ui.dialogs.export_dialog._parse_srt", return_value=[{"start": 0.0, "end": 1.0, "text": "테스트 자막입니다"}]), \
                     patch("ui.dialogs.export_dialog._OverlayRenderWorker", side_effect=make_worker), \
                     patch("ui.dialogs.export_dialog.QProgressDialog"), \
                     patch("ui.dialogs.export_dialog._save_es"):
                    dialog._render()

                self.assertEqual(len(workers), 1)
                self.assertTrue(workers[0].started)
                self.assertEqual(workers[0].payload["media_path"], media_path)
                self.assertTrue(workers[0].payload["output_path"].endswith("_자막입힘.mp4"))
                try:
                    os.remove(workers[0].payload["srt_path"])
                except OSError:
                    pass
            finally:
                dialog.close()
                parent.close()


if __name__ == "__main__":
    unittest.main()
