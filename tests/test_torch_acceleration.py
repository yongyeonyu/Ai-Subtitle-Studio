import types
import unittest
from unittest import mock

from core.audio import torch_acceleration


def _fake_torch(
    *,
    mps: bool = False,
    cuda: bool = False,
    mps_allocated: int = 0,
    mps_driver: int = 0,
    mps_recommended: int = 0,
    cuda_free: int = 0,
    cuda_total: int = 0,
    cuda_allocated: int = 0,
):
    return types.SimpleNamespace(
        backends=types.SimpleNamespace(
            mps=types.SimpleNamespace(is_available=lambda: bool(mps))
        ),
        mps=types.SimpleNamespace(
            current_allocated_memory=lambda: int(mps_allocated),
            driver_allocated_memory=lambda: int(mps_driver),
            recommended_max_memory=lambda: int(mps_recommended),
        ),
        cuda=types.SimpleNamespace(
            is_available=lambda: bool(cuda),
            mem_get_info=lambda: (int(cuda_free), int(cuda_total)),
            memory_allocated=lambda: int(cuda_allocated),
        ),
    )


class _FakeTo:
    def __init__(self):
        self.calls: list[str] = []

    def to(self, device):
        self.calls.append(str(device))
        return self


class TorchAccelerationTest(unittest.TestCase):
    def test_preferred_torch_device_name_prefers_mps(self):
        with mock.patch.dict("sys.modules", {"torch": _fake_torch(mps=True, cuda=True)}):
            self.assertEqual(torch_acceleration.preferred_torch_device_name(), "mps")

    def test_preferred_torch_device_name_respects_disabled_setting(self):
        with mock.patch.dict("sys.modules", {"torch": _fake_torch(mps=True, cuda=True)}):
            self.assertEqual(
                torch_acceleration.preferred_torch_device_name({"audio_torch_gpu_enabled": False}),
                "cpu",
            )

    def test_move_torch_model_to_preferred_device_moves_module(self):
        module = _FakeTo()
        with mock.patch.dict("sys.modules", {"torch": _fake_torch(mps=False, cuda=True)}):
            device = torch_acceleration.move_torch_model_to_preferred_device(module, log_label="TEST")
        self.assertEqual(device, "cuda")
        self.assertEqual(module.calls, ["cuda"])

    def test_move_torch_tensor_to_device_preserves_cpu_value(self):
        tensor = _FakeTo()
        result = torch_acceleration.move_torch_tensor_to_device(tensor, "cpu")
        self.assertIs(result, tensor)
        self.assertEqual(tensor.calls, [])

    def test_preferred_torch_device_name_falls_back_to_cpu_on_high_mps_pressure(self):
        with mock.patch.dict(
            "sys.modules",
            {
                "torch": _fake_torch(
                    mps=True,
                    cuda=False,
                    mps_allocated=920,
                    mps_driver=940,
                    mps_recommended=1000,
                )
            },
        ):
            self.assertEqual(
                torch_acceleration.preferred_torch_device_name(
                    task="vad",
                    estimated_bytes=32,
                ),
                "cpu",
            )

    def test_torch_acceleration_snapshot_reports_device_pressure(self):
        with mock.patch.dict(
            "sys.modules",
            {
                "torch": _fake_torch(
                    mps=True,
                    cuda=False,
                    mps_allocated=256,
                    mps_driver=320,
                    mps_recommended=1024,
                )
            },
        ):
            snapshot = torch_acceleration.torch_acceleration_snapshot(
                task="stt",
                estimated_bytes=64,
            )
        self.assertTrue(snapshot["enabled"])
        self.assertEqual(snapshot["primary_backend"], "mps")
        self.assertTrue(snapshot["gpu_available"])
        self.assertIn("mps", snapshot["device_snapshots"])
        self.assertGreater(snapshot["device_snapshots"]["mps"]["future_pressure_ratio"], 0.0)


if __name__ == "__main__":
    unittest.main()
