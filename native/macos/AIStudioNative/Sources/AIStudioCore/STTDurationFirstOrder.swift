import Foundation

public enum STTDurationFirstOrderNative {
    public static let schema = "ai_subtitle_studio.stt.duration_first_order.v1"
    public static let computeProfileSchema = "ai_subtitle_studio.stt.compute_profile.v1"
    public static let submissionEnabledSchema = "ai_subtitle_studio.stt.duration_first_submission_enabled.v1"
    public static let workerTimeoutSchema = "ai_subtitle_studio.stt.worker_silence_timeout.v1"
    public static let stragglerConfigSchema = "ai_subtitle_studio.stt.straggler_config.v1"

    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        let starts = doubleArray(payload["starts"])
        let durations = doubleArray(payload["durations"]).map { max(0.001, $0) }
        let count = min(starts.count, durations.count)
        if count <= 1 {
            return [
                "schema": schema,
                "backend": "swift",
                "order": Array(0..<count),
                "input_count": count,
                "identity": true,
            ]
        }

        var order = Array(0..<count).sorted { left, right in
            let durationDelta = durations[right] - durations[left]
            if abs(durationDelta) > 0.000_000_1 {
                return durations[left] > durations[right]
            }
            return starts[left] < starts[right]
        }

        var seen = Set<Int>()
        order = order.filter { index in
            if index < 0 || index >= count || seen.contains(index) {
                return false
            }
            seen.insert(index)
            return true
        }
        for index in 0..<count where !seen.contains(index) {
            order.append(index)
        }

        let identity = order == Array(0..<count)
        let spread = (durations.max() ?? 0.0) - (durations.min() ?? 0.0)
        if identity || spread < 0.05 {
            order = Array(0..<count)
        }

        return [
            "schema": schema,
            "backend": "swift",
            "order": order,
            "input_count": count,
            "identity": order == Array(0..<count),
            "duration_spread": rounded(spread),
        ]
    }

    public static func computeProfile(payload: [String: Any]) -> [String: Any] {
        let fallback = SubtitleAssemblyValue.string(payload["fallback"]).isEmpty
            ? "ane_gpu"
            : SubtitleAssemblyValue.string(payload["fallback"])
        let value = SubtitleAssemblyValue.string(payload["compute_units"])
        let profile: String
        if value.isEmpty {
            profile = fallback
        } else {
            let key = value
                .replacingOccurrences(of: "-", with: "_")
                .replacingOccurrences(of: " ", with: "")
                .lowercased()
            if ["all", "full", "allcomputeunits"].contains(key) {
                profile = "all"
            } else if ["cpuandgpu", "cpu_gpu", "gpucpu", "gpu", "cpuandgputhenane"].contains(key) {
                profile = "gpu"
            } else if [
                "cpuandneuralengine",
                "cpu_neural_engine",
                "cpu_ane",
                "ane",
                "neuralengine",
                "anegpu",
                "ane_gpu",
            ].contains(key) {
                profile = "ane_gpu"
            } else if ["cpuonly", "cpu"].contains(key) {
                profile = "cpu"
            } else {
                profile = fallback
            }
        }
        return [
            "schema": computeProfileSchema,
            "backend": "swift",
            "profile": profile,
        ]
    }

    public static func submissionEnabled(payload: [String: Any]) -> [String: Any] {
        let rescuePass = boolValue(payload["rescue_pass"], fallback: false)
        let precisionPass = boolValue(payload["precision_pass"], fallback: false)
        let wordTimestamps = boolValue(payload["word_timestamps"], fallback: false)
        let enabledSetting = boolValue(payload["enabled_setting"], fallback: true)
        let enabled = (rescuePass || precisionPass || wordTimestamps) && enabledSetting
        return [
            "schema": submissionEnabledSchema,
            "backend": "swift",
            "enabled": enabled,
        ]
    }

    public static func workerSilenceTimeout(payload: [String: Any]) -> [String: Any] {
        let settings = payload["settings"] as? [String: Any] ?? [:]
        let precisionPass = boolValue(settings["stt_word_timestamp_precision_pass"], fallback: false)
        let label = SubtitleAssemblyValue.string(payload["log_label"])
        let wordTimestamps = boolValue(payload["word_timestamps"], fallback: false)
        let key: String
        let defaultValue: Double
        if precisionPass || label.contains("단어정밀") {
            key = "stt_word_timestamp_worker_response_timeout_sec"
            defaultValue = 45.0
        } else if wordTimestamps {
            key = "stt_worker_word_timestamp_response_timeout_sec"
            defaultValue = 90.0
        } else {
            key = "stt_worker_response_timeout_sec"
            defaultValue = 150.0
        }
        let rawValue = settings.keys.contains(key) ? settings[key] : defaultValue
        let parsed = pythonFloatLike(rawValue, invalidFallback: defaultValue)
        let timeout = parsed <= 0.0 ? 0.0 : max(0.05, min(600.0, parsed))
        return [
            "schema": workerTimeoutSchema,
            "backend": "swift",
            "key": key,
            "timeout": rounded(timeout),
        ]
    }

    public static func stragglerConfig(payload: [String: Any]) -> [String: Any] {
        let settings = payload["settings"] as? [String: Any] ?? [:]
        let mode = SubtitleAssemblyValue.string(payload["mode"]).lowercased()
        let isRecheck = mode == "recheck"

        let timeoutKey = isRecheck
            ? "stt_recheck_worker_straggler_timeout_sec"
            : "stt_word_timestamp_worker_straggler_timeout_sec"
        let maxMissingKey = isRecheck
            ? "stt_recheck_worker_straggler_max_missing_chunks"
            : "stt_word_timestamp_worker_straggler_max_missing_chunks"
        let ratioKey = isRecheck
            ? "stt_recheck_worker_straggler_min_received_ratio"
            : "stt_word_timestamp_worker_straggler_min_received_ratio"

        let timeoutDefault = isRecheck ? 18.0 : 12.0
        let maxMissingDefault = isRecheck ? 4.0 : 1.0
        let ratioDefault = isRecheck ? 0.60 : 0.90
        let ratioMinimum = isRecheck ? 0.25 : 0.50
        let maxMissingMaximum = isRecheck ? 4 : 8

        let timeoutRaw = settings.keys.contains(timeoutKey) ? settings[timeoutKey] : timeoutDefault
        let timeoutValue = pythonFloatLike(timeoutRaw, invalidFallback: timeoutDefault)
        let timeout = timeoutValue <= 0.0 ? 0.0 : max(2.0, min(120.0, timeoutValue))

        let maxMissingRaw = settings.keys.contains(maxMissingKey) ? settings[maxMissingKey] : maxMissingDefault
        let maxMissingValue = Int(pythonFloatLike(maxMissingRaw, invalidFallback: maxMissingDefault))
        let maxMissing = max(1, min(maxMissingMaximum, maxMissingValue))

        let ratioRaw = settings.keys.contains(ratioKey) ? settings[ratioKey] : ratioDefault
        let ratioValue = pythonFloatLike(ratioRaw, invalidFallback: ratioDefault)
        let ratio = ratioValue <= 0.0 ? 0.0 : max(ratioMinimum, min(1.0, ratioValue))

        return [
            "schema": stragglerConfigSchema,
            "backend": "swift",
            "mode": isRecheck ? "recheck" : "precision",
            "timeout": rounded(timeout),
            "max_missing_chunks": maxMissing,
            "min_received_ratio": rounded(ratio),
        ]
    }

    private static func doubleArray(_ value: Any?) -> [Double] {
        if let values = value as? [Double] {
            return values
        }
        if let values = value as? [Any] {
            return values.map { SubtitleAssemblyValue.number($0) }
        }
        return []
    }

    private static func boolValue(_ value: Any?, fallback: Bool) -> Bool {
        guard let value else {
            return fallback
        }
        if let value = value as? Bool {
            return value
        }
        if let value = value as? NSNumber {
            return value.boolValue
        }
        let text = SubtitleAssemblyValue.string(value).lowercased()
        if ["1", "true", "yes", "on", "enabled", "enable", "사용"].contains(text) {
            return true
        }
        if ["0", "false", "no", "off", "disabled", "disable", "끄기", "끔", "미사용"].contains(text) {
            return false
        }
        return fallback
    }

    private static func pythonFloatLike(_ value: Any?, invalidFallback: Double) -> Double {
        guard let value else {
            return 0.0
        }
        if value is NSNull {
            return 0.0
        }
        if let value = value as? Double {
            return value
        }
        if let value = value as? Float {
            return Double(value)
        }
        if let value = value as? Int {
            return Double(value)
        }
        if let value = value as? NSNumber {
            return value.doubleValue
        }
        let text = SubtitleAssemblyValue.string(value)
        if text.isEmpty {
            return 0.0
        }
        return Double(text) ?? invalidFallback
    }

    private static func rounded(_ value: Double) -> Double {
        (value * 1_000_000.0).rounded() / 1_000_000.0
    }
}
