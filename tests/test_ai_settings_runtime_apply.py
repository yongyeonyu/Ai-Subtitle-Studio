# Version: 03.04.01
# Phase: PHASE2

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from ui.main.main_window import MainWindow
from ui.settings.settings_ai import SettingsDialog


class _DummyEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = {}
        self.selected_model = "old"
        self.engine_lbl = QLabel("", self)

    def _update_engine_label_text(self):
        self.engine_lbl.setText(
            "\n".join([
                f"[음성] : {self.settings.get('selected_audio_ai')}",
                f"[STT] : {self.settings.get('selected_whisper_model')}",
                f"[LLM] : {self.selected_model}",
            ])
        )


class AISettingsRuntimeApplyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_apply_ai_settings_updates_active_editor_and_sidebar(self):
        window = MainWindow()
        editor = _DummyEditor()
        window._active_editor = lambda: editor
        settings = {
            "selected_audio_ai": "deepfilter",
            "selected_vad": "silero",
            "selected_whisper_model": "mlx-community/whisper-large-v3-mlx",
            "selected_model": "gemma3:4b",
        }

        with patch("ui.home_ui.save_settings") as save_mock:
            window._apply_ai_settings(settings)

        save_mock.assert_called_once_with(settings)
        self.assertEqual(editor.settings["selected_whisper_model"], "mlx-community/whisper-large-v3-mlx")
        self.assertEqual(editor.selected_model, "gemma3:4b")
        self.assertIn("자막 LLM", window.sidebar_settings_label.text())
        self.assertIn("gemma3:4b", window.sidebar_settings_label.text())
        self.assertIn("whisper-large-v3", window.sidebar_settings_label.text())
        window.close()
        editor.close()

    def test_settings_dialog_save_notification_applies_to_editor_parent(self):
        editor = _DummyEditor()
        dialog = SettingsDialog({}, editor)
        dialog.result_settings = {
            "selected_audio_ai": "none",
            "selected_vad": "none",
            "selected_whisper_model": "large-v3",
            "selected_model": "사용 안함 (Whisper 단독 진행)",
        }

        dialog._notify_runtime_settings_applied()

        self.assertEqual(editor.settings["selected_whisper_model"], "large-v3")
        self.assertEqual(editor.selected_model, "사용 안함 (Whisper 단독 진행)")
        self.assertIn("[STT] : large-v3", editor.engine_lbl.text())
        dialog.close()
        editor.close()

    def test_presets_live_in_sidebar_not_ai_settings_dialog(self):
        window = MainWindow()
        try:
            window._unified_dashboard = True
            window._build_home_content()
            dialog = SettingsDialog({}, window)
            label_texts = [label.text() for label in dialog.findChildren(QLabel)]
            self.assertFalse(any("자막 정확도 프리셋" in text for text in label_texts))
            self.assertFalse(any("오디오 프리셋" in text for text in label_texts))
            widget_texts = []
            for widget in dialog.findChildren(QWidget):
                text_getter = getattr(widget, "text", None)
                if callable(text_getter):
                    try:
                        widget_texts.append(str(text_getter() or ""))
                    except RuntimeError:
                        pass
            self.assertNotIn("러프컷 분석에서 LLM 사용", widget_texts)
            self.assertFalse(any("API Key / 온도" in text for text in label_texts))
            self.assertIsNotNone(getattr(window, "sidebar_preset_panel", None))
            audio_values = set(dialog.audio_map.values())
            self.assertIn("rnnoise", audio_values)
            self.assertIn("deepfilter", audio_values)
            self.assertNotIn("demucs", audio_values)

            base = {
                "stt_quality_preset": "balanced",
                "audio_preset": "",
                "selected_whisper_model": "mlx-community/whisper-large-v3-mlx",
                "selected_model": "exaone3.5:2.4b",
                "selected_audio_ai": "deepfilter",
                "selected_vad": "silero",
            }
            with patch("ui.home_ui.load_settings", return_value=dict(base)), patch("ui.home_ui.save_settings") as save_mock:
                for i in range(window.sidebar_stt_quality_combo.count()):
                    if window.sidebar_stt_quality_combo.itemData(i) == "fast":
                        window.sidebar_stt_quality_combo.setCurrentIndex(i)
                        break
                self.assertTrue(save_mock.called)
                saved = save_mock.call_args.args[0]
                self.assertEqual(saved["stt_quality_preset"], "fast")
                self.assertIn("selected_whisper_model", saved)

            with patch("ui.home_ui.load_settings", return_value=dict(base)), patch("ui.home_ui.save_settings") as save_mock:
                for i in range(window.sidebar_audio_preset_combo.count()):
                    if window.sidebar_audio_preset_combo.itemData(i) == "야외":
                        window.sidebar_audio_preset_combo.setCurrentIndex(i)
                        break
                self.assertTrue(save_mock.called)
                saved = save_mock.call_args.args[0]
                self.assertEqual(saved["audio_preset"], "야외")
                self.assertEqual(saved["selected_audio_ai"], "deepfilter")
        finally:
            if "dialog" in locals():
                dialog.close()
                dialog.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_roughcut_llm_sidebar_has_no_inherit_mode(self):
        window = MainWindow()
        try:
            inherited_name, _ = window._roughcut_llm_name(
                {
                    "selected_model": "exaone3.5:7.8b",
                    "roughcut_llm_enabled": True,
                    "roughcut_llm_use_override": False,
                    "roughcut_llm_provider": "inherit",
                    "roughcut_llm_model": "inherit",
                },
                "exaone3.5:7.8b",
            )
            self.assertEqual(inherited_name, "미사용")

            base = {
                "roughcut_llm_enabled": True,
                "roughcut_llm_use_override": True,
                "roughcut_llm_provider": "ollama",
                "roughcut_llm_model": "exaone3.5:7.8b",
            }
            with patch("ui.home_ui.load_settings", return_value=dict(base)), patch("ui.home_ui.save_settings") as save_mock:
                window._apply_sidebar_model_selection({
                    "roughcut_llm_enabled": False,
                    "roughcut_llm_use_override": True,
                    "roughcut_llm_provider": "none",
                    "roughcut_llm_model": "사용 안함",
                })
            saved = save_mock.call_args.args[0]
            self.assertFalse(saved["roughcut_llm_enabled"])
            self.assertEqual(saved["roughcut_llm_provider"], "none")
            self.assertEqual(saved["roughcut_llm_model"], "사용 안함")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_model_selection_persists_to_user_settings(self):
        window = MainWindow()
        base = {
            "selected_audio_ai": "deepfilter",
            "selected_vad": "silero",
            "selected_whisper_model": "whisper-large-v3",
            "selected_whisper_model_secondary": "ghost613-turbo-korean-4bit",
            "selected_model": "exaone3.5:7.8b",
            "audio_preset": "야외",
            "stt_quality_preset": "precise",
        }
        try:
            with patch("ui.home_ui.load_settings", return_value=dict(base)), patch("ui.home_ui.save_settings") as save_mock:
                window._apply_sidebar_model_selection({
                    "selected_model": "gemma3:4b",
                    "selected_llm_provider": "ollama",
                })

            save_mock.assert_called_once()
            saved = save_mock.call_args.args[0]
            self.assertEqual(saved["selected_model"], "gemma3:4b")
            self.assertEqual(saved["selected_llm_provider"], "ollama")
            self.assertEqual(saved["audio_preset"], "야외")
            self.assertEqual(saved["stt_quality_preset"], "precise")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
