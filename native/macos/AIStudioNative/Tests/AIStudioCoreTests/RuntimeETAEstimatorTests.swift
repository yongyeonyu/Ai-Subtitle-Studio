import XCTest
@testable import AIStudioCore

final class RuntimeETAEstimatorTests: XCTestCase {
    func testRecentRunPullsPredictionTowardLatestVariantTiming() throws {
        let storeURL = temporaryStoreURL()
        defer { try? FileManager.default.removeItem(at: storeURL.deletingLastPathComponent()) }

        var payload = makePayload(storeURL: storeURL, mode: "precise", cacheState: "cold")
        payload["processing_time_sec"] = 120.0
        XCTAssertNil(RuntimeETAEstimator.record(payload: payload)["error"])

        let firstPrediction = doubleValue(RuntimeETAEstimator.predict(payload: payload)["predicted_processing_sec"])

        payload["processing_time_sec"] = 210.0
        XCTAssertNil(RuntimeETAEstimator.record(payload: payload)["error"])
        let secondPrediction = doubleValue(RuntimeETAEstimator.predict(payload: payload)["predicted_processing_sec"])

        XCTAssertGreaterThan(secondPrediction, firstPrediction + 20.0)
    }

    func testWarmCachePredictsFasterThanColdCache() throws {
        let storeURL = temporaryStoreURL()
        defer { try? FileManager.default.removeItem(at: storeURL.deletingLastPathComponent()) }

        let cold = RuntimeETAEstimator.predict(payload: makePayload(storeURL: storeURL, mode: "balanced", cacheState: "cold"))
        let warm = RuntimeETAEstimator.predict(payload: makePayload(storeURL: storeURL, mode: "balanced", cacheState: "warm", likelyWarmStart: true))

        XCTAssertLessThan(
            doubleValue(warm["predicted_processing_sec"]),
            doubleValue(cold["predicted_processing_sec"])
        )
    }

    func testDifferentVariantsKeepSeparateSpeedProfiles() throws {
        let storeURL = temporaryStoreURL()
        defer { try? FileManager.default.removeItem(at: storeURL.deletingLastPathComponent()) }

        var fast = makePayload(storeURL: storeURL, mode: "fast", cacheState: "cold")
        fast["processing_time_sec"] = 70.0
        XCTAssertNil(RuntimeETAEstimator.record(payload: fast)["error"])

        var precise = makePayload(storeURL: storeURL, mode: "precise", cacheState: "cold")
        precise["processing_time_sec"] = 210.0
        XCTAssertNil(RuntimeETAEstimator.record(payload: precise)["error"])

        let fastPrediction = RuntimeETAEstimator.predict(payload: fast)
        let precisePrediction = RuntimeETAEstimator.predict(payload: precise)

        XCTAssertLessThan(
            doubleValue(fastPrediction["predicted_processing_sec"]),
            doubleValue(precisePrediction["predicted_processing_sec"])
        )
    }

    private func temporaryStoreURL() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("runtime-eta-tests-\(UUID().uuidString)")
            .appendingPathComponent("time_history.json")
    }

    private func makePayload(
        storeURL: URL,
        mode: String,
        cacheState: String,
        likelyWarmStart: Bool = false
    ) -> [String: Any] {
        [
            "store_path": storeURL.path,
            "model_key": "QUALITY:STT:test|LLM:codex|DIA:X",
            "variant": [
                "mode": mode,
                "stt_quality_preset": mode,
                "stt_primary": "mlx-community/whisper-large-v3-mlx",
                "stt_secondary": "",
                "stt_ensemble_enabled": false,
                "llm_provider": "openai",
                "llm_model": "OpenAI Codex ChatGPT [구독/CLI/API키 불필요]",
                "diarization_enabled": false,
                "max_speakers": 1,
                "selected_vad": "silero",
                "selected_audio_ai": "deepfilter",
            ],
            "media": [
                "duration_sec": 300.0,
                "fps": 29.97,
                "width": 1920,
                "height": 1080,
                "pixel_count": 1920.0 * 1080.0,
                "audio_quality_score": 82.0,
                "cut_density_per_min": 1.5,
                "speaker_hint": 1,
                "is_audio_only": false,
            ],
            "runtime": [
                "queue_index": 0,
                "total_files": 1,
                "prefetch_audio_hit": false,
                "cut_boundary_cache_enabled": true,
                "vad_cache_enabled": true,
                "stt_runtime_reuse_enabled": true,
                "prefetch_ahead": 0,
                "auto_audio_tune_enabled": true,
                "cache_state": cacheState,
                "cut_boundary_cache_state": cacheState,
                "vad_cache_state": cacheState,
                "speaker_cache_state": "disabled",
                "likely_warm_start": likelyWarmStart,
                "cache_score": cacheState == "warm" ? 0.9 : 0.45,
            ],
        ]
    }

    private func doubleValue(_ value: Any?) -> Double {
        switch value {
        case let value as Double:
            return value
        case let value as NSNumber:
            return value.doubleValue
        default:
            return 0.0
        }
    }
}
