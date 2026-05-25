import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.editor.editor_widget import EditorWidget
from ui.editor.editor_save_manager import EditorSaveManagerMixin
from ui.editor.editor_pipeline import EditorPipelineMixin
from ui.main.main_window import MainWindow


class _AutoSaveEditor:
    _auto_save_interval_ms = EditorWidget._auto_save_interval_ms
    _editor_auto_save_allowed = EditorWidget._editor_auto_save_allowed
    _on_auto_save = EditorWidget._on_auto_save


class _SaveBoundaryEditor(EditorSaveManagerMixin):
    def __init__(self):
        self._auto_cut_boundary_scan_active = False
        self._auto_cut_boundary_scan_lines = [{"timeline_sec": 12.0, "time": 12.0, "status": "provisional"}]
        self.timeline = SimpleNamespace(
            canvas=SimpleNamespace(
                scan_boundary_times=[{"timeline_sec": 12.0, "time": 12.0, "status": "provisional"}],
            )
        )
        self._window = SimpleNamespace(
            backend=SimpleNamespace(
                _cut_boundary_prescan_completed=True,
                _cut_boundary_prescan_thread=None,
                _cut_boundary_follower_thread=None,
            ),
            backend_fast=None,
        )

    def window(self):
        return self._window


class _ManualSaveNoOpEditor(EditorSaveManagerMixin):
    def __init__(self):
        self._saved_segments_signature = "saved-signature"
        self._autosave_requires_manual_save = True
        self._mark_save_completed = Mock(return_value=True)
        self._has_unsaved_changes = Mock(return_value=False)
        self._flush_pending_segment_queue_now = Mock(side_effect=AssertionError("no-op save must not flush"))
        self._get_current_segments = Mock(side_effect=AssertionError("no-op save must not load segments"))
        self._window = SimpleNamespace(_refresh_saved_status_label=Mock())

    def window(self):
        return self._window

    def _current_project_path_for_dirty_check(self):
        return ""


class _PendingProjectRefreshEditor(EditorSaveManagerMixin):
    def __init__(self, project_path):
        self._current_project_path = project_path
        self._saved_project_path = project_path
        self._saved_project_signature = ""
        self._saved_segments_signature = self._segments_dirty_signature([])
        self._project_analysis_refresh_pending = True
        self._project_analysis_refresh_pending_path = project_path
        self.sm = SimpleNamespace(is_dirty=False)
        self._is_dirty = False

    def _get_current_segments(self):
        return []

    def window(self):
        return SimpleNamespace(_current_project_path=self._current_project_path)


class _CompletedRecoverySaveEditor(EditorSaveManagerMixin):
    def __init__(self):
        self._saved_segments_signature = ""
        self._autosave_requires_manual_save = False
        self._subtitle_generation_completed = True
        self._process_completed_finalized = True
        self._segment_state = []
        self._has_unsaved_changes = Mock(return_value=True)
        self._flush_pending_segment_queue_now = Mock()
        self._warn_pending_stt_before_save = Mock(return_value=True)
        self._persist_editor_srts = Mock(return_value=True)
        self._auto_save_project = Mock(return_value="/tmp/project.json")
        self._remember_saved_segments = Mock()
        self._remember_saved_project_file = Mock()
        self._mark_save_completed = Mock(return_value=True)
        self._sync_queue_saved_state = Mock()
        self._should_auto_export_after_editor_save = Mock(return_value=False)
        self._schedule_auto_export_saved_subtitle_videos = Mock()
        self._recover_generation_segments_from_backend_backup = Mock(side_effect=self._recover_impl)
        self._window = SimpleNamespace(_refresh_saved_status_label=Mock(), _current_project_path="/tmp/project.json")
        self.settings = {}

    def _recover_impl(self):
        self._segment_state = [{"start": 0.0, "end": 1.0, "text": "복구 자막"}]
        return True

    def _get_current_segments(self):
        return [dict(seg) for seg in self._segment_state]

    def window(self):
        return self._window

    def _current_project_path_for_dirty_check(self):
        return "/tmp/project.json"


class _DeferredProjectSaveEditor(EditorSaveManagerMixin):
    def __init__(self):
        self.media_path = "/tmp/deferred-source.mp4"
        self.video_fps = 30.0
        self.settings = {}
        self._saved_segments_signature = ""
        self._autosave_requires_manual_save = True
        self._has_unsaved_changes = Mock(return_value=True)
        self._flush_pending_segment_queue_now = Mock()
        self._warn_pending_stt_before_save = Mock(return_value=True)
        self._persist_editor_srts = Mock(return_value=True)
        self._auto_save_project = Mock(return_value="/tmp/deferred-project.aissproj")
        self._sync_queue_saved_state = Mock()
        self._show_confirm_dialog = Mock()
        self._window = SimpleNamespace(
            _current_project_path="/tmp/deferred-project.aissproj",
            _refresh_saved_status_label=Mock(),
        )
        self._segments = [{"start": 0.0, "end": 1.0, "text": "빠른 저장"}]

    def _get_current_segments(self):
        return [dict(seg) for seg in self._segments]

    def window(self):
        return self._window

    def _segments_for_srt_output(self, segs):
        return list(segs or [])


class _SourceSrtSaveEditor(EditorSaveManagerMixin):
    def __init__(self):
        self.media_path = "/tmp/media.mp4"
        self.video_fps = 30.0
        self._source_srt_path = "/tmp/opened.assets/subtitles/final.srt"
        self._window = SimpleNamespace(_multiclip_files=[])
        self._last_saved_srt_outputs = []

    def window(self):
        return self._window

    def _segments_for_srt_output(self, segs):
        return list(segs or [])


class _AutoProjectCreateSaveEditor(EditorSaveManagerMixin):
    def __init__(self):
        self.media_path = "/tmp/manual-save-source.mp4"
        self.settings = {"roughcut_llm_enabled": True}
        self.timeline = SimpleNamespace(
            lock_chk=SimpleNamespace(isChecked=Mock(return_value=False)),
            canvas=SimpleNamespace(_active_clip_idx=0),
        )
        self._window = SimpleNamespace(
            _current_project_path="",
            _multiclip_files=[],
            _log_visible=False,
            _dashboard_mode="dashboard",
            _project_panel_visible=True,
        )

    def window(self):
        return self._window


class _CompletionEditor(EditorPipelineMixin):
    def __init__(self):
        self._segment_state = [{"start": 0.0, "end": 1.0, "text": "ok"}]
        self.sm = SimpleNamespace(
            complete_ai=Mock(),
            complete_auto_mode=Mock(),
            stop_processing=Mock(),
            update_progress=Mock(),
        )
        self._flush_pending_segment_queue_now = Mock()
        self._clear_processing_indicators = Mock()
        self._safe_enable_start_btn = Mock()
        self._post_completion_sync = Mock()
        self._on_save = Mock(return_value=True)
        self._get_current_segments = Mock(side_effect=lambda: list(self._segment_state))
        self._refresh_editor_timestamp_metadata = Mock(return_value=0)
        self.append_segments = Mock(side_effect=self._append_segments_impl)
        self._set_auto_cut_boundary_scan_active = Mock()
        self._set_auto_cut_boundary_scan_lines = Mock()
        self._refresh_cut_boundary_placeholder_from_project = Mock()
        self.settings = {}
        self.is_auto_start = False
        self._segment_queue = []
        self._window = SimpleNamespace(
            _force_editor_idle_after_generation=Mock(),
            sync_menu_from_editor=Mock(),
            _refresh_saved_status_label=Mock(),
            _start_post_completion_idle_timer=Mock(),
            _unlock_workspace_sidebar_width=Mock(),
            _auto_processing_active=False,
            backend=SimpleNamespace(
                _active=False,
                _last_generation_final_segments=[],
                _last_generation_final_media_path="",
                _cut_boundary_prescan_thread=None,
                _cut_boundary_follower_thread=None,
            ),
            backend_fast=None,
        )
        self.media_path = "/tmp/test.mp4"

    def _append_segments_impl(self, segments):
        self._segment_state = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]

    def window(self):
        return self._window


class _PostCompletionSyncEditor(EditorPipelineMixin):
    def __init__(self, confirmed_segments, canvas_segments):
        self._confirmed_segments = [dict(seg) for seg in list(confirmed_segments or []) if isinstance(seg, dict)]
        self._cached_segs = [dict(seg) for seg in self._confirmed_segments]
        self._get_current_segments = Mock(side_effect=self._get_segments_impl)
        self._redraw_timeline = Mock()
        self._cache_current_segments = Mock(side_effect=self._cache_segments_impl)
        self.timeline = SimpleNamespace(
            canvas=SimpleNamespace(
                segments=[dict(seg) for seg in list(canvas_segments or []) if isinstance(seg, dict)],
                total_duration=max(
                    [float(seg.get("end", seg.get("start", 0.0)) or 0.0) for seg in list(canvas_segments or []) if isinstance(seg, dict)]
                    or [0.0]
                ),
                _multiclip_boxes=[],
                update=Mock(),
            ),
            _fit_to_view_locked=True,
            _manual_zoom_since_fit=True,
            fit_to_view=Mock(),
            global_canvas=SimpleNamespace(total_duration=0.0, update=Mock()),
        )

    def _get_segments_impl(self, force_rebuild: bool = False):
        return [dict(seg) for seg in list(self._confirmed_segments)]

    def _cache_segments_impl(self, segments):
        self._cached_segs = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
        return [dict(seg) for seg in self._cached_segs]


class _PipelineSignal:
    def __init__(self):
        self.connected = []

    def connect(self, slot):
        self.connected.append(slot)

    def disconnect(self, slot):
        self.connected = [item for item in self.connected if item != slot]


class EditorAutosaveCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_auto_save_is_fixed_to_five_minutes(self):
        editor = _AutoSaveEditor()
        editor.settings = {}
        self.assertEqual(editor._auto_save_interval_ms(), 300_000)

        editor.settings = {"editor_auto_save_interval_sec": 1}
        self.assertEqual(editor._auto_save_interval_ms(), 300_000)

        editor.settings = {"editor_auto_save_interval_sec": 600}
        self.assertEqual(editor._auto_save_interval_ms(), 300_000)

    def test_editor_does_not_start_periodic_auto_save_timer(self):
        editor = EditorWidget(
            "sample.m4a",
            [{"start": 0.0, "end": 1.0, "text": "테스트", "speaker": "00"}],
        )
        try:
            self.assertFalse(editor._auto_save_timer.isActive())
        finally:
            editor.close()

    def test_auto_save_is_disabled_even_when_document_state_changes(self):
        editor = _AutoSaveEditor()
        editor.sm = SimpleNamespace(
            is_locked=False,
            is_dirty=True,
            state="ST_EDITING",
            start_autosave=Mock(),
        )
        editor._has_unsaved_changes = Mock(return_value=False)
        editor._mark_save_completed = Mock()
        editor._get_current_segments = Mock(side_effect=AssertionError("unchanged autosave should not scan"))
        editor.sig_auto_save = SimpleNamespace(emit=Mock())
        editor._on_save = Mock()

        editor._on_auto_save()

        editor._has_unsaved_changes.assert_not_called()
        editor._mark_save_completed.assert_not_called()
        editor.sm.start_autosave.assert_not_called()
        editor.sig_auto_save.emit.assert_not_called()
        editor._on_save.assert_not_called()
        editor._get_current_segments.assert_not_called()

    def test_auto_save_remains_disabled_outside_editing_state(self):
        editor = _AutoSaveEditor()
        editor.sm = SimpleNamespace(is_locked=False, is_dirty=True, state="ST_COMP", start_autosave=Mock())
        editor._has_unsaved_changes = Mock(side_effect=AssertionError("disabled autosave must not inspect state"))
        editor._get_current_segments = Mock(side_effect=AssertionError("disabled autosave must not scan subtitles"))

        editor._on_auto_save()

        editor.sm.start_autosave.assert_not_called()
        editor._has_unsaved_changes.assert_not_called()

    def test_auto_save_remains_disabled_for_manual_confirm_operations(self):
        editor = _AutoSaveEditor()
        editor._autosave_requires_manual_save = True
        editor.sm = SimpleNamespace(is_locked=False, is_dirty=True, state="ST_EDITING", start_autosave=Mock())
        editor._has_unsaved_changes = Mock(side_effect=AssertionError("disabled autosave must not inspect manual-save state"))
        editor._get_current_segments = Mock(side_effect=AssertionError("disabled autosave must not scan"))

        editor._on_auto_save()

        editor.sm.start_autosave.assert_not_called()
        editor._has_unsaved_changes.assert_not_called()

    def test_auto_save_no_longer_cancels_or_saves_dirty_editor_content(self):
        editor = _AutoSaveEditor()
        editor.sm = SimpleNamespace(
            is_locked=False,
            is_dirty=True,
            state="ST_EDITING",
            start_autosave=Mock(),
        )
        editor._autosave_requires_manual_save = False
        editor._has_unsaved_changes = Mock(return_value=True)
        editor._cancel_post_generation_roughcut_draft = Mock(return_value=True)
        editor._get_current_segments = Mock(return_value=[{"start": 0.0, "end": 1.0, "text": "자동저장"}])
        editor._persist_editor_srts = Mock(return_value=True)
        editor._auto_save_project = Mock(return_value="/tmp/project.json")
        editor._remember_saved_segments = Mock()
        editor._remember_saved_project_file = Mock()
        editor._mark_save_completed = Mock()

        editor._on_auto_save()

        editor._has_unsaved_changes.assert_not_called()
        editor._cancel_post_generation_roughcut_draft.assert_not_called()
        editor.sm.start_autosave.assert_not_called()
        editor._get_current_segments.assert_not_called()
        editor._persist_editor_srts.assert_not_called()
        editor._auto_save_project.assert_not_called()
        editor._remember_saved_segments.assert_not_called()
        editor._remember_saved_project_file.assert_not_called()
        editor._mark_save_completed.assert_not_called()

    def test_manual_save_returns_immediately_when_nothing_changed(self):
        editor = _ManualSaveNoOpEditor()

        result = EditorSaveManagerMixin._on_save(editor, skip_auto_next=True)

        self.assertTrue(result)
        editor._has_unsaved_changes.assert_called_once()
        editor._mark_save_completed.assert_called_once_with(touch_saved_time=False)
        self.assertFalse(editor._autosave_requires_manual_save)
        editor._flush_pending_segment_queue_now.assert_not_called()
        editor._get_current_segments.assert_not_called()

    def test_manual_save_cancels_pending_roughcut_even_when_nothing_changed(self):
        editor = _ManualSaveNoOpEditor()
        editor._cancel_post_generation_roughcut_draft = Mock(return_value=True)

        result = EditorSaveManagerMixin._on_save(editor, skip_auto_next=True)

        self.assertTrue(result)
        editor._cancel_post_generation_roughcut_draft.assert_called_once_with(reason="수동 저장")
        editor._flush_pending_segment_queue_now.assert_not_called()
        editor._get_current_segments.assert_not_called()

    def test_manual_save_recovers_backend_backup_when_completion_temporarily_has_no_segments(self):
        editor = _CompletedRecoverySaveEditor()

        result = EditorSaveManagerMixin._on_save(
            editor,
            skip_auto_next=True,
            schedule_analysis_refresh=False,
            queue_learning=False,
            auto_export=False,
        )

        self.assertTrue(result)
        editor._flush_pending_segment_queue_now.assert_called_once()
        editor._recover_generation_segments_from_backend_backup.assert_called_once()
        editor._persist_editor_srts.assert_called_once()
        saved_segments = editor._persist_editor_srts.call_args.args[0]
        self.assertEqual([seg["text"] for seg in saved_segments], ["복구 자막"])
        editor._auto_save_project.assert_called_once()
        editor._mark_save_completed.assert_called_once_with(touch_saved_time=True)

    def test_manual_save_defers_project_save_after_srt_persist(self):
        editor = _DeferredProjectSaveEditor()

        result = EditorSaveManagerMixin._on_save(
            editor,
            skip_auto_next=True,
            schedule_analysis_refresh=False,
            queue_learning=False,
            auto_export=False,
        )

        self.assertTrue(result)
        editor._persist_editor_srts.assert_called_once()
        editor._auto_save_project.assert_not_called()
        self.assertTrue(editor._deferred_project_save_pending)
        self.assertEqual(editor._deferred_project_save_segments[0]["text"], "빠른 저장")

    def test_close_flushes_deferred_project_save_without_prompt_when_clean(self):
        editor = _DeferredProjectSaveEditor()
        editor._schedule_deferred_project_save(
            editor._get_current_segments(),
            schedule_analysis_refresh=False,
        )
        editor._has_unsaved_changes = Mock(return_value=False)

        self.assertTrue(editor._confirm_close_before_exit("종료 확인"))

        editor._auto_save_project.assert_called_once()
        editor._show_confirm_dialog.assert_not_called()
        self.assertFalse(editor._deferred_project_save_pending)

    def test_persist_editor_srts_prefers_opened_source_srt_path_for_direct_srt_mode(self):
        editor = _SourceSrtSaveEditor()

        with patch("ui.editor.editor_save_manager.save_srt") as save_mock:
            ok = editor._persist_editor_srts(
                [{"start": 0.0, "end": 1.0, "text": "열린 SRT"}],
                autosave=False,
            )

        self.assertTrue(ok)
        self.assertEqual(save_mock.call_args.args[1], "/tmp/opened.assets/subtitles/final.srt")
        self.assertEqual(editor._last_saved_srt_outputs, [("/tmp/opened.assets/subtitles/final.srt", "/tmp/media.mp4")])

    def test_manual_save_auto_project_create_does_not_prefill_roughcut_analysis(self):
        editor = _AutoProjectCreateSaveEditor()
        segs = [{"start": 0.0, "end": 1.0, "text": "외부 SRT 저장"}]

        with patch("core.project.project_manager.create_project", return_value="/tmp/generated.aissproj") as create_project, \
             patch("core.project.project_manager.save_project") as save_project, \
             patch("ui.editor.editor_save_manager.attach_project_session") as attach_project_session:
            project_path = editor._auto_save_project(segs, allow_create=True)

        self.assertEqual(project_path, "/tmp/generated.aissproj")
        self.assertFalse(create_project.call_args.kwargs["prefill_analysis_artifacts"])
        save_project.assert_called_once()
        self.assertFalse(save_project.call_args.kwargs["persist_analysis_artifacts"])
        attach_project_session.assert_called_once()

    def test_hook_backend_signals_reconnects_backend_and_batch_slots(self):
        backend = SimpleNamespace(
            sig_chunk_done=_PipelineSignal(),
            sig_progress=_PipelineSignal(),
            sig_batch_finished=_PipelineSignal(),
        )

        class _SignalEditor(EditorPipelineMixin):
            def __init__(self):
                self._window = SimpleNamespace(backend=backend)
                self.append_segments = Mock()
                self.update_progress = Mock()
                self._connect_cut_boundary_placeholder_signal = Mock()
                self._on_batch_finished = Mock()
                self.is_batch_mode = True

            def window(self):
                return self._window

        editor = _SignalEditor()

        editor._hook_backend_signals()

        editor._connect_cut_boundary_placeholder_signal.assert_called_once()
        self.assertEqual(backend.sig_chunk_done.connected, [editor.append_segments])
        self.assertEqual(backend.sig_progress.connected, [editor.update_progress])
        self.assertEqual(backend.sig_batch_finished.connected, [editor._on_batch_finished])

    def test_prepare_partial_rerun_state_trims_preview_and_prefix_vad(self):
        recorded_vad = {}
        removed_ranges = []
        cleared_ranges = []

        class _PartialEditor(EditorPipelineMixin):
            def __init__(self):
                self.timeline = SimpleNamespace(
                    canvas=SimpleNamespace(
                        vad_segments=[
                            {"start": 0.0, "end": 2.0},
                            {"start": 2.0, "end": 5.0},
                            {"start": 6.0, "end": 8.0},
                        ]
                    )
                )
                self._live_stt_preview_segments = [
                    {"start": 0.0, "end": 1.0, "text": "앞"},
                    {"start": 4.0, "end": 6.0, "text": "겹침"},
                ]

            def clear_segments_in_range(self, start, end):
                cleared_ranges.append((start, end))

            def set_vad_segments(self, segs):
                recorded_vad["segments"] = list(segs)

            def _remove_live_editor_preview_overlapping(self, ranges):
                removed_ranges.extend(list(ranges or []))

        editor = _PartialEditor()

        prefix_vad = editor._prepare_partial_rerun_state(4.0, 10.0, rerun_cut_boundaries=False)

        self.assertEqual(cleared_ranges, [])
        self.assertEqual(editor._partial_rerun_replace_range, (4.0, 10.0))
        self.assertFalse(editor._partial_rerun_replace_committed)
        self.assertEqual(editor._live_stt_preview_segments, [{"start": 0.0, "end": 1.0, "text": "앞"}])
        self.assertEqual(removed_ranges, [{"start": 4.0, "end": 10.0}])
        self.assertEqual(
            prefix_vad,
            [
                {"start": 0.0, "end": 2.0},
                {"start": 2.0, "end": 4.0},
            ],
        )
        self.assertEqual(recorded_vad["segments"], prefix_vad)

    def test_pending_internal_project_refresh_does_not_mark_clean_editor_dirty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "project.json")
            with open(project_path, "w", encoding="utf-8") as handle:
                handle.write("{\"version\":1}")
            editor = _PendingProjectRefreshEditor(project_path)
            editor._remember_saved_project_file(project_path)

            with open(project_path, "w", encoding="utf-8") as handle:
                handle.write("{\"version\":2}")

            self.assertFalse(editor._project_file_has_unsaved_changes())
            self.assertFalse(editor._has_unsaved_changes())

    def test_generation_idle_cleanup_clears_busy_surfaces_and_prefetch_cache(self):
        state_manager = SimpleNamespace(is_locked=True, state="ST_PROC", complete_ai=Mock())
        canvas = SimpleNamespace(
            _editor_processing_input_locked=True,
            setProperty=Mock(),
        )
        timeline = SimpleNamespace(canvas=canvas, set_playhead_busy=Mock(), set_playback_center_lock=Mock())
        video_player = SimpleNamespace(set_scan_cut_active=Mock())
        prefetch_manager = SimpleNamespace(clear=Mock())
        editor = SimpleNamespace(
            sm=state_manager,
            timeline=timeline,
            video_player=video_player,
            _background_prefetch_manager=prefetch_manager,
            _clear_processing_indicators=Mock(),
            _safe_enable_start_btn=Mock(),
        )
        window = SimpleNamespace(_editor_widget=None, _auto_processing_active=True, _restore_normal_cursor=Mock())

        with patch("ui.main.main_window.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            result = MainWindow._force_editor_idle_after_generation(window, editor, reason="test")

        self.assertTrue(result["idle"])
        self.assertFalse(editor._is_ai_processing)
        self.assertTrue(editor._subtitle_generation_completed)
        state_manager.complete_ai.assert_called()
        self.assertFalse(canvas._editor_processing_input_locked)
        canvas.setProperty.assert_called_with("editor_processing_input_locked", False)
        timeline.set_playhead_busy.assert_called_with(False)
        timeline.set_playback_center_lock.assert_called_with(False)
        video_player.set_scan_cut_active.assert_called_with(False)
        prefetch_manager.clear.assert_called_once()
        self.assertEqual(editor._last_background_prefetch_request, {})
        self.assertFalse(window._auto_processing_active)
        self.assertGreaterEqual(window._restore_normal_cursor.call_count, 1)

    def test_backend_generation_finalizer_autosaves_after_final_segments_exist(self):
        editor = _CompletionEditor()

        with patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._finalize_generation_from_backend(reason="test")
            editor._finalize_generation_from_backend(reason="duplicate")

        editor.sm.complete_ai.assert_called_once()
        self.assertGreaterEqual(editor._flush_pending_segment_queue_now.call_count, 1)
        editor._on_save.assert_called_once()
        self.assertFalse(editor._on_save.call_args.kwargs["cancel_post_generation_roughcut"])
        self.assertTrue(editor._on_save.call_args.kwargs["force"])
        self.assertTrue(editor._process_completed_finalized)
        self.assertTrue(getattr(editor, "_generation_completion_autosave_done", False))

    def test_set_process_completed_refreshes_timestamp_layer_after_queue_flush(self):
        editor = _CompletionEditor()

        with patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._set_process_completed()

        refresh_kwargs = [
            dict(call.kwargs)
            for call in editor._refresh_editor_timestamp_metadata.call_args_list
        ]
        self.assertIn({"full": True}, refresh_kwargs)
        self.assertIn({"full": False}, refresh_kwargs)

    def test_stt_progress_complete_does_not_finalize_before_backend_finalizer(self):
        editor = _CompletionEditor()
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor._completion_handled = False
        editor._process_completed_finalized = False
        editor.sm = SimpleNamespace(
            update_progress=Mock(),
            complete_ai=Mock(),
            _is_stage_status_active=Mock(return_value=False),
        )

        with patch("ui.editor.editor_pipeline.QTimer.singleShot") as single_shot:
            editor.update_progress(10, 10)

        editor.sm.complete_ai.assert_not_called()
        self.assertFalse(editor._completion_handled)
        self.assertFalse(editor._process_completed_finalized)
        self.assertEqual(editor.sm.update_progress.call_args_list[-1].args[3], "⏳ 자막 최적화/검수 중...")
        single_shot.assert_not_called()

    def test_backend_generation_finalizer_waits_until_segments_exist(self):
        editor = _CompletionEditor()
        editor._get_current_segments = Mock(return_value=[])
        editor.sm.update_progress = Mock()

        with patch("ui.editor.editor_pipeline.QTimer.singleShot") as single_shot:
            editor._finalize_generation_from_backend(reason="test")

        editor.sm.complete_ai.assert_not_called()
        self.assertFalse(getattr(editor, "_process_completed_finalized", False))
        self.assertEqual(editor.sm.update_progress.call_args_list[-1].args[3], "⏳ 최종 자막 반영 중...")
        single_shot.assert_called_once()

    def test_backend_generation_finalizer_releases_busy_state_when_final_segments_never_arrive(self):
        editor = _CompletionEditor()
        editor._segment_state = []
        editor._window.backend._active = True
        editor._window._auto_processing_active = True

        with patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._finalize_generation_from_backend(reason="test", attempt=60)

        editor.sm.stop_processing.assert_called_once_with("⚠️ 최종 자막 세그먼트 없음")
        editor._clear_processing_indicators.assert_called_once()
        editor._safe_enable_start_btn.assert_called_once()
        self.assertTrue(editor._process_completed_finalized)
        self.assertFalse(editor._window.backend._active)
        self.assertFalse(editor._window._auto_processing_active)
        editor._window._unlock_workspace_sidebar_width.assert_called_once()
        editor._window.sync_menu_from_editor.assert_called_with(editor)

    def test_generation_completion_autosave_waits_when_segments_are_missing(self):
        editor = _CompletionEditor()
        editor._get_current_segments = Mock(return_value=[])
        editor._segment_queue = []
        editor._generation_completion_autosave_done = False

        with patch("ui.editor.editor_pipeline.QTimer.singleShot") as single_shot:
            editor._run_generation_completion_autosave(attempt=0)

        editor._on_save.assert_not_called()
        single_shot.assert_called_once()
        self.assertTrue(getattr(editor, "_generation_completion_autosave_pending", False))

    def test_generation_completion_autosave_forces_save_without_canceling_roughcut(self):
        editor = _CompletionEditor()

        with patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._schedule_generation_completion_autosave(delay_ms=1)

        editor._on_save.assert_called_once()
        kwargs = editor._on_save.call_args.kwargs
        self.assertTrue(kwargs["force"])
        self.assertFalse(kwargs["cancel_post_generation_roughcut"])
        self.assertFalse(kwargs["queue_learning"])
        self.assertFalse(kwargs["auto_export"])
        self.assertTrue(editor._generation_completion_autosave_done)

    def test_backend_generation_finalizer_recovers_missing_segments_from_backend_backup(self):
        editor = _CompletionEditor()
        editor._segment_state = []
        editor._window.backend._last_generation_final_media_path = editor.media_path
        editor._window.backend._last_generation_final_segments = [
            {"start": 0.0, "end": 1.0, "text": "복구된 자막"},
        ]

        with patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._finalize_generation_from_backend(reason="test")

        editor.append_segments.assert_called_once()
        editor.sm.complete_ai.assert_called_once()
        editor._on_save.assert_called_once()
        self.assertTrue(editor._process_completed_finalized)
        self.assertEqual(editor._segment_state[0]["text"], "복구된 자막")

    def test_recover_generation_segments_from_backend_fast_backup_when_backend_exists(self):
        editor = _CompletionEditor()
        editor._segment_state = []
        editor._window.backend._last_generation_final_media_path = editor.media_path
        editor._window.backend._last_generation_final_segments = []
        editor._window.backend_fast = SimpleNamespace(
            _last_generation_final_media_path=editor.media_path,
            _last_generation_final_segments=[
                {"start": 0.0, "end": 1.0, "text": "fast 복구 자막"},
            ],
            _cut_boundary_prescan_thread=None,
            _cut_boundary_follower_thread=None,
        )

        recovered = editor._recover_generation_segments_from_backend_backup()

        self.assertTrue(recovered)
        editor.append_segments.assert_called_once()
        self.assertEqual(editor._segment_state[0]["text"], "fast 복구 자막")
        self.assertEqual(editor._window.backend_fast._last_generation_final_segments, [])

    def test_recover_generation_segments_from_backend_backup_accepts_samefile_path_variants(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media_path = os.path.join(tmpdir, "clip.mp4")
            with open(media_path, "wb") as handle:
                handle.write(b"data")
            alias_path = os.path.join(tmpdir, "alias.mp4")
            os.symlink(media_path, alias_path)

            editor = _CompletionEditor()
            editor._segment_state = []
            editor.media_path = media_path
            editor._window.backend._last_generation_final_media_path = alias_path
            editor._window.backend._last_generation_final_segments = [
                {"start": 0.0, "end": 1.0, "text": "samefile 복구 자막"},
            ]

            recovered = editor._recover_generation_segments_from_backend_backup()

            self.assertTrue(recovered)
            self.assertEqual(editor._segment_state[0]["text"], "samefile 복구 자막")

    def test_set_process_completed_clears_stale_cut_boundary_preview_when_backend_idle(self):
        editor = _CompletionEditor()

        with patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._set_process_completed()

        editor._set_auto_cut_boundary_scan_active.assert_called_with(False)
        editor._set_auto_cut_boundary_scan_lines.assert_called_with([])
        editor._refresh_cut_boundary_placeholder_from_project.assert_called_once()

    def test_set_process_completed_rebuilds_editor_to_drop_live_preview_artifacts(self):
        editor = _CompletionEditor()
        editor._clear_live_generation_preview_artifacts = Mock(return_value=True)

        with patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._set_process_completed()

        editor._clear_live_generation_preview_artifacts.assert_called_once()

    def test_set_process_completed_loads_deferred_waveform_after_resource_cleanup(self):
        editor = _CompletionEditor()
        calls = []
        editor._window._post_generation_resource_cleanup = Mock(side_effect=lambda **_kwargs: calls.append("cleanup"))
        editor._load_deferred_open_waveform = Mock(side_effect=lambda **kwargs: calls.append(("waveform", kwargs.get("reason"))))

        with patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._set_process_completed()

        self.assertEqual(calls[:2], ["cleanup", ("waveform", "generation_complete")])
        editor._load_deferred_open_waveform.assert_called_once_with(reason="generation_complete")

    def test_set_process_completed_can_skip_post_generation_side_effects_for_project_open(self):
        editor = _CompletionEditor()
        editor._load_deferred_open_waveform = Mock()

        with patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._set_process_completed(suppress_post_generation_tasks=True)

        editor.sm.complete_ai.assert_called_once()
        editor._post_completion_sync.assert_called_once()
        editor._load_deferred_open_waveform.assert_not_called()
        editor._set_auto_cut_boundary_scan_active.assert_not_called()
        editor._set_auto_cut_boundary_scan_lines.assert_not_called()
        editor._refresh_cut_boundary_placeholder_from_project.assert_not_called()
        editor._on_save.assert_not_called()

    def test_post_completion_sync_redraws_when_middle_boundary_changed_but_endpoints_match(self):
        confirmed = [
            {"start": 94.995, "end": 96.73, "text": "커피 드는데?"},
            {"start": 99.933, "end": 104.538, "text": "가자"},
            {"start": 104.538, "end": 106.707, "text": "하나 들고 가시모"},
        ]
        stale_canvas = [
            {"start": 94.995, "end": 96.73, "text": "커피 드는데?"},
            {"start": 99.933, "end": 106.707, "text": "가자"},
            {"start": 104.538, "end": 106.707, "text": "하나 들고 가시모"},
        ]
        editor = _PostCompletionSyncEditor(confirmed, stale_canvas)

        editor._post_completion_sync()

        editor._get_current_segments.assert_called_once_with(force_rebuild=True)
        editor._cache_current_segments.assert_called_once()
        self.assertEqual(editor._cache_current_segments.call_args.args[0], confirmed)
        editor._redraw_timeline.assert_called_once()

    def test_post_completion_sync_drops_transient_stt_rows_from_timeline(self):
        confirmed_with_pending = [
            {"start": 132.9, "end": 133.6, "text": "-", "stt_pending": True, "stt_preview_source": "STT2"},
            {"start": 135.102, "end": 138.672, "text": "이런거 다 가네"},
        ]
        canvas_with_pending = [
            {"start": 132.9, "end": 133.6, "text": "-", "stt_pending": True, "stt_preview_source": "STT2"},
            {"start": 135.102, "end": 138.672, "text": "이런거 다 가네"},
        ]
        editor = _PostCompletionSyncEditor(confirmed_with_pending, canvas_with_pending)

        editor._post_completion_sync()

        editor._get_current_segments.assert_called_once_with(force_rebuild=True)
        editor._cache_current_segments.assert_called_once()
        self.assertEqual(
            editor._cache_current_segments.call_args.args[0],
            [{"start": 135.102, "end": 138.672, "text": "이런거 다 가네"}],
        )
        editor._redraw_timeline.assert_called_once()

    def test_post_completion_sync_redraws_when_canvas_has_only_extra_stt_pending_row(self):
        confirmed = [
            {"start": 135.102, "end": 138.672, "text": "이런거 다 가네"},
        ]
        canvas_with_pending = [
            {"start": 132.9, "end": 133.6, "text": "-", "stt_pending": True, "stt_preview_source": "STT2"},
            {"start": 135.102, "end": 138.672, "text": "이런거 다 가네"},
        ]
        editor = _PostCompletionSyncEditor(confirmed, canvas_with_pending)

        editor._post_completion_sync()

        editor._get_current_segments.assert_called_once_with(force_rebuild=True)
        editor._cache_current_segments.assert_called_once()
        self.assertEqual(editor._cache_current_segments.call_args.args[0], confirmed)
        editor._redraw_timeline.assert_called_once()

    def test_post_completion_sync_keeps_stt_candidate_lanes_while_dropping_ghost_rows(self):
        confirmed = [
            {"start": 135.102, "end": 138.672, "text": "이런거 다 가네"},
        ]
        canvas_with_pending = [
            {"start": 132.9, "end": 133.6, "text": "-", "stt_pending": True, "stt_preview_source": "STT2"},
            {"start": 135.102, "end": 138.672, "text": "이런거 다 가네"},
        ]
        editor = _PostCompletionSyncEditor(confirmed, canvas_with_pending)
        editor._live_stt_preview_segments = [
            {"start": 132.9, "end": 133.6, "text": "-", "stt_preview_source": "STT2"},
            {"start": 137.0, "end": 138.0, "text": "후보", "stt_preview_source": "STT1"},
        ]

        editor._post_completion_sync()

        self.assertEqual(
            editor._live_stt_preview_segments,
            [
                {"start": 132.9, "end": 133.6, "text": "-", "stt_preview_source": "STT2"},
                {"start": 137.0, "end": 138.0, "text": "후보", "stt_preview_source": "STT1"},
            ],
        )
        self.assertEqual(editor._cache_current_segments.call_args.args[0], confirmed)
        editor._redraw_timeline.assert_called_once()

    def test_post_completion_sync_does_not_fit_view_after_roughcut_or_subtitle_completion(self):
        confirmed = [
            {"start": 94.995, "end": 96.73, "text": "커피 드는데?"},
        ]
        editor = _PostCompletionSyncEditor(confirmed, confirmed)
        editor.timeline.canvas._multiclip_boxes = [{"start": 0.0, "end": 180.0}]
        editor.timeline._fit_to_view_locked = False
        editor.timeline._manual_zoom_since_fit = False

        editor._post_completion_sync()

        editor.timeline.fit_to_view.assert_not_called()
        editor.timeline.global_canvas.update.assert_called_once()

    def test_post_completion_sync_skips_redraw_when_canvas_matches_confirmed_segments(self):
        confirmed = [
            {"start": 94.995, "end": 96.73, "text": "커피 드는데?"},
            {"start": 99.933, "end": 104.538, "text": "가자"},
            {"start": 104.538, "end": 106.707, "text": "하나 들고 가시모"},
        ]
        editor = _PostCompletionSyncEditor(confirmed, confirmed)

        editor._post_completion_sync()

        editor._get_current_segments.assert_called_once_with(force_rebuild=True)
        editor._cache_current_segments.assert_not_called()
        editor._redraw_timeline.assert_not_called()

    def test_project_save_suppresses_stale_provisional_boundaries_after_scan_completed(self):
        editor = _SaveBoundaryEditor()

        rows = editor._project_provisional_cut_boundaries_for_save()

        self.assertEqual(rows, [])

    def test_project_save_keeps_provisional_boundaries_while_scan_is_active(self):
        editor = _SaveBoundaryEditor()
        editor._auto_cut_boundary_scan_active = True

        rows = editor._project_provisional_cut_boundaries_for_save()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timeline_sec"], 12.0)


if __name__ == "__main__":
    unittest.main()
