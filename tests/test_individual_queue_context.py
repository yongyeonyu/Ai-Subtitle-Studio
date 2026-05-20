# Version: 03.15.00
# Phase: PHASE2
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.backend_fast import CoreBackendFast
from core.pipeline.backend_core import CoreBackend


class _NoopThread:
    def __init__(self, *args, **kwargs):
        self.started = False

    def start(self):
        self.started = True

    def is_alive(self):
        return False

    def join(self, timeout=None):
        return None


class _ImmediateThread:
    def __init__(self, target=None, *args, **kwargs):
        self._target = target
        self._alive = False

    def start(self):
        self._alive = True
        if self._target is not None:
            self._target()
        self._alive = False

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        return None


class _JoinableThread:
    def __init__(self, *, alive=True, auto_finish=False):
        self._alive = bool(alive)
        self._auto_finish = bool(auto_finish)
        self.join_calls = []

    def start(self):
        return None

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        self.join_calls.append(timeout)
        if self._auto_finish:
            self._alive = False
        return None


class _Signal:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class _ImmediateTimer:
    def __init__(self, _delay, callback):
        self._callback = callback

    def start(self):
        if callable(self._callback):
            self._callback()


class _ActionEvent:
    def __init__(self, owner):
        self._owner = owner
        self._is_set = False

    def clear(self):
        self._is_set = False

    def set(self):
        self._is_set = True

    def wait(self, timeout=None):
        if self._is_set or getattr(self._owner, "action_state", "") != "wait":
            return True
        raise AssertionError("start_event waited before auto-start fired")


class _FakeActionSession:
    def __init__(self):
        self.action_state = "wait"
        self.state_ref = [self.action_state]
        self.final_segments = []
        self.start_event = _ActionEvent(self)
        self.edit_event = _ActionEvent(self)

    def callbacks(self, start_hook=None, stop_hook=None):
        def _sync_state(value):
            self.action_state = value
            self.state_ref[0] = value

        def on_save(segs):
            self.final_segments = list(segs or [])
            _sync_state("next")
            self.start_event.set()
            self.edit_event.set()

        def on_start():
            if callable(start_hook):
                start_hook()
            _sync_state("start")
            self.start_event.set()

        def on_prev():
            _sync_state("prev")
            self.start_event.set()
            self.edit_event.set()

        def on_exit(segs):
            self.final_segments = list(segs or [])
            _sync_state("exit")
            if callable(stop_hook):
                stop_hook()
            self.start_event.set()
            self.edit_event.set()

        return on_save, on_start, on_prev, on_exit


class _DummyUi:
    def __init__(self):
        self._runtime_settings_override = None
        self._multiclip_files = ["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"]
        self._multiclip_boundaries = [{"start": 0.0, "end": 10.0, "file": "/tmp/clip_a.mp4"}]
        self._accumulated_vad = [{"start": 1.0, "end": 2.0}]
        self._project_boundary_times = [10.0]
        self._reuse_clip_indices = {0}
        self._current_project_path = "/tmp/stale_project.json"
        self.queued_files = []

    def append_log(self, _msg):
        pass

    def init_queue_list(self, files):
        self.queued_files = list(files or [])


class _FakeVideoProcessor:
    def __init__(self):
        self._fast_mode_overrides = {"legacy": True}
        self._auto_audio_tune_overrides = {"selected_vad": "ten_vad"}
        self.hard_cut_boundaries = [1.0, 2.0]
        self.stage_callback = lambda *_args: None
        self.tune_calls = []

    def clear_fast_mode_overrides(self):
        self._fast_mode_overrides = None

    def clear_auto_audio_tune_overrides(self):
        self._auto_audio_tune_overrides = None

    def set_auto_audio_tune_overrides(self, overrides):
        self.tune_calls.append(dict(overrides or {}))
        self._auto_audio_tune_overrides = dict(overrides or {}) if overrides else None

    def extract_audio(self, target_file):
        return ("/tmp/chunks", [])


class IndividualQueueContextTests(unittest.TestCase):
    def test_single_manual_pipeline_initializes_one_card_queue_panel(self):
        ui = _DummyUi()
        backend = CoreBackend(ui)
        backend._ask_single_existing_subtitle = lambda _target: False

        with patch("core.pipeline.backend_core.threading.Thread", _NoopThread):
            backend.start_pipeline(["/tmp/manual_single.mp4"])

        self.assertFalse(backend._individual_queue_mode)
        self.assertTrue(backend._show_queue_for_current_run)
        self.assertEqual(ui.queued_files, ["/tmp/manual_single.mp4"])

    def test_restart_current_file_unblocks_start_wait_and_edit_wait(self):
        ui = _DummyUi()
        backend = CoreBackend(ui)
        backend._action_state = ["wait"]
        backend._start_event = threading.Event()
        backend._edit_event = threading.Event()
        backend._speaker_map = ["00"]

        backend.restart_current_file()

        self.assertEqual(backend._action_state, ["restart"])
        self.assertTrue(backend._start_event.is_set())
        self.assertTrue(backend._edit_event.is_set())
        self.assertEqual(backend._speaker_map, [])

    def test_wait_cut_boundary_prescan_before_stt_caps_long_prescan_wait(self):
        ui = _DummyUi()
        backend = CoreBackend(ui)
        backend._cut_boundary_prescan_thread = _JoinableThread(alive=True, auto_finish=False)
        backend._cut_boundary_follower_thread = None
        emitted = []
        backend._ui_emit = lambda *args, **kwargs: emitted.append(args) or True

        with patch("core.pipeline.cut_boundary_helpers.load_settings", return_value={}):
            backend._wait_cut_boundary_prescan_before_stt()

        self.assertEqual(backend._cut_boundary_prescan_thread.join_calls, [3.0])
        self.assertEqual(emitted, [])

    def test_wait_cut_boundary_prescan_before_stt_refreshes_when_threads_finish_quickly(self):
        ui = _DummyUi()
        backend = CoreBackend(ui)
        backend._cut_boundary_prescan_thread = _JoinableThread(alive=True, auto_finish=True)
        backend._cut_boundary_follower_thread = _JoinableThread(alive=True, auto_finish=True)
        emitted = []
        backend._ui_emit = lambda *args, **kwargs: emitted.append(args) or True

        with patch("core.pipeline.cut_boundary_helpers.load_settings", return_value={}):
            backend._wait_cut_boundary_prescan_before_stt()

        self.assertEqual(backend._cut_boundary_prescan_thread.join_calls, [3.0])
        self.assertEqual(backend._cut_boundary_follower_thread.join_calls, [1.0])
        self.assertEqual(
            emitted,
            [
                ("_sig_refresh_cut_boundary_placeholder",),
                ("_sig_refresh_cut_boundary_placeholder",),
            ],
        )

    def test_single_file_auto_start_does_not_wait_for_second_manual_start(self):
        ui = _DummyUi()
        backend = CoreBackend(ui)
        backend.files_to_process = ["/tmp/auto_single.mp4"]
        backend.is_auto_start = True
        backend._individual_queue_mode = True
        backend._active = True
        backend.video_processor = SimpleNamespace(
            clear_fast_mode_overrides=lambda: None,
            set_auto_audio_tune_overrides=lambda _value: None,
            stage_callback=None,
        )
        backend._backup_existing = lambda *_args, **_kwargs: None
        backend._subtitle_generation_memory_checkpoint = lambda *_args, **_kwargs: None
        backend._ui_attr = (
            lambda name, *_args, **_kwargs: (lambda *_a, **_k: True)
            if name == "open_editor_for_file_and_wait"
            else None
        )
        backend._ui_call = lambda method, *_args, **_kwargs: True if method == "open_editor_for_file_and_wait" else None
        backend._ui_emit = lambda *_args, **_kwargs: True
        backend._ui_object = lambda: SimpleNamespace(
            _current_project_path="/tmp/existing_project.aissproj",
            _multiclip_files=["/tmp/auto_single.mp4"],
            _editor_widget=SimpleNamespace(settings={}),
        )
        backend._auto_scan_cut_boundaries_for_start = lambda *_args, **_kwargs: None
        backend._apply_personalization_runtime_override_for_file = lambda *_args, **_kwargs: {}
        backend._reload_speaker_settings = lambda: None
        backend._wait_cut_boundary_prescan_before_stt = lambda: (_ for _ in ()).throw(RuntimeError("auto-start-reached"))

        with patch("core.pipeline.single_pipeline.SinglePipelineActionSession", _FakeActionSession), \
             patch("core.pipeline.single_pipeline.threading.Timer", _ImmediateTimer):
            with self.assertRaisesRegex(RuntimeError, "auto-start-reached"):
                backend._process_one("/tmp/auto_single.mp4", 0)

    def test_folder_pipeline_clears_multiclip_context_before_queue_run(self):
        ui = _DummyUi()
        backend = CoreBackend(ui)

        with patch("core.pipeline.backend_core.threading.Thread", _NoopThread):
            backend.start_pipeline(
                ["/tmp/folder_clip_1.mp4", "/tmp/folder_clip_2.mp4"],
                folder="/tmp/source_folder",
            )

        self.assertTrue(backend._individual_queue_mode)
        self.assertEqual(ui._multiclip_files, [])
        self.assertEqual(ui._multiclip_boundaries, [])
        self.assertEqual(ui._accumulated_vad, [])
        self.assertEqual(ui._project_boundary_times, [])
        self.assertEqual(ui._reuse_clip_indices, set())
        self.assertIsNone(ui._current_project_path)
        self.assertEqual(ui.queued_files, ["/tmp/folder_clip_1.mp4", "/tmp/folder_clip_2.mp4"])

    def test_fast_batch_clears_multiclip_context_before_queue_run(self):
        ui = _DummyUi()
        backend = CoreBackendFast(ui)

        with patch("core.backend_fast.threading.Thread", _NoopThread):
            backend.start_batch(
                ["/tmp/auto_clip_1.mp4", "/tmp/auto_clip_2.mp4"],
                folder="/tmp/auto_folder",
            )

        self.assertTrue(backend._individual_queue_mode)
        self.assertEqual(ui._multiclip_files, [])
        self.assertEqual(ui._multiclip_boundaries, [])
        self.assertEqual(ui._accumulated_vad, [])
        self.assertEqual(ui._project_boundary_times, [])
        self.assertEqual(ui._reuse_clip_indices, set())
        self.assertIsNone(ui._current_project_path)
        self.assertEqual(ui.queued_files, ["/tmp/auto_clip_1.mp4", "/tmp/auto_clip_2.mp4"])

    def test_individual_clip_reset_clears_backend_and_audio_state(self):
        ui = _DummyUi()
        backend = CoreBackend(ui)
        backend.video_processor = _FakeVideoProcessor()
        backend._speaker_map = [{"speaker": "old"}]
        backend._reuse_existing_single_subtitle = True
        backend._reuse_existing_multiclip_subtitles = True
        backend._reuse_clip_indices = {0}
        backend._cut_boundary_pipeline_cache = {"old": True}
        backend._cut_boundary_provisional_rows = [{"start": 1.0}]
        backend._auto_audio_tune_cache = {"/tmp/old.mp4": {"audio_preset": "old"}}
        backend._prefetch_cache = {"/tmp/next.mp4": ("cached", [])}
        backend._prefetch_threads = {"/tmp/next.mp4": object()}
        old_generation = backend._prefetch_generation

        backend._reset_backend_individual_clip_context(invalidate_prefetch=True)

        self.assertEqual(backend._speaker_map, [])
        self.assertFalse(backend._reuse_existing_single_subtitle)
        self.assertFalse(backend._reuse_existing_multiclip_subtitles)
        self.assertEqual(backend._reuse_clip_indices, set())
        self.assertIsNone(backend._cut_boundary_pipeline_cache)
        self.assertEqual(backend._cut_boundary_provisional_rows, [])
        self.assertEqual(backend._auto_audio_tune_cache, {})
        self.assertEqual(backend._prefetch_cache, {})
        self.assertEqual(backend._prefetch_threads, {})
        self.assertGreater(backend._prefetch_generation, old_generation)
        self.assertIsNone(backend.video_processor._fast_mode_overrides)
        self.assertIsNone(backend.video_processor._auto_audio_tune_overrides)
        self.assertEqual(backend.video_processor.hard_cut_boundaries, [])
        self.assertIsNone(backend.video_processor.stage_callback)

    def test_empty_auto_audio_tune_clears_previous_clip_override(self):
        ui = _DummyUi()
        backend = CoreBackend(ui)
        backend.video_processor = _FakeVideoProcessor()
        backend._auto_audio_tune_settings_for_file = lambda _target: {}
        backend._validate_audio_extract_result = lambda result, *_args, **_kwargs: result

        result = backend._get_audio_extract_result("/tmp/clip_without_tune.mp4")

        self.assertEqual(result, ("/tmp/chunks", []))
        self.assertEqual(backend.video_processor.tune_calls, [{}])
        self.assertIsNone(backend.video_processor._auto_audio_tune_overrides)

    def test_audio_extract_publishes_runtime_auto_tune_to_sidebar(self):
        ui = _DummyUi()
        ui._sig_runtime_audio_tune = _Signal()
        backend = CoreBackend(ui)
        backend.video_processor = _FakeVideoProcessor()
        backend._auto_audio_tune_settings_for_file = lambda _target: {
            "selected_audio_ai": "clearvoice",
            "selected_vad": "ten_vad",
        }
        backend._validate_audio_extract_result = lambda result, *_args, **_kwargs: result

        result = backend._get_audio_extract_result("/tmp/clip_with_tune.mp4")

        self.assertEqual(result, ("/tmp/chunks", []))
        self.assertEqual(backend.video_processor.tune_calls, [{"selected_audio_ai": "clearvoice", "selected_vad": "ten_vad"}])
        self.assertEqual(len(ui._sig_runtime_audio_tune.calls), 1)
        target_file, payload = ui._sig_runtime_audio_tune.calls[0]
        self.assertEqual(target_file, "/tmp/clip_with_tune.mp4")
        self.assertEqual(payload["tune"]["selected_audio_ai"], "clearvoice")
        self.assertEqual(payload["tune"]["selected_vad"], "ten_vad")

    def test_prefetch_only_warms_audio_cache_without_reusing_chunks(self):
        calls = []

        class _PrefetchVideoProcessor:
            def set_auto_audio_tune_overrides(self, overrides):
                pass

            def extract_audio(self, target_file, **kwargs):
                calls.append((target_file, dict(kwargs)))
                return ("/tmp/stale_chunks", [])

            def stop_transcribe(self):
                pass

        ui = _DummyUi()
        backend = CoreBackend(ui)
        backend._active = True
        backend._auto_audio_tune_settings_for_file = lambda _target: {}

        with patch("core.pipeline.pipeline_helpers.VideoProcessor", _PrefetchVideoProcessor), patch(
            "core.pipeline.pipeline_helpers.threading.Thread",
            _ImmediateThread,
        ):
            backend._prefetch_audio_for_file("/tmp/prefetch.mp4")

        self.assertEqual(calls, [("/tmp/prefetch.mp4", {"prefetch_only": True})])
        self.assertIsNone(backend._prefetch_cache.get("/tmp/prefetch.mp4"))

    def test_queue_clip_save_does_not_clear_missing_analysis_metadata(self):
        ui = _DummyUi()
        ui._editor_widget = None
        ui._current_project_path = "/tmp/project.json"
        backend = CoreBackend(ui)

        with patch("core.project.project_manager.save_project") as save_project:
            project_path = backend._save_project_for_queue_clip(
                "/tmp/source.mp4",
                "/tmp/source.srt",
                [{"start": 0.0, "end": 1.0, "text": "hello"}],
            )

        self.assertEqual(project_path, "/tmp/project.json")
        kwargs = save_project.call_args.kwargs
        self.assertIsNone(kwargs["voice_activity_segments"])
        self.assertIsNone(kwargs["stt_preview_segments"])
        self.assertIsNone(kwargs["provisional_cut_boundaries"])


if __name__ == "__main__":
    unittest.main()
