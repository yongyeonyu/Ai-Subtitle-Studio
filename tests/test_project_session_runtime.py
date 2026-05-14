import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from ui.project.project_session_runtime import (
    apply_project_multiclip_runtime,
    attach_project_session,
    clear_multiclip_runtime_state,
    detach_project_session,
    load_local_project_settings,
    save_local_project_settings,
    set_project_boundary_rows,
    set_runtime_multiclip_state,
    sorted_project_media_paths,
)


class _Signal:
    def __init__(self):
        self.emitted = []

    def emit(self, payload):
        self.emitted.append(list(payload or []))


class ProjectSessionRuntimeTests(unittest.TestCase):
    def test_clear_multiclip_runtime_state_resets_lists_and_flags(self):
        owner = SimpleNamespace(
            _multiclip_files=["a.mp4"],
            _multiclip_boundaries=[{"end": 1.0}],
            _accumulated_vad=[{"start": 0.0}],
            _reuse_existing_multiclip_subtitles=True,
        )
        clear_multiclip_runtime_state(owner)
        self.assertEqual(owner._multiclip_files, [])
        self.assertEqual(owner._multiclip_boundaries, [])
        self.assertEqual(owner._accumulated_vad, [])
        self.assertFalse(owner._reuse_existing_multiclip_subtitles)

    def test_detach_project_session_clears_project_runtime_and_emits_boundary_reset(self):
        signal = _Signal()
        owner = SimpleNamespace(
            _current_project_path="/tmp/sample.json",
            _project_boundary_times=[1.0, 2.0],
            _is_auto_pipeline=False,
            _multiclip_files=["a.mp4"],
            _multiclip_boundaries=[{"end": 1.0}],
            _accumulated_vad=[{"start": 0.0}],
            _reuse_existing_multiclip_subtitles=True,
            _sig_update_project_boundary_times=signal,
        )
        detach_project_session(owner, auto_pipeline=True)
        self.assertIsNone(owner._current_project_path)
        self.assertEqual(owner._project_boundary_times, [])
        self.assertTrue(owner._is_auto_pipeline)
        self.assertEqual(signal.emitted, [[]])
        self.assertEqual(owner._multiclip_files, [])

    def test_attach_project_session_sets_project_path_and_boundary_rows(self):
        signal = _Signal()
        owner = SimpleNamespace(
            _current_project_path=None,
            _project_boundary_times=[],
            _is_auto_pipeline=True,
            _multiclip_files=["stale.mp4"],
            _multiclip_boundaries=[{"end": 3.0}],
            _accumulated_vad=[{"start": 0.0}],
            _reuse_existing_multiclip_subtitles=True,
            _sig_update_project_boundary_times=signal,
        )
        project = {
            "analysis": {
                "cut_boundaries": [
                    {"time": 1.5, "verified": True},
                    {"time": 3.0, "verified": True},
                ]
            }
        }
        result = attach_project_session(
            owner,
            "/tmp/project.json",
            project,
            auto_pipeline=False,
            clear_multiclip=True,
        )
        self.assertEqual(owner._current_project_path, "/tmp/project.json")
        self.assertFalse(owner._is_auto_pipeline)
        self.assertEqual(result, owner._project_boundary_times)
        self.assertEqual(signal.emitted, [owner._project_boundary_times])
        self.assertEqual(owner._multiclip_files, [])

    def test_set_project_boundary_rows_updates_runtime_and_emits_signal(self):
        signal = _Signal()
        owner = SimpleNamespace(
            _project_boundary_times=[9.0],
            _sig_update_project_boundary_times=signal,
        )
        result = set_project_boundary_rows(owner, [1.0, 2.0])
        self.assertEqual(result, [1.0, 2.0])
        self.assertEqual(owner._project_boundary_times, [1.0, 2.0])
        self.assertEqual(signal.emitted, [[1.0, 2.0]])

    def test_apply_project_multiclip_runtime_tracks_media_and_clip_boundaries(self):
        owner = SimpleNamespace(
            _multiclip_files=[],
            _multiclip_boundaries=[],
        )
        project = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "source_path": "/tmp/a.mp4",
                                "order": 0,
                                "timeline_start": 0.0,
                                "timeline_end": 5.0,
                            },
                            {
                                "source_path": "/tmp/b.mp4",
                                "order": 1,
                                "timeline_start": 5.0,
                                "timeline_end": 8.0,
                            },
                        ]
                    }
                ]
            }
        }
        boundaries = apply_project_multiclip_runtime(owner, ["/tmp/a.mp4", "/tmp/b.mp4"], project)
        self.assertEqual(owner._multiclip_files, ["/tmp/a.mp4", "/tmp/b.mp4"])
        self.assertEqual(owner._multiclip_boundaries, boundaries)
        self.assertEqual(boundaries[1]["end"], 8.0)

        apply_project_multiclip_runtime(owner, ["/tmp/a.mp4"], project)
        self.assertEqual(owner._multiclip_files, [])
        self.assertEqual(owner._multiclip_boundaries, [])

    def test_set_runtime_multiclip_state_clears_single_clip_and_updates_boundaries(self):
        signal = _Signal()
        owner = SimpleNamespace(
            _multiclip_files=[],
            _multiclip_boundaries=[],
            _project_boundary_times=[9.0],
            _sig_update_project_boundary_times=signal,
        )
        set_runtime_multiclip_state(
            owner,
            ["/tmp/a.mp4", "/tmp/b.mp4"],
            [{"start": 0.0, "end": 2.0, "file": "/tmp/a.mp4"}],
            project_boundary_rows=[],
        )
        self.assertEqual(owner._multiclip_files, ["/tmp/a.mp4", "/tmp/b.mp4"])
        self.assertEqual(owner._multiclip_boundaries, [{"start": 0.0, "end": 2.0, "file": "/tmp/a.mp4"}])
        self.assertEqual(owner._project_boundary_times, [])
        self.assertEqual(signal.emitted[-1], [])

        set_runtime_multiclip_state(owner, ["/tmp/a.mp4"], owner._multiclip_boundaries, project_boundary_rows=[])
        self.assertEqual(owner._multiclip_files, [])
        self.assertEqual(owner._multiclip_boundaries, [])

    def test_local_project_settings_use_project_data_manager_when_available(self):
        fake_settings = {"mode": "high"}
        with mock.patch("core.project.data_manager.load_settings", return_value=fake_settings):
            self.assertEqual(load_local_project_settings(), fake_settings)
        with mock.patch("core.project.data_manager.save_settings") as save_project_settings:
            save_local_project_settings(fake_settings)
            save_project_settings.assert_called_once_with(fake_settings)

    def test_sorted_project_media_paths_prefers_existing_editor_media_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first = os.path.join(tmpdir, "a.mp4")
            second = os.path.join(tmpdir, "b.mp4")
            third = os.path.join(tmpdir, "c.mp4")
            for path in (first, second, third):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("x")
            project = {
                "editor_state": {"media_files": [second, first, "/missing/file.mp4"]},
                "media": [
                    {"path": third, "order": 0},
                ],
            }
            self.assertEqual(sorted_project_media_paths(project), [second, first])


if __name__ == "__main__":
    unittest.main()
