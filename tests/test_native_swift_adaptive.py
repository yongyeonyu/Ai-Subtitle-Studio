import os
import unittest
from unittest import mock

import core.native_swift_common_split as common_split
import core.native_swift_policy as swift_policy
import core.native_swift_quality as swift_quality


class NativeSwiftAdaptiveRoutingTests(unittest.TestCase):
    def test_quality_scoring_uses_swift_only_for_large_mac_batches(self):
        settings = {
            "mac_native_acceleration_enabled": True,
            "native_swift_quality_scoring_enabled": True,
            "native_swift_quality_scoring_min_segments": 64,
        }
        with mock.patch.object(swift_quality, "IS_MAC", True), mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(swift_quality._enabled(settings, 12))
            self.assertTrue(swift_quality._enabled(settings, 64))

    def test_quality_scoring_env_override_keeps_bench_switch_available(self):
        settings = {"native_swift_quality_scoring_enabled": False}
        with mock.patch.object(swift_quality, "IS_MAC", True), mock.patch.dict(
            os.environ,
            {"AI_SUBTITLE_STUDIO_SWIFT_QUALITY": "1"},
            clear=True,
        ):
            self.assertTrue(swift_quality._enabled(settings, 1))

    def test_common_split_uses_swift_only_for_large_mac_batches(self):
        settings = {
            "mac_native_acceleration_enabled": True,
            "native_swift_common_split_enabled": True,
            "native_swift_common_split_min_items": 1000,
        }
        with mock.patch.object(common_split, "IS_MAC", True), mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(common_split._enabled(256, settings))
            self.assertTrue(common_split._enabled(1000, settings))

    def test_common_split_respects_disable_flag(self):
        settings = {
            "mac_native_acceleration_enabled": True,
            "native_swift_common_split_enabled": False,
            "native_swift_common_split_min_items": 1,
        }
        with mock.patch.object(common_split, "IS_MAC", True), mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(common_split._enabled(1000, settings))

    def test_swift_policy_helpers_require_experimental_gate(self):
        settings = {"native_swift_lora_scoring_enabled": True}
        with mock.patch.object(swift_policy, "IS_MAC", True), mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(
                swift_policy._enabled(
                    settings,
                    "native_swift_lora_scoring_enabled",
                    "AI_SUBTITLE_STUDIO_SWIFT_LORA_SCORING",
                    default=False,
                )
            )

    def test_swift_policy_helpers_allow_benchmark_experimental_gate(self):
        settings = {
            "native_swift_policy_experimental_enabled": True,
            "native_swift_lora_scoring_enabled": True,
        }
        with mock.patch.object(swift_policy, "IS_MAC", True), mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(
                swift_policy._enabled(
                    settings,
                    "native_swift_lora_scoring_enabled",
                    "AI_SUBTITLE_STUDIO_SWIFT_LORA_SCORING",
                    default=False,
                )
            )

    def test_swift_policy_local_env_still_requires_experimental_gate(self):
        settings = {"native_swift_lora_scoring_enabled": True}
        with mock.patch.object(swift_policy, "IS_MAC", True), mock.patch.dict(
            os.environ,
            {"AI_SUBTITLE_STUDIO_SWIFT_LORA_SCORING": "1"},
            clear=True,
        ):
            self.assertFalse(
                swift_policy._enabled(
                    settings,
                    "native_swift_lora_scoring_enabled",
                    "AI_SUBTITLE_STUDIO_SWIFT_LORA_SCORING",
                    default=False,
                )
            )

    def test_swift_policy_local_env_allowed_with_experimental_gate(self):
        settings = {"native_swift_policy_experimental_enabled": True}
        with mock.patch.object(swift_policy, "IS_MAC", True), mock.patch.dict(
            os.environ,
            {"AI_SUBTITLE_STUDIO_SWIFT_LORA_SCORING": "1"},
            clear=True,
        ):
            self.assertTrue(
                swift_policy._enabled(
                    settings,
                    "native_swift_lora_scoring_enabled",
                    "AI_SUBTITLE_STUDIO_SWIFT_LORA_SCORING",
                    default=False,
                )
            )


if __name__ == "__main__":
    unittest.main()
