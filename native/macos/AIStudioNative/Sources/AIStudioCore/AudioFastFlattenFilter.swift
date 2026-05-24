import Foundation

public enum AudioFastFlattenFilterNative {
    public static let schema = "ai_subtitle_studio.audio.fast_flatten_filter.v1"
    public static let sampleSpanSchema = "ai_subtitle_studio.audio.route_sample_span.v1"
    public static let audioAIVariantSchema = "ai_subtitle_studio.audio.ai_variant.v1"
    public static let routePreviewDivergenceSchema = "ai_subtitle_studio.audio.route_preview_divergence.v1"
    public static let routeSplitDecisionSchema = "ai_subtitle_studio.audio.route_split_decision.v1"

    public static func evaluate(payload: [String: Any]) -> [String: Any] {
        let settings = payload["settings"] as? [String: Any] ?? payload
        let hp = Int(floatSetting(settings, "macos_native_fast_audio_flatten_hp", 150.0, minValue: 0.0, maxValue: 500.0))
        let lp = Int(floatSetting(settings, "macos_native_fast_audio_flatten_lp", 4600.0, minValue: 1000.0, maxValue: 8000.0))
        let nf: Double? = hasConcreteValue(settings["macos_native_fast_audio_flatten_nf"])
            ? floatSetting(settings, "macos_native_fast_audio_flatten_nf", -30.0, minValue: -80.0, maxValue: 0.0)
            : nil
        let treble = floatSetting(settings, "macos_native_fast_audio_flatten_treble", 0.0, minValue: -10.0, maxValue: 20.0)
        let compThreshold = floatSetting(settings, "macos_native_fast_audio_flatten_comp_th", -24.0, minValue: -60.0, maxValue: 0.0)
        let volume = floatSetting(settings, "macos_native_fast_audio_flatten_volume", 3.2, minValue: 0.5, maxValue: 8.0)
        let limiter = floatSetting(settings, "macos_native_fast_audio_flatten_limiter", 0.93, minValue: 0.1, maxValue: 1.0)

        var filters: [String] = []
        if hp > 0 {
            filters.append("highpass=f=\(hp)")
        }
        if lp > 0 {
            filters.append("lowpass=f=\(lp)")
        }
        if let nf {
            filters.append("afftdn=nf=\(formatFilterNumber(nf))")
        }
        filters.append("acompressor=threshold=\(formatFilterNumber(compThreshold))dB:ratio=3:attack=5:release=55")
        if abs(treble) >= 0.01 {
            filters.append("equalizer=f=3200:width_type=h:width=2200:g=\(formatFilterNumber(treble))")
        }
        filters.append("volume=\(formatFilterNumber(volume))")
        filters.append("alimiter=limit=\(formatFilterNumber(limiter))")

        return [
            "schema": schema,
            "backend": "swift",
            "filter": filters.joined(separator: ","),
            "filter_count": filters.count,
        ]
    }

    public static func sampleSpan(payload: [String: Any]) -> [String: Any] {
        let settings = payload["settings"] as? [String: Any] ?? [:]
        let start = max(0.0, SubtitleAssemblyValue.number(payload["start"], fallback: 0.0))
        let requestedEnd = SubtitleAssemblyValue.number(payload["end"], fallback: start)
        let end = max(start, requestedEnd)
        let duration = max(0.0, end - start)
        if duration <= 0.0 {
            return [
                "schema": sampleSpanSchema,
                "backend": "swift",
                "start": rounded(start),
                "duration": 0.0,
            ]
        }
        let maxSample = SubtitleAssemblyValue.number(settings["audio_chunk_profile_sec"], fallback: 30.0)
        let sampleDuration = min(duration, max(8.0, min(30.0, maxSample)))
        let sampleStart = start + max(0.0, (duration - sampleDuration) / 2.0)
        return [
            "schema": sampleSpanSchema,
            "backend": "swift",
            "start": rounded(sampleStart),
            "duration": rounded(sampleDuration),
        ]
    }

    public static func audioAIVariant(payload: [String: Any]) -> [String: Any] {
        let audioKind = SubtitleAssemblyValue.string(payload["audio_ai"]).lowercased()
        let fastFlattenEnabled = boolValue(payload["fast_flatten_enabled"])
        let nativeFFmpegEnabled = boolValue(payload["clearvoice_native_ffmpeg_enabled"])
        let clearvoiceModel = SubtitleAssemblyValue.string(payload["clearvoice_model_name"]).isEmpty
            ? "MossFormerGAN_SE_16K"
            : SubtitleAssemblyValue.string(payload["clearvoice_model_name"])
        let variant: String
        if audioKind != "none" && !audioKind.isEmpty && fastFlattenEnabled {
            variant = "macos_native_fast_audio_flatten_v1"
        } else if audioKind == "clearvoice" {
            variant = nativeFFmpegEnabled ? "native_ffmpeg_v1" : clearvoiceModel
        } else {
            variant = ""
        }
        return [
            "schema": audioAIVariantSchema,
            "backend": "swift",
            "variant": variant,
        ]
    }

    public static func routePreviewDivergence(payload: [String: Any]) -> [String: Any] {
        let route = payload["route"] as? [String: Any] ?? payload
        let featureConfidence = optionalNumber(route["feature_confidence"])
        let selfScore = optionalNumber(route["self_score"])
        let divergence: Double
        if let featureConfidence, let selfScore {
            divergence = abs(selfScore - featureConfidence)
        } else {
            let previewGap = scoreGap(route["preview_scores"])
            let featureGap = scoreGap(route["candidate_scores"])
            divergence = abs(previewGap - featureGap)
        }
        return [
            "schema": routePreviewDivergenceSchema,
            "backend": "swift",
            "divergence": rounded(divergence),
        ]
    }

    public static func routeSplitDecision(payload: [String: Any]) -> [String: Any] {
        let fallbackLike = boolValue(payload["fallback_like"])
        let challenging = boolValue(payload["challenging"])
        let lowConfidence = boolValue(payload["low_confidence"])
        let baselineGuard = boolValue(payload["baseline_guard"])
        let previewSwitch = boolValue(payload["preview_switch"])
        let specialist = boolValue(payload["specialist"])
        let volatile = boolValue(payload["volatile"])
        let noise = SubtitleAssemblyValue.string(payload["noise"]).lowercased()
        let candidateGap = SubtitleAssemblyValue.number(payload["candidate_gap"], fallback: 0.0)
        let previewGap = SubtitleAssemblyValue.number(payload["preview_gap"], fallback: 0.0)
        let gapLimit = SubtitleAssemblyValue.number(payload["gap_limit"], fallback: 0.0)
        let previewDivergence = SubtitleAssemblyValue.number(payload["preview_divergence"], fallback: 0.0)
        let previewDivergenceMin = SubtitleAssemblyValue.number(payload["preview_divergence_min"], fallback: 0.08)

        let shouldSplit: Bool
        if fallbackLike && challenging && (lowConfidence || candidateGap <= gapLimit + 0.03) {
            shouldSplit = true
        } else if baselineGuard && (
            previewSwitch
            || previewDivergence >= previewDivergenceMin
            || candidateGap <= gapLimit + 0.02
        ) {
            shouldSplit = true
        } else if previewSwitch && previewDivergence >= previewDivergenceMin {
            shouldSplit = true
        } else if challenging && volatile && lowConfidence && (
            candidateGap <= gapLimit || previewGap <= gapLimit
        ) {
            shouldSplit = true
        } else if specialist && volatile && lowConfidence && previewDivergence >= max(0.04, gapLimit) {
            shouldSplit = true
        } else if noise == "high" && volatile && lowConfidence && candidateGap <= gapLimit {
            shouldSplit = true
        } else {
            shouldSplit = false
        }

        return [
            "schema": routeSplitDecisionSchema,
            "backend": "swift",
            "split": shouldSplit,
        ]
    }

    private static func floatSetting(
        _ settings: [String: Any],
        _ key: String,
        _ fallback: Double,
        minValue: Double,
        maxValue: Double
    ) -> Double {
        var value = SubtitleAssemblyValue.number(settings[key], fallback: fallback)
        value = max(minValue, value)
        value = min(maxValue, value)
        return value
    }

    private static func hasConcreteValue(_ value: Any?) -> Bool {
        guard let value else {
            return false
        }
        if value is NSNull {
            return false
        }
        return true
    }

    private static func boolValue(_ value: Any?) -> Bool {
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
        return false
    }

    private static func optionalNumber(_ value: Any?) -> Double? {
        guard let value else {
            return nil
        }
        if value is NSNull {
            return nil
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
        return text.isEmpty ? nil : Double(text)
    }

    private static func scoreGap(_ value: Any?) -> Double {
        let rows: [[String: Any]]
        if let typedRows = value as? [[String: Any]] {
            rows = typedRows
        } else if let anyRows = value as? [Any] {
            rows = anyRows.compactMap { $0 as? [String: Any] }
        } else {
            rows = []
        }
        var scores: [Double] = []
        for row in rows {
            if let score = optionalNumber(row["score"]) {
                scores.append(score)
            }
        }
        if scores.isEmpty {
            return 0.0
        }
        scores.sort(by: >)
        if scores.count == 1 {
            return max(0.0, scores[0])
        }
        return max(0.0, scores[0] - scores[1])
    }

    private static func formatFilterNumber(_ value: Double) -> String {
        String(format: "%g", locale: Locale(identifier: "en_US_POSIX"), value)
    }

    private static func rounded(_ value: Double) -> Double {
        (value * 1_000.0).rounded() / 1_000.0
    }
}
