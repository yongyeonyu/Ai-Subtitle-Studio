import Darwin
import Foundation

public enum NativeResourceAllocator {
    private static let gibibyte = 1_073_741_824.0

    public static func plan(payload: [String: Any] = [:]) -> [String: Any] {
        let settings = payload["settings"] as? [String: Any] ?? [:]
        let memory = payload["memory"] as? [String: Any] ?? MemoryPressure.snapshot(payload: payload)
        let topology = topologySnapshot(payload: payload)
        let pressureStage = normalizedStage(memory["pressure_stage"])
        let activeLabels = stringArray(payload["active_labels"])
        let requests = resourceRequests(payload["requests"], activeLabels: activeLabels)
            .sorted { left, right in
                let leftPriority = taskPriority(left)
                let rightPriority = taskPriority(right)
                if leftPriority == rightPriority {
                    return normalizedTask(left["task"]) < normalizedTask(right["task"])
                }
                return leftPriority > rightPriority
            }
        let reserveCores = interactiveReserveCores(
            settings: settings,
            pressureStage: pressureStage,
            activeLabels: activeLabels,
            topology: topology
        )
        let cpuBudget = cpuWorkerBudget(
            pressureStage: pressureStage,
            reserveCores: reserveCores,
            topology: topology
        )
        let memoryBudgetBytes = memoryBudget(memory: memory, pressureStage: pressureStage)
        var allocations: [String: Any] = [:]
        var orderedTasks: [[String: Any]] = []
        let previousAllocations = allocationMap(payload["previous_allocation"])

        for request in requests {
            var allocation = allocationForRequest(
                request,
                pressureStage: pressureStage,
                cpuBudget: cpuBudget,
                memoryBudgetBytes: memoryBudgetBytes,
                topology: topology,
                settings: settings
            )
            let task = String(describing: allocation["task"] ?? "")
            if !task.isEmpty {
                allocation = attachDynamicState(
                    allocation,
                    previous: previousAllocations[task],
                    pressureStage: pressureStage
                )
                allocations[task] = allocation
                orderedTasks.append(allocation)
            }
        }
        let dynamic = dynamicTransition(
            current: orderedTasks,
            previous: previousAllocations,
            pressureStage: pressureStage,
            activeLabels: activeLabels
        )

        return [
            "schema": "ai_subtitle_studio.native_resource_allocator.v1",
            "ok": true,
            "source": "swift_native_resource_allocator",
            "timestamp": Date().timeIntervalSince1970,
            "pressure_stage": pressureStage,
            "active_labels": activeLabels,
            "topology": topology,
            "memory": compactMemory(memory),
            "global": [
                "interactive_reserve_cores": reserveCores,
                "cpu_worker_budget": cpuBudget,
                "memory_budget_bytes": memoryBudgetBytes,
                "pressure_stage": pressureStage,
            ],
            "allocations": allocations,
            "ordered_allocations": orderedTasks,
            "dynamic": dynamic,
        ]
    }

    private static func topologySnapshot(payload: [String: Any]) -> [String: Any] {
        let override = payload["topology"] as? [String: Any] ?? [:]
        let logical = max(1, intValue(override["logical_cores"]) ?? ProcessInfo.processInfo.processorCount)
        let active = max(1, min(logical, intValue(override["active_cores"]) ?? ProcessInfo.processInfo.activeProcessorCount))
        let physical = max(1, intValue(override["physical_cores"]) ?? sysctlInt("hw.physicalcpu") ?? logical)
        let performance = max(1, min(logical, intValue(override["performance_cores"]) ?? performanceCoreCount(fallbackPhysical: physical)))
        let efficiencyFallback = max(0, logical - performance)
        let efficiency = max(0, min(logical - performance, intValue(override["efficiency_cores"]) ?? efficiencyFallback))
        let gpu = max(0, intValue(override["gpu_cores"]) ?? sysctlInt("hw.perflevel0.gpu_core_count") ?? 0)
        let neural = max(0, intValue(override["neural_engine_cores"]) ?? 16)
        let memoryBytes = max(0, intValue(override["memory_bytes"]) ?? Int(ProcessInfo.processInfo.physicalMemory))
        return [
            "logical_cores": logical,
            "active_cores": active,
            "physical_cores": physical,
            "performance_cores": performance,
            "efficiency_cores": efficiency,
            "gpu_cores": gpu,
            "neural_engine_cores": neural,
            "memory_bytes": memoryBytes,
        ]
    }

    private static func resourceRequests(_ raw: Any?, activeLabels: [String]) -> [[String: Any]] {
        if let requests = raw as? [[String: Any]], !requests.isEmpty {
            return requests
        }
        let pipelineActive = activeLabels.contains("pipeline") || activeLabels.contains("fast")
        let editorActive = activeLabels.contains("editor")
        let subtitleOptimizeActive = activeLabels.contains("subtitle_optimize")
        return [
            ["task": "ui", "workload": 1, "minimum": 1, "priority": 120],
            ["task": "timeline", "workload": editorActive ? 2 : 1, "minimum": 1, "priority": 115],
            ["task": "cut_pioneer", "workload": pipelineActive ? 4 : 1, "minimum": 1, "priority": 110],
            ["task": "cut_follower", "workload": pipelineActive ? 4 : 1, "minimum": 1, "priority": 105],
            ["task": "stt", "workload": pipelineActive ? 4 : 1, "minimum": 1, "priority": 100, "model": "whisperkit"],
            ["task": "stt_precision", "workload": pipelineActive ? 10 : 1, "minimum": 1, "priority": 96, "model": "whisperkit"],
            ["task": "subtitle_llm", "workload": pipelineActive ? 4 : 1, "minimum": 1, "priority": 80],
            ["task": "subtitle_optimize", "workload": subtitleOptimizeActive ? 3 : 0, "minimum": subtitleOptimizeActive ? 1 : 0, "priority": 78],
            ["task": "audio_extract", "workload": pipelineActive ? 6 : 2, "minimum": 1, "priority": 70],
            ["task": "vad", "workload": pipelineActive ? 4 : 1, "minimum": 1, "priority": 65],
            ["task": "roughcut_llm", "workload": 2, "minimum": 0, "priority": 45],
            ["task": "background", "workload": 4, "minimum": 0, "priority": 10],
        ]
    }

    private static func allocationForRequest(
        _ request: [String: Any],
        pressureStage: String,
        cpuBudget: Int,
        memoryBudgetBytes: Int,
        topology: [String: Any],
        settings: [String: Any]
    ) -> [String: Any] {
        let task = normalizedTask(request["task"])
        let priority = taskPriority(request)
        let workload = max(0, intValue(request["workload"]) ?? 1)
        let requested = intValue(request["requested_workers"]) ?? intValue(request["workers"]) ?? workload
        let minimum = max(0, intValue(request["minimum"]) ?? (task == "background" ? 0 : 1))
        let maximum = max(minimum, intValue(request["maximum"]) ?? defaultCap(
            task: task,
            pressureStage: pressureStage,
            topology: topology,
            settings: settings
        ))
        let workers = boundedWorkers(
            task: task,
            requested: requested,
            workload: workload,
            minimum: minimum,
            maximum: maximum,
            cpuBudget: cpuBudget,
            pressureStage: pressureStage
        )
        let perf = max(1, intValue(topology["performance_cores"]) ?? 1)
        let efficiency = max(0, intValue(topology["efficiency_cores"]) ?? 0)
        let performanceWorkers = min(workers, perf)
        let efficiencyWorkers = max(0, min(efficiency, workers - performanceWorkers))
        let memoryBytes = taskMemoryBudget(
            task: task,
            workers: workers,
            memoryBudgetBytes: memoryBudgetBytes,
            pressureStage: pressureStage
        )
        return [
            "task": task,
            "workers": workers,
            "performance_workers": performanceWorkers,
            "efficiency_workers": efficiencyWorkers,
            "accelerator": acceleratorPlan(task: task, workers: workers, topology: topology, pressureStage: pressureStage),
            "compute_units": computeUnits(task: task, pressureStage: pressureStage),
            "memory_budget_bytes": memoryBytes,
            "model_slots": modelSlots(task: task, workers: workers, pressureStage: pressureStage),
            "should_pause": shouldPause(task: task, pressureStage: pressureStage, workers: workers),
            "priority": priority,
            "pressure_stage": pressureStage,
            "reason": reason(task: task, pressureStage: pressureStage),
        ]
    }

    private static func defaultCap(
        task: String,
        pressureStage: String,
        topology: [String: Any],
        settings: [String: Any]
    ) -> Int {
        let logical = max(1, intValue(topology["logical_cores"]) ?? 1)
        let perf = max(1, intValue(topology["performance_cores"]) ?? 1)
        let efficiency = max(0, intValue(topology["efficiency_cores"]) ?? 0)
        let healthyWide = min(logical, perf + min(efficiency, 4))
        let healthyBalanced = min(logical, perf + min(efficiency, 2))
        switch task {
        case "ui", "timeline":
            return 1
        case "stt_precision":
            if pressureStage == "normal" {
                let gpu = max(0, intValue(topology["gpu_cores"]) ?? 0)
                let acceleratorWide = gpu > 0 ? gpu : healthyWide
                return min(logical, max(1, acceleratorWide))
            }
            return 1
        case "stt":
            return pressureStage == "normal" ? min(2, max(1, perf)) : 1
        case "subtitle", "subtitle_llm", "subtitle_optimize", "roughcut", "roughcut_llm":
            if isAPIModel(settings: settings) {
                return 1
            }
            return pressureStage == "normal" ? min(2, max(1, perf / 2)) : 1
        case "audio_extract", "audio", "vad":
            return pressureStage == "normal" ? healthyWide : max(1, min(perf, healthyBalanced))
        case "cut_boundary", "cut_pioneer", "cut_follower":
            return pressureStage == "normal" ? min(4, healthyBalanced) : max(1, min(2, perf))
        case "background":
            return pressureStage == "critical" ? 0 : (pressureStage == "warning" ? 1 : min(2, max(1, efficiency)))
        default:
            return pressureStage == "normal" ? healthyBalanced : max(1, min(perf, healthyBalanced))
        }
    }

    private static func boundedWorkers(
        task: String,
        requested: Int,
        workload: Int,
        minimum: Int,
        maximum: Int,
        cpuBudget: Int,
        pressureStage: String
    ) -> Int {
        if workload <= 0 || maximum <= 0 {
            return minimum == 0 ? 0 : max(1, minimum)
        }
        var cap = min(maximum, max(minimum, cpuBudget))
        if shouldHardPause(task: task, pressureStage: pressureStage) {
            cap = 0
        }
        let raw = min(max(0, requested), max(0, workload), max(0, cap))
        if minimum == 0 {
            return max(0, raw)
        }
        return max(minimum, raw)
    }

    private static func cpuWorkerBudget(pressureStage: String, reserveCores: Int, topology: [String: Any]) -> Int {
        let logical = max(1, intValue(topology["logical_cores"]) ?? 1)
        let perf = max(1, intValue(topology["performance_cores"]) ?? 1)
        let efficiency = max(0, intValue(topology["efficiency_cores"]) ?? 0)
        switch pressureStage {
        case "critical":
            return max(1, min(logical - reserveCores, max(1, perf - 1)))
        case "warning":
            return max(1, min(logical - reserveCores, perf + min(efficiency, 1)))
        default:
            return max(1, min(logical - reserveCores, perf + min(efficiency, 4)))
        }
    }

    private static func interactiveReserveCores(
        settings: [String: Any],
        pressureStage: String,
        activeLabels: [String],
        topology: [String: Any]
    ) -> Int {
        let logical = max(1, intValue(topology["logical_cores"]) ?? 1)
        let configured = intValue(settings["native_resource_allocator_reserve_cores"])
        if let configured {
            return max(0, min(logical - 1, configured))
        }
        if activeLabels.contains("exit") {
            return min(logical - 1, 2)
        }
        if pressureStage == "critical" {
            return min(logical - 1, 2)
        }
        return min(logical - 1, 1)
    }

    private static func memoryBudget(memory: [String: Any], pressureStage: String) -> Int {
        let available = max(0, intValue(memory["available_memory_bytes"]) ?? 0)
        let reserveGiB: Double
        switch pressureStage {
        case "critical":
            reserveGiB = 1.5
        case "warning":
            reserveGiB = 2.0
        default:
            reserveGiB = 1.0
        }
        let reserveBytes = Int(reserveGiB * gibibyte)
        return max(256 * 1_048_576, available - reserveBytes)
    }

    private static func taskMemoryBudget(task: String, workers: Int, memoryBudgetBytes: Int, pressureStage: String) -> Int {
        if workers <= 0 {
            return 0
        }
        let ratio: Double
        switch task {
        case "stt", "stt_precision":
            ratio = pressureStage == "normal" ? 0.36 : 0.22
        case "subtitle", "subtitle_llm", "subtitle_optimize", "roughcut", "roughcut_llm":
            ratio = pressureStage == "normal" ? 0.28 : 0.16
        case "audio_extract", "vad", "cut_boundary", "cut_pioneer", "cut_follower":
            ratio = 0.18
        case "background":
            ratio = pressureStage == "normal" ? 0.08 : 0.02
        default:
            ratio = 0.10
        }
        return max(0, Int(Double(memoryBudgetBytes) * ratio))
    }

    private static func modelSlots(task: String, workers: Int, pressureStage: String) -> Int {
        if workers <= 0 {
            return 0
        }
        switch task {
        case "stt_precision":
            return pressureStage == "normal" ? min(4, workers) : 1
        case "stt":
            return pressureStage == "normal" ? min(2, workers) : 1
        case "subtitle", "subtitle_llm", "subtitle_optimize", "roughcut", "roughcut_llm":
            return 1
        default:
            return 0
        }
    }

    private static func acceleratorPlan(
        task: String,
        workers: Int,
        topology: [String: Any],
        pressureStage: String
    ) -> [String: Any] {
        let gpu = max(0, intValue(topology["gpu_cores"]) ?? 0)
        let neural = max(0, intValue(topology["neural_engine_cores"]) ?? 0)
        switch task {
        case "stt_precision":
            let gpuLanes = pressureStage == "normal" ? min(max(0, workers), max(1, gpu)) : 0
            let aneLanes = pressureStage == "normal" ? min(max(1, workers), max(1, neural)) : 1
            return [
                "policy": "whisperkit_ane_gpu_saturation",
                "prefer": ["ane", "gpu", "cpu"],
                "gpu_lanes": gpuLanes,
                "ane_lanes": aneLanes,
            ]
        case "stt", "stt1", "stt2":
            return [
                "policy": "whisperkit_balanced",
                "prefer": ["ane", "gpu", "cpu"],
                "gpu_lanes": min(max(0, workers), max(1, gpu)),
                "ane_lanes": min(max(1, workers), max(1, neural)),
            ]
        default:
            return [
                "policy": "cpu_balanced",
                "prefer": ["cpu"],
                "gpu_lanes": 0,
                "ane_lanes": 0,
            ]
        }
    }

    private static func computeUnits(task: String, pressureStage: String) -> String {
        switch task {
        case "stt_precision", "stt", "stt1", "stt2":
            return pressureStage == "critical" ? "cpuAndNeuralEngine" : "all"
        default:
            return "cpuOnly"
        }
    }

    private static func shouldPause(task: String, pressureStage: String, workers: Int) -> Bool {
        shouldHardPause(task: task, pressureStage: pressureStage) || (task == "background" && workers <= 0)
    }

    private static func reason(task: String, pressureStage: String) -> String {
        if shouldHardPause(task: task, pressureStage: pressureStage) {
            return "pause_low_priority_under_critical_pressure"
        }
        if pressureStage == "critical" {
            return "reserve_memory_and_interactive_cores"
        }
        if pressureStage == "warning" {
            return "reduce_efficiency_core_fanout"
        }
        if task == "stt_precision" {
            return "prefer_whisperkit_ane_gpu_saturation"
        }
        return "use_available_apple_core_budget"
    }

    private static func shouldHardPause(task: String, pressureStage: String) -> Bool {
        guard pressureStage == "critical" else { return false }
        return task == "background" || task == "roughcut" || task == "roughcut_llm"
    }

    private static func attachDynamicState(
        _ allocation: [String: Any],
        previous: [String: Any]?,
        pressureStage: String
    ) -> [String: Any] {
        var out = allocation
        let currentWorkers = intValue(allocation["workers"]) ?? 0
        let previousWorkers = intValue(previous?["workers"]) ?? 0
        let delta = currentWorkers - previousWorkers
        out["previous_workers"] = previousWorkers
        out["worker_delta"] = delta
        out["action"] = allocationAction(
            task: normalizedTask(allocation["task"]),
            workers: currentWorkers,
            previousWorkers: previousWorkers,
            shouldPause: boolValue(allocation["should_pause"]),
            pressureStage: pressureStage
        )
        out["lease_ms"] = leaseMilliseconds(task: normalizedTask(allocation["task"]), pressureStage: pressureStage)
        out["reclaim_deadline_ms"] = reclaimDeadlineMilliseconds(pressureStage: pressureStage)
        out["allocate_deadline_ms"] = allocateDeadlineMilliseconds(pressureStage: pressureStage)
        return out
    }

    private static func dynamicTransition(
        current: [[String: Any]],
        previous: [String: [String: Any]],
        pressureStage: String,
        activeLabels: [String]
    ) -> [String: Any] {
        var actions: [[String: Any]] = []
        var currentTasks: Set<String> = []
        var currentWorkersTotal = 0
        var previousWorkersTotal = 0
        var currentMemoryTotal = 0
        var previousMemoryTotal = 0

        for allocation in current {
            let task = normalizedTask(allocation["task"])
            currentTasks.insert(task)
            let currentWorkers = intValue(allocation["workers"]) ?? 0
            let previousWorkers = intValue(previous[task]?["workers"]) ?? 0
            let currentMemory = intValue(allocation["memory_budget_bytes"]) ?? 0
            let previousMemory = intValue(previous[task]?["memory_budget_bytes"]) ?? 0
            currentWorkersTotal += currentWorkers
            previousWorkersTotal += previousWorkers
            currentMemoryTotal += currentMemory
            previousMemoryTotal += previousMemory
            let action = allocationAction(
                task: task,
                workers: currentWorkers,
                previousWorkers: previousWorkers,
                shouldPause: boolValue(allocation["should_pause"]),
                pressureStage: pressureStage
            )
            if action != "hold" {
                actions.append(actionPayload(
                    task: task,
                    action: action,
                    currentWorkers: currentWorkers,
                    previousWorkers: previousWorkers,
                    currentMemoryBytes: currentMemory,
                    previousMemoryBytes: previousMemory,
                    pressureStage: pressureStage
                ))
            }
        }

        for (task, previousAllocation) in previous where !currentTasks.contains(task) {
            let previousWorkers = intValue(previousAllocation["workers"]) ?? 0
            let previousMemory = intValue(previousAllocation["memory_budget_bytes"]) ?? 0
            previousWorkersTotal += previousWorkers
            previousMemoryTotal += previousMemory
            if previousWorkers > 0 || previousMemory > 0 {
                actions.append(actionPayload(
                    task: task,
                    action: "reclaim",
                    currentWorkers: 0,
                    previousWorkers: previousWorkers,
                    currentMemoryBytes: 0,
                    previousMemoryBytes: previousMemory,
                    pressureStage: pressureStage
                ))
            }
        }

        actions.sort { left, right in
            let leftAction = actionSortWeight(String(describing: left["action"] ?? "hold"))
            let rightAction = actionSortWeight(String(describing: right["action"] ?? "hold"))
            if leftAction == rightAction {
                return taskPriority(["task": left["task"] ?? ""]) > taskPriority(["task": right["task"] ?? ""])
            }
            return leftAction > rightAction
        }

        let reclaimActions = actions.filter { action in
            let kind = String(describing: action["action"] ?? "")
            return kind == "reclaim" || kind == "shrink" || kind == "pause"
        }
        let allocateActions = actions.filter { action in
            let kind = String(describing: action["action"] ?? "")
            return kind == "allocate" || kind == "expand"
        }
        let activePipeline = activeLabels.contains("pipeline")
            || activeLabels.contains("cut_boundary")
            || activeLabels.contains("stt")
            || activeLabels.contains("subtitle_llm")
            || activeLabels.contains("subtitle_optimize")
        return [
            "schema": "ai_subtitle_studio.native_resource_allocator.dynamic.v1",
            "mode": dynamicMode(pressureStage: pressureStage, hasReclaim: !reclaimActions.isEmpty),
            "pressure_stage": pressureStage,
            "active_labels": activeLabels,
            "next_poll_ms": nextPollMilliseconds(pressureStage: pressureStage, activePipeline: activePipeline),
            "reclaim_deadline_ms": reclaimDeadlineMilliseconds(pressureStage: pressureStage),
            "allocate_deadline_ms": allocateDeadlineMilliseconds(pressureStage: pressureStage),
            "changed": !actions.isEmpty,
            "worker_delta": currentWorkersTotal - previousWorkersTotal,
            "memory_budget_delta_bytes": currentMemoryTotal - previousMemoryTotal,
            "actions": actions,
            "reclaim": reclaimActions,
            "allocate": allocateActions,
            "stage_order": current.map { normalizedTask($0["task"]) },
        ]
    }

    private static func allocationAction(
        task: String,
        workers: Int,
        previousWorkers: Int,
        shouldPause: Bool,
        pressureStage: String
    ) -> String {
        if shouldPause || shouldHardPause(task: task, pressureStage: pressureStage) {
            return previousWorkers > 0 ? "pause" : "hold"
        }
        if workers <= 0 && previousWorkers > 0 {
            return "reclaim"
        }
        if workers > 0 && previousWorkers <= 0 {
            return "allocate"
        }
        if workers > previousWorkers {
            return "expand"
        }
        if workers < previousWorkers {
            return "shrink"
        }
        return "hold"
    }

    private static func actionPayload(
        task: String,
        action: String,
        currentWorkers: Int,
        previousWorkers: Int,
        currentMemoryBytes: Int,
        previousMemoryBytes: Int,
        pressureStage: String
    ) -> [String: Any] {
        [
            "task": task,
            "action": action,
            "workers": currentWorkers,
            "previous_workers": previousWorkers,
            "worker_delta": currentWorkers - previousWorkers,
            "memory_budget_bytes": currentMemoryBytes,
            "previous_memory_budget_bytes": previousMemoryBytes,
            "memory_budget_delta_bytes": currentMemoryBytes - previousMemoryBytes,
            "priority": taskPriority(["task": task]),
            "lease_ms": leaseMilliseconds(task: task, pressureStage: pressureStage),
            "reclaim_deadline_ms": reclaimDeadlineMilliseconds(pressureStage: pressureStage),
            "allocate_deadline_ms": allocateDeadlineMilliseconds(pressureStage: pressureStage),
        ]
    }

    private static func actionSortWeight(_ action: String) -> Int {
        switch action {
        case "pause":
            return 50
        case "reclaim":
            return 45
        case "shrink":
            return 40
        case "allocate":
            return 30
        case "expand":
            return 20
        default:
            return 0
        }
    }

    private static func dynamicMode(pressureStage: String, hasReclaim: Bool) -> String {
        if pressureStage == "critical" {
            return "immediate_reclaim"
        }
        if pressureStage == "warning" {
            return hasReclaim ? "fast_reclaim" : "fast_rebalance"
        }
        return hasReclaim ? "balanced_reclaim" : "balanced_expand"
    }

    private static func nextPollMilliseconds(pressureStage: String, activePipeline: Bool) -> Int {
        switch pressureStage {
        case "critical":
            return activePipeline ? 120 : 180
        case "warning":
            return activePipeline ? 180 : 260
        default:
            return activePipeline ? 300 : 450
        }
    }

    private static func reclaimDeadlineMilliseconds(pressureStage: String) -> Int {
        switch pressureStage {
        case "critical":
            return 0
        case "warning":
            return 40
        default:
            return 120
        }
    }

    private static func allocateDeadlineMilliseconds(pressureStage: String) -> Int {
        switch pressureStage {
        case "critical":
            return 25
        case "warning":
            return 35
        default:
            return 80
        }
    }

    private static func leaseMilliseconds(task: String, pressureStage: String) -> Int {
        if task == "background" || task == "roughcut" || task == "roughcut_llm" {
            return pressureStage == "normal" ? 800 : 180
        }
        switch pressureStage {
        case "critical":
            return 220
        case "warning":
            return 420
        default:
            return 900
        }
    }

    private static func compactMemory(_ memory: [String: Any]) -> [String: Any] {
        [
            "memory_bytes": intValue(memory["memory_bytes"]) ?? 0,
            "available_memory_bytes": intValue(memory["available_memory_bytes"]) ?? 0,
            "available_memory_ratio": doubleValue(memory["available_memory_ratio"]) ?? 0.0,
            "compressed_memory_ratio": doubleValue(memory["compressed_memory_ratio"]) ?? 0.0,
            "process_rss_bytes": intValue(memory["process_rss_bytes"]) ?? 0,
            "pressure_stage": normalizedStage(memory["pressure_stage"]),
        ]
    }

    private static func performanceCoreCount(fallbackPhysical: Int) -> Int {
        if let perfLevel0 = sysctlInt("hw.perflevel0.physicalcpu"), perfLevel0 > 0 {
            return perfLevel0
        }
        if let perfLevel0 = sysctlInt("hw.perflevel0.logicalcpu"), perfLevel0 > 0 {
            return perfLevel0
        }
        return max(1, fallbackPhysical / 2)
    }

    private static func sysctlInt(_ name: String) -> Int? {
        var value: Int32 = 0
        var size = MemoryLayout<Int32>.size
        let result = sysctlbyname(name, &value, &size, nil, 0)
        guard result == 0 else {
            return nil
        }
        return Int(value)
    }

    private static func normalizedTask(_ value: Any?) -> String {
        let text = String(describing: value ?? "worker")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        return text.isEmpty ? "worker" : text
    }

    private static func taskPriority(_ request: [String: Any]) -> Int {
        if let configured = intValue(request["priority"]) {
            return configured
        }
        switch normalizedTask(request["task"]) {
        case "ui":
            return 120
        case "timeline":
            return 115
        case "cut_boundary", "cut_pioneer":
            return 110
        case "cut_follower":
            return 105
        case "stt", "stt1":
            return 100
        case "stt_window":
            return 96
        case "stt_precision":
            return 96
        case "stt2":
            return 90
        case "subtitle", "subtitle_llm":
            return 80
        case "subtitle_optimize":
            return 78
        case "audio_extract", "audio":
            return 70
        case "vad":
            return 65
        case "roughcut", "roughcut_llm":
            return 45
        case "background":
            return 10
        default:
            return 50
        }
    }

    private static func normalizedStage(_ value: Any?) -> String {
        let text = String(describing: value ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        if text == "critical" || text == "warning" || text == "normal" {
            return text
        }
        return "normal"
    }

    private static func stringArray(_ value: Any?) -> [String] {
        guard let items = value as? [Any] else {
            return []
        }
        var out: [String] = []
        for item in items {
            let text = String(describing: item).trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if !text.isEmpty && !out.contains(text) {
                out.append(text)
            }
        }
        return out
    }

    private static func allocationMap(_ value: Any?) -> [String: [String: Any]] {
        var source: [String: Any] = [:]
        if let plan = value as? [String: Any] {
            source = plan["allocations"] as? [String: Any] ?? plan
        } else {
            source = [:]
        }
        var out: [String: [String: Any]] = [:]
        for (key, raw) in source {
            guard let row = raw as? [String: Any] else { continue }
            let task = normalizedTask(row["task"] ?? key)
            out[task] = row
        }
        return out
    }

    private static func intValue(_ value: Any?) -> Int? {
        if let number = value as? NSNumber {
            return number.intValue
        }
        if let number = value as? Int {
            return number
        }
        if let number = value as? UInt64 {
            return number > UInt64(Int.max) ? Int.max : Int(number)
        }
        if let number = value as? Double {
            return Int(number)
        }
        if let text = value as? String, let parsed = Double(text.trimmingCharacters(in: .whitespacesAndNewlines)) {
            return Int(parsed)
        }
        return nil
    }

    private static func doubleValue(_ value: Any?) -> Double? {
        if let number = value as? NSNumber {
            return number.doubleValue
        }
        if let number = value as? Double {
            return number
        }
        if let number = value as? Int {
            return Double(number)
        }
        if let text = value as? String, let parsed = Double(text.trimmingCharacters(in: .whitespacesAndNewlines)) {
            return parsed
        }
        return nil
    }

    private static func boolValue(_ value: Any?) -> Bool {
        if let value = value as? Bool {
            return value
        }
        if let value = value as? NSNumber {
            return value.boolValue
        }
        let text = String(describing: value ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        return ["1", "true", "yes", "on"].contains(text)
    }

    private static func isAPIModel(settings: [String: Any]) -> Bool {
        let provider = String(describing: settings["selected_llm_provider"] ?? settings["llm_provider"] ?? "")
            .lowercased()
        let model = String(describing: settings["selected_model"] ?? settings["llm_model"] ?? "")
            .lowercased()
        return provider.contains("openai")
            || provider.contains("gemini")
            || provider.contains("anthropic")
            || model.hasPrefix("gpt")
            || model.contains("gemini")
    }
}
