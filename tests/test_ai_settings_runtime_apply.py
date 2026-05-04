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
            self.assertEqual([dialog.tabs.tabText(i) for i in range(dialog.tabs.count())], ["자막 검수", "중분류", "모델/API", "자동 설정"])
            label_texts = [label.text() for label in dialog.findChildren(QLabel)]
            self.assertFalse(any("자막 정확도 프리셋" in text for text in label_texts))
            self.assertFalse(any("오디오 프리셋" in text for text in label_texts))
            self.assertTrue(any("LoRA 교정:" in text for text in label_texts))
            self.assertTrue(any("적용 데이터:" in text for text in label_texts))
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
            self.assertTrue(any("Hugging Face Token:" in text for text in label_texts))
            self.assertIsNone(getattr(window, "sidebar_preset_panel", None))
            self.assertFalse(hasattr(window, "sidebar_stt_quality_combo"))
            self.assertFalse(hasattr(window, "sidebar_audio_preset_combo"))
            self.assertFalse(hasattr(window, "sidebar_auto_preset_btn"))
            audio_values = set(dialog.audio_map.values())
            self.assertIn("rnnoise", audio_values)
            self.assertIn("deepfilter", audio_values)
            self.assertIn("resemble_enhance", audio_values)
            self.assertIn("clearvoice", audio_values)
            self.assertNotIn("demucs", audio_values)
            self.assertIn("ten_vad", set(dialog.vad_map.values()))

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
            "audio_preset": "실외-마이크유",
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
            self.assertEqual(saved["audio_preset"], "실외-마이크유")
            self.assertEqual(saved["stt_quality_preset"], "precise")
            user_preset = saved["stt_quality_user_presets"]["precise"]["settings"]
            self.assertEqual(user_preset["selected_model"], "gemma3:4b")
            from core.audio.stt_quality_presets import apply_stt_quality_preset

            reloaded = apply_stt_quality_preset(saved, "precise")
            self.assertEqual(reloaded["selected_model"], "gemma3:4b")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_shortcuts_no_longer_include_advanced_settings(self):
        window = MainWindow()
        try:
            row = window._editor_shortcuts_row()
            texts = []
            for widget in row.findChildren(QWidget):
                getter = getattr(widget, "text", None)
                if callable(getter):
                    try:
                        texts.append(str(getter() or ""))
                    except RuntimeError:
                        pass
            self.assertNotIn("상세설정", texts)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_auto_preset_button_removed(self):
        window = MainWindow()
        try:
            window._unified_dashboard = True
            window._build_home_content()
            settings = {
                "audio_preset": "실내-마이크유",
                "stt_quality_preset": "balanced",
                "audio_preset_auto_decision": {
                    "audio_preset": "실내-마이크유",
                    "stt_quality_preset": "balanced",
                    "reason": "자동 판정 테스트",
                },
            }
            window._sync_sidebar_preset_panel(settings)
            self.assertIsNone(getattr(window, "sidebar_auto_preset_btn", None))
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
