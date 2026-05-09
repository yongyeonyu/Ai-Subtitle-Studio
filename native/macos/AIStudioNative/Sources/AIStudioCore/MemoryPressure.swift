import Darwin
import Foundation

public enum MemoryPressure {
    private static let gibibyte = 1_073_741_824.0

    public static func snapshot(payload: [String: Any] = [:]) -> [String: Any] {
        let settings = payload["settings"] as? [String: Any] ?? payload
        let pid = intSetting(payload["pid"]) ?? Int(ProcessInfo.processInfo.processIdentifier)
        let physicalBytes = UInt64(ProcessInfo.processInfo.physicalMemory)
        let warningReserveBytes = bytesFromGiB(
            doubleSetting(settings["macos_memory_warning_reserve_gb"], defaultValue: 3.0)
        )
        let criticalReserveBytes = bytesFromGiB(
            doubleSetting(settings["macos_memory_critical_reserve_gb"], defaultValue: 1.5)
        )
        let compressedWarningRatio = doubleSetting(
            settings["macos_memory_compressed_warning_ratio"],
            defaultValue: 0.22
        )
        let compressedCriticalRatio = doubleSetting(
            settings["macos_memory_compressed_critical_ratio"],
            defaultValue: 0.30
        )

        let vm = virtualMemorySnapshot(physicalBytes: physicalBytes)
        let availableBytes = vm.availableBytes
        let availableRatio = ratio(availableBytes, physicalBytes)
        let compressedRatio = ratio(vm.compressedBytes, physicalBytes)
        let pressureStage = stage(
            availableBytes: availableBytes,
            availableRatio: availableRatio,
            compressedRatio: compressedRatio,
            warningReserveBytes: warningReserveBytes,
            criticalReserveBytes: criticalReserveBytes,
            compressedWarningRatio: compressedWarningRatio,
            compressedCriticalRatio: compressedCriticalRatio
        )

        var result: [String: Any] = [
            "source": "swift_mach_vm",
            "ok": vm.ok,
            "pid": pid,
            "memory_bytes": intBytes(physicalBytes),
            "available_memory_bytes": intBytes(availableBytes),
            "available_memory_ratio": round4(availableRatio),
            "free_bytes": intBytes(vm.freeBytes),
            "inactive_bytes": intBytes(vm.inactiveBytes),
            "speculative_bytes": intBytes(vm.speculativeBytes),
            "active_bytes": intBytes(vm.activeBytes),
            "wired_bytes": intBytes(vm.wiredBytes),
            "compressed_bytes": intBytes(vm.compressedBytes),
            "compressed_memory_ratio": round4(compressedRatio),
            "page_size": Int(vm.pageSize),
            "pressure_stage": pressureStage,
            "recommended_action": action(for: pressureStage),
            "warning_reserve_bytes": intBytes(warningReserveBytes),
            "critical_reserve_bytes": intBytes(criticalReserveBytes),
            "compressed_warning_ratio": round4(compressedWarningRatio),
            "compressed_critical_ratio": round4(compressedCriticalRatio)
        ]
        if let process = processSnapshot(pid: pid) {
            result["process_rss_bytes"] = intBytes(process.rssBytes)
            result["process_virtual_bytes"] = intBytes(process.virtualBytes)
            result["process_resident_ratio"] = round4(ratio(process.rssBytes, physicalBytes))
        }
        if let error = vm.error {
            result["error"] = error
        }
        return result
    }

    private struct VirtualMemorySnapshot {
        let ok: Bool
        let pageSize: vm_size_t
        let freeBytes: UInt64
        let speculativeBytes: UInt64
        let inactiveBytes: UInt64
        let activeBytes: UInt64
        let wiredBytes: UInt64
        let compressedBytes: UInt64
        let availableBytes: UInt64
        let error: String?
    }

    private struct ProcessSnapshot {
        let rssBytes: UInt64
        let virtualBytes: UInt64
    }

    private static func virtualMemorySnapshot(physicalBytes: UInt64) -> VirtualMemorySnapshot {
        var pageSize: vm_size_t = 0
        let host = mach_host_self()
        if host_page_size(host, &pageSize) != KERN_SUCCESS || pageSize == 0 {
            pageSize = 4096
        }

        var stats = vm_statistics64_data_t()
        var count = mach_msg_type_number_t(
            MemoryLayout<vm_statistics64_data_t>.stride / MemoryLayout<integer_t>.stride
        )
        let status = withUnsafeMutablePointer(to: &stats) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { rebound in
                host_statistics64(host, HOST_VM_INFO64, rebound, &count)
            }
        }
        guard status == KERN_SUCCESS else {
            return VirtualMemorySnapshot(
                ok: false,
                pageSize: pageSize,
                freeBytes: 0,
                speculativeBytes: 0,
                inactiveBytes: 0,
                activeBytes: 0,
                wiredBytes: 0,
                compressedBytes: 0,
                availableBytes: 0,
                error: "host_statistics64 failed: \(status)"
            )
        }

        let page = UInt64(pageSize)
        let freeBytes = UInt64(stats.free_count) * page
        let speculativeBytes = UInt64(stats.speculative_count) * page
        let inactiveBytes = UInt64(stats.inactive_count) * page
        let activeBytes = UInt64(stats.active_count) * page
        let wiredBytes = UInt64(stats.wire_count) * page
        let compressedBytes = UInt64(stats.compressor_page_count) * page
        // macOS can reclaim a meaningful part of inactive pages, but not all of
        // them instantly. Count half as stop/exit headroom so scheduling stays
        // conservative under memory pressure.
        let conservativeAvailable = freeBytes + speculativeBytes + inactiveBytes / 2
        let availableBytes = physicalBytes > 0 ? min(physicalBytes, conservativeAvailable) : conservativeAvailable
        return VirtualMemorySnapshot(
            ok: true,
            pageSize: pageSize,
            freeBytes: freeBytes,
            speculativeBytes: speculativeBytes,
            inactiveBytes: inactiveBytes,
            activeBytes: activeBytes,
            wiredBytes: wiredBytes,
            compressedBytes: compressedBytes,
            availableBytes: availableBytes,
            error: nil
        )
    }

    private static func processSnapshot(pid: Int) -> ProcessSnapshot? {
        var info = proc_taskinfo()
        let expectedSize = MemoryLayout<proc_taskinfo>.stride
        let readSize = withUnsafeMutablePointer(to: &info) { pointer -> Int32 in
            proc_pidinfo(Int32(pid), PROC_PIDTASKINFO, 0, pointer, Int32(expectedSize))
        }
        guard readSize == Int32(expectedSize) else {
            return taskInfoForCurrentProcess(pid: pid)
        }
        return ProcessSnapshot(
            rssBytes: UInt64(max(0, info.pti_resident_size)),
            virtualBytes: UInt64(max(0, info.pti_virtual_size))
        )
    }

    private static func taskInfoForCurrentProcess(pid: Int) -> ProcessSnapshot? {
        guard pid == Int(ProcessInfo.processInfo.processIdentifier) else {
            return nil
        }
        var info = task_basic_info_data_t()
        var count = mach_msg_type_number_t(
            MemoryLayout<task_basic_info_data_t>.stride / MemoryLayout<natural_t>.stride
        )
        let status = withUnsafeMutablePointer(to: &info) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { rebound in
                task_info(mach_task_self_, task_flavor_t(TASK_BASIC_INFO), rebound, &count)
            }
        }
        guard status == KERN_SUCCESS else {
            return nil
        }
        return ProcessSnapshot(
            rssBytes: UInt64(info.resident_size),
            virtualBytes: UInt64(info.virtual_size)
        )
    }

    private static func stage(
        availableBytes: UInt64,
        availableRatio: Double,
        compressedRatio: Double,
        warningReserveBytes: UInt64,
        criticalReserveBytes: UInt64,
        compressedWarningRatio: Double,
        compressedCriticalRatio: Double
    ) -> String {
        if availableBytes <= criticalReserveBytes || availableRatio <= 0.10 || compressedRatio >= compressedCriticalRatio {
            return "critical"
        }
        if availableBytes <= warningReserveBytes || availableRatio <= 0.18 || compressedRatio >= compressedWarningRatio {
            return "warning"
        }
        return "normal"
    }

    private static func action(for stage: String) -> String {
        switch stage {
        case "critical":
            return "trim_caches_models_and_keep_exit_reserve"
        case "warning":
            return "trim_runtime_caches"
        default:
            return "none"
        }
    }

    private static func ratio(_ numerator: UInt64, _ denominator: UInt64) -> Double {
        guard denominator > 0 else {
            return 0.0
        }
        return max(0.0, min(1.0, Double(numerator) / Double(denominator)))
    }

    private static func round4(_ value: Double) -> Double {
        (value * 10_000.0).rounded() / 10_000.0
    }

    private static func bytesFromGiB(_ value: Double) -> UInt64 {
        UInt64(max(0.0, value) * gibibyte)
    }

    private static func intBytes(_ value: UInt64) -> Int {
        value > UInt64(Int.max) ? Int.max : Int(value)
    }

    private static func doubleSetting(_ value: Any?, defaultValue: Double) -> Double {
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
        return defaultValue
    }

    private static func intSetting(_ value: Any?) -> Int? {
        if let number = value as? NSNumber {
            return number.intValue
        }
        if let number = value as? Int {
            return number
        }
        if let text = value as? String, let parsed = Int(text.trimmingCharacters(in: .whitespacesAndNewlines)) {
            return parsed
        }
        return nil
    }
}
