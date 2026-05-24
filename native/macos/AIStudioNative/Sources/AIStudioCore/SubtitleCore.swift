import Foundation

public enum SubtitleCoreNative {
    public static let requestSchema = "ai_subtitle_studio.subtitle_core.request.v1"
    public static let responseSchema = "ai_subtitle_studio.subtitle_core.response.v1"

    public static func plan(payload: [String: Any]) -> [String: Any] {
        let operation = stringValue(payload["operation"]).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !operation.isEmpty else {
            return errorResponse(operation: "", message: "Missing subtitle core operation")
        }

        let schema = stringValue(payload["schema"]).trimmingCharacters(in: .whitespacesAndNewlines)
        if !schema.isEmpty && schema != requestSchema {
            return errorResponse(operation: operation, message: "Unsupported subtitle core schema: \(schema)")
        }

        let requestPayload = payload["payload"] as? [String: Any] ?? [:]
        switch operation {
        case "common_split_plan":
            return commonSplitPlanResponse(payload: requestPayload, operation: operation)
        case "subtitle_assembly_plan":
            return subtitleAssemblyPlanResponse(payload: requestPayload, operation: operation)
        case "subtitle_assembly_quality_gate":
            return subtitleAssemblyQualityGateResponse(payload: requestPayload, operation: operation)
        case "subtitle_llm_context_plan":
            return subtitleLLMContextPlanResponse(payload: requestPayload, operation: operation)
        case "subtitle_llm_context_gate":
            return subtitleLLMContextGateResponse(payload: requestPayload, operation: operation)
        case "subtitle_global_canvas_summary":
            return subtitleGlobalCanvasSummaryResponse(payload: requestPayload, operation: operation)
        case "subtitle_resource_plan":
            return subtitleResourcePlanResponse(payload: requestPayload, operation: operation)
        case "subtitle_segments_summary":
            return subtitleSegmentsSummaryResponse(payload: requestPayload, operation: operation)
        case "subtitle_stt_segments_summary":
            return subtitleSTTSegmentsSummaryResponse(payload: requestPayload, operation: operation)
        case "subtitle_timing_metrics":
            return subtitleTimingMetricsResponse(payload: requestPayload, operation: operation)
        case "subtitle_waveform_summary":
            return subtitleWaveformSummaryResponse(payload: requestPayload, operation: operation)
        case "stt_lattice_best_word_match":
            return sttLatticeBestWordMatchResponse(payload: requestPayload, operation: operation)
        case "subtitle_lora_selective_merge_indexes":
            return subtitleLoraSelectiveMergeResponse(payload: requestPayload, operation: operation)
        case "subtitle_lora_merge_settings":
            return subtitleLoraMergeSettingsResponse(payload: requestPayload, operation: operation)
        case "subtitle_lora_packaging_mode":
            return subtitleLoraPackagingModeResponse(payload: requestPayload, operation: operation)
        case "subtitle_lora_packaging_candidate_score":
            return subtitleLoraPackagingCandidateScoreResponse(payload: requestPayload, operation: operation)
        case "subtitle_lora_packaging_reasons":
            return subtitleLoraPackagingReasonsResponse(payload: requestPayload, operation: operation)
        case "stt_duration_first_order":
            return sttDurationFirstOrderResponse(payload: requestPayload, operation: operation)
        case "stt_compute_profile":
            return sttComputeProfileResponse(payload: requestPayload, operation: operation)
        case "stt_duration_first_submission_enabled":
            return sttDurationFirstSubmissionEnabledResponse(payload: requestPayload, operation: operation)
        case "stt_worker_silence_timeout":
            return sttWorkerSilenceTimeoutResponse(payload: requestPayload, operation: operation)
        case "stt_straggler_config":
            return sttStragglerConfigResponse(payload: requestPayload, operation: operation)
        case "audio_fast_flatten_filter":
            return audioFastFlattenFilterResponse(payload: requestPayload, operation: operation)
        case "audio_route_sample_span":
            return audioRouteSampleSpanResponse(payload: requestPayload, operation: operation)
        case "audio_ai_variant":
            return audioAIVariantResponse(payload: requestPayload, operation: operation)
        case "audio_route_preview_divergence":
            return audioRoutePreviewDivergenceResponse(payload: requestPayload, operation: operation)
        case "audio_route_split_decision":
            return audioRouteSplitDecisionResponse(payload: requestPayload, operation: operation)
        default:
            return errorResponse(operation: operation, message: "Unsupported subtitle core operation: \(operation)")
        }
    }

    private static func commonSplitPlanResponse(payload: [String: Any], operation: String) -> [String: Any] {
        do {
            guard JSONSerialization.isValidJSONObject(payload) else {
                return errorResponse(operation: operation, message: "Invalid subtitle core payload")
            }
            let data = try JSONSerialization.data(withJSONObject: payload, options: [])
            let request = try JSONDecoder().decode(CommonSplitPlanRequest.self, from: data)
            let response = CommonSplitPlanner.plan(request)
            return [
                "schema": responseSchema,
                "operation": operation,
                "backend": "swift",
                "result": try jsonObject(from: response),
            ]
        } catch {
            let message = String(describing: error).replacingOccurrences(of: "\n", with: " ")
            return errorResponse(operation: operation, message: message)
        }
    }

    private static func subtitleAssemblyPlanResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleAssemblyPlanner.plan(payload: payload),
        ]
    }

    private static func subtitleAssemblyQualityGateResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleAssemblyQualityGate.evaluate(payload: payload),
        ]
    }

    private static func subtitleLLMContextPlanResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleLLMContextPolicy.plan(payload: payload),
        ]
    }

    private static func subtitleLLMContextGateResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleLLMContextPolicy.gate(payload: payload),
        ]
    }

    private static func subtitleGlobalCanvasSummaryResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleGlobalCanvasSummaryNative.evaluate(payload: payload),
        ]
    }

    private static func subtitleResourcePlanResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleResourcePlanNative.evaluate(payload: payload),
        ]
    }

    private static func subtitleSegmentsSummaryResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleSegmentsSummaryNative.evaluate(payload: payload),
        ]
    }

    private static func subtitleSTTSegmentsSummaryResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleSTTSegmentsSummaryNative.evaluate(payload: payload),
        ]
    }

    private static func subtitleTimingMetricsResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleTimingMetricsNative.evaluate(payload: payload),
        ]
    }

    private static func subtitleWaveformSummaryResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleWaveformSummaryNative.evaluate(payload: payload),
        ]
    }

    private static func sttLatticeBestWordMatchResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": STTLatticeMatchNative.evaluate(payload: payload),
        ]
    }

    private static func subtitleLoraSelectiveMergeResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleLoraSelectiveMergeNative.evaluate(payload: payload),
        ]
    }

    private static func subtitleLoraMergeSettingsResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleLoraSelectiveMergeNative.mergeSettings(payload: payload),
        ]
    }

    private static func subtitleLoraPackagingModeResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleLoraSelectiveMergeNative.packagingMode(payload: payload),
        ]
    }

    private static func subtitleLoraPackagingCandidateScoreResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleLoraSelectiveMergeNative.packagingCandidateScore(payload: payload),
        ]
    }

    private static func subtitleLoraPackagingReasonsResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": SubtitleLoraSelectiveMergeNative.packagingReasons(payload: payload),
        ]
    }

    private static func sttDurationFirstOrderResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": STTDurationFirstOrderNative.evaluate(payload: payload),
        ]
    }

    private static func sttComputeProfileResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": STTDurationFirstOrderNative.computeProfile(payload: payload),
        ]
    }

    private static func sttDurationFirstSubmissionEnabledResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": STTDurationFirstOrderNative.submissionEnabled(payload: payload),
        ]
    }

    private static func sttWorkerSilenceTimeoutResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": STTDurationFirstOrderNative.workerSilenceTimeout(payload: payload),
        ]
    }

    private static func sttStragglerConfigResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": STTDurationFirstOrderNative.stragglerConfig(payload: payload),
        ]
    }

    private static func audioFastFlattenFilterResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": AudioFastFlattenFilterNative.evaluate(payload: payload),
        ]
    }

    private static func audioRouteSampleSpanResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": AudioFastFlattenFilterNative.sampleSpan(payload: payload),
        ]
    }

    private static func audioAIVariantResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": AudioFastFlattenFilterNative.audioAIVariant(payload: payload),
        ]
    }

    private static func audioRoutePreviewDivergenceResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": AudioFastFlattenFilterNative.routePreviewDivergence(payload: payload),
        ]
    }

    private static func audioRouteSplitDecisionResponse(payload: [String: Any], operation: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "backend": "swift",
            "result": AudioFastFlattenFilterNative.routeSplitDecision(payload: payload),
        ]
    }

    private static func errorResponse(operation: String, message: String) -> [String: Any] {
        [
            "schema": responseSchema,
            "operation": operation,
            "error": message,
        ]
    }

    private static func stringValue(_ value: Any?) -> String {
        guard let value else {
            return ""
        }
        return String(describing: value)
    }

    private static func jsonObject<T: Encodable>(from value: T) throws -> Any {
        let data = try JSONEncoder().encode(value)
        return try JSONSerialization.jsonObject(with: data, options: [])
    }
}
