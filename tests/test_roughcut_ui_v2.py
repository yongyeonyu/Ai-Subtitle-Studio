# Version: 03.02.15
# Phase: PHASE2
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

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
            "user_prompt": "editor prompt",
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
            self.assertEqual([dialog.tabs.tabText(i) for i in range(dialog.tabs.count())], ["빠른 설정", "에디터 LLM", "러프컷 LLM", "AI"])
            collected = dialog._collect_settings()
            self.assertEqual(collected["user_prompt"], "editor prompt")
            self.assertEqual(dialog.chk_editor_roughcut_draft_enabled.text(), "자막 생성 후 러프컷 초안 생성")
            self.assertTrue(collected["editor_roughcut_draft_enabled"])
            self.assertEqual(collected["editor_roughcut_draft_prompt"], "editor roughcut draft prompt")
            self.assertEqual(collected["llm_threads"], 5)
            self.assertEqual(collected["llm_workers"], 5)
            self.assertTrue(collected["subtitle_quality_enabled"])
            self.assertEqual(collected["review_auto_correct_apply_threshold"], 94)
            self.assertTrue(collected["roughcut_llm_enabled"])
            self.assertTrue(collected["roughcut_llm_use_override"])
            self.assertEqual(collected["roughcut_llm_provider"], "openai")
            self.assertEqual(collected["roughcut_llm_model"], "gpt-roughcut")
            self.assertEqual(collected["roughcut_llm_prompt"], "roughcut prompt")
            self.assertEqual(collected["roughcut_llm_threads"], 3)
            self.assertNotIn("google_api_key", collected)
            self.assertNotIn("openai_api_key", collected)
        finally:
            dialog.close()

    def test_settings_dialog_reads_legacy_llm_workers_for_editor_threads(self):
        dialog = SettingsDialog({"llm_workers": 6})
        try:
            self.assertEqual(dialog.spin_editor_llm_threads.value(), 6)
        finally:
            dialog.close()

    def test_fast_preset_disables_editor_roughcut_draft_option(self):
        dialog = SettingsDialog({"editor_roughcut_draft_enabled": True, "stt_quality_preset": "fast"})
        try:
            self.assertFalse(dialog.chk_editor_roughcut_draft_enabled.isEnabled())
            self.assertFalse(dialog.chk_editor_roughcut_draft_enabled.isChecked())
            collected = dialog._collect_settings()
            self.assertFalse(collected["editor_roughcut_draft_enabled"])
        finally:
            dialog.close()

    def test_advanced_settings_no_longer_shows_llm_prompt_or_quality_tabs(self):
        dialog = AdvancedSettingsDialog({})
        try:
            tab_names = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
            self.assertIn("시스템", tab_names)
            self.assertNotIn("LLM 프롬프트", tab_names)
            self.assertNotIn("자막 품질", tab_names)
            self.assertFalse(hasattr(dialog, "edit_user_prompt"))
            self.assertFalse(hasattr(dialog, "chk_subtitle_quality_enabled"))
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
