import XCTest
@testable import AIStudioCore

final class NativeResourceAllocatorTests: XCTestCase {
    func testCriticalPressurePausesBackgroundAndKeepsSTTConservative() throws {
        let response = NativeResourceAllocator.plan(
            payload: [
                "topology": [
                    "logical_cores": 10,
                    "physical_cores": 10,
                    "performance_cores": 4,
                    "efficiency_cores": 6,
                    "memory_bytes": 16 * 1_073_741_824,
                ],
                "memory": [
                    "memory_bytes": 16 * 1_073_741_824,
                    "available_memory_bytes": 900 * 1_048_576,
                    "available_memory_ratio": 0.052,
                    "pressure_stage": "critical",
                ],
                "requests": [
                    ["task": "stt", "workload": 4, "requested_workers": 4, "minimum": 1],
                    ["task": "background", "workload": 4, "requested_workers": 4, "minimum": 0],
                ],
            ]
        )

        XCTAssertEqual(response["schema"] as? String, "ai_subtitle_studio.native_resource_allocator.v1")
        XCTAssertEqual(response["pressure_stage"] as? String, "critical")
        let allocations = try XCTUnwrap(response["allocations"] as? [String: Any])
        let stt = try XCTUnwrap(allocations["stt"] as? [String: Any])
        let background = try XCTUnwrap(allocations["background"] as? [String: Any])
        XCTAssertEqual(stt["workers"] as? Int, 1)
        XCTAssertEqual(stt["model_slots"] as? Int, 1)
        XCTAssertEqual(background["workers"] as? Int, 0)
        XCTAssertEqual(background["should_pause"] as? Bool, true)
    }

    func testNormalPressureUsesPerformanceAndEfficiencyCoreBudget() throws {
        let response = NativeResourceAllocator.plan(
            payload: [
                "active_labels": ["pipeline", "editor"],
                "topology": [
                    "logical_cores": 10,
                    "physical_cores": 10,
                    "performance_cores": 4,
                    "efficiency_cores": 6,
                    "memory_bytes": 16 * 1_073_741_824,
                ],
                "memory": [
                    "memory_bytes": 16 * 1_073_741_824,
                    "available_memory_bytes": 6 * 1_073_741_824,
                    "available_memory_ratio": 0.375,
                    "pressure_stage": "normal",
                ],
                "requests": [
                    ["task": "audio_extract", "workload": 8, "requested_workers": 8, "minimum": 1],
                    ["task": "subtitle_llm", "workload": 4, "requested_workers": 4, "minimum": 1],
                ],
            ]
        )

        let global = try XCTUnwrap(response["global"] as? [String: Any])
        XCTAssertEqual(global["cpu_worker_budget"] as? Int, 8)
        let allocations = try XCTUnwrap(response["allocations"] as? [String: Any])
        let audio = try XCTUnwrap(allocations["audio_extract"] as? [String: Any])
        let llm = try XCTUnwrap(allocations["subtitle_llm"] as? [String: Any])
        XCTAssertEqual(audio["workers"] as? Int, 8)
        XCTAssertEqual(audio["performance_workers"] as? Int, 4)
        XCTAssertEqual(audio["efficiency_workers"] as? Int, 4)
        XCTAssertEqual(llm["workers"] as? Int, 2)
    }

    func testFullCoreProfileUsesAllLogicalCoresForNativePipelineBudget() throws {
        let response = NativeResourceAllocator.plan(
            payload: [
                "active_labels": ["pipeline"],
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
                "requests": [
                    ["task": "audio_extract", "workload": 10, "requested_workers": 10, "minimum": 1],
                    ["task": "stt_precision", "workload": 10, "requested_workers": 10, "minimum": 1],
                ],
            ]
        )

        let global = try XCTUnwrap(response["global"] as? [String: Any])
        XCTAssertEqual(global["interactive_reserve_cores"] as? Int, 0)
        XCTAssertEqual(global["cpu_worker_budget"] as? Int, 10)
        let allocations = try XCTUnwrap(response["allocations"] as? [String: Any])
        let audio = try XCTUnwrap(allocations["audio_extract"] as? [String: Any])
        XCTAssertEqual(audio["workers"] as? Int, 10)
        let precision = try XCTUnwrap(allocations["stt_precision"] as? [String: Any])
        XCTAssertEqual(precision["workers"] as? Int, 10)
        XCTAssertEqual(precision["compute_units"] as? String, "all")
        let accelerator = try XCTUnwrap(precision["accelerator"] as? [String: Any])
        XCTAssertEqual(accelerator["policy"] as? String, "whisperkit_ane_gpu_saturation")
        XCTAssertEqual(accelerator["gpu_lanes"] as? Int, 10)
        XCTAssertEqual(accelerator["ane_lanes"] as? Int, 10)
    }

    func testVadAndAudioMLUseMetalGPUHintsWithoutClaimingANE() throws {
        let response = NativeResourceAllocator.plan(
            payload: [
                "active_labels": ["pipeline"],
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
                "requests": [
                    ["task": "vad", "workload": 4, "requested_workers": 4, "minimum": 1],
                    ["task": "audio_ml", "workload": 4, "requested_workers": 4, "minimum": 1],
                ],
            ]
        )

        let allocations = try XCTUnwrap(response["allocations"] as? [String: Any])
        let vad = try XCTUnwrap(allocations["vad"] as? [String: Any])
        let vadAccelerator = try XCTUnwrap(vad["accelerator"] as? [String: Any])
        XCTAssertEqual(vadAccelerator["policy"] as? String, "metal_ml_balanced")
        XCTAssertEqual(vadAccelerator["prefer"] as? [String], ["gpu", "cpu"])
        XCTAssertGreaterThan(try XCTUnwrap(vadAccelerator["gpu_lanes"] as? Int), 0)
        XCTAssertEqual(vadAccelerator["ane_lanes"] as? Int, 0)
        XCTAssertEqual(vad["compute_units"] as? String, "cpuOnly")

        let audioML = try XCTUnwrap(allocations["audio_ml"] as? [String: Any])
        let audioMLAccelerator = try XCTUnwrap(audioML["accelerator"] as? [String: Any])
        XCTAssertEqual(audioMLAccelerator["policy"] as? String, "metal_ml_balanced")
        XCTAssertGreaterThan(try XCTUnwrap(audioMLAccelerator["gpu_lanes"] as? Int), 0)
        XCTAssertEqual(audioMLAccelerator["ane_lanes"] as? Int, 0)
    }

    func testNormalPressureAllowsAggressiveSTTPrecisionSlots() throws {
        let response = NativeResourceAllocator.plan(
            payload: [
                "topology": [
                    "logical_cores": 10,
                    "physical_cores": 10,
                    "performance_cores": 4,
                    "efficiency_cores": 6,
                    "memory_bytes": 16 * 1_073_741_824,
                ],
                "memory": [
                    "memory_bytes": 16 * 1_073_741_824,
                    "available_memory_bytes": 6 * 1_073_741_824,
                    "available_memory_ratio": 0.375,
                    "pressure_stage": "normal",
                ],
                "requests": [
                    ["task": "stt_precision", "workload": 3, "requested_workers": 3, "minimum": 1],
                ],
            ]
        )

        let allocations = try XCTUnwrap(response["allocations"] as? [String: Any])
        let precision = try XCTUnwrap(allocations["stt_precision"] as? [String: Any])
        XCTAssertEqual(precision["workers"] as? Int, 3)
        XCTAssertEqual(precision["model_slots"] as? Int, 3)
        XCTAssertEqual(precision["compute_units"] as? String, "all")
    }

    func testSubtitleOptimizeActiveLabelGetsNativeLLMBudget() throws {
        let response = NativeResourceAllocator.plan(
            payload: [
                "active_labels": ["pipeline", "subtitle_optimize"],
                "topology": [
                    "logical_cores": 10,
                    "physical_cores": 10,
                    "performance_cores": 4,
                    "efficiency_cores": 6,
                    "memory_bytes": 16 * 1_073_741_824,
                ],
                "memory": [
                    "memory_bytes": 16 * 1_073_741_824,
                    "available_memory_bytes": 6 * 1_073_741_824,
                    "available_memory_ratio": 0.375,
                    "pressure_stage": "normal",
                ],
            ]
        )

        let allocations = try XCTUnwrap(response["allocations"] as? [String: Any])
        let optimize = try XCTUnwrap(allocations["subtitle_optimize"] as? [String: Any])
        XCTAssertEqual(optimize["workers"] as? Int, 2)
        XCTAssertEqual(optimize["model_slots"] as? Int, 1)
        let dynamic = try XCTUnwrap(response["dynamic"] as? [String: Any])
        XCTAssertEqual(dynamic["next_poll_ms"] as? Int, 300)
    }

    func testPipelineStagePriorityOrdersCutSttSubtitleAndRoughcut() throws {
        let response = NativeResourceAllocator.plan(
            payload: [
                "topology": [
                    "logical_cores": 10,
                    "physical_cores": 10,
                    "performance_cores": 4,
                    "efficiency_cores": 6,
                    "memory_bytes": 16 * 1_073_741_824,
                ],
                "memory": [
                    "memory_bytes": 16 * 1_073_741_824,
                    "available_memory_bytes": 6 * 1_073_741_824,
                    "available_memory_ratio": 0.375,
                    "pressure_stage": "normal",
                ],
                "requests": [
                    ["task": "roughcut_llm", "workload": 1, "minimum": 1],
                    ["task": "subtitle_llm", "workload": 1, "minimum": 1],
                    ["task": "stt_precision", "workload": 1, "minimum": 1],
                    ["task": "stt", "workload": 1, "minimum": 1],
                    ["task": "cut_follower", "workload": 1, "minimum": 1],
                    ["task": "cut_pioneer", "workload": 1, "minimum": 1],
                ],
            ]
        )

        let ordered = try XCTUnwrap(response["ordered_allocations"] as? [[String: Any]])
        let tasks = ordered.compactMap { $0["task"] as? String }
        XCTAssertLessThan(try XCTUnwrap(tasks.firstIndex(of: "cut_pioneer")), try XCTUnwrap(tasks.firstIndex(of: "stt")))
        XCTAssertLessThan(try XCTUnwrap(tasks.firstIndex(of: "cut_follower")), try XCTUnwrap(tasks.firstIndex(of: "stt")))
        XCTAssertLessThan(try XCTUnwrap(tasks.firstIndex(of: "stt")), try XCTUnwrap(tasks.firstIndex(of: "stt_precision")))
        XCTAssertLessThan(try XCTUnwrap(tasks.firstIndex(of: "stt_precision")), try XCTUnwrap(tasks.firstIndex(of: "subtitle_llm")))
        XCTAssertLessThan(try XCTUnwrap(tasks.firstIndex(of: "subtitle_llm")), try XCTUnwrap(tasks.firstIndex(of: "roughcut_llm")))

        let allocations = try XCTUnwrap(response["allocations"] as? [String: Any])
        let cut = try XCTUnwrap(allocations["cut_pioneer"] as? [String: Any])
        let roughcut = try XCTUnwrap(allocations["roughcut_llm"] as? [String: Any])
        XCTAssertGreaterThan(try XCTUnwrap(cut["priority"] as? Int), try XCTUnwrap(roughcut["priority"] as? Int))
    }

    func testCriticalPressureBuildsImmediateReclaimActionsFromPreviousPlan() throws {
        let response = NativeResourceAllocator.plan(
            payload: [
                "active_labels": ["pipeline", "stt"],
                "topology": [
                    "logical_cores": 10,
                    "physical_cores": 10,
                    "performance_cores": 4,
                    "efficiency_cores": 6,
                    "memory_bytes": 16 * 1_073_741_824,
                ],
                "memory": [
                    "memory_bytes": 16 * 1_073_741_824,
                    "available_memory_bytes": 700 * 1_048_576,
                    "available_memory_ratio": 0.043,
                    "pressure_stage": "critical",
                ],
                "previous_allocation": [
                    "allocations": [
                        "stt": ["task": "stt", "workers": 2, "memory_budget_bytes": 2_000_000_000],
                        "roughcut_llm": ["task": "roughcut_llm", "workers": 1, "memory_budget_bytes": 900_000_000],
                        "background": ["task": "background", "workers": 2, "memory_budget_bytes": 300_000_000],
                    ]
                ],
                "requests": [
                    ["task": "stt", "workload": 4, "requested_workers": 4, "minimum": 1],
                    ["task": "roughcut_llm", "workload": 2, "requested_workers": 2, "minimum": 0],
                    ["task": "background", "workload": 4, "requested_workers": 4, "minimum": 0],
                ],
            ]
        )

        let allocations = try XCTUnwrap(response["allocations"] as? [String: Any])
        let roughcut = try XCTUnwrap(allocations["roughcut_llm"] as? [String: Any])
        XCTAssertEqual(roughcut["workers"] as? Int, 0)
        XCTAssertEqual(roughcut["should_pause"] as? Bool, true)
        XCTAssertEqual(roughcut["action"] as? String, "pause")

        let dynamic = try XCTUnwrap(response["dynamic"] as? [String: Any])
        XCTAssertEqual(dynamic["mode"] as? String, "immediate_reclaim")
        XCTAssertEqual(dynamic["next_poll_ms"] as? Int, 120)
        XCTAssertEqual(dynamic["reclaim_deadline_ms"] as? Int, 0)
        XCTAssertLessThan(try XCTUnwrap(dynamic["worker_delta"] as? Int), 0)
        let reclaim = try XCTUnwrap(dynamic["reclaim"] as? [[String: Any]])
        let reclaimTasks = reclaim.compactMap { $0["task"] as? String }
        XCTAssertTrue(reclaimTasks.contains("roughcut_llm"))
        XCTAssertTrue(reclaimTasks.contains("background"))
        XCTAssertTrue(reclaimTasks.contains("stt"))
    }

    func testNormalPressureBuildsFastAllocateActionsWithoutPreviousPlan() throws {
        let response = NativeResourceAllocator.plan(
            payload: [
                "active_labels": ["pipeline"],
                "topology": [
                    "logical_cores": 10,
                    "physical_cores": 10,
                    "performance_cores": 4,
                    "efficiency_cores": 6,
                    "memory_bytes": 16 * 1_073_741_824,
                ],
                "memory": [
                    "memory_bytes": 16 * 1_073_741_824,
                    "available_memory_bytes": 6 * 1_073_741_824,
                    "available_memory_ratio": 0.375,
                    "pressure_stage": "normal",
                ],
                "requests": [
                    ["task": "cut_pioneer", "workload": 4, "requested_workers": 4, "minimum": 1],
                    ["task": "stt", "workload": 2, "requested_workers": 2, "minimum": 1],
                ],
            ]
        )

        let dynamic = try XCTUnwrap(response["dynamic"] as? [String: Any])
        XCTAssertEqual(dynamic["mode"] as? String, "balanced_expand")
        XCTAssertEqual(dynamic["next_poll_ms"] as? Int, 300)
        let allocate = try XCTUnwrap(dynamic["allocate"] as? [[String: Any]])
        let tasks = allocate.compactMap { $0["task"] as? String }
        XCTAssertEqual(tasks, ["cut_pioneer", "stt"])
        XCTAssertGreaterThan(try XCTUnwrap(dynamic["worker_delta"] as? Int), 0)
    }
}
