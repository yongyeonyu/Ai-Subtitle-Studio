import Foundation

public enum AudioChunkManifest {
    private static let vadStartRegex = try? NSRegularExpression(
        pattern: #"vad_\d+_([0-9.]+)\.wav$"#,
        options: [.caseInsensitive]
    )

    public static func manifest(payload: [String: Any]) -> [String: Any] {
        let chunkDir = stringValue(payload["chunk_dir"])
        guard !chunkDir.isEmpty else {
            return ["error": "Missing chunk_dir"]
        }
        let fallbackStep = max(0, doubleValue(payload["fallback_step_sec"], defaultValue: 0))
        let requireVADStart = boolValue(payload["require_vad_start"])
        let root = URL(fileURLWithPath: chunkDir, isDirectory: true)

        do {
            let urls = try FileManager.default.contentsOfDirectory(
                at: root,
                includingPropertiesForKeys: [.isRegularFileKey],
                options: [.skipsHiddenFiles]
            )
            var rows: [[String: Any]] = []
            rows.reserveCapacity(urls.count)
            for url in urls {
                guard url.pathExtension.lowercased() == "wav" else { continue }
                let values = try? url.resourceValues(forKeys: [.isRegularFileKey])
                if values?.isRegularFile == false { continue }
                let name = url.lastPathComponent
                let parsed = vadStart(from: name)
                if requireVADStart && parsed == nil { continue }
                rows.append([
                    "name": name,
                    "path": url.path,
                    "start": parsed ?? 0.0,
                    "duration": wavDuration(url: url),
                    "has_vad_start": parsed != nil,
                ])
            }
            rows.sort { left, right in
                let lhs = doubleValue(left["start"], defaultValue: 0)
                let rhs = doubleValue(right["start"], defaultValue: 0)
                if lhs == rhs {
                    return stringValue(left["name"]) < stringValue(right["name"])
                }
                return lhs < rhs
            }
            if fallbackStep > 0 {
                for index in rows.indices where !(rows[index]["has_vad_start"] as? Bool ?? false) {
                    rows[index]["start"] = Double(index) * fallbackStep
                }
            }
            for index in rows.indices {
                let start = doubleValue(rows[index]["start"], defaultValue: 0)
                let duration = max(0, doubleValue(rows[index]["duration"], defaultValue: 0))
                rows[index]["duration"] = duration
                rows[index]["end"] = start + duration
            }
            return ["chunks": rows, "backend": "swift"]
        } catch {
            return ["error": String(describing: error).replacingOccurrences(of: "\n", with: " ")]
        }
    }

    private static func vadStart(from name: String) -> Double? {
        guard let regex = vadStartRegex else { return nil }
        let range = NSRange(name.startIndex..<name.endIndex, in: name)
        guard
            let match = regex.firstMatch(in: name, options: [], range: range),
            match.numberOfRanges >= 2,
            let swiftRange = Range(match.range(at: 1), in: name)
        else {
            return nil
        }
        return Double(name[swiftRange])
    }

    private static func wavDuration(url: URL) -> Double {
        guard let handle = try? FileHandle(forReadingFrom: url) else {
            return 0
        }
        defer { try? handle.close() }

        let header = handle.readData(ofLength: 12)
        guard header.count == 12, ascii(header, 0, 4) == "RIFF", ascii(header, 8, 4) == "WAVE" else {
            return 0
        }
        var cursor: UInt64 = 12
        var byteRate: UInt32 = 0
        var dataSize: UInt32 = 0

        while true {
            let chunkHeader = handle.readData(ofLength: 8)
            guard chunkHeader.count == 8 else { break }
            cursor += 8
            let chunkID = ascii(chunkHeader, 0, 4)
            let chunkSize = readUInt32LE(chunkHeader, 4)
            let bodyStart = cursor
            let nextChunk = bodyStart + UInt64(chunkSize) + UInt64(chunkSize % 2)

            if chunkID == "fmt " {
                let body = handle.readData(ofLength: min(Int(chunkSize), 16))
                if body.count >= 12 {
                    byteRate = readUInt32LE(body, 8)
                }
                try? handle.seek(toOffset: nextChunk)
                cursor = nextChunk
            } else if chunkID == "data" {
                dataSize = chunkSize
                break
            } else {
                try? handle.seek(toOffset: nextChunk)
                cursor = nextChunk
            }
        }
        guard byteRate > 0, dataSize > 0 else {
            return 0
        }
        return Double(dataSize) / Double(byteRate)
    }

    private static func ascii(_ data: Data, _ offset: Int, _ count: Int) -> String {
        guard offset >= 0, offset + count <= data.count else {
            return ""
        }
        return String(data: data.subdata(in: offset..<(offset + count)), encoding: .ascii) ?? ""
    }

    private static func readUInt32LE(_ data: Data, _ offset: Int) -> UInt32 {
        guard offset + 4 <= data.count else { return 0 }
        return UInt32(data[offset])
            | (UInt32(data[offset + 1]) << 8)
            | (UInt32(data[offset + 2]) << 16)
            | (UInt32(data[offset + 3]) << 24)
    }

    private static func stringValue(_ value: Any?) -> String {
        guard let value else { return "" }
        return String(describing: value)
    }

    private static func doubleValue(_ value: Any?, defaultValue: Double) -> Double {
        if let value = value as? Double { return value }
        if let value = value as? NSNumber { return value.doubleValue }
        if let value = value as? String, let parsed = Double(value) { return parsed }
        return defaultValue
    }

    private static func boolValue(_ value: Any?) -> Bool {
        if let value = value as? Bool { return value }
        let text = stringValue(value).trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return ["1", "true", "yes", "on"].contains(text)
    }
}
