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
                    "stt_selective_secondary_recheck_enabled": true,
                    "stt_whisperkit_recheck_concurrent_workers": 8,
                    "stt_whisperkit_recheck_concurrent_max_workers": 10,
                    "stt_whisperkit_gpu_saturation_max_workers": 10,
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
        XCTAssertTrue(aneTasks.contains("stt2"))
        XCTAssertTrue(metalTasks.contains("vad"))
        XCTAssertGreaterThanOrEqual(try XCTUnwrap(summary["max_ane_lanes"] as? Int), 10)
        XCTAssertEqual(summary["gpu_lane_capacity"] as? Int, 10)
        XCTAssertEqual(summary["ane_model_lane_capacity"] as? Int, 10)
        XCTAssertEqual(summary["gpu_lane_peak_ratio"] as? Double ?? -1.0, 1.0, accuracy: 0.000_001)
        XCTAssertEqual(summary["ane_model_lane_peak_ratio"] as? Double ?? -1.0, 1.0, accuracy: 0.000_001)
        XCTAssertGreaterThanOrEqual(try XCTUnwrap(summary["full_gpu_lane_task_count"] as? Int), 1)
        XCTAssertGreaterThanOrEqual(try XCTUnwrap(summary["full_ane_model_lane_task_count"] as? Int), 1)
        XCTAssertEqual(summary["gpu_lane_peak_saturated"] as? Bool, true)
        XCTAssertEqual(summary["ane_model_lane_peak_saturated"] as? Bool, true)
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
        let maxOverlap = try XCTUnwrap(result["max_overlap"] as? Double)
        XCTAssertEqual(maxOverlap, 0.2, accuracy: 0.000001)
        XCTAssertEqual(result["max_overlap_index"] as? Int, 2)
        XCTAssertEqual(result["max_gap_index"] as? Int, -1)
        XCTAssertEqual(result["stable_for_save_reopen"] as? Bool, false)
        let signature = try XCTUnwrap(result["segment_feed_signature"] as? String)
        XCTAssertEqual(signature.count, 16)
        XCTAssertEqual(signature, "f7561398dbe42cf2")
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
        XCTAssertEqual(result["stt2_first_start"] as? Double ?? -1.0, 1.1, accuracy: 0.000_001)
        XCTAssertEqual(result["stt2_last_end"] as? Double ?? -1.0, 2.8, accuracy: 0.000_001)
        XCTAssertEqual(result["longest_stt2_run_sec"] as? Double ?? -1.0, 1.7, accuracy: 0.000_001)
        XCTAssertEqual(result["longest_stt2_run_start"] as? Double ?? -1.0, 1.1, accuracy: 0.000_001)
        XCTAssertEqual(result["longest_stt2_run_end"] as? Double ?? -1.0, 2.8, accuracy: 0.000_001)
        XCTAssertEqual(result["longest_stt2_run_count"] as? Int, 2)
        XCTAssertEqual(result["stt2_active"] as? Bool, true)
        XCTAssertEqual(result["selective_recheck_active"] as? Bool, true)
        XCTAssertEqual(result["stable_for_timeline_feed"] as? Bool, true)
        let signature = try XCTUnwrap(result["timeline_feed_signature"] as? String)
        XCTAssertEqual(signature.count, 16)
        XCTAssertEqual(signature, "7968feb0964ebf10")
        let accelerator = try XCTUnwrap(result["accelerator_summary"] as? [String: Any])
        XCTAssertEqual(accelerator["metal_claims_ane"] as? Bool, false)
        XCTAssertEqual(accelerator["ane_task_count"] as? Int, 0)
    }

    func testSubtitleCoreSTTLatticeBestWordMatchKeepsCppParityContract() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "stt_lattice_best_word_match",
            "payload": [
                "anchor_start": 1.0,
                "anchor_end": 2.0,
                "word_starts": [0.0, 1.1, 2.4],
                "word_ends": [0.4, 1.9, 2.8],
                "textual_scores": [1.0, 0.8, 1.0],
                "used_indices": [0],
                "min_match_score": 0.1,
            ],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "stt_lattice_best_word_match")
        XCTAssertEqual(response["backend"] as? String, "swift")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.stt_lattice.match.v1")
        XCTAssertEqual(result["backend"] as? String, "swift")
        XCTAssertEqual(result["best_index"] as? Int, 1)
        XCTAssertEqual(result["best_score"] as? Double ?? -1.0, 0.8, accuracy: 0.000_001)
        XCTAssertEqual(result["accepted"] as? Bool, true)
        XCTAssertEqual(result["candidate_count"] as? Int, 3)
        XCTAssertEqual(result["used_count"] as? Int, 1)
    }

    func testSubtitleCoreLoraSelectiveMergeIndexesMatchesPythonPolicyShape() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_lora_selective_merge_indexes",
            "payload": [
                "rows": [
                    ["start": 0.0, "end": 2.0, "text": "깨끗한 문장입니다"],
                    ["start": 2.1, "end": 2.35, "text": "왜?", "quality": ["confidence_label": "yellow"]],
                    ["start": 2.5, "end": 3.2, "text": "다음 문장입니다"],
                ],
                "settings": ["sub_max_cps": 12, "subtitle_lora_selective_quality_max_score": 82.0],
                "merge_settings": ["split_length_threshold": 20, "sub_min_duration": 0.8],
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "subtitle_lora_selective_merge_indexes")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_lora.selective_merge.v1")
        XCTAssertEqual(result["selected_indexes"] as? [Int], [0, 1, 2])
        let reasons = try XCTUnwrap(result["reasons_map"] as? [String: [String]])
        XCTAssertEqual(reasons["1"], ["micro_fragment", "quality_yellow"])
    }

    func testSubtitleCoreLoraMergeSettingsMatchesPythonBounds() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_lora_merge_settings",
            "payload": [
                "settings": [
                    "subtitle_lora_split_floor_chars": 18,
                    "split_length_threshold": 20,
                    "sub_min_duration": 0.3,
                    "subtitle_lora_micro_merge_min_duration": 0.8,
                    "sub_gap_break_sec": 1.5,
                    "subtitle_lora_micro_merge_gap_sec": 1.8,
                    "word_timing_gap_break_sec": 0.65,
                    "subtitle_lora_micro_merge_word_gap_sec": 1.2,
                    "continuous_threshold": 2.0,
                    "subtitle_lora_micro_merge_continuous_sec": 3.0,
                ],
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "subtitle_lora_merge_settings")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_lora.merge_settings.v1")
        XCTAssertEqual(result["split_length_threshold"] as? Int, 20)
        XCTAssertEqual(result["sub_min_duration"] as? Double ?? -1.0, 0.8, accuracy: 0.000_001)
        XCTAssertEqual(result["sub_gap_break_sec"] as? Double ?? -1.0, 1.8, accuracy: 0.000_001)
        XCTAssertEqual(result["word_timing_gap_break_sec"] as? Double ?? -1.0, 1.2, accuracy: 0.000_001)
        XCTAssertEqual(result["continuous_threshold"] as? Double ?? -1.0, 3.0, accuracy: 0.000_001)
    }

    func testSubtitleCoreLoraPackagingModeNormalizesSelectiveAliases() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_lora_packaging_mode",
            "payload": [
                "settings": ["subtitle_lora_packaging_mode": "selective"],
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "subtitle_lora_packaging_mode")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_lora.packaging_mode.v1")
        XCTAssertEqual(result["mode"] as? String, "readability_selective")
    }

    func testSubtitleCoreLoraPackagingCandidateScoreKeepsPythonFormulaShape() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_lora_packaging_candidate_score",
            "payload": [
                "line_lengths": [11, 9],
                "pattern": "12|10",
                "strategy": "lora_line_count",
                "current_pattern": "22",
                "target_patterns": ["12|10", "11|11"],
                "target_line_count": 2,
                "threshold": 12,
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "subtitle_lora_packaging_candidate_score")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_lora.packaging_candidate_score.v1")
        XCTAssertEqual(result["valid"] as? Bool, true)
        XCTAssertEqual(result["score"] as? Double ?? -1.0, 310.8, accuracy: 0.000_001)
    }

    func testSubtitleCoreLoraPackagingReasonsMatchesPythonPolicyOrder() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_lora_packaging_reasons",
            "payload": [
                "threshold": 20,
                "chars": 18,
                "line_count": 1,
                "current_pattern": "18",
                "target_patterns": ["9|9"],
                "target_line_count": 2,
                "quality_label": "yellow",
                "quality_score": 76.0,
                "quality_max_score": 84.0,
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "subtitle_lora_packaging_reasons")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.subtitle_lora.packaging_reasons.v1")
        XCTAssertEqual(
            result["reasons"] as? [String],
            ["single_line_overflow", "pattern_mismatch", "line_count_target", "quality_yellow"]
        )
    }

    func testSubtitleCoreSTTDurationFirstOrderSortsLongerChunksFirst() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "stt_duration_first_order",
            "payload": [
                "starts": [5.0, 1.0, 0.0],
                "durations": [1.0, 4.0, 0.5],
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "stt_duration_first_order")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.stt.duration_first_order.v1")
        XCTAssertEqual(result["order"] as? [Int], [1, 0, 2])
        XCTAssertEqual(result["identity"] as? Bool, false)
    }

    func testSubtitleCoreSTTComputeProfileNormalizesNativeUnits() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "stt_compute_profile",
            "payload": [
                "compute_units": "cpu_ane",
                "fallback": "gpu",
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "stt_compute_profile")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.stt.compute_profile.v1")
        XCTAssertEqual(result["profile"] as? String, "ane_gpu")
    }

    func testSubtitleCoreSTTDurationFirstSubmissionEnabledMatchesPythonGate() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "stt_duration_first_submission_enabled",
            "payload": [
                "rescue_pass": false,
                "precision_pass": true,
                "word_timestamps": false,
                "enabled_setting": true,
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "stt_duration_first_submission_enabled")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.stt.duration_first_submission_enabled.v1")
        XCTAssertEqual(result["enabled"] as? Bool, true)
    }

    func testSubtitleCoreSTTWorkerSilenceTimeoutMatchesPrecisionClamp() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "stt_worker_silence_timeout",
            "payload": [
                "settings": [
                    "stt_word_timestamp_precision_pass": true,
                    "stt_word_timestamp_worker_response_timeout_sec": 999.0,
                ],
                "log_label": "단어정밀",
                "word_timestamps": false,
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "stt_worker_silence_timeout")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.stt.worker_silence_timeout.v1")
        XCTAssertEqual(result["key"] as? String, "stt_word_timestamp_worker_response_timeout_sec")
        XCTAssertEqual(result["timeout"] as? Double ?? -1.0, 600.0, accuracy: 0.000_001)
    }

    func testSubtitleCoreSTTStragglerConfigMatchesRecheckBounds() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "stt_straggler_config",
            "payload": [
                "mode": "recheck",
                "settings": [
                    "stt_recheck_worker_straggler_timeout_sec": 1.0,
                    "stt_recheck_worker_straggler_max_missing_chunks": 99,
                    "stt_recheck_worker_straggler_min_received_ratio": 0.1,
                ],
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "stt_straggler_config")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.stt.straggler_config.v1")
        XCTAssertEqual(result["mode"] as? String, "recheck")
        XCTAssertEqual(result["timeout"] as? Double ?? -1.0, 2.0, accuracy: 0.000_001)
        XCTAssertEqual(result["max_missing_chunks"] as? Int, 4)
        XCTAssertEqual(result["min_received_ratio"] as? Double ?? -1.0, 0.25, accuracy: 0.000_001)
    }

    func testSubtitleCoreAudioFastFlattenFilterMatchesPythonFilterShape() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "audio_fast_flatten_filter",
            "payload": [
                "settings": [
                    "macos_native_fast_audio_flatten_hp": 170,
                    "macos_native_fast_audio_flatten_lp": 4200,
                    "macos_native_fast_audio_flatten_nf": -34,
                    "macos_native_fast_audio_flatten_treble": 2.8,
                    "macos_native_fast_audio_flatten_comp_th": -30,
                    "macos_native_fast_audio_flatten_volume": 4.3,
                    "macos_native_fast_audio_flatten_limiter": 0.90,
                ],
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "audio_fast_flatten_filter")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.audio.fast_flatten_filter.v1")
        let filter = try XCTUnwrap(result["filter"] as? String)
        XCTAssertTrue(filter.contains("highpass=f=170"))
        XCTAssertTrue(filter.contains("lowpass=f=4200"))
        XCTAssertTrue(filter.contains("afftdn=nf=-34"))
        XCTAssertTrue(filter.contains("volume=4.3"))
        XCTAssertTrue(filter.contains("alimiter=limit=0.9"))
    }

    func testSubtitleCoreAudioRouteSampleSpanMatchesPythonCenteredWindow() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "audio_route_sample_span",
            "payload": [
                "start": 10.0,
                "end": 70.0,
                "settings": ["audio_chunk_profile_sec": 20.0],
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "audio_route_sample_span")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.audio.route_sample_span.v1")
        XCTAssertEqual(result["start"] as? Double ?? -1.0, 30.0, accuracy: 0.000_001)
        XCTAssertEqual(result["duration"] as? Double ?? -1.0, 20.0, accuracy: 0.000_001)
    }

    func testSubtitleCoreAudioAIVariantPreservesFastFlattenPriority() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "audio_ai_variant",
            "payload": [
                "audio_ai": "clearvoice",
                "fast_flatten_enabled": true,
                "clearvoice_native_ffmpeg_enabled": true,
                "clearvoice_model_name": "MossFormer2_SE_48K",
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "audio_ai_variant")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.audio.ai_variant.v1")
        XCTAssertEqual(result["variant"] as? String, "macos_native_fast_audio_flatten_v1")
    }

    func testSubtitleCoreAudioRoutePreviewDivergenceMatchesGapFallback() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "audio_route_preview_divergence",
            "payload": [
                "route": [
                    "preview_scores": [["score": 0.7], ["score": 0.55]],
                    "candidate_scores": [["score": 0.9], ["score": 0.5]],
                ],
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "audio_route_preview_divergence")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.audio.route_preview_divergence.v1")
        XCTAssertEqual(result["divergence"] as? Double ?? -1.0, 0.25, accuracy: 0.000_001)
    }

    func testSubtitleCoreAudioRouteSplitDecisionMatchesBaselineGuardPath() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "audio_route_split_decision",
            "payload": [
                "fallback_like": false,
                "challenging": false,
                "low_confidence": false,
                "baseline_guard": true,
                "preview_switch": false,
                "specialist": false,
                "volatile": false,
                "noise": "low",
                "candidate_gap": 0.2,
                "preview_gap": 0.1,
                "gap_limit": 0.06,
                "preview_divergence": 0.12,
                "preview_divergence_min": 0.08,
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "audio_route_split_decision")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        XCTAssertEqual(result["schema"] as? String, "ai_subtitle_studio.audio.route_split_decision.v1")
        XCTAssertEqual(result["split"] as? Bool, true)
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
        XCTAssertEqual(result["max_active_bin_index"] as? Int, 0)
        XCTAssertEqual(result["max_active_segments"] as? Int, 2)
        let coverageRatio = try XCTUnwrap(result["coverage_ratio"] as? Double)
        let longestGap = try XCTUnwrap(result["longest_empty_span_sec"] as? Double)
        let longestGapStart = try XCTUnwrap(result["longest_empty_start_sec"] as? Double)
        let longestGapEnd = try XCTUnwrap(result["longest_empty_end_sec"] as? Double)
        XCTAssertEqual(coverageRatio, 0.625, accuracy: 0.000001)
        XCTAssertEqual(longestGap, 1.5, accuracy: 0.000001)
        XCTAssertEqual(longestGapStart, 1.5, accuracy: 0.000001)
        XCTAssertEqual(longestGapEnd, 3.0, accuracy: 0.000001)
        XCTAssertEqual(result["stable_for_global_canvas"] as? Bool, false)
        let accelerator = try XCTUnwrap(result["accelerator_summary"] as? [String: Any])
        XCTAssertEqual(accelerator["metal_claims_ane"] as? Bool, false)
        XCTAssertEqual(accelerator["ane_task_count"] as? Int, 0)
    }

    func testSubtitleCoreGlobalCanvasSummaryCanReturnMergedSegmentsForPainter() throws {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "subtitle_global_canvas_summary",
            "payload": [
                "duration": 5.0,
                "bin_count": 5,
                "include_merged_segments": true,
                "allowed_lanes": ["SUBTITLE"],
                "output_lane": "SUBTITLE",
                "merge_gap_sec": 0.05,
                "segments": [
                    ["start": 1.0, "end": 1.4, "text": "중간", "lane": "SUBTITLE"],
                    ["start": 0.0, "end": 1.0, "text": "앞", "lane": "SUBTITLE"],
                    ["start": 1.6, "end": 2.0, "text": "대기", "lane": "STT1"],
                ],
            ],
        ])

        XCTAssertEqual(response["operation"] as? String, "subtitle_global_canvas_summary")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        let merged = try XCTUnwrap(result["merged_segments"] as? [[String: Any]])
        XCTAssertEqual(merged.count, 1)
        XCTAssertEqual(merged.first?["lane"] as? String, "SUBTITLE")
        XCTAssertEqual(merged.first?["text"] as? String, "앞 중간")
        XCTAssertEqual(merged.first?["count"] as? Int, 2)
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
        XCTAssertEqual(result["matched_reference_indices"] as? [Int], [0, 1])
        let timingMAE = try XCTUnwrap(result["timing_mae_sec"] as? Double)
        let overlapScore = try XCTUnwrap(result["overlap_score"] as? Double)
        XCTAssertEqual(timingMAE, 0.125, accuracy: 0.000001)
        XCTAssertEqual(overlapScore, 85.0, accuracy: 0.000001)
        XCTAssertEqual(try XCTUnwrap(result["max_start_error_sec"] as? Double), 0.2, accuracy: 0.000001)
        XCTAssertEqual(try XCTUnwrap(result["max_end_error_sec"] as? Double), 0.1, accuracy: 0.000001)
        XCTAssertEqual(try XCTUnwrap(result["max_pair_timing_error_sec"] as? Double), 0.15, accuracy: 0.000001)
        XCTAssertEqual(result["worst_match_hypothesis_index"] as? Int, 1)
        XCTAssertEqual(result["worst_match_reference_index"] as? Int, 1)
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
        XCTAssertEqual(accelerator["accelerate_vdsp"] as? Bool, true)
        XCTAssertEqual(accelerator["metal_claims_ane"] as? Bool, false)
        XCTAssertEqual(accelerator["ane_task_count"] as? Int, 0)
    }
}
