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
    SUBTITLE_CORE_OPERATION_STT_LATTICE_BEST_WORD_MATCH,
    SUBTITLE_CORE_OPERATION_SUBTITLE_LORA_SELECTIVE_MERGE_INDEXES,
    SUBTITLE_CORE_OPERATION_SUBTITLE_LORA_MERGE_SETTINGS,
    SUBTITLE_CORE_OPERATION_SUBTITLE_LORA_PACKAGING_MODE,
    SUBTITLE_CORE_OPERATION_SUBTITLE_LORA_PACKAGING_CANDIDATE_SCORE,
    SUBTITLE_CORE_OPERATION_SUBTITLE_LORA_PACKAGING_REASONS,
    SUBTITLE_CORE_OPERATION_STT_DURATION_FIRST_ORDER,
    SUBTITLE_CORE_OPERATION_STT_COMPUTE_PROFILE,
    SUBTITLE_CORE_OPERATION_STT_DURATION_FIRST_SUBMISSION_ENABLED,
    SUBTITLE_CORE_OPERATION_STT_WORKER_SILENCE_TIMEOUT,
    SUBTITLE_CORE_OPERATION_STT_STRAGGLER_CONFIG,
    SUBTITLE_CORE_OPERATION_AUDIO_AI_VARIANT,
    SUBTITLE_CORE_OPERATION_AUDIO_FAST_FLATTEN_FILTER,
    SUBTITLE_CORE_OPERATION_AUDIO_ROUTE_PREVIEW_DIVERGENCE,
    SUBTITLE_CORE_OPERATION_AUDIO_ROUTE_SPLIT_DECISION,
    SUBTITLE_CORE_OPERATION_AUDIO_ROUTE_SAMPLE_SPAN,
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
        self.assertEqual(
            normalize_subtitle_core_operation("stt-lattice-best-word-match"),
            SUBTITLE_CORE_OPERATION_STT_LATTICE_BEST_WORD_MATCH,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-lora-selective-merge-indexes"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_LORA_SELECTIVE_MERGE_INDEXES,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-lora-merge-settings"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_LORA_MERGE_SETTINGS,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-lora-packaging-mode"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_LORA_PACKAGING_MODE,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-lora-packaging-candidate-score"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_LORA_PACKAGING_CANDIDATE_SCORE,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("subtitle-lora-packaging-reasons"),
            SUBTITLE_CORE_OPERATION_SUBTITLE_LORA_PACKAGING_REASONS,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("stt-duration-first-order"),
            SUBTITLE_CORE_OPERATION_STT_DURATION_FIRST_ORDER,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("stt-compute-profile"),
            SUBTITLE_CORE_OPERATION_STT_COMPUTE_PROFILE,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("stt-duration-first-submission-enabled"),
            SUBTITLE_CORE_OPERATION_STT_DURATION_FIRST_SUBMISSION_ENABLED,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("stt-worker-silence-timeout"),
            SUBTITLE_CORE_OPERATION_STT_WORKER_SILENCE_TIMEOUT,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("stt-straggler-config"),
            SUBTITLE_CORE_OPERATION_STT_STRAGGLER_CONFIG,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("audio-ai-variant"),
            SUBTITLE_CORE_OPERATION_AUDIO_AI_VARIANT,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("audio-route-preview-divergence"),
            SUBTITLE_CORE_OPERATION_AUDIO_ROUTE_PREVIEW_DIVERGENCE,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("audio-route-split-decision"),
            SUBTITLE_CORE_OPERATION_AUDIO_ROUTE_SPLIT_DECISION,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("audio-fast-flatten-filter"),
            SUBTITLE_CORE_OPERATION_AUDIO_FAST_FLATTEN_FILTER,
        )
        self.assertEqual(
            normalize_subtitle_core_operation("audio-route-sample-span"),
            SUBTITLE_CORE_OPERATION_AUDIO_ROUTE_SAMPLE_SPAN,
        )


if __name__ == "__main__":
    unittest.main()
