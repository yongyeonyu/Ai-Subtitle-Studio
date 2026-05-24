import unittest
from unittest.mock import patch

from core import native_subtitle_resource as native
from core.native_swift_subtitle_resource import plan_subtitle_resource_via_swift


class NativeSubtitleResourceTests(unittest.TestCase):
    def test_cpp_resource_lane_summary_counts_ane_gpu_and_metal_without_cross_claiming(self):
        if not native.native_subtitle_resource_enabled():
            self.skipTest("native subtitle resource extension unavailable")
        rows = [
            {
                "task": "stt_precision",
                "accelerator": {"policy": "whisperkit_ane_gpu_saturation", "gpu_lanes": 8, "ane_lanes": 8},
            },
            {
                "task": "vad",
                "accelerator": {"policy": "metal_ml_balanced", "gpu_lanes": 4, "ane_lanes": 0},
            },
            {
                "task": "subtitle_llm",
                "accelerator": {"policy": "cpu_balanced", "gpu_lanes": 0, "ane_lanes": 0},
            },
        ]

        summary = native.resource_lane_summary(rows, gpu_lane_capacity=8, ane_model_lane_capacity=8)

        self.assertIsNotNone(summary)
        self.assertEqual(summary["native_backend"], "cpp")
        self.assertEqual(summary["gpu_task_count"], 2)
        self.assertEqual(summary["ane_task_count"], 1)
        self.assertEqual(summary["metal_task_count"], 1)
        self.assertEqual(summary["gpu_lanes_total"], 12)
        self.assertEqual(summary["ane_lanes_total"], 8)
        self.assertEqual(summary["max_gpu_lanes"], 8)
        self.assertEqual(summary["max_ane_lanes"], 8)
        self.assertEqual(summary["gpu_lane_capacity"], 8)
        self.assertEqual(summary["ane_model_lane_capacity"], 8)
        self.assertEqual(summary["gpu_lane_peak_ratio"], 1.0)
        self.assertEqual(summary["ane_model_lane_peak_ratio"], 1.0)
        self.assertEqual(summary["full_gpu_lane_task_count"], 1)
        self.assertEqual(summary["full_ane_model_lane_task_count"], 1)
        self.assertTrue(summary["gpu_lane_peak_saturated"])
        self.assertTrue(summary["ane_model_lane_peak_saturated"])
        self.assertFalse(summary["metal_claims_ane"])
        self.assertEqual(summary["ane_tasks"], ["stt_precision"])
        self.assertEqual(summary["metal_tasks"], ["vad"])

    def test_swift_resource_wrapper_attaches_cpp_parity_summary(self):
        if not native.native_subtitle_resource_enabled():
            self.skipTest("native subtitle resource extension unavailable")
        swift_payload = {
            "schema": "ai_subtitle_studio.subtitle_resource.plan.v1",
            "backend": "swift",
            "pressure_stage": "normal",
            "accelerator_summary": {
                "schema": "ai_subtitle_studio.subtitle_resource.summary.v1",
                "gpu_task_count": 2,
                "ane_task_count": 1,
                "metal_task_count": 1,
                "gpu_lanes_total": 12,
                "ane_lanes_total": 8,
                "max_gpu_lanes": 8,
                "max_ane_lanes": 8,
                "gpu_lane_capacity": 8,
                "ane_model_lane_capacity": 8,
                "gpu_lane_peak_ratio": 1.0,
                "ane_model_lane_peak_ratio": 1.0,
                "full_gpu_lane_task_count": 1,
                "full_ane_model_lane_task_count": 1,
                "gpu_lane_peak_saturated": True,
                "ane_model_lane_peak_saturated": True,
                "metal_claims_ane": False,
                "routing": [
                    {
                        "task": "stt_precision",
                        "policy": "whisperkit_ane_gpu_saturation",
                        "compute_units": "all",
                        "gpu_lanes": 8,
                        "ane_lanes": 8,
                    },
                    {
                        "task": "vad",
                        "policy": "metal_ml_balanced",
                        "compute_units": "cpuOnly",
                        "gpu_lanes": 4,
                        "ane_lanes": 0,
                    },
                ],
            },
        }

        with patch(
            "core.native_swift_subtitle_resource.run_subtitle_core_operation_via_swift",
            return_value=swift_payload,
        ):
            result = plan_subtitle_resource_via_swift(settings={})

        self.assertIsNotNone(result)
        summary = result["accelerator_summary"]
        self.assertEqual(summary["cpp_backend"], "cpp")
        self.assertTrue(summary["cpp_parity"])
        self.assertEqual(summary["cpp_summary"]["gpu_lanes_total"], 12)
        self.assertEqual(summary["cpp_summary"]["gpu_lane_capacity"], 8)
        self.assertTrue(summary["cpp_summary"]["ane_model_lane_peak_saturated"])

    def test_swift_resource_wrapper_passes_hardware_topology_when_missing(self):
        swift_payload = {
            "schema": "ai_subtitle_studio.subtitle_resource.plan.v1",
            "backend": "swift",
            "pressure_stage": "normal",
            "accelerator_summary": {},
        }
        hardware = {
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "gpu_cores": 10,
            "neural_engine_cores": 16,
            "memory_bytes": 16 * 1024 ** 3,
        }

        with patch("core.native_swift_subtitle_resource.hardware_profile", return_value=hardware), \
             patch(
                 "core.native_swift_subtitle_resource.run_subtitle_core_operation_via_swift",
                 return_value=swift_payload,
             ) as runner:
            result = plan_subtitle_resource_via_swift(settings={})

        self.assertIsNotNone(result)
        payload = runner.call_args.args[1]
        self.assertEqual(payload["topology"]["gpu_cores"], 10)
        self.assertEqual(payload["topology"]["neural_engine_cores"], 16)


if __name__ == "__main__":
    unittest.main()
