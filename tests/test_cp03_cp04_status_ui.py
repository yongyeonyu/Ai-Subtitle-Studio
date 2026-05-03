# Version: 03.08.10
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
from PyQt6.QtWidgets import QApplication, QLabel, QTextEdit, QWidget

from core.runtime import config
from core.state_manager import SubtitleStateManager
from core.work_mode import EDITOR_MODE
from ui.home_ui import HomeUIMixin
from ui.menu_bar import StatusRail
from ui.queue_widget import QueueMixin


class _DummyHome(QObject, HomeUIMixin):
    def __init__(self, editor):
        super().__init__()
        self._editor = editor
        self.saved_status_label = QLabel("")
        self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)

    def _active_editor(self):
        return self._editor


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

    def test_status_rail_uses_green_flash_and_short_korean_stages(self):
        rail = StatusRail()
        try:
            flash_style = rail._state_style(True)
            self.assertIn("#34C759", flash_style)
            self.assertNotIn("#007AFF", flash_style)

            def editor_for(status, *, dirty=True, processing=True):
                label = QLabel(status)
                return SimpleNamespace(
                    status_lbl=label,
                    current_state="ST_PROC" if processing else "ST_COMP",
                    current_mode="MODE_AI_ALL",
                    _is_ai_processing=processing,
                    _is_dirty=dirty,
                    _stt_mode_enabled=False,
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

    def test_progress_ticks_do_not_overwrite_active_stage_status(self):
        state_manager = SubtitleStateManager()
        state_manager.start_ai_all()
        state_manager.set_custom_status("⏳ LLM 최적화 중")
        state_manager.update_progress(1, 3, 33)
        self.assertIn("LLM", state_manager._status_msg)

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
                self.assertTrue(editor._on_save(skip_auto_next=True))
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
                with open(project_path, "r", encoding="utf-8") as f:
                    saved_project = json.load(f)
                self.assertEqual(saved_project.get("roughcut_state"), {})
                self.assertEqual(saved_project.get("subtitles", {}).get("segments"), [])
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
