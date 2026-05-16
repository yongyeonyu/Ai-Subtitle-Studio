import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import core.runtime.memory_manager as memory_manager
from core.runtime.memory_manager import (
    RuntimeMemoryManager,
    SubtitleGenerationMemoryGuard,
    default_runtime_disk_cache_paths,
    prune_runtime_disk_caches,
    register_runtime_cache_path,
    runtime_disk_cache_usage,
    unregister_runtime_cache_path,
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

    def test_runtime_disk_cache_usage_reuses_recent_scan_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_a = root / "cache_a"
            cache_a.mkdir()
            (cache_a / "sample.bin").write_bytes(b"x" * 128)

            first = runtime_disk_cache_usage([cache_a])

            with patch("pathlib.Path.rglob", side_effect=AssertionError("recent disk usage should be served from cache")):
                second = runtime_disk_cache_usage([cache_a])

            self.assertEqual(first["total_bytes"], second["total_bytes"])
            self.assertEqual(first["file_count"], second["file_count"])

    def test_runtime_disk_cache_usage_uses_root_index_after_registered_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_a = root / "cache_a"
            cache_a.mkdir()
            first = cache_a / "first.bin"
            first.write_bytes(b"x" * 128)
            usage = runtime_disk_cache_usage([cache_a])
            self.assertEqual(usage["total_bytes"], 128)

            second = cache_a / "second.bin"
            second.write_bytes(b"y" * 256)
            register_runtime_cache_path(second, root=cache_a)

            with patch("os.scandir", side_effect=AssertionError("registered writes should update the root index without rescanning")):
                updated = runtime_disk_cache_usage([cache_a])

            self.assertEqual(updated["file_count"], 2)
            self.assertEqual(updated["total_bytes"], 384)

    def test_register_runtime_cache_path_reuses_cached_entries_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager._RUNTIME_DISK_ROOT_INDEX.clear()
            cache_root = Path(tmp) / "cache_a"
            cache_root.mkdir()
            sample = cache_root / "sample.bin"
            sample.write_bytes(b"x" * 128)
            entries: dict[str, tuple[float, int]] = {}
            root_key = memory_manager._runtime_disk_root_key(cache_root)
            memory_manager._RUNTIME_DISK_ROOT_INDEX[root_key] = {
                "root": str(cache_root),
                "exists": True,
                "bytes": 0,
                "files": 0,
                "entries": entries,
                "is_file": False,
                "scanned_at": time.time(),
            }

            register_runtime_cache_path(sample, root=cache_root)

            updated = memory_manager._RUNTIME_DISK_ROOT_INDEX[root_key]
            self.assertIs(updated["entries"], entries)
            self.assertIn(str(sample), entries)

    def test_unregister_runtime_cache_path_reuses_cached_entries_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager._RUNTIME_DISK_ROOT_INDEX.clear()
            cache_root = Path(tmp) / "cache_a"
            cache_root.mkdir()
            sample = cache_root / "sample.bin"
            sample.write_bytes(b"x" * 128)
            stat = sample.stat()
            entries: dict[str, tuple[float, int]] = {
                str(sample): (float(stat.st_mtime or 0.0), 128),
            }
            root_key = memory_manager._runtime_disk_root_key(cache_root)
            memory_manager._RUNTIME_DISK_ROOT_INDEX[root_key] = {
                "root": str(cache_root),
                "exists": True,
                "bytes": 128,
                "files": 1,
                "entries": entries,
                "is_file": False,
                "scanned_at": time.time(),
            }

            unregister_runtime_cache_path(sample, root=cache_root, size_bytes=128)

            updated = memory_manager._RUNTIME_DISK_ROOT_INDEX[root_key]
            self.assertIs(updated["entries"], entries)
            self.assertNotIn(str(sample), entries)

    def test_prune_runtime_disk_caches_uses_streaming_scandir_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_a = root / "cache_a"
            nested = cache_a / "nested"
            nested.mkdir(parents=True)
            old_file = cache_a / "old.bin"
            new_file = nested / "new.bin"
            old_file.write_bytes(b"x" * 300)
            new_file.write_bytes(b"x" * 300)
            os.utime(old_file, (100, 100))
            os.utime(new_file, (200, 200))

            with patch("pathlib.Path.rglob", side_effect=AssertionError("prune should not materialize rglob results")):
                result = prune_runtime_disk_caches(paths=[cache_a], target_total_bytes=350)

            self.assertEqual(result["removed_files"], 1)
            self.assertFalse(old_file.exists())
            self.assertTrue(new_file.exists())

    def test_prune_runtime_disk_caches_skips_sort_when_under_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_a = Path(tmp) / "cache_a"
            cache_a.mkdir()
            (cache_a / "sample.bin").write_bytes(b"x" * 128)

            with patch("builtins.sorted", side_effect=AssertionError("under-budget prune should not sort candidates")):
                result = prune_runtime_disk_caches(paths=[cache_a], target_total_bytes=1024)

            self.assertEqual(result["removed_files"], 0)
            self.assertEqual(result["remaining_bytes"], 128)

    def test_default_runtime_disk_cache_paths_include_preview_cache_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.memory_manager.config.DATASET_DIR", tmp):
                paths = [str(path) for path in default_runtime_disk_cache_paths()]

        self.assertIn(str(Path(tmp) / "video_preview_cache"), paths)

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

    def test_subtitle_generation_guard_writes_stage_snapshot_and_cleans(self):
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 1 * 1024 ** 3,
            "available_memory_ratio": 0.06,
            "memory_pressure_stage": "critical",
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "cpu_load_ratio": 0.12,
        }
        callbacks = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.memory_manager.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.memory_manager.process_rss_bytes", return_value=8 * 1024 ** 3), \
                 patch("core.runtime.memory_manager.trim_runtime_memory_caches", return_value={"actions": ["trim"]}) as trim:
                guard = SubtitleGenerationMemoryGuard(
                    settings={
                        "runtime_memory_tracemalloc_enabled": False,
                        "subtitle_generation_memory_checkpoint_interval_ms": 0,
                    },
                    diagnostics_dir=tmp,
                    cache_paths=[],
                    pressure_callback=lambda stage, payload: callbacks.append(
                        (stage, payload.get("subtitle_generation_stage"))
                    ),
                )
                result = guard.checkpoint(
                    "stt_transcribe_done",
                    include_gpu=True,
                    cleanup=True,
                    force=True,
                )

            self.assertEqual(result["pressure_stage"], "critical")
            self.assertEqual(result["subtitle_generation_stage"], "stt_transcribe_done")
            self.assertIn(("critical", "stt_transcribe_done"), callbacks)
            self.assertTrue((Path(tmp) / "subtitle_generation_latest.json").exists())
            self.assertTrue(trim.called)


if __name__ == "__main__":
    unittest.main()
