import Foundation

extension RuntimeETAEstimator {
    static func estimate(request: RuntimeETARequest, store: RuntimeETAStore) -> (
        predictedSec: Double,
        predictedRatio: Double,
        confidence: Double,
        matchedVariantCount: Int,
        source: String
    ) {
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

    static func weightedAverage(
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

    static func neighborWeight(
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

    static func heuristicSpeedRatio(request: RuntimeETARequest, weights: RuntimeETAWeights) -> Double {
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

    static func relativeDiff(_ lhs: Double, _ rhs: Double) -> Double {
        let left = max(0.0, lhs)
        let right = max(0.0, rhs)
        let denom = max(1.0, max(left, right))
        return abs(left - right) / denom
    }

    static func clamp(_ value: Double, min lower: Double, max upper: Double) -> Double {
        Swift.max(lower, Swift.min(upper, value))
    }
}
