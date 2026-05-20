import os
import sys
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
from core.runtime.stage_metrics import reset_stage_metrics, snapshot_stage_metrics


class RuntimeMemoryManagerTests(unittest.TestCase):
    def setUp(self):
        reset_stage_metrics()

    def tearDown(self):
        reset_stage_metrics()

    def test_process_rss_bytes_reuses_psutil_process_object(self):
        class FakeMemory:
            rss = 12345

        class FakeProcess:
            def memory_info(self):
                return FakeMemory()

        class FakePsutil:
            Error = RuntimeError
            calls = 0

            @classmethod
            def Process(cls, _pid):
                cls.calls += 1
                return FakeProcess()

        memory_manager._RSS_PSUTIL_PROCESS = None
        memory_manager._RSS_PSUTIL_UNAVAILABLE = False
        with patch.dict(sys.modules, {"psutil": FakePsutil}):
            first = memory_manager.process_rss_bytes()
            second = memory_manager.process_rss_bytes()

        self.assertEqual(first, 12345)
        self.assertEqual(second, 12345)
        self.assertEqual(FakePsutil.calls, 1)
        memory_manager._RSS_PSUTIL_PROCESS = None

    def test_runtime_trim_callables_are_resolved_once(self):
        memory_manager._RUNTIME_TRIM_CALLABLES = None
        first = memory_manager._runtime_trim_callables()

        with patch("builtins.__import__", side_effect=AssertionError("trim callables should be cached")):
            second = memory_manager._runtime_trim_callables()

        self.assertIs(first, second)
        self.assertTrue(first)
        memory_manager._RUNTIME_TRIM_CALLABLES = None

    def test_trim_runtime_memory_caches_records_action_costs_and_failures(self):
        def _ok_action():
            return None

        def _bad_action():
            raise RuntimeError("trim boom")

        with patch("core.runtime.memory_manager._runtime_trim_callables", return_value=[
            ("test.ok", _ok_action),
            ("test.bad", _bad_action),
        ]), patch("core.runtime.memory_manager.gc.collect", return_value=0), \
             patch(
                 "core.native_macos_memory.native_allocator_pressure_relief",
                 return_value={"ok": False},
             ):
            result = memory_manager.trim_runtime_memory_caches(stage="critical", include_gpu=False)

        self.assertEqual(result["stage"], "critical")
        self.assertIn("test.ok", result["actions"])
        self.assertIn("gc.collect", result["actions"])
        self.assertGreaterEqual(result["elapsed_ms"], 0.0)
        self.assertTrue(any(item["action"] == "test.ok" and item["ok"] for item in result["action_timings"]))
        self.assertTrue(any(item["action"] == "test.bad" and not item["ok"] for item in result["action_timings"]))
        self.assertTrue(any(item["action"] == "test.bad" for item in result["failures"]))

    def test_native_prune_callable_is_resolved_once(self):
        memory_manager._NATIVE_PRUNE_CALLABLE = memory_manager._NATIVE_PRUNE_CALLABLE_UNSET
        first = memory_manager._native_prune_callable()

        with patch("builtins.__import__", side_effect=AssertionError("native prune callable should be cached")):
            second = memory_manager._native_prune_callable()

        self.assertIs(first, second)
        self.assertTrue(callable(first))
        memory_manager._NATIVE_PRUNE_CALLABLE = memory_manager._NATIVE_PRUNE_CALLABLE_UNSET

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

    def test_runtime_disk_root_key_reuses_resolved_path_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager._expanded_resolved_path_text.cache_clear()
            cache_root = Path(tmp) / "cache_a"
            cache_root.mkdir()
            first = memory_manager._runtime_disk_root_key(cache_root)

            with patch("pathlib.Path.resolve", side_effect=AssertionError("root key should reuse resolved path cache")):
                second = memory_manager._runtime_disk_root_key(cache_root)

            self.assertEqual(first, second)

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

    def test_prune_runtime_disk_caches_python_fallback_avoids_full_sorted_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_a = root / "cache_a"
            cache_a.mkdir()
            old_file = cache_a / "old.bin"
            new_file = cache_a / "new.bin"
            old_file.write_bytes(b"x" * 300)
            new_file.write_bytes(b"x" * 300)
            os.utime(old_file, (100, 100))
            os.utime(new_file, (200, 200))

            with patch("core.runtime.memory_manager._prune_runtime_disk_caches_native", return_value=None), \
                 patch("builtins.sorted", side_effect=AssertionError("fallback prune should use heap instead of sorted copy")):
                result = prune_runtime_disk_caches(paths=[cache_a], target_total_bytes=350)

            self.assertEqual(result["removed_files"], 1)
            self.assertFalse(old_file.exists())
            self.assertTrue(new_file.exists())

    def test_prune_runtime_disk_caches_uses_native_result_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager._RUNTIME_DISK_ROOT_INDEX.clear()
            cache_a = Path(tmp) / "cache_a"
            cache_a.mkdir()
            root_key = memory_manager._runtime_disk_root_key(cache_a)
            memory_manager._RUNTIME_DISK_ROOT_INDEX[root_key] = {
                "root": str(cache_a),
                "exists": True,
                "bytes": 999,
                "files": 9,
                "entries": {"stale.bin": (1.0, 999)},
                "is_file": False,
                "scanned_at": time.time(),
            }

            native_result = {
                "removed_files": 2,
                "removed_bytes": 600,
                "remaining_bytes": 300,
                "target_total_bytes": 350,
                "used_native": True,
            }
            with patch("core.runtime.memory_manager._prune_runtime_disk_caches_native", return_value=native_result):
                result = prune_runtime_disk_caches(paths=[cache_a], target_total_bytes=350)

            self.assertEqual(result, native_result)
            self.assertNotIn(root_key, memory_manager._RUNTIME_DISK_ROOT_INDEX)

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
            memory_manager._default_runtime_disk_cache_paths_cached.cache_clear()
            with patch("core.runtime.memory_manager.config.DATASET_DIR", tmp):
                paths = [str(path) for path in default_runtime_disk_cache_paths()]

        self.assertIn(str(Path(tmp) / "video_preview_cache"), paths)

    def test_default_runtime_disk_cache_paths_reuses_cached_static_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager._default_runtime_disk_cache_paths_cached.cache_clear()
            with patch("core.runtime.memory_manager.config.DATASET_DIR", tmp), \
                 patch("pathlib.Path.exists", side_effect=[False] * 9 + [AssertionError("cached roots should not re-stat")]):
                first = default_runtime_disk_cache_paths()
                second = default_runtime_disk_cache_paths()

        self.assertEqual(first, second)

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

    def test_manager_poll_can_defer_trim_while_runtime_work_is_busy(self):
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 1 * 1024 ** 3,
            "available_memory_ratio": 0.06,
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "cpu_load_ratio": 0.25,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.memory_manager.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.memory_manager.process_rss_bytes", return_value=14 * 1024 ** 3), \
                 patch.object(RuntimeMemoryManager, "_maybe_trim") as maybe_trim, \
                 patch.object(RuntimeMemoryManager, "_maybe_report_leak") as maybe_report_leak, \
                 patch("core.runtime.memory_manager.gc.collect") as gc_collect:
                manager = RuntimeMemoryManager(
                    settings={"runtime_memory_tracemalloc_enabled": False},
                    diagnostics_dir=tmp,
                    cache_paths=[],
                )
                result = manager.poll(allow_trim=False)

            self.assertEqual(result["pressure_stage"], "critical")
            self.assertEqual(result["trim_deferred_reason"], "busy_runtime_work")
            maybe_trim.assert_not_called()
            maybe_report_leak.assert_not_called()
            gc_collect.assert_not_called()

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

    def test_pressure_stage_reuses_snapshot_resource_mapping(self):
        marker = {}

        class ResourceDict(dict):
            def copy(self):
                raise AssertionError("pressure stage should not copy resource mapping")

        resource = ResourceDict(
            {
                "memory_bytes": 16 * 1024 ** 3,
                "available_memory_bytes": 10 * 1024 ** 3,
                "available_memory_ratio": 0.62,
                "memory_pressure_stage": "warning",
                "process_rss_bytes": 3 * 1024 ** 3,
            }
        )
        marker["resource"] = resource
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.memory_manager.current_resource_snapshot", return_value=resource):
                manager = RuntimeMemoryManager(
                    settings={
                        "runtime_memory_tracemalloc_enabled": False,
                        "macos_memory_trim_runtime_caches_enabled": False,
                    },
                    diagnostics_dir=tmp,
                    cache_paths=[],
                )
                result = manager.collect_snapshot()

        self.assertIs(result["resource"], resource)
        self.assertEqual(result["pressure_stage"], "warning")

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

    def test_subtitle_generation_guard_auto_trims_gpu_on_critical_pressure(self):
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 512 * 1024 ** 2,
            "available_memory_ratio": 0.03,
            "memory_pressure_stage": "critical",
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "cpu_load_ratio": 0.12,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.memory_manager.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.memory_manager.process_rss_bytes", return_value=512 * 1024 ** 2), \
                 patch("core.runtime.memory_manager.trim_runtime_memory_caches", return_value={"actions": ["trim"]}) as trim:
                guard = SubtitleGenerationMemoryGuard(
                    settings={
                        "runtime_memory_tracemalloc_enabled": False,
                        "subtitle_generation_memory_checkpoint_interval_ms": 0,
                        "subtitle_generation_gpu_trim_cooldown_sec": 0,
                    },
                    diagnostics_dir=tmp,
                    cache_paths=[],
                )
                result = guard.checkpoint(
                    "stt_transcribe_chunk:5/13",
                    include_gpu=False,
                    cleanup=False,
                    force=True,
                )

        self.assertTrue(result["checkpoint_auto_cleanup"])
        self.assertTrue(result["checkpoint_auto_include_gpu"])
        trim.assert_called_with(stage="critical", include_gpu=True)

    def test_subtitle_generation_guard_records_trim_cooldown_skip(self):
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 512 * 1024 ** 2,
            "available_memory_ratio": 0.03,
            "memory_pressure_stage": "critical",
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "cpu_load_ratio": 0.12,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.memory_manager.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.memory_manager.process_rss_bytes", return_value=512 * 1024 ** 2), \
                 patch("core.runtime.memory_manager.trim_runtime_memory_caches", return_value={"actions": ["trim"]}) as trim:
                guard = SubtitleGenerationMemoryGuard(
                    settings={
                        "runtime_memory_tracemalloc_enabled": False,
                        "macos_memory_trim_runtime_caches_enabled": False,
                        "subtitle_generation_memory_checkpoint_interval_ms": 0,
                        "subtitle_generation_gpu_trim_cooldown_sec": 20,
                    },
                    diagnostics_dir=tmp,
                    cache_paths=[],
                )
                guard._last_gpu_trim_at = time.time()
                result = guard.checkpoint(
                    "save_export_done",
                    include_gpu=False,
                    cleanup=False,
                    force=True,
                )

        self.assertTrue(result["stage_trim_requested"])
        self.assertEqual(result["stage_trim_skipped_reason"], "cooldown")
        self.assertGreater(result["stage_trim_cooldown_remaining_sec"], 0)
        self.assertEqual(result["stage_trim_summary"]["requested_count"], 1)
        self.assertEqual(result["stage_trim_summary"]["skipped_count"], 1)
        self.assertEqual(result["stage_trim_summary"]["skipped_by_reason"]["cooldown"], 1)
        trim.assert_not_called()

    def test_subtitle_generation_guard_accumulates_trim_summary_by_stage_family(self):
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 512 * 1024 ** 2,
            "available_memory_ratio": 0.03,
            "memory_pressure_stage": "critical",
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
            "cpu_load_ratio": 0.12,
        }
        trim_results = [
            {
                "actions": ["warmup.trim"],
                "elapsed_ms": 2.0,
                "action_timings": [{"action": "warmup.trim", "elapsed_ms": 1.0, "ok": True}],
                "failures": [],
            },
            {
                "actions": ["gc.collect"],
                "elapsed_ms": 9.5,
                "action_timings": [{"action": "gc.collect", "elapsed_ms": 3.0, "ok": True}],
                "failures": [],
            },
            {
                "actions": ["mlx.core.clear_cache"],
                "elapsed_ms": 14.25,
                "action_timings": [{"action": "mlx.core.clear_cache", "elapsed_ms": 7.0, "ok": False}],
                "failures": [{"action": "mlx.core.clear_cache", "error_type": "RuntimeError", "message": "boom"}],
            },
        ]
        trim_iter = iter(trim_results)

        def _next_trim(*_args, **_kwargs):
            try:
                return next(trim_iter)
            except StopIteration:
                return trim_results[-1]

        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.memory_manager.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.memory_manager.process_rss_bytes", return_value=512 * 1024 ** 2), \
                 patch("core.runtime.memory_manager.trim_runtime_memory_caches", side_effect=_next_trim):
                guard = SubtitleGenerationMemoryGuard(
                    settings={
                        "runtime_memory_tracemalloc_enabled": False,
                        "subtitle_generation_memory_checkpoint_interval_ms": 0,
                        "subtitle_generation_gpu_trim_cooldown_sec": 0,
                    },
                    diagnostics_dir=tmp,
                    cache_paths=[],
                )
                guard.checkpoint("cut_prescan_done", cleanup=True, force=True)
                result = guard.checkpoint("stt_transcribe_chunk:1/13", include_gpu=False, cleanup=True, force=True)

        summary = result["stage_trim_summary"]
        self.assertEqual(summary["executed_count"], 2)
        self.assertEqual(summary["requested_count"], 2)
        self.assertEqual(summary["total_failure_count"], 1)
        self.assertEqual(summary["slowest_stage_key"], "stt_transcribe_chunk")
        self.assertEqual(summary["stages"]["cut_prescan_done"]["executed_count"], 1)
        self.assertEqual(summary["stages"]["stt_transcribe_chunk"]["executed_count"], 1)
        self.assertEqual(summary["actions"]["gc.collect"]["count"], 1)
        self.assertEqual(summary["actions"]["mlx.core.clear_cache"]["failure_count"], 1)
        metrics = snapshot_stage_metrics(max_events=10)
        self.assertIn("stt1", metrics["resources"])
        self.assertGreaterEqual(metrics["resources"]["stt1"]["stage_done_count"], 1)
        self.assertIn("stage_trim_elapsed_ms", metrics["recent_events"][-1]["metrics"])


if __name__ == "__main__":
    unittest.main()
