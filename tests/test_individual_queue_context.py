# Version: 03.15.00
# Phase: PHASE2
import unittest
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


if __name__ == "__main__":
    unittest.main()
