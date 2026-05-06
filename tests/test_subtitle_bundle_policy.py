import unittest

from core.personalization.subtitle_bundle_policy import (
    resolve_subtitle_bundle_policy,
    should_flush_subtitle_bundle,
)


class SubtitleBundlePolicyTests(unittest.TestCase):
    def test_default_policy_holds_until_target_seconds(self):
        flush, policy = should_flush_subtitle_bundle(
            60.0,
            180,
            settings={"subtitle_bundle_autopilot_enabled": True, "subtitle_bundle_target_sec": 180},
            segments=[{"start": 0.0, "end": 60.0, "text": "테스트"}],
        )

        self.assertFalse(flush)
        self.assertEqual(policy["reason"], "hold")

    def test_default_policy_flushes_at_target_seconds(self):
        flush, policy = should_flush_subtitle_bundle(
            181.0,
            180,
            settings={"subtitle_bundle_autopilot_enabled": True, "subtitle_bundle_target_sec": 180},
            segments=[{"start": 0.0, "end": 181.0, "text": "테스트"}],
        )

        self.assertTrue(flush)
        self.assertEqual(policy["reason"], "target_sec")

    def test_confirmed_cut_boundary_can_flush_before_target(self):
        flush, policy = should_flush_subtitle_bundle(
            50.0,
            180,
            settings={
                "subtitle_bundle_autopilot_enabled": True,
                "subtitle_bundle_target_sec": 180,
                "subtitle_bundle_confirmed_cut_min_sec": 45,
            },
            segments=[{"start": 0.0, "end": 50.0, "text": "테스트"}],
            cut_boundaries=[{"timeline_sec": 49.2}],
        )

        self.assertTrue(flush)
        self.assertEqual(policy["reason"], "confirmed_cut")

    def test_provisional_cut_boundary_waits_for_safer_minimum(self):
        early_flush, early_policy = should_flush_subtitle_bundle(
            70.0,
            180,
            settings={
                "subtitle_bundle_autopilot_enabled": True,
                "subtitle_bundle_target_sec": 180,
                "subtitle_bundle_provisional_cut_min_sec": 120,
            },
            segments=[{"start": 0.0, "end": 70.0, "text": "테스트"}],
            provisional_cut_boundaries=[{"timeline_sec": 69.5}],
        )
        late_flush, late_policy = should_flush_subtitle_bundle(
            125.0,
            180,
            settings={
                "subtitle_bundle_autopilot_enabled": True,
                "subtitle_bundle_target_sec": 180,
                "subtitle_bundle_provisional_cut_min_sec": 120,
            },
            segments=[{"start": 0.0, "end": 125.0, "text": "테스트"}],
            provisional_cut_boundaries=[{"timeline_sec": 124.0}],
        )

        self.assertFalse(early_flush)
        self.assertEqual(early_policy["reason"], "hold")
        self.assertTrue(late_flush)
        self.assertEqual(late_policy["reason"], "provisional_cut")

    def test_lora_bundle_settings_blend_into_target(self):
        policy = resolve_subtitle_bundle_policy(
            {
                "subtitle_bundle_autopilot_enabled": True,
                "subtitle_bundle_target_sec": 180,
                "subtitle_bundle_lora_blend": 0.5,
            },
            segments=[
                {
                    "start": 0.0,
                    "end": 60.0,
                    "text": "테스트",
                    "_lora_segment_settings": {"chunk_time_limit": 240},
                }
            ],
        )

        self.assertEqual(policy["target_sec"], 210.0)
        self.assertEqual(policy["lora_values"], [240.0])

    def test_manual_mode_keeps_legacy_slider_limit(self):
        flush, policy = should_flush_subtitle_bundle(
            59.0,
            60,
            settings={"subtitle_bundle_autopilot_enabled": False, "chunk_time_limit": 60},
        )
        self.assertFalse(flush)

        flush, policy = should_flush_subtitle_bundle(
            60.0,
            60,
            settings={"subtitle_bundle_autopilot_enabled": False, "chunk_time_limit": 60},
        )
        self.assertTrue(flush)
        self.assertEqual(policy["reason"], "manual_limit")


if __name__ == "__main__":
    unittest.main()
