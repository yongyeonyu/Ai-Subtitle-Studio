# Version: 03.09.10
# Phase: PHASE2
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QSizePolicy, QCheckBox, QComboBox, QTableWidgetItem, QWidget, QMessageBox, QPushButton

from ui.main.main_window import MainWindow
from ui.style import APP_PANEL_GAP, COLORS


class SidebarTerminalLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_terminal_log_lives_in_sidebar_and_sidebar_stays_visible(self):
        window = MainWindow()
        try:
            window.show_home()
            window.show_home()
            self.assertIs(window.log_text, window.sidebar_terminal_panel.log_text)
            self.assertIs(window.sidebar_terminal_panel.parent(), window.home_page)
            self.assertIsNotNone(getattr(window, "sidebar_queue_panel", None))
            self.assertTrue(window.bottom_work_panel.isHidden())

            window._apply_log_visible(False, persist=False)
            self.assertFalse(window.home_page.isHidden())
            self.assertFalse(window.sidebar_terminal_panel.isHidden())
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

    def test_sidebar_terminal_log_shows_user_friendly_progress_text(self):
        window = MainWindow()
        try:
            window.append_log("설정 적용: LLM(exaone3.5:7.8b), 간격 설정은 최종 패스에서 적용")
            window.append_log("[텍스트 LoRA] 자동 교정 허용: 교정 memory/오답 memory/사용자 단어/줄바꿈 규칙을 최종 LLM에 적용합니다.")
            window.append_log("[정제-교정사전] 누적적용 8회: '하추핑' => '하츄핑'")

            shown = window.log_text.toPlainText()
            raw = window.log_text.raw_log_text()

            self.assertIn("준비: 자막 품질 설정을 적용했어요.", shown)
            self.assertIn("준비: 사용자 말투와 교정 기록을 반영할 준비를 했어요.", shown)
            self.assertIn("진행: 교정 · 사전 8회", shown)
            self.assertNotIn("교정 memory/오답 memory/사용자 단어/줄바꿈 규칙", shown)
            self.assertIn("설정 적용: LLM(exaone3.5:7.8b)", raw)
            self.assertIn("[텍스트 LoRA] 자동 교정 허용", raw)
            self.assertIn("[정제-교정사전] 누적적용 8회", raw)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_terminal_log_prefers_current_stage_percent_header(self):
        window = MainWindow()
        try:
            window._generation_progress_snapshot = lambda: {
                "running": True,
                "title": "자막 생성 | STT 1",
                "progressText": "37%",
                "percent": 37,
                "percentValue": 37.0,
            }
            window.append_log("[stt] 병렬 인식 시작")

            lines = [line for line in window.log_text.toPlainText().splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 1)
            self.assertEqual(lines[0], "진행: STT1 37% · 1차 인식")
            self.assertIn("진행: STT", "\n".join(lines[1:]))
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_terminal_log_compacts_subtitle_stt1_stt2_progress_into_short_lines(self):
        window = MainWindow()
        try:
            window._generation_progress_snapshot = lambda: {
                "running": True,
                "title": "자막 생성 | [자막 전체 생성] 대기중",
                "progressText": "39%",
                "percent": 39,
                "percentValue": 39.0,
            }
            window.append_log("🔥 [STT1] macOS STT persistent worker 유지: 다음 STT 재사용 92%")
            window.append_log("🔥 [STT2] macOS STT persistent worker 유지: 다음 STT 재사용 95%")
            window.append_log("[자막 LLM] 자동교정 33%")

            lines = [line for line in window.log_text.toPlainText().splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3)
            self.assertEqual(lines[0], "진행: 자막 39% · 자동교정")
            self.assertIn("진행: STT1 92% · 재사용", lines)
            self.assertIn("진행: STT2 95% · 재사용", lines)
            self.assertNotIn("진행: 자막 33%", "\n".join(lines))
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_terminal_log_shows_detailed_stt_and_roughcut_completion_lines(self):
        window = MainWindow()
        try:
            window.append_log("  ▶ [STT1] 진행 상황: 00분 22초 / 02분 59초 (13%)")
            window.append_log("↩️ [러프컷 LLM] chunk 5/7 로컬 규칙으로 대체 (71%)")
            window.append_log("✅ 러프컷 후처리 완료: LLM 초안 · 중분류 10개")

            lines = [line for line in window.log_text.toPlainText().splitlines() if line.strip()]
            self.assertIn("진행: STT1 13% · 00:22/02:59", lines)
            self.assertIn("진행: 러프컷 71% · 5/7chunk, 로컬 대체", lines)
            self.assertIn("완료: 러프컷 · LLM, 중분류 10개", lines)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_terminal_log_adds_short_default_explanations(self):
        window = MainWindow()
        try:
            window.append_log("[lora] 48%")
            window.append_log("word_timestamp 61%")

            shown = window.log_text.toPlainText()
            self.assertIn("진행: LoRA 48% · 말투 반영", shown)
            self.assertIn("진행: 타이밍 61% · 시간 정렬", shown)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_global_menu_omits_sidebar_button(self):
        window = MainWindow()
        try:
            self.assertIs(window.global_menu_bar.parent(), window.right_workspace)
            self.assertFalse(hasattr(window.global_menu_bar, "btn_log"))
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_global_menu_qml_badges_are_removed_for_korean_only_labels(self):
        window = MainWindow()
        try:
            self.assertEqual(window.global_menu_bar.btn_undo.property("qmlBadge"), "")
            self.assertEqual(window.global_menu_bar.btn_redo.property("qmlBadge"), "")
            self.assertEqual(window.global_menu_bar.btn_save.property("qmlBadge"), "")
            self.assertEqual(window.global_menu_bar.btn_help.property("qmlBadge"), "")
            self.assertEqual(window.global_menu_bar.btn_undo.text(), "실행취소")
            self.assertEqual(window.global_menu_bar.btn_redo.text(), "다시실행")
            self.assertEqual(window.global_menu_bar.btn_help.text(), "도움말")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_stt2_menu_uses_curated_native_models(self):
        window = MainWindow()
        try:
            window._whisper_model_items = lambda: [
                "whisperkit-persistent:large-v3-v20240930_626MB",
                "mlx-community/whisper-large-v3-mlx",
                "whisper-medium-komixv2",
                "seastar105/whisper-medium-komixv2",
                "youngouk/whisper-medium-komixv2-mlx",
                "ghost613-turbo-korean-4bit",
            ]

            items = window._stt2_model_items()

            self.assertIn("whisperkit-persistent:large-v3-v20240930_626MB", items)
            self.assertIn("mlx-community/whisper-large-v3-mlx", items)
            self.assertNotIn("whisper-medium-komixv2", items)
            self.assertNotIn("seastar105/whisper-medium-komixv2", items)
            self.assertIn("youngouk/whisper-medium-komixv2-mlx", items)
            self.assertIn("ghost613-turbo-korean-4bit", items)
            self.assertEqual(
                window._short_model_name("whisperkit-persistent:large-v3-v20240930_626MB"),
                "WhisperKit Large V3 · 정밀",
            )
            self.assertEqual(window._short_model_name("youngouk/whisper-medium-komixv2-mlx"), "KomixV2 MLX · 한국어 특화")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_project_info_button_aligns_with_global_menu_bar_top(self):
        window = MainWindow()
        try:
            window._unified_dashboard = True
            window._build_home_content()
            window.resize(460, 760)
            window.show()
            self.app.processEvents()

            project_info_btn = getattr(window, "_project_info_button_card", None)
            ai_btn = window.global_menu_bar._tool_buttons[0]
            self.assertIsNotNone(project_info_btn)
            self.assertEqual(
                project_info_btn.mapTo(window, QPoint(0, 0)).y(),
                window.global_menu_bar.mapTo(window, QPoint(0, 0)).y(),
            )
            self.assertGreaterEqual(project_info_btn.height(), ai_btn.height())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_main_panel_borders_have_single_line_and_shared_gaps(self):
        window = MainWindow()
        try:
            root_layout = window.centralWidget().layout()
            margins = root_layout.contentsMargins()
            self.assertEqual((margins.left(), margins.top(), margins.right(), margins.bottom()), (APP_PANEL_GAP, APP_PANEL_GAP, APP_PANEL_GAP, APP_PANEL_GAP))
            self.assertEqual(root_layout.spacing(), APP_PANEL_GAP)
            self.assertEqual(window.workspace_splitter.handleWidth(), APP_PANEL_GAP)
            self.assertFalse(window.workspace_splitter.handle(1).isEnabled())
            self.assertEqual(window.right_layout.spacing(), APP_PANEL_GAP)
            for widget in (
                window.home_page,
                window.stack,
                window.bottom_work_panel,
                window.global_menu_bar,
            ):
                self.assertIn("border: 1px", widget.styleSheet())
            self.assertIn("border-radius: 7px", window.stack.styleSheet())
            self.assertIn("border-radius: 7px", window.bottom_work_panel.styleSheet())
            self.assertIn("border-radius: 7px", window.global_menu_bar.styleSheet())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_unified_sidebar_margins_match_queue_status_gap(self):
        window = MainWindow()
        try:
            window._unified_dashboard = True
            window.resize(2048, 1258)
            window._build_home_content()
            window.show()
            self.app.processEvents()

            home_layout = window.home_page.layout()
            home_margins = home_layout.contentsMargins()
            self.assertEqual(
                (home_margins.left(), home_margins.top(), home_margins.right(), home_margins.bottom()),
                (APP_PANEL_GAP, APP_PANEL_GAP, APP_PANEL_GAP, 0),
            )
            self.assertEqual(home_layout.spacing(), APP_PANEL_GAP)

            queue_panel = getattr(window, "sidebar_queue_panel", None)
            self.assertIsNotNone(queue_panel)
            left_layout = queue_panel.parentWidget().layout()
            self.assertEqual(left_layout.spacing(), APP_PANEL_GAP)

            status_card = window.sidebar_settings_label.parentWidget()
            queue_bottom = queue_panel.mapTo(window, QPoint(0, queue_panel.height())).y()
            status_top = status_card.mapTo(window, QPoint(0, 0)).y()
            self.assertEqual(status_top - queue_bottom, APP_PANEL_GAP)

            home_right = window.home_page.mapTo(window, QPoint(window.home_page.width(), 0)).x()
            right_left = window.right_workspace.mapTo(window, QPoint(0, 0)).x()
            self.assertEqual(right_left - home_right, APP_PANEL_GAP)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_recent_work_button_removed_and_queue_panel_sits_under_auto_cards(self):
        window = MainWindow()
        try:
            window._unified_dashboard = True
            window._build_home_content()
            window.resize(460, 760)
            window.show()
            window._sync_sidebar_terminal_panel_height()
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
            self.assertEqual(left_layout.stretch(left_layout.indexOf(queue_panel)), 9)
            nav_buttons = []
            for label in window.home_page.findChildren(QLabel):
                if label.text() in {"홈", "에디터", "러프컷", "숏폼"}:
                    parent = label.parentWidget()
                    if parent is not None and parent.objectName() == "MenuButton":
                        nav_buttons.append(parent)
            self.assertEqual(len(nav_buttons), 4)
            self.assertTrue(all(btn.maximumHeight() == 26 for btn in nav_buttons))
            preset_panel = getattr(window, "sidebar_preset_panel", None)
            self.assertIsNone(preset_panel)
            quality_combo = getattr(window, "sidebar_subtitle_quality_combo", None)
            self.assertIsNotNone(quality_combo)
            self.assertEqual([quality_combo.itemText(i) for i in range(quality_combo.count())], ["Fast", "Auto", "High", "STT"])
            self.assertGreaterEqual(quality_combo.view().minimumWidth(), 104)
            self.assertIn("QAbstractItemView::item", quality_combo.styleSheet())
            quality_row = window.home_page.findChild(QWidget, "SidebarSubtitleQualityRow")
            self.assertIsNotNone(quality_row)
            self.assertEqual(quality_row.height(), 24)
            self.assertEqual(getattr(window, "sidebar_subtitle_quality_save_btn", None).text(), "저장")
            self.assertGreaterEqual(window.sidebar_settings_label.minimumHeight(), 88)
            self.assertGreaterEqual(window.sidebar_settings_label.parentWidget().minimumHeight(), 122)
            self.assertFalse(window.sidebar_runtime_label.isVisible())
            quality_combos = list(window.home_page.findChildren(QComboBox))
            workspace_combos = [
                combo for combo in quality_combos
                if str(combo.property("subtitleQualityScope") or "workspace") == "workspace"
            ]
            auto_scope_combos = [
                combo for combo in quality_combos
                if str(combo.property("subtitleQualityScope") or "workspace") in {"icloud", "nas"}
            ]
            self.assertTrue(workspace_combos)
            self.assertEqual([workspace_combos[0].itemText(i) for i in range(workspace_combos[0].count())], ["Fast", "Auto", "High", "STT"])
            self.assertEqual(len(auto_scope_combos), 2)
            for combo in auto_scope_combos:
                self.assertEqual([combo.itemText(i) for i in range(combo.count())], ["Fast", "Auto", "High"])
            auto_toggles = {
                checkbox.objectName(): checkbox
                for checkbox in window.home_page.findChildren(QCheckBox)
                if checkbox.objectName() in {"icloudAutoToggle", "nasAutoToggle"}
            }
            self.assertEqual(set(auto_toggles), {"icloudAutoToggle", "nasAutoToggle"})
            self.assertTrue(all((checkbox.text() or "") == "" for checkbox in auto_toggles.values()))
            icloud_card_labels = [label.text() for label in auto_toggles["icloudAutoToggle"].parentWidget().findChildren(QLabel)]
            nas_card_labels = [label.text() for label in auto_toggles["nasAutoToggle"].parentWidget().findChildren(QLabel)]
            self.assertIn("iCloud 자동", icloud_card_labels)
            self.assertIn("NAS 자동", nas_card_labels)
            settings_buttons = {
                button.objectName(): button
                for button in window.home_page.findChildren(QPushButton)
                if button.objectName() in {"icloudAutoSettingsButton", "nasAutoSettingsButton"}
            }
            self.assertEqual(set(settings_buttons), {"icloudAutoSettingsButton", "nasAutoSettingsButton"})
            self.assertGreaterEqual(window.sidebar_terminal_panel.maximumHeight(), 116)
            self.assertLessEqual(window.sidebar_terminal_panel.maximumHeight(), 188)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_unified_dashboard_hides_legacy_status_rail_when_progress_nav_exists(self):
        window = MainWindow()
        try:
            window._unified_dashboard = True
            window._build_home_content()
            self.app.processEvents()

            rail = getattr(window, "status_rail", None)
            nav = getattr(window, "sidebar_nav_menu", None)
            self.assertIsNotNone(nav)
            self.assertIsNone(rail)
            from ui.menu_bar import StatusRail
            self.assertEqual(window.home_page.findChildren(StatusRail), [])
            items = list(getattr(nav, "_items", []) or [])
            self.assertTrue(items)
            self.assertEqual(items[0].get("id"), "generation_status")
            self.assertEqual(items[0].get("meta"), "CPU -- · PROC -- · RAM --")
            self.assertEqual(items[0].get("height"), 42)
            self.assertEqual(nav.minimumHeight(), 42 + (4 * (len(items) - 1)) + (26 * (len(items) - 1)))
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
            rows = window._pipeline_rows({"selected_audio_ai": "deepfilter", "selected_vad": "silero"})
            self.assertEqual([row[0] for row in rows], [
                "cut_boundary",
                "preprocess",
                "audio",
                "stt1",
                "stt2",
                "vad",
                "subtitle_llm",
                "roughcut_llm",
                "lora",
                "deep_learning",
            ])
            self.assertIn("font-weight:400", html)
            self.assertIn("model:stt1", html)
            self.assertIn("prompt:subtitle_llm", html)
            self.assertIn("prompt:roughcut_llm", html)
            self.assertNotIn("model:audio", html)
            self.assertNotIn("model:vad", html)
            self.assertNotIn("DeepFilter<span", html)
            self.assertNotIn("Silero<span", html)
            self.assertNotIn(">단계</td>", html)
            self.assertNotIn(">모델</td>", html)
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
            self.assertIn("color:#34C759; padding:0 8px 0 0; font-weight:400;", progress_html)
            self.assertIn("color:#FFD60A; padding:0 8px 0 0; font-weight:400;", progress_html)
            self.assertIn("color:#34C759; padding:0; font-family:Menlo", progress_html)
            self.assertIn("style='color:#FFD60A; text-decoration:none;", progress_html)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_subtitle_quality_combos_keep_scope_specific_auto_modes(self):
        path_settings = {
            "icloud_stt_quality_preset": "fast",
            "nas_stt_quality_preset": "balanced",
        }

        def _load_path_settings():
            return dict(path_settings)

        def _save_path_settings(settings):
            path_settings.update(settings)

        with mock.patch("ui.home_sidebar._path_load_settings", side_effect=_load_path_settings), \
                mock.patch("ui.home_sidebar._path_save_settings", side_effect=_save_path_settings), \
                mock.patch("ui.home_sidebar._runtime_load_settings", return_value={"stt_quality_preset": "balanced"}):
            window = MainWindow()
            try:
                window._unified_dashboard = True
                window._build_home_content()
                self.app.processEvents()

                combos = {
                    str(combo.property("subtitleQualityScope") or "workspace"): combo
                    for combo in window.home_page.findChildren(QComboBox)
                    if str(combo.property("subtitleQualityScope") or "workspace") in {"icloud", "nas"}
                }
                self.assertEqual([combos["icloud"].itemText(i) for i in range(combos["icloud"].count())], ["Fast", "Auto", "High"])
                self.assertEqual(combos["icloud"].currentData(), "fast")
                self.assertEqual(combos["nas"].currentData(), "balanced")
                for scope in ("icloud", "nas"):
                    combo = combos[scope]
                    card = combo.parentWidget()
                    self.assertIsNotNone(card)
                    self.assertGreaterEqual(card.width() - combo.geometry().right() - 1, 10)

                combos["icloud"].setCurrentIndex(combos["icloud"].findData("precise"))
                self.assertEqual(path_settings["icloud_stt_quality_preset"], "precise")
                self.assertEqual(path_settings["nas_stt_quality_preset"], "balanced")
                self.assertEqual(combos["nas"].currentData(), "balanced")

                override = window._set_runtime_quality_override_for_scope("nas")
                self.assertEqual(override["stt_quality_preset"], "balanced")
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_sidebar_pipeline_shows_runtime_auto_audio_and_vad_selection(self):
        window = MainWindow()
        try:
            base_settings = {
                "selected_audio_ai": "deepfilter",
                "selected_whisper_model": "whisper-large-v3",
                "stt_ensemble_enabled": False,
                "selected_vad": "silero",
                "selected_model": "사용 안함 (Whisper 단독 진행)",
                "roughcut_llm_enabled": False,
            }
            window._set_runtime_audio_tune_display(
                "/tmp/current_clip.mp4",
                {
                    "tune": {
                        "selected_audio_ai": "clearvoice",
                        "selected_vad": "ten_vad",
                        "vad_post_stt_align_enabled": True,
                    },
                    "decision": {"audio_tune_reason": "잡음 대응"},
                },
            )

            effective = window._settings_with_runtime_audio_tune(base_settings)
            rows = {stage: model for _key, stage, model in window._pipeline_rows(effective)}

            self.assertEqual(rows["음성"], "ClearVoice 자동")
            self.assertEqual(rows["VAD"], "TEN VAD 자동")

            window._refresh_sidebar_engine_info(settings=base_settings)
            html = window.sidebar_settings_label.text()
            self.assertIn("ClearVoice 자동", html)
            self.assertIn("TEN VAD 자동", html)
            self.assertIn("current_clip.mp4", window.sidebar_settings_label.toolTip())
            self.assertIn("잡음 대응", window.sidebar_settings_label.toolTip())
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
            self.assertIn(">8</td>", html)
            self.assertIn("러프컷 LLM", html)
            self.assertIn("style='color:#34C759; text-decoration:none;", html)
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

    def test_disabled_pipeline_stages_start_completed_and_use_misusage_label(self):
        window = MainWindow()
        try:
            settings = {
                "cut_boundary_level": "off",
                "scan_cut_boundary_level": "off",
                "cut_boundary_detection_enabled": False,
                "scan_cut_enabled": False,
                "selected_audio_ai": "deepfilter",
                "selected_whisper_model": "whisper-large-v3-turbo",
                "stt_ensemble_enabled": False,
                "selected_vad": "none",
                "selected_model": "사용 안함 (Whisper 단독 진행)",
                "selected_llm_provider": "none",
                "roughcut_llm_enabled": True,
                "roughcut_llm_provider": "ollama",
                "roughcut_llm_model": "exaone3.5:7.8b",
            }

            rows = window._pipeline_rows(settings)
            row_map = {key: model for key, _stage, model in rows}
            completed = window._pipeline_completed_stage_keys(settings, set())

            self.assertEqual(row_map["cut_boundary"], "미사용")
            self.assertEqual(row_map["subtitle_llm"], "미사용")
            self.assertEqual(row_map["roughcut_llm"], "미사용")
            self.assertEqual(
                completed,
                {"cut_boundary", "stt2", "vad", "subtitle_llm", "roughcut_llm"},
            )
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_cut_boundary_sidebar_menu_is_mode_owned(self):
        window = MainWindow()
        captured = []
        try:
            with mock.patch("ui.home_sidebar._runtime_load_settings", return_value={"cut_boundary_level": "medium"}), \
                 mock.patch("ui.home_sidebar.show_context_menu", side_effect=lambda _parent, _pos, items: captured.extend(items) or None):
                window._on_sidebar_model_link("model:cut_boundary")

            self.assertEqual(captured, [])
            self.assertEqual(window._cut_boundary_sidebar_label({"cut_boundary_level": "low"}), "사용")
            self.assertEqual(window._cut_boundary_sidebar_label({"cut_boundary_level": "medium"}), "사용")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_saved_editor_after_generation_marks_pipeline_done(self):
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
            self.assertEqual(
                completed,
                {
                    "cut_boundary",
                    "preprocess",
                    "audio",
                    "stt1",
                    "stt2",
                    "vad",
                    "subtitle_llm",
                    "roughcut_llm",
                    "lora",
                    "deep_learning",
                },
            )
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_fast_preset_saved_editor_marks_all_stages_complete_even_when_disabled(self):
        window = MainWindow()
        try:
            editor = type("Editor", (), {})()
            editor._roughcut_draft_status = "idle"
            editor._last_roughcut_draft_major_count = None
            editor.sm = type("State", (), {"state": "ST_SAVED"})()
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: False
            settings = {
                "cut_boundary_level": "off",
                "scan_cut_boundary_level": "off",
                "cut_boundary_detection_enabled": False,
                "scan_cut_enabled": False,
                "selected_audio_ai": "deepfilter",
                "selected_whisper_model": "whisper-large-v3-turbo",
                "stt_ensemble_enabled": False,
                "selected_vad": "none",
                "selected_model": "사용 안함 (Whisper 단독 진행)",
                "selected_llm_provider": "none",
                "roughcut_llm_enabled": False,
            }

            completed = window._pipeline_completed_stage_keys(settings, set())

            self.assertEqual(
                completed,
                {
                    "cut_boundary",
                    "preprocess",
                    "audio",
                    "stt1",
                    "stt2",
                    "vad",
                    "subtitle_llm",
                    "roughcut_llm",
                    "lora",
                    "deep_learning",
                },
            )
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_confirmed_cut_boundary_lines_do_not_block_completion(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[
                    {"timeline_sec": 1.2, "status": "confirmed"},
                    {"timeline_sec": 2.4, "verified": True},
                ],
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_SAVED"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: False

            completed = window._pipeline_completed_stage_keys(
                {
                    "stt_ensemble_enabled": False,
                    "selected_vad": "none",
                    "roughcut_llm_enabled": False,
                },
                set(),
            )

            self.assertIn("cut_boundary", completed)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_pipeline_live_log_marks_verified_cut_and_cache_reuse_green(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[
                    {"timeline_sec": 1.2, "status": "verified"},
                    {"timeline_sec": 2.4, "confirmed": True},
                ],
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_PROC"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: True
            window.log_text.setPlainText(
                "\n".join(
                    [
                        "  └ ♻️ [전처리] 원본/설정이 같은 오디오 캐시를 재사용합니다",
                        "  ▶ [STT1] 진행 상황: 00분 22초 / 02분 59초 (13%)",
                        "[STT2] Loading weights: 100%",
                        "[LLM-보정차단] 원문 무결성 검사",
                    ]
                )
            )

            settings = {
                "selected_audio_ai": "deepfilter",
                "selected_whisper_model": "whisper-large-v3",
                "stt_ensemble_enabled": True,
                "selected_whisper_model_secondary": "ghost613-turbo-korean-4bit",
                "selected_vad": "silero",
                "selected_model": "gemma4:e4b",
                "roughcut_llm_enabled": False,
            }
            current = window._pipeline_current_stage_keys(settings)
            completed = window._pipeline_completed_stage_keys(settings, current)

            self.assertEqual(current & {"stt1", "stt2", "subtitle_llm"}, {"stt1", "stt2", "subtitle_llm"})
            self.assertIn("cut_boundary", completed)
            self.assertIn("preprocess", completed)
            self.assertIn("audio", completed)
            self.assertNotIn("stt1", completed)
            self.assertNotIn("stt2", completed)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_live_pipeline_stage_prevents_stale_saved_state_from_marking_done(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[{"timeline_sec": 1.2, "status": "verified"}],
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_SAVED"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: True
            window.log_text.setPlainText("[STT2] Loading weights: 100%\n[LLM-보정차단] 원문 무결성 검사")

            current = window._pipeline_current_stage_keys(
                {
                    "stt_ensemble_enabled": True,
                    "selected_vad": "silero",
                    "roughcut_llm_enabled": False,
                }
            )
            completed = window._pipeline_completed_stage_keys(
                {
                    "stt_ensemble_enabled": True,
                    "selected_vad": "silero",
                    "roughcut_llm_enabled": False,
                },
                current,
            )

            self.assertIn("stt2", current)
            self.assertNotIn("stt1", completed)
            self.assertNotIn("stt2", completed)
            self.assertNotIn("subtitle_llm", completed)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_pipeline_current_stage_prefers_queue_status_over_stale_log_history(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[],
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_PROC"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: True
            window.log_text.setPlainText(
                "\n".join(
                    [
                        "⏳ [전처리] FFMPEG 오디오 추출 중",
                        "⏳ [자막 LLM] 교정/분리 중",
                    ]
                )
            )
            window.queue_status_probe_parts = lambda _row=0, _columns=(0, 2, 4): ["[STT] STT1/STT2 병렬 인식 중"]

            current = window._pipeline_current_stage_keys(
                {
                    "stt_ensemble_enabled": True,
                    "selected_vad": "silero",
                    "roughcut_llm_enabled": False,
                }
            )

            self.assertEqual(current, {"stt1", "stt2"})
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_pipeline_current_stage_uses_recent_log_suffix_when_queue_status_is_missing(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[],
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_PROC"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: True
            stale_lines = [f"⏳ [전처리] FFMPEG 오디오 추출 중 {idx}" for idx in range(30)]
            window.log_text.setPlainText(
                "\n".join(
                    stale_lines
                    + [
                        "[STT2] Loading weights: 100%",
                        "  ▶ [STT1] 진행 상황: 00분 22초 / 02분 59초 (13%)",
                    ]
                )
            )

            current = window._pipeline_current_stage_keys(
                {
                    "stt_ensemble_enabled": True,
                    "selected_vad": "silero",
                    "roughcut_llm_enabled": False,
                }
            )

            self.assertEqual(current, {"stt1", "stt2"})
            self.assertNotIn("preprocess", current)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_engine_summary_label_does_not_fake_live_pipeline_stages(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[],
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_PROC"),
                engine_lbl=QLabel(
                    "[VAD] : Silero\n"
                    "[음성] : DeepFilter\n"
                    "[STT] : whisper-large-v3 + Whisper-Large-v3-turbo-STT-Zeroth-KO-v2\n"
                    "[LLM] : EXAONE3.5"
                ),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: True
            window.log_text.setPlainText("")

            settings = {
                "selected_audio_ai": "deepfilter",
                "selected_whisper_model": "whisper-large-v3",
                "stt_ensemble_enabled": True,
                "selected_whisper_model_secondary": "ghost613-turbo-korean-4bit",
                "selected_vad": "silero",
                "selected_model": "exaone3.5:7.8b",
                "roughcut_llm_enabled": False,
            }

            current = window._pipeline_current_stage_keys(settings)
            completed = window._pipeline_completed_stage_keys(settings, current)

            self.assertEqual(current, set())
            for key in ("cut_boundary", "preprocess", "audio", "stt1", "stt2", "vad", "subtitle_llm", "lora", "deep_learning"):
                self.assertNotIn(key, completed)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_save_completion_log_marks_stt1_complete_even_if_stale_stt_log_remains(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[{"timeline_sec": 1.2, "status": "verified"}],
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_PROC"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: True
            window.log_text.setPlainText(
                "\n".join(
                    [
                        "  ▶ [STT1] 진행 상황: 00분 46초 / 02분 59초 (38%)",
                        "📦 프로젝트 저장 완료: DJI_20260217224203_0075_D.json",
                        "💾 저장 완료: DJI_20260217224203_0075_D.srt",
                    ]
                )
            )

            settings = {
                "cut_boundary_level": "off",
                "scan_cut_boundary_level": "off",
                "cut_boundary_detection_enabled": False,
                "scan_cut_enabled": False,
                "selected_audio_ai": "deepfilter",
                "selected_whisper_model": "whisper-large-v3-turbo",
                "stt_ensemble_enabled": False,
                "selected_vad": "silero",
                "selected_model": "사용 안함 (Whisper 단독 진행)",
                "selected_llm_provider": "none",
                "roughcut_llm_enabled": False,
            }

            current = window._pipeline_current_stage_keys(settings)
            completed = window._pipeline_completed_stage_keys(settings, current)

            self.assertIn("stt1", current)
            self.assertIn("stt1", completed)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_unconfirmed_cut_boundary_lines_keep_cut_stage_pending(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[{"timeline_sec": 1.2, "status": "provisional"}],
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_SAVED"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: False

            completed = window._pipeline_completed_stage_keys(
                {
                    "stt_ensemble_enabled": False,
                    "selected_vad": "none",
                    "roughcut_llm_enabled": False,
                },
                set(),
            )

            self.assertNotIn("cut_boundary", completed)
            self.assertTrue(window._cut_boundary_scan_pending(editor))
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_cut_boundary_completion_wait_log_does_not_mark_stage_green(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[],
                _cut_boundary_prescan_completed=False,
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_PROC"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: True
            window.log_text.setPlainText("  🎬 [컷 경계] STT 시작 전 자동 분석 완료 대기 중...")
            settings = {
                "stt_ensemble_enabled": False,
                "selected_vad": "none",
                "roughcut_llm_enabled": False,
            }

            current = window._pipeline_current_stage_keys(settings)
            completed = window._pipeline_completed_stage_keys(settings, current)

            self.assertIn("cut_boundary", current)
            self.assertNotIn("cut_boundary", completed)
            self.assertTrue(window._cut_boundary_log_pending(window._pipeline_status_blob()))
            self.assertFalse(window._cut_boundary_scan_completed(editor, window._pipeline_status_blob()))
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_cut_boundary_final_completion_log_still_marks_stage_done(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[],
                _cut_boundary_prescan_completed=False,
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_PROC"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: True
            window.log_text.setPlainText(
                "\n".join(
                    [
                        "  🎬 [컷 경계] STT 시작 전 자동 분석 완료 대기 중...",
                        "  ✅ [컷 경계] STT 시작 전 자동 분석 완료",
                    ]
                )
            )
            settings = {
                "stt_ensemble_enabled": False,
                "selected_vad": "none",
                "roughcut_llm_enabled": False,
            }

            current = window._pipeline_current_stage_keys(settings)
            completed = window._pipeline_completed_stage_keys(settings, current)

            self.assertFalse(window._cut_boundary_log_pending(window._pipeline_status_blob()))
            self.assertIn("cut_boundary", completed)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_cut_boundary_relocation_log_keeps_stage_pending_during_audio(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[],
                _cut_boundary_prescan_completed=False,
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_PROC"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: True
            window.log_text.setPlainText(
                "\n".join(
                    [
                        "  ▒ [컷 경계] split G 주제없음 frame=32988->86928 time=550.350s->1450.249s fps=59.940",
                        "  └ [음성] ClearVoice 음성 향상 진행 중... 120초",
                        "  ▫️ [컷 경계] 임시선 재배치: 610.810s (gray_window_rollback_mps, score 75.8)",
                        "  └ [음성] ClearVoice 음성 향상 진행 중... 125초",
                    ]
                )
            )
            settings = {
                "stt_ensemble_enabled": False,
                "selected_vad": "none",
                "roughcut_llm_enabled": False,
            }

            current = window._pipeline_current_stage_keys(settings)
            completed = window._pipeline_completed_stage_keys(settings, current)

            self.assertIn("cut_boundary", current)
            self.assertIn("audio", current)
            self.assertTrue(window._cut_boundary_log_pending(window._pipeline_status_blob()))
            self.assertNotIn("cut_boundary", completed)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_pipeline_table_does_not_mark_done_from_queue_header_percent_only(self):
        window = MainWindow()
        try:
            editor = SimpleNamespace(
                _auto_cut_boundary_scan_active=False,
                _auto_cut_boundary_scan_lines=[],
                _roughcut_draft_status="idle",
                _last_roughcut_draft_major_count=None,
                sm=SimpleNamespace(state="ST_IDLE"),
            )
            window._active_editor = lambda: editor
            window._is_subtitle_generation_running = lambda: False
            window.queue_header_lbl.setText("큐 리스트 : (1/1) - 100% 완료")
            window.queue_table.setRowCount(1)
            window.queue_table.setItem(0, 0, QTableWidgetItem("저장 준비 중"))

            completed = window._pipeline_completed_stage_keys(
                {
                    "stt_ensemble_enabled": True,
                    "selected_vad": "silero",
                    "roughcut_llm_enabled": True,
                },
                set(),
            )

            self.assertEqual(completed, {"roughcut_llm"})
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_timeline_cut_boundary_marker_verified_statuses(self):
        from ui.timeline.timeline_paint import cut_boundary_scan_marker_verified

        self.assertTrue(cut_boundary_scan_marker_verified({"status": "confirmed"}))
        self.assertTrue(cut_boundary_scan_marker_verified({"status": "verified"}))
        self.assertTrue(cut_boundary_scan_marker_verified({"confirmed": True}))
        self.assertFalse(cut_boundary_scan_marker_verified({"status": "provisional"}))

    def test_sidebar_queue_status_is_plain_and_eta_header_is_full_text(self):
        window = MainWindow()
        try:
            window.queue_table.setRowCount(1)
            window.queue_table.setItem(0, 0, QTableWidgetItem("✅ 자막 생성 완료"))
            window.queue_table.setItem(0, 1, QTableWidgetItem("DJI_20260217224203_0075_D.MP4"))
            window.queue_table.setItem(0, 3, QTableWidgetItem("00:10"))
            window.queue_table.setItem(0, 4, QTableWidgetItem("00:10 / 01:37"))
            items = window._sidebar_queue_items()
            self.assertEqual(items[0]["order"], "1")
            self.assertEqual(items[0]["status"], "자막 생성 완료")
            self.assertTrue(items[0]["done"])
            self.assertNotIn("✅", items[0]["status"])
            self.assertEqual(items[0]["eta"], "00:10 / 01:37")

            panel = window._ensure_sidebar_queue_panel()
            panel.set_queue("큐 리스트 : (1/1) - 100% 완료", items)
            self.assertFalse(panel._table.horizontalHeader().isVisible())
            self.assertEqual(panel._table.columnCount(), 2)
            self.assertIn("완료", panel._table.item(0, 0).text())
            self.assertIn("0️⃣1️⃣ DJI_", panel._table.item(0, 1).text())
            self.assertIn("00:10 / 01:37", panel._table.item(0, 1).text())
            self.assertNotIn("?", panel._table.item(0, 1).text())
            self.assertNotIn("예상시간", panel._table.item(0, 1).text())
            self.assertGreaterEqual(panel._table.item(0, 1).text().count("\n"), 2)
            self.assertGreaterEqual(panel._table.rowHeight(0), 62)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_queue_running_eta_uses_elapsed_over_expected(self):
        window = MainWindow()
        try:
            window.queue_table.setRowCount(1)
            window.queue_table.setItem(0, 0, QTableWidgetItem("자막 생성 중"))
            window.queue_table.setItem(0, 1, QTableWidgetItem("clip_a.mp4"))
            window.queue_table.setItem(0, 3, QTableWidgetItem("02:59"))
            window.queue_table.setItem(0, 4, QTableWidgetItem("00:02"))
            items = window._sidebar_queue_items()
            self.assertEqual(items[0]["eta"], "00:00 / 00:02")

            window.queue_table.setItem(0, 4, QTableWidgetItem("01:35 / 02:59"))
            items = window._sidebar_queue_items()
            self.assertEqual(items[0]["eta"], "01:35 / 02:59")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_queue_order_uses_keycap_digits(self):
        window = MainWindow()
        try:
            panel = window._ensure_sidebar_queue_panel()
            panel.set_queue(
                "큐 리스트 : (10/12) - 30% 완료",
                [
                    {
                        "order": "10",
                        "file": "clip_10.mov",
                        "eta": "00:10 / 00:30",
                        "status": "대기 중",
                        "statusDisplay": "대기 중",
                        "done": False,
                        "active": False,
                        "error": False,
                    }
                ],
            )

            self.assertIn("1️⃣0️⃣ clip_10.mov", panel._table.item(0, 1).text())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_queue_single_digit_order_is_two_keycaps(self):
        window = MainWindow()
        try:
            panel = window._ensure_sidebar_queue_panel()
            panel.set_queue(
                "큐 리스트 : (2/12) - 10% 완료",
                [
                    {
                        "order": "2",
                        "file": "clip_02.mov",
                        "eta": "00:02 / 00:20",
                        "status": "대기 중",
                        "statusDisplay": "대기 중",
                        "done": False,
                        "active": False,
                        "error": False,
                    }
                ],
            )

            self.assertIn("0️⃣2️⃣ clip_02.mov", panel._table.item(0, 1).text())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_queue_panel_does_not_mark_active_status_with_complete_word_as_done(self):
        window = MainWindow()
        try:
            panel = window._ensure_sidebar_queue_panel()
            panel.set_queue(
                "큐 리스트 : (1/1) - 99% 완료",
                [
                    {
                        "order": "1",
                        "file": "clip_01.mov",
                        "eta": "00:21 / 02:59",
                        "status": "자막 생성 완료 판정 중",
                        "statusDisplay": "자막 생성 완료 판정 중",
                        "done": False,
                        "active": True,
                        "error": False,
                    }
                ],
            )

            self.assertEqual(panel._table.item(0, 0).text(), "자막 생성 완료 판정 중")
            self.assertEqual(panel._table.item(0, 0).foreground().color().name().upper(), COLORS["warning"])
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_queue_panel_focuses_active_row(self):
        window = MainWindow()
        try:
            panel = window._ensure_sidebar_queue_panel()
            items = [
                {
                    "order": str(idx + 1),
                    "file": f"clip_{idx + 1}.mov",
                    "eta": "00:10",
                    "status": "대기 중",
                    "statusDisplay": "대기 중",
                    "done": False,
                    "active": idx == 8,
                    "error": False,
                }
                for idx in range(12)
            ]
            panel.set_queue("큐 리스트 : (9/12) - 30% 완료", items)

            self.assertEqual(panel._table.currentRow(), 8)
            active_fg = panel._table.item(8, 1).foreground().color().name().upper()
            waiting_fg = panel._table.item(0, 1).foreground().color().name().upper()
            self.assertEqual(active_fg, COLORS["warning"])
            self.assertEqual(waiting_fg, "#9DB0BB")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_queue_panel_sanitizes_multiple_active_rows(self):
        window = MainWindow()
        try:
            panel = window._ensure_sidebar_queue_panel()
            items = [
                {
                    "order": str(idx + 1),
                    "file": f"clip_{idx + 1}.mov",
                    "eta": "00:10",
                    "status": "컷 경계 확인 중",
                    "statusDisplay": "컷 경계 확인 중",
                    "done": False,
                    "active": idx in {1, 2},
                    "error": False,
                }
                for idx in range(4)
            ]
            panel.set_queue("큐 리스트 : (2/4) - 10% 완료", items)

            self.assertEqual(panel._table.currentRow(), 1)
            self.assertEqual(panel._table.item(1, 1).foreground().color().name().upper(), COLORS["warning"])
            self.assertEqual(panel._table.item(2, 1).foreground().color().name().upper(), "#9DB0BB")
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

    def test_queue_updates_do_not_collapse_bottom_panel_during_editor_processing(self):
        window = MainWindow()
        editor = QWidget()
        try:
            editor.sm = SimpleNamespace(state="ST_PROC")
            editor._is_ai_processing = True
            window._editor_widget = editor
            window.stack.addWidget(editor)
            window.stack.setCurrentWidget(editor)
            window.bottom_work_panel.setVisible(True)
            window.bottom_work_panel.setMaximumHeight(190)

            window._show_bottom_queue_table()

            self.assertFalse(window.bottom_work_panel.isHidden())
            self.assertEqual(window.bottom_work_panel.maximumHeight(), 190)
            self.assertTrue(window._should_preserve_editor_processing_layout())
        finally:
            window._editor_widget = None
            editor.close()
            editor.deleteLater()
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
            slot = getattr(window, "_project_info_button_slot", None)
            terminal = getattr(window, "sidebar_terminal_panel", None)
            self.assertIsNotNone(button)
            self.assertIsNotNone(slot)
            self.assertIsNotNone(terminal)
            self.assertGreater(
                button.mapTo(window, QPoint(0, 0)).y(),
                terminal.mapTo(window, QPoint(0, 0)).y(),
            )
            self.assertEqual(
                button.mapTo(window, QPoint(0, 0)).y(),
                window.global_menu_bar.mapTo(window, QPoint(0, 0)).y(),
            )
            self.assertEqual(slot.height(), button.height())
            self.assertEqual(window.global_menu_bar.height(), button.height())

            window._toggle_project_info_card()
            self.app.processEvents()
            overlay = getattr(window, "_project_info_overlay", None)
            self.assertIsNotNone(overlay)
            self.assertLess(
                overlay.mapTo(window, QPoint(0, 0)).y(),
                button.mapTo(window, QPoint(0, 0)).y(),
            )

            window._toggle_project_info_card()
            self.app.processEvents()
            self.assertIsNone(getattr(window, "_project_info_overlay", None))
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_sidebar_terminal_panel_fills_gap_between_status_and_project_button(self):
        window = MainWindow()
        try:
            window._unified_dashboard = True
            window.resize(2048, 1258)
            window._build_home_content()
            window.show()
            self.app.processEvents()

            terminal = getattr(window, "sidebar_terminal_panel", None)
            status_card = getattr(window, "_sidebar_status_card_widget", None)
            slot = getattr(window, "_project_info_button_slot", None)
            queue_panel = getattr(window, "sidebar_queue_panel", None)
            self.assertIsNotNone(terminal)
            self.assertIsNotNone(status_card)
            self.assertIsNotNone(slot)
            self.assertIsNotNone(queue_panel)

            status_bottom = status_card.mapTo(window, QPoint(0, status_card.height())).y()
            terminal_top = terminal.mapTo(window, QPoint(0, 0)).y()
            terminal_bottom = terminal.mapTo(window, QPoint(0, terminal.height())).y()
            slot_top = slot.mapTo(window, QPoint(0, 0)).y()

            self.assertEqual(terminal_top - status_bottom, APP_PANEL_GAP)
            self.assertEqual(slot_top - terminal_bottom, APP_PANEL_GAP)
            self.assertGreaterEqual(terminal.height(), 128)
            self.assertLessEqual(terminal.height(), 188)
            self.assertGreater(queue_panel.height(), terminal.height())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_global_menu_buttons_keep_action_height_while_project_info_aligns_with_bar(self):
        from ui.menu_bar import MENU_BUTTON_HEIGHT

        window = MainWindow()
        try:
            window._unified_dashboard = True
            window._build_home_content()
            self.app.processEvents()

            button = getattr(window, "_project_info_button_card", None)
            self.assertIsNotNone(button)
            self.assertEqual(
                button.mapTo(window, QPoint(0, 0)).y(),
                window.global_menu_bar.mapTo(window, QPoint(0, 0)).y(),
            )
            self.assertEqual(button.height(), MENU_BUTTON_HEIGHT)
            for menu_button in window.global_menu_bar._tool_buttons:
                self.assertEqual(menu_button.height(), MENU_BUTTON_HEIGHT)
                self.assertLessEqual(menu_button.iconSize().height(), 18)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_home_preserves_running_backend_and_runtime_processes(self):
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

            self.assertFalse(editor.stopped)
            self.assertTrue(editor._roughcut_draft_timer.isActive())
            self.assertTrue(editor._roughcut_draft_pending)
            self.assertEqual(editor._roughcut_draft_generation, 3)
            self.assertNotIn("idle", editor.statuses)
            self.assertFalse(backend.stopped)
            cleanup_runtime.assert_not_called()
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

            def _shutdown_runtime(models, logger=None, **_kwargs):
                stopped_models.extend(models or [])
                return {"models": list(models or []), "processes": 1}

            with mock.patch("ui.main.main_window.threading.Thread", _ImmediateThread), \
                 mock.patch("ui.main.main_window.load_settings", return_value={"selected_model": "gemma4:e4b"}), \
                 mock.patch("core.llm.ollama_provider.shutdown_local_ollama_runtime", side_effect=_shutdown_runtime):
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

    def test_post_generation_cleanup_releases_models_immediately(self):
        window = MainWindow()
        editor = QWidget(window)
        editor.sm = SimpleNamespace(is_locked=False, state="ST_COMP")
        editor._is_ai_processing = False
        editor._abort_pending_editor_processing_ui_work = mock.Mock()
        editor._live_editor_preview_queue = [{"text": "temp"}]
        editor._live_editor_preview_segments = [{"text": "temp"}]
        editor._subtitle_context_window_index_cache = {"0": 0}
        release_calls = []
        try:
            window._editor_widget = editor
            with (
                mock.patch.object(
                    window,
                    "_release_ai_models_for_editor_mode",
                    side_effect=lambda **kwargs: release_calls.append(kwargs),
                ),
                mock.patch.object(window, "_schedule_post_generation_gc") as schedule_gc,
            ):
                result = window._post_generation_resource_cleanup(
                    reason="subtitle_generation_complete",
                    editor=editor,
                )

            self.assertTrue(result["cleaned"])
            self.assertEqual(
                release_calls,
                [{"force": True, "preserve_roughcut_status": True, "ollama_timeout_sec": 1.2}],
            )
            editor._abort_pending_editor_processing_ui_work.assert_called_once()
            self.assertEqual(editor._live_editor_preview_queue, [])
            self.assertEqual(editor._live_editor_preview_segments, [])
            self.assertEqual(editor._subtitle_context_window_index_cache, {})
            self.assertTrue(editor._post_generation_models_release_requested)
            self.assertFalse(editor._post_generation_models_released)
            schedule_gc.assert_called_once_with(editor=editor, delay_ms=450)
        finally:
            window._editor_widget = None
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
            with mock.patch("core.llm.ollama_provider.shutdown_local_ollama_runtime") as stop_llm:
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
            with mock.patch("core.llm.ollama_provider.shutdown_local_ollama_runtime") as stop_llm:
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

    def test_home_navigation_preserves_idle_editor_video_surface(self):
        window = MainWindow()

        class _Video:
            def __init__(self):
                self._ui_timer = QTimer()
                self._ui_timer.start(10_000)
                self.paused = False
                self.shutdown_calls = 0
                self.media_player = mock.Mock()
                self.vocal_player = mock.Mock()

            def suspend_for_navigation(self):
                self.paused = True

            def shutdown_backend(self):
                self.shutdown_calls += 1

        class _Editor(QWidget):
            def __init__(self):
                super().__init__()
                self.sm = SimpleNamespace(is_locked=False, state="ST_IDLE")
                self._is_ai_processing = False
                self._roughcut_draft_timer = QTimer()
                self._roughcut_draft_timer.start(10_000)
                self._roughcut_draft_pending = True
                self._roughcut_draft_generation = 1
                self.video_player = _Video()

            def _set_roughcut_draft_status(self, _status):
                pass

        editor = _Editor()
        try:
            window._editor_widget = editor
            with mock.patch("core.audio.live_stt.stop_live_stt_worker", return_value=False), \
                 mock.patch(
                     "core.platform_compat.cleanup_app_runtime_processes",
                     return_value={
                         "ollama_models": 0,
                         "ollama_processes": 0,
                         "child_processes": 0,
                         "legacy_preview_ffmpeg": 0,
                     },
                 ):
                cleaned = window._cleanup_runtime_for_navigation(context="홈 이동", timeout_sec=0.1)

            self.assertFalse(cleaned)
            self.assertTrue(editor.video_player.paused)
            self.assertEqual(editor.video_player.shutdown_calls, 0)
            editor.video_player.media_player.stop.assert_not_called()
            editor.video_player.vocal_player.stop.assert_not_called()
            self.assertTrue(editor.video_player._ui_timer.isActive())
        finally:
            window._editor_widget = None
            editor.close()
            editor.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_app_exit_force_does_not_log_pipeline_stop_for_idle_backend(self):
        window = MainWindow()

        class _Backend:
            _active = False

            def __init__(self):
                self.stopped = False

            def stop(self, *, log_context="파이프라인 중단"):
                self.stopped = True
                self.log_context = log_context

        backend = _Backend()
        try:
            window._editor_widget = None
            window.backend = backend
            with mock.patch(
                "core.platform_compat.cleanup_app_runtime_processes",
                return_value={
                    "ollama_models": 0,
                    "ollama_processes": 0,
                    "child_processes": 0,
                    "legacy_preview_ffmpeg": 0,
                },
            ):
                cleaned = window._cleanup_runtime_for_navigation(
                    context="앱 종료", timeout_sec=0.1, force=True
                )

            self.assertFalse(cleaned)
            self.assertFalse(backend.stopped)
        finally:
            window.backend = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_app_exit_force_passes_context_to_active_backend_stop(self):
        window = MainWindow()

        class _Backend:
            def __init__(self):
                self._active = True
                self.log_context = None

            def stop(self, *, log_context="파이프라인 중단"):
                self.log_context = log_context
                self._active = False

        backend = _Backend()
        try:
            window._editor_widget = None
            window.backend = backend
            with mock.patch(
                "core.platform_compat.cleanup_app_runtime_processes",
                return_value={
                    "ollama_models": 0,
                    "ollama_processes": 0,
                    "child_processes": 0,
                    "legacy_preview_ffmpeg": 0,
                },
            ):
                cleaned = window._cleanup_runtime_for_navigation(
                    context="앱 종료", timeout_sec=0.1, force=True
                )

            self.assertTrue(cleaned)
            self.assertEqual(backend.log_context, "앱 종료")
        finally:
            window.backend = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_fast_exit_pause_signals_runtime_without_joining_backend_threads(self):
        window = MainWindow()

        class _Event:
            def __init__(self):
                self.set_called = False

            def set(self):
                self.set_called = True

        class _ThreadRef:
            def __init__(self):
                self.join_called = False

            def is_alive(self):
                return True

            def join(self, timeout=None):
                self.join_called = True

        class _Backend:
            def __init__(self):
                self._active = True
                self._action_state = ["wait"]
                self._edit_event = _Event()
                self._start_event = _Event()
                self._pipeline_thread = _ThreadRef()
                self.stop_called = False

            def stop(self, *, log_context="파이프라인 중단", unload_llm=True):
                self.stop_called = True
                self.stop_context = log_context
                self.unload_llm = unload_llm

        class _Trainer:
            def __init__(self):
                self.suspend_args = None
                self.shutdown_timeout = None

            def suspend_for_foreground_activity(self, *, reason, hold_ms):
                self.suspend_args = (reason, hold_ms)
                return {"suspended": True}

            def shutdown(self, *, timeout_sec=3.0):
                self.shutdown_timeout = timeout_sec
                return {"stopped": False, "busy": True}

        class _Manager:
            def __init__(self):
                self._running = True
                self.stopped = False

            def stop(self):
                self.stopped = True
                self._running = False

        fake_threads = []

        class _FakeThread:
            def __init__(self, *, target, daemon=False, name=None):
                self.target = target
                self.daemon = daemon
                self.name = name
                self.started = False
                fake_threads.append(self)

            def start(self):
                self.started = True

        backend = _Backend()
        trainer = _Trainer()
        cloud_manager = _Manager()
        nas_manager = _Manager()
        try:
            window.backend = backend
            window.backend_fast = None
            window._personalization_idle_trainer = trainer
            window._cloud_sync_manager = cloud_manager
            window._nas_sync_manager = nas_manager
            with mock.patch("ui.main.main_window.threading.Thread", _FakeThread), \
                 mock.patch("core.audio.live_stt.stop_live_stt_worker", return_value=False):
                paused = window._pause_all_runtime_work_for_exit(context="앱 종료")

            self.assertTrue(paused)
            self.assertTrue(window._fast_exit_requested)
            self.assertEqual(trainer.suspend_args, ("app_exit", 3_600_000))
            self.assertEqual(trainer.shutdown_timeout, 0.0)
            self.assertTrue(cloud_manager.stopped)
            self.assertTrue(nas_manager.stopped)
            self.assertFalse(backend._active)
            self.assertEqual(backend._action_state[0], "exit")
            self.assertTrue(backend._edit_event.set_called)
            self.assertTrue(backend._start_event.set_called)
            self.assertFalse(backend._pipeline_thread.join_called)
            self.assertFalse(backend.stop_called)
            self.assertEqual(len(fake_threads), 1)
            self.assertTrue(fake_threads[0].daemon)
            self.assertEqual(fake_threads[0].name, "fast-exit-backend-stop")
            self.assertTrue(fake_threads[0].started)
        finally:
            window.backend = None
            window.backend_fast = None
            window._editor_widget = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_quick_exit_skips_backup_when_runtime_busy_and_pauses_first(self):
        window = MainWindow()
        events = []
        try:
            window._has_active_runtime_work_for_exit = lambda: True
            window._pause_all_runtime_work_for_exit = lambda *, context: events.append(("pause", context))
            window._start_runtime_cleanup_for_app_exit_async = lambda *, timeout_sec: events.append(("cleanup_async", timeout_sec))
            window._backup_before_quick_exit = lambda: events.append(("backup", None))
            window._schedule_forced_process_exit = lambda *, delay_ms: events.append(("schedule", delay_ms))

            with mock.patch("ui.main.main_file_ops.QApplication.quit") as quit_app:
                window._quick_exit()

            expected_timeout = 0.08 if sys.platform == "darwin" else 0.15
            expected_delay = 20 if sys.platform == "darwin" else 60
            self.assertEqual(events, [("schedule", expected_delay), ("pause", "앱 종료"), ("cleanup_async", expected_timeout)])
            quit_app.assert_called_once()
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_exit_runtime_detection_includes_busy_personalization_trainer(self):
        window = MainWindow()

        class _Trainer:
            def is_busy(self):
                return True

        try:
            window._editor_widget = None
            window.backend = None
            window.backend_fast = None
            window._auto_processing_active = False
            window._personalization_idle_trainer = _Trainer()

            self.assertTrue(window._has_active_runtime_work_for_exit())
        finally:
            window._personalization_idle_trainer = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_about_to_quit_force_exit_is_scheduled_for_busy_personalization_trainer(self):
        window = MainWindow()
        calls = []

        class _Trainer:
            def is_busy(self):
                return True

        try:
            window._editor_widget = None
            window.backend = None
            window.backend_fast = None
            window._auto_processing_active = False
            window._personalization_idle_trainer = _Trainer()
            window._schedule_forced_process_exit = lambda *, delay_ms: calls.append(delay_ms)

            scheduled = window._schedule_forced_exit_for_busy_about_to_quit()

            self.assertTrue(scheduled)
            self.assertEqual(calls, [80 if sys.platform == "darwin" else 320])
        finally:
            window._personalization_idle_trainer = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_pause_editor_runtime_for_exit_aborts_pending_editor_ui_work(self):
        window = MainWindow()

        class _Timer:
            def __init__(self):
                self.stopped = False

            def stop(self):
                self.stopped = True

        events = []
        try:
            editor = SimpleNamespace(
                _abort_pending_editor_processing_ui_work=lambda: events.append("abort"),
                sm=SimpleNamespace(stop_processing=lambda message: events.append(("stop", message))),
                _spinner_timer=_Timer(),
                _roughcut_draft_timer=_Timer(),
                _cut_boundary_scan_timer=_Timer(),
                video_player=None,
            )

            paused = window._pause_editor_runtime_for_exit(editor)

            self.assertTrue(paused)
            self.assertIn("abort", events)
            self.assertIn(("stop", "앱 종료로 작업을 일시 정지했습니다."), events)
            self.assertTrue(editor._spinner_timer.stopped)
            self.assertTrue(editor._roughcut_draft_timer.stopped)
            self.assertTrue(editor._cut_boundary_scan_timer.stopped)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_exit_backup_skips_editor_save_when_no_unsaved_changes(self):
        window = MainWindow()

        class _Editor:
            def __init__(self):
                self.save_called = False

            def _has_unsaved_changes(self):
                return False

            def _on_save(self, **_kwargs):
                self.save_called = True

        editor = _Editor()
        try:
            window._editor_widget = editor
            window._current_project_path = ""

            window._backup_before_quick_exit(include_project_backup=False)

            self.assertFalse(editor.save_called)
        finally:
            window._editor_widget = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_quick_exit_cancel_keeps_app_running_when_editor_is_dirty(self):
        window = MainWindow()

        class _Editor:
            def _has_unsaved_changes(self):
                return True

            def _on_save(self, **_kwargs):
                raise AssertionError("cancelled exit must not save")

        try:
            window._editor_widget = _Editor()
            window._pause_all_runtime_work_for_exit = mock.Mock()
            window._start_runtime_cleanup_for_app_exit_async = mock.Mock()
            window._schedule_forced_process_exit = mock.Mock()

            with mock.patch(
                "ui.main.main_file_ops.confirm_save_changes",
                return_value=QMessageBox.StandardButton.Cancel,
            ), mock.patch("ui.main.main_file_ops.QApplication.quit") as quit_app:
                window._quick_exit()

            self.assertFalse(getattr(window, "_quick_exit_requested", False))
            window._pause_all_runtime_work_for_exit.assert_not_called()
            window._start_runtime_cleanup_for_app_exit_async.assert_not_called()
            window._schedule_forced_process_exit.assert_not_called()
            quit_app.assert_not_called()
        finally:
            window._editor_widget = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_quick_exit_still_closes_when_runtime_pause_raises(self):
        window = MainWindow()
        original_close = window.close
        try:
            window._pause_all_runtime_work_for_exit = mock.Mock(side_effect=RuntimeError("boom"))
            window._start_runtime_cleanup_for_app_exit_async = mock.Mock()
            window._schedule_forced_process_exit = mock.Mock()
            window.close = mock.Mock()

            with mock.patch("ui.main.main_file_ops.QApplication.quit") as quit_app:
                window._quick_exit()

            self.assertTrue(getattr(window, "_quick_exit_requested", False))
            window._schedule_forced_process_exit.assert_called_once()
            window._start_runtime_cleanup_for_app_exit_async.assert_called_once()
            window.close.assert_called_once()
            quit_app.assert_called_once()
        finally:
            window.close = original_close
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_exit_confirm_no_does_not_save_again_during_backup(self):
        window = MainWindow()
        regular_save = mock.Mock(return_value=True)

        class _Editor:
            def _has_unsaved_changes(self):
                return True

            def _on_save(self, **kwargs):
                return regular_save(**kwargs)

        try:
            window._editor_widget = _Editor()
            with mock.patch(
                "ui.main.main_file_ops.confirm_save_changes",
                return_value=QMessageBox.StandardButton.No,
            ):
                self.assertTrue(window._confirm_save_dirty_editor_before_exit())

            window._backup_before_quick_exit(include_project_backup=False)

            regular_save.assert_not_called()
            self.assertTrue(bool(getattr(window, "_editor_exit_save_skipped", False)))
        finally:
            window._editor_widget = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_exit_confirm_yes_saves_dirty_editor_before_runtime_pause(self):
        window = MainWindow()
        save = mock.Mock(return_value=True)

        class _Editor:
            def _has_unsaved_changes(self):
                return True

            def _on_save(self, **kwargs):
                return save(**kwargs)

        try:
            window._editor_widget = _Editor()
            with mock.patch(
                "ui.main.main_file_ops.confirm_save_changes",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                self.assertTrue(window._confirm_save_dirty_editor_before_exit())

            save.assert_called_once_with(skip_auto_next=True)
        finally:
            window._editor_widget = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_exit_confirm_prefers_fast_exit_save_path(self):
        window = MainWindow()
        fast_save = mock.Mock(return_value=True)
        regular_save = mock.Mock(return_value=True)

        class _Editor:
            def _has_unsaved_changes(self):
                return True

            def _on_save_for_exit(self):
                return fast_save()

            def _on_save(self, **kwargs):
                return regular_save(**kwargs)

        try:
            window._editor_widget = _Editor()
            with mock.patch(
                "ui.main.main_file_ops.confirm_save_changes",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                self.assertTrue(window._confirm_save_dirty_editor_before_exit())

            fast_save.assert_called_once_with()
            regular_save.assert_not_called()
            self.assertTrue(bool(getattr(window, "_editor_exit_save_completed", False)))
        finally:
            window._editor_widget = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_exit_backup_skips_second_save_after_fast_exit_save(self):
        window = MainWindow()
        regular_save = mock.Mock(return_value=True)

        class _Editor:
            def _has_unsaved_changes(self):
                return True

            def _on_save(self, **kwargs):
                return regular_save(**kwargs)

        try:
            window._editor_widget = _Editor()
            window._editor_exit_save_completed = True

            window._backup_before_quick_exit(include_project_backup=False)

            regular_save.assert_not_called()
        finally:
            window._editor_widget = None
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_window_close_cancel_ignores_event_before_runtime_pause(self):
        window = MainWindow()
        event = SimpleNamespace(accept=mock.Mock(), ignore=mock.Mock())
        try:
            window._confirm_save_dirty_editor_before_exit = mock.Mock(return_value=False)
            window._pause_all_runtime_work_for_exit = mock.Mock()

            with mock.patch.dict(os.environ, {"QT_QPA_PLATFORM": "cocoa"}):
                MainWindow.closeEvent(window, event)

            event.ignore.assert_called_once()
            event.accept.assert_not_called()
            window._pause_all_runtime_work_for_exit.assert_not_called()
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_window_close_accepts_even_when_runtime_pause_raises(self):
        window = MainWindow()
        event = SimpleNamespace(accept=mock.Mock(), ignore=mock.Mock())
        try:
            window._confirm_save_dirty_editor_before_exit = mock.Mock(return_value=True)
            window._has_active_runtime_work_for_exit = mock.Mock(return_value=False)
            window._pause_all_runtime_work_for_exit = mock.Mock(side_effect=RuntimeError("boom"))
            window._start_runtime_cleanup_for_app_exit_async = mock.Mock()
            window._schedule_forced_process_exit = mock.Mock()
            window._backup_before_quick_exit = mock.Mock()

            with mock.patch.dict(os.environ, {"QT_QPA_PLATFORM": "cocoa"}):
                MainWindow.closeEvent(window, event)

            event.accept.assert_called_once()
            event.ignore.assert_not_called()
            window._schedule_forced_process_exit.assert_called_once()
            window._start_runtime_cleanup_for_app_exit_async.assert_called_once()
            window._backup_before_quick_exit.assert_called_once_with(include_project_backup=False)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_app_exit_cleanup_runs_even_after_fast_exit_pause(self):
        window = MainWindow()
        try:
            window._fast_exit_requested = True
            cleanup_calls = []
            runtime_calls = []
            window._cleanup_runtime_for_navigation = lambda **kwargs: cleanup_calls.append(kwargs) or False
            window._clear_runtime_memory_caches = lambda **kwargs: None
            with mock.patch(
                "core.platform_compat.cleanup_app_runtime_processes",
                side_effect=lambda **kwargs: runtime_calls.append(kwargs) or {
                    "ollama_models": 1,
                    "ollama_processes": 1,
                    "child_processes": 0,
                    "legacy_preview_ffmpeg": 0,
                },
            ):
                first = window._cleanup_runtime_for_app_exit(timeout_sec=0.8)
                second = window._cleanup_runtime_for_app_exit(timeout_sec=0.8)

            self.assertTrue(first)
            self.assertFalse(second)
            self.assertEqual(
                cleanup_calls,
                [
                    {
                        "context": "앱 종료",
                        "timeout_sec": 0.8,
                        "force": True,
                        "stop_active": True,
                    }
                ],
            )
            self.assertEqual(len(runtime_calls), 1)
            self.assertEqual(runtime_calls[0]["timeout_sec"], 0.8)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_repeated_home_does_not_cleanup_same_idle_editor_twice(self):
        window = MainWindow()

        class _Editor(QWidget):
            def __init__(self):
                super().__init__()
                self.sm = SimpleNamespace(is_locked=False, state="ST_IDLE")
                self._is_ai_processing = False

        editor = _Editor()
        try:
            window._editor_widget = editor
            with mock.patch(
                "core.platform_compat.cleanup_app_runtime_processes",
                return_value={
                    "ollama_models": 1,
                    "ollama_processes": 0,
                    "child_processes": 0,
                    "legacy_preview_ffmpeg": 0,
                },
            ) as cleanup_runtime:
                first = window._cleanup_runtime_for_navigation(context="홈 이동", timeout_sec=0.1)
                second = window._cleanup_runtime_for_navigation(context="홈 이동", timeout_sec=0.1)

            self.assertTrue(first)
            self.assertFalse(second)
            cleanup_runtime.assert_called_once()
        finally:
            window._editor_widget = None
            editor.close()
            editor.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_open_editor_screen_restores_video_surface_after_home(self):
        window = MainWindow()

        class _Video:
            def __init__(self):
                self.restore_calls = 0

            def restore_after_navigation(self):
                self.restore_calls += 1

        class _Editor(QWidget):
            def __init__(self):
                super().__init__()
                self.video_player = _Video()

        editor = _Editor()
        try:
            window.stack.addWidget(editor)
            window._editor_widget = editor
            window._attach_global_menu_to_editor = mock.Mock()
            window._show_bottom_queue_table = mock.Mock()
            window._release_ai_models_for_editor_mode = mock.Mock()
            window._activate_editor_idle_mode = mock.Mock()
            window._build_home_content = mock.Mock()

            window._open_editor_screen()
            self.app.processEvents()

            self.assertGreaterEqual(editor.video_player.restore_calls, 1)
        finally:
            window._editor_widget = None
            editor.close()
            editor.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
