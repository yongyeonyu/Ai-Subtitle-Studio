# Version: 03.14.06
# Phase: PHASE2
import os
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QWidget

from core.runtime import config
from core.project.project_io import read_project_storage_payload
from core.state_manager import SubtitleStateManager
from core.work_mode import EDITOR_MODE
from ui.editor.editor_actions import EditorActionsMixin
from ui.editor.editor_pipeline import EditorPipelineMixin
from ui.home_ui import HomeUIMixin
from ui.main.main_signals import SignalHandlersMixin
from ui.menu_bar import StatusRail
from ui.queue_widget import QueueMixin
from ui.style import COLORS


class _DummyHome(QObject, QueueMixin, HomeUIMixin):
    def __init__(self, editor):
        super().__init__()
        self._editor = editor
        self.saved_status_label = QLabel("")
        self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)
        self.queue_header_lbl = QLabel("")
        self.queue_table = QTableWidget(0, 5)
        self._current_file_idx = 0
        self._total_files = 0
        self._real_pct = 0
        self._expected_seconds = {}
        self._file_start_times = {}
        self._file_complete_times = {}
        self._queue_row_cache = []
        self._sidebar_queue_cache_items = []
        self._sidebar_queue_cache_header = ""
        self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

    def _active_editor(self):
        return self._editor

    def _show_bottom_queue_table(self):
        pass

    def _sync_sidebar_queue_panel(self):
        pass


class Cp03Cp04StatusUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_saved_status_is_dot_and_version_only_with_generation_blink(self):
        state_manager = SimpleNamespace(state="ST_SAVED", is_locked=False, is_dirty=False)
        editor = SimpleNamespace(sm=state_manager, _is_ai_processing=False)
        home = _DummyHome(editor)

        home._refresh_saved_status_label(is_dirty=False)
        text = home.saved_status_label.text()
        self.assertIn(f"v{config.APP_VERSION}", text)
        self.assertIn("#34C759", text)
        for forbidden in ("상태 / 설정", "현재 설정", "저장됨:", "버전:", "자막:", "러프컷:"):
            self.assertNotIn(forbidden, text)

        state_manager.state = "ST_PROC"
        state_manager.is_locked = True
        state_manager.is_dirty = True
        home._refresh_saved_status_label(is_dirty=True)
        self.assertTrue(home._saved_status_blink_timer.isActive())
        self.assertEqual(home._saved_status_blink_timer.interval(), 1000)
        self.assertIn("#FF453A", home.saved_status_label.text())

        home._tick_saved_status_blink()
        self.assertIn("#5A1F24", home.saved_status_label.text())

        state_manager.state = "ST_SAVED"
        state_manager.is_locked = False
        state_manager.is_dirty = False
        home._refresh_saved_status_label(is_dirty=False)
        self.assertFalse(home._saved_status_blink_timer.isActive())
        self.assertIn("#34C759", home.saved_status_label.text())

    def test_saved_status_blue_blink_for_lite_and_heavy_learning(self):
        state_manager = SimpleNamespace(state="ST_SAVED", is_locked=False, is_dirty=False)
        editor = SimpleNamespace(sm=state_manager, _is_ai_processing=False)
        home = _DummyHome(editor)

        home._personalization_idle_trainer = SimpleNamespace(
            learning_status=lambda: {"active": True, "mode": "lite", "blink_interval_ms": 1000}
        )
        home._refresh_saved_status_label(is_dirty=False)
        self.assertTrue(home._saved_status_blink_timer.isActive())
        self.assertEqual(home._saved_status_blink_timer.interval(), 1000)
        self.assertIn("#0A84FF", home.saved_status_label.text())
        self.assertIn("Lite learning", home.saved_status_label.toolTip())

        home._personalization_idle_trainer = SimpleNamespace(
            learning_status=lambda: {"active": True, "mode": "heavy", "blink_interval_ms": 100}
        )
        home._refresh_saved_status_label(is_dirty=False)
        self.assertEqual(home._saved_status_blink_timer.interval(), 100)
        self.assertIn("#0A84FF", home.saved_status_label.text())
        self.assertIn("Heavy learning", home.saved_status_label.toolTip())

    def test_runtime_pressure_color_moves_to_app_title(self):
        state_manager = SimpleNamespace(state="ST_SAVED", is_locked=False, is_dirty=False)
        editor = SimpleNamespace(sm=state_manager, _is_ai_processing=False)
        home = _DummyHome(editor)
        home._runtime_resource_snapshot = {"pressure_stage": "warning"}
        home._runtime_resource_coordinator = SimpleNamespace(status_color=lambda _snapshot: "#FFD60A")

        home._refresh_saved_status_label(is_dirty=False)

        text = home.saved_status_label.text()
        self.assertIn("AI Subtitle Studio", text)
        self.assertIn("#FFD60A", text)

    def test_saved_status_refresh_does_not_force_sidebar_nav_refresh(self):
        state_manager = SimpleNamespace(state="ST_PROC", is_locked=True, is_dirty=False)
        editor = SimpleNamespace(sm=state_manager, _is_ai_processing=True)
        home = _DummyHome(editor)
        home._refresh_sidebar_nav_menu = patcher = SimpleNamespace(called=False)

        def _mark_called():
            patcher.called = True

        home._refresh_sidebar_nav_menu = _mark_called
        home._refresh_saved_status_label(is_dirty=False)

        self.assertFalse(patcher.called)

    def test_generation_progress_snapshot_tracks_elapsed_against_expected(self):
        state_manager = SimpleNamespace(state="ST_PROC", is_locked=True, is_dirty=False)
        status_lbl = QLabel("⏳ [STT] Whisper 중")
        editor = SimpleNamespace(sm=state_manager, _is_ai_processing=True, status_lbl=status_lbl, settings={"stt_ensemble_enabled": True})
        home = _DummyHome(editor)
        home._runtime_resource_snapshot = {
            "system_cpu_percent": 18.0,
            "process_cpu_percent": 56.0,
            "rss_gb": 0.23,
        }
        home._current_file_idx = 1
        home._total_files = 1
        home._real_pct = 0
        home._expected_seconds = {0: 600.0}
        home._file_start_times = {0: 1000.0}
        home._file_complete_times = {}
        home.queue_table = QTableWidget(1, 5)
        home.queue_table.setItem(0, 0, QTableWidgetItem("자막 생성 중"))
        home.queue_table.setItem(0, 4, QTableWidgetItem("00:00 / 10:00"))

        with patch("ui.home_sidebar.time.time", return_value=1120.0):
            snapshot = home._generation_progress_snapshot()

        self.assertTrue(snapshot["running"])
        self.assertEqual(snapshot["percent"], 20)
        self.assertEqual(snapshot["progressText"], "20%")
        self.assertEqual(snapshot["subtitle"], "02:00 / 10:00")
        self.assertEqual(snapshot["meta"], "CPU 18% · PROC 56% · RAM 0.23GB")
        self.assertIn("STT 1/2", snapshot["title"])

    def test_generation_progress_snapshot_treats_backend_fast_as_running(self):
        state_manager = SimpleNamespace(state="ST_IDLE", is_locked=False, is_dirty=False)
        status_lbl = QLabel("⏳ [STT] Whisper 중")
        editor = SimpleNamespace(sm=state_manager, _is_ai_processing=False, status_lbl=status_lbl, settings={})
        home = _DummyHome(editor)
        home.backend_fast = SimpleNamespace(_active=True)
        home.backend = None
        home._current_file_idx = 1
        home._total_files = 1
        home._real_pct = 0
        home._expected_seconds = {0: 600.0}
        home._file_start_times = {0: 1000.0}
        home._file_complete_times = {}
        home.queue_table = QTableWidget(1, 5)
        home.queue_table.setItem(0, 0, QTableWidgetItem("자막 생성 중"))
        home.queue_table.setItem(0, 4, QTableWidgetItem("00:00 / 10:00"))

        with patch("ui.home_sidebar.time.time", return_value=1120.0):
            snapshot = home._generation_progress_snapshot()

        self.assertTrue(snapshot["running"])
        self.assertEqual(snapshot["percent"], 20)
        self.assertEqual(snapshot["progressText"], "20%")
        self.assertEqual(snapshot["subtitle"], "02:00 / 10:00")

    def test_generation_progress_snapshot_keeps_running_for_active_queue_row_after_backend_flags_drop(self):
        state_manager = SimpleNamespace(state="ST_SAVED", is_locked=False, is_dirty=False)
        status_lbl = QLabel("⏳ [자막 메모리] 강제 정리 중")
        editor = SimpleNamespace(sm=state_manager, _is_ai_processing=False, status_lbl=status_lbl, settings={})
        home = _DummyHome(editor)
        home.backend_fast = None
        home.backend = None
        home._queue_execution_started_at = 1000.0
        home._current_file_idx = 1
        home._total_files = 1
        home._real_pct = 0
        home._expected_seconds = {0: 840.0}
        home._file_start_times = {0: 1000.0}
        home._file_complete_times = {}
        home.queue_table = QTableWidget(1, 5)
        home.queue_table.setItem(0, 0, QTableWidgetItem("자막 생성 중"))
        home.queue_table.setItem(0, 4, QTableWidgetItem("00:00 / 14:00"))

        with patch("ui.home_sidebar.time.time", return_value=1336.0):
            snapshot = home._generation_progress_snapshot()

        self.assertTrue(snapshot["running"])
        self.assertEqual(snapshot["percent"], 40)
        self.assertEqual(snapshot["progressText"], "40%")
        self.assertEqual(snapshot["subtitle"], "05:36 / 14:00")

    def test_generation_progress_snapshot_caps_running_progress_below_100_until_done(self):
        state_manager = SimpleNamespace(state="ST_PROC", is_locked=True, is_dirty=False)
        status_lbl = QLabel("⏳ [자막 LLM] 최적화 중")
        editor = SimpleNamespace(sm=state_manager, _is_ai_processing=True, status_lbl=status_lbl, settings={})
        home = _DummyHome(editor)
        home._current_file_idx = 1
        home._total_files = 1
        home._real_pct = 100
        home._expected_seconds = {0: 300.0}
        home._file_start_times = {0: 1000.0}
        home._file_complete_times = {}
        home.queue_table = QTableWidget(1, 5)
        home.queue_table.setItem(0, 0, QTableWidgetItem("자막 생성 중"))
        home.queue_table.setItem(0, 4, QTableWidgetItem("00:00 / 05:00"))

        with patch("ui.home_sidebar.time.time", return_value=1400.0):
            snapshot = home._generation_progress_snapshot()

        self.assertTrue(snapshot["running"])
        self.assertEqual(snapshot["percent"], 99)
        self.assertEqual(snapshot["progressText"], "99%")

    def test_generation_progress_snapshot_reaches_100_only_after_completion(self):
        state_manager = SimpleNamespace(state="ST_SAVED", is_locked=False, is_dirty=False)
        status_lbl = QLabel("✨ 자막 생성 완료")
        editor = SimpleNamespace(sm=state_manager, _is_ai_processing=False, status_lbl=status_lbl, settings={})
        home = _DummyHome(editor)
        home._current_file_idx = 1
        home._total_files = 1
        home._real_pct = 100
        home._expected_seconds = {0: 300.0}
        home._file_start_times = {0: 1000.0}
        home._file_complete_times = {0: 1280.0}
        home.queue_table = QTableWidget(1, 5)
        home.queue_table.setItem(0, 0, QTableWidgetItem("✅ 완료"))
        home.queue_table.setItem(0, 4, QTableWidgetItem("04:40 / 05:00"))

        with patch("ui.home_sidebar.time.time", return_value=1400.0):
            snapshot = home._generation_progress_snapshot()
            nav_item = home._sidebar_generation_nav_item()

        self.assertFalse(snapshot["running"])
        self.assertEqual(snapshot["percent"], 100)
        self.assertEqual(snapshot["subtitle"], "04:40 / 05:00")
        self.assertTrue(nav_item["progressVisible"])
        self.assertEqual(nav_item["progressPercent"], 100)
        self.assertEqual(nav_item["id"], "generation_status")
        self.assertEqual(nav_item["height"], 42)

    def test_generation_progress_snapshot_stays_running_while_post_generation_roughcut_is_pending(self):
        state_manager = SimpleNamespace(state="ST_SAVED", is_locked=False, is_dirty=False)
        status_lbl = QLabel("✨ 자막 생성 완료")
        editor = SimpleNamespace(
            sm=state_manager,
            _is_ai_processing=False,
            status_lbl=status_lbl,
            settings={"roughcut_llm_enabled": True},
            _roughcut_draft_pending=True,
            _roughcut_draft_cleanup_pending=lambda: True,
        )
        home = _DummyHome(editor)
        home._current_file_idx = 1
        home._total_files = 1
        home._real_pct = 100
        home._expected_seconds = {0: 600.0}
        home._file_start_times = {0: 1000.0}
        home._file_complete_times = {}
        home.queue_table = QTableWidget(1, 5)
        home.queue_table.setItem(0, 0, QTableWidgetItem("저장 준비 중"))
        home.queue_table.setItem(0, 4, QTableWidgetItem("00:00 / 10:00"))

        with patch("ui.home_sidebar.time.time", return_value=1120.0):
            snapshot = home._generation_progress_snapshot()

        self.assertTrue(snapshot["running"])
        self.assertEqual(snapshot["percent"], 20)
        self.assertEqual(snapshot["progressText"], "20%")
        self.assertEqual(snapshot["subtitle"], "02:00 / 10:00")

    def test_pipeline_completed_stage_keys_do_not_mark_roughcut_done_while_running(self):
        state_manager = SimpleNamespace(state="ST_SAVED", is_locked=False, is_dirty=False)
        status_lbl = QLabel("✨ 자막 생성 완료")
        settings = {
            "roughcut_llm_enabled": True,
            "roughcut_llm_provider": "openai",
            "roughcut_llm_model": "codex",
        }
        editor = SimpleNamespace(
            sm=state_manager,
            _is_ai_processing=False,
            status_lbl=status_lbl,
            settings=settings,
            _roughcut_draft_status="running",
            _roughcut_draft_pending=False,
            _last_roughcut_draft_major_count=12,
            _roughcut_draft_cleanup_pending=lambda: False,
            _roughcut_draft_runtime_enabled=lambda: True,
        )
        home = _DummyHome(editor)

        current_keys = home._pipeline_current_stage_keys(settings)
        completed_keys = home._pipeline_completed_stage_keys(settings, current_keys)

        self.assertEqual(current_keys, {"roughcut_llm"})
        self.assertNotIn("roughcut_llm", completed_keys)

    def test_generation_progress_snapshot_appends_completion_quality_score(self):
        state_manager = SimpleNamespace(state="ST_SAVED", is_locked=False, is_dirty=False)
        status_lbl = QLabel("✨ 자막 생성 완료")
        editor = SimpleNamespace(
            sm=state_manager,
            _is_ai_processing=False,
            status_lbl=status_lbl,
            settings={},
            _quality_summary=None,
            _get_current_segments=lambda: [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "자막",
                    "subtitle_quality_self_review_summary": {
                        "overall_score": 65.604955,
                    },
                }
            ],
        )
        home = _DummyHome(editor)
        home._current_file_idx = 1
        home._total_files = 1
        home._real_pct = 100
        home._expected_seconds = {0: 300.0}
        home._file_start_times = {0: 1000.0}
        home._file_complete_times = {0: 1280.0}
        home.queue_table = QTableWidget(1, 5)
        home.queue_table.setItem(0, 0, QTableWidgetItem("✅ 완료"))
        home.queue_table.setItem(0, 4, QTableWidgetItem("04:40 / 05:00"))

        with patch("ui.home_sidebar.time.time", return_value=1400.0):
            snapshot = home._generation_progress_snapshot()

        self.assertEqual(snapshot["subtitle"], "04:40 / 05:00 · 65.60")

    def test_status_rail_uses_green_flash_and_short_korean_stages(self):
        rail = StatusRail()
        try:
            flash_style = rail._state_style(True)
            self.assertIn("#34C759", flash_style)
            self.assertNotIn("#007AFF", flash_style)

            def editor_for(status, *, dirty=True, processing=True, stt_ensemble_enabled=True):
                label = QLabel(status)
                return SimpleNamespace(
                    status_lbl=label,
                    current_state="ST_PROC" if processing else "ST_COMP",
                    current_mode="MODE_AI_ALL",
                    _is_ai_processing=processing,
                    _is_dirty=dirty,
                    _stt_mode_enabled=False,
                    settings={"stt_ensemble_enabled": bool(stt_ensemble_enabled)},
                    _get_current_segments=lambda: [{"start": 0.0, "end": 1.0, "text": "테스트"}],
                )

            cases = {
                "⏳ [전처리] FFMPEG 오디오 추출 중": "전처리",
                "⏳ [STT] Whisper 중": "STT 1/2",
                "⏳ [자막 LLM] 최적화 중": "자막 LLM",
                "💾 자동 저장 중...": "저장",
                "저장 완료": "완료",
                "✨ 자막 생성 완료": "완료",
            }
            for status, expected in cases.items():
                self.assertEqual(rail._stage_text(EDITOR_MODE, editor_for(status)), expected)
            self.assertEqual(
                rail._stage_text(EDITOR_MODE, editor_for("⏳ [STT] Whisper 중", stt_ensemble_enabled=False)),
                "STT 1",
            )
            rail.state_button.setText("에디터 | 검토")
            initial_hint = rail.sizeHint().width()
            rail.state_button.setText("자막 생성 | 매우 긴 처리 상태 텍스트")
            self.assertEqual(rail.sizeHint().width(), initial_hint)
            stale_label = QLabel("자막 생성 중")
            completed_editor = SimpleNamespace(
                status_lbl=stale_label,
                current_state="ST_COMP",
                current_mode="MODE_AI_ALL",
                _is_ai_processing=False,
                _is_dirty=True,
                _stt_mode_enabled=False,
                _get_current_segments=lambda: [{"start": 0.0, "end": 1.0, "text": "테스트"}],
            )
            self.assertEqual(rail._stage_text(EDITOR_MODE, completed_editor), "완료")
        finally:
            rail.close()

    def test_refresh_cut_boundary_placeholder_preserves_editor_result_when_roughcut_is_empty(self):
        placeholder_result = {"segments": [{"major_id": "A", "title": "주제없음"}]}
        editor = SimpleNamespace(
            _roughcut_result=None,
            redraws=0,
        )

        def _refresh_from_project():
            editor._roughcut_result = dict(placeholder_result)

        editor._refresh_cut_boundary_placeholder_from_project = _refresh_from_project
        editor._redraw_timeline = lambda: setattr(editor, "redraws", int(editor.redraws) + 1)

        roughcut = SimpleNamespace(_result=None)
        refresh_calls = []
        roughcut.refresh_from_editor = lambda analyze_if_missing=False: refresh_calls.append(bool(analyze_if_missing))

        window = SimpleNamespace(
            _editor_widget=editor,
            _roughcut_widget=roughcut,
            _editor_roughcut_result={"stale": True},
        )

        SignalHandlersMixin._do_refresh_cut_boundary_placeholder(window)

        self.assertEqual(refresh_calls, [False])
        self.assertEqual(window._editor_roughcut_result, placeholder_result)
        self.assertEqual(editor.redraws, 1)

    def test_footer_menu_button_style_has_checked_feedback(self):
        from ui.editor.editor_widget import EditorWidget

        class _Editor:
            _footer_menu_button_style = EditorWidget._footer_menu_button_style

        editor = _Editor()
        style = editor._footer_menu_button_style(font_size="11px")

        self.assertIn("QPushButton:checked", style)
        self.assertIn("QPushButton:hover:checked", style)
        self.assertIn("border-color: #D7EBFF", style)

    def test_sync_footer_menu_button_states_marks_active_and_video_visible(self):
        from ui.editor.editor_widget import EditorWidget

        class _Editor:
            _sync_footer_menu_button_states = EditorWidget._sync_footer_menu_button_states

        btn_ai = QPushButton("AI")
        btn_ai.setCheckable(True)
        btn_spk = QPushButton("화자")
        btn_spk.setCheckable(True)
        btn_gap = QPushButton("간격")
        btn_gap.setCheckable(True)
        btn_vid = QPushButton("비디오")
        btn_vid.setCheckable(True)

        editor = _Editor()
        editor._footer_menu_buttons = {
            "ai": btn_ai,
            "speaker": btn_spk,
            "gap": btn_gap,
            "video": btn_vid,
        }
        editor._active_footer_menu_id = "speaker"
        editor.video_player = SimpleNamespace(isVisible=lambda: True)

        editor._sync_footer_menu_button_states()

        self.assertFalse(btn_ai.isChecked())
        self.assertTrue(btn_spk.isChecked())
        self.assertFalse(btn_gap.isChecked())
        self.assertTrue(btn_vid.isChecked())

    def test_invoke_footer_menu_action_resets_transient_selection_after_callback(self):
        from ui.editor.editor_widget import EditorWidget

        class _Editor:
            _sync_footer_menu_button_states = EditorWidget._sync_footer_menu_button_states
            _invoke_footer_menu_action = EditorWidget._invoke_footer_menu_action

        btn_ai = QPushButton("AI")
        btn_ai.setCheckable(True)
        editor = _Editor()
        editor._footer_menu_buttons = {"ai": btn_ai}
        editor._active_footer_menu_id = ""
        editor.video_player = None

        seen = []

        def _callback():
            seen.append(btn_ai.isChecked())

        editor._invoke_footer_menu_action("ai", _callback, transient=True)

        self.assertEqual(seen, [True])
        self.assertFalse(btn_ai.isChecked())
        self.assertEqual(editor._active_footer_menu_id, "")

    def test_status_rail_shows_generation_mode_while_processing(self):
        rail = StatusRail()
        try:
            label = QLabel("⏳ [전처리] FFMPEG 오디오 추출 및 기본 필터 적용 중...")
            editor = SimpleNamespace(
                status_lbl=label,
                current_state="ST_PROC",
                current_mode="MODE_AI_ALL",
                _is_ai_processing=True,
                _is_dirty=True,
                _stt_mode_enabled=False,
                _get_current_segments=lambda: [],
            )

            mode_text, _icon, _color = rail._mode_meta(EDITOR_MODE, editor)
            self.assertEqual(mode_text, "자막 생성")
            self.assertEqual(rail._stage_text(EDITOR_MODE, editor), "전처리")

            editor.current_state = "ST_EDITING"
            editor._is_ai_processing = False
            editor.status_lbl.setText("✏ 편집 중")
            mode_text, _icon, _color = rail._mode_meta(EDITOR_MODE, editor)
            self.assertEqual(mode_text, "에디터")
        finally:
            rail.close()

    def test_trim_vad_segments_before_keeps_prefix_and_clips_overlap(self):
        dummy = SimpleNamespace()
        rows = [
            {"start": 0.0, "end": 2.0},
            {"start": 2.5, "end": 5.0},
            {"start": 5.0, "end": 7.0},
        ]
        kept = EditorPipelineMixin._trim_vad_segments_before(dummy, rows, 4.0)
        self.assertEqual(
            kept,
            [
                {"start": 0.0, "end": 2.0},
                {"start": 2.5, "end": 4.0},
            ],
        )

    def test_trim_cut_boundary_state_for_partial_rerun_filters_project_and_ui_after_start(self):
        class _Sig:
            def __init__(self):
                self.emitted = []

            def emit(self, payload=None):
                self.emitted.append(payload)

        class _Timeline:
            def __init__(self):
                self.boundary_times = None
                self.scan_boundary_times = None

            def set_boundary_times(self, times):
                self.boundary_times = list(times)

            def set_scan_boundary_times(self, times):
                self.scan_boundary_times = list(times)

        with tempfile.TemporaryDirectory() as tmp:
            project_path = os.path.join(tmp, "sample.assp")
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": "03.15.00",
                        "user_settings": {},
                        "analysis": {
                            "cut_boundaries": [
                                {"timeline_sec": 10.0, "timeline_frame": 300, "fps": 30.0},
                                {"timeline_sec": 50.0, "timeline_frame": 1500, "fps": 30.0},
                            ],
                            "cut_boundary_provisional_boundaries": [
                                {"timeline_sec": 12.0, "timeline_frame": 360, "fps": 30.0, "status": "provisional"},
                                {"timeline_sec": 55.0, "timeline_frame": 1650, "fps": 30.0, "status": "provisional"},
                            ],
                            "cut_boundary_prescan_done": True,
                            "cut_boundary_cache_path": "/tmp/cache.json",
                            "cut_boundary_cache_type": "cut_boundaries_only",
                        },
                    },
                    f,
                    ensure_ascii=False,
                )

            sig_boundaries = _Sig()
            sig_refresh = _Sig()
            backend = SimpleNamespace(
                _cut_boundary_pipeline_cache={"old": True},
                _cut_boundary_provisional_rows=[],
            )
            main_w = SimpleNamespace(
                _current_project_path=project_path,
                _project_boundary_times=[10.0, 50.0],
                _sig_update_project_boundary_times=sig_boundaries,
                _sig_refresh_cut_boundary_placeholder=sig_refresh,
                backend=backend,
            )
            timeline = _Timeline()
            editor = SimpleNamespace(
                window=lambda: main_w,
                _auto_cut_boundary_scan_lines=[
                    {"timeline_sec": 12.0, "timeline_frame": 360, "fps": 30.0, "status": "provisional"},
                    {"timeline_sec": 55.0, "timeline_frame": 1650, "fps": 30.0, "status": "provisional"},
                ],
                timeline=timeline,
            )
            editor._trim_cut_boundary_rows_before = lambda rows, cutoff: EditorPipelineMixin._trim_cut_boundary_rows_before(editor, rows, cutoff)
            editor._set_auto_cut_boundary_scan_lines = lambda rows: setattr(editor, "_auto_cut_boundary_scan_lines", list(rows))

            EditorPipelineMixin._trim_cut_boundary_state_for_partial_rerun(editor, 40.0)

            self.assertEqual(len(main_w._project_boundary_times), 1)
            self.assertEqual(main_w._project_boundary_times[0]["timeline_sec"], 10.0)
            self.assertEqual(len(timeline.boundary_times), 1)
            self.assertEqual(timeline.boundary_times[0]["timeline_sec"], 10.0)
            self.assertEqual(len(editor._auto_cut_boundary_scan_lines), 1)
            self.assertEqual(editor._auto_cut_boundary_scan_lines[0]["timeline_sec"], 12.0)
            self.assertEqual(len(sig_boundaries.emitted[-1]), 1)
            self.assertEqual(sig_boundaries.emitted[-1][0]["timeline_sec"], 10.0)
            self.assertIsNone(backend._cut_boundary_pipeline_cache)
            self.assertEqual(len(backend._cut_boundary_provisional_rows), 1)

            saved = read_project_storage_payload(project_path)
            saved_analysis = saved.get("analysis", {})
            self.assertEqual(len(saved_analysis.get("cut_boundaries", [])), 1)
            self.assertEqual(saved_analysis["cut_boundaries"][0]["timeline_sec"], 10.0)
            self.assertEqual(len(saved_analysis.get("cut_boundary_provisional_boundaries", [])), 1)
            self.assertEqual(saved_analysis["cut_boundary_provisional_boundaries"][0]["timeline_sec"], 12.0)
            self.assertNotIn("cut_boundary_prescan_done", saved_analysis)
            self.assertNotIn("cut_boundary_cache_path", saved_analysis)
            self.assertNotIn("cut_boundary_cache_type", saved_analysis)

    def test_progress_ticks_do_not_overwrite_active_stage_status(self):
        state_manager = SubtitleStateManager()
        state_manager.start_ai_all()
        state_manager.set_custom_status("⏳ LLM 최적화 중")
        state_manager.update_progress(1, 3, 33)
        self.assertIn("LLM", state_manager._status_msg)

    def test_start_pipeline_marks_processing_before_cut_prescan_and_schedules_waveform(self):
        class DummyEditor(EditorPipelineMixin):
            def __init__(self):
                self.sm = SubtitleStateManager()
                self.settings = {}
                self.is_auto_start = False
                self.calls = []
                self._deferred_open_waveform_path = "/tmp/clip.mp4"
                self._deferred_open_waveform_loaded = False
                self.main = SimpleNamespace(
                    _stop_post_completion_idle_timer=lambda: None,
                    sync_menu_from_editor=lambda editor=None: self.calls.append(("sync", self.sm.state)),
                )

            def window(self):
                return self.main

            def _snapshot_start_layout(self):
                return {}

            def _prepare_cut_boundaries_before_start(self):
                self.calls.append(("prescan", self.sm.state, self.sm._button_text, self.sm._status_msg))

            def _load_deferred_open_waveform(self, *, reason=""):
                self.calls.append(("waveform", reason, self.sm.state, self.sm._status_msg))
                return True

            def _execute_pipeline_logic(self, is_restart):
                self.calls.append(("execute", self.sm.state, self.sm._button_text, self.sm._status_msg))

            def _restore_start_layout(self, snap):
                self.calls.append(("restore", self.sm.state))

        editor = DummyEditor()
        scheduled = []

        with patch("core.settings.load_settings", return_value={}), patch(
            "ui.editor.editor_pipeline_startup.QTimer.singleShot",
            side_effect=lambda delay, callback: scheduled.append((int(delay), callback)),
        ):
            editor._start_pipeline(is_restart=False)

        prescan = [item for item in editor.calls if item[0] == "prescan"][0]
        self.assertNotIn("waveform", [item[0] for item in editor.calls])
        self.assertEqual([delay for delay, _callback in scheduled], [260])
        self.assertEqual(prescan[1], SubtitleStateManager.ST_PROC)
        self.assertIn("정지", prescan[2])
        self.assertIn("시작 준비", prescan[3])

        scheduled[0][1]()
        self.assertIn(("waveform", "pipeline_start", SubtitleStateManager.ST_PROC, prescan[3]), editor.calls)

    def test_prepare_cut_boundaries_before_start_forces_rescan_for_existing_project(self):
        class _Backend:
            def __init__(self):
                self.calls = []
                self._force_cut_boundary_rescan_once = False
                self._cut_boundary_prescan_completed = True

            def _auto_scan_cut_boundaries_for_start(self, project_path, files):
                self.calls.append((project_path, list(files or [])))

        class DummyEditor(EditorPipelineMixin):
            def __init__(self, main, media_path):
                self.main = main
                self.media_path = media_path
                self.settings = {}

            def window(self):
                return self.main

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sample.mp4")
            project_path = os.path.join(tmp, "sample.assp")
            open(media_path, "wb").close()
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump({"analysis": {"cut_boundary_prescan_done": True}}, f, ensure_ascii=False)

            backend = _Backend()
            main = SimpleNamespace(
                backend=backend,
                _multiclip_files=[],
                _current_project_path=project_path,
            )
            editor = DummyEditor(main, media_path)

            editor._prepare_cut_boundaries_before_start()

        self.assertEqual(backend.calls, [(project_path, [media_path])])
        self.assertTrue(backend._force_cut_boundary_rescan_once)
        self.assertFalse(backend._cut_boundary_prescan_completed)

    def test_prepare_cut_boundaries_before_start_forces_rescan_for_new_project_too(self):
        class _Backend:
            def __init__(self):
                self.calls = []
                self._force_cut_boundary_rescan_once = False
                self._cut_boundary_prescan_completed = True

            def _auto_scan_cut_boundaries_for_start(self, project_path, files):
                self.calls.append((project_path, list(files or [])))

        class DummyEditor(EditorPipelineMixin):
            def __init__(self, main, media_path):
                self.main = main
                self.media_path = media_path
                self.settings = {"example": True}

            def window(self):
                return self.main

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sample.mp4")
            project_path = os.path.join(tmp, "created.assp")
            open(media_path, "wb").close()

            backend = _Backend()
            main = SimpleNamespace(
                backend=backend,
                _multiclip_files=[],
                _current_project_path="",
            )
            editor = DummyEditor(main, media_path)

            with patch("ui.editor.editor_pipeline_startup.create_project", return_value=project_path) as create_mock:
                editor._prepare_cut_boundaries_before_start()

        self.assertEqual(backend.calls, [(project_path, [media_path])])
        self.assertEqual(main._current_project_path, project_path)
        create_mock.assert_called_once_with(
            name="sample",
            media_paths=[media_path],
            srt_path=os.path.join(tmp, "sample.srt"),
            user_settings={"example": True},
            prefill_analysis_artifacts=False,
        )
        self.assertTrue(backend._force_cut_boundary_rescan_once)
        self.assertFalse(backend._cut_boundary_prescan_completed)

    def test_stop_pipeline_clears_pending_editor_work_before_backend_stop(self):
        class _Timer:
            def __init__(self):
                self.stopped = False

            def stop(self):
                self.stopped = True

        class _Event:
            def __init__(self):
                self.set_called = False

            def set(self):
                self.set_called = True

        class _Backend:
            def __init__(self):
                self._active = True
                self._edit_event = _Event()
                self._start_event = _Event()
                self.stop_called = False

            def stop(self, *, log_context="파이프라인 중단"):
                self.stop_called = True
                self.stop_context = log_context
                self._active = False

        class DummyEditor(EditorPipelineMixin):
            def __init__(self):
                self.sm = SubtitleStateManager()
                self.sm.start_ai_all()
                self._segment_queue = [{"text": "pending"}]
                self._live_editor_preview_queue = [{"text": "preview"}]
                self._live_editor_preview_keys = {("STT1", 0.0, 1.0, "preview")}
                self._pending_cursor_video_seek_sec = 12.3
                self._queue_timer = _Timer()
                self._live_editor_preview_timer = _Timer()
                self._timeline_timer = _Timer()
                self._video_context_refresh_timer = _Timer()
                self._cursor_video_seek_timer = _Timer()
                self._spinner_timer = _Timer()
                self.main = SimpleNamespace(
                    _stop_post_completion_idle_timer=lambda: None,
                    backend_fast=None,
                    backend=_Backend(),
                    _unlock_workspace_sidebar_width=lambda: None,
                )

            def window(self):
                return self.main

        editor = DummyEditor()

        with patch("ui.editor.editor_pipeline.QTimer.singleShot") as single_shot:
            editor._stop_pipeline()

        self.assertEqual(editor._segment_queue, [])
        self.assertEqual(editor._live_editor_preview_queue, [])
        self.assertEqual(editor._live_editor_preview_keys, set())
        self.assertIsNone(editor._pending_cursor_video_seek_sec)
        self.assertTrue(editor._queue_timer.stopped)
        self.assertTrue(editor._live_editor_preview_timer.stopped)
        self.assertTrue(editor._timeline_timer.stopped)
        self.assertTrue(editor._video_context_refresh_timer.stopped)
        self.assertTrue(editor._cursor_video_seek_timer.stopped)
        self.assertTrue(editor.main.backend.stop_called)
        self.assertTrue(editor.main.backend._edit_event.set_called)
        self.assertTrue(editor.main.backend._start_event.set_called)
        self.assertEqual(editor.main.backend.stop_context, "작업 중지")
        single_shot.assert_any_call(120, editor._safe_enable_start_btn)

    def test_state_machine_progress_only_update_skips_redundant_menu_sync(self):
        from ui.editor.editor_widget import EditorWidget

        class _Label:
            def __init__(self):
                self._text = ""

            def setText(self, text):
                self._text = str(text)

            def text(self):
                return self._text

        class _Button:
            def __init__(self):
                self.text_value = ""
                self.enabled_value = True
                self.calls = 0

            def setText(self, text):
                self.calls += 1
                self.text_value = str(text)

            def setEnabled(self, enabled):
                self.calls += 1
                self.enabled_value = bool(enabled)

        class _Editor:
            _on_state_machine_update = EditorWidget._on_state_machine_update
            _clean_action_label = EditorWidget._clean_action_label

            def __init__(self):
                self._is_ai_processing = False
                self._is_dirty = False
                self.status_lbl = _Label()
                self.btn_start = _Button()
                self.apply_lock_calls = 0
                self.menu_sync_calls = 0
                self.saved_refresh_calls = 0
                self.main = SimpleNamespace(
                    sync_menu_from_editor=lambda _editor: setattr(self, "menu_sync_calls", self.menu_sync_calls + 1),
                    _refresh_saved_status_label=lambda **_kwargs: setattr(self, "saved_refresh_calls", self.saved_refresh_calls + 1),
                )

            def window(self):
                return self.main

            def _apply_text_editor_lock_state(self):
                self.apply_lock_calls += 1

            def _apply_processing_canvas_lock_state(self):
                pass

        editor = _Editor()

        editor._on_state_machine_update("MODE_AI_ALL", "ST_PROC", True, True, "처리중 (1/10)", "■ 정지", True)
        editor._on_state_machine_update("MODE_AI_ALL", "ST_PROC", True, True, "처리중 (2/10)", "■ 정지", True)

        self.assertEqual(editor.menu_sync_calls, 1)
        self.assertEqual(editor.saved_refresh_calls, 1)
        self.assertEqual(editor.status_lbl.text(), "처리중 (2/10)")
        self.assertEqual(editor.btn_start.text_value, "정지")
        self.assertTrue(editor.btn_start.enabled_value)

    def test_processing_lock_uses_selection_lock_for_text_editor(self):
        from ui.editor.editor_widget import EditorWidget

        class _TextEdit:
            def __init__(self):
                self.selection_locked_calls = []

            def set_selection_locked(self, locked):
                self.selection_locked_calls.append(bool(locked))

        class _Editor:
            _apply_text_editor_lock_state = EditorWidget._apply_text_editor_lock_state

            def __init__(self):
                self.text_edit = _TextEdit()
                self.sm = SimpleNamespace(is_locked=True)

            def _timeline_lock_edit_enabled(self):
                return False

        editor = _Editor()

        editor._apply_text_editor_lock_state()

        self.assertEqual(editor.text_edit.selection_locked_calls, [True])

    def test_processing_lock_updates_canvas_input_lock(self):
        from ui.editor.editor_widget import EditorWidget

        class _Canvas:
            def __init__(self):
                self.properties = {}
                self._editor_processing_input_locked = False

            def setProperty(self, key, value):
                self.properties[key] = value

        class _Timeline:
            def __init__(self):
                self.canvas = _Canvas()

        class _Editor:
            _apply_processing_canvas_lock_state = EditorWidget._apply_processing_canvas_lock_state

            def __init__(self):
                self.timeline = _Timeline()
                self.sm = SimpleNamespace(is_locked=True)

        editor = _Editor()

        editor._apply_processing_canvas_lock_state()

        self.assertTrue(editor.timeline.canvas._editor_processing_input_locked)
        self.assertTrue(editor.timeline.canvas.properties["editor_processing_input_locked"])

    def test_queue_completion_status_completes_editor_state(self):
        class DummyQueue(QueueMixin):
            def __init__(self):
                self.synced = False
                self.refreshed_dirty = None
                self.editor = SimpleNamespace(sm=SubtitleStateManager(), is_auto_start=False)
                self.editor.sm.start_ai_all()
                self.editor._set_process_completed = self._complete_editor
                self.editor._has_unsaved_changes = lambda: True
                self._editor_widget = self.editor

            def _complete_editor(self):
                self.editor.sm.complete_ai()

            def sync_menu_from_editor(self, editor=None):
                self.synced = editor is self.editor

            def _refresh_saved_status_label(self, is_dirty=None, touch_saved_time=False):
                self.refreshed_dirty = is_dirty

        queue = DummyQueue()
        queue._sync_editor_stage_from_queue_status("✅ 자막 생성 완료")
        self.assertEqual(queue.editor.sm.state, SubtitleStateManager.ST_COMP)
        self.assertIn("완료", queue.editor.sm._status_msg)
        self.assertTrue(queue.synced)
        self.assertIs(queue.refreshed_dirty, True)

    def test_final_queue_header_marks_remaining_rows_done(self):
        class DummyTimer:
            def __init__(self):
                self.stopped = False

            def start(self, _interval):
                pass

            def stop(self):
                self.stopped = True

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()
                self.synced = False

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                self.synced = True

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])
        queue.update_queue_status(0, "✅ 완료")
        queue.update_queue_header(2, 2, 100, "")

        statuses = [
            queue.queue_table.item(row, 0).text()
            for row in range(queue.queue_table.rowCount())
        ]
        self.assertEqual(statuses, ["✅ 완료", "대기 중"])
        self.assertFalse(queue._live_timer.stopped)
        self.assertTrue(queue.synced)

    def test_checked_queue_completion_status_is_done_but_plain_text_is_active(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = DummyQueue()
        self.assertEqual(queue._queue_status_flags("✅ 자막 생성 완료"), (True, False, False))
        self.assertEqual(queue._queue_status_flags("자막 생성 완료"), (False, False, True))
        self.assertEqual(queue._queue_status_flags("✅ 컷 경계 완료"), (False, False, True))

    def test_final_queue_header_does_not_complete_active_processing_row(self):
        class DummyTimer:
            def __init__(self):
                self.stopped = False

            def start(self, _interval):
                pass

            def stop(self):
                self.stopped = True

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue.update_queue_status(0, "저장 준비 중")
        queue.update_queue_header(1, 1, 100, "")

        self.assertEqual(queue.queue_header_lbl.text(), "큐 리스트 : (1/1) - 99% 완료")
        self.assertEqual(queue.queue_table.item(0, 0).text(), "저장 준비 중")
        self.assertFalse(queue._live_timer.stopped)

        queue.update_queue_status(0, "✅ 완료")
        queue.update_queue_header(1, 1, 100, "")
        self.assertEqual(queue.queue_header_lbl.text(), "큐 리스트 : (1/1) - 100% 완료")
        self.assertTrue(queue._live_timer.stopped)

    def test_manual_save_syncs_single_queue_row_to_complete(self):
        class DummyMain(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = SimpleNamespace(start=lambda _interval: None, stop=lambda: None)

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        class DummyEditor(EditorActionsMixin):
            def __init__(self, main_w):
                self._main_w = main_w
                self.media_path = "/tmp/clip_a.mp4"

            def window(self):
                return self._main_w

        main_w = DummyMain()
        main_w.init_queue_list(["/tmp/clip_a.mp4"])
        main_w.update_queue_status(0, "저장 준비 중")

        editor = DummyEditor(main_w)
        editor._sync_queue_saved_state()

        self.assertEqual(main_w.queue_table.item(0, 0).text(), "✅ 완료")
        self.assertEqual(main_w.queue_header_lbl.text(), "큐 리스트 : (1/1) - 100% 완료")

    def test_queue_status_refreshes_sidebar_engine_info_on_completion(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self.engine_refresh_count = 0
                self._live_timer = DummyTimer()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

            def _refresh_sidebar_engine_info(self):
                self.engine_refresh_count += 1

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        before = queue.engine_refresh_count

        queue.update_queue_status(0, "✅ 완료")
        queue.update_queue_header(1, 1, 100, "")

        self.assertGreaterEqual(queue.engine_refresh_count, before + 2)

    def test_completed_queue_row_keeps_done_highlight_when_next_clip_starts(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()
                self.synced = False

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                self.synced = True

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])
        queue.update_queue_status(0, "✅ 완료")
        done_bg = queue.queue_table.item(0, 0).background().color().name().upper()

        queue.update_queue_header(2, 2, 0, "")
        queue.update_queue_status(1, "⏳ 오디오 추출 중")

        self.assertIn("완료", queue.queue_table.item(0, 0).text())
        self.assertEqual(queue.queue_table.item(0, 0).background().color().name().upper(), done_bg)
        queue._refresh_sidebar_queue_cache()
        self.assertTrue(queue._sidebar_queue_cache_items[0]["done"])
        self.assertTrue(queue._sidebar_queue_cache_items[1]["active"])

    def test_completed_queue_row_ignores_late_non_terminal_updates(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()
                self.synced = False

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                self.synced = True

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4", "/tmp/clip_c.mp4"])
        queue.update_queue_status(0, "✅ 완료")
        queue.update_queue_status(1, "✅ 완료")
        row0_bg = queue.queue_table.item(0, 0).background().color().name().upper()
        row1_bg = queue.queue_table.item(1, 0).background().color().name().upper()

        queue.update_queue_status(0, "컷 경계 확인 중 50%", "66", "", "")
        queue.update_queue_status(1, "🎥 자막영상출력(mov)", "10", "", "")
        queue.update_queue_status(2, "컷 경계 확인 중 10%", "", "", "")

        self.assertEqual(queue.queue_table.item(0, 0).text(), "✅ 완료")
        self.assertEqual(queue.queue_table.item(1, 0).text(), "✅ 완료")
        self.assertEqual(queue.queue_table.item(0, 0).background().color().name().upper(), row0_bg)
        self.assertEqual(queue.queue_table.item(1, 0).background().color().name().upper(), row1_bg)
        self.assertIn("컷 경계", queue.queue_table.item(2, 0).text())
        queue._refresh_sidebar_queue_cache()
        self.assertTrue(queue._sidebar_queue_cache_items[0]["done"])
        self.assertTrue(queue._sidebar_queue_cache_items[1]["done"])
        self.assertTrue(queue._sidebar_queue_cache_items[2]["active"])

    def test_completed_queue_row_resets_when_same_clip_restarts(self):
        class DummyTimer:
            def __init__(self):
                self.started = False
                self.stopped = False

            def start(self, _interval):
                self.started = True

            def stop(self):
                self.stopped = True

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()
                self.synced = False

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                self.synced = True

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue.update_queue_status(0, "✅ 완료")
        queue.update_queue_header(1, 1, 100, "")
        self.assertEqual(queue.queue_header_lbl.text(), "큐 리스트 : (1/1) - 100% 완료")
        self.assertTrue(queue._queue_status_flags(queue.queue_table.item(0, 0).text())[0])
        self.assertIn(0, queue._file_complete_times)

        queue.update_queue_status(0, "⏳ 오디오 추출 중")
        queue.update_queue_header(1, 1, 0, "")

        self.assertEqual(queue.queue_table.item(0, 0).text(), "⏳ 오디오 추출 중")
        self.assertEqual(queue.queue_table.item(0, 4).text(), "계산 중")
        self.assertEqual(queue.queue_header_lbl.text(), "큐 리스트 : (1/1) - 0% 완료")
        self.assertNotIn(0, queue._file_complete_times)
        queue._refresh_sidebar_queue_cache()
        self.assertFalse(queue._sidebar_queue_cache_items[0]["done"])
        self.assertTrue(queue._sidebar_queue_cache_items[0]["active"])
        self.assertTrue(queue._live_timer.started)

    def test_completed_queue_row_resets_when_same_clip_restarts_from_llm_stage(self):
        class DummyTimer:
            def __init__(self):
                self.started = False
                self.stopped = False

            def start(self, _interval):
                self.started = True

            def stop(self):
                self.stopped = True

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()
                self.synced = False

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                self.synced = True

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue.update_queue_status(0, "✅ 완료")
        queue.update_queue_header(1, 1, 100, "")

        queue.update_queue_status(0, "⏳ [STT+자막 LLM] 인식 결과 교정/분리 중")

        self.assertEqual(queue.queue_table.item(0, 0).text(), "⏳ [STT+자막 LLM] 인식 결과 교정/분리 중")
        self.assertNotIn(0, queue._file_complete_times)
        queue._refresh_sidebar_queue_cache()
        self.assertFalse(queue._sidebar_queue_cache_items[0]["done"])
        self.assertTrue(queue._sidebar_queue_cache_items[0]["active"])
        self.assertTrue(queue._live_timer.started)

    def test_queue_visuals_allow_only_current_row_active(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4", "/tmp/clip_c.mp4"])
        queue._current_file_idx = 3
        queue.queue_table.item(0, 0).setText("컷 경계 확인 중 50%")
        queue.queue_table.item(1, 0).setText("🎥 자막영상출력(mov)")
        queue.queue_table.item(2, 0).setText("⏳ Whisper 중")
        for row in range(queue.queue_table.rowCount()):
            queue._apply_queue_row_visual_state(row)

        queue._refresh_sidebar_queue_cache()
        active_rows = [
            row
            for row, item in enumerate(queue._sidebar_queue_cache_items)
            if item["active"]
        ]
        self.assertEqual(active_rows, [2])
        self.assertNotEqual(queue.queue_table.item(0, 0).foreground().color().name().upper(), COLORS["warning"])
        self.assertNotEqual(queue.queue_table.item(1, 0).foreground().color().name().upper(), COLORS["warning"])
        self.assertEqual(queue.queue_table.item(2, 0).foreground().color().name().upper(), COLORS["warning"])

    def test_queue_header_advance_repairs_prior_incomplete_rows(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()
                self.synced = False

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                self.synced = True

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4", "/tmp/clip_c.mp4"])
        queue.update_queue_status(0, "컷 경계 확인 중 50%")
        queue.update_queue_status(1, "🎥 자막영상출력(mov)")
        queue.update_queue_header(3, 3, 5, "")

        self.assertEqual(queue.queue_table.item(0, 0).text(), "✅ 완료")
        self.assertEqual(queue.queue_table.item(1, 0).text(), "✅ 완료")
        self.assertEqual(queue.queue_table.item(2, 0).text(), "대기 중")
        queue._refresh_sidebar_queue_cache()
        self.assertTrue(queue._sidebar_queue_cache_items[0]["done"])
        self.assertTrue(queue._sidebar_queue_cache_items[1]["done"])
        self.assertFalse(queue._sidebar_queue_cache_items[2]["done"])

    def test_pending_eta_update_does_not_mark_prior_rows_done(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])
        queue.update_queue_status(1, "대기 중", "20", "1920x1080", "00:10")

        self.assertEqual(queue.queue_table.item(0, 0).text(), "대기 중")
        self.assertEqual(queue.queue_table.item(1, 0).text(), "대기 중")

    def test_queue_update_methods_accept_structured_payload_dicts(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])
        queue.update_queue_status(
            {
                "row": 1,
                "status": "대기 중",
                "eta": "20",
                "info": "1920x1080",
                "duration": "00:10",
            }
        )
        queue.update_queue_header({"idx": 2, "total": 2, "pct": 50, "eta": "2분 10초"})

        self.assertEqual(queue.queue_table.item(1, 2).text(), "1920x1080")
        self.assertEqual(queue.queue_table.item(1, 3).text(), "00:10")
        self.assertEqual(queue.queue_table.item(1, 4).text(), "00:20")
        self.assertIn("(2/2) - 50%", queue.queue_header_lbl.text())

    def test_late_eta_header_does_not_rewind_current_queue_index(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4", "/tmp/clip_c.mp4"])
        queue.update_queue_header(3, 3, 5, "")
        queue.update_queue_header(1, 3, 0, "2분 10초")

        self.assertEqual(queue._current_file_idx, 3)
        self.assertEqual(queue._real_pct, 5)
        self.assertIn("(3/3) - 5%", queue.queue_header_lbl.text())
        self.assertEqual(queue.queue_table.item(0, 0).text(), "✅ 완료")
        self.assertEqual(queue.queue_table.item(1, 0).text(), "✅ 완료")

    def test_late_pending_eta_does_not_clear_active_queue_row(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])
        queue.update_queue_status(1, "컷 경계 확인 중 50%")
        queue.update_queue_status(1, "대기 중", "20", "1920x1080", "00:10")

        self.assertEqual(queue.queue_table.item(1, 0).text(), "컷 경계 확인 중 50%")
        self.assertEqual(queue.queue_table.item(1, 2).text(), "1920x1080")
        self.assertEqual(queue.queue_table.item(1, 3).text(), "00:10")
        queue._refresh_sidebar_queue_cache()
        self.assertEqual(queue._sidebar_queue_cache_items[1]["eta"], "00:00 / 00:20")

    def test_cut_boundary_active_row_updates_elapsed_time_per_clip(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyBackend:
            def __init__(self):
                self._active = True
                self.pipeline_start_time = 100.0

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()
                self.backend = DummyBackend()
                self.backend_fast = None

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])

        with patch("ui.queue_widget.time.time", return_value=100.0):
            queue.update_queue_status(0, "컷 경계 확인 중 5%", "57:31", "", "57:31")

        self.assertIn(0, queue._file_start_times)
        self.assertEqual(queue.queue_table.item(0, 4).text(), "00:00 / 57:31")

        with patch("ui.queue_widget.time.time", return_value=105.0):
            queue._update_live_queue_header()

        self.assertEqual(queue.queue_table.item(0, 4).text(), "00:05 / 57:31")
        queue._refresh_sidebar_queue_cache()
        self.assertEqual(queue._sidebar_queue_cache_items[0]["eta"], "00:05 / 57:31")

    def test_active_row_elapsed_time_keeps_ticking_without_backend_active_flag(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()
                self.backend = SimpleNamespace(_active=False, pipeline_start_time=0.0)
                self.backend_fast = None

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])

        with patch("ui.queue_widget.time.time", return_value=100.0):
            queue.update_queue_status(0, "[STT] STT1/STT2 병렬 인식 중", "15:54", "", "15:54")

        with patch("ui.queue_widget.time.time", return_value=130.0):
            queue._update_live_queue_header()

        self.assertNotIn(0, queue._file_start_times)
        self.assertEqual(queue.queue_table.item(0, 4).text(), "15:54")

        queue.backend.pipeline_start_time = 100.0
        with patch("ui.queue_widget.time.time", return_value=306.0):
            queue._update_live_queue_header()

        self.assertEqual(queue.queue_table.item(0, 4).text(), "03:26 / 15:54")
        self.assertEqual(queue._sidebar_queue_cache_items[0]["eta"], "03:26 / 15:54")

    def test_zero_or_unknown_queue_eta_displays_unavailable(self):
        class DummyTimer:
            def start(self, _interval):
                pass

            def stop(self):
                pass

        class DummyBackend:
            def __init__(self):
                self._active = True
                self.pipeline_start_time = 100.0

        class DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._live_timer = DummyTimer()
                self.backend = DummyBackend()
                self.backend_fast = None

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])

        with patch("ui.queue_widget.time.time", return_value=100.0):
            queue.update_queue_status(0, "[음성] ClearVoice 음성 향상 중", "00:00", "", "00:00")

        self.assertEqual(queue.queue_table.item(0, 4).text(), "00:00 / 예상불가")

        with patch("ui.queue_widget.time.time", return_value=105.0):
            queue._update_live_queue_header()

        self.assertEqual(queue.queue_table.item(0, 4).text(), "00:05 / 예상불가")
        queue._refresh_sidebar_queue_cache()
        self.assertEqual(queue._sidebar_queue_cache_items[0]["eta"], "00:05 / 예상불가")
        self.assertEqual(queue._queue_card_time_text("11:11 / 00:00", "-"), "11:11 / 예상불가")

    def test_restart_queue_eta_metadata_restarts_media_duration_probe(self):
        from ui.main.main_window import MainWindow

        class ImmediateThread:
            def __init__(self, target=None, daemon=None, name=None):
                self.target = target
                self.daemon = daemon
                self.name = name
                self.started = False

            def start(self):
                self.started = True
                if callable(self.target):
                    self.target()

        class Backend:
            def __init__(self):
                self.files_to_process = ["old.mp4"]
                self._show_queue_for_current_run = False
                self._video_durations = {"old.mp4": 12.0}
                self.called = False

            def _precalculate_etas(self):
                self.called = True

        window = MainWindow()
        backend = Backend()
        try:
            with patch("ui.main.main_window.threading.Thread", ImmediateThread):
                window._restart_queue_eta_metadata(backend, ["/tmp/new.mp4"])

            self.assertTrue(backend.called)
            self.assertEqual(backend.files_to_process, ["/tmp/new.mp4"])
            self.assertTrue(backend._show_queue_for_current_run)
            self.assertEqual(backend._video_durations, {})
            self.assertEqual(backend._eta_thread.name, "eta-calculator-restart")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_save_clears_dirty_until_real_subtitle_edit(self):
        from ui.editor.editor_widget import EditorWidget

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sample.m4a")
            open(media_path, "wb").close()
            editor = EditorWidget(
                "sample.m4a",
                [{"start": 0.0, "end": 1.0, "text": "첫 자막", "speaker": "00"}],
                media_path=media_path,
            )
            try:
                editor._flush_queue()
                editor._mark_initial_segments_saved()
                self.assertFalse(editor._has_unsaved_changes())
                self.assertFalse(editor.sm.is_dirty)

                cur = editor.text_edit.textCursor()
                cur.movePosition(QTextCursor.MoveOperation.End)
                cur.insertText(" 수정")
                editor.text_edit.setTextCursor(cur)
                editor._app_start_time = 0
                editor._on_text_edited()
                self.assertTrue(editor._has_unsaved_changes())
                self.assertTrue(editor.sm.is_dirty)

                editor._auto_save_project = lambda segs=None: None
                scheduled_exports = []
                editor._schedule_auto_export_saved_subtitle_videos = lambda: scheduled_exports.append(True)
                self.assertTrue(editor._on_save(skip_auto_next=True))
                self.assertEqual(scheduled_exports, [])
                self.assertFalse(editor._has_unsaved_changes())
                self.assertFalse(editor.sm.is_dirty)

                editor._on_text_edited()
                self.assertFalse(editor._has_unsaved_changes())
                self.assertFalse(editor.sm.is_dirty)

                class SavedQueue(QueueMixin):
                    def __init__(self, target):
                        self._editor_widget = target
                        self.refreshed_dirty = None

                    def sync_menu_from_editor(self, editor=None):
                        pass

                    def _refresh_saved_status_label(self, is_dirty=None, touch_saved_time=False):
                        self.refreshed_dirty = is_dirty

                saved_queue = SavedQueue(editor)
                saved_queue._sync_editor_stage_from_queue_status("✅ 자막생성완료")
                self.assertIs(saved_queue.refreshed_dirty, False)
                self.assertFalse(editor.sm.is_dirty)

                prompted = []
                editor._show_confirm_dialog = lambda *args, **kwargs: prompted.append(True)
                exited = []
                editor.sig_exit.connect(lambda *args: exited.append(True))
                editor._on_exit()
                self.assertFalse(prompted)
                self.assertTrue(exited)
            finally:
                editor.close()

    def test_segment_timing_edit_after_save_prompts_on_editor_exit(self):
        from ui.editor.editor_widget import EditorWidget

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sample.m4a")
            open(media_path, "wb").close()
            editor = EditorWidget(
                "sample.m4a",
                [{"start": 0.0, "end": 1.0, "text": "첫 자막", "speaker": "00"}],
                media_path=media_path,
            )
            try:
                editor._flush_queue()
                editor._mark_initial_segments_saved()
                editor._skip_prev_confirm_once = True

                editor._on_seg_time_changed(0, 0.5, 1.5, "square_right")
                self.app.processEvents()

                self.assertTrue(editor._has_unsaved_changes())
                self.assertTrue(editor.sm.is_dirty)
                self.assertFalse(editor._skip_prev_confirm_once)

                prompted = []
                editor._show_confirm_dialog = lambda *args, **kwargs: (
                    prompted.append(args),
                    QMessageBox.StandardButton.Cancel,
                )[1]
                exited = []
                editor.sig_exit.connect(lambda *args: exited.append(True))
                editor._skip_prev_confirm_once = True

                editor._on_exit()

                self.assertTrue(prompted)
                self.assertFalse(exited)
            finally:
                editor.close()

    def test_project_file_change_marks_editor_dirty(self):
        from ui.editor.editor_actions import EditorActionsMixin

        class ProjectDirtyEditor(EditorActionsMixin):
            def __init__(self, project_path):
                self._current_project_path = project_path
                self._is_dirty = False
                self.sm = SubtitleStateManager()
                self.refreshes = []
                self._remember_saved_segments([])

            def _get_current_segments(self):
                return []

            def window(self):
                return SimpleNamespace(
                    _current_project_path=self._current_project_path,
                    _refresh_saved_status_label=lambda **kwargs: self.refreshes.append(kwargs),
                )

        with tempfile.TemporaryDirectory() as tmp:
            project_path = os.path.join(tmp, "sample.assp")
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump({"project": "sample", "version": 1}, f, ensure_ascii=False)

            editor = ProjectDirtyEditor(project_path)
            editor._remember_saved_project_file()
            self.assertFalse(editor._has_unsaved_changes())
            self.assertFalse(editor._is_dirty)
            self.assertFalse(editor.sm.is_dirty)

            with open(project_path, "w", encoding="utf-8") as f:
                json.dump({"project": "sample", "version": 2}, f, ensure_ascii=False)

            self.assertTrue(editor._has_unsaved_changes())
            self.assertTrue(editor._is_dirty)
            self.assertTrue(editor.sm.is_dirty)
            self.assertTrue(any(item.get("is_dirty") is True for item in editor.refreshes))

    def test_editor_manual_edit_pauses_idle_work_without_unloading_models(self):
        from ui.editor.editor_segments import EditorSegmentsMixin

        calls = []

        class EditWindow:
            def _refresh_saved_status_label(self, **kwargs):
                calls.append(("refresh", kwargs))

            def _reset_post_completion_idle_timer(self):
                calls.append(("reset_idle", None))

            def _pause_personalization_for_foreground_activity(self, reason, *, hold_ms=0):
                calls.append(("pause_lora", reason, hold_ms))

            def _release_ai_models_for_editor_mode(self, *args, **kwargs):
                calls.append(("release", args, kwargs))

        class DirtyEditor(EditorSegmentsMixin):
            def __init__(self):
                self.sm = SubtitleStateManager()
                self._window = EditWindow()

            def _has_unsaved_changes(self):
                return True

            def window(self):
                return self._window

        editor = DirtyEditor()
        editor._mark_dirty()

        self.assertTrue(editor.sm.is_dirty)
        self.assertIn(("reset_idle", None), calls)
        self.assertTrue(any(item[0] == "pause_lora" and item[1] == "subtitle_editor_edit" for item in calls))
        self.assertFalse(any(item[0] == "release" for item in calls))

    def test_editor_top_mode_toolbar_is_removed(self):
        from ui.editor.editor_widget import EditorWidget

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sample.m4a")
            open(media_path, "wb").close()
            editor = EditorWidget("sample.m4a", [], media_path=media_path)
            try:
                self.assertIsNone(editor._editor_wrap.findChild(QWidget, "subtitleTableHeader"))
                self.assertIsNone(editor._editor_wrap.findChild(QWidget, "subtitleEditorModeBar"))
            finally:
                editor.close()
                editor.deleteLater()
                self.app.processEvents()

    def test_restart_from_completed_state_backs_up_clears_and_resets_queue(self):
        from ui.main.main_window import MainWindow

        class _Backend:
            def __init__(self, files):
                self.files_to_process = files
                self.current_folder = os.path.dirname(files[0])
                self._reuse_existing_single_subtitle = True
                self._reuse_existing_multiclip_subtitles = True
                self._reuse_clip_indices = {0}
                self._force_no_reuse_once = False
                self._speaker_map = ["00"]
                self.pipeline_start_time = 0.0
                self.is_first_start = True
                self._active = False
                self.restarted = False

            def restart_current_file(self):
                self.restarted = True

            def stop(self):
                self._active = False

        class _Canvas:
            def __init__(self):
                self.total_duration = 4.0
                self.segments = [{"start": 0.0, "end": 1.0, "text": "old"}]
                self.gap_segments = [{"start": 1.0, "end": 2.0, "is_gap": True}]
                self.vad_segments = [{"start": 0.0, "end": 1.2}]
                self.boundary_times = [1.5]
                self.scan_boundary_times = [1.4]
                self.active_seg_start = 1.0
                self.playhead_sec = 1.0
                self.re_recog_zone = (0.0, 1.0)
                self.re_recog_progress = 0.5
                self._hover_line = 1
                self._hover_handle = (self.segments[0], "right")
                self._drag_seg = self.segments[0]
                self._drag_edge = "right"
                self._drag_adj_l = {"start": 0.0}
                self._drag_adj_r = {"end": 2.0}
                self._snap_lines = [1.0]
                self._edit_active = True
                self._edit_line = 1
                self._edit_text = "old"
                self._edit_orig = "old"
                self._speech_mask = object()
                self.invalidated_markers = False
                self.invalidated_static = False
                self.updated = False

            def update(self):
                self.updated = True

            def _invalidate_marker_caches(self):
                self.invalidated_markers = True

            def _invalidate_static_cache(self):
                self.invalidated_static = True

        class _Timeline:
            def __init__(self):
                self.canvas = _Canvas()
                self.global_canvas = _Canvas()
                self.updated_segments = None
                self.playhead = None
                self.vad = None

            def update_segments(self, segments, start, total):
                self.updated_segments = (segments, start, total)

            def set_playhead(self, sec):
                self.playhead = sec

            def set_vad_segments(self, segments):
                self.vad = segments
                self.canvas.vad_segments = segments
                self.global_canvas.vad_segments = segments

            def set_boundary_times(self, times):
                self.canvas.boundary_times = list(times or [])

            def set_scan_boundary_times(self, times):
                self.canvas.scan_boundary_times = list(times or [])

        class _VideoPlayer:
            def __init__(self):
                self.context_segments = None
                self.seek_sec = None
                self.segments = [{"start": 0.0, "end": 1.0, "text": "old"}]
                self._pending_segments = [{"start": 0.0, "end": 1.0, "text": "old"}]
                self._subtitle_starts = [0.0]
                self._last_segments_signature = "old"

            def set_context_segments(self, segments):
                self.context_segments = segments

            def seek(self, sec):
                self.seek_sec = sec

        class _Roughcut:
            def __init__(self):
                self._result = object()
                self._stored_roughcut_result = object()
                self._source_signature = "sig"
                self._selected_candidate_id = "candidate_a"
                self._roughcut_candidates = [{"candidate_id": "candidate_a"}]
                self._user_edits = {"chapter_1": {"title": "old"}}
                self.refreshed = False
                self.empty = False

            def _refresh_candidate_combo(self):
                self.refreshed = True

            def _set_empty_state(self):
                self.empty = True

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sample.mp4")
            open(media_path, "wb").close()
            project_path = os.path.join(tmp, "sample.assp")
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": "03.04.01",
                        "phase": "PHASE2",
                        "media": [{"order": 0, "path": media_path, "type": "video", "duration": 4.0, "offset": 0.0}],
                        "timeline": {
                            "tracks": [{
                                "clips": [{
                                    "id": "clip_1",
                                    "source_path": media_path,
                                    "timeline_start": 0.0,
                                    "timeline_end": 4.0,
                                    "order": 0,
                                }]
                            }]
                        },
                        "subtitles": {"segments": [{"start": 0.0, "end": 1.0, "text": "old"}]},
                        "analysis": {
                            "cut_boundaries": [{"timeline_sec": 1.5, "timeline_frame": 45, "fps": 30.0}],
                            "cut_boundary_provisional_boundaries": [{"timeline_sec": 1.4, "timeline_frame": 42, "fps": 30.0, "status": "provisional"}],
                        },
                        "editor_state": {
                            "analysis": {
                                "cut_boundaries": [{"timeline_sec": 1.5, "timeline_frame": 45, "fps": 30.0}],
                                "cut_boundary_provisional_boundaries": [{"timeline_sec": 1.4, "timeline_frame": 42, "fps": 30.0, "status": "provisional"}],
                            },
                            "multiclip": {
                                "cut_boundaries": [{"timeline_sec": 1.5, "timeline_frame": 45, "fps": 30.0}],
                                "cut_boundary_provisional_boundaries": [{"timeline_sec": 1.4, "timeline_frame": 42, "fps": 30.0, "status": "provisional"}],
                            },
                        },
                        "roughcut_state": {"source_signature": "sig", "candidates": [{"candidate_id": "candidate_a"}]},
                    },
                    f,
                    ensure_ascii=False,
                )
            window = MainWindow()
            try:
                editor = SimpleNamespace(
                    media_path=media_path,
                    text_edit=QTextEdit(),
                    _segment_queue=[{"start": 0.0, "end": 1.0, "text": "old"}],
                    _cached_segs=[{"start": 0.0, "end": 1.0, "text": "old"}],
                    _active_seg_start=1.0,
                    _completion_handled=True,
                    _roughcut_draft_pending=True,
                    _is_dirty=True,
                    _project_boundary_times=[1.5],
                    _auto_cut_boundary_scan_lines=[1.4],
                    _cut_boundary_topicless_middle_segments=[{"label": "A 주제없음"}],
                    _middle_segments=[{"label": "A 주제없음"}],
                    timeline=_Timeline(),
                    video_player=_VideoPlayer(),
                    _get_current_segments=lambda: [
                        {"start": 0.0, "end": 1.25, "text": "백업 자막", "speaker": "00"}
                    ],
                )
                remembered = []
                editor._remember_saved_segments = lambda segs: remembered.append(list(segs))
                window._editor_widget = editor
                window.backend = _Backend([media_path])
                window._current_project_path = project_path
                window._editor_roughcut_result = object()
                window._roughcut_widget = _Roughcut()

                self.assertTrue(window._restart_current_pipeline_from_beginning(editor))

                self.assertTrue(window.backend.restarted)
                self.assertTrue(window.backend._active)
                self.assertFalse(window.backend._reuse_existing_single_subtitle)
                self.assertFalse(window.backend._reuse_existing_multiclip_subtitles)
                self.assertEqual(window.backend._reuse_clip_indices, set())
                self.assertTrue(window.backend._force_no_reuse_once)
                self.assertTrue(window.backend._force_cut_boundary_rescan_once)
                self.assertFalse(window.backend.is_first_start)
                self.assertGreater(window.backend.pipeline_start_time, 0.0)
                self.assertEqual(editor.text_edit.toPlainText(), "")
                self.assertEqual(editor._segment_queue, [])
                self.assertEqual(editor._cached_segs, [])
                self.assertEqual(editor.timeline.updated_segments[0], [])
                self.assertEqual(editor.timeline.playhead, 0.0)
                self.assertEqual(editor.timeline.vad, [])
                self.assertEqual(editor.timeline.canvas.segments, [])
                self.assertEqual(editor.timeline.canvas.gap_segments, [])
                self.assertEqual(editor.timeline.canvas.vad_segments, [])
                self.assertIsNone(editor.timeline.canvas.active_seg_start)
                self.assertEqual(editor.timeline.canvas.playhead_sec, 0.0)
                self.assertIsNone(editor.timeline.canvas.re_recog_zone)
                self.assertIsNone(editor.timeline.canvas.re_recog_progress)
                self.assertIsNone(editor.timeline.canvas._hover_line)
                self.assertIsNone(editor.timeline.canvas._hover_handle)
                self.assertIsNone(editor.timeline.canvas._drag_seg)
                self.assertIsNone(editor.timeline.canvas._drag_edge)
                self.assertEqual(editor.timeline.canvas._snap_lines, [])
                self.assertEqual(editor.timeline.canvas.boundary_times, [])
                self.assertEqual(editor.timeline.canvas.scan_boundary_times, [])
                self.assertFalse(editor.timeline.canvas._edit_active)
                self.assertIsNone(editor.timeline.canvas._speech_mask)
                self.assertTrue(editor.timeline.canvas.invalidated_markers)
                self.assertTrue(editor.timeline.canvas.invalidated_static)
                self.assertEqual(editor.timeline.global_canvas.segments, [])
                self.assertEqual(editor.timeline.global_canvas.gap_segments, [])
                self.assertEqual(editor.timeline.global_canvas.vad_segments, [])
                self.assertEqual(editor._project_boundary_times, [])
                self.assertEqual(editor._auto_cut_boundary_scan_lines, [])
                self.assertEqual(editor._cut_boundary_topicless_middle_segments, [])
                self.assertEqual(editor._middle_segments, [])
                self.assertEqual(editor.video_player.context_segments, [])
                self.assertEqual(editor.video_player.segments, [])
                self.assertEqual(editor.video_player._pending_segments, [])
                self.assertEqual(editor.video_player._subtitle_starts, [])
                self.assertEqual(editor.video_player._last_segments_signature, "")
                self.assertEqual(editor.video_player.seek_sec, 0.0)
                self.assertEqual(remembered[-1], [])
                self.assertIsNone(window._editor_roughcut_result)
                self.assertEqual(window._project_boundary_times, [])
                self.assertIsNone(window._roughcut_widget._result)
                self.assertEqual(window._roughcut_widget._roughcut_candidates, [])
                self.assertEqual(window._roughcut_widget._selected_candidate_id, "")
                self.assertTrue(window._roughcut_widget.refreshed)
                self.assertTrue(window._roughcut_widget.empty)
                saved_project = read_project_storage_payload(project_path)
                self.assertEqual(saved_project.get("roughcut_state"), {})
                self.assertNotIn("segments", saved_project.get("subtitles", {}))
                self.assertEqual(saved_project.get("subtitles", {}).get("storage"), "editor_state.rendering.subtitle_canvas")
                self.assertEqual(saved_project.get("analysis", {}).get("cut_boundaries"), [])
                self.assertEqual(saved_project.get("analysis", {}).get("cut_boundary_provisional_boundaries"), [])
                self.assertEqual(saved_project.get("editor_state", {}).get("analysis", {}).get("cut_boundaries"), [])
                self.assertEqual(saved_project.get("editor_state", {}).get("analysis", {}).get("cut_boundary_provisional_boundaries"), [])
                self.assertEqual(saved_project.get("editor_state", {}).get("multiclip", {}).get("cut_boundaries"), [])
                self.assertEqual(saved_project.get("editor_state", {}).get("multiclip", {}).get("cut_boundary_provisional_boundaries"), [])
                self.assertIn("대기", window.queue_table.item(0, 0).text())
                self.assertIn("(1/1)", window.queue_header_lbl.text())
                backup_dir = os.path.join(tmp, "자막백업")
                self.assertTrue(
                    any("restart_segments" in name for name in os.listdir(backup_dir))
                )
            finally:
                window.close()

    def test_restart_prescan_uses_current_cut_boundary_settings(self):
        from ui.main.main_window import MainWindow

        class _Backend:
            def __init__(self):
                self.calls = []

            def _auto_scan_cut_boundaries_for_start(self, project_path, files):
                self.calls.append((project_path, list(files or [])))

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sample.mp4")
            project_path = os.path.join(tmp, "sample.assp")
            open(media_path, "wb").close()
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": "03.14.00",
                        "media": [{"path": media_path}],
                        "user_settings": {
                            "stt_quality_preset": "fast",
                            "cut_boundary_level": "off",
                            "cut_boundary_detection_enabled": False,
                        },
                        "analysis": {
                            "cut_boundaries": [],
                            "cut_boundary_prescan_done": True,
                            "cut_boundary_cache_path": "/tmp/stale.json",
                            "cut_boundary_cache_type": "cut_boundaries_only",
                        },
                    },
                    f,
                    ensure_ascii=False,
                )

            window = MainWindow()
            backend = _Backend()
            try:
                window._current_project_path = project_path
                current_settings = {
                    "stt_quality_preset": "balanced",
                    "scan_cut_boundary_level": "low",
                    "cut_boundary_level": "low",
                    "cut_boundary_detection_enabled": True,
                    "scan_cut_enabled": True,
                    "scan_cut_auto_enabled": True,
                    "cut_boundary_enabled": True,
                }
                with patch("ui.main.main_window.load_settings", return_value=dict(current_settings)):
                    window._prepare_cut_boundary_prescan_for_restart(backend, [media_path])

                self.assertEqual(backend.calls, [(project_path, [media_path])])
                saved = read_project_storage_payload(project_path)
                self.assertEqual(saved["user_settings"]["stt_quality_preset"], "balanced")
                self.assertEqual(saved["user_settings"]["cut_boundary_level"], "low")
                self.assertNotIn("cut_boundary_prescan_done", saved["analysis"])
                self.assertNotIn("cut_boundary_cache_path", saved["analysis"])
                self.assertNotIn("cut_boundary_cache_type", saved["analysis"])
                self.assertTrue(bool(getattr(backend, "_force_cut_boundary_rescan_once", False)))
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_restart_from_completed_state_restarts_single_file_pipeline_when_backend_thread_is_gone(self):
        from ui.main.main_window import MainWindow

        class _DeadThread:
            def is_alive(self):
                return False

        class _Backend:
            def __init__(self, files):
                self.files_to_process = files
                self.current_folder = os.path.dirname(files[0])
                self.is_icloud = False
                self._pipeline_thread = _DeadThread()
                self._reuse_existing_single_subtitle = True
                self._reuse_existing_multiclip_subtitles = True
                self._reuse_clip_indices = {0}
                self._force_no_reuse_once = False
                self._speaker_map = ["00"]
                self.pipeline_start_time = 0.0
                self.is_first_start = True
                self._active = False
                self.start_calls = []

            def restart_current_file(self):
                raise AssertionError("dead thread fallback should not use restart_current_file")

            def start_pipeline(self, files, folder=None, is_icloud=False, is_auto_start=False):
                self.start_calls.append(
                    {
                        "files": list(files or []),
                        "folder": folder,
                        "is_icloud": bool(is_icloud),
                        "is_auto_start": bool(is_auto_start),
                    }
                )

            def stop(self):
                self._active = False

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sample.mp4")
            open(media_path, "wb").close()
            project_path = os.path.join(tmp, "sample.assp")
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": "03.04.01",
                        "phase": "PHASE2",
                        "media": [{"order": 0, "path": media_path, "type": "video", "duration": 4.0, "offset": 0.0}],
                        "subtitles": {"segments": [{"start": 0.0, "end": 1.0, "text": "old"}]},
                    },
                    f,
                    ensure_ascii=False,
                )

            window = MainWindow()
            try:
                editor = SimpleNamespace(
                    media_path=media_path,
                    text_edit=QTextEdit(),
                    _segment_queue=[{"start": 0.0, "end": 1.0, "text": "old"}],
                    _cached_segs=[{"start": 0.0, "end": 1.0, "text": "old"}],
                    _active_seg_start=1.0,
                    _completion_handled=True,
                    _is_dirty=True,
                    timeline=SimpleNamespace(
                        canvas=SimpleNamespace(
                            total_duration=4.0,
                            segments=[],
                            gap_segments=[],
                            vad_segments=[],
                            active_seg_start=None,
                            update=lambda: None,
                            _invalidate_marker_caches=lambda: None,
                            _invalidate_static_cache=lambda: None,
                        ),
                        global_canvas=SimpleNamespace(vad_segments=[]),
                        update_segments=lambda *args, **kwargs: None,
                        set_playhead=lambda *args, **kwargs: None,
                        set_vad_segments=lambda *args, **kwargs: None,
                        set_boundary_times=lambda *args, **kwargs: None,
                        set_scan_boundary_times=lambda *args, **kwargs: None,
                    ),
                    video_player=SimpleNamespace(
                        set_context_segments=lambda *args, **kwargs: None,
                        seek=lambda *args, **kwargs: None,
                    ),
                    _get_current_segments=lambda: [{"start": 0.0, "end": 1.0, "text": "old"}],
                )
                window._editor_widget = editor
                window.backend = _Backend([media_path])
                window._current_project_path = project_path

                self.assertTrue(window._restart_current_pipeline_from_beginning(editor))
                self.assertEqual(
                    window.backend.start_calls,
                    [
                        {
                            "files": [media_path],
                            "folder": os.path.dirname(media_path),
                            "is_icloud": False,
                            "is_auto_start": True,
                        }
                    ],
                )
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_forced_multiclip_restart_moves_existing_srts_to_backup(self):
        from core.pipeline import multiclip_pipeline
        from core.pipeline.multiclip_pipeline import MulticlipPipelineMixin

        class _Thread:
            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                pass

        class _Ui:
            def __init__(self):
                self._reuse_existing_multiclip_subtitles = True
                self._reuse_clip_indices = {0}
                self.init_files = None

            def init_queue_list(self, files):
                self.init_files = list(files)

        class _Backend(MulticlipPipelineMixin):
            def __init__(self, ui):
                import threading

                self.ui = ui
                self._prefetch_lock = threading.Lock()
                self._prefetch_generation = 0
                self._prefetch_cache = {}
                self._prefetch_threads = {}
                self._force_no_reuse_once = True

        with tempfile.TemporaryDirectory() as tmp:
            media_paths = []
            for idx in range(2):
                media = os.path.join(tmp, f"clip{idx}.mp4")
                srt = os.path.splitext(media)[0] + ".srt"
                open(media, "wb").close()
                with open(srt, "w", encoding="utf-8") as f:
                    f.write("1\n00:00:00,000 --> 00:00:01,000\nold\n")
                media_paths.append(media)

            ui = _Ui()
            backend = _Backend(ui)
            with patch.object(multiclip_pipeline.threading, "Thread", _Thread):
                backend.start_multiclip_pipeline(media_paths, folder=tmp)

            self.assertFalse(os.path.exists(os.path.join(tmp, "clip0.srt")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "clip1.srt")))
            self.assertEqual(ui.init_files, media_paths)
            backup_names = os.listdir(os.path.join(tmp, "자막백업"))
            self.assertEqual(len([name for name in backup_names if name.endswith(".bak")]), 2)


if __name__ == "__main__":
    unittest.main()
