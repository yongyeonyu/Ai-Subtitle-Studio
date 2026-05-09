import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.runtime.memory_manager import (
    RuntimeMemoryManager,
    prune_runtime_disk_caches,
    runtime_disk_cache_usage,
)


class RuntimeMemoryManagerTests(unittest.TestCase):
    def test_manager_keeps_tracemalloc_off_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = RuntimeMemoryManager(
                settings={},
                diagnostics_dir=tmp,
                cache_paths=[],
            )

        self.assertFalse(manager._trace_enabled)

    def test_runtime_disk_cache_usage_and_prune(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_a = root / "cache_a"
            cache_b = root / "cache_b"
            cache_a.mkdir()
            cache_b.mkdir()
            files = [
                cache_a / "old.bin",
                cache_a / "mid.bin",
                cache_b / "new.bin",
            ]
            sizes = [200, 300, 400]
            for idx, (path, size) in enumerate(zip(files, sizes, strict=True)):
                path.write_bytes(b"x" * size)
                os.utime(path, (100 + idx, 100 + idx))

            usage = runtime_disk_cache_usage([cache_a, cache_b])
            self.assertEqual(usage["file_count"], 3)
            self.assertEqual(usage["total_bytes"], sum(sizes))

            result = prune_runtime_disk_caches(paths=[cache_a, cache_b], target_total_bytes=450)
            self.assertGreaterEqual(result["removed_files"], 1)
            self.assertLessEqual(result["remaining_bytes"], 450)

    def test_manager_poll_triggers_trim_callback_on_critical_pressure(self):
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 1 * 1024 ** 3,
            "available_memory_ratio": 0.06,
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "cpu_load_ratio": 0.25,
        }
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.memory_manager.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.memory_manager.process_rss_bytes", return_value=14 * 1024 ** 3):
                manager = RuntimeMemoryManager(
                    settings={
                        "runtime_memory_tracemalloc_enabled": False,
                        "macos_memory_trim_runtime_caches_enabled": False,
                    },
                    diagnostics_dir=tmp,
                    cache_paths=[],
                )
                manager.register_trim_callback("test", lambda stage, payload: events.append((stage, payload["pressure_stage"])))
                result = manager.poll()

            self.assertEqual(result["pressure_stage"], "critical")
            self.assertEqual(events, [("critical", "critical")])
            self.assertTrue((Path(tmp) / "latest.json").exists())

    def test_manager_poll_stays_idle_when_memory_is_healthy(self):
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 10 * 1024 ** 3,
            "available_memory_ratio": 0.62,
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "cpu_load_ratio": 0.12,
        }
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.memory_manager.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.memory_manager.process_rss_bytes", return_value=2 * 1024 ** 3):
                manager = RuntimeMemoryManager(
                    settings={"runtime_memory_tracemalloc_enabled": False},
                    diagnostics_dir=tmp,
                    cache_paths=[],
                )
                manager.register_trim_callback("test", lambda stage, payload: events.append(stage))
                result = manager.poll()

            self.assertEqual(result["pressure_stage"], "normal")
            self.assertEqual(events, [])

    def test_manager_prefers_native_pressure_stage_and_rss(self):
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 10 * 1024 ** 3,
            "available_memory_ratio": 0.62,
            "memory_pressure_stage": "warning",
            "process_rss_bytes": 3 * 1024 ** 3,
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "cpu_load_ratio": 0.12,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.memory_manager.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.memory_manager.process_rss_bytes", return_value=9 * 1024 ** 3):
                manager = RuntimeMemoryManager(
                    settings={
                        "runtime_memory_tracemalloc_enabled": False,
                        "macos_memory_trim_runtime_caches_enabled": False,
                    },
                    diagnostics_dir=tmp,
                    cache_paths=[],
                )
                result = manager.poll()

            self.assertEqual(result["pressure_stage"], "warning")
            self.assertEqual(result["rss_bytes"], 3 * 1024 ** 3)


if __name__ == "__main__":
    unittest.main()
