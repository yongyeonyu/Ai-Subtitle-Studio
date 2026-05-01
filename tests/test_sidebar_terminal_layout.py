# Version: 03.02.14
# Phase: PHASE2
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTableWidgetItem, QWidget

from ui.main.main_window import MainWindow


class SidebarTerminalLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_terminal_log_lives_in_sidebar_and_menu_toggles_sidebar(self):
        window = MainWindow()
        try:
            window.show_home()
            window.show_home()
            self.assertIs(window.log_text, window.sidebar_terminal_panel.log_text)
            self.assertIs(window.sidebar_terminal_panel.parent(), window.home_page)
            self.assertIsNotNone(getattr(window, "sidebar_queue_panel", None))
            self.assertTrue(window.bottom_work_panel.isHidden())

            window._apply_log_visible(False, persist=False)
            self.assertTrue(window.home_page.isHidden())
            self.assertTrue(window.sidebar_terminal_panel.isHidden())
            self.assertTrue(window.bottom_work_panel.isHidden())

            window._apply_log_visible(True, persist=False)
            self.assertFalse(window.home_page.isHidden())
            self.assertFalse(window.sidebar_terminal_panel.isHidden())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_terminal_log_has_memory_cap(self):
        window = MainWindow()
        try:
            for i in range(900):
                window.append_log(f"line {i}")
            self.assertLessEqual(window.log_text.document().blockCount(), 800)
            self.assertIn("line 899", window.log_text.toPlainText())
            self.assertNotIn("line 0\n", window.log_text.toPlainText())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_global_menu_uses_sidebar_button_label(self):
        window = MainWindow()
        try:
            self.assertEqual(window.global_menu_bar.btn_log.text(), "사이드바")
            self.assertIs(window.global_menu_bar.parent(), window.right_workspace)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_project_info_button_matches_global_ai_button_height(self):
        window = MainWindow()
        try:
            window._unified_dashboard = True
            window._build_home_content()
            self.app.processEvents()

            project_info_btn = getattr(window, "_project_info_button_card", None)
            ai_btn = window.global_menu_bar._tool_buttons[0]
            self.assertIsNotNone(project_info_btn)
            self.assertEqual(project_info_btn.height(), ai_btn.height())
            self.assertEqual(project_info_btn.minimumHeight(), ai_btn.minimumHeight())
            self.assertEqual(project_info_btn.maximumHeight(), ai_btn.maximumHeight())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_main_panel_borders_have_single_line_and_three_pixel_gaps(self):
        window = MainWindow()
        try:
            root_layout = window.centralWidget().layout()
            margins = root_layout.contentsMargins()
            self.assertEqual((margins.left(), margins.top(), margins.right(), margins.bottom()), (3, 3, 3, 3))
            self.assertEqual(root_layout.spacing(), 3)
            self.assertEqual(window.workspace_splitter.handleWidth(), 3)
            self.assertEqual(window.right_layout.spacing(), 3)
            for widget in (
                window.home_page,
                window.bottom_work_panel,
                window.global_menu_bar,
            ):
                self.assertIn("border: 1px", widget.styleSheet())
            self.assertIn("border: none", window.stack.styleSheet())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_recent_work_button_removed_and_queue_panel_sits_under_auto_cards(self):
        window = MainWindow()
        try:
            window._unified_dashboard = True
            window._build_home_content()
            self.app.processEvents()

            labels = window.home_page.findChildren(QWidget)
            visible_texts = []
            for obj in labels:
                text_getter = getattr(obj, "text", None)
                if callable(text_getter):
                    try:
                        visible_texts.append(str(text_getter() or ""))
                    except RuntimeError:
                        pass
            self.assertNotIn("최근 작업", visible_texts)
            self.assertNotIn("Dashboard", visible_texts)
            self.assertIn("AI Subtitle Studio", window.saved_status_label.text())
            self.assertNotIn("자막:", window.saved_status_label.text())
            self.assertNotIn("러프컷:", window.saved_status_label.text())
            queue_panel = getattr(window, "sidebar_queue_panel", None)
            self.assertIsNotNone(queue_panel)
            self.assertIsNotNone(queue_panel.parentWidget())
            self.assertGreaterEqual(queue_panel.minimumHeight(), 134)
            preset_panel = getattr(window, "sidebar_preset_panel", None)
            self.assertIsNotNone(preset_panel)
            self.assertLessEqual(window.sidebar_terminal_panel.maximumHeight(), 132)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_pipeline_model_column_uses_terminal_style_font(self):
        window = MainWindow()
        try:
            html = window._pipeline_info_html(
                {
                    "selected_audio_ai": "deepfilter",
                    "selected_whisper_model": "whisper-large-v3",
                    "selected_stt2_model": "ghost613-turbo-korean-4bit",
                    "selected_vad": "silero",
                    "selected_model": "exaone3.5:7.8b",
                    "selected_roughcut_llm_model": "사용 안함",
                }
            )
            self.assertIn("font-family:Menlo, Monaco, Consolas, monospace", html)
            self.assertIn("font-weight:400", html)
            self.assertIn("model:stt1", html)
            self.assertNotIn("text-decoration:none; font-weight:800", html)

            window._pipeline_current_stage_keys = lambda _settings: {"stt1"}
            window._pipeline_completed_stage_keys = lambda _settings, _current: {"preprocess", "audio"}
            progress_html = window._pipeline_info_html(
                {
                    "selected_audio_ai": "deepfilter",
                    "selected_whisper_model": "whisper-large-v3",
                    "selected_stt2_model": "ghost613-turbo-korean-4bit",
                    "selected_vad": "silero",
                    "selected_model": "exaone3.5:7.8b",
                    "selected_roughcut_llm_model": "사용 안함",
                }
            )
            self.assertIn("color:#00D46A; padding:1px 10px 1px 0; font-weight:800;", progress_html)
            self.assertIn("color:#FFD60A; padding:1px 10px 1px 0; font-weight:800;", progress_html)
            self.assertIn("style='color:#00D46A; text-decoration:none;", progress_html)
            self.assertIn("style='color:#FFD60A; text-decoration:none;", progress_html)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_pipeline_roughcut_completion_marks_final_stage_green(self):
        window = MainWindow()
        try:
            editor = type("Editor", (), {})()
            editor._roughcut_draft_status = "done"
            editor._last_roughcut_draft_major_count = 5
            editor.sm = type("State", (), {"state": "ST_SAVED"})()
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: False
            html = window._pipeline_info_html(
                {
                    "selected_audio_ai": "deepfilter",
                    "selected_whisper_model": "whisper-large-v3",
                    "stt_ensemble_enabled": True,
                    "selected_whisper_model_secondary": "ghost613-turbo-korean-4bit",
                    "selected_vad": "silero",
                    "selected_model": "gemma4:e4b",
                    "roughcut_llm_enabled": True,
                    "roughcut_llm_model": "exaone3.5:7.8b",
                }
            )

            self.assertIn(">7</td>", html)
            self.assertIn("러프컷 LLM", html)
            self.assertIn("style='color:#00D46A; text-decoration:none;", html)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_queue_status_is_plain_and_eta_header_is_full_text(self):
        window = MainWindow()
        try:
            window.queue_table.setRowCount(1)
            window.queue_table.setItem(0, 0, QTableWidgetItem("✅ 자막 생성 완료"))
            window.queue_table.setItem(0, 1, QTableWidgetItem("DJI_20260217224203_0075_D.MP4"))
            window.queue_table.setItem(0, 4, QTableWidgetItem("01:37 / ?"))
            items = window._sidebar_queue_items()
            self.assertEqual(items[0]["status"], "자막 생성 완료")
            self.assertNotIn("✅", items[0]["status"])

            panel = window._ensure_sidebar_queue_panel()
            panel.set_queue("큐 리스트 : (1/1) - 100% 완료", items)
            self.assertEqual(panel._table.horizontalHeaderItem(2).text(), "예상시간")
            self.assertEqual(panel._table.item(0, 0).text(), "자막 생성 완료")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_roughcut_llm_menu_keeps_only_capable_models(self):
        window = MainWindow()
        try:
            window._llm_model_items = lambda: [
                {
                    "name": "exaone3.5:2.4b",
                    "display_name": "exaone3.5:2.4b",
                    "details": {"provider": "ollama", "parameter_size": "2.4B"},
                },
                {
                    "name": "exaone3.5:7.8b",
                    "display_name": "exaone3.5:7.8b",
                    "details": {"provider": "ollama", "parameter_size": "7.8B"},
                },
                {
                    "name": "gemma2:9b",
                    "display_name": "gemma2:9b",
                    "details": {"provider": "ollama", "parameter_size": "9B"},
                },
                {
                    "name": "llama3.2:1b",
                    "display_name": "llama3.2:1b",
                    "details": {"provider": "ollama", "parameter_size": "1B"},
                },
                {
                    "name": "mistral:latest",
                    "display_name": "mistral:latest",
                    "details": {"provider": "ollama"},
                },
                {
                    "name": "Gemini 2.5 Flash (API)",
                    "display_name": "Gemini 2.5 Flash [무료/제한 API]",
                    "details": {"provider": "google", "parameter_size": "Cloud"},
                },
                {
                    "name": "Gemini 2.5 Pro (API)",
                    "display_name": "Gemini 2.5 Pro [유료/API 고품질]",
                    "details": {"provider": "google", "parameter_size": "Cloud"},
                },
                {
                    "name": "OpenAI GPT-5 Nano [유료/API 저비용]",
                    "display_name": "OpenAI GPT-5 Nano [유료/API 저비용]",
                    "details": {"provider": "openai", "parameter_size": "Cloud"},
                },
                {
                    "name": "OpenAI GPT-5.2 [유료/API 고품질]",
                    "display_name": "OpenAI GPT-5.2 [유료/API 고품질]",
                    "details": {"provider": "openai", "parameter_size": "Cloud"},
                },
            ]

            names = [item["name"] for item in window._roughcut_llm_items()]
            self.assertIn("exaone3.5:7.8b", names)
            self.assertIn("gemma2:9b", names)
            self.assertIn("mistral:latest", names)
            self.assertIn("Gemini 2.5 Pro (API)", names)
            self.assertIn("OpenAI GPT-5.2 [유료/API 고품질]", names)
            self.assertNotIn("exaone3.5:2.4b", names)
            self.assertNotIn("llama3.2:1b", names)
            self.assertNotIn("Gemini 2.5 Flash (API)", names)
            self.assertNotIn("OpenAI GPT-5 Nano [유료/API 저비용]", names)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_global_menu_stays_at_workspace_bottom_in_editor(self):
        from ui.editor.editor_widget import EditorWidget

        window = MainWindow()
        editor = None
        try:
            editor = EditorWidget(video_name="sample.mp4", segments=[], media_path="", parent=window)
            window.stack.addWidget(editor)
            window._attach_global_menu_to_editor(editor)
            self.app.processEvents()

            self.assertIs(window.global_menu_bar.parent(), window.right_workspace)
            self.assertEqual(window.right_layout.indexOf(window.global_menu_bar), window.right_layout.count() - 1)
            self.assertEqual(editor.external_menu_host.height(), 0)
            self.assertTrue(editor.external_menu_host.isHidden())
        finally:
            if editor is not None:
                editor.close()
                editor.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_global_menu_stays_below_roughcut_bottom_panel(self):
        window = MainWindow()
        roughcut_bottom = QWidget()
        try:
            window._set_roughcut_bottom_widget(roughcut_bottom)
            window._dock_global_menu_to_workspace()
            self.app.processEvents()

            self.assertIs(window.global_menu_bar.parent(), window.right_workspace)
            self.assertEqual(window.right_layout.indexOf(window.global_menu_bar), window.right_layout.count() - 1)
            self.assertLess(
                window.right_layout.indexOf(window.bottom_work_panel),
                window.right_layout.indexOf(window.global_menu_bar),
            )
            self.assertFalse(window.bottom_work_panel.isHidden())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_project_info_button_stays_at_sidebar_bottom_and_opens_overlay(self):
        window = MainWindow()
        try:
            window._unified_dashboard = True
            window.resize(460, 760)
            window._build_home_content()
            window.show()
            self.app.processEvents()

            button = getattr(window, "_project_info_button_card", None)
            terminal = getattr(window, "sidebar_terminal_panel", None)
            self.assertIsNotNone(button)
            self.assertIsNotNone(terminal)
            self.assertGreater(button.y(), terminal.y())
            self.assertEqual(button.height(), 44)

            window._toggle_project_info_card()
            self.app.processEvents()
            overlay = getattr(window, "_project_info_overlay", None)
            self.assertIsNotNone(overlay)
            self.assertLess(overlay.y(), button.y())

            window._toggle_project_info_card()
            self.app.processEvents()
            self.assertIsNone(getattr(window, "_project_info_overlay", None))
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_global_menu_buttons_match_project_info_button_height(self):
        from ui.menu_bar import MENU_BUTTON_HEIGHT

        window = MainWindow()
        try:
            window._unified_dashboard = True
            window._build_home_content()
            self.app.processEvents()

            button = getattr(window, "_project_info_button_card", None)
            self.assertIsNotNone(button)
            self.assertEqual(button.height(), MENU_BUTTON_HEIGHT)
            for menu_button in window.global_menu_bar._tool_buttons:
                self.assertEqual(menu_button.height(), MENU_BUTTON_HEIGHT)
                self.assertLessEqual(menu_button.iconSize().height(), 18)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
