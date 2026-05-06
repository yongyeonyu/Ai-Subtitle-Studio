# Version: 03.01.37
# Phase: PHASE2
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import media_info
from core.performance import (
    adaptive_llm_worker_count,
    adaptive_worker_count,
    bounded_worker_count,
    ffprobe_worker_count,
    mark_runtime_scheduler_start,
)


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

    def test_probe_media_many_preserves_order(self):
        with patch("core.media_info.probe_media", side_effect=lambda path: {"duration": float(path[-1])}):
            result = media_info.probe_media_many(["clip1", "clip2", "clip3"], max_workers=3)

        self.assertEqual([item["duration"] for item in result], [1.0, 2.0, 3.0])

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


if __name__ == "__main__":
    unittest.main()
