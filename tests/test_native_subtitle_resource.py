import unittest

from core import native_subtitle_resource as native


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

        summary = native.resource_lane_summary(rows)

        self.assertIsNotNone(summary)
        self.assertEqual(summary["native_backend"], "cpp")
        self.assertEqual(summary["gpu_task_count"], 2)
        self.assertEqual(summary["ane_task_count"], 1)
        self.assertEqual(summary["metal_task_count"], 1)
        self.assertEqual(summary["gpu_lanes_total"], 12)
        self.assertEqual(summary["ane_lanes_total"], 8)
        self.assertEqual(summary["max_gpu_lanes"], 8)
        self.assertEqual(summary["max_ane_lanes"], 8)
        self.assertFalse(summary["metal_claims_ane"])
        self.assertEqual(summary["ane_tasks"], ["stt_precision"])
        self.assertEqual(summary["metal_tasks"], ["vad"])


if __name__ == "__main__":
    unittest.main()
