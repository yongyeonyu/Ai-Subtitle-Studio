import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.runtime.multi_process import (
    RuntimeResourceCoordinator,
    manual_lora_runtime_settings,
    runtime_acceleration_snapshot,
    runtime_llm_worker_plan,
    runtime_parallel_worker_plan,
)


class _Logger:
    def __init__(self):
        self.messages = []

    def log(self, message):
        self.messages.append(str(message))


class RuntimeMultiProcessTests(unittest.TestCase):
    def test_manual_lora_runtime_settings_keeps_one_core_for_stop(self):
        snapshot = {
            "logical_cores": 10,
            "physical_cores": 8,
            "performance_cores": 4,
        }
        with patch("core.runtime.multi_process.hardware_profile", return_value=snapshot):
            settings = manual_lora_runtime_settings({"runtime_scheduler_reserve_cores": 0})

        self.assertEqual(settings["runtime_performance_profile"], "max")
        self.assertEqual(settings["runtime_scheduler_reserve_cores"], 1)
        self.assertEqual(settings["runtime_native_threads"], 9)
        self.assertTrue(settings["runtime_manual_lora_full_speed"])

    def test_runtime_parallel_worker_plan_adds_coordinator_metadata(self):
        with patch("core.runtime.multi_process.runtime_scheduler_reserve_cores", return_value=0), \
             patch("core.runtime.multi_process.distributed_worker_ceiling", return_value=6), \
             patch("core.runtime.multi_process.adaptive_worker_count", return_value=(4, {"reason": "resource_adaptive"})):
            workers, meta = runtime_parallel_worker_plan(
                settings={"runtime_performance_profile": "max"},
                task="stt",
                workload=12,
                requested=4,
                minimum=1,
                maximum=8,
                reserve_task="stt",
            )

        self.assertEqual(workers, 4)
        self.assertEqual(meta["worker_ceiling"], 6)
        self.assertEqual(meta["reserve_cores"], 0)
        self.assertEqual(meta["coordinator"], "runtime_parallel_worker_plan")
        self.assertEqual(meta["reason"], "resource_adaptive")

    def test_runtime_parallel_worker_plan_floors_mixed_accelerator_work(self):
        with patch("core.runtime.multi_process.runtime_scheduler_reserve_cores", return_value=0), \
             patch("core.runtime.multi_process.distributed_worker_ceiling", return_value=2), \
             patch("core.runtime.multi_process.adaptive_worker_count", return_value=(1, {"reductions": ["high_cpu_load"]})):
            workers, meta = runtime_parallel_worker_plan(
                settings={"runtime_performance_profile": "max"},
                task="stt",
                workload=2,
                requested=2,
                minimum=1,
                maximum=2,
                reserve_task="stt",
                accelerators=["npu", "gpu"],
            )

        self.assertEqual(workers, 2)
        self.assertTrue(meta["accelerator_mix_applied"])
        self.assertEqual(meta["accelerator_mix_floor"], 2)
        self.assertEqual(meta["accelerators"], ["npu", "gpu"])

    def test_runtime_llm_worker_plan_adds_coordinator_metadata(self):
        with patch("core.runtime.multi_process.adaptive_llm_worker_count", return_value=(2, {"reason": "resource_adaptive"})):
            workers, meta = runtime_llm_worker_plan(
                settings={"llm_threads_auto_enabled": True},
                workload=8,
                provider="ollama",
                model="exaone3.5:7.8b",
                task="subtitle",
                requested=2,
            )

        self.assertEqual(workers, 2)
        self.assertEqual(meta["reason"], "resource_adaptive")
        self.assertEqual(meta["coordinator"], "runtime_llm_worker_plan")

    def test_runtime_resource_coordinator_poll_writes_snapshot_and_formats_status(self):
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 6 * 1024 ** 3,
            "available_memory_ratio": 0.37,
            "logical_cores": 10,
            "physical_cores": 8,
            "performance_cores": 4,
        }
        logger = _Logger()
        window = SimpleNamespace(
            _auto_processing_active=True,
            backend=SimpleNamespace(_active=True),
            backend_fast=SimpleNamespace(_active=False),
            _editor_widget=SimpleNamespace(_is_ai_processing=True, _stt_mode_enabled=True),
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            with patch("core.runtime.multi_process.runtime_monitor_dir", return_value=tmpdir), \
                 patch("core.runtime.multi_process.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.multi_process.process_rss_bytes", return_value=3 * 1024 ** 3), \
                 patch("core.runtime.multi_process.runtime_disk_cache_usage", return_value={"total_bytes": 2 * 1024 ** 3, "file_count": 7}), \
                 patch("core.runtime.multi_process.native_thread_budget", return_value=10), \
                 patch("core.runtime.multi_process.hardware_profile", return_value=snapshot), \
                 patch("core.runtime.multi_process.runtime_acceleration_snapshot", return_value={"summary": "CPU + GPU + NPU", "available": {"cpu": True, "gpu": True, "npu": True}}):
                coordinator = RuntimeResourceCoordinator(settings={"runtime_performance_profile": "max"}, logger=logger)
                coordinator._sample_system_cpu_percent = lambda: 72.5
                coordinator._sample_process_cpu_percent = lambda: 54.0
                data = coordinator.poll(window=window)

            self.assertTrue((tmpdir / "latest.json").exists())

        self.assertEqual(data["profile"], "max")
        self.assertEqual(data["pressure_stage"], "normal")
        self.assertEqual(data["logical_cores"], 10)
        self.assertEqual(data["native_thread_budget"], 10)
        self.assertEqual(data["disk_cache_files"], 7)
        self.assertEqual(data["accelerators"]["summary"], "CPU + GPU + NPU")
        self.assertIn("pipeline", data["active_labels"])
        self.assertIn("editor", data["active_labels"])
        self.assertIn("stt", data["active_labels"])
        self.assertIn("RUNTIME", coordinator.status_html(data))
        self.assertIn("ACCEL CPU + GPU + NPU", coordinator.status_html(data))
        self.assertIn("cpu=72", coordinator.status_plain(data))
        self.assertIn("accel=CPU + GPU + NPU", coordinator.status_plain(data))
        self.assertTrue(any("📊 [Runtime]" in item for item in logger.messages))

    def test_runtime_resource_coordinator_exit_mode_overrides_pressure_stage(self):
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 12 * 1024 ** 3,
            "available_memory_ratio": 0.75,
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            with patch("core.runtime.multi_process.runtime_monitor_dir", return_value=tmpdir), \
                 patch("core.runtime.multi_process.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.multi_process.process_rss_bytes", return_value=1 * 1024 ** 3), \
                 patch("core.runtime.multi_process.runtime_disk_cache_usage", return_value={"total_bytes": 0, "file_count": 0}), \
                 patch("core.runtime.multi_process.native_thread_budget", return_value=8), \
                 patch("core.runtime.multi_process.hardware_profile", return_value=snapshot):
                coordinator = RuntimeResourceCoordinator(settings={}, logger=None)
                coordinator._sample_system_cpu_percent = lambda: 12.0
                coordinator._sample_process_cpu_percent = lambda: 8.0
                coordinator.set_exit_mode(True)
                data = coordinator.poll(window=None)

        self.assertEqual(data["pressure_stage"], "exit")
        self.assertTrue(data["exit_mode"])

    def test_runtime_acceleration_snapshot_reports_enabled_backends(self):
        hardware = {
            "accelerators": {"metal": True, "neural_engine_path": "/tmp/ane"},
        }
        with patch("core.runtime.multi_process.hardware_profile", return_value=hardware), \
             patch("core.audio.npu_acceleration.apple_neural_engine_available", return_value=True), \
             patch("core.audio.torch_acceleration.torch_acceleration_snapshot", return_value={"ordered_backends": ["mps", "cpu"], "gpu_available": True}):
            snapshot = runtime_acceleration_snapshot({"runtime_hardware_acceleration_enabled": True})

        self.assertEqual(snapshot["summary"], "CPU + GPU + NPU")
        self.assertTrue(snapshot["available"]["cpu"])
        self.assertTrue(snapshot["available"]["gpu"])
        self.assertTrue(snapshot["available"]["npu"])


if __name__ == "__main__":
    unittest.main()
