import XCTest
@testable import AIStudioCore

final class SubtitleCoreTests: XCTestCase {
    func testSubtitleCoreCommonSplitPlanWrapsPlannerResponse() throws {
        let payload: [String: Any] = [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "common_split_plan",
            "payload": [
                "segments": [
                    [
                        "start": 0.0,
                        "end": 8.0,
                        "text": "여기 안에 들어가 있는 것도 똑같고 저기 방향제도 똑같고 이번에는 동일한 차를 그냥 2대를 만드셨네",
                        "words": [
                            ["word": "여기", "start": 0.0, "end": 0.7],
                            ["word": "안에", "start": 0.7, "end": 1.4],
                            ["word": "들어가", "start": 1.4, "end": 2.1],
                            ["word": "있는", "start": 2.1, "end": 2.8],
                            ["word": "것도", "start": 2.8, "end": 3.5],
                            ["word": "똑같고", "start": 3.5, "end": 4.2],
                            ["word": "저기", "start": 4.2, "end": 4.9],
                            ["word": "방향제도", "start": 4.9, "end": 5.6],
                            ["word": "똑같고", "start": 5.6, "end": 6.3],
                            ["word": "이번에는", "start": 6.3, "end": 7.0],
                            ["word": "동일한", "start": 7.0, "end": 7.5],
                            ["word": "차를", "start": 7.5, "end": 8.0],
                        ],
                        "policy": [
                            "enabled": true,
                            "target_chars": 16,
                            "hard_chars": 24,
                            "hard_duration": 5.5,
                            "min_duration": 0.2,
                        ],
                    ],
                ],
            ],
        ]

        let response = SubtitleCoreNative.plan(payload: payload)
        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "common_split_plan")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        let plans = try XCTUnwrap(result["plans"] as? [[String: Any]])
        XCTAssertEqual(plans.count, 1)
        XCTAssertEqual(plans.first?["action"] as? String, "split")
    }

    func testSubtitleCoreRejectsUnknownOperation() {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "unknown_operation",
            "payload": [:],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "unknown_operation")
        XCTAssertNotNil(response["error"] as? String)
    }

    func testSubtitleCoreAssemblyPlanWrapsSwiftPlannerResponse() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_assembly_plan",
            "payload": [
                "candidate_variant": "mode_swift_assembled",
                "quality_baseline_variants": ["mode_fast", "mode_auto", "mode_high"],
                "available_variants": [
                    ["name": "mode_fast"],
                    ["name": "mode_auto"],
                    ["name": "mode_high"],
                    ["name": "mode_high_full_core_overlap"],
                ],
            ],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "subtitle_assembly_plan")
        XCTAssertEqual(response["backend"] as? String, "swift")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_assembly.plan.v1")
        XCTAssertEqual(result["candidate_variant"] as? String, "mode_swift_assembled")
        XCTAssertEqual(result["source_variant"] as? String, "mode_high_full_core_overlap")
        let qualityFloor = try XCTUnwrap(result["quality_floor"] as? [String: Any])
        XCTAssertEqual(qualityFloor["baseline_variants"] as? [String], ["mode_fast", "mode_auto", "mode_high"])
        let settings = try XCTUnwrap(result["settings_overrides"] as? [String: Any])
        XCTAssertEqual(settings["native_subtitle_assembly_enabled"] as? Bool, true)
        XCTAssertEqual(settings["native_subtitle_assembly_quality_floor"] as? String, "best_fast_auto_high")
        XCTAssertEqual(settings["stt_accelerator_distribution"] as? String, "gpu+npu+cpu")
        XCTAssertEqual(settings["stt_word_timestamps_precision_max_segments"] as? Int, 48)
    }

    func testSubtitleCoreResourcePlanSummarizesANEAndMetalRoutes() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_resource_plan",
            "payload": [
                "active_labels": ["pipeline", "stt", "subtitle_optimize"],
                "settings": [
                    "benchmark_runtime_profile": "apple_m_full_core_throughput",
                ],
                "topology": [
                    "logical_cores": 10,
                    "physical_cores": 10,
                    "performance_cores": 4,
                    "efficiency_cores": 6,
                    "gpu_cores": 10,
                    "neural_engine_cores": 16,
                    "memory_bytes": 16 * 1_073_741_824,
                ],
                "memory": [
                    "memory_bytes": 16 * 1_073_741_824,
                    "available_memory_bytes": 6 * 1_073_741_824,
                    "available_memory_ratio": 0.375,
                    "pressure_stage": "normal",
                ],
            ],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "subtitle_resource_plan")
        XCTAssertEqual(response["backend"] as? String, "swift")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_resource.plan.v1")
        let summary = try XCTUnwrap(result["accelerator_summary"] as? [String: Any])
        XCTAssertEqual(summary["metal_claims_ane"] as? Bool, false)
        XCTAssertGreaterThan(try XCTUnwrap(summary["gpu_task_count"] as? Int), 0)
        XCTAssertGreaterThan(try XCTUnwrap(summary["ane_task_count"] as? Int), 0)
        XCTAssertGreaterThan(try XCTUnwrap(summary["metal_task_count"] as? Int), 0)
        let aneTasks = try XCTUnwrap(summary["ane_tasks"] as? [String])
        let metalTasks = try XCTUnwrap(summary["metal_tasks"] as? [String])
        XCTAssertTrue(aneTasks.contains("stt_precision"))
        XCTAssertTrue(metalTasks.contains("vad"))
    }

    func testSubtitleCoreSegmentsSummaryReportsSaveReopenInvariants() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_segments_summary",
            "payload": [
                "segments": [
                    ["start": 0.0, "end": 1.0, "text": "첫 문장"],
                    ["start": 0.9, "end": 2.0, "text": ""],
                    ["start": 1.8, "end": 1.7, "text": "잘못된 길이"],
                    ["start": 1.6, "end": 2.4, "text": "역순"],
                ],
            ],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "subtitle_segments_summary")
        XCTAssertEqual(response["backend"] as? String, "swift")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_segments.summary.v1")
        XCTAssertEqual(result["segment_count"] as? Int, 4)
        XCTAssertEqual(result["invalid_duration_count"] as? Int, 1)
        XCTAssertEqual(result["non_monotonic_count"] as? Int, 1)
        XCTAssertEqual(result["overlap_count"] as? Int, 3)
        XCTAssertEqual(result["empty_text_count"] as? Int, 1)
        XCTAssertEqual(result["stable_for_save_reopen"] as? Bool, false)
        let accelerator = try XCTUnwrap(result["accelerator_summary"] as? [String: Any])
        XCTAssertEqual(accelerator["metal_claims_ane"] as? Bool, false)
        XCTAssertEqual(accelerator["ane_task_count"] as? Int, 0)
    }

    func testSubtitleCoreSTTSegmentsSummaryReportsSTT2LaneUse() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_stt_segments_summary",
            "payload": [
                "segments": [
                    ["start": 0.0, "end": 1.0, "text": "첫 문장", "stt_selected_source": "STT1"],
                    [
                        "start": 1.1,
                        "end": 2.0,
                        "text": "두 번째",
                        "stt_selected_source": "STT2",
                        "stt_recheck_applied": true,
                    ],
                    [
                        "start": 2.1,
                        "end": 2.8,
                        "text": "세 번째",
                        "stt_ensemble_source": "STT2_SELECTIVE_RECHECK",
                        "stt_word_precision_applied": true,
                    ],
                ],
            ],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "subtitle_stt_segments_summary")
        XCTAssertEqual(response["backend"] as? String, "swift")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_stt_segments.summary.v1")
        XCTAssertEqual(result["segment_count"] as? Int, 3)
        XCTAssertEqual(result["stt1_selected_count"] as? Int, 1)
        XCTAssertEqual(result["stt2_selected_count"] as? Int, 2)
        XCTAssertEqual(result["recheck_applied_count"] as? Int, 1)
        XCTAssertEqual(result["word_precision_count"] as? Int, 1)
        XCTAssertEqual(result["stt2_active"] as? Bool, true)
        XCTAssertEqual(result["selective_recheck_active"] as? Bool, true)
        XCTAssertEqual(result["stable_for_timeline_feed"] as? Bool, true)
        let accelerator = try XCTUnwrap(result["accelerator_summary"] as? [String: Any])
        XCTAssertEqual(accelerator["metal_claims_ane"] as? Bool, false)
        XCTAssertEqual(accelerator["ane_task_count"] as? Int, 0)
    }

    func testSubtitleCoreGlobalCanvasSummaryReportsOccupancyAndGaps() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_global_canvas_summary",
            "payload": [
                "duration": 4.0,
                "bin_count": 4,
                "segments": [
                    ["start": 0.0, "end": 1.0, "text": "A"],
                    ["start": 0.5, "end": 1.5, "text": "B"],
                    ["start": 3.0, "end": 4.0, "text": "C"],
                    ["start": 2.0, "end": 2.0, "text": "invalid"],
                ],
            ],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "subtitle_global_canvas_summary")
        XCTAssertEqual(response["backend"] as? String, "swift")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_global_canvas.summary.v1")
        XCTAssertEqual(result["segment_count"] as? Int, 4)
        XCTAssertEqual(result["valid_segment_count"] as? Int, 3)
        XCTAssertEqual(result["invalid_duration_count"] as? Int, 1)
        XCTAssertEqual(result["occupied_bin_count"] as? Int, 3)
        XCTAssertEqual(result["dense_bin_count"] as? Int, 1)
        XCTAssertEqual(result["max_active_segments"] as? Int, 2)
        let coverageRatio = try XCTUnwrap(result["coverage_ratio"] as? Double)
        let longestGap = try XCTUnwrap(result["longest_empty_span_sec"] as? Double)
        XCTAssertEqual(coverageRatio, 0.625, accuracy: 0.000001)
        XCTAssertEqual(longestGap, 1.5, accuracy: 0.000001)
        XCTAssertEqual(result["stable_for_global_canvas"] as? Bool, false)
        let accelerator = try XCTUnwrap(result["accelerator_summary"] as? [String: Any])
        XCTAssertEqual(accelerator["metal_claims_ane"] as? Bool, false)
        XCTAssertEqual(accelerator["ane_task_count"] as? Int, 0)
    }

    func testSubtitleCoreAssemblyQualityGateRequiresCandidateNotBelowBestMode() throws {
        let failed = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_assembly_quality_gate",
            "payload": [
                "candidate_variant": "mode_swift_assembled",
                "baseline_variants": ["mode_fast", "mode_auto", "mode_high"],
                "ranked_results": [
                    ["name": "mode_fast", "quality": ["quality_score": 75.0]],
                    ["name": "mode_auto", "quality": ["quality_score": 80.0]],
                    ["name": "mode_high", "quality": ["quality_score": 87.0]],
                    ["name": "mode_swift_assembled", "quality": ["quality_score": 86.999]],
                ],
            ],
        ])
        let failedResult = try XCTUnwrap(failed["result"] as? [String: Any])
        XCTAssertEqual(failedResult["passed"] as? Bool, false)
        XCTAssertEqual(failedResult["reason"] as? String, "quality_score_below_best_fast_auto_high")
        XCTAssertEqual(failedResult["baseline_variant"] as? String, "mode_high")

        let passed = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_assembly_quality_gate",
            "payload": [
                "candidate_variant": "mode_swift_assembled",
                "baseline_variants": ["mode_fast", "mode_auto", "mode_high"],
                "ranked_results": [
                    ["name": "mode_fast", "quality": ["quality_score": 75.0]],
                    ["name": "mode_auto", "quality": ["quality_score": 80.0]],
                    ["name": "mode_high", "quality": ["quality_score": 87.0]],
                    ["name": "mode_swift_assembled", "quality": ["quality_score": 87.0]],
                ],
            ],
        ])
        let passedResult = try XCTUnwrap(passed["result"] as? [String: Any])
        XCTAssertEqual(passedResult["passed"] as? Bool, true)
        XCTAssertEqual(passedResult["reason"] as? String, "candidate_not_below_best_fast_auto_high")
    }

    func testSubtitleCoreLLMContextPlanIncludesPreviousCurrentNextAndVAD() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_llm_context_plan",
            "payload": [
                "segments": [
                    ["start": 90.0, "end": 92.0, "text": "아까 뭐래", "stt_selected_source": "STT1"],
                    [
                        "start": 94.9,
                        "end": 99.5,
                        "text": "커피지와 같이 여기 맞는데 아 가자",
                        "stt_selected_source": "STT1",
                        "stt_candidates": [
                            ["source": "STT1", "text": "커피지와 같이 여기 맞는데 아 가자"],
                            ["source": "STT2", "text": "커피지와 같이 여기 맞는데 가자"],
                        ],
                    ],
                    ["start": 100.0, "end": 102.0, "text": "그냥 가져가", "stt_selected_source": "STT2"],
                ],
                "vad_segments": [["start": 94.8, "end": 99.7]],
            ],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "subtitle_llm_context_plan")
        XCTAssertEqual(response["backend"] as? String, "swift")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_llm_context_pack.v1")
        let packs = try XCTUnwrap(result["packs"] as? [[String: Any]])
        XCTAssertEqual(packs.count, 3)
        let pack = packs[1]
        let window = try XCTUnwrap(pack["window"] as? [String: Any])
        XCTAssertEqual((window["previous"] as? [String: Any])?["text"] as? String, "아까 뭐래")
        XCTAssertEqual((window["current"] as? [String: Any])?["selected_source"] as? String, "STT1")
        XCTAssertEqual((window["next"] as? [String: Any])?["text"] as? String, "그냥 가져가")
        let vad = try XCTUnwrap(pack["vad"] as? [String: Any])
        XCTAssertEqual(try XCTUnwrap(vad["speech_overlap_ratio"] as? Double), 1.0, accuracy: 0.000001)
    }

    func testSubtitleCoreLLMContextGateRejectsNeighborTakeover() throws {
        let contextResponse = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_llm_context_plan",
            "payload": [
                "segments": [
                    ["start": 90.0, "end": 92.0, "text": "아까 뭐래 네 커피지인데 어 어디"],
                    ["start": 94.9, "end": 99.5, "text": "커피지와 같이 여기 맞는데 아 가자"],
                    ["start": 100.0, "end": 102.0, "text": "그냥 가져가"],
                ],
            ],
        ])
        let contextResult = try XCTUnwrap(contextResponse["result"] as? [String: Any])
        let packs = try XCTUnwrap(contextResult["packs"] as? [[String: Any]])
        let currentPack = packs[1]

        let rejected = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_llm_context_gate",
            "payload": [
                "source_text": "커피지와 같이 여기 맞는데 아 가자",
                "chunks": ["아까 뭐래 네 커피지인데 어 어디"],
                "context_pack": currentPack,
            ],
        ])
        let rejectedResult = try XCTUnwrap(rejected["result"] as? [String: Any])
        XCTAssertEqual(rejectedResult["accepted"] as? Bool, false)
        XCTAssertEqual(rejectedResult["reason"] as? String, "neighbor_context_takeover")

        let accepted = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_llm_context_gate",
            "payload": [
                "source_text": "커피지와 같이 여기 맞는데 아 가자",
                "chunks": ["커피지와 같이 여기 맞는데 아 가자"],
                "context_pack": currentPack,
            ],
        ])
        let acceptedResult = try XCTUnwrap(accepted["result"] as? [String: Any])
        XCTAssertEqual(acceptedResult["accepted"] as? Bool, true)
        XCTAssertEqual(acceptedResult["reason"] as? String, "stt_vad_context_supported")
    }

    func testSubtitleCoreTimingMetricsMatchesPythonBenchmarkPairing() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_timing_metrics",
            "payload": [
                "hypothesis": [
                    ["start": 0.1, "end": 1.1, "text": "첫 문장"],
                    ["start": 2.2, "end": 3.1, "text": "두 번째"],
                ],
                "reference": [
                    ["start": 0.0, "end": 1.0, "text": "첫 문장"],
                    ["start": 2.0, "end": 3.0, "text": "두 번째"],
                ],
            ],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["backend"] as? String, "swift")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_timing.metrics.v1")
        XCTAssertEqual(result["matched_pairs"] as? Int, 2)
        let timingMAE = try XCTUnwrap(result["timing_mae_sec"] as? Double)
        let overlapScore = try XCTUnwrap(result["overlap_score"] as? Double)
        XCTAssertEqual(timingMAE, 0.125, accuracy: 0.000001)
        XCTAssertEqual(overlapScore, 85.0, accuracy: 0.000001)
    }

    func testSubtitleCoreWaveformSummaryKeepsANEAndMetalClaimsExplicit() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_waveform_summary",
            "payload": [
                "waveform": [0.0, 0.25, -1.0, 0.01],
                "duration": 1.0,
                "speech_threshold": 0.02,
            ],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "subtitle_waveform_summary")
        XCTAssertEqual(response["backend"] as? String, "swift")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_waveform.summary.v1")
        XCTAssertEqual(result["sample_count"] as? Int, 4)
        XCTAssertEqual(result["speech_like_count"] as? Int, 2)
        let maxPeak = try XCTUnwrap(result["max_peak"] as? Double)
        let speechRatio = try XCTUnwrap(result["speech_like_ratio"] as? Double)
        XCTAssertEqual(maxPeak, 1.0, accuracy: 0.000001)
        XCTAssertEqual(speechRatio, 0.5, accuracy: 0.000001)
        let accelerator = try XCTUnwrap(result["accelerator_summary"] as? [String: Any])
        XCTAssertEqual(accelerator["metal_claims_ane"] as? Bool, false)
        XCTAssertEqual(accelerator["ane_task_count"] as? Int, 0)
    }
}
