import Foundation

public enum RuntimeDiskCache {
    struct CacheEntry {
        let mtime: Double
        let size: Int64
        let path: String
        let basename: String
    }

    public static func prune(payload: [String: Any]) -> [String: Any] {
        let paths = stringArray(payload["paths"])
        let targetTotalBytes = max(0, int64Value(payload["target_total_bytes"]))
        if paths.isEmpty {
            return response(
                removedFiles: 0,
                removedBytes: 0,
                remainingBytes: 0,
                targetTotalBytes: targetTotalBytes,
                scannedFiles: 0
            )
        }

        let fileManager = FileManager.default
        var entries: [CacheEntry] = []
        var totalBytes: Int64 = 0
        for rawPath in paths {
            let expanded = (rawPath as NSString).expandingTildeInPath
            var isDirectory: ObjCBool = false
            guard fileManager.fileExists(atPath: expanded, isDirectory: &isDirectory) else {
                continue
            }
            if isDirectory.boolValue {
                scanDirectory(expanded, fileManager: fileManager, entries: &entries, totalBytes: &totalBytes)
            } else if let entry = fileEntry(expanded, fileManager: fileManager) {
                entries.append(entry)
                totalBytes += entry.size
            }
        }

        guard totalBytes > targetTotalBytes else {
            return response(
                removedFiles: 0,
                removedBytes: 0,
                remainingBytes: totalBytes,
                targetTotalBytes: targetTotalBytes,
                scannedFiles: entries.count
            )
        }

        let scannedFiles = entries.count
        heapifyOldestFirst(&entries)

        var removedFiles = 0
        var removedBytes: Int64 = 0
        while totalBytes > targetTotalBytes, let entry = popOldest(&entries) {
            do {
                try fileManager.removeItem(atPath: entry.path)
            } catch {
                continue
            }
            totalBytes -= entry.size
            removedFiles += 1
            removedBytes += entry.size
        }

        return response(
            removedFiles: removedFiles,
            removedBytes: removedBytes,
            remainingBytes: max(0, totalBytes),
            targetTotalBytes: targetTotalBytes,
            scannedFiles: scannedFiles
        )
    }

    static func heapifyOldestFirst(_ entries: inout [CacheEntry]) {
        guard entries.count > 1 else {
            return
        }
        for index in stride(from: (entries.count / 2) - 1, through: 0, by: -1) {
            siftDown(&entries, from: index)
        }
    }

    static func popOldest(_ entries: inout [CacheEntry]) -> CacheEntry? {
        guard !entries.isEmpty else {
            return nil
        }
        if entries.count == 1 {
            return entries.removeLast()
        }
        let oldest = entries[0]
        entries[0] = entries.removeLast()
        siftDown(&entries, from: 0)
        return oldest
    }

    static func siftDown(_ entries: inout [CacheEntry], from start: Int) {
        var parent = start
        while true {
            let left = (parent * 2) + 1
            let right = left + 1
            var candidate = parent
            if left < entries.count && isOlder(entries[left], than: entries[candidate]) {
                candidate = left
            }
            if right < entries.count && isOlder(entries[right], than: entries[candidate]) {
                candidate = right
            }
            if candidate == parent {
                return
            }
            entries.swapAt(parent, candidate)
            parent = candidate
        }
    }

    static func isOlder(_ lhs: CacheEntry, than rhs: CacheEntry) -> Bool {
        if lhs.mtime == rhs.mtime {
            return lhs.basename < rhs.basename
        }
        return lhs.mtime < rhs.mtime
    }

    static func scanDirectory(
        _ root: String,
        fileManager: FileManager,
        entries: inout [CacheEntry],
        totalBytes: inout Int64
    ) {
        let url = URL(fileURLWithPath: root, isDirectory: true)
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .contentModificationDateKey, .fileSizeKey]
        guard let enumerator = fileManager.enumerator(
            at: url,
            includingPropertiesForKeys: Array(keys),
            options: [],
            errorHandler: { _, _ in true }
        ) else {
            return
        }
        for case let fileURL as URL in enumerator {
            guard let entry = fileEntry(fileURL, keys: keys) else {
                continue
            }
            entries.append(entry)
            totalBytes += entry.size
        }
    }

    static func fileEntry(_ path: String, fileManager: FileManager) -> CacheEntry? {
        let url = URL(fileURLWithPath: path)
        return fileEntry(url, keys: [.isRegularFileKey, .contentModificationDateKey, .fileSizeKey])
    }

    static func fileEntry(_ url: URL, keys: Set<URLResourceKey>) -> CacheEntry? {
        let values: URLResourceValues
        do {
            values = try url.resourceValues(forKeys: keys)
        } catch {
            return nil
        }
        guard values.isRegularFile == true else {
            return nil
        }
        let size = max(0, Int64(values.fileSize ?? 0))
        return CacheEntry(
            mtime: values.contentModificationDate?.timeIntervalSince1970 ?? 0.0,
            size: size,
            path: url.path,
            basename: url.lastPathComponent
        )
    }

    static func response(
        removedFiles: Int,
        removedBytes: Int64,
        remainingBytes: Int64,
        targetTotalBytes: Int64,
        scannedFiles: Int
    ) -> [String: Any] {
        [
            "removed_files": max(0, removedFiles),
            "removed_bytes": max(0, removedBytes),
            "remaining_bytes": max(0, remainingBytes),
            "target_total_bytes": max(0, targetTotalBytes),
            "scanned_files": max(0, scannedFiles),
            "used_native": true,
        ]
    }

    static func stringArray(_ value: Any?) -> [String] {
        guard let values = value as? [Any] else {
            return []
        }
        return values.compactMap { item in
            let text = String(describing: item).trimmingCharacters(in: .whitespacesAndNewlines)
            return text.isEmpty ? nil : text
        }
    }

    static func int64Value(_ value: Any?) -> Int64 {
        switch value {
        case let value as Int64:
            return value
        case let value as Int:
            return Int64(value)
        case let value as NSNumber:
            return value.int64Value
        case let value as String:
            return Int64(value.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0
        default:
            return 0
        }
    }
}
