# Version: 03.09.24
# Phase: PHASE2
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from core.roughcut import (
    EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID,
    apply_roughcut_order_to_subtitles,
    build_editor_roughcut_candidate_payload,
    build_editor_roughcut_draft_result,
    describe_editor_roughcut_llm_scope,
    editor_roughcut_draft_enabled,
    editor_roughcut_draft_llm_allowed,
    merge_editor_roughcut_draft_state,
)
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_pipeline import EditorPipelineMixin
from ui.editor.editor_roughcut_draft import EditorRoughcutDraftMixin
from ui.editor.editor_segments_runtime_cache import EditorSegmentsRuntimeCacheMixin
from ui.timeline.timeline_analysis import roughcut_major_markers


def _segments(count: int = 7) -> list[dict]:
    out = []
    cursor = 0.0
    for idx in range(count):
        out.append(
            {
                "start": cursor,
                "end": cursor + 1.0,
                "text": f"자막 내용 {idx + 1}입니다",
                "speaker": "00",
            }
        )
        cursor += 1.2
    return out


class EditorRoughcutDraftTests(unittest.TestCase):
    def test_cancel_post_generation_roughcut_stops_pending_timer(self):
        class _Timer:
            def __init__(self):
                self.active = True

            def isActive(self):
                return self.active

            def stop(self):
                self.active = False

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self._roughcut_draft_timer = _Timer()
                self._roughcut_draft_pending = True
                self._roughcut_draft_generation = 4
                self._roughcut_draft_status = "queued"
                self._roughcut_draft_thread = None
                self.queue_done_calls = 0

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status

            def _mark_roughcut_queue_done(self, **_kwargs):
                self.queue_done_calls += 1

        editor = _Editor()

        cancelled = editor._cancel_post_generation_roughcut_draft(reason="test")

        self.assertTrue(cancelled)
        self.assertFalse(editor._roughcut_draft_timer.isActive())
        self.assertFalse(editor._roughcut_draft_pending)
        self.assertEqual(editor._roughcut_draft_generation, 5)
        self.assertEqual(editor._roughcut_draft_status, "idle")
        self.assertEqual(editor.queue_done_calls, 1)
        self.assertTrue(editor._roughcut_draft_cancelled)

    def test_cancelled_post_generation_roughcut_ignores_stale_timeout(self):
        class _Timer:
            def __init__(self):
                self.active = True

            def isActive(self):
                return self.active

            def stop(self):
                self.active = False

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self._roughcut_draft_timer = _Timer()
                self._roughcut_draft_pending = True
                self._roughcut_draft_generation = 1
                self._roughcut_draft_status = "queued"
                self._roughcut_draft_thread = None
                self.get_segments = mock.Mock(side_effect=AssertionError("cancelled roughcut must not inspect subtitles"))

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status

            def _mark_roughcut_queue_done(self, **_kwargs):
                pass

            def _get_current_segments(self):
                return self.get_segments()

        editor = _Editor()

        self.assertTrue(editor._cancel_post_generation_roughcut_draft(reason="수동 저장"))
        editor._run_post_generation_roughcut_draft()

        self.assertEqual(editor._roughcut_draft_status, "idle")
        self.assertFalse(editor._roughcut_draft_pending)
        editor.get_segments.assert_not_called()

    def test_foreground_activity_does_not_log_cancel_after_roughcut_done(self):
        class _Timer:
            def __init__(self):
                self.active = True
                self.stopped = False

            def isActive(self):
                return self.active

            def stop(self):
                self.active = False
                self.stopped = True

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self._roughcut_draft_timer = _Timer()
                self._roughcut_draft_pending = True
                self._roughcut_draft_generation = 2
                self._roughcut_draft_status = "done"
                self._roughcut_draft_thread = None

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status

        editor = _Editor()
        logger = mock.Mock()

        with mock.patch("ui.editor.editor_roughcut_draft.get_logger", return_value=logger):
            cancelled = editor._cancel_post_generation_roughcut_draft(reason="편집 시작")

        self.assertFalse(cancelled)
        self.assertFalse(editor._roughcut_draft_pending)
        self.assertTrue(editor._roughcut_draft_timer.stopped)
        logger.log.assert_not_called()

    def test_manual_save_cancel_blocks_delayed_auto_schedule_single_shot(self):
        class _Timer:
            def __init__(self):
                self.started = []
                self.active = False

            def isActive(self):
                return self.active

            def stop(self):
                self.active = False

            def start(self, ms):
                self.active = True
                self.started.append(int(ms))

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self._roughcut_draft_timer = _Timer()
                self._roughcut_draft_pending = True
                self._roughcut_draft_generation = 7
                self._roughcut_draft_status = "queued"
                self._roughcut_draft_thread = None
                self._roughcut_draft_auto_schedule_epoch = 3
                self._roughcut_draft_settings_override = None
                self.queue_notes = []

            def _roughcut_draft_post_generation_autorun_enabled(self):
                return True

            def _roughcut_draft_runtime_enabled(self):
                return True

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status

            def _mark_roughcut_queue_active(self, note):
                self.queue_notes.append(note)

            def _mark_roughcut_queue_done(self, **_kwargs):
                pass

        editor = _Editor()

        self.assertTrue(editor._cancel_post_generation_roughcut_draft(reason="수동 저장"))
        editor._schedule_post_generation_roughcut_draft(force=True)

        self.assertEqual(editor._roughcut_draft_status, "idle")
        self.assertFalse(editor._roughcut_draft_pending)
        self.assertEqual(editor._roughcut_draft_timer.started, [])
        self.assertEqual(editor.queue_notes, [])

        editor._roughcut_draft_manual_run_requested = True
        editor._schedule_post_generation_roughcut_draft(force=True, require_autorun=False)

        self.assertEqual(editor._roughcut_draft_status, "queued")
        self.assertTrue(editor._roughcut_draft_pending)
        self.assertEqual(editor._roughcut_draft_timer.started, [120])

    def test_manual_save_blocks_delayed_auto_schedule_even_if_pending_flag_was_cleared(self):
        class _Timer:
            def __init__(self):
                self.started = []
                self.active = False

            def isActive(self):
                return self.active

            def stop(self):
                self.active = False

            def start(self, ms):
                self.active = True
                self.started.append(int(ms))

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self._roughcut_draft_timer = _Timer()
                self._roughcut_draft_pending = False
                self._roughcut_draft_generation = 7
                self._roughcut_draft_status = "idle"
                self._roughcut_draft_thread = None
                self._roughcut_draft_auto_schedule_epoch = 4
                self._roughcut_draft_settings_override = None

            def _roughcut_draft_post_generation_autorun_enabled(self):
                return True

            def _roughcut_draft_runtime_enabled(self):
                return True

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status

            def _mark_roughcut_queue_active(self, note):
                raise AssertionError("manual-save-blocked roughcut must not update queue")

        editor = _Editor()

        self.assertFalse(editor._cancel_post_generation_roughcut_draft(reason="수동 저장"))
        editor._schedule_post_generation_roughcut_draft(force=True)

        self.assertEqual(editor._roughcut_draft_status, "idle")
        self.assertFalse(editor._roughcut_draft_pending)
        self.assertEqual(editor._roughcut_draft_timer.started, [])

    def test_foreground_activity_cancels_pending_post_generation_roughcut(self):
        class _Editor(EditorSegmentsRuntimeCacheMixin):
            def __init__(self):
                self.cancel_reasons = []

            def _cancel_post_generation_roughcut_draft(self, *, reason: str = "") -> bool:
                self.cancel_reasons.append(reason)
                return True

            def window(self):
                return SimpleNamespace()

        editor = _Editor()

        editor._note_editor_foreground_activity()

        self.assertEqual(editor.cancel_reasons, ["편집 시작"])
        self.assertGreater(getattr(editor, "_last_editor_foreground_activity_at", 0.0), 0.0)

    def test_clip_duration_clamp_logs_repeated_change_once(self):
        class _Editor(EditorSegmentsRuntimeCacheMixin):
            video_fps = 30.0

            def _segment_clip_total_duration(self) -> float:
                return 1.0

        editor = _Editor()
        rows = [{"start": 0.0, "end": 2.0, "text": "tail"}]
        logger = mock.Mock()

        with mock.patch("ui.editor.editor_segments_runtime_cache.get_logger", return_value=logger), \
             mock.patch("ui.editor.editor_segments_runtime_cache.time.monotonic", return_value=10.0):
            editor._clamp_segments_to_clip_duration(rows)
            editor._clamp_segments_to_clip_duration(rows)

        logger.log.assert_called_once()

    def test_manual_global_roughcut_saves_then_schedules_llm(self):
        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self.calls = []
                self._roughcut_draft_thread = None
                self._roughcut_llm_cooldown_until = 99.0

            def _on_save(self, **kwargs):
                self.calls.append(("save", kwargs))
                return True

            def _cancel_post_generation_roughcut_draft(self, *, reason: str = ""):
                self.calls.append(("cancel", reason))
                return True

            def _schedule_post_generation_roughcut_draft(self, force=False, *, require_autorun=True, settings_override=None):
                self.calls.append(("schedule", force, require_autorun, dict(settings_override or {})))

        editor = _Editor()

        editor._run_manual_roughcut_llm_from_global_canvas()

        self.assertEqual([call[0] for call in editor.calls], ["save", "cancel", "schedule"])
        self.assertTrue(editor.calls[0][1]["schedule_analysis_refresh"] is False)
        self.assertTrue(editor.calls[0][1]["queue_learning"] is False)
        self.assertTrue(editor.calls[2][1])
        self.assertFalse(editor.calls[2][2])
        self.assertTrue(editor.calls[2][3]["roughcut_llm_enabled"])
        self.assertEqual(editor._roughcut_llm_cooldown_until, 0.0)
        self.assertTrue(editor._roughcut_draft_manual_run_requested)

    def test_roughcut_middle_rows_sort_chronologically_before_apply(self):
        class _Editor(EditorRoughcutDraftMixin):
            pass

        editor = _Editor()
        rows = [
            {"major_id": "C", "start": 12.0, "end": 20.0},
            {"major_id": "A", "start": 0.0, "end": 5.0},
            {"major_id": "B", "start": 5.0, "end": 12.0},
        ]

        sorted_rows = editor._sorted_roughcut_middle_rows(rows)

        self.assertEqual([row["major_id"] for row in sorted_rows], ["A", "B", "C"])

    def test_post_generation_autorun_ignores_legacy_false_when_roughcut_llm_is_enabled(self):
        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self.settings = {
                    "editor_roughcut_draft_enabled": True,
                    "roughcut_run_after_subtitle_generation": False,
                    "roughcut_llm_enabled": True,
                }

            def _draft_settings_snapshot(self):
                return dict(self.settings)

        editor = _Editor()

        self.assertTrue(editor._roughcut_draft_post_generation_autorun_enabled())

    def test_post_generation_autorun_skips_when_roughcut_llm_is_disabled(self):
        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self.settings = {
                    "editor_roughcut_draft_enabled": True,
                    "roughcut_run_after_subtitle_generation": True,
                    "roughcut_llm_enabled": False,
                }

            def _draft_settings_snapshot(self):
                return dict(self.settings)

        editor = _Editor()

        self.assertFalse(editor._roughcut_draft_post_generation_autorun_enabled())

    def test_draft_settings_snapshot_uses_partial_rerun_override(self):
        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self.settings = {"stt_quality_preset": "fast", "selected_model": "old"}
                self._roughcut_draft_settings_override = {
                    "stt_quality_preset": "precise",
                    "selected_model": "roughcut-mode-model",
                }

        editor = _Editor()

        with mock.patch("core.settings.load_settings", return_value={}):
            snapshot = editor._draft_settings_snapshot()

        self.assertEqual(snapshot["stt_quality_preset"], "precise")
        self.assertEqual(snapshot["selected_model"], "roughcut-mode-model")

    def test_manual_partial_rerun_schedule_bypasses_autorun_gate(self):
        class _Timer:
            def __init__(self):
                self.started = []

            def isActive(self):
                return False

            def start(self, ms):
                self.started.append(int(ms))

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self._roughcut_draft_timer = _Timer()
                self._roughcut_draft_status = "idle"
                self._roughcut_draft_pending = False
                self._roughcut_draft_settings_override = None
                self.queue_notes = []

            def _roughcut_draft_post_generation_autorun_enabled(self):
                return False

            def _roughcut_draft_runtime_enabled(self):
                return True

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status

            def _mark_roughcut_queue_active(self, note):
                self.queue_notes.append(note)

        editor = _Editor()

        editor._schedule_post_generation_roughcut_draft(
            force=True,
            require_autorun=False,
            settings_override={"stt_quality_preset": "precise"},
        )

        self.assertEqual(editor._roughcut_draft_status, "queued")
        self.assertTrue(editor._roughcut_draft_pending)
        self.assertEqual(editor._roughcut_draft_timer.started, [120])
        self.assertEqual(editor._roughcut_draft_settings_override["stt_quality_preset"], "precise")

    def test_post_generation_draft_waits_for_cut_boundary_settle_when_project_has_provisionals(self):
        class _Timer:
            def __init__(self):
                self.started = []

            def start(self, ms):
                self.started.append(int(ms))

        class _Main:
            def __init__(self, path):
                self._current_project_path = path
                self._multiclip_files = []
                self._multiclip_boundaries = []
                self.backend = None
                self.backend_fast = None

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self, path):
                self.settings = {
                    "editor_roughcut_draft_enabled": True,
                    "roughcut_run_after_subtitle_generation": True,
                }
                self._main = _Main(path)
                self._roughcut_draft_timer = _Timer()
                self._roughcut_draft_status = "idle"
                self._roughcut_draft_thread = None
                self._auto_cut_boundary_scan_active = False
                self._auto_cut_boundary_scan_lines = []
                self.video_player = None

            def window(self):
                return self._main

            def _draft_settings_snapshot(self):
                return dict(self.settings)

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status

            def _get_current_segments(self):
                return _segments(6)

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/project.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "analysis": {
                            "cut_boundary_provisional_boundaries": [
                                {"timeline_sec": 12.5, "timeline_frame": 375, "fps": 30.0, "status": "provisional"}
                            ]
                        }
                    },
                    fh,
                    ensure_ascii=False,
                )
            editor = _Editor(path)

            editor._run_post_generation_roughcut_draft()

        self.assertEqual(editor._roughcut_draft_status, "queued")
        self.assertEqual(editor._roughcut_draft_timer.started, [900])

    def test_draft_reference_major_segments_prefers_project_topicless_segments(self):
        class _Main:
            def __init__(self, path):
                self._current_project_path = path

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self, path):
                self._main = _Main(path)
                self._middle_segments = [{"major_id": "Z", "title": "최종 중분류", "start": 0.0, "end": 10.0}]

            def window(self):
                return self._main

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/project.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "analysis": {
                            "cut_boundary_topicless_middle_segments": [
                                {"major_id": "A", "title": "주제없음", "start": 0.0, "end": 5.0}
                            ],
                            "middle_segments": [
                                {"major_id": "B", "title": "최종 중분류", "start": 0.0, "end": 5.0}
                            ],
                        }
                    },
                    fh,
                    ensure_ascii=False,
                )

            editor = _Editor(path)
            rows = editor._draft_reference_major_segments()

        self.assertEqual([row["major_id"] for row in rows], ["A"])

    def test_draft_reviewed_cut_boundaries_prefers_project_reviewed_rows_over_provisional_memory(self):
        class _Main:
            def __init__(self, path):
                self._current_project_path = path

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self, path):
                self._main = _Main(path)
                self._cut_boundary_provisional_rows = [{"candidate_key": "prov", "timeline_sec": 1.0}]

            def window(self):
                return self._main

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/project.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "analysis": {
                            "cut_boundary_reviewed_rows": [
                                {"candidate_key": "reviewed", "timeline_sec": 2.0, "verified": True}
                            ]
                        }
                    },
                    fh,
                    ensure_ascii=False,
                )

            editor = _Editor(path)
            rows = editor._draft_reviewed_cut_boundaries()

        self.assertEqual([row["candidate_key"] for row in rows], ["reviewed"])

    def test_apply_cut_boundary_topicless_rows_invalidates_global_canvas_static_cache(self):
        class _Carrier:
            def __init__(self):
                self.updated = False
                self.invalidated_markers = False
                self.invalidated_static = False
                self._paint_index_cache = {}

            def update(self):
                self.updated = True

            def _invalidate_marker_caches(self):
                self.invalidated_markers = True

            def _invalidate_static_cache(self):
                self.invalidated_static = True

        class _Timeline(_Carrier):
            def __init__(self):
                super().__init__()
                self.canvas = _Carrier()
                self.global_canvas = _Carrier()

        class _Main(_Carrier):
            pass

        class _Editor(EditorPipelineMixin, _Carrier):
            def __init__(self):
                _Carrier.__init__(self)
                self._main = _Main()
                self.timeline = _Timeline()

            def window(self):
                return self._main

        editor = _Editor()
        rows = [
            {
                "start": 0.0,
                "end": 12.0,
                "major_id": "A",
                "title": "주제없음",
                "is_topicless_placeholder": True,
            }
        ]

        editor._apply_cut_boundary_topicless_rows_to_ui(rows, source="cache")

        self.assertTrue(editor.invalidated_static)
        self.assertTrue(editor.timeline.canvas.invalidated_markers)
        self.assertTrue(editor.timeline.global_canvas.invalidated_static)
        self.assertTrue(editor.timeline.global_canvas.updated)
        self.assertEqual(editor.timeline.global_canvas._middle_segments, rows)
        self.assertEqual(editor._roughcut_result["source"], "cut_boundary_cache")

    def test_completion_schedules_roughcut_and_sync_after_cleanup(self):
        class _Timer:
            def __init__(self):
                self.stop_count = 0

            def stop(self):
                self.stop_count += 1

        class _State:
            def __init__(self):
                self.completed = False

            def complete_ai(self):
                self.completed = True

        class _Main:
            def __init__(self):
                self.release_calls = []

            def sync_menu_from_editor(self, _editor):
                pass

            def _refresh_saved_status_label(self, **_kwargs):
                pass

            def _start_post_completion_idle_timer(self):
                pass

            def _release_ai_models_for_editor_mode(self, *, force=False, preserve_roughcut_status=False):
                self.release_calls.append((force, preserve_roughcut_status))

        class _Editor(EditorPipelineMixin):
            def __init__(self, main):
                self.sm = _State()
                self.is_auto_start = False
                self._roughcut_draft_status = "idle"
                self.roughcut_schedule_count = 0
                self.post_sync_count = 0
                self._main = main
                self._spinner_timer = _Timer()
                self._last_live_processing_stage = "자막 LLM 검수 중"
                self._next_live_processing_stage_at = 123.0

            def window(self):
                return self._main

            def _schedule_post_generation_roughcut_draft(self, force=False):
                self.roughcut_schedule_count += 1
                self._roughcut_draft_status = "queued"

            def _post_completion_sync(self):
                self.post_sync_count += 1

            def _get_current_segments(self):
                return []

        scheduled = []

        def fake_single_shot(delay_ms, callback):
            scheduled.append((delay_ms, callback))

        main = _Main()
        editor = _Editor(main)

        with mock.patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=fake_single_shot):
            editor._set_process_completed()

            self.assertTrue(editor.sm.completed)
            self.assertEqual(editor._spinner_timer.stop_count, 1)
            self.assertEqual(editor._last_live_processing_stage, "")
            self.assertEqual(editor._next_live_processing_stage_at, 0.0)
            self.assertIn(0, [delay for delay, _callback in scheduled])
            self.assertEqual([delay for delay, _callback in scheduled[1:3]], [900, 200])

            next(callback for delay, callback in scheduled if delay == 900)()
            self.assertEqual(editor.roughcut_schedule_count, 1)

            next(callback for delay, callback in scheduled if delay == 200)()
            self.assertEqual(editor.post_sync_count, 1)
            self.assertEqual(main.release_calls, [])

            editor._roughcut_draft_status = "done"

        self.assertEqual(main.release_calls, [])

    def test_late_processing_stage_after_completion_is_ignored(self):
        class _Timer:
            def __init__(self):
                self.stop_count = 0

            def stop(self):
                self.stop_count += 1

        class _State:
            state = "ST_COMP"
            is_locked = False

            def __init__(self):
                self.custom_statuses = []

            def set_custom_status(self, msg):
                self.custom_statuses.append(msg)

        class _Label:
            def __init__(self):
                self.text = None

            def setText(self, text):
                self.text = text

        class _Editor(EditorPipelineMixin):
            def __init__(self):
                self.sm = _State()
                self.status_lbl = _Label()
                self._spinner_timer = _Timer()
                self._last_live_processing_stage = "자막 생성 중"
                self._next_live_processing_stage_at = 123.0

        editor = _Editor()

        editor.set_live_processing_stage("자막 LLM 검수 중 (10/10)")

        self.assertEqual(editor.sm.custom_statuses, [])
        self.assertIsNone(editor.status_lbl.text)
        self.assertEqual(editor._spinner_timer.stop_count, 1)
        self.assertEqual(editor._last_live_processing_stage, "")

    def test_fast_recognition_forces_editor_draft_off(self):
        self.assertFalse(
            editor_roughcut_draft_enabled(
                {"editor_roughcut_draft_enabled": True, "stt_quality_preset": "fast"}
            )
        )
        self.assertTrue(
            editor_roughcut_draft_enabled(
                {"editor_roughcut_draft_enabled": True, "stt_quality_preset": "balanced"}
            )
        )

    def test_long_editor_draft_uses_chunked_llm_scope_when_context_is_small(self):
        self.assertTrue(
            editor_roughcut_draft_llm_allowed(
                _segments(12),
                {"roughcut_llm_rows_auto_enabled": False, "roughcut_llm_max_context_rows": 5},
            )
        )
        self.assertTrue(
            editor_roughcut_draft_llm_allowed(
                _segments(5),
                {"roughcut_llm_rows_auto_enabled": False, "roughcut_llm_max_context_rows": 5},
            )
        )
        scope = describe_editor_roughcut_llm_scope(
            _segments(12),
            {"roughcut_llm_rows_auto_enabled": False, "roughcut_llm_max_context_rows": 5},
        )
        self.assertEqual(scope["mode"], "chunked")
        self.assertEqual(scope["max_context_rows"], 5)
        self.assertGreater(scope["chunk_count"], 1)
        for chunk in scope["chunks"]:
            self.assertLessEqual(
                chunk["prompt_end_index"] - chunk["prompt_start_index"] + 1,
                5,
            )

    def test_post_generation_long_video_runs_chunked_llm_instead_of_skipping(self):
        class _Signal:
            def __init__(self):
                self.calls = []

            def emit(self, result, segments, payload):
                self.calls.append((result, segments, payload))

        class _Main:
            _multiclip_files = []
            _multiclip_boundaries = []

        class _Player:
            total_time = 100.0

        class _Editor(EditorSegmentsMixin):
            def __init__(self):
                self.settings = {
                    "editor_roughcut_draft_enabled": True,
                    "selected_model": "gemma4:e4b",
                    "roughcut_llm_enabled": True,
                    "roughcut_llm_rows_auto_enabled": False,
                    "roughcut_llm_max_context_rows": 5,
                    "roughcut_major_min_subtitle_count": 1,
                    "editor_roughcut_draft_max_major_segments": 10,
                }
                self._roughcut_draft_status = "idle"
                self._roughcut_draft_thread = None
                self._roughcut_draft_generation = 0
                self._roughcut_llm_cooldown_until = 0.0
                self.sig_roughcut_draft_ready = _Signal()
                self.video_player = _Player()
                self.media_path = "/tmp/source.mp4"
                self._main = _Main()

            def window(self):
                return self._main

            def _draft_settings_snapshot(self):
                return dict(self.settings)

            def _get_current_segments(self):
                return _segments(12)

        editor = _Editor()
        class _ImmediateThread:
            def __init__(self, target, *args, **kwargs):
                self._target = target

            def start(self):
                self._target()

        llm_payload = {
            "major_segments": [
                {
                    "major_id": "A",
                    "title": "첫 묶음",
                    "start_subtitle_id": 0,
                    "end_subtitle_id": 5,
                    "confidence": 0.8,
                },
                {
                    "major_id": "B",
                    "title": "둘째 묶음",
                    "start_subtitle_id": 6,
                    "end_subtitle_id": 11,
                    "confidence": 0.8,
                },
            ]
        }
        with mock.patch("ui.editor.editor_roughcut_draft.threading.Thread", _ImmediateThread), \
             mock.patch("core.roughcut.run_editor_roughcut_llm_draft", return_value=llm_payload) as run_llm:
            editor._run_post_generation_roughcut_draft()

        self.assertIsNotNone(editor._roughcut_draft_thread)
        run_llm.assert_called_once()
        self.assertEqual(len(editor.sig_roughcut_draft_ready.calls), 1)
        result, segments, payload = editor.sig_roughcut_draft_ready.calls[0]
        self.assertEqual(payload["refinement_source"], "llm_refined")
        self.assertTrue(result.segments)
        self.assertEqual(len(segments), 12)

    def test_post_generation_uses_roughcut_override_model_even_when_subtitle_model_is_disabled(self):
        from core.llm.codex_provider import DEFAULT_CODEX_LABEL

        class _Signal:
            def __init__(self):
                self.calls = []

            def emit(self, result, segments, payload):
                self.calls.append((result, segments, payload))

        class _Main:
            _multiclip_files = []
            _multiclip_boundaries = []

        class _Player:
            total_time = 100.0

        class _Editor(EditorSegmentsMixin):
            def __init__(self):
                self.settings = {
                    "editor_roughcut_draft_enabled": True,
                    "selected_llm_provider": "none",
                    "selected_model": "사용 안함",
                    "roughcut_llm_enabled": True,
                    "roughcut_llm_use_override": True,
                    "roughcut_llm_provider": "openai",
                    "roughcut_llm_model": DEFAULT_CODEX_LABEL,
                    "roughcut_llm_rows_auto_enabled": False,
                    "roughcut_llm_max_context_rows": 12,
                    "roughcut_major_min_subtitle_count": 1,
                    "editor_roughcut_draft_max_major_segments": 10,
                }
                self._roughcut_draft_status = "idle"
                self._roughcut_draft_thread = None
                self._roughcut_draft_generation = 0
                self._roughcut_llm_cooldown_until = 0.0
                self.sig_roughcut_draft_ready = _Signal()
                self.video_player = _Player()
                self.media_path = "/tmp/source.mp4"
                self._main = _Main()

            def window(self):
                return self._main

            def _draft_settings_snapshot(self):
                return dict(self.settings)

            def _get_current_segments(self):
                return _segments(6)

        editor = _Editor()

        class _ImmediateThread:
            def __init__(self, target, *args, **kwargs):
                self._target = target

            def start(self):
                self._target()

        llm_payload = {
            "major_segments": [
                {
                    "major_id": "A",
                    "title": "첫 묶음",
                    "start_subtitle_id": 0,
                    "end_subtitle_id": 5,
                    "confidence": 0.8,
                }
            ]
        }
        with mock.patch("ui.editor.editor_roughcut_draft.threading.Thread", _ImmediateThread), \
             mock.patch("core.roughcut.run_editor_roughcut_llm_draft", return_value=llm_payload) as run_llm:
            editor._run_post_generation_roughcut_draft()

        self.assertIsNotNone(editor._roughcut_draft_thread)
        run_llm.assert_called_once()
        self.assertEqual(len(editor.sig_roughcut_draft_ready.calls), 1)
        result, segments, payload = editor.sig_roughcut_draft_ready.calls[0]
        self.assertEqual(payload["refinement_source"], "llm_refined")
        self.assertTrue(result.segments)
        self.assertEqual(len(segments), 6)

    def test_short_post_generation_autorun_logs_local_draft_reason_without_llm_thread(self):
        class _Signal:
            def __init__(self):
                self.calls = []

            def emit(self, result, segments, payload):
                self.calls.append((result, segments, payload))

        class _Main:
            _multiclip_files = []
            _multiclip_boundaries = []

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self.settings = {
                    "editor_roughcut_draft_enabled": True,
                    "selected_llm_provider": "openai",
                    "selected_model": "roughcut-ready",
                    "roughcut_llm_enabled": True,
                    "roughcut_major_min_subtitle_count": 5,
                }
                self._roughcut_draft_status = "idle"
                self._roughcut_draft_thread = None
                self._roughcut_draft_generation = 0
                self._roughcut_llm_cooldown_until = 0.0
                self.sig_roughcut_draft_ready = _Signal()
                self.video_player = None
                self.media_path = "/tmp/source.mp4"
                self._main = _Main()

            def window(self):
                return self._main

            def _draft_settings_snapshot(self):
                return dict(self.settings)

            def _get_current_segments(self):
                return _segments(2)

        editor = _Editor()
        logger = mock.Mock()

        with mock.patch("ui.editor.editor_roughcut_draft.get_logger", return_value=logger), \
             mock.patch("ui.editor.editor_roughcut_draft.threading.Thread") as thread_cls, \
             mock.patch("core.roughcut.run_editor_roughcut_llm_draft") as run_llm:
            editor._run_post_generation_roughcut_draft()

        thread_cls.assert_not_called()
        run_llm.assert_not_called()
        self.assertEqual(len(editor.sig_roughcut_draft_ready.calls), 1)
        _result, segments, payload = editor.sig_roughcut_draft_ready.calls[0]
        self.assertEqual(len(segments), 2)
        self.assertEqual(payload["refinement_source"], "local_after_generation")
        logged = "\n".join(str(call.args[0]) for call in logger.log.call_args_list if call.args)
        self.assertIn("최소 기준 5개 미만", logged)
        self.assertNotIn("러프컷 LLM 후처리 시작", logged)

    def test_post_generation_released_local_llm_uses_local_draft_without_thread(self):
        class _Signal:
            def __init__(self):
                self.calls = []

            def emit(self, result, segments, payload):
                self.calls.append((result, segments, payload))

        class _Main:
            _multiclip_files = []
            _multiclip_boundaries = []

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self.settings = {
                    "editor_roughcut_draft_enabled": True,
                    "selected_llm_provider": "ollama",
                    "selected_model": "gemma4:e4b",
                    "roughcut_llm_enabled": True,
                    "roughcut_major_min_subtitle_count": 1,
                }
                self._post_generation_models_release_requested = True
                self._post_generation_models_released = False
                self._roughcut_draft_status = "idle"
                self._roughcut_draft_thread = None
                self._roughcut_draft_generation = 0
                self._roughcut_llm_cooldown_until = 0.0
                self.sig_roughcut_draft_ready = _Signal()
                self.video_player = None
                self.media_path = "/tmp/source.mp4"
                self._main = _Main()

            def window(self):
                return self._main

            def _draft_settings_snapshot(self):
                return dict(self.settings)

            def _get_current_segments(self):
                return _segments(12)

        editor = _Editor()
        with mock.patch("ui.editor.editor_roughcut_draft.threading.Thread") as thread_cls, \
             mock.patch("core.roughcut.run_editor_roughcut_llm_draft") as run_llm:
            editor._run_post_generation_roughcut_draft()

        thread_cls.assert_not_called()
        run_llm.assert_not_called()
        self.assertEqual(len(editor.sig_roughcut_draft_ready.calls), 1)
        _result, segments, payload = editor.sig_roughcut_draft_ready.calls[0]
        self.assertEqual(payload["refinement_source"], "local_after_generation_runtime_released")
        self.assertEqual(len(segments), 12)

    def test_editor_draft_prompt_targets_post_generation_workflow(self):
        from core.roughcut import build_editor_roughcut_draft_prompt

        prompt = build_editor_roughcut_draft_prompt(_segments(3))
        payload = json.loads(prompt)

        self.assertEqual(payload["prompt_id"], "editor_post_generation_roughcut_draft_v1")
        self.assertIn("자막 생성이 완료된 뒤", payload["editor_instructions"])
        self.assertIn("전체를 먼저 훑어보고", payload["editor_instructions"])
        self.assertIn("화면 전환, 주제 전환, 장소 전환", payload["editor_instructions"])
        self.assertIn("실외에서 실내로 들어오거나", payload["editor_instructions"])
        self.assertIn("음향 경계로 먼저 크게 나뉜 구간 안에서도", payload["editor_instructions"])
        self.assertIn("단순한 말 끊김", payload["editor_instructions"])
        self.assertIn("10개 이하", payload["editor_instructions"])
        self.assertIn("공백 없이", payload["editor_instructions"])
        self.assertIn("중분류를 하나만 반환하면 잘못된 결과", payload["editor_instructions"])
        self.assertEqual(payload["workflow_steps"][0], "subtitle_rows 전체를 먼저 끝까지 읽고 영상 전체 내용을 파악한다.")

    def test_editor_draft_prompt_includes_reference_major_segments(self):
        from core.roughcut import build_editor_roughcut_draft_prompt

        prompt = build_editor_roughcut_draft_prompt(
            _segments(3),
            reference_major_segments=[
                {
                    "major_id": "A",
                    "title": "주제없음",
                    "summary": "컷 경계 기반 임시 중분류",
                    "start": 0.0,
                    "end": 3.6,
                    "timeline_start_frame": 0,
                    "timeline_end_frame": 108,
                    "frame_range": {"unit": "frame", "start": 0, "end": 108, "timeline_frame_rate": 30.0},
                    "is_topicless_placeholder": True,
                }
            ],
        )
        payload = json.loads(prompt)

        self.assertIn("reference_major_segments", payload)
        self.assertEqual(payload["reference_major_segments"][0]["major_id"], "A")
        self.assertTrue(payload["reference_major_segments"][0]["is_topicless_placeholder"])
        self.assertIn("임시 중분류 초안", payload["editor_instructions"])
        self.assertIn("실외→실내", payload["editor_instructions"])
        self.assertIn("추가로 다시 분리할 수 있다", payload["editor_instructions"])

    def test_editor_draft_prompt_includes_reviewed_audio_boundaries(self):
        from core.roughcut import build_editor_roughcut_draft_prompt

        prompt = build_editor_roughcut_draft_prompt(
            _segments(3),
            reviewed_cut_boundaries=[
                {
                    "candidate_key": "audio_01",
                    "timeline_sec": 12.5,
                    "timeline_frame": 375,
                    "source": "audio_gain_provisional",
                    "audio_gain_db_delta": 14.2,
                    "status": "checked",
                },
                {
                    "candidate_key": "visual_01",
                    "timeline_sec": 13.0,
                    "timeline_frame": 390,
                    "status": "verified",
                    "score": 92.0,
                },
            ],
        )
        payload = json.loads(prompt)

        self.assertIn("reviewed_cut_boundaries", payload)
        self.assertIn("audio_boundary_hints", payload)
        self.assertEqual(payload["audio_boundary_hints"][0]["kind"], "audio")
        self.assertEqual(payload["audio_boundary_hints"][0]["boundary_id"], "audio_01")
        self.assertIn("audio_boundary_hints는 후발대가 검토한 음성 경계 후보", payload["editor_instructions"])
        self.assertIn("reviewed_cut_boundaries는 후발대가 롤백 검토하며 다시 본 컷 경계 힌트", payload["editor_instructions"])

    def test_editor_draft_llm_uses_roughcut_specific_model_gate(self):
        from core.roughcut.editor_draft import run_editor_roughcut_llm_draft

        with mock.patch("core.roughcut.editor_draft._call_ollama_json") as call_ollama:
            disabled = run_editor_roughcut_llm_draft(
                _segments(3),
                settings={
                    "selected_model": "exaone3.5:7.8b",
                    "roughcut_llm_enabled": False,
                },
            )

        self.assertIsNone(disabled)
        call_ollama.assert_not_called()

        with mock.patch("core.roughcut.editor_draft._call_ollama_json", return_value={"major_segments": []}) as call_ollama:
            enabled = run_editor_roughcut_llm_draft(
                _segments(3),
                settings={
                    "selected_model": "사용 안함",
                    "roughcut_llm_enabled": True,
                    "roughcut_llm_use_override": True,
                    "roughcut_llm_provider": "ollama",
                    "roughcut_llm_model": "roughcut-local",
                },
            )

        self.assertEqual(enabled, {"major_segments": []})
        self.assertEqual(call_ollama.call_args.args[0], "roughcut-local")

    def test_editor_draft_prepares_different_roughcut_llm_before_ollama_call(self):
        from core.roughcut.editor_draft import run_editor_roughcut_llm_draft

        settings = {
            "selected_llm_provider": "ollama",
            "selected_model": "subtitle-local",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "roughcut-local",
        }
        with mock.patch("core.roughcut.editor_draft.prepare_roughcut_llm_model_for_run") as prepare, \
             mock.patch("core.roughcut.editor_draft._call_ollama_json", return_value={"major_segments": []}) as call_ollama:
            result = run_editor_roughcut_llm_draft(_segments(3), settings=settings)

        self.assertEqual(result, {"major_segments": []})
        prepare.assert_called_once()
        self.assertIs(prepare.call_args.args[0], settings)
        self.assertEqual(prepare.call_args.args[1].model, "roughcut-local")
        self.assertEqual(call_ollama.call_args.args[0], "roughcut-local")

    def test_editor_draft_codex_missing_cli_skips_chunk_retries(self):
        from core.llm.codex_provider import DEFAULT_CODEX_LABEL
        from core.roughcut.editor_draft import run_editor_roughcut_llm_draft

        settings = {
            "selected_llm_provider": "none",
            "selected_model": "사용 안함",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "openai",
            "roughcut_llm_model": DEFAULT_CODEX_LABEL,
            "roughcut_llm_rows_auto_enabled": False,
            "roughcut_llm_max_context_rows": 5,
        }
        with mock.patch(
            "core.llm.codex_provider.codex_cli_available",
            return_value=(False, "Codex CLI를 찾을 수 없습니다."),
        ) as available, mock.patch(
            "core.roughcut.editor_draft._call_openai_json",
            return_value={"major_segments": []},
        ) as call_openai, mock.patch(
            "core.roughcut.editor_draft.prepare_roughcut_llm_model_for_run"
        ) as prepare:
            result = run_editor_roughcut_llm_draft(_segments(12), settings=settings)

        self.assertIsNone(result)
        available.assert_called_once()
        prepare.assert_not_called()
        call_openai.assert_not_called()

    def test_editor_draft_codex_uses_tuned_chunks_and_longer_timeout(self):
        from core.llm.codex_provider import DEFAULT_CODEX_LABEL
        from core.roughcut.editor_draft import run_editor_roughcut_llm_draft

        settings = {
            "selected_llm_provider": "none",
            "selected_model": "사용 안함",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "openai",
            "roughcut_llm_model": DEFAULT_CODEX_LABEL,
            "roughcut_llm_rows_auto_enabled": True,
        }

        scope = describe_editor_roughcut_llm_scope(_segments(492), settings)
        self.assertEqual(scope["mode"], "chunked")
        self.assertGreaterEqual(scope["chunk_count"], 9)
        self.assertLessEqual(scope["chunk_count"], 12)
        self.assertGreaterEqual(scope["chunk_rows"], 48)
        self.assertLess(scope["chunk_rows"], 72)
        self.assertTrue(scope["policy"].get("codex_wide_context"))

        with mock.patch(
            "core.llm.codex_provider.codex_cli_available",
            return_value=(True, "/usr/local/bin/codex"),
        ), mock.patch(
            "core.roughcut.editor_draft.prepare_roughcut_llm_model_for_run"
        ), mock.patch(
            "core.roughcut.editor_draft._call_openai_json",
            return_value={"major_segments": []},
        ) as call_openai:
            result = run_editor_roughcut_llm_draft(_segments(6), settings=settings, timeout=45)

        self.assertEqual(result, {"major_segments": []})
        call_openai.assert_called_once()
        self.assertGreaterEqual(call_openai.call_args.kwargs["timeout"], 180)

    def test_chunked_codex_timeout_aborts_after_first_roughcut_llm_call(self):
        from core.llm.codex_provider import DEFAULT_CODEX_LABEL
        from core.roughcut.editor_draft import run_editor_roughcut_llm_draft

        settings = {
            "selected_llm_provider": "none",
            "selected_model": "사용 안함",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "openai",
            "roughcut_llm_model": DEFAULT_CODEX_LABEL,
            "roughcut_llm_rows_auto_enabled": False,
            "roughcut_llm_max_context_rows": 5,
        }
        with mock.patch(
            "core.llm.codex_provider.codex_cli_available",
            return_value=(True, "/usr/local/bin/codex"),
        ), mock.patch(
            "core.roughcut.editor_draft.prepare_roughcut_llm_model_for_run"
        ), mock.patch(
            "core.roughcut.editor_draft._call_openai_json",
            side_effect=RuntimeError("Codex CLI 실행 시간이 초과되었습니다."),
        ) as call_openai:
            result = run_editor_roughcut_llm_draft(_segments(12), settings=settings)

        self.assertIsNone(result)
        self.assertEqual(call_openai.call_count, 1)

    def test_editor_draft_ollama_call_uses_shared_python_client_provider(self):
        from core.roughcut.editor_draft import _call_ollama_json

        with mock.patch("core.llm.ollama_provider.generate_text", return_value='{"major_segments": []}') as generate:
            result = _call_ollama_json("roughcut-local", "prompt", timeout=7)

        self.assertEqual(result, {"major_segments": []})
        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[:2], ("roughcut-local", "prompt"))
        self.assertEqual(generate.call_args.kwargs["num_predict"], 1024)
        self.assertEqual(generate.call_args.kwargs["temperature"], 0.2)

    def test_chunked_connection_refused_aborts_after_first_roughcut_llm_call(self):
        from core.roughcut.editor_draft import run_editor_roughcut_llm_draft

        settings = {
            "selected_llm_provider": "ollama",
            "selected_model": "roughcut-local",
            "roughcut_llm_enabled": True,
            "roughcut_llm_rows_auto_enabled": False,
            "roughcut_llm_max_context_rows": 5,
        }
        with mock.patch("core.roughcut.editor_draft.prepare_roughcut_llm_model_for_run"), \
             mock.patch(
                 "core.roughcut.editor_draft._call_ollama_json",
                 side_effect=RuntimeError("[Errno 61] Connection refused"),
             ) as call_ollama:
            result = run_editor_roughcut_llm_draft(_segments(12), settings=settings)

        self.assertIsNone(result)
        self.assertEqual(call_ollama.call_count, 1)

    def test_failed_post_generation_draft_schedules_model_release(self):
        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self._roughcut_draft_generation = 0
                self._roughcut_draft_thread = object()
                self._roughcut_draft_status = "running"
                self.release_calls = 0

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status

            def _release_ai_models_after_roughcut_draft(self):
                self.release_calls += 1

        editor = _Editor()

        with mock.patch("ui.editor.editor_roughcut_draft.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._apply_post_generation_roughcut_draft(
                None,
                [],
                {"_generation": 0, "refinement_source": "failed"},
            )

        self.assertEqual(editor._roughcut_draft_status, "failed")
        self.assertIsNone(editor._roughcut_draft_thread)
        self.assertEqual(editor.release_calls, 1)

    def test_successful_post_generation_draft_schedules_model_release(self):
        class _Main:
            def __init__(self):
                self._current_project_path = "/tmp/editor-post-generation.aistudio"
                self._roughcut_widget = None
                self._editor_roughcut_result = None
                self._multiclip_boundaries = []
                self._auto_processing_active = True

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self, main):
                self._main = main
                self._roughcut_draft_generation = 0
                self._roughcut_draft_thread = object()
                self._roughcut_draft_status = "running"
                self._last_roughcut_draft_major_count = None
                self.settings = {}
                self.media_path = "/tmp/source.mp4"
                self.release_calls = 0
                self.redraw_calls = 0
                self.sm = SimpleNamespace(is_locked=True, state="ST_PROC", complete_ai=mock.Mock())
                self.timeline = SimpleNamespace(
                    canvas=SimpleNamespace(
                        _editor_processing_input_locked=True,
                        setProperty=mock.Mock(),
                    ),
                    set_playhead_busy=mock.Mock(),
                    set_playback_center_lock=mock.Mock(),
                )

            def window(self):
                return self._main

            def _draft_settings_snapshot(self):
                return dict(self.settings)

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status
                if count is not None:
                    self._last_roughcut_draft_major_count = count

            def _redraw_timeline(self):
                self.redraw_calls += 1

            def _release_ai_models_after_roughcut_draft(self):
                self.release_calls += 1

        segments = _segments(6)
        result = build_editor_roughcut_draft_result(segments, settings={"roughcut_major_min_subtitle_count": 2})
        candidate = build_editor_roughcut_candidate_payload(
            result,
            source_segments=segments,
            settings={},
            source_path="/tmp/source.mp4",
            source_media="현재 에디터",
            media_files=["/tmp/source.mp4"],
            clip_boundaries=[],
            editor_mode="single",
        )
        candidate["_generation"] = 0
        candidate["refinement_source"] = "llm_refined"

        main = _Main()
        editor = _Editor(main)

        with mock.patch("ui.editor.editor_roughcut_draft.QTimer.singleShot", side_effect=lambda _delay, callback: callback()), \
             mock.patch("core.project.project_manager.save_project_roughcut_state") as save_project_roughcut_state, \
             mock.patch("core.project.project_io.read_project_file", return_value={"roughcut_state": {}}), \
             mock.patch("ui.editor.editor_roughcut_draft.os.path.exists", return_value=False):
            editor._apply_post_generation_roughcut_draft(result, segments, candidate)

        save_project_roughcut_state.assert_called_once()
        self.assertEqual(
            save_project_roughcut_state.call_args.kwargs.get("preliminary_middle_segments"),
            list(candidate.get("segments", []) or []),
        )
        self.assertNotIn("segments", save_project_roughcut_state.call_args.kwargs)
        self.assertEqual(editor._roughcut_draft_status, "done")
        self.assertEqual(editor.release_calls, 1)
        self.assertEqual(editor.redraw_calls, 1)
        editor.sm.complete_ai.assert_called_once()
        self.assertFalse(editor.timeline.canvas._editor_processing_input_locked)
        editor.timeline.canvas.setProperty.assert_any_call("editor_processing_input_locked", False)
        editor.timeline.set_playhead_busy.assert_called_with(False)
        editor.timeline.set_playback_center_lock.assert_called_with(False)
        self.assertFalse(main._auto_processing_active)
        self.assertIs(main._editor_roughcut_result, result)
        self.assertIsNone(editor._roughcut_draft_thread)
        self.assertEqual(
            [row["major_id"] for row in getattr(editor, "_middle_segments")],
            [segment.major_id for segment in result.segments],
        )
        self.assertEqual(
            [row["major_id"] for row in getattr(editor, "_preliminary_middle_segments")],
            [segment.major_id for segment in result.segments],
        )

    def test_local_post_generation_draft_clears_finished_thread(self):
        class _Main:
            def __init__(self):
                self._current_project_path = "/tmp/editor-post-generation-local.aistudio"
                self._roughcut_widget = None
                self._editor_roughcut_result = None
                self._multiclip_boundaries = []
                self._auto_processing_active = True

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self, main):
                self._main = main
                self._roughcut_draft_generation = 0
                self._roughcut_draft_thread = object()
                self._roughcut_draft_status = "running"
                self._last_roughcut_draft_major_count = None
                self.settings = {}
                self.media_path = "/tmp/source.mp4"
                self.sm = SimpleNamespace(is_locked=True, state="ST_PROC", complete_ai=mock.Mock())
                self.timeline = SimpleNamespace(
                    canvas=SimpleNamespace(
                        _editor_processing_input_locked=True,
                        setProperty=mock.Mock(),
                    ),
                    set_playhead_busy=mock.Mock(),
                    set_playback_center_lock=mock.Mock(),
                )

            def window(self):
                return self._main

            def _draft_settings_snapshot(self):
                return dict(self.settings)

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status

            def _redraw_timeline(self):
                pass

            def _release_ai_models_after_roughcut_draft(self):
                pass

        segments = _segments(6)
        result = build_editor_roughcut_draft_result(segments, settings={"roughcut_major_min_subtitle_count": 2})
        candidate = build_editor_roughcut_candidate_payload(
            result,
            source_segments=segments,
            settings={},
            source_path="/tmp/source.mp4",
            source_media="현재 에디터",
            media_files=["/tmp/source.mp4"],
            clip_boundaries=[],
            editor_mode="single",
        )
        candidate["_generation"] = 0
        candidate["refinement_source"] = "local_after_generation_runtime_released"

        main = _Main()
        editor = _Editor(main)

        with mock.patch("ui.editor.editor_roughcut_draft.QTimer.singleShot", side_effect=lambda _delay, callback: callback()), \
             mock.patch("core.project.project_manager.save_project_roughcut_state"), \
             mock.patch("core.project.project_io.read_project_file", return_value={"roughcut_state": {}}), \
             mock.patch("ui.editor.editor_roughcut_draft.os.path.exists", return_value=False):
            editor._apply_post_generation_roughcut_draft(result, segments, candidate)

        self.assertEqual(editor._roughcut_draft_status, "done")
        self.assertIsNone(editor._roughcut_draft_thread)

    def test_chunked_editor_draft_merges_llm_chunks_using_global_subtitle_ids(self):
        from core.roughcut.editor_draft import run_editor_roughcut_llm_draft

        settings = {
            "selected_model": "roughcut-local",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "roughcut-local",
            "roughcut_llm_rows_auto_enabled": False,
            "roughcut_llm_max_context_rows": 5,
            "roughcut_llm_chunk_min_rows": 4,
            "roughcut_llm_chunk_max_rows": 5,
            "roughcut_llm_chunk_rows": 4,
            "roughcut_llm_lookahead_rows": 1,
        }
        llm_responses = [
            {
                "major_segments": [
                    {
                        "major_id": "A",
                        "title": "초반",
                        "start_subtitle_id": 0,
                        "end_subtitle_id": 3,
                        "confidence": 0.8,
                    }
                ]
            },
            {
                "major_segments": [
                    {
                        "major_id": "B",
                        "title": "중반",
                        "start_subtitle_id": 4,
                        "end_subtitle_id": 7,
                        "confidence": 0.8,
                    }
                ]
            },
            {
                "major_segments": [
                    {
                        "major_id": "C",
                        "title": "후반",
                        "start_subtitle_id": 8,
                        "end_subtitle_id": 11,
                        "confidence": 0.8,
                    }
                ]
            },
        ]

        with mock.patch("core.roughcut.editor_draft.prepare_roughcut_llm_model_for_run") as prepare, \
             mock.patch("core.roughcut.editor_draft._call_ollama_json", side_effect=llm_responses) as call_ollama:
            result = run_editor_roughcut_llm_draft(_segments(12), settings=settings)

        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(call_ollama.call_count, 3)
        self.assertEqual(result["_chunk_mode"], "cut_boundary_windowed")
        self.assertEqual(result["_chunk_count"], 3)
        self.assertEqual(
            [(row["start_subtitle_id"], row["end_subtitle_id"]) for row in result["major_segments"]],
            [(0, 3), (4, 7), (8, 11)],
        )

    def test_builds_major_segments_with_subtitle_rows_as_minor_groups(self):
        result = build_editor_roughcut_draft_result(
            _segments(7),
            settings={
                "roughcut_major_min_subtitle_count": 3,
                "editor_roughcut_draft_max_subtitle_count": 3,
            },
        )

        self.assertEqual(len(result.segments), 3)
        self.assertEqual(result.segments[0].major_id, "A")
        self.assertEqual(len(result.segments[0].minor_groups), 3)
        self.assertEqual(result.segments[0].minor_groups[0].subtitle_ids, (0,))
        self.assertEqual(len(result.chapters), 7)
        self.assertEqual(len(result.edl_segments), 3)

    def test_reference_major_segments_shape_local_draft_boundaries(self):
        result = build_editor_roughcut_draft_result(
            _segments(6),
            settings={"editor_roughcut_draft_max_major_segments": 10},
            reference_major_segments=[
                {
                    "major_id": "A",
                    "title": "주제없음",
                    "summary": "도입 구간",
                    "start": 0.0,
                    "end": 3.6,
                    "timeline_start_frame": 0,
                    "timeline_end_frame": 108,
                    "frame_range": {"unit": "frame", "start": 0, "end": 108, "timeline_frame_rate": 30.0},
                    "is_topicless_placeholder": True,
                },
                {
                    "major_id": "B",
                    "title": "주제없음",
                    "summary": "후반 구간",
                    "start": 3.6,
                    "end": 7.2,
                    "timeline_start_frame": 108,
                    "timeline_end_frame": 216,
                    "frame_range": {"unit": "frame", "start": 108, "end": 216, "timeline_frame_rate": 30.0},
                    "is_topicless_placeholder": True,
                },
            ],
        )

        self.assertEqual([segment.major_id for segment in result.segments], ["A", "B"])
        self.assertAlmostEqual(result.segments[0].start, 0.0)
        self.assertAlmostEqual(result.segments[0].end, result.segments[1].start)

    def test_llm_groups_merge_back_toward_reference_segments_when_oversplit(self):
        result = build_editor_roughcut_draft_result(
            _segments(8),
            settings={"editor_roughcut_draft_max_major_segments": 10},
            llm_payload={
                "major_segments": [
                    {"major_id": "A", "title": "도입1", "start_subtitle_id": 0, "end_subtitle_id": 1, "confidence": 0.8},
                    {"major_id": "B", "title": "도입2", "start_subtitle_id": 2, "end_subtitle_id": 3, "confidence": 0.8},
                    {"major_id": "C", "title": "후반1", "start_subtitle_id": 4, "end_subtitle_id": 5, "confidence": 0.8},
                    {"major_id": "D", "title": "후반2", "start_subtitle_id": 6, "end_subtitle_id": 7, "confidence": 0.8},
                ]
            },
            reference_major_segments=[
                {"major_id": "A", "title": "주제없음", "summary": "임시 중분류 앞", "start": 0.0, "end": 4.8},
                {"major_id": "B", "title": "주제없음", "summary": "임시 중분류 뒤", "start": 4.8, "end": 9.6},
            ],
        )

        self.assertEqual([segment.major_id for segment in result.segments], ["A", "B"])
        self.assertEqual(len(result.segments[0].subtitle_ids), 4)
        self.assertEqual(len(result.segments[1].subtitle_ids), 4)

    def test_llm_single_major_group_is_rejected_when_reference_has_multiple_segments(self):
        result = build_editor_roughcut_draft_result(
            _segments(12),
            settings={"editor_roughcut_draft_max_major_segments": 10},
            llm_payload={
                "major_segments": [
                    {
                        "major_id": "A",
                        "title": "전체 통합",
                        "summary": "영상 전체를 하나로 묶음",
                        "start_subtitle_id": 0,
                        "end_subtitle_id": 11,
                        "confidence": 0.9,
                        "status": "confirmed",
                    }
                ]
            },
            reference_major_segments=[
                {
                    "major_id": "A",
                    "title": "도입",
                    "summary": "도입 구간",
                    "start": 0.0,
                    "end": 7.2,
                },
                {
                    "major_id": "B",
                    "title": "후반",
                    "summary": "후반 구간",
                    "start": 7.2,
                    "end": 14.4,
                },
            ],
        )

        self.assertEqual([segment.major_id for segment in result.segments], ["A", "B"])
        self.assertGreater(len(result.segments[0].subtitle_ids), 0)
        self.assertGreater(len(result.segments[1].subtitle_ids), 0)

    def test_llm_single_major_group_is_rejected_for_long_subtitle_flow(self):
        result = build_editor_roughcut_draft_result(
            _segments(12),
            settings={
                "roughcut_major_min_subtitle_count": 1,
                "editor_roughcut_draft_max_subtitle_count": 2,
                "editor_roughcut_draft_max_major_segments": 10,
            },
            llm_payload={
                "major_segments": [
                    {
                        "major_id": "A",
                        "title": "전체 통합",
                        "summary": "긴 자막 흐름을 하나로 묶음",
                        "start_subtitle_id": 0,
                        "end_subtitle_id": 11,
                        "confidence": 0.9,
                        "status": "confirmed",
                    }
                ]
            },
        )

        self.assertGreaterEqual(len(result.segments), 2)
        self.assertEqual(result.segments[0].major_id, "A")
        self.assertEqual(result.segments[1].major_id, "B")

    def test_timeline_major_markers_expose_abc_segments(self):
        result = build_editor_roughcut_draft_result(
            _segments(6),
            settings={
                "roughcut_major_min_subtitle_count": 3,
                "editor_roughcut_draft_max_subtitle_count": 3,
            },
        )

        markers = roughcut_major_markers(result)

        self.assertEqual([m["label"] for m in markers], ["A", "B"])
        self.assertEqual(markers[0]["kind"], "roughcut_major")
        self.assertLess(markers[0]["start"], markers[0]["end"])

    def test_llm_major_ids_are_renumbered_and_limited_to_a_to_z_for_timeline(self):
        payload = {
            "major_segments": [
                {
                    "major_id": f"M{idx + 40}",
                    "title": f"묶음 {idx}",
                    "start_subtitle_id": idx,
                    "end_subtitle_id": idx,
                    "confidence": 0.8,
                }
                for idx in range(30)
            ]
        }

        result = build_editor_roughcut_draft_result(
            _segments(30),
            settings={"editor_roughcut_draft_max_major_segments": 26},
            llm_payload=payload,
        )
        labels = [marker["label"] for marker in roughcut_major_markers(result)]

        self.assertEqual(len(labels), 26)
        self.assertEqual(labels[0], "A")
        self.assertEqual(labels[-1], "Z")
        self.assertNotIn("M56", labels)

    def test_local_draft_default_targets_ten_major_segments(self):
        result = build_editor_roughcut_draft_result(
            _segments(60),
            settings={
                "roughcut_major_min_subtitle_count": 1,
                "editor_roughcut_draft_max_subtitle_count": 1,
            },
        )
        labels = [marker["label"] for marker in roughcut_major_markers(result)]

        self.assertEqual(len(labels), 10)
        self.assertEqual(labels, list("ABCDEFGHIJ"))

    def test_editor_draft_major_segments_cover_full_media_without_gaps(self):
        result = build_editor_roughcut_draft_result(
            [
                {"start": 1.0, "end": 2.0, "text": "인트로"},
                {"start": 4.0, "end": 5.0, "text": "본론"},
                {"start": 9.0, "end": 10.0, "text": "마무리"},
            ],
            media_duration=12.0,
            settings={
                "roughcut_major_min_subtitle_count": 1,
                "editor_roughcut_draft_max_subtitle_count": 1,
            },
        )

        self.assertEqual(result.segments[0].start, 0.0)
        self.assertEqual(result.segments[-1].end, 12.0)
        for previous, current in zip(result.segments, result.segments[1:]):
            self.assertAlmostEqual(previous.end, current.start)
        for decision, segment in zip(result.edit_decisions, result.segments):
            self.assertAlmostEqual(decision.source_start, segment.start)
            self.assertAlmostEqual(decision.source_end, segment.end)

    def test_merges_editor_draft_candidate_without_dropping_existing_candidates(self):
        segments = _segments(5)
        result = build_editor_roughcut_draft_result(segments)
        candidate = build_editor_roughcut_candidate_payload(
            result,
            source_segments=segments,
            source_path="/tmp/source.mp4",
            media_files=["/tmp/source.mp4"],
        )
        state = merge_editor_roughcut_draft_state(
            {"candidates": [{"candidate_id": "manual_candidate", "name": "수동 후보"}]},
            candidate,
        )

        self.assertEqual(state["selected_candidate_id"], EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID)
        self.assertEqual(state["candidate_count"], 2)
        self.assertEqual(state["candidates"][0]["candidate_id"], EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID)
        self.assertEqual(state["candidates"][1]["candidate_id"], "manual_candidate")

    def test_editor_save_order_requires_explicit_roughcut_flag(self):
        segments = _segments(5)
        result = build_editor_roughcut_draft_result(segments)
        candidate = build_editor_roughcut_candidate_payload(
            result,
            source_segments=segments,
            source_path="/tmp/source.mp4",
            media_files=["/tmp/source.mp4"],
        )
        state = merge_editor_roughcut_draft_state({}, candidate)
        self.assertEqual(apply_roughcut_order_to_subtitles(segments, state), segments)

        state["candidates"][0]["editor_save_order_enabled"] = True
        ordered = apply_roughcut_order_to_subtitles(segments, state)
        self.assertEqual(len(ordered), len(segments))
        self.assertEqual(ordered[0]["start"], 0.0)


if __name__ == "__main__":
    unittest.main()
