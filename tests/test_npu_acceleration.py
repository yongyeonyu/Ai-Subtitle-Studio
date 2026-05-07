import unittest
from unittest.mock import patch

from core.audio.npu_acceleration import prefer_npu_whisper_model, whisper_model_npu_target


class NpuAccelerationTests(unittest.TestCase):
    def test_large_v3_family_maps_to_coreml_target(self):
        self.assertEqual(
            whisper_model_npu_target("mlx-community/whisper-large-v3-mlx"),
            "coreml:large-v3-v20240930_626MB",
        )
        self.assertEqual(
            whisper_model_npu_target("large-v3"),
            "coreml:large-v3-v20240930_626MB",
        )

    def test_prefer_npu_keeps_unsupported_models(self):
        with patch("core.audio.npu_acceleration.config.IS_MAC", True):
            routed = prefer_npu_whisper_model(
                "youngouk/ghost613-turbo-korean-4bit-mlx",
                {"runtime_npu_acceleration_enabled": True, "stt_npu_prefer_enabled": True},
                emit_log=False,
            )
        self.assertEqual(routed, "youngouk/ghost613-turbo-korean-4bit-mlx")

    def test_prefer_npu_routes_supported_model_when_coreml_runtime_exists(self):
        with patch("core.audio.npu_acceleration.config.IS_MAC", True), \
             patch("core.audio.npu_acceleration.apple_neural_engine_available", return_value=True):
            routed = prefer_npu_whisper_model(
                "mlx-community/whisper-large-v3-mlx",
                {"runtime_npu_acceleration_enabled": True, "stt_npu_prefer_enabled": True},
                emit_log=False,
            )
        self.assertEqual(routed, "coreml:large-v3-v20240930_626MB")

    def test_prefer_npu_can_be_disabled_in_settings(self):
        with patch("core.audio.npu_acceleration.config.IS_MAC", True), \
             patch("core.audio.npu_acceleration.apple_neural_engine_available", return_value=True):
            routed = prefer_npu_whisper_model(
                "mlx-community/whisper-large-v3-mlx",
                {"runtime_npu_acceleration_enabled": False, "stt_npu_prefer_enabled": True},
                emit_log=False,
            )
        self.assertEqual(routed, "mlx-community/whisper-large-v3-mlx")


if __name__ == "__main__":
    unittest.main()
