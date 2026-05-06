# Version: 03.09.11
# Phase: PHASE2
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget

from core.roughcut.models import (
    ChapterMetadata,
    EDLSegment,
    EditDecision,
    RoughCutMinorGroup,
    RoughCutResult,
    RoughCutSegment,
    RoughCutTitleSuggestion,
)
from ui.roughcut.roughcut_widget import RoughcutWidget
from ui.settings.settings_gap import GapSettingsDialog
from ui.settings.settings_advanced import AdvancedSettingsDialog
from ui.settings.settings_ai import SettingsDialog


class RoughcutUiV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_major_log_and_title_panels_render_without_removing_legacy_table(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="차량 외부 리뷰",
                        major_id="A",
                        tags=("외부", "타이어"),
                        minor_groups=(
                            RoughCutMinorGroup(
                                "A1",
                                "A",
                                "A1",
                                "외부 디자인",
                                0.0,
                                4.0,
                                chapter_ids=("chapter_0001",),
                                confidence=0.9,
                                status="confirmed",
                            ),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "외부 디자인", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                title_suggestions=(
                    RoughCutTitleSuggestion("title_001", "EV6 외부 디자인 총정리", 0.9, expected_reach="높음"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._populate_result()

            self.assertEqual(widget.main_tabs.count(), 2)
            self.assertGreaterEqual(widget.bottom_tabs.tabs.count(), 6)
            self.assertEqual(widget.table.rowCount(), 1)
            self.assertIn("chapter_0001", widget.major_panel._minor_buttons)
            self.assertEqual(widget.title_panel._suggestions[0].title, "EV6 외부 디자인 총정리")
            self.assertIn("분석 완료", widget.log_panel.status_lbl.text())
            self.assertIn("chapter_0001", widget.bottom_tabs.edl_text.toPlainText())

            widget.style_panel.set_style({"transition": "fade", "font_size": 50})
            widget._save_roughcut_export_style(widget.style_panel.style_payload())
            payload = widget._current_candidate_payload(widget._result)
            self.assertEqual(payload["roughcut_export_style"]["transition"], "fade")
            self.assertEqual(payload["roughcut_export_style"]["font_size"], 50)
        finally:
            widget.close()

    def test_settings_dialog_collects_roughcut_llm_without_plain_api_keys(self):
        dialog = SettingsDialog({
            "selected_model": "base-model",
            "selected_llm_provider": "ollama",
            "editor_roughcut_draft_enabled": True,
            "editor_roughcut_draft_prompt": "editor roughcut draft prompt",
            "llm_threads": 5,
            "subtitle_quality_enabled": True,
            "review_auto_correct_apply_threshold": 94,
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "openai",
            "roughcut_llm_model": "gpt-roughcut",
            "roughcut_llm_prompt": "roughcut prompt",
            "roughcut_llm_threads": 3,
        })
        try:
            self.assertEqual([dialog.tabs.tabText(i) for i in range(dialog.tabs.count())], ["자막 검수", "중분류", "모델/API", "자동 설정"])
            self.assertEqual(dialog.combo_stt_quality_preset.currentData(), "balanced")
            collected = dialog._collect_settings()
            self.assertTrue(collected["settings_simplified_ui_enabled"])
            self.assertTrue(collected["subtitle_bundle_autopilot_enabled"])
            self.assertEqual(collected["user_prompt"], "")
            self.assertFalse(hasattr(dialog, "chk_editor_roughcut_draft_enabled"))
            self.assertTrue(collected["editor_roughcut_draft_enabled"])
            self.assertEqual(collected["editor_roughcut_draft_prompt"], "")
            self.assertEqual(collected["llm_threads"], 5)
            self.assertTrue(collected["llm_threads_auto_enabled"])
            self.assertTrue(collected["llm_workers_auto_enabled"])
            self.assertFalse(collected["subtitle_quality_enabled"])
            self.assertEqual(collected["review_auto_correct_apply_threshold"], 94)
            self.assertFalse(collected["roughcut_llm_enabled"])
            self.assertFalse(collected["roughcut_llm_use_override"])
            self.assertEqual(collected["roughcut_llm_provider"], "none")
            self.assertEqual(collected["roughcut_llm_model"], "사용 안함")
            self.assertEqual(collected["roughcut_llm_prompt"], "")
            self.assertEqual(collected["roughcut_llm_threads"], 3)
            self.assertTrue(collected["roughcut_llm_threads_auto_enabled"])
            self.assertTrue(collected["roughcut_llm_rows_auto_enabled"])
            self.assertTrue(collected["roughcut_llm_rows_lora_enabled"])
            self.assertFalse(hasattr(dialog, "spin_roughcut_context_rows"))
            self.assertFalse(hasattr(dialog, "spin_roughcut_chunk_rows"))
            self.assertFalse(hasattr(dialog, "spin_roughcut_lookahead_rows"))
            self.assertNotIn("google_api_key", collected)
            self.assertNotIn("openai_api_key", collected)
        finally:
            dialog.close()

    def test_ai_tab_exposes_api_tokens_and_model_download_controls(self):
        dialog = SettingsDialog({})
        try:
            ai_tab = dialog.tabs.widget(2)
            self.assertIsNotNone(ai_tab.findChild(QLineEdit, "GoogleApiKeyInput"))
            self.assertIsNotNone(ai_tab.findChild(QLineEdit, "OpenAiApiKeyInput"))
            self.assertIsNotNone(ai_tab.findChild(QLineEdit, "HuggingFaceTokenInput"))
            self.assertIsNotNone(ai_tab.findChild(QWidget, "AiModelDownloadPanel"))

            labels = {label.text() for label in ai_tab.findChildren(QLabel)}
            self.assertIn("Google API Key:", labels)
            self.assertIn("OpenAI API Key:", labels)
            self.assertIn("Hugging Face Token:", labels)
            self.assertIn("모델 관리:", labels)
            self.assertIn("설치 가능한 LLM:", labels)
            self.assertIn("필수/STT 모델:", labels)
            self.assertNotIn("STT1 Whisper 모델:", labels)
            self.assertNotIn("자막 품질 검사:", labels)
            self.assertNotIn("텍스트 LoRA 보조:", labels)
        finally:
            dialog.close()

    def test_settings_dialog_hides_manual_llm_thread_control(self):
        dialog = SettingsDialog({"llm_workers": 6})
        try:
            self.assertFalse(hasattr(dialog, "spin_editor_llm_threads"))
            collected = dialog._collect_settings()
            self.assertTrue(collected["llm_threads_auto_enabled"])
        finally:
            dialog.close()

    def test_auto_settings_mode_uses_same_quality_presets_and_syncs_auto_scopes(self):
        with patch(
            "ui.settings.settings_ai.load_path_settings",
            return_value={
                "auto_start_mode": "quality",
                "icloud_stt_quality_preset": "fast",
                "nas_stt_quality_preset": "balanced",
            },
        ), patch("ui.settings.settings_ai.save_path_settings") as save_mock:
            dialog = SettingsDialog({})
            try:
                labels = [dialog.combo_auto_start_mode.itemText(i) for i in range(dialog.combo_auto_start_mode.count())]
                values = [dialog.combo_auto_start_mode.itemData(i) for i in range(dialog.combo_auto_start_mode.count())]
                self.assertEqual(labels, ["Fast", "Auto", "High"])
                self.assertEqual(values, ["fast", "balanced", "precise"])
                self.assertEqual(dialog.combo_auto_start_mode.currentData(), "precise")

                self.assertFalse(hasattr(dialog, "combo_simple_operation_mode"))
                collected = dialog._collect_settings()

                self.assertEqual(collected["auto_start_mode"], "balanced")
                self.assertEqual(collected["simple_operation_mode"], "auto")
                self.assertFalse(collected["operation_mode_choices_visible"])
                saved = save_mock.call_args.args[0]
                self.assertEqual(saved["auto_start_mode"], "balanced")
                self.assertEqual(saved["icloud_stt_quality_preset"], "balanced")
                self.assertEqual(saved["nas_stt_quality_preset"], "balanced")
            finally:
                dialog.close()

    def test_gap_dialog_hides_manual_sliders_behind_simple_mode(self):
        dialog = GapSettingsDialog({"settings_simplified_ui_enabled": True, "simple_operation_mode": "precise"})
        try:
            self.assertFalse(dialog.chk_show_manual_gap_settings.isChecked())
            self.assertTrue(dialog._manual_gap_scroll_area.isHidden())
            dialog._collect_data()
            self.assertTrue(dialog.result["subtitle_bundle_autopilot_enabled"])
            self.assertEqual(dialog.result["simple_operation_mode"], "high")
            self.assertFalse(dialog.result["operation_mode_choices_visible"])
        finally:
            dialog.close()

    def test_fast_preset_disables_editor_roughcut_draft_option(self):
        dialog = SettingsDialog({"editor_roughcut_draft_enabled": True, "stt_quality_preset": "fast"})
        try:
            self.assertFalse(hasattr(dialog, "chk_editor_roughcut_draft_enabled"))
            collected = dialog._collect_settings()
            self.assertTrue(collected["editor_roughcut_draft_enabled"])
            self.assertEqual(collected["editor_roughcut_draft_prompt"], "")
        finally:
            dialog.close()

    def test_advanced_settings_no_longer_shows_llm_prompt_or_quality_tabs(self):
        dialog = AdvancedSettingsDialog({})
        try:
            tab_names = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
            self.assertIn("시스템", tab_names)
            self.assertNotIn("Silero", tab_names)
            self.assertNotIn("DeepFilter", tab_names)
            self.assertNotIn("Whisper", tab_names)
            self.assertNotIn("ffmpeg", tab_names)
            self.assertNotIn("LLM 프롬프트", tab_names)
            self.assertNotIn("자막 품질", tab_names)
            self.assertFalse(hasattr(dialog, "edit_user_prompt"))
            self.assertFalse(hasattr(dialog, "chk_subtitle_quality_enabled"))
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
