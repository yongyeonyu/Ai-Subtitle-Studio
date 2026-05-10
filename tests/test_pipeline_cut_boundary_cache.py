# Version: 03.12.00
# Phase: PHASE2
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

import core.cut_boundary as cut_boundary
from core.pipeline.pipeline_helpers import PipelineHelpersMixin


class _DummyUi:
    def __init__(self, project_path: str):
        self._current_project_path = project_path


class _DummyBackend(PipelineHelpersMixin):
    def __init__(self, project_path: str):
        self.ui = _DummyUi(project_path)
        self._cut_boundary_provisional_rows = []
        self._cut_boundary_pipeline_cache = None
        self.emitted = []

    def _ui_emit(self, name, *args):
        self.emitted.append((name, args))


class PipelineCutBoundaryCacheTests(unittest.TestCase):
    def _write_project(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "analysis": {
                        "cut_boundaries": [{"timeline_sec": 10.0, "time": 10.0}],
                        "cut_boundary_provisional_boundaries": [{"timeline_sec": 9.5, "time": 9.5}],
                    }
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def test_cut_boundary_snapshot_is_shared_between_calls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "sample.project.json")
            self._write_project(project_path)
            backend = _DummyBackend(project_path)

            with mock.patch(
                "core.cut_boundary.project_cut_boundaries",
                wraps=cut_boundary.project_cut_boundaries,
            ) as cut_mock, mock.patch(
                "core.cut_boundary.project_cut_provisional_boundaries",
                wraps=cut_boundary.project_cut_provisional_boundaries,
            ) as provisional_mock:
                cuts = backend._project_cut_boundaries_for_pipeline()
                provisional = backend._project_provisional_cut_boundaries_for_pipeline()

            self.assertEqual(len(cuts), 1)
            self.assertEqual(len(provisional), 1)
            self.assertEqual(cut_mock.call_count, 1)
            self.assertEqual(provisional_mock.call_count, 1)

    def test_follower_marks_then_removes_checked_provisional_rows(self):
        backend = _DummyBackend("")
        provisional_rows = [
            {"timeline_sec": 10.0, "time": 10.0, "clip_idx": 0, "status": "provisional"},
            {"timeline_sec": 20.0, "time": 20.0, "clip_idx": 0, "status": "provisional"},
            {
                "timeline_sec": 10.02,
                "time": 10.02,
                "clip_idx": 0,
                "status": "provisional",
                "follower_relocated": True,
            },
        ]

        marked = backend._mark_cut_boundary_rows_following(
            provisional_rows,
            [{"timeline_sec": 10.0, "time": 10.0, "clip_idx": 0}],
        )

        self.assertTrue(marked)
        self.assertEqual(provisional_rows[0]["status"], "verifying")
        self.assertEqual(provisional_rows[0]["detector_stage"], "follower")
        self.assertEqual(provisional_rows[0]["line_color"], "#FFCC00")

        removed = backend._remove_cut_boundary_checked_rows(
            provisional_rows,
            [{"timeline_sec": 10.0, "time": 10.0, "clip_idx": 0}],
        )

        self.assertTrue(removed)
        self.assertEqual([round(row["timeline_sec"], 2) for row in provisional_rows], [20.0, 10.02])

    def test_split_by_saved_cut_boundaries_offset_skips_pre_offset_boundaries(self):
        backend = _DummyBackend("")
        backend._cut_boundary_pipeline_cache = {
            "project_path": "",
            "mtime_ns": None,
            "provisional_signature": "[]",
            "cut_boundaries": [
                {"timeline_sec": 5.0, "time": 5.0},
                {"timeline_sec": 12.0, "time": 12.0},
            ],
            "provisional_cut_boundaries": [],
        }

        seen_boundaries = []

        def fake_split(segments, boundaries, enabled=True):
            seen_boundaries.extend(boundaries)
            return [dict(seg) for seg in segments]

        with mock.patch("core.pipeline.pipeline_helpers.load_settings", return_value={"cut_boundary_detection_enabled": True}), \
             mock.patch("core.cut_boundary.cut_boundary_enabled", return_value=True), \
             mock.patch("core.cut_boundary.split_segments_by_cut_boundaries", side_effect=fake_split):
            backend._split_by_saved_cut_boundaries(
                [{"start": 0.0, "end": 4.0, "text": "hello"}],
                offset=10.0,
                context="test",
            )

        self.assertEqual(len(seen_boundaries), 1)
        self.assertAlmostEqual(float(seen_boundaries[0]["timeline_sec"]), 2.0, places=3)

    def test_completed_follower_clears_saved_provisional_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "sample.project.json")
            confirmed = [{"timeline_sec": 10.0, "time": 10.0, "timeline_frame": 300, "fps": 30.0}]
            provisional = [{"timeline_sec": 9.5, "time": 9.5, "timeline_frame": 285, "fps": 30.0, "status": "provisional"}]
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "analysis": {
                            "cut_boundaries": list(confirmed),
                            "cut_boundary_provisional_boundaries": list(provisional),
                        },
                        "editor_state": {
                            "analysis": {
                                "cut_boundaries": list(confirmed),
                                "cut_boundary_provisional_boundaries": list(provisional),
                            },
                            "multiclip": {
                                "cut_boundaries": list(confirmed),
                                "cut_boundary_provisional_boundaries": list(provisional),
                            },
                        },
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            backend = _DummyBackend(project_path)
            backend._cut_boundary_provisional_rows = list(provisional)
            backend._cut_boundary_pipeline_cache = {
                "project_path": project_path,
                "provisional_cut_boundaries": list(provisional),
            }

            backend._clear_completed_cut_boundary_provisionals(
                project_path,
                settings={"cut_boundary_detection_enabled": True},
                detected=confirmed,
            )

            self.assertEqual(backend._cut_boundary_provisional_rows, [])
            self.assertIsNone(backend._cut_boundary_pipeline_cache)
            self.assertIn(("_sig_preview_cut_boundary_scan_lines", ([],)), backend.emitted)
            with open(project_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["analysis"]["cut_boundary_provisional_boundaries"], [])
            self.assertEqual(saved["editor_state"]["analysis"]["cut_boundary_provisional_boundaries"], [])
            self.assertEqual(saved["editor_state"]["multiclip"]["cut_boundary_provisional_boundaries"], [])
            self.assertEqual(len(saved["analysis"]["cut_boundaries"]), 1)
            self.assertAlmostEqual(float(saved["analysis"]["cut_boundaries"][0]["timeline_sec"]), 10.0, places=3)

    def test_cut_boundary_follower_starts_streaming_before_all_pioneers_finish(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "sample.project.json")
            file_one = os.path.join(tmpdir, "clip1.mp4")
            file_two = os.path.join(tmpdir, "clip2.mp4")
            for path in (file_one, file_two):
                with open(path, "wb") as f:
                    f.write(b"media")
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump({"analysis": {}}, f)

            backend = _DummyBackend(project_path)
            backend._load_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._save_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._clear_completed_cut_boundary_provisionals = lambda *_args, **_kwargs: None
            backend._force_cut_boundary_topicless_segments_to_project = lambda *_args, **_kwargs: None
            backend._emit_cut_boundary_count_to_sidebar = lambda *_args, **_kwargs: None

            verify_started = threading.Event()
            second_scan_saw_follower = []
            verify_calls = []

            def fake_scan(path, **kwargs):
                clip_idx = int(kwargs.get("clip_idx", 0) or 0)
                if clip_idx == 1:
                    second_scan_saw_follower.append(verify_started.wait(timeout=1.0))
                row = {
                    "timeline_sec": 10.0 + clip_idx,
                    "time": 10.0 + clip_idx,
                    "clip_local_sec": 10.0,
                    "clip_idx": clip_idx,
                    "source": "unit_pioneer",
                    "refine_pending": True,
                }
                found_callback = kwargs.get("found_callback")
                if callable(found_callback):
                    found_callback(dict(row), [dict(row)])
                completion_callback = kwargs.get("completion_callback")
                if callable(completion_callback):
                    completion_callback({"clip_idx": clip_idx, "worker_total": 1, "worker_completed": 1, "done": True})
                return [row]

            def fake_verify(path, rows, **kwargs):
                verify_started.set()
                verify_calls.append((path, list(rows or [])))
                found_callback = kwargs.get("found_callback")
                if callable(found_callback):
                    for row in rows or []:
                        fixed = dict(row)
                        fixed["status"] = "verified"
                        fixed["verified"] = True
                        found_callback(fixed, [fixed])
                return list(rows or [])

            with mock.patch("core.pipeline.cut_boundary_helpers.load_settings", return_value={"cut_boundary_detection_enabled": True}), \
                 mock.patch("core.cut_boundary.cut_boundary_enabled", return_value=True), \
                 mock.patch("core.cut_boundary.cut_boundary_scan_profile", return_value={"positions": (0, 2, 4, 6, 8), "mask": "x5", "sample_step_sec": 1.0}), \
                 mock.patch("core.cut_boundary.scan_media_cut_boundary_provisionals", side_effect=fake_scan), \
                 mock.patch("core.cut_boundary.verify_media_cut_boundary_rows", side_effect=fake_verify), \
                 mock.patch("core.cut_boundary.sync_project_cut_boundaries", lambda *_args, **_kwargs: None):
                backend._auto_scan_cut_boundaries_for_start_sync(project_path, [file_one, file_two])

            follower = getattr(backend, "_cut_boundary_follower_thread", None)
            self.assertIsNotNone(follower)
            follower.join(timeout=2.0)

            self.assertFalse(follower.is_alive())
            self.assertTrue(second_scan_saw_follower)
            self.assertTrue(second_scan_saw_follower[0])
            self.assertGreaterEqual(len(verify_calls), 2)
            self.assertEqual(verify_calls[0][0], file_one)
            self.assertTrue(backend._cut_boundary_prescan_completed)

    def test_cut_boundary_follower_streams_single_clip_before_pioneer_returns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "sample.project.json")
            media_path = os.path.join(tmpdir, "clip.mp4")
            with open(media_path, "wb") as f:
                f.write(b"media")
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump({"analysis": {}}, f)

            backend = _DummyBackend(project_path)
            backend._load_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._save_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._clear_completed_cut_boundary_provisionals = lambda *_args, **_kwargs: None
            backend._force_cut_boundary_topicless_segments_to_project = lambda *_args, **_kwargs: None
            backend._emit_cut_boundary_count_to_sidebar = lambda *_args, **_kwargs: None

            verify_started = threading.Event()
            verify_calls = []
            scan_saw_follower_before_return = []

            def fake_scan(path, **kwargs):
                progress_callback = kwargs.get("progress_callback")
                if callable(progress_callback):
                    progress_callback({
                        "clip_idx": 0,
                        "percent": 25,
                        "worker_idx": 0,
                        "worker_total": 1,
                        "worker_percent": 25,
                        "timestamp": 10.0,
                        "duration": 80.0,
                        "provisional_detected": 1,
                    })
                row = {
                    "timeline_sec": 12.0,
                    "time": 12.0,
                    "clip_local_sec": 12.0,
                    "clip_idx": 0,
                    "source": "unit_pioneer",
                    "refine_pending": True,
                }
                found_callback = kwargs.get("found_callback")
                if callable(found_callback):
                    found_callback(dict(row), [dict(row)])
                scan_saw_follower_before_return.append(verify_started.wait(timeout=1.0))
                completion_callback = kwargs.get("completion_callback")
                if callable(completion_callback):
                    completion_callback({"clip_idx": 0, "worker_total": 1, "worker_completed": 1, "done": True})
                return [row]

            def fake_verify(path, rows, **kwargs):
                verify_started.set()
                verify_calls.append((path, list(rows or []), kwargs))
                found_callback = kwargs.get("found_callback")
                if callable(found_callback):
                    for row in rows or []:
                        fixed = dict(row)
                        fixed["status"] = "verified"
                        fixed["verified"] = True
                        found_callback(fixed, [fixed])
                return list(rows or [])

            settings = {
                "cut_boundary_detection_enabled": True,
                "scan_cut_follower_stream_start_percent": 25,
                "scan_cut_follower_stream_batch_size": 4,
                "scan_cut_follower_stream_min_interval_sec": 0.0,
            }
            with mock.patch("core.pipeline.cut_boundary_helpers.load_settings", return_value=settings), \
                 mock.patch("core.cut_boundary.cut_boundary_enabled", return_value=True), \
                 mock.patch("core.cut_boundary.cut_boundary_scan_profile", return_value={"positions": (0, 2, 4, 6, 8), "mask": "x5", "sample_step_sec": 1.0}), \
                 mock.patch("core.cut_boundary.scan_media_cut_boundary_provisionals", side_effect=fake_scan), \
                 mock.patch("core.cut_boundary.verify_media_cut_boundary_rows", side_effect=fake_verify), \
                 mock.patch("core.cut_boundary.sync_project_cut_boundaries", lambda *_args, **_kwargs: None):
                backend._auto_scan_cut_boundaries_for_start_sync(project_path, [media_path])

            follower = getattr(backend, "_cut_boundary_follower_thread", None)
            self.assertIsNotNone(follower)
            follower.join(timeout=2.0)

            self.assertFalse(follower.is_alive())
            self.assertTrue(scan_saw_follower_before_return)
            self.assertTrue(scan_saw_follower_before_return[0])
            self.assertEqual(len(verify_calls), 1)
            self.assertEqual(verify_calls[0][0], media_path)
            self.assertEqual(verify_calls[0][1][0]["candidate_key"], "0:12.000")

    def test_long_4k_cut_boundary_delays_follower_until_pioneer_finishes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "sample.project.json")
            media_path = os.path.join(tmpdir, "long_4k.mp4")
            with open(media_path, "wb") as f:
                f.write(b"media")
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump({"analysis": {}}, f)

            backend = _DummyBackend(project_path)
            backend._cut_boundary_placeholder_duration = lambda _files: 1450.0
            backend._load_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._save_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._clear_completed_cut_boundary_provisionals = lambda *_args, **_kwargs: None
            backend._force_cut_boundary_topicless_segments_to_project = lambda *_args, **_kwargs: None
            backend._emit_cut_boundary_count_to_sidebar = lambda *_args, **_kwargs: None

            verify_started = threading.Event()
            scan_saw_follower_before_return = []
            verify_calls = []
            scan_runtime = []

            def fake_scan(path, **kwargs):
                scan_runtime.append({
                    "sample_step_sec": float(kwargs.get("sample_step_sec", 0.0) or 0.0),
                    "sequential_decode": bool(
                        dict(kwargs.get("settings") or {}).get("scan_cut_pioneer_sequential_decode_enabled")
                    ),
                    "cv2_backend": str(dict(kwargs.get("settings") or {}).get("scan_cut_cv2_video_backend") or ""),
                    "backend_policy": str(dict(kwargs.get("settings") or {}).get("cut_boundary_backend_policy") or ""),
                })
                progress_callback = kwargs.get("progress_callback")
                if callable(progress_callback):
                    progress_callback({
                        "clip_idx": 0,
                        "percent": 50,
                        "worker_idx": 0,
                        "worker_total": 4,
                        "worker_percent": 50,
                        "timestamp": 720.0,
                        "duration": 1450.0,
                        "provisional_detected": 1,
                    })
                row = {
                    "timeline_sec": 720.0,
                    "time": 720.0,
                    "clip_local_sec": 720.0,
                    "clip_idx": 0,
                    "source": "unit_pioneer",
                    "refine_pending": True,
                }
                found_callback = kwargs.get("found_callback")
                if callable(found_callback):
                    found_callback(dict(row), [dict(row)])
                scan_saw_follower_before_return.append(verify_started.wait(timeout=0.2))
                completion_callback = kwargs.get("completion_callback")
                if callable(completion_callback):
                    completion_callback({"clip_idx": 0, "worker_total": 4, "worker_completed": 4, "done": True})
                return [row]

            def fake_verify(path, rows, **kwargs):
                verify_started.set()
                verify_calls.append((path, list(rows or []), kwargs))
                found_callback = kwargs.get("found_callback")
                if callable(found_callback):
                    for row in rows or []:
                        fixed = dict(row)
                        fixed["status"] = "verified"
                        fixed["verified"] = True
                        found_callback(fixed, [fixed])
                return list(rows or [])

            settings = {
                "cut_boundary_detection_enabled": True,
                "scan_cut_long4k_min_duration_sec": 600,
                "scan_cut_follower_stream_start_percent": 25,
                "scan_cut_follower_stream_min_interval_sec": 0.0,
            }
            with mock.patch("core.pipeline.cut_boundary_helpers.load_settings", return_value=settings), \
                 mock.patch("core.media_info.probe_media", return_value={"duration": 1450.0, "width": 3840, "height": 2160, "fps": 59.94}), \
                 mock.patch("core.cut_boundary.cut_boundary_enabled", return_value=True), \
                 mock.patch("core.cut_boundary.cut_boundary_scan_profile", return_value={"positions": (0, 2, 4, 6, 8), "mask": "x5", "sample_step_sec": 1.0}), \
                 mock.patch("core.cut_boundary.scan_media_cut_boundary_provisionals", side_effect=fake_scan), \
                 mock.patch("core.cut_boundary.verify_media_cut_boundary_rows", side_effect=fake_verify), \
                 mock.patch("core.cut_boundary.sync_project_cut_boundaries", lambda *_args, **_kwargs: None):
                backend._auto_scan_cut_boundaries_for_start_sync(project_path, [media_path])

            follower = getattr(backend, "_cut_boundary_follower_thread", None)
            self.assertIsNotNone(follower)
            follower.join(timeout=2.0)

            self.assertFalse(follower.is_alive())
            self.assertTrue(scan_saw_follower_before_return)
            self.assertFalse(scan_saw_follower_before_return[0])
            self.assertEqual(len(verify_calls), 1)
            self.assertEqual(len(scan_runtime), 1)
            self.assertEqual(scan_runtime[0]["sample_step_sec"], 1.0)
            self.assertFalse(scan_runtime[0]["sequential_decode"])
            self.assertEqual(scan_runtime[0]["cv2_backend"], "avfoundation")
            self.assertEqual(scan_runtime[0]["backend_policy"], "fast")
            verify_settings = dict(verify_calls[0][2].get("settings") or {})
            self.assertTrue(verify_settings.get("scan_cut_follower_deferred_until_pioneer_done"))
            self.assertEqual(int(verify_settings.get("scan_cut_follower_stream_start_percent", 0)), 100)
            self.assertGreaterEqual(int(verify_settings.get("scan_cut_follower_stream_batch_size", 0)), 16)

    def test_long_4k_deferred_follower_is_micro_batched_for_visible_progress(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "sample.project.json")
            media_path = os.path.join(tmpdir, "long_4k.mp4")
            with open(media_path, "wb") as f:
                f.write(b"media")
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump({"analysis": {}}, f)

            backend = _DummyBackend(project_path)
            backend._cut_boundary_placeholder_duration = lambda _files: 1450.0
            backend._load_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._save_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._clear_completed_cut_boundary_provisionals = lambda *_args, **_kwargs: None
            backend._force_cut_boundary_topicless_segments_to_project = lambda *_args, **_kwargs: None
            backend._emit_cut_boundary_count_to_sidebar = lambda *_args, **_kwargs: None

            verify_batch_sizes = []

            def fake_scan(path, **kwargs):
                rows = []
                found_callback = kwargs.get("found_callback")
                for idx in range(40):
                    sec = 20.0 + idx * 10.0
                    row = {
                        "timeline_sec": sec,
                        "time": sec,
                        "clip_local_sec": sec,
                        "clip_idx": 0,
                        "source": "unit_pioneer",
                        "refine_pending": True,
                    }
                    rows.append(row)
                    if callable(found_callback):
                        found_callback(dict(row), list(rows))
                completion_callback = kwargs.get("completion_callback")
                if callable(completion_callback):
                    completion_callback({"clip_idx": 0, "worker_total": 4, "worker_completed": 4, "done": True})
                return rows

            def fake_verify(path, rows, **kwargs):
                verify_batch_sizes.append(len(list(rows or [])))
                found_callback = kwargs.get("found_callback")
                verified = []
                for row in rows or []:
                    fixed = dict(row)
                    fixed["status"] = "verified"
                    fixed["verified"] = True
                    verified.append(fixed)
                    if callable(found_callback):
                        found_callback(dict(fixed), list(verified))
                return verified

            settings = {
                "cut_boundary_detection_enabled": True,
                "scan_cut_long4k_min_duration_sec": 600,
                "scan_cut_follower_verify_micro_batch_size": 999,
                "scan_cut_follower_verify_micro_batch_max": 16,
                "scan_cut_long4k_follower_stream_batch_size": 16,
            }
            with mock.patch("core.pipeline.cut_boundary_helpers.load_settings", return_value=settings), \
                 mock.patch("core.media_info.probe_media", return_value={"duration": 1450.0, "width": 3840, "height": 2160, "fps": 59.94}), \
                 mock.patch("core.cut_boundary.cut_boundary_enabled", return_value=True), \
                 mock.patch("core.cut_boundary.cut_boundary_scan_profile", return_value={"positions": (0, 2, 4, 6, 8), "mask": "x5", "sample_step_sec": 1.0}), \
                 mock.patch("core.cut_boundary.scan_media_cut_boundary_provisionals", side_effect=fake_scan), \
                 mock.patch("core.cut_boundary.verify_media_cut_boundary_rows", side_effect=fake_verify), \
                 mock.patch("core.cut_boundary.sync_project_cut_boundaries", lambda *_args, **_kwargs: None):
                backend._auto_scan_cut_boundaries_for_start_sync(project_path, [media_path])

            follower = getattr(backend, "_cut_boundary_follower_thread", None)
            self.assertIsNotNone(follower)
            follower.join(timeout=2.0)

            self.assertFalse(follower.is_alive())
            self.assertGreaterEqual(len(verify_batch_sizes), 3)
            self.assertLessEqual(max(verify_batch_sizes), 16)
            self.assertEqual(sum(verify_batch_sizes), 40)
            self.assertTrue(
                any(name == "_sig_preview_cut_boundary_scan_lines" and args and args[0] for name, args in backend.emitted)
            )

    def test_pioneer_uses_low_profile_while_follower_keeps_resolved_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "sample.project.json")
            media_path = os.path.join(tmpdir, "clip.mp4")
            with open(media_path, "wb") as f:
                f.write(b"media")
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump({"analysis": {}}, f)

            backend = _DummyBackend(project_path)
            backend._load_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._save_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._clear_completed_cut_boundary_provisionals = lambda *_args, **_kwargs: None
            backend._force_cut_boundary_topicless_segments_to_project = lambda *_args, **_kwargs: None
            backend._emit_cut_boundary_count_to_sidebar = lambda *_args, **_kwargs: None

            scan_levels = []
            scan_setting_levels = []
            scan_fast_runtime = []
            verify_levels = []
            verify_setting_levels = []
            verify_fast_runtime = []

            def fake_profile(settings):
                level = str(settings.get("scan_cut_boundary_level") or "medium")
                if level == "low":
                    return {
                        "level": "low",
                        "resolved_level": "low",
                        "positions": (1, 3, 7, 10, 12, 14, 17, 21, 23),
                        "mask": "custom9",
                        "sample_step_sec": 1.0,
                    }
                return {
                    "level": "medium",
                    "resolved_level": "medium",
                    "positions": (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24),
                    "mask": "custom13",
                    "sample_step_sec": 1.0,
                }

            def fake_scan(path, **kwargs):
                profile = dict(kwargs.get("scan_profile") or {})
                settings = dict(kwargs.get("settings") or {})
                scan_levels.append(str(profile.get("level") or ""))
                scan_setting_levels.append(str(settings.get("scan_cut_boundary_level") or ""))
                scan_fast_runtime.append({
                    "pioneer_workers": int(settings.get("scan_cut_pioneer_workers", 0) or 0),
                    "verify_workers": int(settings.get("scan_cut_verify_workers", 0) or 0),
                    "ffmpeg_scene_prepass": bool(settings.get("scan_cut_ffmpeg_scene_prepass_enabled")),
                    "ffmpeg_scene_replace": bool(settings.get("scan_cut_ffmpeg_scene_replace_opencv_enabled")),
                    "backend_policy": str(settings.get("cut_boundary_backend_policy") or ""),
                    "cv2_backend": str(settings.get("scan_cut_cv2_video_backend") or ""),
                    "sequential_decode": bool(settings.get("scan_cut_pioneer_sequential_decode_enabled")),
                    "sample_step_sec": float(kwargs.get("sample_step_sec", 0.0) or 0.0),
                })
                row = {
                    "timeline_sec": 10.0,
                    "time": 10.0,
                    "clip_local_sec": 10.0,
                    "clip_idx": 0,
                    "source": "unit_pioneer",
                    "refine_pending": True,
                }
                completion_callback = kwargs.get("completion_callback")
                if callable(completion_callback):
                    completion_callback({"clip_idx": 0, "worker_total": 1, "worker_completed": 1, "done": True})
                return [row]

            def fake_verify(path, rows, **kwargs):
                profile = dict(kwargs.get("scan_profile") or {})
                settings = dict(kwargs.get("settings") or {})
                verify_levels.append(str(profile.get("level") or ""))
                verify_setting_levels.append(str(settings.get("scan_cut_boundary_level") or ""))
                verify_fast_runtime.append({
                    "verify_workers": int(settings.get("scan_cut_verify_workers", 0) or 0),
                    "outer_splits": int(settings.get("scan_cut_follower_outer_splits", 0) or 0),
                    "stream_batch": int(settings.get("scan_cut_follower_stream_batch_size", 0) or 0),
                    "stream_start": int(settings.get("scan_cut_follower_stream_start_percent", 0) or 0),
                })
                return list(rows or [])

            settings = {
                "autopilot_enabled": False,
                "cut_boundary_detection_enabled": True,
                "scan_cut_boundary_level": "medium",
                "cut_boundary_level": "medium",
                "scan_cut_level": "medium",
            }
            with mock.patch("core.pipeline.cut_boundary_helpers.load_settings", return_value=settings), \
                 mock.patch("core.cut_boundary.cut_boundary_enabled", return_value=True), \
                 mock.patch("core.cut_boundary.cut_boundary_scan_profile", side_effect=fake_profile), \
                 mock.patch("core.cut_boundary.scan_media_cut_boundary_provisionals", side_effect=fake_scan), \
                 mock.patch("core.cut_boundary.verify_media_cut_boundary_rows", side_effect=fake_verify), \
                 mock.patch("core.cut_boundary.sync_project_cut_boundaries", lambda *_args, **_kwargs: None):
                backend._auto_scan_cut_boundaries_for_start_sync(project_path, [media_path])

            follower = getattr(backend, "_cut_boundary_follower_thread", None)
            self.assertIsNotNone(follower)
            follower.join(timeout=2.0)

            self.assertEqual(scan_levels, ["low"])
            self.assertEqual(scan_setting_levels, ["low"])
            self.assertEqual(scan_fast_runtime, [{
                "pioneer_workers": 4,
                "verify_workers": 4,
                "ffmpeg_scene_prepass": False,
                "ffmpeg_scene_replace": False,
                "backend_policy": "fast",
                "cv2_backend": "avfoundation",
                "sequential_decode": False,
                "sample_step_sec": 1.0,
            }])
            self.assertEqual(verify_levels, ["medium"])
            self.assertEqual(verify_setting_levels, ["medium"])
            self.assertEqual(verify_fast_runtime, [{
                "verify_workers": 4,
                "outer_splits": 4,
                "stream_batch": 4,
                "stream_start": 25,
            }])

    def test_cut_boundary_pioneer_progress_never_exceeds_100_without_final_worker_total(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "sample.project.json")
            media_path = os.path.join(tmpdir, "clip.mp4")
            with open(media_path, "wb") as f:
                f.write(b"media")
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump({"analysis": {}}, f)

            backend = _DummyBackend(project_path)
            backend._load_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._save_cut_boundary_cache_for_start = lambda *_args, **_kwargs: None
            backend._clear_completed_cut_boundary_provisionals = lambda *_args, **_kwargs: None
            backend._force_cut_boundary_topicless_segments_to_project = lambda *_args, **_kwargs: None
            sidebar_percents = []

            def capture_sidebar(_count, **kwargs):
                if "percent" in kwargs:
                    sidebar_percents.append(int(kwargs["percent"]))

            backend._emit_cut_boundary_count_to_sidebar = capture_sidebar

            def fake_scan(path, **kwargs):
                progress_callback = kwargs.get("progress_callback")
                if callable(progress_callback):
                    for worker_idx in range(10):
                        progress_callback({
                            "clip_idx": 0,
                            "percent": 100,
                            "worker_idx": worker_idx,
                            "worker_total": 10,
                            "worker_percent": 100,
                            "timestamp": 80.0,
                            "duration": 80.0,
                            "provisional_detected": 0,
                        })
                    progress_callback({
                        "clip_idx": 0,
                        "percent": 100,
                        "worker_idx": 0,
                        "timestamp": 80.0,
                        "duration": 80.0,
                        "detected": 0,
                    })
                completion_callback = kwargs.get("completion_callback")
                if callable(completion_callback):
                    completion_callback({"clip_idx": 0, "worker_total": 10, "worker_completed": 10, "done": True})
                return []

            with mock.patch("core.pipeline.cut_boundary_helpers.load_settings", return_value={"cut_boundary_detection_enabled": True}), \
                 mock.patch("core.cut_boundary.cut_boundary_enabled", return_value=True), \
                 mock.patch("core.cut_boundary.cut_boundary_scan_profile", return_value={"positions": (0, 2, 4, 6, 8), "mask": "x5", "sample_step_sec": 1.0}), \
                 mock.patch("core.cut_boundary.scan_media_cut_boundary_provisionals", side_effect=fake_scan), \
                 mock.patch("core.cut_boundary.verify_media_cut_boundary_rows", return_value=[]), \
                 mock.patch("core.cut_boundary.sync_project_cut_boundaries", lambda *_args, **_kwargs: None):
                backend._auto_scan_cut_boundaries_for_start_sync(project_path, [media_path])

            follower = getattr(backend, "_cut_boundary_follower_thread", None)
            if follower is not None:
                follower.join(timeout=2.0)

            self.assertTrue(sidebar_percents)
            self.assertLessEqual(max(sidebar_percents), 100)


if __name__ == "__main__":
    unittest.main()
