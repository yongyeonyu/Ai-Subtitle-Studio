# Version: 03.09.10
# Phase: PHASE2
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QSizePolicy, QTableWidgetItem, QWidget

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
            self.assertEqual(queue_panel.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Expanding)
            self.assertGreater(queue_panel.maximumHeight(), 10000)
            left_layout = queue_panel.parentWidget().layout()
            self.assertEqual(left_layout.stretch(left_layout.indexOf(queue_panel)), 3)
            nav_buttons = []
            for label in window.home_page.findChildren(QLabel):
                if label.text() in {"홈", "에디터", "러프컷", "숏폼"}:
                    parent = label.parentWidget()
                    if parent is not None and parent.objectName() == "MenuButton":
                        nav_buttons.append(parent)
            self.assertEqual(len(nav_buttons), 4)
            self.assertTrue(all(btn.maximumHeight() == 36 for btn in nav_buttons))
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

    def test_pipeline_table_stays_idle_before_first_stage_log(self):
        window = MainWindow()
        try:
            settings = {
                "selected_audio_ai": "clearvoice",
                "selected_whisper_model": "whisper-large-v3",
                "stt_ensemble_enabled": True,
                "selected_whisper_model_secondary": "ghost613-turbo-korean-4bit",
                "selected_vad": "silero",
                "selected_model": "gemma4:e4b",
                "roughcut_llm_enabled": True,
                "roughcut_llm_model": "exaone3.5:7.8b",
            }
            window.backend = type("Backend", (), {"_active": True})()
            window.queue_header_lbl.setText("큐 리스트 : (0/1) - 0% 완료")
            window.queue_table.setRowCount(1)
            window.queue_table.setItem(0, 0, QTableWidgetItem("대기"))
            window.queue_table.setItem(0, 2, QTableWidgetItem(""))
            window.queue_table.setItem(0, 4, QTableWidgetItem("?"))

            current = window._pipeline_current_stage_keys(settings)
            completed = window._pipeline_completed_stage_keys(settings, current)

            self.assertEqual(current, set())
            self.assertEqual(completed, set())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_saved_editor_without_generation_log_does_not_mark_pipeline_done(self):
        window = MainWindow()
        try:
            editor = type("Editor", (), {})()
            editor._roughcut_draft_status = "idle"
            editor._last_roughcut_draft_major_count = None
            editor.sm = type("State", (), {"state": "ST_SAVED"})()
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: False
            settings = {
                "selected_audio_ai": "none",
                "selected_whisper_model": "whisper-large-v3",
                "stt_ensemble_enabled": False,
                "selected_vad": "silero",
                "selected_model": "gemma4:e4b",
                "roughcut_llm_enabled": False,
            }

            current = window._pipeline_current_stage_keys(settings)
            completed = window._pipeline_completed_stage_keys(settings, current)

            self.assertEqual(current, set())
            self.assertEqual(completed, set())
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
            self.assertEqual(items[0]["order"], "1")
            self.assertEqual(items[0]["status"], "자막 생성 완료")
            self.assertTrue(items[0]["done"])
            self.assertNotIn("✅", items[0]["status"])

            panel = window._ensure_sidebar_queue_panel()
            panel.set_queue("큐 리스트 : (1/1) - 100% 완료", items)
            self.assertEqual(panel._table.horizontalHeaderItem(0).text(), "순서")
            self.assertEqual(panel._table.horizontalHeaderItem(2).text(), "상태")
            self.assertEqual(panel._table.horizontalHeaderItem(3).text(), "예상시간")
            self.assertEqual(panel._table.item(0, 0).text(), "1")
            self.assertEqual(panel._table.item(0, 2).text(), "완료")
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

    def test_home_stops_running_backend_and_runtime_processes(self):
        window = MainWindow()

        class _Editor(QWidget):
            def __init__(self, parent):
                super().__init__(parent)
                self.sm = SimpleNamespace(is_locked=True, state="ST_PROC")
                self._is_ai_processing = True
                self._roughcut_draft_timer = QTimer(self)
                self._roughcut_draft_timer.start(10_000)
                self._roughcut_draft_pending = True
                self._roughcut_draft_generation = 3
                self.statuses = []
                self.stopped = False

            def _stop_pipeline(self):
                self.stopped = True
                self._is_ai_processing = False
                self.sm.is_locked = False

            def _set_roughcut_draft_status(self, status):
                self.statuses.append(status)

        class _Backend:
            def __init__(self):
                self._active = True
                self.stopped = False

            def stop(self):
                self.stopped = True
                self._active = False

        class _ImmediateThread:
            def __init__(self, target, *args, **kwargs):
                self._target = target

            def start(self):
                self._target()

        editor = _Editor(window)
        backend = _Backend()
        try:
            window._editor_widget = editor
            window.backend = backend

            with mock.patch("ui.main.main_window.threading.Thread", _ImmediateThread), \
                 mock.patch("core.platform_compat.cleanup_app_runtime_processes", return_value={
                     "ollama_models": 1,
                     "ollama_processes": 1,
                     "child_processes": 1,
                     "legacy_preview_ffmpeg": 0,
                 }) as cleanup_runtime:
                window.show_home()

            self.assertTrue(editor.stopped)
            self.assertFalse(editor._roughcut_draft_timer.isActive())
            self.assertFalse(editor._roughcut_draft_pending)
            self.assertEqual(editor._roughcut_draft_generation, 4)
            self.assertIn("idle", editor.statuses)
            self.assertTrue(backend.stopped)
            cleanup_runtime.assert_called()
        finally:
            window.backend = None
            window._editor_widget = None
            editor.close()
            editor.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_editor_mode_releases_idle_ai_models_without_stopping_backend(self):
        window = MainWindow()

        class _Editor(QWidget):
            def __init__(self, parent):
                super().__init__(parent)
                self.sm = SimpleNamespace(is_locked=False, state="ST_COMP")
                self._is_ai_processing = False
                self._roughcut_draft_timer = QTimer(self)
                self._roughcut_draft_timer.start(10_000)
                self._roughcut_draft_pending = True
                self._roughcut_draft_generation = 7
                self.statuses = []

            def _set_roughcut_draft_status(self, status):
                self.statuses.append(status)

        class _Processor:
            def __init__(self):
                self.stopped = False

            def stop_transcribe(self):
                self.stopped = True

        class _Backend:
            def __init__(self):
                self._active = False
                self.stopped = False
                self.video_processor = _Processor()

            def stop(self):
                self.stopped = True

        class _ImmediateThread:
            def __init__(self, target, *args, **kwargs):
                self._target = target

            def start(self):
                self._target()

        editor = _Editor(window)
        backend = _Backend()
        stopped_models = []
        try:
            window._editor_widget = editor
            window.backend = backend

            with mock.patch("ui.main.main_window.threading.Thread", _ImmediateThread), \
                 mock.patch("ui.main.main_window.load_settings", return_value={"selected_model": "gemma4:e4b"}), \
                 mock.patch("core.llm.ollama_provider.stop_local_llm_models", side_effect=lambda models, logger=None, **_kwargs: stopped_models.extend(models)):
                window._release_ai_models_for_editor_mode()

            self.assertFalse(backend.stopped)
            self.assertTrue(backend.video_processor.stopped)
            self.assertFalse(editor._roughcut_draft_timer.isActive())
            self.assertFalse(editor._roughcut_draft_pending)
            self.assertEqual(editor._roughcut_draft_generation, 8)
            self.assertIn("idle", editor.statuses)
            self.assertIn("gemma4:e4b", stopped_models)
        finally:
            window.backend = None
            editor.close()
            editor.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_editor_mode_does_not_release_models_while_backend_active(self):
        window = MainWindow()

        class _Processor:
            def __init__(self):
                self.stopped = False

            def stop_transcribe(self):
                self.stopped = True

        editor = QWidget(window)
        editor.sm = SimpleNamespace(is_locked=False, state="ST_IDLE")
        processor = _Processor()
        window._editor_widget = editor
        window.backend = SimpleNamespace(_active=True, video_processor=processor)
        try:
            with mock.patch("core.llm.ollama_provider.stop_local_llm_models") as stop_llm:
                window._release_ai_models_for_editor_mode()

            self.assertFalse(processor.stopped)
            stop_llm.assert_not_called()
        finally:
            window.backend = None
            editor.close()
            editor.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_editor_mode_does_not_release_models_while_processing(self):
        window = MainWindow()

        class _Processor:
            def __init__(self):
                self.stopped = False

            def stop_transcribe(self):
                self.stopped = True

        editor = QWidget(window)
        editor.sm = SimpleNamespace(is_locked=True, state="ST_PROC")
        editor._is_ai_processing = True
        processor = _Processor()
        window._editor_widget = editor
        window.backend = SimpleNamespace(video_processor=processor)
        try:
            with mock.patch("core.llm.ollama_provider.stop_local_llm_models") as stop_llm:
                window._release_ai_models_for_editor_mode()

            self.assertFalse(processor.stopped)
            stop_llm.assert_not_called()
        finally:
            window.backend = None
            editor.close()
            editor.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_home_cleanup_stops_threads_workers_and_runtime_processes(self):
        window = MainWindow()

        class _Video:
            def __init__(self):
                self._ui_timer = QTimer()
                self._ui_timer.start(10_000)
                self.paused = False
                self.media_player = mock.Mock()
                self.vocal_player = mock.Mock()

            def pause_video(self):
                self.paused = True

        class _Timeline:
            def __init__(self):
                self.stopped = False

            def stop_waveform_workers(self):
                self.stopped = True

        class _Editor(QWidget):
            def __init__(self):
                super().__init__()
                self.sm = SimpleNamespace(is_locked=True, state="ST_PROC")
                self._is_ai_processing = True
                self._roughcut_draft_timer = QTimer()
                self._roughcut_draft_timer.start(10_000)
                self._roughcut_draft_pending = True
                self._roughcut_draft_generation = 1
                self.video_player = _Video()
                self.timeline = _Timeline()
                self.pipeline_stopped = False
                self.cleaned = False

            def _stop_pipeline(self):
                self.pipeline_stopped = True

            def _set_roughcut_draft_status(self, _status):
                pass

            def _cleanup(self):
                self.cleaned = True

        class _Processor:
            def __init__(self):
                self.released = False

            def release_runtime_models(self):
                self.released = True

        class _Thread:
            def __init__(self):
                self.join_called = False

            def is_alive(self):
                return not self.join_called

            def join(self, timeout=None):
                self.join_called = True

        class _Backend:
            def __init__(self):
                self._active = True
                self.stopped = False
                self.video_processor = _Processor()
                self._pipeline_thread = _Thread()
                self._eta_thread = _Thread()

            def stop(self):
                self.stopped = True
                self._active = False

        editor = _Editor()
        backend = _Backend()
        try:
            window._editor_widget = editor
            window.backend = backend
            with mock.patch("core.audio.live_stt.stop_live_stt_worker", return_value=True), \
                 mock.patch("core.platform_compat.cleanup_app_runtime_processes", return_value={
                     "ollama_models": 1,
                     "ollama_processes": 1,
                     "child_processes": 1,
                     "legacy_preview_ffmpeg": 0,
                 }) as cleanup_runtime:
                cleaned = window._cleanup_runtime_for_navigation(context="홈 이동", timeout_sec=0.1, force=True)

            self.assertTrue(cleaned)
            self.assertTrue(editor.pipeline_stopped)
            self.assertTrue(editor.cleaned)
            self.assertFalse(editor._roughcut_draft_timer.isActive())
            self.assertTrue(editor.video_player.paused)
            editor.video_player.media_player.stop.assert_called_once()
            editor.video_player.vocal_player.stop.assert_called_once()
            self.assertTrue(editor.timeline.stopped)
            self.assertTrue(backend.stopped)
            self.assertTrue(backend.video_processor.released)
            self.assertTrue(backend._pipeline_thread.join_called)
            self.assertTrue(backend._eta_thread.join_called)
            cleanup_runtime.assert_called_once()
        finally:
            window.backend = None
            window._editor_widget = None
            editor.close()
            editor.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_initial_home_does_not_cleanup_idle_backend(self):
        window = MainWindow()

        class _Backend:
            _active = False

            def __init__(self):
                self.stopped = False

            def stop(self):
                self.stopped = True

        backend = _Backend()
        try:
            window._editor_widget = None
            window.backend = backend
            with mock.patch("core.platform_compat.cleanup_app_runtime_processes") as cleanup_runtime:
                cleaned = window._cleanup_runtime_for_navigation(context="홈 이동", timeout_sec=0.1)

            self.assertFalse(cleaned)
            self.assertFalse(backend.stopped)
            cleanup_runtime.assert_not_called()
        finally:
            window.backend = None
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
