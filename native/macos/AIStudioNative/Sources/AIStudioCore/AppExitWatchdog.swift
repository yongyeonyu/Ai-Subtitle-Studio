import Darwin
import Foundation

public enum AppExitWatchdog {
    public struct Options: Equatable {
        public var pid: pid_t
        public var delayMs: Int
        public var termGraceMs: Int

        public init(pid: pid_t, delayMs: Int = 20, termGraceMs: Int = 50) {
            self.pid = pid
            self.delayMs = max(0, delayMs)
            self.termGraceMs = max(0, termGraceMs)
        }
    }

    public static func parseOptions(_ arguments: [String]) throws -> Options {
        var pid: pid_t = 0
        var delayMs = 20
        var termGraceMs = 50
        var index = 0
        while index < arguments.count {
            let key = arguments[index]
            guard index + 1 < arguments.count else {
                throw NSError(domain: "AppExitWatchdog", code: 1, userInfo: [NSLocalizedDescriptionKey: "Missing value for \(key)"])
            }
            let value = arguments[index + 1]
            switch key {
            case "--pid":
                pid = pid_t(Int32(Int(value) ?? 0))
            case "--delay-ms":
                delayMs = Int(value) ?? delayMs
            case "--term-grace-ms":
                termGraceMs = Int(value) ?? termGraceMs
            default:
                throw NSError(domain: "AppExitWatchdog", code: 2, userInfo: [NSLocalizedDescriptionKey: "Unknown option \(key)"])
            }
            index += 2
        }
        guard pid > 0 else {
            throw NSError(domain: "AppExitWatchdog", code: 3, userInfo: [NSLocalizedDescriptionKey: "Invalid pid"])
        }
        return Options(pid: pid, delayMs: delayMs, termGraceMs: termGraceMs)
    }

    public static func run(options: Options) {
        sleepMilliseconds(options.delayMs)
        let descendants = descendantPIDs(root: options.pid)
        terminate(descendants, signal: SIGTERM)
        terminate([options.pid], signal: SIGTERM)
        sleepMilliseconds(options.termGraceMs)
        terminate(descendants, signal: SIGKILL)
        if processExists(options.pid) {
            terminate([options.pid], signal: SIGKILL)
        }
    }

    private static func sleepMilliseconds(_ milliseconds: Int) {
        if milliseconds > 0 {
            usleep(useconds_t(milliseconds * 1_000))
        }
    }

    private static func processExists(_ pid: pid_t) -> Bool {
        if pid <= 0 {
            return false
        }
        if kill(pid, 0) == 0 {
            return true
        }
        return errno == EPERM
    }

    private static func terminate(_ pids: [pid_t], signal: Int32) {
        let selfPID = getpid()
        for pid in Set(pids) where pid > 0 && pid != selfPID {
            _ = kill(pid, signal)
        }
    }

    private static func processRows() -> [(pid: pid_t, ppid: pid_t)] {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/ps")
        process.arguments = ["-axo", "pid=,ppid="]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            return []
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        guard let output = String(data: data, encoding: .utf8) else {
            return []
        }
        return output.split(separator: "\n").compactMap { line in
            let parts = line.split(whereSeparator: { $0 == " " || $0 == "\t" })
            guard parts.count >= 2, let pid = Int32(parts[0]), let ppid = Int32(parts[1]) else {
                return nil
            }
            return (pid: pid_t(pid), ppid: pid_t(ppid))
        }
    }

    private static func descendantPIDs(root: pid_t) -> [pid_t] {
        let rows = processRows()
        var children: [pid_t: [pid_t]] = [:]
        for row in rows {
            children[row.ppid, default: []].append(row.pid)
        }
        var result: [pid_t] = []
        var stack = children[root] ?? []
        var seen = Set<pid_t>([root])
        while let pid = stack.popLast() {
            if seen.contains(pid) {
                continue
            }
            seen.insert(pid)
            result.append(pid)
            stack.append(contentsOf: children[pid] ?? [])
        }
        return result
    }
}
