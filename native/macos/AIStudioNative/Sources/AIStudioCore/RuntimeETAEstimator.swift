import Foundation

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
}
