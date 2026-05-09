import Darwin
import Foundation

public enum ProjectJSONError: Error, LocalizedError {
    case notObject
    case invalidJSON
    case writeFailed(String)

    public var errorDescription: String? {
        switch self {
        case .notObject:
            return "Project JSON must be an object"
        case .invalidJSON:
            return "Invalid project JSON"
        case .writeFailed(let path):
            return "Unable to write project JSON: \(path)"
        }
    }
}

public enum ProjectJSON {
    private static let runtimeKeys: Set<String> = [
        "_project_file_path",
        "_external_subtitle_segments_cache",
        "_external_stt_tracks_cache",
    ]

    public static func readObject(from url: URL) throws -> [String: Any] {
        let data = try Data(contentsOf: url)
        let object = try JSONSerialization.jsonObject(with: data)
        guard let dictionary = object as? [String: Any] else {
            throw ProjectJSONError.notObject
        }
        return dictionary
    }

    public static func normalizedData(from object: [String: Any]) throws -> Data {
        let stripped = stripRuntimeKeys(from: object)
        guard JSONSerialization.isValidJSONObject(stripped) else {
            throw ProjectJSONError.invalidJSON
        }
        var options: JSONSerialization.WritingOptions = [.prettyPrinted, .sortedKeys]
        if #available(macOS 10.15, *) {
            options.insert(.withoutEscapingSlashes)
        }
        var data = try JSONSerialization.data(withJSONObject: stripped, options: options)
        data.append(Data("\n".utf8))
        return data
    }

    public static func normalizedData(fromJSONData data: Data) throws -> Data {
        let object = try JSONSerialization.jsonObject(with: data)
        guard let dictionary = object as? [String: Any] else {
            throw ProjectJSONError.notObject
        }
        return try normalizedData(from: dictionary)
    }

    public static func atomicWrite(_ data: Data, to url: URL) throws {
        let directory = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let tempURL = directory.appendingPathComponent(".tmp-\(UUID().uuidString).json")

        FileManager.default.createFile(atPath: tempURL.path, contents: nil)
        let handle = try FileHandle(forWritingTo: tempURL)
        do {
            try handle.write(contentsOf: data)
            try handle.synchronize()
            try handle.close()
        } catch {
            try? handle.close()
            try? FileManager.default.removeItem(at: tempURL)
            throw error
        }

        if rename(tempURL.path, url.path) != 0 {
            try? FileManager.default.removeItem(at: tempURL)
            throw ProjectJSONError.writeFailed(url.path)
        }
    }

    public static func summary(for object: [String: Any]) -> [String: Any] {
        let media = object["media"] as? [[String: Any]] ?? []
        let subtitles = object["subtitles"] as? [String: Any] ?? [:]
        let editorState = object["editor_state"] as? [String: Any] ?? [:]
        let analysis = object["analysis"] as? [String: Any] ?? [:]
        let assetStorage = object["asset_storage"] as? [String: Any] ?? [:]
        let tracks = assetStorage["tracks"] as? [String: Any] ?? [:]
        return [
            "app": object["app"] as? String ?? "",
            "version": object["version"] as? String ?? "",
            "media_count": media.count,
            "subtitle_storage": subtitles["storage"] as? String ?? "",
            "has_editor_state": !editorState.isEmpty,
            "has_analysis": !analysis.isEmpty,
            "external_track_count": tracks.count,
        ]
    }

    private static func stripRuntimeKeys(from object: [String: Any]) -> [String: Any] {
        var output = object
        for key in runtimeKeys {
            output.removeValue(forKey: key)
        }
        return output
    }
}
