import Foundation

public enum VADSegmentsNative {
    public static func flagsToSegments(payload: [String: Any]) -> [String: Any] {
        let flags = intArray(payload["flags"])
        let hopSec = positiveDouble(payload["hop_sec"], defaultValue: 0.032)
        let minSpeechSec = max(0.0, doubleValue(payload["min_speech_sec"], defaultValue: 0.0))
        let minSilenceSec = max(0.0, doubleValue(payload["min_silence_sec"], defaultValue: 0.0))
        let speechPadSec = max(0.0, doubleValue(payload["speech_pad_sec"], defaultValue: 0.0))
        let source = stringValue(payload["source"], defaultValue: "vad")
        let postSTTAlign = boolValue(payload["for_post_stt_align"], defaultValue: false)

        var raw: [(Double, Double)] = []
        var startIndex: Int?
        for (index, flag) in flags.enumerated() {
            if flag != 0 && startIndex == nil {
                startIndex = index
            } else if flag == 0, let start = startIndex {
                raw.append((Double(start) * hopSec, Double(index) * hopSec))
                startIndex = nil
            }
        }
        if let start = startIndex {
            raw.append((Double(start) * hopSec, Double(flags.count) * hopSec))
        }

        var merged: [[Double]] = []
        for (rawStart, rawEnd) in raw {
            if rawEnd - rawStart < minSpeechSec {
                continue
            }
            let start = max(0.0, rawStart - speechPadSec)
            let end = rawEnd + speechPadSec
            if let last = merged.last, start - last[1] <= minSilenceSec {
                merged[merged.count - 1][1] = max(last[1], end)
            } else {
                merged.append([start, end])
            }
        }

        let segments: [[String: Any]] = merged.compactMap { item in
            guard item.count >= 2 else { return nil }
            let start = rounded(item[0], places: 3)
            let end = rounded(max(item[0], item[1]), places: 3)
            guard end > start else { return nil }
            return [
                "start": start,
                "end": end,
                "source": source,
                "post_stt_align": postSTTAlign,
                "vad_word_filter": !postSTTAlign,
                "speech_pad_sec": rounded(speechPadSec, places: 3),
                "min_silence_sec": rounded(minSilenceSec, places: 3),
            ]
        }

        return [
            "segments": segments,
            "backend": "swift",
            "schema": "ai_subtitle_studio.vad_segments.v1",
        ]
    }

    private static func intArray(_ value: Any?) -> [Int] {
        guard let values = value as? [Any] else { return [] }
        return values.map { intValue($0, defaultValue: 0) }
    }

    private static func intValue(_ value: Any?, defaultValue: Int) -> Int {
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

    private static func doubleValue(_ value: Any?, defaultValue: Double) -> Double {
        switch value {
        case let value as Double:
            return value.isFinite ? value : defaultValue
        case let value as NSNumber:
            let number = value.doubleValue
            return number.isFinite ? number : defaultValue
        case let value as String:
            let number = Double(value.trimmingCharacters(in: .whitespacesAndNewlines))
            return number?.isFinite == true ? number! : defaultValue
        default:
            return defaultValue
        }
    }

    private static func positiveDouble(_ value: Any?, defaultValue: Double) -> Double {
        max(0.000001, doubleValue(value, defaultValue: defaultValue))
    }

    private static func stringValue(_ value: Any?, defaultValue: String) -> String {
        let text = String(describing: value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? defaultValue : text
    }

    private static func boolValue(_ value: Any?, defaultValue: Bool) -> Bool {
        switch value {
        case let value as Bool:
            return value
        case let value as NSNumber:
            return value.boolValue
        case let value as String:
            let text = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if ["1", "true", "yes", "on", "enabled"].contains(text) {
                return true
            }
            if ["0", "false", "no", "off", "disabled"].contains(text) {
                return false
            }
            return defaultValue
        default:
            return defaultValue
        }
    }

    private static func rounded(_ value: Double, places: Int) -> Double {
        let scale = pow(10.0, Double(max(0, places)))
        return (value * scale).rounded() / scale
    }
}
