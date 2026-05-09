import unittest
from unittest.mock import patch

from core.performance import current_resource_snapshot


class NativeMacOSMemoryTests(unittest.TestCase):
    def test_resource_snapshot_uses_native_memory_when_available(self):
        native = {
            "source": "swift_mach_vm",
            "memory_bytes": 16 * 1024 ** 3,
            "available_memory_bytes": 2 * 1024 ** 3,
            "available_memory_ratio": 0.125,
            "pressure_stage": "warning",
            "process_rss_bytes": 512 * 1024 ** 2,
            "compressed_bytes": 3 * 1024 ** 3,
            "compressed_memory_ratio": 0.1875,
        }
        with patch("core.performance.hardware_profile", return_value={
            "system": "Darwin",
            "machine": "arm64",
            "logical_cores": 8,
            "physical_cores": 8,
            "performance_cores": 4,
            "efficiency_cores": 4,
            "memory_bytes": 16 * 1024 ** 3,
            "accelerators": {"metal": True},
        }), patch("core.native_macos_memory.native_memory_snapshot", return_value=native):
            snapshot = current_resource_snapshot({"macos_native_memory_snapshot_enabled": True})

        self.assertEqual(snapshot["available_memory_bytes"], 2 * 1024 ** 3)
        self.assertEqual(snapshot["memory_pressure_stage"], "warning")
        self.assertEqual(snapshot["process_rss_bytes"], 512 * 1024 ** 2)
        self.assertEqual(snapshot["native_memory"]["source"], "swift_mach_vm")


if __name__ == "__main__":
    unittest.main()
