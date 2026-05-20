import tempfile
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.runtime.multi_process import (
    RuntimeResourceCoordinator,
    _ACCELERATION_CALLOUTS_UNSET,
    _runtime_acceleration_callouts,
    apply_apple_m_subtitle_pipeline_plan,
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
    def setUp(self):
        import core.runtime.multi_process as multi_process

        multi_process._ACCELERATION_CALLOUTS = _ACCELERATION_CALLOUTS_UNSET

    def tearDown(self):
        import core.runtime.multi_process as multi_process

        multi_process._ACCELERATION_CALLOUTS = _ACCELERATION_CALLOUTS_UNSET

    def test_runtime_acceleration_callouts_are_resolved_once(self):
        first = _runtime_acceleration_callouts()
        with patch("builtins.__import__", side_effect=AssertionError("acceleration imports should be cached")):
            second = _runtime_acceleration_callouts()

        self.assertIs(first, second)

    def test_runtime_resource_coordinator_reuses_psutil_module_after_init(self):
        class FakeProcess:
            def __init__(self):
                self.calls = 0

            def cpu_percent(self, interval=None):
                self.calls += 1
                return 33.0

        class FakePsutil:
            process = FakeProcess()
            system_calls = 0

            @classmethod
            def Process(cls, _pid):
                return cls.process

            @classmethod
            def cpu_percent(cls, interval=None):
                cls.system_calls += 1
                return 44.0

        with patch.dict(sys.modules, {"psutil": FakePsutil}):
            coordinator = RuntimeResourceCoordinator(settings={}, logger=None)

        with patch("builtins.__import__", side_effect=AssertionError("psutil should be reused after init")):
            self.assertEqual(coordinator._sample_system_cpu_percent(), 44.0)
            self.assertEqual(coordinator._sample_process_cpu_percent(), 33.0)

    def test_apply_apple_m_subtitle_pipeline_plan_sets_shared_worker_budget(self):
        snapshot = {
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "memory_bytes": 16 * 1024 ** 3,
        }
        with patch("core.runtime.multi_process.config.IS_APPLE_SILICON", True), \
             patch("core.runtime.multi_process.hardware_profile", return_value=snapshot):
            settings = apply_apple_m_subtitle_pipeline_plan({
                "runtime_scheduler_ramp_up_enabled": True,
                "stt_ensemble_parallel_enabled": True,
            })

        self.assertEqual(settings["runtime_performance_profile"], "max")
        self.assertEqual(settings["runtime_native_threads"], 9)
        self.assertEqual(settings["runtime_scheduler_reserve_cores"], 1)
        self.assertFalse(settings["runtime_scheduler_ramp_up_enabled"])
        self.assertEqual(settings["io_workers"], 8)
        self.assertEqual(settings["audio_chunk_route_max_workers"], 8)
        self.assertEqual(settings["ffmpeg_filter_threads"], 6)
        self.assertEqual(settings["scan_cut_pioneer_cpu_max_workers"], 4)
        self.assertEqual(settings["scan_cut_follower_cpu_max_workers"], 4)
        self.assertEqual(settings["scan_cut_follower_outer_splits"], 4)
        self.assertTrue(settings["scan_cut_parallel_quarter_enabled"])
        self.assertEqual(settings["scan_cut_parallel_quarter_count"], 4)
        self.assertEqual(settings["scan_cut_follower_stream_start_percent"], 25)
        self.assertEqual(settings["scan_cut_follower_stream_batch_size"], 16)
        self.assertFalse(settings["scan_cut_follower_mps_enabled"])
        self.assertFalse(settings["stt_ensemble_parallel_enabled"])
        self.assertEqual(settings["stt_word_timestamps_mode"], "selective")
        self.assertEqual(settings["llm_threads_resource_max"], 5)
        self.assertEqual(settings["local_ollama_llm_max_workers"], 2)
        self.assertTrue(settings["native_cpp_llm_macro_groups_enabled"])
        self.assertTrue(settings["native_swift_quality_scoring_enabled"])
        self.assertTrue(settings["native_swift_common_split_enabled"])
        self.assertFalse(settings["native_swift_llm_candidate_policy_enabled"])
        self.assertFalse(settings["native_swift_deep_policy_enabled"])
        self.assertFalse(settings["native_swift_lora_scoring_enabled"])
        self.assertEqual(settings["_apple_m_pipeline_parallel_plan"]["audio_workers"], 8)

    def test_apply_apple_m_subtitle_pipeline_plan_uses_m5_chip_aware_budget(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "brand_string": "Apple M5",
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
        }
        with patch("core.runtime.multi_process.config.IS_APPLE_SILICON", True), \
             patch("core.runtime.multi_process.hardware_profile", return_value=snapshot):
            settings = apply_apple_m_subtitle_pipeline_plan({})

        plan = settings["_apple_m_pipeline_parallel_plan"]
        self.assertTrue(plan["chip_aware"])
        self.assertEqual(plan["chip_profile"]["chip_name"], "Apple M5")
        self.assertEqual(settings["runtime_native_threads"], 9)
        self.assertEqual(settings["runtime_scheduler_reserve_cores"], 1)
        self.assertEqual(settings["io_workers"], 9)
        self.assertEqual(settings["ffmpeg_filter_threads"], 8)
        self.assertEqual(settings["scan_cut_pioneer_cpu_max_workers"], 4)
        self.assertEqual(settings["scan_cut_follower_cpu_max_workers"], 4)
        self.assertEqual(settings["scan_cut_follower_outer_splits"], 4)
        self.assertTrue(settings["scan_cut_parallel_quarter_enabled"])
        self.assertEqual(settings["scan_cut_parallel_quarter_count"], 4)
        self.assertEqual(settings["scan_cut_follower_stream_start_percent"], 25)
        self.assertEqual(settings["scan_cut_follower_stream_batch_size"], 16)
        self.assertEqual(settings["stt_primary_gpu_slots"], 1)
        self.assertEqual(settings["stt_npu_coreml_slots"], 1)
        self.assertEqual(settings["stt_accelerator_distribution"], "gpu+npu+cpu")
        self.assertTrue(plan["native_cpp_llm_macro_groups"])
        self.assertEqual(plan["native_swift_quality_min_segments"], 64)
        self.assertEqual(plan["native_swift_common_split_min_items"], 1000)

    def test_apply_apple_m_subtitle_pipeline_plan_can_be_disabled(self):
        original = {"apple_m_pipeline_parallel_enabled": False, "io_workers": 2}
        with patch("core.runtime.multi_process.config.IS_APPLE_SILICON", True):
            settings = apply_apple_m_subtitle_pipeline_plan(original)

        self.assertEqual(settings, original)

    def test_apply_apple_m_subtitle_pipeline_plan_preserves_explicit_cut_follower_mps_opt_in(self):
        snapshot = {
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "memory_bytes": 16 * 1024 ** 3,
        }
        with patch("core.runtime.multi_process.config.IS_APPLE_SILICON", True), \
             patch("core.runtime.multi_process.hardware_profile", return_value=snapshot):
            settings = apply_apple_m_subtitle_pipeline_plan({
                "scan_cut_follower_mps_enabled": True,
            })

        self.assertTrue(settings["scan_cut_follower_mps_enabled"])

    def test_apply_apple_m_plan_preserves_manual_native_batch_thresholds(self):
        snapshot = {
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "memory_bytes": 16 * 1024 ** 3,
        }
        with patch("core.runtime.multi_process.config.IS_APPLE_SILICON", True), \
             patch("core.runtime.multi_process.hardware_profile", return_value=snapshot):
            settings = apply_apple_m_subtitle_pipeline_plan({
                "apple_m_pipeline_respect_manual_worker_settings": True,
                "native_swift_quality_scoring_min_segments": 128,
                "native_swift_common_split_min_items": 1500,
                "native_swift_lora_scoring_enabled": True,
            })

        self.assertEqual(settings["native_swift_quality_scoring_min_segments"], 128)
        self.assertEqual(settings["native_swift_common_split_min_items"], 1500)
        self.assertFalse(settings["native_swift_lora_scoring_enabled"])

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

    def test_runtime_parallel_worker_plan_clamps_to_distributed_ceiling(self):
        with patch("core.runtime.multi_process.runtime_scheduler_reserve_cores", return_value=1), \
             patch("core.runtime.multi_process.distributed_worker_ceiling", return_value=3), \
             patch("core.runtime.multi_process.adaptive_worker_count", return_value=(8, {"reason": "resource_adaptive"})):
            workers, meta = runtime_parallel_worker_plan(
                settings={"runtime_performance_profile": "max"},
                task="cut_pioneer",
                workload=20,
                requested=8,
                minimum=1,
                maximum=8,
                reserve_task="cut_pioneer",
            )

        self.assertEqual(workers, 3)
        self.assertEqual(meta["worker_ceiling"], 3)
        self.assertEqual(meta["worker_upper_bound"], 3)

    def test_runtime_parallel_worker_plan_treats_zero_maximum_as_auto(self):
        with patch("core.runtime.multi_process.runtime_scheduler_reserve_cores", return_value=0), \
             patch("core.runtime.multi_process.distributed_worker_ceiling", return_value=6), \
             patch("core.runtime.multi_process.adaptive_worker_count", return_value=(8, {"reason": "resource_adaptive"})):
            workers, meta = runtime_parallel_worker_plan(
                settings={"runtime_performance_profile": "max"},
                task="io",
                workload=12,
                requested=8,
                minimum=1,
                maximum=0,
                reserve_task="io",
            )

        self.assertEqual(workers, 6)
        self.assertEqual(meta["worker_upper_bound"], 6)

    def test_runtime_parallel_worker_plan_sanitizes_numeric_settings(self):
        with patch("core.runtime.multi_process.runtime_scheduler_reserve_cores", return_value="0.0"), \
             patch("core.runtime.multi_process.distributed_worker_ceiling", return_value="6.0"), \
             patch("core.runtime.multi_process.adaptive_worker_count", return_value=("5", {"reason": "resource_adaptive"})):
            workers, meta = runtime_parallel_worker_plan(
                settings={"runtime_performance_profile": "max"},
                task="io",
                workload="12.0",
                requested="5",
                minimum="2",
                maximum="auto",
                reserve_task="io",
            )

        self.assertEqual(workers, 5)
        self.assertEqual(meta["worker_ceiling"], 6)
        self.assertEqual(meta["worker_upper_bound"], 6)
        self.assertEqual(meta["reserve_cores"], 0)

    def test_runtime_parallel_worker_plan_uses_bench_locked_cut_follower_four_way_cap(self):
        hardware = {
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
        }
        with patch("core.runtime.multi_process.hardware_profile", return_value=hardware), \
             patch("core.runtime.multi_process.runtime_scheduler_reserve_cores", return_value=0), \
             patch("core.runtime.multi_process.distributed_worker_ceiling", return_value=10), \
             patch("core.runtime.multi_process.adaptive_worker_count", return_value=(10, {"reason": "resource_adaptive"})):
            workers, meta = runtime_parallel_worker_plan(
                settings={"runtime_performance_profile": "max"},
                task="cut_follower",
                workload=24,
                requested=10,
                minimum=1,
                maximum=24,
                reserve_task="cut_follower",
                accelerators=["cpu"],
            )

        self.assertEqual(workers, 4)
        self.assertEqual(meta["worker_upper_bound"], 4)
        self.assertEqual(meta["worker_topology_limit"], 4)
        self.assertTrue(meta["worker_topology_applied"])
        self.assertEqual(meta["worker_topology"]["reason"], "bench_locked_four_way_follower")

    def test_runtime_parallel_worker_plan_serializes_cut_follower_gpu_queue(self):
        hardware = {
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
        }
        with patch("core.runtime.multi_process.hardware_profile", return_value=hardware), \
             patch("core.runtime.multi_process.runtime_scheduler_reserve_cores", return_value=0), \
             patch("core.runtime.multi_process.distributed_worker_ceiling", return_value=10), \
             patch("core.runtime.multi_process.adaptive_worker_count", return_value=(10, {"reason": "resource_adaptive"})):
            workers, meta = runtime_parallel_worker_plan(
                settings={"runtime_performance_profile": "max"},
                task="cut_follower",
                workload=24,
                requested=10,
                minimum=1,
                maximum=24,
                reserve_task="cut_follower",
                accelerators=["mps"],
            )

        self.assertEqual(workers, 1)
        self.assertEqual(meta["worker_upper_bound"], 1)
        self.assertEqual(meta["worker_topology"]["reason"], "single_gpu_queue")

    def test_runtime_parallel_worker_plan_uses_bench_locked_cut_pioneer_four_way_cap(self):
        hardware = {
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
        }
        with patch("core.runtime.multi_process.hardware_profile", return_value=hardware), \
             patch("core.runtime.multi_process.runtime_scheduler_reserve_cores", return_value=0), \
             patch("core.runtime.multi_process.distributed_worker_ceiling", return_value=10), \
             patch("core.runtime.multi_process.adaptive_worker_count", return_value=(10, {"reason": "resource_adaptive"})):
            workers, meta = runtime_parallel_worker_plan(
                settings={"runtime_performance_profile": "max"},
                task="cut_pioneer",
                workload=120,
                requested=10,
                minimum=1,
                maximum=120,
                reserve_task="cut_pioneer",
                accelerators=["cpu"],
            )

        self.assertEqual(workers, 4)
        self.assertEqual(meta["worker_upper_bound"], 4)
        self.assertTrue(meta["worker_topology_applied"])
        self.assertEqual(meta["worker_topology"]["reason"], "bench_locked_four_way_pioneer")

    def test_runtime_parallel_worker_plan_uses_bench_locked_cut_pioneer_four_way_for_medium_clip(self):
        hardware = {
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
        }
        with patch("core.runtime.multi_process.hardware_profile", return_value=hardware), \
             patch("core.runtime.multi_process.runtime_scheduler_reserve_cores", return_value=0), \
             patch("core.runtime.multi_process.distributed_worker_ceiling", return_value=10), \
             patch("core.runtime.multi_process.adaptive_worker_count", return_value=(10, {"reason": "resource_adaptive"})):
            workers, meta = runtime_parallel_worker_plan(
                settings={"runtime_performance_profile": "max"},
                task="cut_pioneer",
                workload=60,
                requested=10,
                minimum=1,
                maximum=120,
                reserve_task="cut_pioneer",
                accelerators=["cpu"],
            )

        self.assertEqual(workers, 4)
        self.assertEqual(meta["worker_upper_bound"], 4)
        self.assertTrue(meta["worker_topology_applied"])
        self.assertEqual(meta["worker_topology"]["reason"], "bench_locked_four_way_pioneer")

    def test_runtime_parallel_worker_plan_honors_cut_pioneer_configured_cap(self):
        hardware = {
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
        }
        with patch("core.runtime.multi_process.hardware_profile", return_value=hardware), \
             patch("core.runtime.multi_process.runtime_scheduler_reserve_cores", return_value=0), \
             patch("core.runtime.multi_process.distributed_worker_ceiling", return_value=10), \
             patch("core.runtime.multi_process.adaptive_worker_count", return_value=(10, {"reason": "resource_adaptive"})):
            workers, meta = runtime_parallel_worker_plan(
                settings={"runtime_performance_profile": "max", "scan_cut_pioneer_cpu_max_workers": 6},
                task="cut_pioneer",
                workload=120,
                requested=10,
                minimum=1,
                maximum=120,
                reserve_task="cut_pioneer",
                accelerators=["cpu"],
            )

        self.assertEqual(workers, 6)
        self.assertEqual(meta["worker_upper_bound"], 6)
        self.assertTrue(meta["worker_topology_applied"])
        self.assertEqual(meta["worker_topology"]["reason"], "configured")

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
                coordinator = RuntimeResourceCoordinator(
                    settings={
                        "runtime_performance_profile": "max",
                        "runtime_monitor_terminal_log_enabled": True,
                    },
                    logger=logger,
                )
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
        self.assertNotIn("RUNTIME", coordinator.status_html(data))
        self.assertNotIn("ACCEL CPU + GPU + NPU", coordinator.status_html(data))
        self.assertIn("CPU 72%", coordinator.status_html(data))
        self.assertNotIn("ACTIVE", coordinator.status_html(data))
        self.assertEqual(coordinator.status_color(data), "#34C759")
        self.assertIn("cpu=72", coordinator.status_plain(data))
        self.assertNotIn("runtime=max", coordinator.status_plain(data))
        self.assertNotIn("accel=CPU + GPU + NPU", coordinator.status_plain(data))
        self.assertTrue(any("📊 [Runtime] CPU 72%" in item for item in logger.messages))
        self.assertFalse(any("MAX" in item or "ACCEL" in item for item in logger.messages))

    def test_runtime_resource_coordinator_does_not_log_normal_idle_snapshot(self):
        logger = _Logger()
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
                coordinator = RuntimeResourceCoordinator(settings={}, logger=logger)
                coordinator._sample_system_cpu_percent = lambda: 8.0
                coordinator._sample_process_cpu_percent = lambda: 2.0
                data = coordinator.poll(window=None)

            self.assertTrue((tmpdir / "latest.json").exists())

        self.assertEqual(data["pressure_stage"], "normal")
        self.assertEqual(data["active_labels"], [])
        self.assertNotIn("ACTIVE", coordinator.status_html(data))
        self.assertEqual(logger.messages, [])

    def test_runtime_resource_coordinator_terminal_log_is_off_by_default_even_when_active(self):
        logger = _Logger()
        snapshot = {
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 12 * 1024 ** 3,
            "available_memory_ratio": 0.75,
            "logical_cores": 8,
            "physical_cores": 4,
            "performance_cores": 4,
        }
        window = SimpleNamespace(backend=SimpleNamespace(_active=True))
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            with patch("core.runtime.multi_process.runtime_monitor_dir", return_value=tmpdir), \
                 patch("core.runtime.multi_process.current_resource_snapshot", return_value=snapshot), \
                 patch("core.runtime.multi_process.process_rss_bytes", return_value=1 * 1024 ** 3), \
                 patch("core.runtime.multi_process.runtime_disk_cache_usage", return_value={"total_bytes": 0, "file_count": 0}), \
                 patch("core.runtime.multi_process.native_thread_budget", return_value=8), \
                 patch("core.runtime.multi_process.hardware_profile", return_value=snapshot):
                coordinator = RuntimeResourceCoordinator(settings={}, logger=logger)
                coordinator._sample_system_cpu_percent = lambda: 16.0
                coordinator._sample_process_cpu_percent = lambda: 99.0
                data = coordinator.poll(window=window)

        self.assertIn("pipeline", data["active_labels"])
        self.assertEqual(logger.messages, [])

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

    def test_runtime_resource_coordinator_latest_snapshot_stays_defensive_copy(self):
        coordinator = RuntimeResourceCoordinator(settings={}, logger=None)
        coordinator._latest = {
            "pressure_stage": "normal",
            "active_labels": ["pipeline"],
            "rss_gb": 1.25,
        }

        snapshot = coordinator.latest_snapshot()
        snapshot["pressure_stage"] = "critical"
        snapshot["active_labels"] = ["mutated"]

        self.assertEqual(coordinator._latest["pressure_stage"], "normal")
        self.assertEqual(coordinator._latest["active_labels"], ["pipeline"])

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

    def test_runtime_acceleration_snapshot_uses_hardware_gpu_without_torch_gpu(self):
        hardware = {
            "accelerators": {"metal_gpu": True, "mlx": True, "coreml_cli": False},
        }
        with patch("core.runtime.multi_process.hardware_profile", return_value=hardware), \
             patch("core.audio.npu_acceleration.apple_neural_engine_available", return_value=False), \
             patch("core.audio.torch_acceleration.torch_acceleration_snapshot", return_value={"ordered_backends": ["cpu"], "gpu_available": False}):
            snapshot = runtime_acceleration_snapshot({"runtime_hardware_acceleration_enabled": True})

        self.assertEqual(snapshot["summary"], "CPU + GPU")
        self.assertTrue(snapshot["available"]["gpu"])
        self.assertFalse(snapshot["available"]["npu"])

    def test_runtime_acceleration_snapshot_respects_disabled_hardware_acceleration(self):
        hardware = {
            "accelerators": {"metal_gpu": True, "neural_engine_path": "/tmp/ane"},
        }
        with patch("core.runtime.multi_process.hardware_profile", return_value=hardware), \
             patch("core.audio.npu_acceleration.apple_neural_engine_available", return_value=True), \
             patch("core.audio.torch_acceleration.torch_acceleration_snapshot", return_value={"ordered_backends": ["mps", "cpu"], "gpu_available": True}):
            snapshot = runtime_acceleration_snapshot({"runtime_hardware_acceleration_enabled": False})

        self.assertEqual(snapshot["summary"], "CPU")
        self.assertFalse(snapshot["available"]["gpu"])
        self.assertFalse(snapshot["available"]["npu"])


if __name__ == "__main__":
    unittest.main()
