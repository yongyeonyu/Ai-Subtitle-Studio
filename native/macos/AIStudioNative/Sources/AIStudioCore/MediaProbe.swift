import Foundation

public enum MediaProbeNative {
    public static func normalize(payload: [String: Any]) -> [String: Any] {
        let probeJSON = stringValue(payload["probe_json"])
        guard
            !probeJSON.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
            let data = probeJSON.data(using: .utf8),
            let decoded = try? JSONSerialization.jsonObject(with: data, options: []),
            let object = decoded as? [String: Any]
        else {
            return ["result": defaultResult()]
        }
        return ["result": normalizeObject(object)]
    }

    static func normalizeObject(_ payload: [String: Any]) -> [String: Any] {
        var result = defaultResult()
        let format = dictValue(payload["format"])
        var duration = doubleValue(format["duration"])
        result["bit_rate"] = max(0, intValue(format["bit_rate"]))

        let stream = dictValue(arrayValue(payload["streams"]).first)
        if !stream.isEmpty {
            if duration <= 0.0 {
                duration = doubleValue(stream["duration"])
            }
            let width = max(0, intValue(stream["width"]))
            let height = max(0, intValue(stream["height"]))
            let fps = parseFPS(stream["r_frame_rate"]) > 0.0
                ? parseFPS(stream["r_frame_rate"])
                : parseFPS(stream["avg_frame_rate"])
            result["width"] = width
            result["height"] = height
            result["fps"] = fps
            result["bit_rate"] = max(0, intValue(stream["bit_rate"], default: intValue(format["bit_rate"])))
            result["pix_fmt"] = stringValue(stream["pix_fmt"])
            result["color_space"] = stringValue(stream["color_space"])
            result["color_transfer"] = stringValue(stream["color_transfer"])
            result["color_primaries"] = stringValue(stream["color_primaries"])
            result["codec_name"] = stringValue(stream["codec_name"])
            result["profile"] = stringValue(stream["profile"])
            result["bits_per_raw_sample"] = max(0, intValue(stream["bits_per_raw_sample"]))
            if width > 0, height > 0 {
                result["info_txt"] = "\(width)x\(height) (\(String(format: "%.2f", fps))fps)"
            }
        }

        result["duration"] = duration
        if duration > 0.0 {
            result["len_txt"] = durationText(duration)
        }
        return result
    }

    static func defaultResult() -> [String: Any] {
        [
            "duration": 0.0,
            "width": 0,
            "height": 0,
            "fps": 0.0,
            "bit_rate": 0,
            "pix_fmt": "",
            "color_space": "",
            "color_transfer": "",
            "color_primaries": "",
            "codec_name": "",
            "profile": "",
            "bits_per_raw_sample": 0,
            "info_txt": "오디오 파일",
            "len_txt": "-",
        ]
    }

    static func parseFPS(_ value: Any?) -> Double {
        let text = stringValue(value)
        guard !text.isEmpty else { return 0.0 }
        if let slash = text.firstIndex(of: "/") {
            let numerator = String(text[..<slash])
            let denominator = String(text[text.index(after: slash)...])
            let denominatorValue = doubleValue(denominator)
            guard denominatorValue > 0.0 else { return 0.0 }
            return doubleValue(numerator) / denominatorValue
        }
        return doubleValue(text)
    }

    static func durationText(_ duration: Double) -> String {
        let totalSeconds = max(0, Int(duration))
        let minutes = totalSeconds / 60
        let seconds = totalSeconds % 60
        let hours = minutes / 60
        let remainingMinutes = minutes % 60
        if hours > 0 {
            return String(format: "%02d:%02d:%02d", hours, remainingMinutes, seconds)
        }
        return String(format: "%02d:%02d", remainingMinutes, seconds)
    }

    static func stringValue(_ value: Any?) -> String {
        if let text = value as? String {
            return text.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if let value {
            return String(describing: value).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return ""
    }

    static func doubleValue(_ value: Any?, default defaultValue: Double = 0.0) -> Double {
        switch value {
        case let value as Double:
            return value
        case let value as Float:
            return Double(value)
        case let value as NSNumber:
            return value.doubleValue
        case let value as String:
            return Double(value.trimmingCharacters(in: .whitespacesAndNewlines)) ?? defaultValue
        default:
            return defaultValue
        }
    }

    static func intValue(_ value: Any?, default defaultValue: Int = 0) -> Int {
        switch value {
        case let value as Int:
            return value
        case let value as NSNumber:
            return value.intValue
        case let value as String:
            return Int(value.trimmingCharacters(in: .whitespacesAndNewlines)) ?? defaultValue
        default:
            return defaultValue
        }
    }

    static func dictValue(_ value: Any?) -> [String: Any] {
        value as? [String: Any] ?? [:]
    }

    static func arrayValue(_ value: Any?) -> [Any] {
        value as? [Any] ?? []
    }
}
