import unittest
from types import SimpleNamespace
from unittest import mock

from ui.editor.editor_precision_refine import EditorPrecisionRefineMixin, _precision_clip_boundaries
from ui.log.terminal_log_widget import _friendly_log_entry


class _StatusLabel:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = str(text or "")


class _Editor(EditorPrecisionRefineMixin):
    def __init__(self):
        self.settings = {}
        self.video_fps = 30.0
        self.status_lbl = _StatusLabel()
        self._precision_refine_running = False
        self._is_ai_processing = False
        self.sm = SimpleNamespace(state="ST_IDLE")
        self.segments = []
        self.timeline = SimpleNamespace(
            canvas=SimpleNamespace(
                vad_segments=[],
                voice_activity_segments=[],
                boundary_times=[],
                scan_boundary_times=[],
            )
        )
        self.applied_segments = None
        self.applied_kwargs = None
        self.dirty = False
        self.scheduled = False
        self.refreshed = False
        self._undo_mgr = SimpleNamespace(push_immediate=mock.Mock())

    def _get_current_segments(self, force_rebuild=False):
        return [dict(seg) for seg in self.segments]

    def apply_loaded_canvas_state(self, segments, **kwargs):
        self.applied_segments = [dict(seg) for seg in segments]
        self.applied_kwargs = dict(kwargs)

    def _mark_dirty(self):
        self.dirty = True

    def _schedule_timeline(self):
        self.scheduled = True

    def _refresh_video_subtitle_context(self):
        self.refreshed = True

    def _update_quality_summary_label(self):
        self.quality_summary_updated = True


class _FakeLogger:
    def __init__(self):
        self.logs = []
        self.debug = []

    def log(self, message, *, level=None, stage=None):
        self.logs.append((str(message), level, stage))

    def terminal_debug(self, message, *, stage=None):
        self.debug.append((str(message), stage))


class EditorPrecisionRefineTests(unittest.TestCase):
    def test_precision_refine_available_requires_idle_real_subtitles(self):
        editor = _Editor()
        self.assertFalse(editor._precision_refine_available())

        editor.segments = [{"start": 0.0, "end": 1.0, "text": "안녕"}]
        self.assertTrue(editor._precision_refine_available())

        editor._is_ai_processing = True
        self.assertFalse(editor._precision_refine_available())
        editor._is_ai_processing = False

        editor.sm.state = "ST_PROC"
        self.assertFalse(editor._precision_refine_available())

    def test_start_precision_refine_dispatches_worker_thread(self):
        editor = _Editor()
        editor.media_path = "/tmp/sample.mp4"
        editor.segments = [{"start": 0.0, "end": 1.0, "text": "정밀 확인"}]
        created_threads = []

        class _FakeThread:
            def __init__(self, *, target, daemon, name):
                self.target = target
                self.daemon = daemon
                self.name = name
                self.started = False
                created_threads.append(self)

            def start(self):
                self.started = True

        with mock.patch("ui.editor.editor_precision_refine.threading.Thread", side_effect=lambda **kwargs: _FakeThread(**kwargs)):
            editor.start_precision_subtitle_refinement()

        self.assertTrue(editor._precision_refine_running)
        self.assertEqual(len(created_threads), 1)
        self.assertTrue(created_threads[0].started)
        self.assertTrue(created_threads[0].daemon)
        self.assertEqual(created_threads[0].name, "precision-subtitle-refine")

    def test_start_precision_refine_thread_start_failure_clears_worker_handles(self):
        editor = _Editor()
        editor.media_path = "/tmp/sample.mp4"
        editor.segments = [{"start": 0.0, "end": 1.0, "text": "정밀 확인"}]
        fake_logger = _FakeLogger()

        class _FailingThread:
            def start(self):
                raise RuntimeError("thread blocked")

        with mock.patch("ui.editor.editor_precision_refine.get_logger", return_value=fake_logger), \
             mock.patch("ui.editor.editor_precision_refine.show_message") as show, \
             mock.patch("ui.editor.editor_precision_refine.threading.Thread", return_value=_FailingThread()):
            editor.start_precision_subtitle_refinement()

        self.assertFalse(editor._precision_refine_running)
        self.assertIsNone(editor._precision_refine_token)
        self.assertIsNone(editor._precision_refine_thread)
        self.assertIsNone(editor._precision_refine_bridge)
        show.assert_called_once()
        self.assertTrue(any("스레드 시작 실패" in message for message, _level, _stage in fake_logger.logs))

    def test_precision_refine_apply_failure_clears_running_state_and_reports(self):
        editor = _Editor()
        token = object()
        editor._precision_refine_running = True
        editor._precision_refine_token = token
        editor._precision_refine_thread = object()
        editor._precision_refine_bridge = object()
        fake_logger = _FakeLogger()

        with mock.patch.object(editor, "_apply_precision_refine_result", side_effect=RuntimeError("apply failed")) as apply, \
             mock.patch("ui.editor.editor_precision_refine.get_logger", return_value=fake_logger), \
             mock.patch("ui.editor.editor_precision_refine.show_message") as show:
            editor._on_precision_refine_succeeded(token, {"before": [], "final_segments": []})

        apply.assert_called_once()
        self.assertFalse(editor._precision_refine_running)
        self.assertIsNone(editor._precision_refine_token)
        self.assertIsNone(editor._precision_refine_thread)
        self.assertIsNone(editor._precision_refine_bridge)
        self.assertEqual(editor.status_lbl.text, "정밀 자막 작업 실패")
        show.assert_called_once()
        self.assertTrue(any("UI 반영 실패" in message for message, _level, _stage in fake_logger.logs))

    def test_precision_refine_applies_quality_timing_and_magnet_result(self):
        editor = _Editor()
        editor.segments = [
            {
                "line": 0,
                "start": 1.0,
                "end": 2.0,
                "text": "안 녕",
                "words": [{"word": "안녕", "start": 1.08, "end": 1.82}],
            }
        ]
        editor.timeline.canvas.vad_segments = [{"start": 1.05, "end": 1.9, "kind": "speech"}]
        editor.timeline.canvas.voice_activity_segments = [
            {"start": 1.04, "end": 1.91, "label": "음성", "kind": "speech"},
            {"start": 3.0, "end": 4.0, "label": "대기", "kind": "idle"},
        ]
        editor.timeline.canvas.boundary_times = [0.5]
        editor.timeline.canvas.scan_boundary_times = [{"timeline_sec": 2.5}]

        quality_result = SimpleNamespace(
            segments=(
                {
                    "line": 0,
                    "start": 1.0,
                    "end": 2.0,
                    "text": "안녕",
                    "words": [{"word": "안녕", "start": 1.08, "end": 1.82}],
                },
            ),
            summary=SimpleNamespace(overall_score=98.0),
        )
        timed = [
            {
                "line": 0,
                "start": 1.05,
                "end": 1.9,
                "text": "안녕",
                "words": [{"word": "안녕", "start": 1.08, "end": 1.82}],
            }
        ]
        magneted = [
            {
                "line": 0,
                "start": 1.04,
                "end": 1.91,
                "text": "안녕",
            }
        ]

        with mock.patch("ui.editor.editor_precision_refine.run_subtitle_quality_pipeline", return_value=quality_result) as quality, \
             mock.patch("ui.editor.editor_precision_refine.refine_segment_edges_with_context", return_value=timed) as timing, \
             mock.patch("ui.editor.editor_precision_refine.run_selective_precision_whisper", return_value=SimpleNamespace(segments=tuple(timed), report={"target_count": 0, "accepted_count": 0})) as whisper, \
             mock.patch("ui.editor.editor_precision_refine.apply_netflix_subtitle_magnet", return_value=(magneted, {"closed_pairs": 1})) as magnet:
            editor._run_precision_subtitle_refinement()

        quality.assert_called_once()
        timing.assert_called_once()
        whisper.assert_called_once()
        magnet.assert_called_once()
        self.assertEqual(editor.applied_segments, magneted)
        self.assertEqual(editor.applied_kwargs["voice_activity_segments"][0]["source"], "precision_voice_lattice")
        self.assertIn("existing_voice_activity", editor.applied_kwargs["voice_activity_segments"][0]["vad_sources"])
        self.assertTrue(editor.dirty)
        self.assertTrue(editor.scheduled)
        self.assertTrue(editor.refreshed)
        self.assertEqual(editor._last_precision_refine_report["changed_count"], 1)
        self.assertEqual(editor._last_precision_refine_report["selective_precision_whisper"]["target_count"], 0)
        editor._undo_mgr.push_immediate.assert_called_once_with()

    def test_precision_refine_does_not_pass_cut_point_floats_as_clip_boundaries(self):
        editor = _Editor()
        editor.segments = [
            {
                "line": 0,
                "start": 1.0,
                "end": 2.0,
                "text": "정밀 확인",
                "quality": {"flags": ("outside_vad_speech",)},
            }
        ]
        editor.timeline.canvas.boundary_times = [0.5, {"timeline_sec": 2.5}]
        editor.timeline.canvas.scan_boundary_times = [3.0, {"timeline_sec": 4.0}]
        quality_result = SimpleNamespace(segments=tuple(editor.segments), summary=SimpleNamespace(overall_score=90.0))

        with mock.patch("ui.editor.editor_precision_refine.build_precision_vad_lattice_for_media", return_value=SimpleNamespace(segments=(), audio_paths={}, report={})) as lattice, \
             mock.patch("ui.editor.editor_precision_refine.run_subtitle_quality_pipeline", return_value=quality_result) as quality, \
             mock.patch("ui.editor.editor_precision_refine.refine_segment_edges_with_context", side_effect=lambda segments, **_kwargs: list(segments)), \
             mock.patch("ui.editor.editor_precision_refine.run_selective_precision_whisper", side_effect=lambda segments, **_kwargs: SimpleNamespace(segments=tuple(segments), report={"target_count": 0, "accepted_count": 0})), \
             mock.patch("ui.editor.editor_precision_refine.apply_netflix_subtitle_magnet", side_effect=lambda segments, **_kwargs: (list(segments), {"closed_pairs": 0})):
            editor._run_precision_subtitle_refinement()

        lattice.assert_called_once()
        quality.assert_called_once()
        self.assertEqual(quality.call_args.kwargs["context"]["clip_boundaries"], [])
        self.assertEqual(editor.applied_kwargs["boundary_times"], [0.5, {"timeline_sec": 2.5}])
        self.assertEqual(editor.applied_kwargs["provisional_boundaries"], [3.0, {"timeline_sec": 4.0}])

    def test_precision_clip_boundaries_keep_only_span_rows(self):
        rows = [
            1.0,
            {"timeline_sec": 2.0},
            {"start": 4.0, "end": 5.0, "file": "a.mp4"},
            {"start": 7.0, "end": 6.0},
        ]

        self.assertEqual(_precision_clip_boundaries(rows), [{"start": 4.0, "end": 5.0, "file": "a.mp4"}])

    def test_precision_refine_logs_start_progress_and_debug_details(self):
        editor = _Editor()
        editor.media_path = "/tmp/sample.mp4"
        editor.segments = [
            {
                "line": 0,
                "start": 1.0,
                "end": 2.0,
                "text": "정밀 확인",
                "words": [{"word": "정밀", "start": 1.1, "end": 1.5}],
            }
        ]
        editor.timeline.canvas.vad_segments = [{"start": 1.05, "end": 1.9, "kind": "speech"}]
        quality_result = SimpleNamespace(segments=tuple(editor.segments), summary=SimpleNamespace(overall_score=95.0))
        fake_logger = _FakeLogger()

        with mock.patch("ui.editor.editor_precision_refine.get_logger", return_value=fake_logger), \
             mock.patch("ui.editor.editor_precision_refine.build_precision_vad_lattice_for_media", return_value=SimpleNamespace(segments=(), audio_paths={}, source_counts={}, report={})) as lattice, \
             mock.patch("ui.editor.editor_precision_refine.run_subtitle_quality_pipeline", return_value=quality_result), \
             mock.patch("ui.editor.editor_precision_refine.refine_segment_edges_with_context", side_effect=lambda segments, **_kwargs: list(segments)), \
             mock.patch("ui.editor.editor_precision_refine.run_selective_precision_whisper", side_effect=lambda segments, **_kwargs: SimpleNamespace(segments=tuple(segments), report={"target_count": 0, "accepted_count": 0})), \
             mock.patch("ui.editor.editor_precision_refine.apply_netflix_subtitle_magnet", side_effect=lambda segments, **_kwargs: (list(segments), {"closed_pairs": 0})):
            editor._run_precision_subtitle_refinement()

        lattice.assert_called_once()
        messages = [message for message, _level, _stage in fake_logger.logs]
        self.assertTrue(any("시작:" in message for message in messages))
        self.assertTrue(any("VAD lattice 분석 시작" in message for message in messages))
        self.assertTrue(any("선택 정밀 Whisper 완료" in message for message in messages))
        self.assertTrue(any("완료:" in message for message in messages))
        self.assertTrue(all(stage == "precision" for _message, _level, stage in fake_logger.logs))
        debug_messages = [message for message, stage in fake_logger.debug if stage == "precision"]
        self.assertTrue(any("run start" in message for message in debug_messages))
        self.assertTrue(any("vad lattice input" in message for message in debug_messages))
        self.assertTrue(any("run complete" in message for message in debug_messages))

    def test_precision_log_lines_render_as_terminal_progress(self):
        category, summary = _friendly_log_entry("🔎 [정밀 자막] VAD lattice 분석 시작: 기존 VAD 2개")

        self.assertEqual(category, "precision")
        self.assertEqual(summary, "진행: 정밀 · 음성 경계")


if __name__ == "__main__":
    unittest.main()
