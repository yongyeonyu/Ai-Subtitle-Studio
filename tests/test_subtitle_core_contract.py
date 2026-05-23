import unittest

from core.subtitle_core_contract import (
    SUBTITLE_CORE_OPERATION_COMMON_SPLIT_PLAN,
    SUBTITLE_CORE_OPERATION_SUBTITLE_ASSEMBLY_PLAN,
    SUBTITLE_CORE_OPERATION_SUBTITLE_ASSEMBLY_QUALITY_GATE,
    SUBTITLE_CORE_OPERATION_SUBTITLE_GLOBAL_CANVAS_SUMMARY,
    SUBTITLE_CORE_OPERATION_SUBTITLE_RESOURCE_PLAN,
    SUBTITLE_CORE_OPERATION_SUBTITLE_SEGMENTS_SUMMARY,
    SUBTITLE_CORE_OPERATION_SUBTITLE_STT_SEGMENTS_SUMMARY,
    SUBTITLE_CORE_OPERATION_SUBTITLE_TIMING_METRICS,
    SUBTITLE_CORE_OPERATION_SUBTITLE_WAVEFORM_SUMMARY,
    SUBTITLE_CORE_REQUEST_SCHEMA,
    SUBTITLE_CORE_RESPONSE_SCHEMA,
    build_subtitle_core_request,
    normalize_subtitle_core_operation,
    subtitle_core_response_result,
)


class SubtitleCoreContractTests(unittest.TestCase):
    def test_build_request_normalizes_operation_and_keeps_payload_shape(self):
        request = build_subtitle_core_request(
            "common-split-plan",
            payload={"segments": [{"text": "테스트"}]},
            context={"bridge": "unit-test"},
        )

        self.assertEqual(request["schema"], SUBTITLE_CORE_REQUEST_SCHEMA)
        self.assertEqual(request["operation"], SUBTITLE_CORE_OPERATION_COMMON_SPLIT_PLAN)
        self.assertEqual(request["payload"]["segments"][0]["text"], "테스트")
        self.assertEqual(request["context"]["bridge"], "unit-test")

    def test_build_request_rejects_unknown_operation(self):
        with self.assertRaises(ValueError):
            build_subtitle_core_request("subtitle_core_generate", payload={})

    def test_response_result_requires_matching_schema_and_operation(self):
        response = {
            "schema": SUBTITLE_CORE_RESPONSE_SCHEMA,
            "operation": SUBTITLE_CORE_OPERATION_COMMON_SPLIT_PLAN,
            "result": {"plans": [{"action": "keep"}]},
        }

        self.assertEqual(
            subtitle_core_response_result(response, operation="common-split-plan"),
            {"plans": [{"action": "keep"}]},
        )
        self.assertIsNone(subtitle_core_response_result(response, operation="unknown"))

    def test_normalize_operation_maps_known_alias(self):
        self.assertEqual(
            normalize_subtitle_core_operation("common_split"),
            SUBTITLE_CORE_OPERATION_COMMON_SPLIT_PLAN,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-assembly-plan"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_ASSEMBLY_PLAN,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-assembly-quality-gate"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_ASSEMBLY_QUALITY_GATE,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-global-canvas-summary"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_GLOBAL_CANVAS_SUMMARY,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-resource-plan"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_RESOURCE_PLAN,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-segments-summary"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_SEGMENTS_SUMMARY,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-stt-segments-summary"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_STT_SEGMENTS_SUMMARY,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle_stt2_segments"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_STT_SEGMENTS_SUMMARY,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-timing-metrics"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_TIMING_METRICS,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-waveform-summary"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_WAVEFORM_SUMMARY,
        )


if __name__ == "__main__":
    unittest.main()
