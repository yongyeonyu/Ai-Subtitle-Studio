import Foundation

public enum SubtitleResourcePlanNative {
    public static let schema = "ai_subtitle_studio.subtitle_resource.plan.v1"

    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        var allocatorPayload = payload
        if allocatorPayload["active_labels"] == nil {
            allocatorPayload["active_labels"] = ["pipeline", "stt", "subtitle_optimize"]
        }
        let plan = NativeResourceAllocator.plan(payload: allocatorPayload)
        let ordered = SubtitleAssemblyValue.dictionaryRows(plan["ordered_allocations"])
        let topology = plan["topology"] as? [String: Any] ?? [:]
        let summary = summarize(orderedAllocations: ordered, topology: topology)
        return [
            "schema": schema,
            "backend": "swift",
            "allocator_schema": plan["schema"] ?? "",
            "pressure_stage": plan["pressure_stage"] ?? "normal",
            "accelerator_summary": summary,
            "global": plan["global"] ?? [:],
        ]
    }

    private static func summarize(orderedAllocations: [[String: Any]], topology: [String: Any]) -> [String: Any] {
        var aneTasks: [String] = []
        var gpuTasks: [String] = []
        var metalTasks: [String] = []
        var cpuOnlyTasks: [String] = []
        var routing: [[String: Any]] = []
        var gpuLanesTotal = 0
        var aneLanesTotal = 0
        var maxGpuLanes = 0
        var maxAneLanes = 0

        for row in orderedAllocations {
            let task = SubtitleAssemblyValue.string(row["task"])
            if task.isEmpty {
                continue
            }
            let accelerator = row["accelerator"] as? [String: Any] ?? [:]
            let policy = SubtitleAssemblyValue.string(accelerator["policy"])
            let computeUnits = SubtitleAssemblyValue.string(row["compute_units"])
            let gpuLanes = max(0, Int(SubtitleAssemblyValue.number(accelerator["gpu_lanes"])))
            let aneLanes = max(0, Int(SubtitleAssemblyValue.number(accelerator["ane_lanes"])))
            let prefer = SubtitleAssemblyValue.stringArray(accelerator["prefer"], fallback: [])
            let lowerPolicy = policy.lowercased()

            gpuLanesTotal += gpuLanes
            aneLanesTotal += aneLanes
            maxGpuLanes = max(maxGpuLanes, gpuLanes)
            maxAneLanes = max(maxAneLanes, aneLanes)
            if gpuLanes > 0 || prefer.contains("gpu") {
                gpuTasks.append(task)
            }
            if aneLanes > 0 || prefer.contains("ane") {
                aneTasks.append(task)
            }
            if lowerPolicy.contains("metal") {
                metalTasks.append(task)
            }
            if gpuLanes == 0 && aneLanes == 0 && computeUnits == "cpuOnly" {
                cpuOnlyTasks.append(task)
            }
            routing.append([
                "task": task,
                "policy": policy,
                "compute_units": computeUnits,
                "gpu_lanes": gpuLanes,
                "ane_lanes": aneLanes,
            ])
        }

        let gpuLaneCapacity = max(0, Int(SubtitleAssemblyValue.number(topology["gpu_cores"])))
        let neuralLaneCapacity = max(0, Int(SubtitleAssemblyValue.number(topology["neural_engine_cores"])))
        // 변경 금지: ANE physical core 사용률로 과장하지 않고, WhisperKit/Core ML 모델 동시 처리 lane 기준만 기록한다.
        // 이 값은 benchmark artifact에서 "GPU/ANE를 full로 쓰는가"를 확인하는 진단값이며 allocation 정책을 바꾸지 않는다.
        let aneModelLaneCapacity: Int
        if neuralLaneCapacity > 0 {
            aneModelLaneCapacity = min(neuralLaneCapacity, max(gpuLaneCapacity, maxAneLanes))
        } else {
            aneModelLaneCapacity = 0
        }
        let fullGpuLaneTaskCount: Int
        if gpuLaneCapacity > 0 {
            fullGpuLaneTaskCount = routing.filter { Int(SubtitleAssemblyValue.number($0["gpu_lanes"])) >= gpuLaneCapacity }.count
        } else {
            fullGpuLaneTaskCount = 0
        }
        let fullANEModelLaneTaskCount: Int
        if aneModelLaneCapacity > 0 {
            fullANEModelLaneTaskCount = routing.filter { Int(SubtitleAssemblyValue.number($0["ane_lanes"])) >= aneModelLaneCapacity }.count
        } else {
            fullANEModelLaneTaskCount = 0
        }
        let gpuPeakRatio = gpuLaneCapacity > 0 ? Double(maxGpuLanes) / Double(gpuLaneCapacity) : 0.0
        let aneModelPeakRatio = aneModelLaneCapacity > 0 ? Double(maxAneLanes) / Double(aneModelLaneCapacity) : 0.0

        return [
            "schema": "ai_subtitle_studio.subtitle_resource.summary.v1",
            "task_count": orderedAllocations.count,
            "ane_tasks": stableUnique(aneTasks),
            "gpu_tasks": stableUnique(gpuTasks),
            "metal_tasks": stableUnique(metalTasks),
            "cpu_only_tasks": stableUnique(cpuOnlyTasks),
            "gpu_task_count": stableUnique(gpuTasks).count,
            "ane_task_count": stableUnique(aneTasks).count,
            "metal_task_count": stableUnique(metalTasks).count,
            "gpu_lanes_total": gpuLanesTotal,
            "ane_lanes_total": aneLanesTotal,
            "max_gpu_lanes": maxGpuLanes,
            "max_ane_lanes": maxAneLanes,
            "gpu_lane_capacity": gpuLaneCapacity,
            "ane_model_lane_capacity": aneModelLaneCapacity,
            "gpu_lane_peak_ratio": round6(gpuPeakRatio),
            "ane_model_lane_peak_ratio": round6(aneModelPeakRatio),
            "full_gpu_lane_task_count": fullGpuLaneTaskCount,
            "full_ane_model_lane_task_count": fullANEModelLaneTaskCount,
            "gpu_lane_peak_saturated": gpuLaneCapacity > 0 && maxGpuLanes >= gpuLaneCapacity,
            "ane_model_lane_peak_saturated": aneModelLaneCapacity > 0 && maxAneLanes >= aneModelLaneCapacity,
            "metal_claims_ane": false,
            "routing": routing,
        ]
    }

    private static func stableUnique(_ values: [String]) -> [String] {
        var out: [String] = []
        for value in values where !value.isEmpty && !out.contains(value) {
            out.append(value)
        }
        return out
    }

    private static func round6(_ value: Double) -> Double {
        guard value.isFinite else { return 0.0 }
        return (value * 1_000_000.0).rounded() / 1_000_000.0
    }
}
