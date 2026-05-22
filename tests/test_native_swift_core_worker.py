from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import core.native_swift_subtitle as native_subtitle
from core.native_swift_project import read_project_via_swift, write_project_via_swift
from core.native_swift_subtitle import (
    find_native_cli_path,
    native_swift_runtime_enabled,
    parse_srt_via_swift,
    request_native_core_task,
    stop_native_core_worker,
)


class NativeSwiftCoreWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        stop_native_core_worker()

    def tearDown(self) -> None:
        stop_native_core_worker()

    def test_swift_runtime_defaults_on_for_macos_and_keeps_disable_switch(self):
        native_subtitle._native_swift_runtime_enabled_cached.cache_clear()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("core.native_swift_subtitle.sys.platform", "darwin"):
            self.assertTrue(native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_PROJECT_IO"))

        with mock.patch.dict(os.environ, {"AI_SUBTITLE_STUDIO_SWIFT_CORE": "0"}, clear=True), mock.patch(
            "core.native_swift_subtitle.sys.platform",
            "darwin",
        ):
            self.assertFalse(native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_PROJECT_IO"))

        with mock.patch.dict(os.environ, {"AI_SUBTITLE_STUDIO_SWIFT_TIMELINE": "0"}, clear=True), mock.patch(
            "core.native_swift_subtitle.sys.platform",
            "darwin",
        ):
            self.assertFalse(native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_TIMELINE"))

    def test_swift_runtime_enabled_reuses_cached_env_decision(self):
        native_subtitle._native_swift_runtime_enabled_cached.cache_clear()
        with mock.patch.dict(os.environ, {"AI_SUBTITLE_STUDIO_SWIFT_CORE": "1"}, clear=True), \
             mock.patch("core.native_swift_subtitle.sys.platform", "darwin"):
            self.assertTrue(native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_PROJECT_IO"))
            with mock.patch(
                "core.native_swift_subtitle._env_state_value",
                side_effect=AssertionError("runtime env state should be cached"),
            ):
                self.assertTrue(native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_PROJECT_IO"))
        native_subtitle._native_swift_runtime_enabled_cached.cache_clear()

    def test_core_worker_reuses_single_swift_process_across_srt_and_project_tasks(self):
        if find_native_cli_path() is None:
            self.skipTest("AIStudioNativeCLI release build is not available")

        with tempfile.TemporaryDirectory() as tmp:
            srt_path = Path(tmp) / "sample.srt"
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,200\n안녕하세요\n\n"
                "2\n00:00:01,500 --> 00:00:02,700\n반갑습니다\n",
                encoding="utf-8",
            )
            project_path = Path(tmp) / "project.json"
            project_payload = {
                "project_name": "worker-test",
                "analysis": {
                    "stt_candidate_tracks": {
                        "STT1": [{"start": 0.0, "end": 1.0, "text": "안녕하세요"}],
                    }
                },
                "_project_file_path": str(project_path),
            }

            env = {
                "AI_SUBTITLE_STUDIO_SWIFT_CORE": "1",
                "AI_SUBTITLE_STUDIO_SWIFT_PROJECT_IO": "1",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                first_segments = parse_srt_via_swift(str(srt_path))
                first_worker = native_subtitle._CORE_WORKER
                second_segments = parse_srt_via_swift(str(srt_path))
                second_worker = native_subtitle._CORE_WORKER
                wrote = write_project_via_swift(str(project_path), project_payload)
                loaded = read_project_via_swift(str(project_path))
                final_worker = native_subtitle._CORE_WORKER

            self.assertIsNotNone(first_worker)
            self.assertIs(first_worker, second_worker)
            self.assertIs(first_worker, final_worker)
            self.assertIsNone(final_worker.poll())
            self.assertEqual(first_segments, second_segments)
            self.assertEqual(len(first_segments or []), 2)
            self.assertTrue(wrote)
            self.assertIsInstance(loaded, dict)
            self.assertEqual(loaded["project_name"], "worker-test")
            self.assertNotIn("_project_file_path", loaded)

    def test_core_worker_skips_cli_path_lookup_after_worker_is_running(self):
        if find_native_cli_path() is None:
            self.skipTest("AIStudioNativeCLI release build is not available")

        env = {"AI_SUBTITLE_STUDIO_SWIFT_CORE": "1"}
        with mock.patch.dict(os.environ, env, clear=False):
            first = request_native_core_task("pipeline_status_summary", {"status_text": "⏳ [STT] 진행 중"})
            self.assertIsInstance(first, dict)
            with mock.patch(
                "core.native_swift_subtitle.find_native_cli_path",
                side_effect=AssertionError("running worker should be reused without path lookup"),
            ):
                second = request_native_core_task("pipeline_status_summary", {"status_text": "⏳ [VAD] 검사 중"})

        self.assertIsInstance(second, dict)
        self.assertEqual(second.get("keys"), ["vad"])

    def test_find_native_cli_path_reuses_cached_hit_for_same_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(tmp) / "AIStudioNativeCLI"
            cli.write_text("#!/bin/sh\n", encoding="utf-8")
            cli.chmod(0o755)
            native_subtitle._CLI_PATH_CACHE_ENV = None
            native_subtitle._CLI_PATH_CACHE = None
            native_subtitle._CLI_PATH_CACHE_AT = 0.0

            with mock.patch.dict(os.environ, {"AI_SUBTITLE_STUDIO_NATIVE_CLI": str(cli)}, clear=True):
                first = find_native_cli_path()
                with mock.patch(
                    "core.native_swift_subtitle._candidate_cli_paths",
                    side_effect=AssertionError("cached CLI path should be reused"),
                ):
                    second = find_native_cli_path()

        self.assertEqual(first, cli)
        self.assertEqual(second, cli)

    def test_find_native_cli_path_skips_recent_hit_stat_for_same_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(tmp) / "AIStudioNativeCLI"
            cli.write_text("#!/bin/sh\n", encoding="utf-8")
            cli.chmod(0o755)
            native_subtitle._CLI_PATH_CACHE_ENV = None
            native_subtitle._CLI_PATH_CACHE = None
            native_subtitle._CLI_PATH_CACHE_AT = 0.0

            with mock.patch.dict(os.environ, {"AI_SUBTITLE_STUDIO_NATIVE_CLI": str(cli)}, clear=True), \
                 mock.patch("core.native_swift_subtitle.time.time", return_value=100.0):
                first = find_native_cli_path()

            with mock.patch.dict(os.environ, {"AI_SUBTITLE_STUDIO_NATIVE_CLI": str(cli)}, clear=True), \
                 mock.patch("core.native_swift_subtitle.time.time", return_value=101.0), \
                 mock.patch("pathlib.Path.exists", side_effect=AssertionError("recent CLI hit should not stat")):
                second = find_native_cli_path()

        self.assertEqual(first, cli)
        self.assertEqual(second, cli)

    def test_find_native_cli_path_reuses_short_lived_miss_for_same_env(self):
        native_subtitle._CLI_PATH_CACHE_ENV = None
        native_subtitle._CLI_PATH_CACHE = None
        native_subtitle._CLI_PATH_CACHE_AT = 0.0

        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("core.native_swift_subtitle._candidate_cli_paths", return_value=[]), \
             mock.patch("core.native_swift_subtitle.time.time", return_value=100.0):
            self.assertIsNone(find_native_cli_path())

        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch(
                 "core.native_swift_subtitle._candidate_cli_paths",
                 side_effect=AssertionError("recent CLI miss should be cached briefly"),
             ), \
             mock.patch("core.native_swift_subtitle.time.time", return_value=101.0):
            self.assertIsNone(find_native_cli_path())

        native_subtitle._CLI_PATH_CACHE_ENV = None
        native_subtitle._CLI_PATH_CACHE = None
        native_subtitle._CLI_PATH_CACHE_AT = 0.0

    def test_find_native_cli_path_picks_newest_built_cli_without_explicit_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "release" / "AIStudioNativeCLI"
            debug = Path(tmp) / "debug" / "AIStudioNativeCLI"
            release.parent.mkdir(parents=True)
            debug.parent.mkdir(parents=True)
            release.write_text("#!/bin/sh\n", encoding="utf-8")
            debug.write_text("#!/bin/sh\n", encoding="utf-8")
            release.chmod(0o755)
            debug.chmod(0o755)
            os.utime(release, (100.0, 100.0))
            os.utime(debug, (200.0, 200.0))
            native_subtitle._CLI_PATH_CACHE_ENV = None
            native_subtitle._CLI_PATH_CACHE = None
            native_subtitle._CLI_PATH_CACHE_AT = 0.0

            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch("core.native_swift_subtitle._candidate_cli_paths", return_value=[release, debug]):
                self.assertEqual(find_native_cli_path(), debug)

    def test_core_worker_handles_runtime_eta_roundtrip(self):
        if find_native_cli_path() is None:
            self.skipTest("AIStudioNativeCLI release build is not available")

        with tempfile.TemporaryDirectory() as tmp:
            store_path = str(Path(tmp) / "time_history.json")
            payload = {
                "store_path": store_path,
                "model_key": "QUALITY:STT:test|LLM:codex|DIA:X",
                "variant": {
                    "mode": "precise",
                    "stt_quality_preset": "precise",
                    "stt_primary": "mlx-community/whisper-large-v3-mlx",
                    "stt_secondary": "",
                    "stt_ensemble_enabled": False,
                    "llm_provider": "openai",
                    "llm_model": "OpenAI Codex ChatGPT [구독/CLI/API키 불필요]",
                    "diarization_enabled": False,
                    "max_speakers": 1,
                    "selected_vad": "silero",
                    "selected_audio_ai": "deepfilter",
                },
                "media": {
                    "duration_sec": 300.0,
                    "fps": 29.97,
                    "width": 1920,
                    "height": 1080,
                    "pixel_count": 1920 * 1080,
                    "audio_quality_score": 84.0,
                    "cut_density_per_min": 1.2,
                    "speaker_hint": 1,
                    "is_audio_only": False,
                },
                "runtime": {
                    "queue_index": 0,
                    "total_files": 1,
                    "prefetch_audio_hit": False,
                    "cut_boundary_cache_enabled": True,
                    "vad_cache_enabled": True,
                    "stt_runtime_reuse_enabled": True,
                    "prefetch_ahead": 0,
                    "auto_audio_tune_enabled": True,
                    "cache_state": "cold",
                    "cut_boundary_cache_state": "cold",
                    "vad_cache_state": "cold",
                    "speaker_cache_state": "disabled",
                    "likely_warm_start": False,
                    "cache_score": 0.45,
                },
                "processing_time_sec": 135.0,
            }

            env = {"AI_SUBTITLE_STUDIO_SWIFT_CORE": "1"}
            with mock.patch.dict(os.environ, env, clear=False):
                record = request_native_core_task("runtime_eta_record", payload)
                predict = request_native_core_task("runtime_eta_predict", payload)

            self.assertIsInstance(record, dict)
            self.assertTrue(record.get("ok"))
            self.assertIsInstance(predict, dict)
            self.assertGreater(float(predict.get("predicted_processing_sec", 0.0) or 0.0), 0.0)

    def test_core_worker_handles_startup_diagnostic_and_cut_cache_roundtrip(self):
        if find_native_cli_path() is None:
            self.skipTest("AIStudioNativeCLI release build is not available")

        env = {"AI_SUBTITLE_STUDIO_SWIFT_CORE": "1"}
        with mock.patch.dict(os.environ, env, clear=False):
            diagnostic = request_native_core_task(
                "startup_diagnostic_build",
                {
                    "media_path": "/tmp/source/clip.mp4",
                    "media_name": "clip.mp4",
                    "media": {
                        "duration_sec": 1450.249,
                        "fps": 59.94,
                        "width": 3840,
                        "height": 2160,
                        "info_txt": "3840x2160 (59.94fps)",
                    },
                    "audio": {
                        "has_audio": True,
                        "codec": "aac",
                        "sample_rate": 48000,
                        "channels": 2,
                        "bit_rate": 160000,
                        "duration_sec": 1450.249,
                    },
                    "settings": {"max_speakers": 2},
                    "cut_boundaries": [{"timeline_sec": 120.0}, {"timeline_sec": 300.0}],
                    "provisional_cut_boundaries": [{"timeline_sec": 180.0}],
                    "expected_time_sec": 321.0,
                },
            )
            cache_plan = request_native_core_task(
                "cut_boundary_cache_plan",
                {
                    "files": [
                        {
                            "path": "/tmp/demo.mp4",
                            "size": 123,
                            "mtime_ns": 456,
                            "fingerprint_digest": "abc",
                        }
                    ],
                    "settings": {"scan_cut_compare_max_width": 1280, "scan_cut_compare_max_height": 720},
                    "cache_root": "/tmp/cache",
                    "version": 7,
                    "cut_boundary_api_version": "v1",
                    "cut_boundary_algorithm_version": "v2",
                    "cut_boundary_algorithm_id": "algo",
                },
            )

        self.assertIsInstance(diagnostic, dict)
        self.assertEqual(diagnostic["recommended_pipeline"]["mode"], "precise")
        self.assertEqual(diagnostic["estimated_processing_label"], "5분 21초")
        self.assertIsInstance(cache_plan, dict)
        self.assertIn("cache_path", cache_plan)


if __name__ == "__main__":
    unittest.main()
