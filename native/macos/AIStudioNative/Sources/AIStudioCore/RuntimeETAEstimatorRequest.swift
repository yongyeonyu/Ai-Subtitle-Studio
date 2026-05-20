import Foundation

extension RuntimeETAEstimator {
    static func makeRequest(payload: [String: Any]) -> RuntimeETARequest? {
        let storePath = stringValue(payload["store_path"])
        let modelKey = stringValue(payload["model_key"])
        let variantPayload = dictValue(payload["variant"])
        let mediaPayload = dictValue(payload["media"])
        let runtimePayload = dictValue(payload["runtime"])
        let durationSec = max(
            0.0,
            doubleValue(mediaPayload["duration_sec"]),
            doubleValue(payload["video_duration_sec"])
        )
        guard !storePath.isEmpty, !modelKey.isEmpty, durationSec > 0.0 else {
            return nil
        }
        let width = max(0, intValue(mediaPayload["width"]))
        let height = max(0, intValue(mediaPayload["height"]))
        let pixelCount = max(0.0, doubleValue(mediaPayload["pixel_count"], default: Double(width * height)))
        let variant = RuntimeETAVariant(
            mode: normalizedMode(stringValue(variantPayload["mode"], default: "balanced")),
            sttQualityPreset: normalizedMode(stringValue(variantPayload["stt_quality_preset"], default: "balanced")),
            sttPrimary: stringValue(variantPayload["stt_primary"], default: "unknown"),
            sttSecondary: stringValue(variantPayload["stt_secondary"]),
            sttEnsembleEnabled: boolValue(variantPayload["stt_ensemble_enabled"]),
            llmProvider: stringValue(variantPayload["llm_provider"], default: "none"),
            llmModel: stringValue(variantPayload["llm_model"], default: "none"),
            diarizationEnabled: boolValue(variantPayload["diarization_enabled"]),
            maxSpeakers: max(1, intValue(variantPayload["max_speakers"], default: 1)),
            selectedVad: stringValue(variantPayload["selected_vad"], default: "none"),
            selectedAudioAI: stringValue(variantPayload["selected_audio_ai"], default: "none")
        )
        let media = RuntimeETAMedia(
            durationSec: durationSec,
            fps: max(0.0, doubleValue(mediaPayload["fps"])),
            width: width,
            height: height,
            pixelCount: pixelCount,
            audioQualityScore: clamp(doubleValue(mediaPayload["audio_quality_score"], default: 70.0), min: 0.0, max: 100.0),
            cutDensityPerMin: max(0.0, doubleValue(mediaPayload["cut_density_per_min"])),
            speakerHint: max(1, intValue(mediaPayload["speaker_hint"], default: 1)),
            isAudioOnly: boolValue(mediaPayload["is_audio_only"])
        )
        let runtime = RuntimeETARuntime(
            queueIndex: max(0, intValue(runtimePayload["queue_index"])),
            totalFiles: max(1, intValue(runtimePayload["total_files"], default: 1)),
            prefetchAudioHit: boolValue(runtimePayload["prefetch_audio_hit"]),
            cutBoundaryCacheEnabled: boolValue(runtimePayload["cut_boundary_cache_enabled"], default: true),
            vadCacheEnabled: boolValue(runtimePayload["vad_cache_enabled"], default: true),
            sttRuntimeReuseEnabled: boolValue(runtimePayload["stt_runtime_reuse_enabled"], default: true),
            prefetchAhead: max(0, intValue(runtimePayload["prefetch_ahead"])),
            autoAudioTuneEnabled: boolValue(runtimePayload["auto_audio_tune_enabled"], default: true),
            cacheState: normalizedCacheState(stringValue(runtimePayload["cache_state"], default: "cold")),
            cutBoundaryCacheState: normalizedCacheState(stringValue(runtimePayload["cut_boundary_cache_state"], default: "cold")),
            vadCacheState: normalizedCacheState(stringValue(runtimePayload["vad_cache_state"], default: "cold")),
            speakerCacheState: normalizedCacheState(stringValue(runtimePayload["speaker_cache_state"], default: "cold")),
            likelyWarmStart: boolValue(runtimePayload["likely_warm_start"]),
            cacheScore: clamp(doubleValue(runtimePayload["cache_score"], default: 0.45), min: 0.0, max: 1.0)
        )
        let processingTimeSec = payload["processing_time_sec"] == nil ? nil : max(0.0, doubleValue(payload["processing_time_sec"]))
        return RuntimeETARequest(
            storePath: storePath,
            modelKey: modelKey,
            variant: variant,
            media: media,
            runtime: runtime,
            processingTimeSec: processingTimeSec
        )
    }

    static func normalizedMode(_ value: String) -> String {
        switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "fast", "빠름":
            return "fast"
        case "precise", "high", "quality", "정확도 우선", "정밀 인식", "정밀인식":
            return "precise"
        case "stt", "stt mode", "stt 모드":
            return "stt"
        default:
            return "balanced"
        }
    }

    static func normalizedCacheState(_ value: String) -> String {
        switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "warm":
            return "warm"
        case "disabled", "off", "none":
            return "disabled"
        default:
            return "cold"
        }
    }

    static func stringValue(_ value: Any?, default defaultValue: String = "") -> String {
        guard let value else {
            return defaultValue
        }
        let text = String(describing: value).trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? defaultValue : text
    }

    static func boolValue(_ value: Any?, default defaultValue: Bool = false) -> Bool {
        switch value {
        case let value as Bool:
            return value
        case let value as NSNumber:
            return value.boolValue
        case let value as String:
            return ["1", "true", "yes", "on", "사용", "켜짐"].contains(value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
        default:
            return defaultValue
        }
    }

    static func doubleValue(_ value: Any?, default defaultValue: Double = 0.0) -> Double {
        switch value {
        case let value as Double:
            return value.isFinite ? value : defaultValue
        case let value as NSNumber:
            let parsed = value.doubleValue
            return parsed.isFinite ? parsed : defaultValue
        case let value as String:
            let parsed = Double(value) ?? defaultValue
            return parsed.isFinite ? parsed : defaultValue
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
            return Int(Double(value) ?? Double(defaultValue))
        default:
            return defaultValue
        }
    }

    static func dictValue(_ value: Any?) -> [String: Any] {
        value as? [String: Any] ?? [:]
    }
}
