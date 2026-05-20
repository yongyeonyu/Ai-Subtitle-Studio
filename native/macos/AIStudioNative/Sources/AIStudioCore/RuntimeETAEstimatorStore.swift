import Foundation

extension RuntimeETAEstimator {
    static func updateVariantSummary(
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

    static func loadStore(at url: URL) -> RuntimeETAStore {
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

    static func saveStore(_ store: RuntimeETAStore, to url: URL) {
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
}
