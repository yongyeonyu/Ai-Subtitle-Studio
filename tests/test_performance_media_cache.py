# Version: 03.01.37
# Phase: PHASE2
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import media_info
from core.performance import (
    adaptive_llm_worker_count,
    adaptive_worker_count,
    apple_silicon_runtime_profile,
    balanced_task_slices,
    bounded_worker_count,
    distributed_worker_ceiling,
    ffprobe_worker_count,
    mark_runtime_scheduler_start,
    native_runtime_env_overrides,
    native_thread_budget,
    runtime_scheduler_reserve_cores,
)
from core.native_json import dumps_json_text, loads_json, loads_json_output, write_jsonl_line


class PerformanceMediaCacheTest(unittest.TestCase):
    def setUp(self):
        media_info.clear_media_probe_cache_memory()

    def tearDown(self):
        media_info.clear_media_probe_cache_memory()
        mark_runtime_scheduler_start({"runtime_scheduler_ramp_up_enabled": False})

    def test_probe_media_reuses_memory_and_disk_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "sample.mp4"
            media.write_bytes(b"media")
            cache_dir = Path(tmp) / "cache"
            payload = {
                "format": {"duration": "12.5"},
                "streams": [{"width": 1920, "height": 1080, "r_frame_rate": "30000/1001"}],
            }

            with patch("core.media_info.media_probe_cache_dir", return_value=cache_dir), \
                 patch("core.media_info.ffprobe_binary", return_value="ffprobe"), \
                 patch("core.media_info.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(payload))) as run_mock:
                first = media_info.probe_media(str(media))
                second = media_info.probe_media(str(media))

            self.assertEqual(first["duration"], 12.5)
            self.assertEqual(first["width"], 1920)
            self.assertEqual(second, first)
            self.assertEqual(run_mock.call_count, 1)

            media_info.clear_media_probe_cache_memory()
            with patch("core.media_info.media_probe_cache_dir", return_value=cache_dir), \
                 patch("core.media_info.subprocess.run") as run_mock:
                third = media_info.probe_media(str(media))

            self.assertEqual(third, first)
            run_mock.assert_not_called()

    def test_probe_media_cache_returns_independent_dicts_after_caller_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "sample.mp4"
            media.write_bytes(b"media")
            cache_dir = Path(tmp) / "cache"
            payload = {
                "format": {"duration": "12.5"},
                "streams": [{"width": 1920, "height": 1080, "r_frame_rate": "30000/1001"}],
            }

            with patch("core.media_info.media_probe_cache_dir", return_value=cache_dir), \
                 patch("core.media_info.ffprobe_binary", return_value="ffprobe"), \
                 patch("core.media_info.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(payload))):
                first = media_info.probe_media(str(media))
                first["duration"] = 99.0
                second = media_info.probe_media(str(media))

            self.assertEqual(second["duration"], 12.5)

    def test_probe_media_disk_cache_rehydrate_returns_independent_dicts_after_caller_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "sample.mp4"
            media.write_bytes(b"media")
            cache_dir = Path(tmp) / "cache"
            payload = {
                "format": {"duration": "12.5"},
                "streams": [{"width": 1920, "height": 1080, "r_frame_rate": "30000/1001"}],
            }

            with patch("core.media_info.media_probe_cache_dir", return_value=cache_dir), \
                 patch("core.media_info.ffprobe_binary", return_value="ffprobe"), \
                 patch("core.media_info.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(payload))):
                media_info.probe_media(str(media))

            media_info.clear_media_probe_cache_memory()
            with patch("core.media_info.media_probe_cache_dir", return_value=cache_dir), \
                 patch("core.media_info.subprocess.run") as run_mock:
                first = media_info.probe_media(str(media))
                first["duration"] = 99.0
                second = media_info.probe_media(str(media))

            run_mock.assert_not_called()
            self.assertEqual(second["duration"], 12.5)

    def test_probe_media_ignores_malformed_disk_cache_payload_and_reprobes(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "sample.mp4"
            media.write_bytes(b"media")
            cache_dir = Path(tmp) / "cache"
            payload = {
                "format": {"duration": "12.5"},
                "streams": [{"width": 1920, "height": 1080, "r_frame_rate": "30000/1001"}],
            }

            with patch("core.media_info.media_probe_cache_dir", return_value=cache_dir), \
                 patch("core.media_info.ffprobe_binary", return_value="ffprobe"), \
                 patch("core.media_info.read_json_path", return_value=["broken-cache"]), \
                 patch("core.media_info.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(payload))) as run_mock:
                result = media_info.probe_media(str(media))

            self.assertEqual(result["duration"], 12.5)
            self.assertEqual(result["width"], 1920)
            self.assertEqual(run_mock.call_count, 1)

    def test_probe_media_many_preserves_order(self):
        with patch("core.media_info.probe_media", side_effect=lambda path: {"duration": float(path[-1])}):
            result = media_info.probe_media_many(["clip1", "clip2", "clip3"], max_workers=3)

        self.assertEqual([item["duration"] for item in result], [1.0, 2.0, 3.0])

    def test_probe_media_many_lookup_deduplicates_paths_and_returns_unique_map(self):
        with patch(
            "core.media_info.probe_media",
            side_effect=lambda path: {"path": path, "duration": float(path[-1])},
        ) as probe_mock:
            result = media_info.probe_media_many_lookup(["clip2", "clip1", "clip2"], max_workers=4)

        self.assertEqual(probe_mock.call_count, 2)
        self.assertEqual(list(result), ["clip2", "clip1"])
        self.assertEqual(result["clip1"]["duration"], 1.0)
        self.assertEqual(result["clip2"]["duration"], 2.0)

    def test_probe_media_many_deduplicates_duplicate_paths_but_returns_independent_dicts(self):
        with patch(
            "core.media_info.probe_media",
            side_effect=lambda path: {"path": path, "duration": float(path[-1])},
        ) as probe_mock:
            result = media_info.probe_media_many(["clip1", "clip1", "clip2", "clip1"], max_workers=4)

        self.assertEqual(probe_mock.call_count, 2)
        self.assertEqual([item["path"] for item in result], ["clip1", "clip1", "clip2", "clip1"])
        self.assertIsNot(result[0], result[1])
        result[0]["duration"] = 99.0
        self.assertEqual(result[1]["duration"], 1.0)

    def test_probe_media_many_keeps_single_use_rows_without_extra_copy(self):
        probe_results = {
            "clip1": {"path": "clip1", "duration": 1.0},
            "clip2": {"path": "clip2", "duration": 2.0},
        }
        with patch(
            "core.media_info.probe_media",
            side_effect=lambda path: probe_results[path],
        ):
            result = media_info.probe_media_many(["clip1", "clip1", "clip2"], max_workers=4)

        self.assertIsNot(result[0], probe_results["clip1"])
        self.assertIsNot(result[1], probe_results["clip1"])
        self.assertIs(result[2], probe_results["clip2"])

    def test_probe_media_audio_only_payload_keeps_audio_defaults(self):
        payload = {
            "format": {"duration": "61.2"},
            "streams": [],
        }
        with patch("core.media_info.ffprobe_binary", return_value="ffprobe"), \
             patch("core.media_info.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(payload))):
            result = media_info.probe_media("sample.wav", use_cache=False)

        self.assertEqual(result["duration"], 61.2)
        self.assertEqual(result["info_txt"], "오디오 파일")
        self.assertEqual(result["len_txt"], "01:01")

    def test_probe_media_uses_stream_duration_when_format_duration_is_missing(self):
        payload = {
            "format": {},
            "streams": [{"duration": "8.4", "width": 1280, "height": 720, "r_frame_rate": "24000/1001"}],
        }
        with patch("core.media_info.ffprobe_binary", return_value="ffprobe"), \
             patch("core.media_info.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(payload))):
            result = media_info.probe_media("sample.mp4", use_cache=False)

        self.assertEqual(result["duration"], 8.4)
        self.assertEqual(result["width"], 1280)
        self.assertEqual(result["height"], 720)
        self.assertAlmostEqual(result["fps"], 23.976023976, places=6)
        self.assertEqual(result["len_txt"], "00:08")

    def test_probe_media_memory_cache_is_bounded(self):
        original_max = media_info._MEDIA_PROBE_MEM_CACHE_MAX
        try:
            media_info._MEDIA_PROBE_MEM_CACHE_MAX = 3
            with tempfile.TemporaryDirectory() as tmp:
                cache_dir = Path(tmp) / "cache"
                payload = {
                    "format": {"duration": "1.0"},
                    "streams": [{"width": 320, "height": 180, "r_frame_rate": "30/1"}],
                }
                with patch("core.media_info.media_probe_cache_dir", return_value=cache_dir), \
                     patch("core.media_info.ffprobe_binary", return_value="ffprobe"), \
                     patch("core.media_info.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(payload))):
                    for idx in range(5):
                        media = Path(tmp) / f"sample_{idx}.mp4"
                        media.write_bytes(f"media-{idx}".encode("utf-8"))
                        media_info.probe_media(str(media))
            self.assertLessEqual(len(media_info._MEM_CACHE), 3)
        finally:
            media_info._MEDIA_PROBE_MEM_CACHE_MAX = original_max

    def test_worker_bounds_are_conservative(self):
        self.assertGreaterEqual(bounded_worker_count(kind="io"), 1)
        self.assertLessEqual(ffprobe_worker_count(99), 8)
        self.assertEqual(ffprobe_worker_count(0), 1)

    def test_adaptive_llm_workers_keep_api_single_and_local_bounded(self):
        api_workers, api_meta = adaptive_llm_worker_count(
            settings={"llm_threads_auto_enabled": True},
            workload=50,
            provider="openai",
            model="gpt-test",
            task="subtitle",
        )
        local_workers, local_meta = adaptive_llm_worker_count(
            settings={"llm_threads_auto_enabled": True, "llm_threads_resource_max": 3},
            workload=50,
            provider="ollama",
            model="exaone3.5:7.8b",
            task="subtitle",
        )

        self.assertEqual(api_workers, 1)
        self.assertEqual(api_meta["reason"], "api_single_worker")
        self.assertGreaterEqual(local_workers, 1)
        self.assertLessEqual(local_workers, 3)
        self.assertEqual(local_meta["reason"], "resource_adaptive")

    def test_runtime_scheduler_reduces_workers_for_user_active_battery_pressure(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 3 * 1024 ** 3,
            "available_memory_ratio": 0.18,
            "cpu_load_1m": 6.8,
            "cpu_load_ratio": 0.85,
            "on_battery": True,
            "battery_percent": 42,
            "user_idle_seconds": 1.2,
            "user_active": True,
        }
        with patch("core.performance.hardware_profile", return_value=snapshot), \
             patch("core.performance.current_resource_snapshot", return_value=snapshot):
            workers, meta = adaptive_worker_count(
                task="cut_pioneer",
                settings={"runtime_scheduler_auto_enabled": True},
                requested=4,
                workload=20,
                minimum=1,
                maximum=4,
            )

        self.assertEqual(workers, 1)
        self.assertEqual(meta["reason"], "resource_adaptive")
        self.assertIn("battery_power", meta["reductions"])
        self.assertIn("user_active", meta["reductions"])
        self.assertIn("high_cpu_load", meta["reductions"])

    def test_runtime_scheduler_preserves_manual_compat_when_auto_disabled(self):
        snapshot = {
            "system": "Darwin",
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 12 * 1024 ** 3,
            "available_memory_ratio": 0.75,
            "cpu_load_ratio": 0.1,
            "on_battery": False,
            "user_active": False,
        }
        with patch("core.performance.hardware_profile", return_value=snapshot), \
             patch("core.performance.current_resource_snapshot", return_value=snapshot):
            workers, meta = adaptive_worker_count(
                task="stt",
                settings={"stt_workers_auto_enabled": False},
                requested=2,
                workload=2,
                minimum=1,
                maximum=2,
            )

        self.assertEqual(workers, 2)
        self.assertFalse(meta["auto_enabled"])
        self.assertEqual(meta["reason"], "manual_compat")

    def test_runtime_scheduler_ramp_up_starts_with_one_worker(self):
        snapshot = {
            "system": "Darwin",
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 12 * 1024 ** 3,
            "available_memory_ratio": 0.75,
            "cpu_load_ratio": 0.1,
            "on_battery": False,
            "user_active": False,
        }
        settings = {
            "runtime_scheduler_auto_enabled": True,
            "runtime_scheduler_ramp_up_enabled": True,
            "runtime_scheduler_ramp_initial_sec": 60.0,
            "runtime_scheduler_ramp_step_sec": 60.0,
        }
        with patch("core.performance.hardware_profile", return_value=snapshot), \
             patch("core.performance.current_resource_snapshot", return_value=snapshot):
            mark_runtime_scheduler_start(settings)
            workers, meta = adaptive_worker_count(
                task="cut_pioneer",
                settings=settings,
                requested=4,
                workload=20,
                minimum=1,
                maximum=4,
            )

        self.assertEqual(workers, 1)
        self.assertEqual(meta["ramp"]["phase"], "warmup")
        self.assertIn("ramp_up_warmup", meta["reductions"])

    def test_hardware_max_profile_uses_full_cpu_budget_without_user_active_reduction(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 3 * 1024 ** 3,
            "available_memory_ratio": 0.18,
            "cpu_load_1m": 8.5,
            "cpu_load_ratio": 0.85,
            "on_battery": True,
            "battery_percent": 42,
            "user_idle_seconds": 1.2,
            "user_active": True,
        }
        settings = {
            "runtime_scheduler_auto_enabled": True,
            "runtime_hardware_acceleration_enabled": True,
            "runtime_performance_profile": "max",
        }
        with patch("core.performance.hardware_profile", return_value=snapshot), \
             patch("core.performance.current_resource_snapshot", return_value=snapshot):
            workers, meta = adaptive_worker_count(
                task="cut_pioneer",
                settings=settings,
                requested=4,
                workload=20,
                minimum=1,
                maximum=4,
            )

        self.assertEqual(workers, 4)
        self.assertEqual(meta["profile"], "max")
        self.assertNotIn("battery_power", meta["reductions"])
        self.assertNotIn("user_active", meta["reductions"])
        self.assertEqual(meta["ramp"]["reason"], "hardware_max_profile")

    def test_hardware_max_profile_backs_off_under_extreme_cpu_load(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 10 * 1024 ** 3,
            "available_memory_ratio": 0.62,
            "cpu_load_1m": 32.0,
            "cpu_load_ratio": 3.2,
            "on_battery": False,
            "battery_percent": 80,
            "user_idle_seconds": 120.0,
            "user_active": False,
        }
        settings = {
            "runtime_scheduler_auto_enabled": True,
            "runtime_hardware_acceleration_enabled": True,
            "runtime_performance_profile": "max",
        }
        with patch("core.performance.hardware_profile", return_value=snapshot), \
             patch("core.performance.current_resource_snapshot", return_value=snapshot):
            workers, meta = adaptive_worker_count(
                task="cut_follower",
                settings=settings,
                requested=4,
                workload=20,
                minimum=1,
                maximum=8,
            )

        self.assertEqual(workers, 4)
        self.assertIn("extreme_cpu_load", meta["reductions"])

    def test_native_runtime_env_budget_keeps_one_core_for_interaction_in_max_profile(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "memory_bytes": 16 * 1024 ** 3,
            "accelerators": {"mlx": True},
        }
        settings = {
            "runtime_hardware_acceleration_enabled": True,
            "runtime_performance_profile": "max",
            "runtime_native_threads_auto_enabled": True,
        }
        with patch("core.performance.hardware_profile", return_value=snapshot):
            self.assertEqual(native_thread_budget(settings), 9)
            env = native_runtime_env_overrides(settings)

        self.assertEqual(env["AI_SUBTITLE_NATIVE_THREADS"], "9")
        self.assertEqual(env["OMP_NUM_THREADS"], "9")
        self.assertEqual(env["AI_SUBTITLE_NATIVE_JSON"], "1")
        self.assertEqual(env["AI_SUBTITLE_NATIVE_TEXT_SIMILARITY"], "1")
        self.assertEqual(env["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"], "1")
        self.assertEqual(env["AI_SUBTITLE_OLLAMA_PY_CLIENT"], "1")

    def test_apple_silicon_runtime_profile_detects_m5_allocation(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "chip_name": "Apple M5",
            "chip_generation": 5,
            "chip_tier": "base",
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "gpu_cores": 10,
            "neural_engine_cores": 16,
            "memory_bytes": 16 * 1024 ** 3,
            "accelerators": {"metal_gpu": True, "neural_engine_path": True},
        }

        profile = apple_silicon_runtime_profile(
            {"runtime_performance_profile": "max", "runtime_hardware_acceleration_enabled": True},
            profile=snapshot,
        )

        self.assertEqual(profile["chip_name"], "Apple M5")
        self.assertEqual(profile["interactive_reserve_cores"], 1)
        self.assertEqual(profile["cpu"]["native_threads"], 9)
        self.assertEqual(profile["cpu"]["wide_workers"], 9)
        self.assertEqual(profile["cpu"]["balanced_workers"], 7)
        self.assertEqual(profile["gpu"]["stt_slots"], 1)
        self.assertEqual(profile["npu"]["coreml_slots"], 1)
        self.assertEqual(profile["pipeline"]["cut_follower_stream_start_percent"], 25)

    def test_distributed_worker_ceiling_keeps_one_core_for_ui_in_max_profile(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "logical_cores": 10,
            "physical_cores": 8,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "memory_bytes": 16 * 1024 ** 3,
            "accelerators": {"mlx": True},
        }
        settings = {
            "runtime_hardware_acceleration_enabled": True,
            "runtime_performance_profile": "max",
        }
        with patch("core.performance.hardware_profile", return_value=snapshot):
            ceiling = distributed_worker_ceiling(
                settings,
                task="cut_pioneer",
                workload=32,
                reserve_cores=1,
            )

        self.assertEqual(ceiling, 9)

    def test_runtime_scheduler_reserve_cores_keeps_one_core_for_interaction_in_max_profile(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "logical_cores": 10,
            "physical_cores": 8,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "memory_bytes": 16 * 1024 ** 3,
            "accelerators": {"mlx": True},
        }
        settings = {
            "runtime_hardware_acceleration_enabled": True,
            "runtime_performance_profile": "max",
            "runtime_scheduler_reserve_cores": 1,
        }
        with patch("core.performance.hardware_profile", return_value=snapshot):
            self.assertEqual(runtime_scheduler_reserve_cores(settings, task="cut_pioneer"), 1)
            self.assertEqual(runtime_scheduler_reserve_cores(settings, task="stt"), 1)
            self.assertEqual(runtime_scheduler_reserve_cores(settings, task="subtitle_prepass"), 1)

    def test_runtime_scheduler_reserve_cores_keeps_one_core_for_manual_lora(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "logical_cores": 10,
            "physical_cores": 8,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "memory_bytes": 16 * 1024 ** 3,
            "accelerators": {"mlx": True},
        }
        settings = {
            "runtime_hardware_acceleration_enabled": True,
            "runtime_performance_profile": "max",
            "runtime_scheduler_reserve_cores": 0,
        }
        with patch("core.performance.hardware_profile", return_value=snapshot):
            self.assertEqual(runtime_scheduler_reserve_cores(settings, task="manual_lora"), 1)

    def test_runtime_scheduler_reserve_cores_drops_to_zero_on_exit(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "memory_bytes": 16 * 1024 ** 3,
        }
        settings = {"runtime_scheduler_reserve_cores": 2}
        with patch("core.performance.hardware_profile", return_value=snapshot):
            self.assertEqual(runtime_scheduler_reserve_cores(settings, task="cpu", exiting=True), 0)

    def test_balanced_task_slices_split_evenly_without_tiny_batches(self):
        self.assertEqual(
            balanced_task_slices(11, 4, min_batch_size=2),
            [(0, 3), (3, 6), (6, 9), (9, 11)],
        )
        self.assertEqual(
            balanced_task_slices(3, 8, min_batch_size=2),
            [(0, 3)],
        )

    def test_native_json_round_trip_preserves_unicode(self):
        payload = {"text": "안녕하세요", "rows": [{"i": 1}]}
        encoded = dumps_json_text(payload, indent=2, append_newline=True)
        self.assertTrue(encoded.endswith("\n"))
        self.assertEqual(loads_json(encoded), payload)

    def test_native_json_output_helper_uses_default_for_empty_output(self):
        self.assertEqual(loads_json_output("", default={"ok": False}), {"ok": False})
        self.assertEqual(loads_json_output(b"", default=[]), [])

    def test_native_json_write_jsonl_line_appends_single_newline(self):
        stream = StringIO()
        write_jsonl_line(stream, "{\"ok\":true}")
        self.assertEqual(stream.getvalue(), "{\"ok\":true}\n")


if __name__ == "__main__":
    unittest.main()
