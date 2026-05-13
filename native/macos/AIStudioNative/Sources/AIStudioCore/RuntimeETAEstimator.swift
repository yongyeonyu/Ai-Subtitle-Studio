import Foundation

struct RuntimeETAAlgorithm: Codable {
    var name: String = "recency_weighted_variant_eta"
    var version: Int = 2
}

struct RuntimeETAWeights: Codable {
    var maxRuns: Int = 320
    var recencyHalfLifeRuns: Double = 6.0
    var variantExactBoost: Double = 2.4
    var modeMatchBoost: Double = 1.35
    var sttPresetMatchBoost: Double = 1.35
    var sttModelMatchBoost: Double = 1.65
    var llmMatchBoost: Double = 1.25
    var vadMatchBoost: Double = 1.15
    var cacheStateMatchBoost: Double = 1.18
    var diarizationMatchBoost: Double = 1.12
    var warmCacheBoost: Double = 1.12
    var durationWeight: Double = 1.10
    var fpsWeight: Double = 0.26
    var resolutionWeight: Double = 0.44
    var audioQualityWeight: Double = 0.22
    var cutDensityWeight: Double = 0.18
    var speakerWeight: Double = 0.14
    var cacheWeight: Double = 0.30
    var queueWeight: Double = 0.08
    var heuristicWeight: Double = 0.24
    var globalHistoryWeight: Double = 0.28
    var variantHistoryWeight: Double = 0.48
    var minimumNeighborWeight: Double = 0.01
    var fixedOverheadSec: Double = 10.0
    var warmCacheMultiplier: Double = 0.88
    var coldCacheMultiplier: Double = 1.00
    var cacheDisabledMultiplier: Double = 1.12
}

struct RuntimeETAVariant: Codable {
    var mode: String
    var sttQualityPreset: String
    var sttPrimary: String
    var sttSecondary: String
    var sttEnsembleEnabled: Bool
    var llmProvider: String
    var llmModel: String
    var diarizationEnabled: Bool
    var maxSpeakers: Int
    var selectedVad: String
    var selectedAudioAI: String

    func key(modelKey: String, cacheState: String) -> String {
        [
            "mode=\(mode)",
            "preset=\(sttQualityPreset)",
            "model=\(sttPrimary)",
            "model2=\(sttSecondary)",
            "ensemble=\(sttEnsembleEnabled ? 1 : 0)",
            "llmProvider=\(llmProvider)",
            "llmModel=\(llmModel)",
            "vad=\(selectedVad)",
            "audio=\(selectedAudioAI)",
            "dia=\(diarizationEnabled ? 1 : 0)",
            "cache=\(cacheState)",
            "modelKey=\(modelKey)",
        ].joined(separator: "|")
    }
}

struct RuntimeETAMedia: Codable {
    var durationSec: Double
    var fps: Double
    var width: Int
    var height: Int
    var pixelCount: Double
    var audioQualityScore: Double
    var cutDensityPerMin: Double
    var speakerHint: Int
    var isAudioOnly: Bool
}

struct RuntimeETARuntime: Codable {
    var queueIndex: Int
    var totalFiles: Int
    var prefetchAudioHit: Bool
    var cutBoundaryCacheEnabled: Bool
    var vadCacheEnabled: Bool
    var sttRuntimeReuseEnabled: Bool
    var prefetchAhead: Int
    var autoAudioTuneEnabled: Bool
    var cacheState: String
    var cutBoundaryCacheState: String
    var vadCacheState: String
    var speakerCacheState: String
    var likelyWarmStart: Bool
    var cacheScore: Double
}

struct RuntimeETAMetrics: Codable {
    var processingSec: Double
    var speedRatio: Double
}

struct RuntimeETARun: Codable {
    var runId: String
    var recordedAt: Double
    var variantKey: String
    var modelKey: String
    var variant: RuntimeETAVariant
    var media: RuntimeETAMedia
    var runtime: RuntimeETARuntime
    var metrics: RuntimeETAMetrics
}

struct RuntimeETAVariantSummary: Codable {
    var variantKey: String
    var mode: String
    var sttQualityPreset: String
    var sttPrimary: String
    var sttSecondary: String
    var llmProvider: String
    var llmModel: String
    var selectedVad: String
    var diarizationEnabled: Bool
    var cacheState: String
    var count: Int
    var recentSpeedRatio: Double
    var emaSpeedRatio: Double
    var weightedSpeedRatio: Double
    var lastProcessingSec: Double
    var lastDurationSec: Double
    var updatedAt: Double
}

struct RuntimeETAStore: Codable {
    var schema: String
    var createdAt: Double
    var updatedAt: Double
    var algorithm: RuntimeETAAlgorithm
    var weights: RuntimeETAWeights
    var variants: [String: RuntimeETAVariantSummary]
    var runs: [RuntimeETARun]
}

struct RuntimeETARequest {
    var storePath: String
    var modelKey: String
    var variant: RuntimeETAVariant
    var media: RuntimeETAMedia
    var runtime: RuntimeETARuntime
    var processingTimeSec: Double?

    var variantKey: String {
        variant.key(modelKey: modelKey, cacheState: runtime.cacheState)
    }
}

public enum RuntimeETAEstimator {
    static let schema = "ai_subtitle_studio.runtime_eta_store.v2"

    public static func predict(payload: [String: Any]) -> [String: Any] {
        guard let request = makeRequest(payload: payload) else {
            return ["error": "Invalid runtime ETA request"]
        }
        let url = URL(fileURLWithPath: request.storePath)
        var store = loadStore(at: url)
        if !FileManager.default.fileExists(atPath: url.path) {
            saveStore(store, to: url)
        }
        let result = estimate(request: request, store: store)
        store.updatedAt = Date().timeIntervalSince1970
        return [
            "schema": schema,
            "predicted_processing_sec": result.predictedSec,
            "predicted_speed_ratio": result.predictedRatio,
            "confidence": result.confidence,
            "variant_key": request.variantKey,
            "sample_count": store.runs.count,
            "matched_variant_count": result.matchedVariantCount,
            "source": result.source,
        ]
    }

    public static func record(payload: [String: Any]) -> [String: Any] {
        guard let request = makeRequest(payload: payload) else {
            return ["error": "Invalid runtime ETA request"]
        }
        let processingSec = max(0.0, request.processingTimeSec ?? 0.0)
        let durationSec = max(0.0, request.media.durationSec)
        guard processingSec > 0.0, durationSec > 0.0 else {
            return ["error": "Missing duration or processing time"]
        }
        let url = URL(fileURLWithPath: request.storePath)
        var store = loadStore(at: url)
        let now = Date().timeIntervalSince1970
        let ratio = processingSec / durationSec
        let run = RuntimeETARun(
            runId: UUID().uuidString,
            recordedAt: now,
            variantKey: request.variantKey,
            modelKey: request.modelKey,
            variant: request.variant,
            media: request.media,
            runtime: request.runtime,
            metrics: RuntimeETAMetrics(processingSec: processingSec, speedRatio: ratio)
        )
        store.runs.append(run)
        if store.runs.count > max(16, store.weights.maxRuns) {
            store.runs.removeFirst(store.runs.count - max(16, store.weights.maxRuns))
        }
        updateVariantSummary(store: &store, request: request, ratio: ratio, processingSec: processingSec, now: now)
        store.updatedAt = now
        saveStore(store, to: url)
        return [
            "ok": true,
            "schema": schema,
            "variant_key": request.variantKey,
            "run_count": store.runs.count,
            "variant_count": store.variants.count,
        ]
    }

    private static func updateVariantSummary(
        store: inout RuntimeETAStore,
        request: RuntimeETARequest,
        ratio: Double,
        processingSec: Double,
        now: Double
    ) {
        var summary = store.variants[request.variantKey] ?? RuntimeETAVariantSummary(
            variantKey: request.variantKey,
            mode: request.variant.mode,
            sttQualityPreset: request.variant.sttQualityPreset,
            sttPrimary: request.variant.sttPrimary,
            sttSecondary: request.variant.sttSecondary,
            llmProvider: request.variant.llmProvider,
            llmModel: request.variant.llmModel,
            selectedVad: request.variant.selectedVad,
            diarizationEnabled: request.variant.diarizationEnabled,
            cacheState: request.runtime.cacheState,
            count: 0,
            recentSpeedRatio: 0.0,
            emaSpeedRatio: 0.0,
            weightedSpeedRatio: 0.0,
            lastProcessingSec: 0.0,
            lastDurationSec: 0.0,
            updatedAt: now
        )
        summary.count += 1
        summary.recentSpeedRatio = ratio
        if summary.count <= 1 || summary.emaSpeedRatio <= 0.0 {
            summary.emaSpeedRatio = ratio
        } else {
            summary.emaSpeedRatio = (0.35 * ratio) + (0.65 * summary.emaSpeedRatio)
        }
        summary.weightedSpeedRatio = (summary.emaSpeedRatio * 0.60) + (summary.recentSpeedRatio * 0.40)
        summary.lastProcessingSec = processingSec
        summary.lastDurationSec = request.media.durationSec
        summary.updatedAt = now
        store.variants[request.variantKey] = summary
    }

    private static func estimate(request: RuntimeETARequest, store: RuntimeETAStore) -> (predictedSec: Double, predictedRatio: Double, confidence: Double, matchedVariantCount: Int, source: String) {
        let weights = store.weights
        let heuristicRatio = heuristicSpeedRatio(request: request, weights: weights)
        var components: [(ratio: Double, weight: Double)] = []

        var exactVariantCount = 0
        if let summary = store.variants[request.variantKey], summary.weightedSpeedRatio > 0.0 {
            let summarySupport = min(1.0, Double(summary.count) / 6.0)
            components.append((summary.weightedSpeedRatio, max(0.08, weights.variantHistoryWeight * (0.50 + summarySupport * 0.50))))
            exactVariantCount = summary.count
        }

        let exactRuns = weightedAverage(
            runs: store.runs.filter { $0.variantKey == request.variantKey },
            request: request,
            weights: weights
        )
        if exactRuns.count > 0 {
            let support = min(1.0, Double(exactRuns.count) / 3.0)
            components.append((exactRuns.ratio, max(0.08, weights.variantHistoryWeight * support)))
            exactVariantCount = max(exactVariantCount, exactRuns.count)
        } else {
            let modeRuns = weightedAverage(
                runs: store.runs.filter { $0.variant.mode == request.variant.mode },
                request: request,
                weights: weights
            )
            if modeRuns.count > 0 {
                let support = min(1.0, Double(modeRuns.count) / 4.0)
                components.append((modeRuns.ratio, max(0.06, weights.variantHistoryWeight * 0.55 * support)))
            }
        }

        let globalRuns = weightedAverage(runs: store.runs, request: request, weights: weights)
        if globalRuns.count > 0 {
            let support = min(1.0, Double(globalRuns.count) / 12.0)
            components.append((globalRuns.ratio, max(0.05, weights.globalHistoryWeight * support)))
        }

        let historySupport = min(1.0, Double(store.runs.count) / 12.0)
        let heuristicWeight = max(0.08, weights.heuristicWeight * (1.0 - (0.65 * historySupport)))
        components.append((heuristicRatio, heuristicWeight))

        let totalWeight = components.reduce(0.0) { $0 + max(0.0, $1.weight) }
        let blendedRatio: Double
        if totalWeight > 0.0 {
            blendedRatio = components.reduce(0.0) { $0 + ($1.ratio * max(0.0, $1.weight)) } / totalWeight
        } else {
            blendedRatio = heuristicRatio
        }
        let durationSec = max(0.0, request.media.durationSec)
        let predictedSec = max(1.0, (durationSec * blendedRatio) + weights.fixedOverheadSec)
        let confidence = min(
            0.98,
            0.22
                + min(0.30, Double(exactVariantCount) * 0.06)
                + min(0.28, Double(store.runs.count) * 0.02)
                + min(0.18, totalWeight * 0.08)
        )
        let source = exactVariantCount > 0 ? "variant_history" : (store.runs.isEmpty ? "heuristic" : "blended_history")
        return (predictedSec, blendedRatio, confidence, exactVariantCount, source)
    }

    private static func weightedAverage(
        runs: [RuntimeETARun],
        request: RuntimeETARequest,
        weights: RuntimeETAWeights
    ) -> (ratio: Double, count: Int) {
        guard !runs.isEmpty else {
            return (0.0, 0)
        }
        var weightedSum = 0.0
        var totalWeight = 0.0
        var matched = 0
        for (age, run) in runs.reversed().enumerated() {
            let ratio = max(0.0, run.metrics.speedRatio)
            guard ratio > 0.0 else {
                continue
            }
            let weight = neighborWeight(run: run, request: request, weights: weights, age: age)
            guard weight >= weights.minimumNeighborWeight else {
                continue
            }
            weightedSum += ratio * weight
            totalWeight += weight
            matched += 1
        }
        guard totalWeight > 0.0 else {
            return (0.0, 0)
        }
        return (weightedSum / totalWeight, matched)
    }

    private static func neighborWeight(
        run: RuntimeETARun,
        request: RuntimeETARequest,
        weights: RuntimeETAWeights,
        age: Int
    ) -> Double {
        let recency = pow(0.5, Double(age) / max(1.0, weights.recencyHalfLifeRuns))
        let durationDiff = relativeDiff(run.media.durationSec, request.media.durationSec)
        let fpsDiff = relativeDiff(run.media.fps, request.media.fps)
        let resolutionDiff = relativeDiff(run.media.pixelCount, request.media.pixelCount)
        let audioDiff = abs(run.media.audioQualityScore - request.media.audioQualityScore) / 100.0
        let cutDiff = abs(run.media.cutDensityPerMin - request.media.cutDensityPerMin) / 8.0
        let speakerDiff = abs(Double(run.media.speakerHint - request.media.speakerHint)) / 4.0
        let queueDiff = abs(Double(run.runtime.queueIndex - request.runtime.queueIndex)) / 6.0
        let cacheDiff = abs(run.runtime.cacheScore - request.runtime.cacheScore)

        var distance =
            (weights.durationWeight * durationDiff)
            + (weights.fpsWeight * fpsDiff)
            + (weights.resolutionWeight * resolutionDiff)
            + (weights.audioQualityWeight * audioDiff)
            + (weights.cutDensityWeight * cutDiff)
            + (weights.speakerWeight * speakerDiff)
            + (weights.queueWeight * queueDiff)
            + (weights.cacheWeight * cacheDiff)

        if run.variant.mode != request.variant.mode {
            distance += 0.90
        }
        if run.variant.sttQualityPreset != request.variant.sttQualityPreset {
            distance += 0.70
        }
        if run.variant.sttPrimary != request.variant.sttPrimary {
            distance += 1.10
        }
        if run.variant.sttSecondary != request.variant.sttSecondary {
            distance += 0.55
        }
        if run.variant.llmProvider != request.variant.llmProvider {
            distance += 0.45
        }
        if run.variant.llmModel != request.variant.llmModel {
            distance += 0.25
        }
        if run.variant.selectedVad != request.variant.selectedVad {
            distance += 0.25
        }
        if run.variant.selectedAudioAI != request.variant.selectedAudioAI {
            distance += 0.25
        }
        if run.variant.diarizationEnabled != request.variant.diarizationEnabled {
            distance += 0.20
        }

        var boost = 1.0
        if run.variantKey == request.variantKey {
            boost *= weights.variantExactBoost
        } else {
            if run.variant.mode == request.variant.mode {
                boost *= weights.modeMatchBoost
            }
            if run.variant.sttQualityPreset == request.variant.sttQualityPreset {
                boost *= weights.sttPresetMatchBoost
            }
            if run.variant.sttPrimary == request.variant.sttPrimary {
                boost *= weights.sttModelMatchBoost
            }
            if run.variant.llmProvider == request.variant.llmProvider && run.variant.llmModel == request.variant.llmModel {
                boost *= weights.llmMatchBoost
            }
            if run.variant.selectedVad == request.variant.selectedVad {
                boost *= weights.vadMatchBoost
            }
            if run.runtime.cacheState == request.runtime.cacheState {
                boost *= weights.cacheStateMatchBoost
            }
            if run.variant.diarizationEnabled == request.variant.diarizationEnabled {
                boost *= weights.diarizationMatchBoost
            }
        }
        if run.runtime.prefetchAudioHit == request.runtime.prefetchAudioHit && run.runtime.prefetchAudioHit {
            boost *= weights.warmCacheBoost
        }
        return recency * (1.0 / (1.0 + max(0.0, distance))) * boost
    }

    private static func heuristicSpeedRatio(request: RuntimeETARequest, weights: RuntimeETAWeights) -> Double {
        let media = request.media
        let variant = request.variant
        let runtime = request.runtime

        var ratio: Double
        switch variant.mode {
        case "fast":
            ratio = 0.18
        case "balanced":
            ratio = 0.28
        case "precise":
            ratio = 0.42
        case "stt":
            ratio = 0.14
        default:
            ratio = 0.30
        }

        if variant.sttEnsembleEnabled {
            ratio *= 1.22
        }
        if variant.llmProvider == "none" || variant.llmModel == "none" {
            ratio *= 0.74
        } else if variant.llmProvider.contains("openai") || variant.llmModel.lowercased().contains("codex") {
            ratio *= 0.92
        } else {
            ratio *= 1.12
        }
        if variant.diarizationEnabled {
            ratio *= 1.16
        }
        if variant.selectedAudioAI.lowercased().contains("clearvoice") {
            ratio *= 1.08
        } else if variant.selectedAudioAI.lowercased() == "none" {
            ratio *= 0.95
        }
        if variant.selectedVad.lowercased().contains("silero") {
            ratio *= 1.05
        } else if variant.selectedVad.lowercased().contains("ten") {
            ratio *= 0.98
        }

        let megaPixels = max(0.0, media.pixelCount) / 1_000_000.0
        if media.fps > 30.0 {
            ratio *= 1.0 + (((media.fps - 30.0) / 30.0) * weights.fpsWeight)
        }
        if megaPixels > 2.0 {
            ratio *= 1.0 + (((megaPixels - 2.0) / 2.0) * weights.resolutionWeight)
        }
        ratio *= 1.0 + (((100.0 - clamp(media.audioQualityScore, min: 0.0, max: 100.0)) / 100.0) * weights.audioQualityWeight)
        ratio *= 1.0 + ((min(media.cutDensityPerMin, 8.0) / 8.0) * weights.cutDensityWeight)
        ratio *= 1.0 + ((max(0.0, Double(media.speakerHint - 1)) / 3.0) * weights.speakerWeight)

        switch runtime.cacheState {
        case "warm":
            ratio *= weights.warmCacheMultiplier
        case "disabled":
            ratio *= weights.cacheDisabledMultiplier
        default:
            ratio *= weights.coldCacheMultiplier
        }
        if runtime.likelyWarmStart {
            ratio *= 0.94
        }
        if runtime.prefetchAudioHit {
            ratio *= 0.92
        }
        return max(0.02, ratio)
    }

    private static func relativeDiff(_ lhs: Double, _ rhs: Double) -> Double {
        let left = max(0.0, lhs)
        let right = max(0.0, rhs)
        let denom = max(1.0, max(left, right))
        return abs(left - right) / denom
    }

    private static func clamp(_ value: Double, min lower: Double, max upper: Double) -> Double {
        Swift.max(lower, Swift.min(upper, value))
    }

    private static func loadStore(at url: URL) -> RuntimeETAStore {
        let now = Date().timeIntervalSince1970
        let fallback = RuntimeETAStore(
            schema: schema,
            createdAt: now,
            updatedAt: now,
            algorithm: RuntimeETAAlgorithm(),
            weights: RuntimeETAWeights(),
            variants: [:],
            runs: []
        )
        guard FileManager.default.fileExists(atPath: url.path) else {
            return fallback
        }
        do {
            let data = try Data(contentsOf: url)
            let decoded = try JSONDecoder().decode(RuntimeETAStore.self, from: data)
            guard decoded.schema == schema else {
                return fallback
            }
            return decoded
        } catch {
            return fallback
        }
    }

    private static func saveStore(_ store: RuntimeETAStore, to url: URL) {
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true,
                attributes: nil
            )
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(store)
            try data.write(to: url, options: .atomic)
        } catch {
            // Best-effort cache/history persistence only.
        }
    }

    private static func makeRequest(payload: [String: Any]) -> RuntimeETARequest? {
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

    private static func normalizedMode(_ value: String) -> String {
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

    private static func normalizedCacheState(_ value: String) -> String {
        switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "warm":
            return "warm"
        case "disabled", "off", "none":
            return "disabled"
        default:
            return "cold"
        }
    }

    private static func stringValue(_ value: Any?, default defaultValue: String = "") -> String {
        guard let value else {
            return defaultValue
        }
        let text = String(describing: value).trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? defaultValue : text
    }

    private static func boolValue(_ value: Any?, default defaultValue: Bool = false) -> Bool {
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

    private static func doubleValue(_ value: Any?, default defaultValue: Double = 0.0) -> Double {
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

    private static func dictValue(_ value: Any?) -> [String: Any] {
        value as? [String: Any] ?? [:]
    }
}
