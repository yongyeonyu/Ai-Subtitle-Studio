# Version: 03.14.05
# Phase: PHASE2
import unittest
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QTextEdit

from ui.editor.editor_actions import EditorActionsMixin
from ui.editor.editor_canvas_state import EditorCanvasStateMixin
from ui.editor.editor_lifecycle import EditorLifecycleMixin
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_multiclip_ops import EditorMulticlipOpsMixin
from ui.editor.editor_widget import EditorWidget
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.undo_manager import UndoManager
from core.project.project_manager import get_boundary_times
from ui.editor import editor_project_open_native as project_open_native_module
from ui.project.project_panel import ProjectUIMixin
from core.project.project_assets import externalize_project_text_assets
from core.project.project_phase1b import restore_project_stt_preview_segments


class _Timer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class _TextEdit:
    def __init__(self):
        self.cleared = False

    def clear(self):
        self.cleared = True


class _VideoPlayer:
    def __init__(self, total_time=0.0):
        self.total_time = float(total_time)
        self.seek_calls = []
        self.provider = None
        self.context_segments = []
        self.display_time = None

    def seek(self, sec):
        self.seek_calls.append(float(sec))

    def set_subtitle_provider(self, provider):
        self.provider = provider

    def refresh_subtitle_context(self, segments):
        self.context_segments = list(segments or [])

    def set_subtitle_display_time(self, sec):
        self.display_time = float(sec)


class _ScrollBar:
    def __init__(self):
        self._value = 0

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = int(value)


class _TimelineScroll:
    def __init__(self):
        self._horizontal = _ScrollBar()

    def horizontalScrollBar(self):
        return self._horizontal


class _Timeline:
    def __init__(self):
        self.updated = None
        self.active_calls = []
        self.playhead_calls = []
        self.auto_gap_segments_enabled = True
        self.canvas = type("Canvas", (), {"playhead_sec": 0.0, "segments": []})()
        self.global_canvas = type("GlobalCanvas", (), {"total_duration": 0.0, "segments": []})()
        self.scroll = _TimelineScroll()

    def update_segments(self, segs, active_sec, total_dur):
        self.updated = (list(segs), active_sec, total_dur)
        self.canvas.segments = list(segs)
        self.canvas.total_duration = float(total_dur or 0.0)
        self.global_canvas.total_duration = float(total_dur or 0.0)
        self.global_canvas.segments = list(segs)

    def set_active(self, sec):
        self.active_calls.append(float(sec))

    def set_playhead(self, sec, *, preserve_center_lock=False):
        self.canvas.playhead_sec = float(sec)
        self.playhead_calls.append((float(sec), bool(preserve_center_lock)))

    def center_to_sec(self, _sec, smooth=False):
        return None

    def set_auto_gap_segments_enabled(self, enabled: bool):
        self.auto_gap_segments_enabled = bool(enabled)


class _Status:
    def text(self):
        return ""


class _QueueTimer:
    def __init__(self):
        self.started = False
        self.stopped = False

    def isActive(self):
        return False

    def start(self, _ms):
        self.started = True

    def stop(self):
        self.stopped = True


class _ActiveQueueTimer(_QueueTimer):
    def __init__(self):
        super().__init__()
        self.stopped = False

    def isActive(self):
        return True

    def stop(self):
        self.stopped = True


class _SaveFlushEditor(EditorActionsMixin):
    def __init__(self):
        self._queue_timer = _ActiveQueueTimer()
        self._segment_queue = [{"start": 0.0, "end": 1.0, "text": "대기"}]
        self.flushed = False

    def _flush_queue(self):
        self.flushed = True
        self._segment_queue = []


class _LivePreviewEditor(EditorSegmentsMixin):
    def __init__(self):
        self.status_lbl = _Status()
        self.timeline = _Timeline()
        self.video_player = _VideoPlayer(total_time=10.0)
        self._active_seg_start = None
        self._cached_segs = []
        self._segment_queue = []
        self._queue_timer = _QueueTimer()
        self.reload_called_with = None
        self.dirty = False
        self.scheduled = False

    def _get_current_segments(self):
        return list(self._cached_segs)

    def _frame_time(self, sec):
        return round(float(sec), 3)

    def _reload_segments_from_list(self, segs, preserve_view=False):
        self.reload_called_with = list(segs)
        self._cached_segs = list(segs)

    def _mark_dirty(self):
        self.dirty = True

    def _schedule_timeline(self):
        self.scheduled = True


class _UndoableLivePreviewEditor(_LivePreviewEditor):
    def __init__(self):
        super().__init__()
        self.text_edit = QTextEdit()
        self._undo_mgr = UndoManager(self)

    def _get_current_segments(self):
        return list(self._cached_segs)

    def _reload_segments_from_list(self, segs, preserve_view=False):
        self.reload_called_with = list(segs)
        self._cached_segs = [dict(seg) for seg in segs]
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        cur.removeSelectedText()
        for idx, seg in enumerate(self._cached_segs):
            if idx > 0:
                cur.insertText("\n")
            cur.insertText(str(seg.get("text", "") or ""))
            cur.block().setUserData(
                SubtitleBlockData(
                    str(seg.get("speaker", seg.get("spk", "00")) or "00"),
                    float(seg.get("start", 0.0) or 0.0),
                    False,
                    stt_selected_source=str(seg.get("stt_selected_source", "") or ""),
                    quality=dict(seg.get("quality") or {}),
                )
            )
        self._update_timeline_with_confirmed_and_preview(self._cached_segs)


class _ReplacementEditor(EditorSegmentsMixin):
    def __init__(self):
        self.text_edit = QTextEdit()
        self.video_player = _VideoPlayer(total_time=20.0)
        self._cached_segs = []
        self.dirty = False
        self.scheduled = False
        self.refreshed = False

    def load_blocks(self, rows):
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        cur.removeSelectedText()
        for idx, (text, start, is_gap) in enumerate(rows):
            if idx > 0:
                cur.insertText("\n")
            cur.insertText(text)
            cur.block().setUserData(SubtitleBlockData("00", float(start), bool(is_gap)))

    def _mark_dirty(self):
        self.dirty = True

    def _schedule_timeline(self):
        self.scheduled = True

    def _refresh_video_subtitle_context(self):
        self.refreshed = True


class _ActualSelectionEditor(EditorMulticlipOpsMixin, EditorSegmentsMixin):
    _JUNK_TS_RE = re.compile(r"(?!)")
    _JUNK_NO_BRACKET_3PART = re.compile(r"(?!)")
    _JUNK_NO_BRACKET_3PART_END = re.compile(r"(?!)")
    _JUNK_START_RE = re.compile(r"(?!)")

    def __init__(self):
        self.status_lbl = _Status()
        self.text_edit = QTextEdit()
        self.text_edit.update_margins = lambda: None
        self.timeline = _Timeline()
        self.video_player = _VideoPlayer(total_time=100.0)
        self.settings = {
            "continuous_threshold": 2.0,
            "gap_push_rate": 0.7,
            "single_subtitle_end": 0.2,
            "spk1_id": "00",
            "spk2_id": "01",
            "subtitle_quality_auto_check_after_generate": False,
        }
        self.video_fps = 30.0
        self._active_seg_start = None
        self._cached_segs = []
        self._segment_queue = []
        self._queue_timer = _QueueTimer()
        self._sync_lock = False
        self._is_initial_load = False
        self.dirty = False
        self.scheduled = False
        self.refreshed = False

    def _mark_dirty(self):
        self.dirty = True

    def _schedule_timeline(self):
        self.scheduled = True

    def _refresh_video_subtitle_context(self):
        self.refreshed = True


class _ProjectOpenEditor:
    def __init__(self):
        self.timeline = _Timeline()
        self.video_player = _VideoPlayer(total_time=30.0)
        self.text_edit = _TextEdit()
        self._cached_segs = []
        self.reload_called_with = None
        self.completed = False
        self.completed_kwargs = None
        self.scheduled = False
        self.timestamp_refreshes = []
        self.video_context_refreshes = 0
        self.memory_rebuilds = []

    def _reload_segments_from_list(self, segments):
        self.reload_called_with = [dict(seg) for seg in segments]
        self._cached_segs = [dict(seg) for seg in segments]

    def _rebuild_subtitle_memory_cache(self, segments=None):
        rows = [dict(seg) for seg in (segments if segments is not None else self._cached_segs)]
        self._cached_segs = rows
        self.memory_rebuilds.append(rows)
        return {}

    def _refresh_editor_timestamp_metadata(self, *, full=False):
        self.timestamp_refreshes.append(bool(full))
        return len(self._cached_segs)

    def _refresh_video_subtitle_context(self):
        self.video_context_refreshes += 1
        self.video_player.refresh_subtitle_context(self._video_subtitle_context_for_player())

    def _video_subtitle_context_for_player(self):
        return [dict(seg) for seg in self._cached_segs]

    def _global_to_local_sec(self, sec):
        return float(sec)

    def _set_process_completed(self, **kwargs):
        self.completed = True
        self.completed_kwargs = dict(kwargs)

    def _schedule_timeline(self):
        self.scheduled = True


class _CanvasStateEditor(EditorCanvasStateMixin):
    def __init__(self):
        self.video_fps = 30.0
        self.timeline = _Timeline()
        self._cached_segs = []
        self._live_stt_preview_segments = []
        self.scheduled = False

    def _reload_segments_from_list(self, segments, preserve_view=False, mark_dirty=False):
        self._cached_segs = [dict(seg) for seg in list(segments or [])]
        total_dur = max((float(seg.get("end", 0.0) or 0.0) for seg in self._cached_segs), default=0.0)
        self.timeline.update_segments(self._cached_segs, None, total_dur)

    def _get_current_segments(self):
        return list(self._cached_segs)

    def _schedule_timeline(self):
        self.scheduled = True
        segs = list(self._cached_segs)
        preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        combined = sorted(
            segs + preview,
            key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
        )
        total_dur = max((float(seg.get("end", 0.0) or 0.0) for seg in combined), default=0.0)
        self.timeline.update_segments(combined, None, total_dur)


class _ProjectOpenWindow(ProjectUIMixin, EditorLifecycleMixin):
    def __init__(self, editor):
        self.editor = editor
        self._editor_widget = None
        self.runtime_schedule_count = 0
        self.init_args = None

    def _init_editor(self, target_file, is_batch=False):
        self.init_args = (target_file, bool(is_batch))
        self._editor_widget = self.editor

    def _schedule_opened_editor_runtime_refresh(self, editor):
        self.runtime_schedule_count += 1
        self._refresh_opened_editor_runtime(editor)


class _Signal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)


class _LifecycleTimeline:
    def __init__(self):
        self.boundary_times = []

    def set_boundary_times(self, times):
        self.boundary_times = list(times or [])


class _LifecycleEditor:
    def __init__(self, video_name, segments, media_path=None, parent=None, defer_media_load=False, hydrate_existing_srt_on_empty=True):
        self.video_name = video_name
        self.segments = list(segments or [])
        self.media_path = media_path
        self.parent = parent
        self.defer_media_load = bool(defer_media_load)
        self.hydrate_existing_srt_on_empty = bool(hydrate_existing_srt_on_empty)
        self.is_auto_start = False
        self._queue_mode_fit_view = False
        self._project_clips = None
        self.timeline = _LifecycleTimeline()
        self.sig_start = _Signal()
        self.sig_prev = _Signal()
        self.sig_exit = _Signal()
        self.sig_next = _Signal()
        self.sig_save = _Signal()
        self.sig_auto_save = _Signal()
        self._terminal_layout_visible = None

        class _SM:
            def init_state(inner_self):
                inner_self.state = "ST_IDLE"

            def init_auto_state(inner_self):
                inner_self.state = "ST_AUTO"

        self.sm = _SM()

    def set_terminal_visible_layout(self, visible):
        self._terminal_layout_visible = bool(visible)


class _LifecycleStack:
    def __init__(self):
        self.widgets = []
        self.current = None

    def insertWidget(self, index, widget):
        if widget in self.widgets:
            self.widgets.remove(widget)
        index = max(0, min(int(index), len(self.widgets)))
        self.widgets.insert(index, widget)

    def setCurrentWidget(self, widget):
        self.current = widget


class _LifecycleOwner(EditorLifecycleMixin):
    def __init__(self):
        self.stack = _LifecycleStack()
        self._current_project_path = None
        self._project_boundary_times = [1.25, 2.5]
        self._multiclip_boundaries = []
        self._editor_widget = None
        self._on_start_cb = None
        self._on_save_cb = None
        self._on_prev_cb = None
        self.backend = None
        self.scheduled_media = []
        self.fit_calls = 0
        self.idle_mode_reason = None

    def _remove_old_editor(self):
        return None

    def _schedule_native_open_editor_media(self, editor, media_path: str | None):
        self.scheduled_media.append((editor, str(media_path or "")))

    def _schedule_editor_fit_to_view(self, editor, delay_ms: int = 120):
        self.fit_calls += 1

    def _activate_editor_idle_mode(self, reason=""):
        self.idle_mode_reason = str(reason or "")


class _BootstrapTimeline:
    def __init__(self):
        self.waveform_paths = []

    def load_waveform(self, path):
        self.waveform_paths.append(str(path))


class _BootstrapEditor:
    def __init__(self):
        self.timeline = _BootstrapTimeline()
        self.load_calls = []

    def _load_video(self, path, *, load_waveform=True, defer_media_probe=False):
        self.load_calls.append((str(path), bool(load_waveform), bool(defer_media_probe)))


class _Editor(EditorMulticlipOpsMixin):
    def __init__(self):
        self._queue_timer = _Timer()
        self._segment_queue = [{"start": 9.0, "end": 10.0, "text": "stale"}]
        self._is_initial_load = False
        self.text_edit = _TextEdit()
        self.video_player = _VideoPlayer()
        self.timeline = _Timeline()
        self._active_seg_start = None
        self.dirty = False
        self.scheduled = False

    def append_segments(self, segments):
        self._segment_queue.extend(segments)

    def _mark_dirty(self):
        self.dirty = True

    def _schedule_timeline(self):
        self.scheduled = True


class ProjectSegmentReloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_project_open_uses_same_video_subtitle_runtime_refresh_as_srt_open(self):
        editor = _ProjectOpenEditor()
        window = _ProjectOpenWindow(editor)
        segments = [
            {"start": 0.0, "end": 2.0, "text": "프로젝트 자막", "speaker": "00"},
            {"start": 2.5, "end": 4.0, "text": "다음 자막", "speaker": "00"},
        ]
        project = {
            "project_name": "same-runtime",
            "timeline": {"tracks": [{"clips": [{"source_path": "/tmp/sample.mp4"}]}]},
            "editor_state": {},
            "analysis": {
                "preliminary_middle_segments": [
                    {
                        "start": 0.0,
                        "end": 2.0,
                        "major_id": "A",
                        "title": "예비 실외 도입",
                        "segment_stage_name": "예비 중분류 세그먼트",
                    }
                ]
            },
        }

        with patch.object(project_open_native_module.QTimer, "singleShot", side_effect=lambda _delay, cb: cb()):
            opened = window._open_project_segments_in_editor(
                "/tmp/sample_project.json",
                project,
                ["/tmp/sample.mp4"],
                segments,
            )

        self.assertTrue(opened)
        self.assertEqual(window.init_args, ("/tmp/sample.mp4", False))
        self.assertEqual(editor.reload_called_with, segments)
        self.assertFalse(editor.timeline.auto_gap_segments_enabled)
        self.assertTrue(editor.completed)
        self.assertEqual(editor.completed_kwargs, {"suppress_post_generation_tasks": True})
        self.assertTrue(editor.scheduled)
        self.assertGreaterEqual(window.runtime_schedule_count, 1)
        self.assertIsNotNone(editor.video_player.provider)
        self.assertEqual(editor.video_player.provider(), segments)
        self.assertEqual(editor.video_player.context_segments, segments)
        self.assertEqual(editor.video_player.display_time, 0.0)
        self.assertEqual(getattr(editor, "_preliminary_middle_segments")[0]["major_id"], "A")

    def test_apply_loaded_canvas_state_uses_segment_frame_rate_from_project_rows(self):
        editor = _CanvasStateEditor()
        rows = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "프레임 보존",
                "speaker": "00",
                "start_frame": 60,
                "end_frame": 120,
                "timeline_start_frame": 60,
                "timeline_end_frame": 120,
                "frame_rate": 59.94,
                "timeline_frame_rate": 59.94,
                "frame_range": {
                    "unit": "frame",
                    "start": 60,
                    "end": 120,
                    "timeline_frame_rate": 59.94,
                },
            }
        ]

        loaded = editor.apply_loaded_canvas_state(rows, mark_dirty=False)

        self.assertAlmostEqual(loaded[0]["start"], 60.0 / 59.94, places=4)
        self.assertAlmostEqual(loaded[0]["end"], 120.0 / 59.94, places=4)
        self.assertLess(loaded[0]["end"], 2.1)

    def test_project_open_clears_stale_preview_and_duration_before_restore(self):
        class _ProjectCanvasEditor(_CanvasStateEditor):
            def __init__(self):
                super().__init__()
                self.video_player = _VideoPlayer(total_time=0.0)
                self.text_edit = _TextEdit()
                self.completed = False
                self.completed_kwargs = None
                self.timestamp_refreshes = []
                self.video_context_refreshes = 0
                self.memory_rebuilds = []
                self._live_stt_preview_segments = [
                    {"start": 2000.0, "end": 2010.0, "text": "stale", "stt_preview_source": "STT1"}
                ]
                self.timeline.canvas.total_duration = 44.0 * 60.0
                self.timeline.global_canvas.total_duration = 44.0 * 60.0

            def _rebuild_subtitle_memory_cache(self, segments=None):
                rows = [dict(seg) for seg in (segments if segments is not None else self._cached_segs)]
                self._cached_segs = rows
                self.memory_rebuilds.append(rows)
                return {}

            def _refresh_editor_timestamp_metadata(self, *, full=False):
                self.timestamp_refreshes.append(bool(full))
                return len(self._cached_segs)

            def _refresh_video_subtitle_context(self):
                self.video_context_refreshes += 1

            def _video_subtitle_context_for_player(self):
                return [dict(seg) for seg in self._cached_segs]

            def _global_to_local_sec(self, sec):
                return float(sec)

            def _set_process_completed(self, **kwargs):
                self.completed = True
                self.completed_kwargs = dict(kwargs)

        editor = _ProjectCanvasEditor()
        window = _ProjectOpenWindow(editor)
        segments = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "첫 줄",
                "speaker": "00",
                "start_frame": 60,
                "end_frame": 120,
                "timeline_start_frame": 60,
                "timeline_end_frame": 120,
                "frame_rate": 59.94,
                "timeline_frame_rate": 59.94,
                "frame_range": {
                    "unit": "frame",
                    "start": 60,
                    "end": 120,
                    "timeline_frame_rate": 59.94,
                },
            }
        ]
        project = {
            "timeline": {
                "total_duration": 1450.265483,
                "timebase": {"primary_fps": 59.94},
            },
            "analysis": {},
            "editor_state": {"stt": {"preview_segments": []}},
        }

        with patch.object(project_open_native_module.QTimer, "singleShot", side_effect=lambda _delay, cb: cb()):
            opened = window._open_project_segments_in_editor(
                "/tmp/sample_project.json",
                project,
                ["/tmp/sample.mp4"],
                segments,
            )

        self.assertTrue(opened)
        self.assertEqual(editor._live_stt_preview_segments, [])
        self.assertLess(editor.timeline.canvas.total_duration, 3.0)
        self.assertAlmostEqual(editor.timeline.canvas.total_duration, 120.0 / 59.94, places=4)

    def test_project_open_uses_video_header_primary_fps_when_timeline_timebase_is_missing(self):
        class _ProjectCanvasEditor(_CanvasStateEditor):
            def __init__(self):
                super().__init__()
                self.timeline = _Timeline()
                self._live_stt_preview_segments = []
                self._set_loaded_boundary_rows = lambda *_args, **_kwargs: None
                self._set_loaded_scan_boundary_rows = lambda *_args, **_kwargs: None
                self._set_loaded_vad_segments = lambda *_args, **_kwargs: None
                self._set_loaded_editor_segments = lambda rows, **_kwargs: setattr(self, "_cached_segs", list(rows or []))
                self._video_subtitle_context_for_player = lambda: [dict(seg) for seg in self._cached_segs]
                self._global_to_local_sec = lambda sec: float(sec)
                self._set_process_completed = lambda **_kwargs: None

        editor = _ProjectCanvasEditor()
        window = _ProjectOpenWindow(editor)
        segments = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "첫 줄",
                "speaker": "00",
                "start_frame": 60,
                "end_frame": 120,
                "timeline_start_frame": 60,
                "timeline_end_frame": 120,
                "frame_rate": 59.94,
                "timeline_frame_rate": 59.94,
                "frame_range": {
                    "unit": "frame",
                    "start": 60,
                    "end": 120,
                    "timeline_frame_rate": 59.94,
                },
            }
        ]
        project = {
            "video": {
                "primary_fps": 59.94,
                "duration_sec": 1450.265483,
                "timebase": {"primary_fps": 59.94},
            },
            "timeline": {
                "total_duration": 1450.265483,
            },
            "analysis": {},
            "editor_state": {"stt": {"preview_segments": []}},
        }

        with patch.object(project_open_native_module.QTimer, "singleShot", side_effect=lambda _delay, cb: cb()):
            opened = window._open_project_segments_in_editor(
                "/tmp/sample_project.json",
                project,
                ["/tmp/sample.mp4"],
                segments,
            )

        self.assertTrue(opened)
        self.assertAlmostEqual(editor.video_fps, 59.94, places=2)
        self.assertAlmostEqual(editor.timeline.canvas.total_duration, 120.0 / 59.94, places=4)

    def test_init_editor_uses_deferred_media_and_native_fast_open_bootstrap(self):
        owner = _LifecycleOwner()
        target_file = "/tmp/native-fast-open.mp4"

        with patch("ui.editor.editor_widget.EditorWidget", _LifecycleEditor):
            owner._init_editor(target_file, is_batch=False)

        self.assertIsNotNone(owner._editor_widget)
        self.assertTrue(owner._editor_widget.defer_media_load)
        self.assertFalse(owner._editor_widget.hydrate_existing_srt_on_empty)
        self.assertEqual(owner._editor_widget.timeline.boundary_times, owner._project_boundary_times)
        self.assertIs(owner.stack.current, owner._editor_widget)
        self.assertEqual(owner.scheduled_media, [(owner._editor_widget, target_file)])
        self.assertEqual(owner.fit_calls, 1)
        self.assertEqual(owner.idle_mode_reason, "editor_open")

    def test_native_open_media_bootstrap_stages_video_then_waveform(self):
        owner = type("Owner", (), {"_editor_widget": None, "_multiclip_boundaries": []})()
        editor = _BootstrapEditor()
        owner._editor_widget = editor
        delays = []

        def _run_now(delay, callback):
            delays.append(int(delay))
            callback()

        with patch.object(project_open_native_module.QTimer, "singleShot", side_effect=_run_now):
            project_open_native_module.schedule_native_open_editor_media(owner, editor, "/tmp/clip.mp4")

        self.assertEqual(delays, [32, 180])
        self.assertEqual(editor.load_calls, [("/tmp/clip.mp4", False, True)])
        self.assertEqual(editor.timeline.waveform_paths, ["/tmp/clip.mp4"])

    def test_native_open_media_bootstrap_skips_stale_editor(self):
        owner = type("Owner", (), {"_editor_widget": None, "_multiclip_boundaries": []})()
        editor = _BootstrapEditor()
        owner._editor_widget = editor
        scheduled = []

        with patch.object(project_open_native_module.QTimer, "singleShot", side_effect=lambda delay, cb: scheduled.append((int(delay), cb))):
            project_open_native_module.schedule_native_open_editor_media(owner, editor, "/tmp/clip.mp4")

        owner._editor_widget = object()
        for _delay, callback in scheduled:
            callback()

        self.assertEqual(editor.load_calls, [])

    def test_native_editor_post_open_tasks_run_in_staged_order(self):
        owner = type("Owner", (), {"_editor_widget": None})()
        editor = type("Editor", (), {})()
        owner._editor_widget = editor
        seen = []

        with patch.object(project_open_native_module.QTimer, "singleShot", side_effect=lambda _delay, cb: cb()):
            project_open_native_module.schedule_native_editor_post_open_tasks(
                owner,
                editor,
                restore_workspace_callback=lambda: seen.append("restore"),
                apply_project_ui_callback=lambda: seen.append("project_ui"),
                load_multiclip_waveform_callback=lambda: seen.append("waveform"),
                preload_segments_callback=lambda: seen.append("preload"),
            )

        self.assertEqual(seen, ["restore", "project_ui", "waveform", "preload"])

    def test_get_boundary_times_prefers_confirmed_cut_rows_over_clip_boundaries(self):
        project = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {"source_path": "/tmp/a.mp4", "timeline_start": 0.0, "timeline_end": 12.0},
                            {"source_path": "/tmp/b.mp4", "timeline_start": 12.0, "timeline_end": 24.0},
                        ]
                    }
                ]
            },
            "analysis": {
                "cut_boundaries": [
                    {"timeline_sec": 5.0, "timeline_frame": 150, "fps": 30.0},
                    {"timeline_sec": 17.0, "timeline_frame": 510, "fps": 30.0},
                ]
            },
        }

        boundaries = get_boundary_times(project)

        self.assertEqual(len(boundaries), 2)
        self.assertEqual(boundaries[0]["timeline_sec"], 5.0)
        self.assertEqual(boundaries[1]["timeline_sec"], 17.0)

    def test_reload_replaces_pending_segments_before_project_restore(self):
        editor = _Editor()
        restored = [{"start": 1.0, "end": 2.0, "text": "restored"}]

        editor._reload_segments_from_list(restored)

        self.assertTrue(editor._queue_timer.stopped)
        self.assertTrue(editor.text_edit.cleared)
        self.assertTrue(editor._is_initial_load)
        self.assertEqual(len(editor._segment_queue), 1)
        self.assertEqual(editor._segment_queue[0]["text"], "restored")
        self.assertEqual(editor._segment_queue[0]["line"], 0)
        self.assertEqual(editor.timeline.updated[0], editor._segment_queue)
        self.assertEqual(editor.timeline.updated[2], 2.0)
        self.assertTrue(editor.dirty)
        self.assertTrue(editor.scheduled)

    def test_live_stt_preview_updates_timeline_without_editor_commit(self):
        editor = _LivePreviewEditor()

        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "미리보기"}])

        self.assertEqual(len(editor._live_stt_preview_segments), 1)
        self.assertTrue(editor._live_stt_preview_segments[0]["stt_pending"])
        subtitle_drafts = [seg for seg in editor.timeline.updated[0] if seg.get("_live_subtitle_preview")]
        stt_previews = [seg for seg in editor.timeline.updated[0] if seg.get("_live_stt_preview")]
        self.assertEqual(subtitle_drafts[0]["text"], "미리보기")
        self.assertEqual(stt_previews[0]["text"], "미리보기")
        self.assertEqual(editor.timeline.updated[2], 10.0)
        self.assertEqual(editor._segment_queue, [])
        self.assertEqual(editor._active_seg_start, 1.0)
        self.assertEqual(editor.timeline.active_calls[-1], 1.0)
        self.assertEqual(editor.timeline.playhead_calls[-1], (1.0, True))
        self.assertEqual(editor.video_player.seek_calls[-1], 1.0)

    def test_timestamp_area_recovers_missing_block_user_data_after_srt_like_load(self):
        segments = [
            {"start": 1.0, "end": 2.2, "text": "첫 줄", "speaker": "00"},
            {"start": 3.4, "end": 5.0, "text": "둘째 줄", "speaker": "00"},
        ]
        editor = EditorWidget(
            video_name="sample.mp4",
            segments=segments,
            media_path="",
            defer_media_load=True,
        )
        editor.resize(1280, 720)
        editor.show()
        self.app.processEvents()

        doc = editor.text_edit.document()
        for idx in range(doc.blockCount()):
            doc.findBlockByNumber(idx).setUserData(None)

        self.assertIsNone(doc.findBlockByNumber(0).userData())
        self.assertIsNone(doc.findBlockByNumber(1).userData())

        editor.text_edit._flush_timestamp_area_update()
        self.app.processEvents()

        first = doc.findBlockByNumber(0).userData()
        second = doc.findBlockByNumber(1).userData()
        self.assertIsInstance(first, SubtitleBlockData)
        self.assertIsInstance(second, SubtitleBlockData)
        self.assertAlmostEqual(first.start_sec, 1.0, places=2)
        self.assertAlmostEqual(second.start_sec, 3.4, places=2)
        editor.close()

    def test_srt_like_load_repairs_all_timestamp_metadata(self):
        segments = [
            {"start": 1.0, "end": 2.2, "text": "첫 줄", "speaker": "00"},
            {"start": 3.4, "end": 5.0, "text": "둘째 줄", "speaker": "00"},
            {"start": 8.1, "end": 9.0, "text": "셋째 줄", "speaker": "01"},
        ]
        editor = EditorWidget(
            video_name="sample.srt",
            segments=segments,
            media_path="",
            defer_media_load=True,
        )
        try:
            editor.resize(1280, 720)
            editor.show()
            self.app.processEvents()
            doc = editor.text_edit.document()
            for idx in range(doc.blockCount()):
                doc.findBlockByNumber(idx).setUserData(None)

            repaired = editor._restore_all_block_user_data()
            editor._refresh_editor_timestamp_metadata(full=False)

            self.assertEqual(repaired, 3)
            starts = [
                doc.findBlockByNumber(idx).userData().start_sec
                for idx in range(doc.blockCount())
            ]
            self.assertEqual(starts, [1.0, 3.4, 8.1])
            self.assertGreaterEqual(editor.text_edit.viewportMargins().left(), 120)
            self.assertTrue(editor.text_edit.timestampArea.isVisible())
        finally:
            editor.close()

    def test_srt_like_load_restores_timestamp_metadata_from_editor_snapshot(self):
        segments = [
            {"start": 1.0, "end": 2.2, "text": "첫 줄", "speaker": "00"},
            {"start": 3.4, "end": 5.0, "text": "둘째 줄", "speaker": "00"},
        ]
        editor = EditorWidget(
            video_name="sample.srt",
            segments=segments,
            media_path="",
            defer_media_load=True,
        )
        try:
            doc = editor.text_edit.document()
            snapshot = getattr(editor.text_edit, "_timestamp_block_meta_snapshot", {})
            self.assertEqual(sorted(snapshot), [0, 1])

            editor._cached_segs = []
            editor._cached_line_map = {}
            for idx in range(doc.blockCount()):
                doc.findBlockByNumber(idx).setUserData(None)

            repaired = editor._restore_all_block_user_data()

            self.assertEqual(repaired, 2)
            self.assertAlmostEqual(doc.findBlockByNumber(0).userData().start_sec, 1.0)
            self.assertAlmostEqual(doc.findBlockByNumber(1).userData().start_sec, 3.4)
        finally:
            editor.close()

    def test_live_stt_preview_keeps_stt1_and_stt2_overlap_as_separate_lanes(self):
        editor = _LivePreviewEditor()

        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "STT1", "stt_preview_source": "STT1"}])
        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "STT2", "stt_preview_source": "STT2"}])

        self.assertEqual(len(editor._live_stt_preview_segments), 2)
        self.assertEqual(
            [seg["stt_preview_source"] for seg in editor._live_stt_preview_segments],
            ["STT1", "STT2"],
        )
        subtitle_drafts = [seg for seg in editor.timeline.updated[0] if seg.get("_live_subtitle_preview")]
        stt_previews = [seg for seg in editor.timeline.updated[0] if seg.get("_live_stt_preview")]
        self.assertEqual([seg["text"] for seg in subtitle_drafts], ["STT1"])
        self.assertEqual([seg["text"] for seg in stt_previews], ["STT1", "STT2"])

    def test_project_restore_rehydrates_external_stt_candidate_lanes(self):
        editor = _LivePreviewEditor()
        editor._cached_segs = [{"start": 1.0, "end": 2.0, "text": "최종", "speaker": "00"}]
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "sample_project.json"
            project = {
                "project_path": str(project_path),
                "subtitles": {},
                "editor_state": {"stt": {"candidate_tracks": {}}},
                "analysis": {},
            }
            stt_tracks = {
                "STT1": [{"start": 1.0, "end": 2.0, "text": "STT1 후보"}],
                "STT2": [{"start": 1.0, "end": 2.0, "text": "STT2 후보"}],
            }
            externalize_project_text_assets(
                str(project_path),
                project,
                final_segments=editor._cached_segs,
                stt_tracks=stt_tracks,
            )

            restored = restore_project_stt_preview_segments(editor, project)

        self.assertEqual(restored, 2)
        self.assertEqual(
            [seg["stt_preview_source"] for seg in editor._live_stt_preview_segments],
            ["STT1", "STT2"],
        )
        subtitle_drafts = [seg for seg in editor.timeline.updated[0] if seg.get("_live_subtitle_preview")]
        stt_previews = [seg for seg in editor.timeline.updated[0] if seg.get("_live_stt_preview")]
        self.assertEqual(subtitle_drafts, [])
        self.assertEqual([seg["text"] for seg in stt_previews], ["STT1 후보", "STT2 후보"])

    def test_live_subtitle_preview_is_removed_when_final_segment_overlaps(self):
        editor = _LivePreviewEditor()
        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "드래프트", "stt_preview_source": "STT1"}])
        self.assertTrue(any(seg.get("_live_subtitle_preview") for seg in editor.timeline.updated[0]))

        editor._cached_segs = [{"start": 1.0, "end": 2.0, "text": "최종", "speaker": "00"}]
        editor._redraw_timeline_with_live_preview()

        subtitle_drafts = [seg for seg in editor.timeline.updated[0] if seg.get("_live_subtitle_preview")]
        stt_previews = [seg for seg in editor.timeline.updated[0] if seg.get("_live_stt_preview")]
        self.assertEqual(subtitle_drafts, [])
        self.assertEqual([seg["text"] for seg in stt_previews], ["드래프트"])

    def test_live_stt_preview_is_visible_in_editor_without_saved_commit(self):
        editor = _ActualSelectionEditor()
        try:
            editor.preview_stt_segments([
                {"start": 1.0, "end": 2.0, "text": "실시간 드래프트", "stt_preview_source": "STT1"}
            ])
            editor._flush_live_editor_preview_queue()

            self.assertIn("실시간 드래프트", editor.text_edit.toPlainText())
            self.assertEqual([seg for seg in editor._get_current_segments() if not seg.get("is_gap")], [])
        finally:
            editor.text_edit.close()

    def test_live_stt_preview_updates_existing_editor_draft_text_in_place(self):
        editor = _ActualSelectionEditor()
        try:
            editor.preview_stt_segments([
                {"start": 1.0, "end": 2.0, "text": "처음 드래프트", "stt_preview_source": "STT1"}
            ])
            editor._flush_live_editor_preview_queue()

            editor.preview_stt_segments([
                {"start": 1.0, "end": 2.0, "text": "갱신된 실시간 드래프트", "stt_preview_source": "STT1"}
            ])

            self.assertEqual(editor.text_edit.toPlainText(), "갱신된 실시간 드래프트")
            self.assertEqual(len(editor._live_editor_preview_segments), 1)
            self.assertEqual(editor._live_editor_preview_segments[0]["text"], "갱신된 실시간 드래프트")
            self.assertEqual([seg for seg in editor._get_current_segments() if not seg.get("is_gap")], [])
        finally:
            editor.text_edit.close()

    def test_live_stt_preview_autoscrolls_editor_to_latest_draft(self):
        editor = _ActualSelectionEditor()
        try:
            editor.preview_stt_segments([
                {"start": 1.0, "end": 2.0, "text": "첫 드래프트", "stt_preview_source": "STT1"},
                {"start": 3.0, "end": 4.0, "text": "둘째 드래프트", "stt_preview_source": "STT1"},
            ])
            editor._flush_live_editor_preview_queue()

            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 1)
            self.assertAlmostEqual(editor._active_seg_start, 3.0)
            self.assertEqual(editor.timeline.active_calls[-1], 3.0)
        finally:
            editor.text_edit.close()

    def test_llm_review_payload_focuses_matching_editor_draft(self):
        editor = _ActualSelectionEditor()
        try:
            editor.preview_stt_segments([
                {"start": 1.0, "end": 2.0, "text": "첫 드래프트", "stt_preview_source": "STT1"},
                {"start": 3.0, "end": 4.0, "text": "둘째 드래프트", "stt_preview_source": "STT1"},
            ])
            editor._flush_live_editor_preview_queue()

            focused = editor._focus_editor_block_for_processing_segment({
                "active": True,
                "start": 1.0,
                "end": 2.0,
                "text": "첫 드래프트",
            })

            self.assertTrue(focused)
            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 0)
            self.assertAlmostEqual(editor._active_seg_start, 1.0)
            self.assertEqual(editor.timeline.active_calls[-1], 1.0)
            self.assertEqual(editor.timeline.playhead_calls[-1], (1.0, True))
            self.assertEqual(editor.video_player.seek_calls[-1], 1.0)
        finally:
            editor.text_edit.close()

    def test_processing_segment_focus_still_moves_video_without_editor_block(self):
        editor = _LivePreviewEditor()

        focused = editor._focus_editor_block_for_processing_segment({
            "active": True,
            "start": 4.25,
            "end": 5.0,
            "text": "아직 에디터에 없는 처리 중 세그먼트",
        })

        self.assertFalse(focused)
        self.assertEqual(editor._active_seg_start, 4.25)
        self.assertEqual(editor.timeline.active_calls[-1], 4.25)
        self.assertEqual(editor.timeline.playhead_calls[-1], (4.25, True))
        self.assertEqual(editor.video_player.seek_calls[-1], 4.25)

    def test_processing_segment_focus_inserts_visible_editor_draft_when_missing(self):
        editor = _ActualSelectionEditor()
        try:
            focused = editor._focus_editor_block_for_processing_segment({
                "active": True,
                "start": 7.0,
                "end": 8.0,
                "text": "LLM 검수 중인 자막",
            })

            self.assertTrue(focused)
            self.assertEqual(editor.text_edit.toPlainText(), "LLM 검수 중인 자막")
            self.assertEqual(len(editor._live_editor_preview_segments), 1)
            self.assertEqual(editor.timeline.playhead_calls[-1], (7.0, True))
            self.assertEqual(editor.video_player.seek_calls[-1], 7.0)
            self.assertEqual([seg for seg in editor._get_current_segments() if not seg.get("is_gap")], [])
        finally:
            editor.text_edit.close()

    def test_final_segment_replaces_overlapping_live_editor_preview(self):
        editor = _ActualSelectionEditor()
        try:
            editor.preview_stt_segments([
                {"start": 1.0, "end": 2.0, "text": "실시간 드래프트", "stt_preview_source": "STT1"}
            ])
            editor._flush_live_editor_preview_queue()

            editor.append_segments([{"start": 1.0, "end": 2.0, "text": "최종 자막", "speaker": "00"}])
            editor._flush_queue()

            editor_text = editor.text_edit.toPlainText()
            self.assertIn("최종 자막", editor_text)
            self.assertNotIn("실시간 드래프트", editor_text)
            saved = [seg for seg in editor._get_current_segments() if not seg.get("is_gap")]
            self.assertEqual([seg["text"] for seg in saved], ["최종 자막"])
        finally:
            editor.text_edit.close()

    def test_final_live_append_autoscrolls_editor_to_latest_polished_subtitle(self):
        editor = _ActualSelectionEditor()
        try:
            editor.append_segments([
                {"start": 1.0, "end": 2.0, "text": "첫 최종", "speaker": "00"},
                {"start": 3.0, "end": 4.0, "text": "둘째 최종", "speaker": "00"},
            ])
            editor._flush_queue()

            self.assertEqual(editor.text_edit.textCursor().block().text(), "둘째 최종")
            self.assertAlmostEqual(editor._active_seg_start, 2.7)
            self.assertEqual(editor.timeline.active_calls[-1], 2.7)
        finally:
            editor.text_edit.close()

    def test_final_segments_keep_live_preview_candidates_for_manual_selection(self):
        editor = _LivePreviewEditor()
        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "미리보기"}])

        editor.append_segments([{"start": 1.1, "end": 2.1, "text": "최종"}])

        self.assertEqual(len(editor._live_stt_preview_segments), 1)
        self.assertEqual(editor._live_stt_preview_segments[0]["text"], "미리보기")
        self.assertEqual(editor._segment_queue[0]["text"], "최종")
        self.assertTrue(editor._queue_timer.started)

    def test_select_stt_candidate_replaces_overlapping_final_segment(self):
        editor = _LivePreviewEditor()
        editor._cached_segs = [{"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"}]
        editor.preview_stt_segments([
            {"start": 1.0, "end": 2.0, "text": "STT1 후보", "stt_preview_source": "STT1"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual(editor.reload_called_with[0]["text"], "STT1 후보")
        self.assertEqual(editor.reload_called_with[0]["stt_selected_source"], "STT1")
        self.assertEqual(editor.reload_called_with[0]["quality"]["confidence_label"], "green")
        self.assertEqual(len(editor._live_stt_preview_segments), 1)
        self.assertEqual(editor._live_stt_preview_segments[0]["text"], "STT1 후보")

    def test_select_stt_candidate_strips_whisper_control_tokens(self):
        editor = _LivePreviewEditor()
        editor._cached_segs = [{"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"}]
        editor.preview_stt_segments([
            {
                "start": 1.0,
                "end": 2.0,
                "text": "<|startoftranscript|><|ko|><|transcribe|><|400|> STT1 후보<|900|>",
                "stt_preview_source": "STT1",
            }
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual(editor.reload_called_with[0]["text"], "STT1 후보")
        self.assertEqual(editor.reload_called_with[0]["stt_candidates"][0]["text"], "STT1 후보")

    def test_select_stt_candidate_anchors_playhead_to_candidate_start(self):
        editor = _LivePreviewEditor()
        editor.timeline.canvas.playhead_sec = 99.0
        editor.timeline.scroll.horizontalScrollBar().setValue(37)
        editor._cached_segs = [{"start": 90.0, "end": 100.0, "text": "끝 자막", "speaker": "00"}]
        editor.preview_stt_segments([
            {"start": 12.5, "end": 13.5, "text": "STT2 후보", "stt_preview_source": "STT2"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual(editor._active_seg_start, 12.5)
        self.assertEqual(editor.timeline.active_calls[-1], 12.5)
        self.assertEqual(editor.timeline.playhead_calls[-1], (12.5, True))
        self.assertEqual(editor.timeline.canvas.playhead_sec, 12.5)
        self.assertEqual(editor.video_player.seek_calls[-1], 12.5)
        self.assertEqual(editor.timeline.scroll.horizontalScrollBar().value(), 37)

    def test_select_stt_candidate_uses_existing_slot_near_boundary(self):
        editor = _LivePreviewEditor()
        editor.video_fps = 30.0
        editor._cached_segs = [{"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"}]
        editor.preview_stt_segments([
            {"start": 0.92, "end": 2.08, "text": "STT2 후보", "stt_preview_source": "STT2"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual([seg["text"] for seg in editor.reload_called_with], ["STT2 후보"])
        self.assertEqual([(seg["start"], seg["end"]) for seg in editor.reload_called_with], [(1.0, 2.0)])
        self.assertEqual(editor.reload_called_with[0]["stt_selected_source"], "STT2")
        self.assertEqual(editor.reload_called_with[0]["stt_candidates"][0]["_stt_placement_mode"], "manual_final_slot_replace")
        self.assertTrue(editor.reload_called_with[0]["manual_stt_candidate_locked"])
        self.assertEqual(editor.timeline.playhead_calls[-1], (1.0, True))

    def test_select_stt_candidate_ignores_tiny_bleed_across_boundary(self):
        editor = _LivePreviewEditor()
        editor.video_fps = 30.0
        editor._cached_segs = [
            {"start": 0.0, "end": 1.0, "text": "앞 자막", "speaker": "00"},
            {"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"},
        ]
        editor.preview_stt_segments([
            {"start": 0.94, "end": 2.04, "text": "STT1 후보", "stt_preview_source": "STT1"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual([seg["text"] for seg in editor.reload_called_with], ["앞 자막", "STT1 후보"])
        self.assertEqual([(seg["start"], seg["end"]) for seg in editor.reload_called_with], [(0.0, 1.0), (1.0, 2.0)])
        self.assertEqual(editor.reload_called_with[1]["stt_candidates"][0]["_stt_placement_mode"], "manual_final_slot_replace")

    def test_select_one_stt_candidate_replaces_two_split_subtitles_with_one_segment(self):
        editor = _LivePreviewEditor()
        editor.video_fps = 30.0
        editor._cached_segs = [
            {"start": 17.8, "end": 18.9, "text": "요거 작년에도", "speaker": "00"},
            {"start": 18.9, "end": 21.1, "text": "티니핑이랑 해가지고", "speaker": "00"},
            {"start": 21.1, "end": 23.0, "text": "다음 자막", "speaker": "00"},
        ]
        editor.preview_stt_segments([
            {
                "start": 17.8,
                "end": 21.1,
                "text": "요거 작년에도 티니핑이랑 해가지고",
                "stt_preview_source": "STT1",
            }
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual(
            [seg["text"] for seg in editor.reload_called_with],
            ["요거 작년에도 티니핑이랑 해가지고", "다음 자막"],
        )
        self.assertEqual(
            [(seg["start"], seg["end"]) for seg in editor.reload_called_with],
            [(17.8, 21.1), (21.1, 23.0)],
        )
        selected = editor.reload_called_with[0]
        self.assertEqual(selected["stt_selected_source"], "STT1")
        self.assertEqual(selected["quality"]["confidence_label"], "green")
        self.assertTrue(selected["manual_stt_candidate_locked"])
        self.assertEqual(selected["_deep_candidate_selector_policy"]["decision"], "user_locked_candidate")
        self.assertEqual(selected["_deep_candidate_selector_policy"]["replaced_segment_count"], 2)

    def test_select_stt_candidate_preserve_reload_flush_does_not_autoseek_to_tail(self):
        editor = _ActualSelectionEditor()
        try:
            editor._reload_segments_from_list([
                {"start": 0.0, "end": 1.0, "text": "앞", "speaker": "00"},
                {"start": 90.0, "end": 95.0, "text": "뒤", "speaker": "00"},
            ], preserve_view=True)
            editor.timeline.playhead_calls.clear()
            editor.video_player.seek_calls.clear()
            editor.timeline.canvas.playhead_sec = 90.0
            editor.preview_stt_segments([
                {"start": 0.0, "end": 1.0, "text": "STT1 선택", "stt_preview_source": "STT1"}
            ])
            editor.timeline.playhead_calls.clear()
            editor.video_player.seek_calls.clear()

            editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])
            editor._flush_queue()

            self.assertEqual(editor.timeline.playhead_calls, [(0.0, True)])
            self.assertEqual(editor.video_player.seek_calls, [0.0])
            self.assertEqual(editor._segment_queue, [])
            self.assertTrue(editor._queue_timer.stopped)
        finally:
            editor.text_edit.close()

    def test_project_reload_uses_sparse_blocks_but_preserves_segment_end_times(self):
        editor = _ActualSelectionEditor()
        try:
            editor._reload_segments_from_list([
                {"start": 0.0, "end": 1.0, "text": "앞", "speaker": "00"},
                {"start": 4.0, "end": 5.0, "text": "뒤", "speaker": "00"},
            ])

            self.assertEqual(editor.text_edit.document().blockCount(), 2)
            current = editor._get_current_segments()
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in current], [
                (0.0, 1.0, "앞"),
                (4.0, 5.0, "뒤"),
            ])
        finally:
            editor.text_edit.close()

    def test_replace_text_in_all_subtitles_skips_gap_blocks(self):
        editor = _ReplacementEditor()
        try:
            editor.load_blocks([
                ("BMW랑 BMW", 0.0, False),
                ("BMW 쉬는중", 1.0, True),
                ("끝 BMW", 2.0, False),
            ])
            block = editor.text_edit.document().findBlockByNumber(0)
            anchor = QTextCursor(block)
            anchor.setPosition(block.position())
            end = QTextCursor(block)
            end.setPosition(block.position() + 3)

            replaced = editor._replace_text_in_all_subtitles("BMW", "비엠", anchor=anchor, end_cursor=end)

            self.assertEqual(replaced, 3)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["비엠랑 비엠", "BMW 쉬는중", "끝 비엠"])
            self.assertEqual([seg["text"] for seg in editor._cached_segs], ["비엠랑 비엠", "BMW 쉬는중", "끝 비엠"])
            self.assertTrue(editor._cached_segs[1]["is_gap"])
            self.assertTrue(editor.dirty)
            self.assertTrue(editor.scheduled)
            self.assertTrue(editor.refreshed)
            self.assertEqual(editor.text_edit.document().findBlockByNumber(0).userData().start_sec, 0.0)
        finally:
            editor.text_edit.close()

    def test_select_stt_candidate_replaces_existing_slot_without_splitting_edges(self):
        editor = _LivePreviewEditor()
        editor._cached_segs = [
            {"start": 0.0, "end": 4.0, "text": "긴 기존 자막", "speaker": "00"},
        ]
        editor.preview_stt_segments([
            {"start": 1.0, "end": 3.0, "text": "STT2 선택", "stt_preview_source": "STT2"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual([seg["text"] for seg in editor.reload_called_with], ["STT2 선택"])
        self.assertEqual([(seg["start"], seg["end"]) for seg in editor.reload_called_with], [(0.0, 4.0)])
        self.assertEqual(editor.reload_called_with[0]["stt_selected_source"], "STT2")

    def test_select_stt_candidate_splits_same_source_fragments_for_slot(self):
        editor = _LivePreviewEditor()
        editor._cached_segs = [
            {"start": 10.0, "end": 14.0, "text": "STT1 긴 자막", "speaker": "00"},
        ]
        editor.preview_stt_segments([
            {"start": 10.0, "end": 12.0, "text": "STT2 앞", "stt_preview_source": "STT2"},
            {"start": 12.0, "end": 14.0, "text": "STT2 뒤", "stt_preview_source": "STT2"},
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual([seg["text"] for seg in editor.reload_called_with], ["STT2 앞", "STT2 뒤"])
        self.assertEqual([(seg["start"], seg["end"]) for seg in editor.reload_called_with], [(10.0, 12.0), (12.0, 14.0)])
        self.assertEqual(
            [part["text"] for part in editor.reload_called_with[0]["stt_candidates"][0]["_stt_slot_candidate_parts"]],
            ["STT2 앞", "STT2 뒤"],
        )
        self.assertEqual(editor.reload_called_with[0]["stt_candidates"][0]["_stt_slot_split_total"], 2)
        self.assertEqual(editor.reload_called_with[1]["stt_candidates"][0]["_stt_slot_split_total"], 2)

    def test_select_red_stt1_candidate_replaces_long_subtitle_with_three_stt1_segments(self):
        editor = _LivePreviewEditor()
        editor._cached_segs = [
            {
                "start": 2.0,
                "end": 8.0,
                "text": "긴 메인 자막",
                "speaker": "00",
                "quality": {"confidence_label": "red", "flags": ["high_cps"]},
            },
        ]
        editor.preview_stt_segments([
            {"start": 2.0, "end": 3.3, "text": "어 유스 어드벤처", "stt_preview_source": "STT1"},
            {"start": 3.3, "end": 5.9, "text": "2026 2026", "stt_preview_source": "STT1"},
            {"start": 5.9, "end": 8.0, "text": "네 안녕하세요 소셜기유모씨입니다", "stt_preview_source": "STT1"},
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[2])

        self.assertEqual(
            [seg["text"] for seg in editor.reload_called_with],
            ["어 유스 어드벤처", "2026 2026", "네 안녕하세요 소셜기유모씨입니다"],
        )
        self.assertEqual(
            [(seg["start"], seg["end"]) for seg in editor.reload_called_with],
            [(2.0, 3.3), (3.3, 5.9), (5.9, 8.0)],
        )
        self.assertEqual([seg["stt_selected_source"] for seg in editor.reload_called_with], ["STT1", "STT1", "STT1"])
        self.assertTrue(all(seg["manual_stt_candidate_locked"] for seg in editor.reload_called_with))

    def test_select_stt_candidate_is_undo_redo_snapshot(self):
        editor = _UndoableLivePreviewEditor()
        editor._reload_segments_from_list([
            {"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"}
        ])
        editor.preview_stt_segments([
            {"start": 1.0, "end": 2.0, "text": "STT2 후보", "stt_preview_source": "STT2"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])
        self.assertEqual(editor._cached_segs[0]["text"], "STT2 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT2")

        editor._undo_mgr.undo()
        self.assertEqual(editor._cached_segs[0]["text"], "기존")
        self.assertNotIn("stt_selected_source", editor._cached_segs[0])
        self.assertEqual(editor._live_stt_preview_segments[0]["text"], "STT2 후보")

        editor._undo_mgr.redo()
        self.assertEqual(editor._cached_segs[0]["text"], "STT2 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT2")
        self.assertEqual(editor._live_stt_preview_segments[0]["text"], "STT2 후보")

    def test_switching_between_stt1_and_stt2_is_undo_redo_snapshot(self):
        editor = _UndoableLivePreviewEditor()
        editor._reload_segments_from_list([
            {"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"}
        ])
        editor.preview_stt_segments([
            {"start": 1.0, "end": 2.0, "text": "STT1 후보", "stt_preview_source": "STT1"},
            {"start": 1.0, "end": 2.0, "text": "STT2 후보", "stt_preview_source": "STT2"},
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])
        self.assertEqual(editor._cached_segs[0]["text"], "STT1 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT1")

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])
        self.assertEqual(editor._cached_segs[0]["text"], "STT2 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT2")

        editor._undo_mgr.undo()
        self.assertEqual(editor._cached_segs[0]["text"], "STT1 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT1")

        editor._undo_mgr.undo()
        self.assertEqual(editor._cached_segs[0]["text"], "기존")
        self.assertNotIn("stt_selected_source", editor._cached_segs[0])

        editor._undo_mgr.redo()
        self.assertEqual(editor._cached_segs[0]["text"], "STT1 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT1")

        editor._undo_mgr.redo()
        self.assertEqual(editor._cached_segs[0]["text"], "STT2 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT2")

    def test_save_flushes_pending_segment_queue_before_empty_check(self):
        editor = _SaveFlushEditor()

        editor._flush_pending_segment_queue_now()

        self.assertTrue(editor._queue_timer.stopped)
        self.assertTrue(editor.flushed)
        self.assertEqual(editor._segment_queue, [])


if __name__ == "__main__":
    unittest.main()
