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
        let summary = summarize(orderedAllocations: ordered)
        return [
            "schema": schema,
            "backend": "swift",
            "allocator_schema": plan["schema"] ?? "",
            "pressure_stage": plan["pressure_stage"] ?? "normal",
            "accelerator_summary": summary,
            "global": plan["global"] ?? [:],
        ]
    }

    private static func summarize(orderedAllocations: [[String: Any]]) -> [String: Any] {
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
}
