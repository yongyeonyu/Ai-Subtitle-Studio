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
