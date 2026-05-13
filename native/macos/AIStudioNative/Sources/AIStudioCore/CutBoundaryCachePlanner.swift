import CryptoKit
import Foundation

public enum CutBoundaryCachePlanner {
    public static func settingsPayload(payload: [String: Any]) -> [String: Any] {
        let settings = dictValue(payload["settings"])
        return ["settings_payload": buildSettingsPayload(settings: settings)]
    }

    public static func plan(payload: [String: Any]) -> [String: Any] {
        let settings = dictValue(payload["settings"])
        let files = arrayOfDicts(payload["files"])
        let cacheRoot = stringValue(payload["cache_root"])
        let version = intValue(payload["version"], default: 7)
        let apiVersion = stringValue(payload["cut_boundary_api_version"])
        let algorithmVersion = stringValue(payload["cut_boundary_algorithm_version"])
        let algorithmID = stringValue(payload["cut_boundary_algorithm_id"])

        let settingsPayload = buildSettingsPayload(settings: settings)
        let basePayload: [String: Any] = [
            "version": version,
            "cut_boundary_api_version": apiVersion,
            "cut_boundary_algorithm_version": algorithmVersion,
            "cut_boundary_algorithm_id": algorithmID,
            "files": files,
            "settings": settingsPayload,
        ]
        let raw = normalizedJSONData(basePayload) ?? Data()
        let key = sha256Hex(data: raw).prefix(24)
        let cachePath = (cacheRoot as NSString).appendingPathComponent("cut_boundaries_\(key).json")
        return [
            "settings_payload": settingsPayload,
            "base_payload": basePayload,
            "cache_path": cachePath,
        ]
    }

    private static func buildSettingsPayload(settings: [String: Any]) -> [String: Any] {
        let durationSec = max(0.0, doubleValue(settings["cut_boundary_media_duration_sec"]))
        let durationBucket = durationSec > 0.0 ? Int((durationSec / 300.0).rounded(.down) * 300.0) : 0
        return [
            "scan_cut_auto_sample_step_sec": valueOrDefault(settings["scan_cut_auto_sample_step_sec"], default: 2.0),
            "scan_cut_auto_threshold": valueOrDefault(settings["scan_cut_auto_threshold"], default: valueOrDefault(settings["scan_cut_threshold"], default: 24.0)),
            "scan_cut_threshold": valueOrDefault(settings["scan_cut_threshold"], default: 24.0),
            "scan_cut_mode": stringValue(settings["scan_cut_mode"]),
            "scan_cut_boundary_level": stringValue(settings["scan_cut_boundary_level"], default: stringValue(settings["cut_boundary_level"], default: "medium")),
            "scan_cut_boundary_resolved_level": stringValue(settings["scan_cut_boundary_resolved_level"]),
            "scan_cut_boundary_resolved_mask": stringValue(settings["scan_cut_boundary_resolved_mask"]),
            "scan_cut_boundary_provisional_level": stringValue(settings["scan_cut_boundary_provisional_level"]),
            "scan_cut_boundary_provisional_mask": stringValue(settings["scan_cut_boundary_provisional_mask"]),
            "cut_boundary_auto_long_media_sec": valueOrDefault(settings["cut_boundary_auto_long_media_sec"], default: 15.0 * 60.0),
            "cut_boundary_auto_short_media_sec": valueOrDefault(settings["cut_boundary_auto_short_media_sec"], default: 10.0 * 60.0),
            "cut_boundary_media_duration_bucket_sec": durationBucket,
            "cut_boundary_adaptive_level_enabled": boolValue(settings["cut_boundary_adaptive_level_enabled"]),
            "scan_cut_grid_mask": stringValue(settings["scan_cut_grid_mask"]),
            "scan_cut_compare_max_width": intValue(settings["scan_cut_compare_max_width"], default: 1920),
            "scan_cut_compare_max_height": intValue(settings["scan_cut_compare_max_height"], default: 1080),
            "scan_cut_follower_deferred_until_pioneer_done": boolValue(settings["scan_cut_follower_deferred_until_pioneer_done"]),
            "scan_cut_follower_stream_start_percent": valueOrDefault(settings["scan_cut_follower_stream_start_percent"], default: 25),
            "scan_cut_follower_stream_batch_size": valueOrDefault(settings["scan_cut_follower_stream_batch_size"], default: 16),
            "scan_cut_follower_verify_micro_batch_max": valueOrDefault(settings["scan_cut_follower_verify_micro_batch_max"], default: 16),
            "scan_cut_realtime_preview_enabled": truthySetting(settings["scan_cut_realtime_preview_enabled"], default: true),
            "scan_cut_audio_gain_enabled": boolValue(settings["scan_cut_audio_gain_enabled"], default: true),
            "scan_cut_audio_gain_threshold_db": valueOrDefault(settings["scan_cut_audio_gain_threshold_db"], default: 10.0),
            "scan_cut_audio_gain_window_sec": passthroughNumber(settings["scan_cut_audio_gain_window_sec"]),
            "scan_cut_audio_gain_min_gap_sec": passthroughNumber(settings["scan_cut_audio_gain_min_gap_sec"]),
        ]
    }

    private static func truthySetting(_ value: Any?, default defaultValue: Bool) -> Bool {
        guard let value else { return defaultValue }
        if let value = value as? String {
            let lowered = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if lowered.isEmpty || lowered == "auto" {
                return defaultValue
            }
            return !["0", "false", "no", "off", "미사용", "사용안함", "disabled"].contains(lowered)
        }
        return boolValue(value, default: defaultValue)
    }

    private static func normalizedJSONData(_ object: Any) -> Data? {
        try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    private static func sha256Hex(data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func passthroughNumber(_ value: Any?) -> Any {
        switch value {
        case let value as Double:
            return value
        case let value as NSNumber:
            return value.doubleValue
        case let value as String:
            if let parsed = Double(value) {
                return parsed
            }
            return NSNull()
        default:
            return NSNull()
        }
    }

    private static func dictValue(_ value: Any?) -> [String: Any] {
        value as? [String: Any] ?? [:]
    }

    private static func arrayOfDicts(_ value: Any?) -> [[String: Any]] {
        (value as? [[String: Any]]) ?? []
    }

    private static func stringValue(_ value: Any?, default defaultValue: String = "") -> String {
        guard let value else { return defaultValue }
        let text = String(describing: value)
        return text.isEmpty ? defaultValue : text
    }

    private static func boolValue(_ value: Any?, default defaultValue: Bool = false) -> Bool {
        switch value {
        case let value as Bool:
            return value
        case let value as NSNumber:
            return value.boolValue
        case let value as String:
            let lowered = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if ["1", "true", "yes", "on", "사용", "켜짐"].contains(lowered) {
                return true
            }
            if ["0", "false", "no", "off", "사용 안함", "끔"].contains(lowered) {
                return false
            }
            return defaultValue
        default:
            return defaultValue
        }
    }

    private static func doubleValue(_ value: Any?, default defaultValue: Double = 0.0) -> Double {
        switch value {
        case let value as Double:
            return value
        case let value as NSNumber:
            return value.doubleValue
        case let value as String:
            return Double(value) ?? defaultValue
        default:
            return defaultValue
        }
    }

    private static func intValue(_ value: Any?, default defaultValue: Int = 0) -> Int {
        switch value {
        case let value as Int:
            return value
        case let value as NSNumber:
            return value.intValue
        case let value as String:
            return Int(Double(value) ?? Double(defaultValue))
        default:
            return defaultValue
        }
    }

    private static func valueOrDefault(_ value: Any?, default defaultValue: Any) -> Any {
        if value == nil {
            return defaultValue
        }
        if value is NSNull {
            return defaultValue
        }
        return value!
    }
}
